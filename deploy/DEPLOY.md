# Sentinel — produkčné nasadenie bezpečnostných zmien

⚠️ Tieto kroky sa robia na serveri až **po potvrdení používateľom**. Lokálny kód
a testy sú hotové (66/66). Produkcia, rotácia tokenu, apt upgrade a reboot čakajú.

## A. Aktualizácia kódu + závislostí
1. Nahrať aktuálny kód do `/opt/sentinel` (bez `.venv`, `data/*.db`, `.env`).
2. `/opt/sentinel/.venv/bin/pip install -r requirements.txt` (pinned + setuptools≥78.1.1).
3. `systemctl restart sentinel` po prepnutí na nový unit (krok B).

## B. Non-root používateľ + hardened systemd (#2)
```bash
useradd --system --home /opt/sentinel --shell /usr/sbin/nologin sentinel
chown -R sentinel:sentinel /opt/sentinel
chmod 600 /opt/sentinel/.env
install -m644 /opt/sentinel/deploy/sentinel.service /etc/systemd/system/sentinel.service
systemctl daemon-reload && systemctl restart sentinel
systemd-analyze security sentinel    # over skóre (cieľ: výrazne nižšie ako predtým)
```

## C. Práva DB (#4)
```bash
chmod 600 /opt/sentinel/data/sentinel.db   # kód to už vynucuje pri štarte tiež
```

## D. Automatická záloha (#5)
```bash
chmod +x /opt/sentinel/deploy/backup_sentinel_db.sh
install -m644 /opt/sentinel/deploy/sentinel-backup.service /etc/systemd/system/
install -m644 /opt/sentinel/deploy/sentinel-backup.timer   /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now sentinel-backup.timer
systemctl start sentinel-backup.service    # skúšobná záloha
ls -l /opt/sentinel/data/backups           # over 600/700 práva
```

## E. Token rotácia (#1) — až po nasadení redakcie logov
1. Over, že token už NIE je v nových logoch:
   `journalctl -u sentinel --since "5 min ago" | grep -c ':AA'  # → 0`
2. Vyzvať používateľa na `/revoke` + `/token` v BotFather → nový token.
3. Vložiť nový token do `/opt/sentinel/.env`, `systemctl restart sentinel`.
4. Overiť getMe/polling. (Token nikde nevypisovať.)

## F. Aktualizácie systému + reboot (#7) — vyžaduje potvrdenie
```bash
apt-get update && apt-get upgrade -y     # ~103 balíkov
reboot                                   # nový kernel 5.15.0-181
```
Po reštarte: over sentinel.service, UFW, fail2ban, polling.

## G. Allowlist + rate limit (#8) — voliteľné, vyžaduje potvrdenie
Do `/opt/sentinel/.env` pridať `ALLOWED_USER_IDS=...` a/alebo `RATE_LIMIT_ENABLED=1`,
potom `systemctl restart sentinel`. Defaultne sú VYPNUTÉ.

## Verifikačný checklist po každom zásahu
- `/opt/sentinel/.venv/bin/python -m pytest -q`  (alebo na CI)
- `systemd-analyze security sentinel`
- token sa nenachádza v nových logoch
- Telegram getMe/polling OK, DB integrity (`PRAGMA integrity_check`), scheduler beží
- `ufw status`, `fail2ban-client status sshd`
