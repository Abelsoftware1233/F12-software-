#!/usr/bin/env bash
#
# deploy.sh — Automatiseert de installatie van de F12 Scanner op deze server.
#
# Aannames:
#   - Ubuntu/Debian met apt, python3, nginx al geïnstalleerd
#   - DNS A-record voor f12.abelsoftware123.com wijst al naar dit IP
#   - Dit script wordt uitgevoerd vanuit de map waar backend/, frontend/
#     en deploy/ naast elkaar staan (dus de uitgepakte zip)
#   - Je draait dit met sudo: sudo bash deploy.sh
#
# Her-uitvoerbaar: je kunt dit script opnieuw draaien na een code-update,
# het zet dependencies en config gewoon opnieuw neer.

set -euo pipefail

DOMAIN="f12.abelsoftware123.com"
APP_DIR="/var/www/f12"
SERVICE_NAME="f12-backend"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log()  { echo -e "\033[1;34m[deploy]\033[0m $*"; }
warn() { echo -e "\033[1;33m[warn]\033[0m $*"; }
err()  { echo -e "\033[1;31m[error]\033[0m $*" >&2; }

if [[ $EUID -ne 0 ]]; then
  err "Dit script moet als root/sudo draaien: sudo bash deploy.sh"
  exit 1
fi

if [[ ! -f "$SCRIPT_DIR/backend/main.py" ]]; then
  err "Kan backend/main.py niet vinden naast dit script. Draai dit vanuit de uitgepakte projectmap."
  exit 1
fi

# ---------------------------------------------------------------------------
# 1. Systeemcheck: benodigde tools
# ---------------------------------------------------------------------------
log "Controleer benodigde tools..."
for cmd in python3 nginx; do
  if ! command -v "$cmd" &>/dev/null; then
    err "$cmd is niet geïnstalleerd. Installeer dit eerst (apt install $cmd) en draai het script opnieuw."
    exit 1
  fi
done

if ! python3 -m venv --help &>/dev/null; then
  warn "python3-venv lijkt te ontbreken, probeer te installeren..."
  apt-get update -qq && apt-get install -y python3-venv
fi

# ---------------------------------------------------------------------------
# 2. Mappenstructuur + bestanden kopiëren
# ---------------------------------------------------------------------------
log "Zet mappenstructuur op onder $APP_DIR..."
mkdir -p "$APP_DIR/backend" "$APP_DIR/frontend"

cp "$SCRIPT_DIR/backend/main.py" "$APP_DIR/backend/"
cp "$SCRIPT_DIR/backend/requirements.txt" "$APP_DIR/backend/"
cp "$SCRIPT_DIR/frontend/index.html" "$APP_DIR/frontend/"
cp "$SCRIPT_DIR/frontend/script.js" "$APP_DIR/frontend/"

# ---------------------------------------------------------------------------
# 3. Python venv + dependencies
# ---------------------------------------------------------------------------
log "Zet Python venv op en installeer dependencies..."
if [[ ! -d "$APP_DIR/backend/venv" ]]; then
  python3 -m venv "$APP_DIR/backend/venv"
fi
"$APP_DIR/backend/venv/bin/pip" install --upgrade pip -q
"$APP_DIR/backend/venv/bin/pip" install -r "$APP_DIR/backend/requirements.txt" -q

# ---------------------------------------------------------------------------
# 4. Eigenaarschap voor www-data (systemd service draait hieronder)
# ---------------------------------------------------------------------------
log "Zet eigenaarschap naar www-data..."
chown -R www-data:www-data "$APP_DIR"

# ---------------------------------------------------------------------------
# 5. Systemd service installeren
# ---------------------------------------------------------------------------
log "Installeer systemd service..."
cp "$SCRIPT_DIR/deploy/f12-backend.service" "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME" -q
systemctl restart "$SERVICE_NAME"

sleep 1
if systemctl is-active --quiet "$SERVICE_NAME"; then
  log "Backend service draait."
else
  err "Backend service is niet gestart. Bekijk logs met: journalctl -u $SERVICE_NAME -n 50"
  exit 1
fi

# ---------------------------------------------------------------------------
# 6. Nginx config
# ---------------------------------------------------------------------------
log "Zet nginx config neer..."
cp "$SCRIPT_DIR/deploy/nginx-f12.conf" "/etc/nginx/sites-available/${DOMAIN}"

if [[ ! -L "/etc/nginx/sites-enabled/${DOMAIN}" ]]; then
  ln -s "/etc/nginx/sites-available/${DOMAIN}" "/etc/nginx/sites-enabled/${DOMAIN}"
fi

# De meegeleverde nginx config verwacht al een geldig Let's Encrypt cert.
# Als dat er nog niet is, testen we de config niet blind door — anders
# faalt nginx -t gegarandeerd op de ontbrekende cert-paden.
if [[ -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]]; then
  nginx -t
  systemctl reload nginx
  log "Nginx config actief."
else
  warn "Geen Let's Encrypt certificaat gevonden voor ${DOMAIN}."
  warn "Draai eerst: certbot --nginx -d ${DOMAIN}"
  warn "en daarna: nginx -t && systemctl reload nginx"
  warn "(De site-config staat al klaar in /etc/nginx/sites-available/${DOMAIN})"
fi

# ---------------------------------------------------------------------------
# 7. Health check
# ---------------------------------------------------------------------------
log "Test backend health endpoint..."
if curl -fsS http://127.0.0.1:8000/api/health >/dev/null; then
  log "Backend health check OK."
else
  warn "Health check op 127.0.0.1:8000 gaf geen OK terug — controleer de logs."
fi

echo
log "Klaar. Als het certificaat al actief is, ga naar: https://${DOMAIN}"
log "Logs bekijken: journalctl -u ${SERVICE_NAME} -f"
