# f12-software

F12 Scanner — een tool om je eigen website te controleren op per ongeluk
blootgestelde API keys/secrets in HTML/JS, ontbrekende security headers,
en TLS-configuratie.

Let op: in deze versie staan alle bestanden plat in de root (geen
submappen). Pas paden in deploy.sh, nginx-f12.conf en f12-backend.service
aan als je alsnog een andere structuur op de server wilt.

## Bestanden

- backend_main.py         FastAPI app (secret scanner + headers + TLS check)
- backend_requirements.txt
- frontend_index.html     Statische frontend
- frontend_script.js
- deploy.sh               installatiescript
- f12-backend.service     systemd unit
- nginx-f12.conf          nginx reverse proxy config
- DEPLOY.md               volledige handmatige instructies

## Belangrijk

- Gebruik dit alleen op sites waar je zelf eigenaar/beheerder van bent of
  expliciete toestemming voor hebt.
- De backend blokkeert scans naar private/interne IP-adressen (SSRF-preventie).
- Zet nooit echte secrets in deze repo — alleen testdata.
