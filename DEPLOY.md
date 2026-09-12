# F12 Scanner — Deployment op f12.abelsoftware123.com

Aannames: Ubuntu/Debian server, DNS A-record voor `f12.abelsoftware123.com`
wijst al naar dit IP, nginx en python3 zijn geïnstalleerd.

## Snelle route: deploy.sh

Pak de zip uit op de server en draai:

```bash
sudo bash deploy.sh
```

Dit script doet automatisch stap 1 t/m 6 hieronder: mappen aanmaken,
bestanden kopiëren, venv + dependencies installeren, eigenaarschap zetten,
de systemd service installeren en starten, en de nginx config activeren
(als er al een Let's Encrypt certificaat is). Het script is veilig om
opnieuw te draaien na een code-update.

Als er nog geen certificaat is, slaat het script het activeren van HTTPS
over en meldt dat je eerst `certbot --nginx -d f12.abelsoftware123.com`
moet draaien (zie stap 5). Handmatige stappen hieronder blijven relevant
als je liever alles zelf controleert of iets specifieks wilt aanpassen.

## 1. Mappenstructuur op de server

```bash
sudo mkdir -p /var/www/f12/backend /var/www/f12/frontend
sudo chown -R $USER:$USER /var/www/f12
```

Kopieer de bestanden:
- `backend/main.py` en `backend/requirements.txt` → `/var/www/f12/backend/`
- `frontend/index.html` en `frontend/script.js` → `/var/www/f12/frontend/`

## 2. Python venv + dependencies

```bash
cd /var/www/f12/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
deactivate
```

Test lokaal of hij opstart:
```bash
/var/www/f12/backend/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
# in een andere terminal:
curl http://127.0.0.1:8000/api/health
# verwacht: {"status":"ok"}
# stop daarna met Ctrl+C
```

## 3. Eigenaarschap voor de systemd service

De service draait als `www-data`, dus:
```bash
sudo chown -R www-data:www-data /var/www/f12
```

## 4. Systemd service installeren

```bash
sudo cp deploy/f12-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now f12-backend
sudo systemctl status f12-backend
```

Logs volgen:
```bash
sudo journalctl -u f12-backend -f
```

## 5. TLS-certificaat (Let's Encrypt / certbot)

Als certbot nog niet geïnstalleerd is:
```bash
sudo apt install certbot python3-certbot-nginx
```

Zorg dat er eerst een basale HTTP-only nginx config staat (of gebruik
certbot's standalone mode), dan:
```bash
sudo certbot --nginx -d f12.abelsoftware123.com
```

Dit vult automatisch de `ssl_certificate` paden in nginx in.

## 6. Nginx config

```bash
sudo cp deploy/nginx-f12.conf /etc/nginx/sites-available/f12.abelsoftware123.com
sudo ln -s /etc/nginx/sites-available/f12.abelsoftware123.com /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## 7. CORS check

In `backend/main.py` staat `allow_origins=["https://f12.abelsoftware123.com"]`.
Als frontend en backend op hetzelfde domein draaien (wat hier het geval is,
via de nginx `/api/` proxy) is dit vooral een extra beveiligingslaag — de
browser stuurt dan geen cross-origin requests, maar het is goed om dit
overeen te laten komen met je uiteindelijke domein.

## 8. Testen

Ga naar `https://f12.abelsoftware123.com`, voer een URL in (bijvoorbeeld je
eigen testpagina met de verstopte API key) en klik Scan.

## Updates uitrollen

```bash
# nieuwe backend code kopiëren, dan:
sudo systemctl restart f12-backend
```

## Beveiligingsnotities

- De backend blokkeert scans naar private/interne IP-adressen (SSRF-preventie)
  — dus je kunt hem niet gebruiken om je eigen interne netwerk te scannen.
- Overweeg rate limiting toe te voegen (zie commentaar onderin de nginx config)
  als de tool publiek bereikbaar is, zodat hij niet als gratis scanning-proxy
  misbruikt kan worden door derden.
- De tool logt zelf geen gevonden secrets naar disk — resultaten gaan alleen
  terug naar de aanvrager via de API response.
