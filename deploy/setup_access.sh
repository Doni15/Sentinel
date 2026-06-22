#!/bin/bash
# Jednorazová inštalácia strážcu prístupu (access_watch.py) na serveri.
# Spusti ako root NA SERVERI:  bash setup_access.sh
#
# Vytvorí systemd službu waste-access-watch, ktorá sleduje journal Hermes gateway
# a pri pokuse neoprávneného usera pošle adminovi na Telegram upozornenie s /allow.
set -euo pipefail

SKILL_DIR=/home/hermes/.hermes/skills/nitra-waste/scripts
WATCH=$SKILL_DIR/access_watch.py
HERMES_UID=$(id -u hermes)

if [ ! -f "$WATCH" ]; then
    echo "CHYBA: $WATCH neexistuje — najprv nasaď skill cez CI (git push)." >&2
    exit 1
fi

cat > /etc/systemd/system/waste-access-watch.service <<EOF
[Unit]
Description=Sentinel — strážca prístupu (upozorní admina na pokus o kontakt s botom)
After=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 $WATCH
Environment=HERMES_ENV=/home/hermes/.hermes/.env
Environment=WASTE_ADMIN_CHAT_ID=677758312
Environment=HERMES_UID=$HERMES_UID
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now waste-access-watch.service
sleep 1
systemctl --no-pager --full status waste-access-watch.service | head -12 || true

echo
echo "Test upozornenia (mal by ti prísť Telegram):"
HERMES_ENV=/home/hermes/.hermes/.env WASTE_ADMIN_CHAT_ID=677758312 \
    /usr/bin/python3 "$WATCH" --test || true

echo
echo "Hotovo. Sleduj log:  journalctl -u waste-access-watch -f"
