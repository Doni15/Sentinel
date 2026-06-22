#!/bin/bash
# Deploy spúšťaný GitHub Actions cez SSH (forced command v authorized_keys).
# Kľúč na serveri vie spustiť IBA tento skript — nič iné (obmedzenie blast radius).
# Git + pip bežia ako neprivilegovaný user `sentinel`; root len synchro + reštart.
set -euo pipefail
REPO=/opt/sentinel
cd "$REPO"
runuser -u sentinel -- git fetch -q origin main
runuser -u sentinel -- git reset --hard -q origin/main
runuser -u sentinel -- "$REPO/.venv/bin/pip" install -q -r requirements.txt

# --- Hermes skill: synchronizuj z repa do hermes skills priečinka ---
SKILL_SRC="$REPO/hermes_skill/nitra-waste"
SKILL_DST="/home/hermes/.hermes/skills/nitra-waste"
if [ -d "$SKILL_SRC" ] && id hermes >/dev/null 2>&1; then
    mkdir -p /home/hermes/.hermes/skills
    rm -rf "$SKILL_DST"
    cp -a "$SKILL_SRC" "$SKILL_DST"
    chown -R hermes:hermes "$SKILL_DST"
    chmod +x "$SKILL_DST/scripts/query.py" 2>/dev/null || true
    # reštartni Hermes gateway, nech načíta zmenu skillu
    runuser -l hermes -c 'export XDG_RUNTIME_DIR=/run/user/1000; systemctl --user restart hermes-gateway' 2>/dev/null || true
    echo "skill synced -> $SKILL_DST"

    # --- Strážca prístupu: upozorní admina na Telegram pri pokuse o kontakt ---
    WATCH="$SKILL_DST/scripts/access_watch.py"
    if [ -f "$WATCH" ]; then
        HUID=$(id -u hermes)
        cat > /etc/systemd/system/waste-access-watch.service <<EOF
[Unit]
Description=Sentinel — strážca prístupu (upozorní admina na pokus o kontakt s botom)
After=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 $WATCH
Environment=HERMES_ENV=/home/hermes/.hermes/.env
Environment=WASTE_ADMIN_CHAT_ID=677758312
Environment=HERMES_UID=$HUID
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
        systemctl daemon-reload
        systemctl enable --now waste-access-watch.service 2>/dev/null || true
        systemctl restart waste-access-watch.service 2>/dev/null || true
        echo "access-watch installed/restarted"
    fi
fi

# starý bot je disabled; reštartni len ak ešte beží
systemctl is-active --quiet sentinel && systemctl restart sentinel || true
echo "deployed $(runuser -u sentinel -- git -C "$REPO" rev-parse --short HEAD)"
