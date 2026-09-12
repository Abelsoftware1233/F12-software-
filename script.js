// F12 Scanner - frontend logic
// Praat met de FastAPI backend op hetzelfde domein onder /api

const API_BASE = ""; // leeg = zelfde origin, nginx proxied /api naar de backend

const form = document.getElementById("scanForm");
const urlInput = document.getElementById("urlInput");
const scanBtn = document.getElementById("scanBtn");
const statusEl = document.getElementById("status");
const resultsEl = document.getElementById("results");

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const url = urlInput.value.trim();
  if (!url) return;

  setLoading(true);
  resultsEl.innerHTML = "";

  try {
    const res = await fetch(`${API_BASE}/api/scan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Onbekende fout" }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }

    const data = await res.json();
    renderResults(data);
  } catch (err) {
    resultsEl.innerHTML = `<div class="error-box">⚠️ ${escapeHtml(err.message)}</div>`;
  } finally {
    setLoading(false);
  }
});

function setLoading(loading) {
  scanBtn.disabled = loading;
  scanBtn.textContent = loading ? "Scannen…" : "Scan";
  statusEl.textContent = loading ? "Bezig met scannen — dit kan een paar seconden duren…" : "";
}

function renderResults(data) {
  const parts = [];

  parts.push(renderSummary(data));
  parts.push(renderFindings(data.secret_findings));
  parts.push(renderHeaders(data.security_headers));
  parts.push(renderTls(data.tls));
  parts.push(renderSources(data.sources_scanned));

  resultsEl.innerHTML = parts.join("");
}

function renderSummary(data) {
  const s = data.summary;
  return `
    <div class="card">
      <h2>Overzicht</h2>
      <div class="summary-row">
        <div class="summary-stat"><div class="num">${s.total_findings}</div><div class="label">Totaal</div></div>
        <div class="summary-stat"><div class="num" style="color:var(--critical)">${s.critical}</div><div class="label">Kritiek</div></div>
        <div class="summary-stat"><div class="num" style="color:var(--high)">${s.high}</div><div class="label">Hoog</div></div>
      </div>
    </div>
  `;
}

function renderFindings(findings) {
  if (!findings || findings.length === 0) {
    return `<div class="card"><h2>Gevonden secrets</h2><div class="empty-state">✅ Geen verdachte patronen gevonden.</div></div>`;
  }

  const items = findings.map(f => `
    <div class="finding ${f.severity}">
      <div class="finding-top">
        <strong>${escapeHtml(f.type)}</strong>
        <span class="badge ${f.severity}">${f.severity}</span>
      </div>
      <div class="finding-source">${escapeHtml(f.source)} — regel ${f.line_context}</div>
      <div class="finding-preview">${escapeHtml(f.preview)}</div>
    </div>
  `).join("");

  return `<div class="card"><h2>Gevonden secrets (${findings.length})</h2>${items}</div>`;
}

function renderHeaders(headers) {
  if (!headers) return "";
  const rows = headers.map(h => `
    <div class="header-row">
      <span>${escapeHtml(h.header)}</span>
      <span class="${h.present ? 'ok' : 'missing'}">${h.present ? '✅ Aanwezig' : '❌ Ontbreekt'}</span>
    </div>
  `).join("");
  return `<div class="card"><h2>Security headers</h2>${rows}</div>`;
}

function renderTls(tls) {
  if (!tls) return "";
  if (!tls.valid) {
    return `<div class="card"><h2>TLS / HTTPS</h2><div class="error-box">${escapeHtml(tls.error || "TLS-check mislukt")}</div></div>`;
  }
  return `
    <div class="card">
      <h2>TLS / HTTPS</h2>
      <div class="header-row"><span>Protocol</span><span>${escapeHtml(tls.protocol || "-")}</span></div>
      <div class="header-row"><span>Verloopt op</span><span>${escapeHtml(tls.expires || "-")}</span></div>
      <div class="header-row"><span>Dagen tot verlopen</span><span class="${tls.expiring_soon ? 'missing' : 'ok'}">${tls.days_until_expiry}</span></div>
    </div>
  `;
}

function renderSources(sources) {
  if (!sources || sources.length === 0) return "";
  const items = sources.map(s => `<div class="finding-source" style="margin-bottom:6px;">${escapeHtml(s)}</div>`).join("");
  return `<div class="card"><h2>Gescande bronnen (${sources.length})</h2>${items}</div>`;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
                             }
