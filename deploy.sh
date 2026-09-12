#!/usr/bin/env bash
#
# deploy.sh — Automatiseert de installatie van de F12 Scanner op deze server.
# Structuur: alle bestanden staan plat in de repo-root, naast dit script:
#   main.py, requirements.txt, index.html, script.js,
#   f12-backend.service, nginx-f12.conf
#
# Draai met: sudo bash deploy.sh
# Her-uitvoerbaar na git pull + code-update.

set -euo pipefail

DOMAIN="f12.abelsoftware123.com"
APP_DIR="/var/www/f12"
SERVICE_NAME="f12-backend"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log()  { echo -e "\033[1;34m[deploy]\033[0m $*"; }
warn() { echo -e "\033[1;33m[warn]\033[0m $*"; }
err()  { echo -e "\033[1;31m[error]\033[0m $*" >&2; }

if [[ $EUID -ne 0 ]]; then
  err "Dit script moet als root/sudo draaien: sudo bash deploy.sh"
  exit 1
fi

if [[ ! -f "$SCRIPT_DIR/main.py" ]]; then
  err "Kan main.py niet vinden naast dit script. Draai dit vanuit de f12-software repo-root."
  exit 1
fi

log "Controleer benodigde tools..."
for cmd in python3 nginx; do
  if ! command -v "$cmd" &>/dev/null; then
    err "$cmd is niet geïnstalleerd. Installeer dit eerst en draai het script opnieuw."
    exit 1
  fi
done

if ! python3 -m venv --help &>/dev/null; then
  warn "python3-venv lijkt te ontbreken, probeer te installeren..."
  apt-get update -qq && apt-get install -y python3-venv
fi

log "Zet mappenstructuur op onder $APP_DIR..."
mkdir -p "$APP_DIR"

# Kopieer alle relevante bestanden plat naar de app-directory
cp "$SCRIPT_DIR/main.py" "$APP_DIR/main.py"
cp "$SCRIPT_DIR/requirements.txt" "$APP_DIR/requirements.txt"
cp "$SCRIPT_DIR/index.html" "$APP_DIR/index.html"
cp "$SCRIPT_DIR/script.js" "$APP_DIR/script.js"

log "Zet Python venv op en installeer dependencies..."
if [[ ! -d "$APP_DIR/venv" ]]; then
  python3 -m venv "$APP_DIR/venv"
fi
"$APP_DIR/venv/bin/pip" install --upgrade pip -q
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" -q

log "Zet eigenaarschap naar www-data..."
chown -R www-data:www-data "$APP_DIR"

log "Installeer systemd service..."
cp "$SCRIPT_DIR/f12-backend.service" "/etc/systemd/system/${SERVICE_NAME}.service"
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

log "Zet nginx config neer..."
cp "$SCRIPT_DIR/nginx-f12.conf" "/etc/nginx/sites-available/${DOMAIN}"

if [[ ! -L "/etc/nginx/sites-enabled/${DOMAIN}" ]]; then
  ln -s "/etc/nginx/sites-available/${DOMAIN}" "/etc/nginx/sites-enabled/${DOMAIN}"
fi

if [[ -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]]; then
  nginx -t
  systemctl reload nginx
  log "Nginx config actief."
else
  warn "Geen Let's Encrypt certificaat gevonden voor ${DOMAIN}."
  warn "Draai eerst: certbot --nginx -d ${DOMAIN}"
  warn "en daarna: nginx -t && systemctl reload nginx"
fi

log "Test backend health endpoint..."
if curl -fsS http://127.0.0.1:8000/api/health >/dev/null; then
  log "Backend health check OK."
else
  warn "Health check gaf geen OK terug — controleer de logs."
fi

echo
log "Klaar. Als het certificaat al actief is, ga naar: https://${DOMAIN}"
log "Logs bekijken: journalctl -u ${SERVICE_NAME} -f"
