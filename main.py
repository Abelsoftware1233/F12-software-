"""
F12 Scanner - Backend API
Scant een publiek toegankelijke webpagina op:
  - Verstopte/blootgestelde secrets (API keys, tokens, etc.) in HTML/JS
  - Ontbrekende security headers
  - Basale TLS/certificaat info

BELANGRIJK: Deze tool haalt alleen op wat een gewone browser ook ophaalt
(HTML, gelinkte JS-bestanden, HTTP response headers, TLS-certificaat).
Er wordt niets "aangevallen": geen auth bypass, geen brute-force, geen
payloads. Gebruik dit alleen op sites waar je toestemming voor hebt.
"""

import re
import ssl
import socket
import ipaddress
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

app = FastAPI(title="F12 Scanner API", version="1.0.0")

# Pas dit aan naar je eigen frontend origin in productie
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://f12.abelsoftware123.com"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

REQUEST_TIMEOUT = 10.0
MAX_JS_FILES = 15
MAX_CONTENT_BYTES = 3_000_000  # 3 MB cap per file, voorkomt misbruik/DoS op eigen backend

# ---------------------------------------------------------------------------
# Secret detection patterns
# ---------------------------------------------------------------------------
# Elk patroon: (naam, compiled regex, ernst)
SECRET_PATTERNS = [
    ("AWS Access Key", re.compile(r"AKIA[0-9A-Z]{16}"), "hoog"),
    ("AWS Secret Key (heuristiek)", re.compile(r"(?i)aws_secret_access_key\s*[:=]\s*['\"][A-Za-z0-9/+=]{40}['\"]"), "hoog"),
    ("Google API Key", re.compile(r"AIza[0-9A-Za-z\-_]{35}"), "hoog"),
    ("Stripe Live Key", re.compile(r"sk_live_[0-9a-zA-Z]{24,}"), "kritiek"),
    ("Stripe Test Key", re.compile(r"sk_test_[0-9a-zA-Z]{24,}"), "medium"),
    ("Slack Token", re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}"), "hoog"),
    ("GitHub Token", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"), "hoog"),
    ("Generic Bearer Token", re.compile(r"(?i)bearer\s+[A-Za-z0-9\-_\.]{20,}"), "medium"),
    ("JWT", re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"), "medium"),
    ("Generic API Key pattern", re.compile(r"(?i)(api[_-]?key|apikey|secret[_-]?key|access[_-]?token)['\"]?\s*[:=]\s*['\"][A-Za-z0-9\-_\.]{16,}['\"]"), "medium"),
    ("Private Key Block", re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"), "kritiek"),
    ("Database Connection String", re.compile(r"(?i)(postgres|mysql|mongodb)(\+srv)?:\/\/[^\s'\"<>]+:[^\s'\"<>]+@[^\s'\"<>]+"), "kritiek"),
    ("Firebase Config Key", re.compile(r"(?i)firebaseConfig\s*=\s*\{"), "laag"),
]

COMMENT_PATTERNS = [
    re.compile(r"<!--(.*?)-->", re.DOTALL),
    re.compile(r"/\*(.*?)\*/", re.DOTALL),
    re.compile(r"(?m)//.*$"),
]

SECURITY_HEADERS = {
    "Content-Security-Policy": "Voorkomt XSS/data-injection door bronnen te beperken.",
    "Strict-Transport-Security": "Dwingt HTTPS af, voorkomt downgrade/MITM.",
    "X-Content-Type-Options": "Voorkomt MIME-sniffing aanvallen (verwacht: nosniff).",
    "X-Frame-Options": "Voorkomt clickjacking via iframes (verwacht: DENY/SAMEORIGIN).",
    "Referrer-Policy": "Beperkt lekken van URL-info via de Referer header.",
    "Permissions-Policy": "Beperkt toegang tot browser-features (camera, locatie, etc.).",
}


class ScanRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            v = "https://" + v
        parsed = urlparse(v)
        if not parsed.hostname:
            raise ValueError("Ongeldige URL")
        return v


def _block_private_targets(hostname: str) -> None:
    """Voorkom dat de backend als open proxy misbruikt wordt richting
    interne/lokale netwerken (SSRF-preventie)."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise HTTPException(status_code=400, detail="Kan hostname niet resolven")

    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise HTTPException(
                status_code=400,
                detail="Doel wijst naar een privé/lokaal adres — niet toegestaan.",
            )


def _find_secrets(text: str, source: str) -> list[dict]:
    findings = []
    for name, pattern, severity in SECRET_PATTERNS:
        for match in pattern.finditer(text):
            snippet = match.group(0)
            # Masker het midden van de match in de output, zodat het rapport
            # zelf niet opnieuw een lekkende bron wordt.
            if len(snippet) > 12:
                masked = snippet[:6] + "…" + snippet[-4:]
            else:
                masked = snippet[:2] + "…"
            findings.append({
                "type": name,
                "severity": severity,
                "source": source,
                "preview": masked,
                "line_context": _line_number(text, match.start()),
            })
    return findings


def _find_suspicious_comments(text: str, source: str) -> list[dict]:
    findings = []
    suspicious_words = re.compile(r"(?i)(todo|fixme|password|wachtwoord|secret|debug|hack|temp|do not|niet.*productie)")
    for pattern in COMMENT_PATTERNS:
        for match in pattern.finditer(text):
            comment_body = match.group(1) if match.groups() else match.group(0)
            if suspicious_words.search(comment_body):
                findings.append({
                    "type": "Verdachte comment",
                    "severity": "laag",
                    "source": source,
                    "preview": comment_body.strip()[:120],
                    "line_context": _line_number(text, match.start()),
                })
    return findings


def _line_number(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _extract_js_links(html: str, base_url: str) -> list[str]:
    srcs = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
    absolute = []
    for s in srcs:
        absolute.append(urljoin(base_url, s))
    # Ook source maps expliciet checken (vaak vergeten, kunnen source blootleggen)
    maps = re.findall(r"//[#@]\s*sourceMappingURL=([^\s]+)", html)
    for m in maps:
        absolute.append(urljoin(base_url, m))
    return absolute[:MAX_JS_FILES]


def _check_security_headers(headers: httpx.Headers) -> list[dict]:
    results = []
    for header, explanation in SECURITY_HEADERS.items():
        present = header in headers
        results.append({
            "header": header,
            "present": present,
            "value": headers.get(header),
            "explanation": explanation,
        })
    return results


def _check_tls(hostname: str, port: int = 443) -> dict:
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((hostname, port), timeout=REQUEST_TIMEOUT) as sock:
            with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                cipher = ssock.cipher()
                not_after = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
                days_left = (not_after - datetime.now(timezone.utc)).days
                return {
                    "valid": True,
                    "issuer": dict(x[0] for x in cert.get("issuer", [])),
                    "expires": cert["notAfter"],
                    "days_until_expiry": days_left,
                    "expiring_soon": days_left < 30,
                    "protocol": ssock.version(),
                    "cipher": cipher[0] if cipher else None,
                }
    except ssl.SSLCertVerificationError as e:
        return {"valid": False, "error": f"Certificaat validatie mislukt: {e}"}
    except (socket.timeout, socket.gaierror, ConnectionRefusedError, OSError) as e:
        return {"valid": False, "error": f"Kon geen TLS-verbinding maken: {e}"}


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/scan")
async def scan(request: ScanRequest):
    parsed = urlparse(request.url)
    _block_private_targets(parsed.hostname)

    findings: list[dict] = []
    scanned_sources: list[str] = []

    async with httpx.AsyncClient(follow_redirects=True, timeout=REQUEST_TIMEOUT) as client:
        try:
            resp = await client.get(request.url, headers={"User-Agent": "F12-Scanner/1.0"})
        except httpx.RequestError as e:
            raise HTTPException(status_code=400, detail=f"Kon URL niet ophalen: {e}")

        html = resp.text[:MAX_CONTENT_BYTES]
        scanned_sources.append(request.url)
        findings += _find_secrets(html, request.url)
        findings += _find_suspicious_comments(html, request.url)
        headers_result = _check_security_headers(resp.headers)

        js_urls = _extract_js_links(html, str(resp.url))
        for js_url in js_urls:
            try:
                js_resp = await client.get(js_url, headers={"User-Agent": "F12-Scanner/1.0"})
                if js_resp.status_code != 200:
                    continue
                js_text = js_resp.text[:MAX_CONTENT_BYTES]
                scanned_sources.append(js_url)
                findings += _find_secrets(js_text, js_url)
                findings += _find_suspicious_comments(js_text, js_url)
            except httpx.RequestError:
                continue

    tls_result = _check_tls(parsed.hostname) if parsed.scheme == "https" else {
        "valid": False, "error": "Site gebruikt geen HTTPS"
    }

    severity_order = {"kritiek": 0, "hoog": 1, "medium": 2, "laag": 3}
    findings.sort(key=lambda f: severity_order.get(f["severity"], 9))

    return {
        "target": request.url,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "sources_scanned": scanned_sources,
        "secret_findings": findings,
        "security_headers": headers_result,
        "tls": tls_result,
        "summary": {
            "total_findings": len(findings),
            "critical": sum(1 for f in findings if f["severity"] == "kritiek"),
            "high": sum(1 for f in findings if f["severity"] == "hoog"),
        },
    }
