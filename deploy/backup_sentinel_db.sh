#!/bin/bash
# Bezpečná online záloha SQLite DB Sentinela (#5).
#  - online backup cez stdlib sqlite3 (konzistentné aj počas behu bota),
#  - obmedzené práva (umask 077 → súbory 600, adresár 700),
#  - retencia: ponechá posledných RETENTION dní, staršie zmaže.
# Spúšťa sa cez systemd timer (sentinel-backup.timer) pod používateľom sentinel.
set -euo pipefail
umask 077

DB="${SENTINEL_DB:-/opt/sentinel/data/sentinel.db}"
BACKUP_DIR="${SENTINEL_BACKUP_DIR:-/opt/sentinel/data/backups}"
RETENTION="${SENTINEL_BACKUP_RETENTION:-14}"

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

STAMP="$(date +%Y%m%d-%H%M%S)"
DEST="$BACKUP_DIR/sentinel-$STAMP.db"

# online backup cez Python stdlib (sqlite3 CLI nemusí byť nainštalovaný)
/opt/sentinel/.venv/bin/python - "$DB" "$DEST" <<'PY'
import sqlite3, sys
src, dst = sys.argv[1], sys.argv[2]
with sqlite3.connect(src) as s, sqlite3.connect(dst) as d:
    s.backup(d)
PY

gzip -9 "$DEST"
chmod 600 "$DEST.gz"

# retencia: zmaž zálohy staršie ako RETENTION dní
find "$BACKUP_DIR" -name 'sentinel-*.db.gz' -type f -mtime "+$RETENTION" -delete

echo "záloha OK: $DEST.gz (retencia ${RETENTION} dní)"
