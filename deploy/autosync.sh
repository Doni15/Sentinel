#!/bin/bash
# Auto-sync /opt/sentinel z GitHubu: ak je na origin/main nový commit, stiahni ho,
# doinštaluj závislosti a reštartni službu. Spúšťa systemd timer (sentinel-sync.timer).
# Git + pip bežia ako neprivilegovaný user `sentinel`; root len reštartne službu.
set -euo pipefail
REPO=/opt/sentinel
cd "$REPO"

runuser -u sentinel -- git fetch -q origin main
LOCAL=$(runuser -u sentinel -- git rev-parse HEAD)
REMOTE=$(runuser -u sentinel -- git rev-parse origin/main)

if [ "$LOCAL" = "$REMOTE" ]; then
    exit 0   # nič nové
fi

logger -t sentinel-sync "nový commit ${REMOTE:0:8} — aktualizujem"
runuser -u sentinel -- git reset --hard -q origin/main
runuser -u sentinel -- "$REPO/.venv/bin/pip" install -q -r requirements.txt
systemctl restart sentinel
logger -t sentinel-sync "aktualizované na ${REMOTE:0:8}, služba reštartnutá"
