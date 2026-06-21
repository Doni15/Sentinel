#!/bin/bash
# Deploy spúšťaný GitHub Actions cez SSH (forced command v authorized_keys).
# Kľúč na serveri vie spustiť IBA tento skript — nič iné (obmedzenie blast radius).
# Git + pip bežia ako neprivilegovaný user `sentinel`; root len reštartne službu.
set -euo pipefail
REPO=/opt/sentinel
cd "$REPO"
runuser -u sentinel -- git fetch -q origin main
runuser -u sentinel -- git reset --hard -q origin/main
runuser -u sentinel -- "$REPO/.venv/bin/pip" install -q -r requirements.txt
systemctl restart sentinel
echo "deployed $(runuser -u sentinel -- git -C "$REPO" rev-parse --short HEAD)"
