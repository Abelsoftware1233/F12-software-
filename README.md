# f12-software

F12 Scanner — een tool om je eigen website te controleren op per ongeluk
blootgestelde API keys/secrets in HTML/JS, ontbrekende security headers,
en TLS-configuratie.

## Structuur

```
f12-software/
├── backend/           FastAPI app (secret scanner + headers + TLS check)
│   ├── main.py
│   └── requirements.txt
├── frontend/          Statische frontend (URL invoeren, resultaat tonen)
│   ├── index.html
│   └── script.js
├── deploy/            Deployment configs
│   ├── deploy.sh              installatiescript
│   ├── f12-backend.service    systemd unit
│   ├── nginx-f12.conf         nginx reverse proxy config
│   └── DEPLOY.md              volledige handmatige instructies
└── .gitignore
```

## Snel deployen op de server

```bash
git clone git@github.com:jouw-gebruikersnaam/f12-software.git
cd f12-software
chmod +x deploy/deploy.sh
sudo bash deploy/deploy.sh
```

Zie `deploy/DEPLOY.md` voor de volledige handmatige stappen (o.a. certbot
voor TLS) en beveiligingsnotities.

## Belangrijk

- Gebruik dit alleen op sites waar je zelf eigenaar/beheerder van bent of
  expliciete toestemming voor hebt.
- De backend blokkeert scans naar private/interne IP-adressen (SSRF-preventie).
- Zet nooit echte secrets in deze repo — alleen testdata.
