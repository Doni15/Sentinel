"""Centrálna konfigurácia Sentinela (načítaná z .env)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PDF_DIR = DATA_DIR / "pdfs"
ARCHIVE_DIR = str(PDF_DIR / "archive")

# aktívne zdrojové PDF (scraper ich obnovuje pri zmene na NKS)
TRIEDENY_PDF = str(PDF_DIR / "Harmonogram-TZ-2026-27.pdf")
KOMUNAL_PDF = str(PDF_DIR / "Komunal-Stanovistia-2026.pdf")

# zdroje pre scraper: kde na NKS hľadať odkaz na PDF (dynamicky, nie natvrdo URL)
WASTE_SOURCES = [
    {"key": "triedeny",
     "page_url": "https://www.nks.sk/triedenie-odpadu-obcania-nitra",
     "link_pattern": r"Harmonogram-TZ",
     "active_path": TRIEDENY_PDF},
    {"key": "komunal",
     "page_url": "https://www.nks.sk/harmonogram-zvozu",
     "link_pattern": r"Stanovi",
     "active_path": KOMUNAL_PDF},
]

# hodina dennej kontroly zdrojov (scraper). Väčšinou nič nerobí — koná len keď
# nastal next_check_date daného zdroja (self-scheduling).
SOURCE_CHECK_HOUR = int(os.getenv("SOURCE_CHECK_HOUR", "3"))

# DB spoločná pre Sentinel core.
DB_PATH = str(DATA_DIR / "sentinel.db")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")

# čas dennej notifikácie (deň pred zvozom), 24h formát
NOTIFY_HOUR = int(os.getenv("NOTIFY_HOUR", "18"))
NOTIFY_MINUTE = int(os.getenv("NOTIFY_MINUTE", "0"))

# --- prístupová kontrola (#8) — DEFAULTNE VYPNUTÁ ---
# rodinný allowlist: prázdne = povolení všetci. Aktivuj zoznamom chat ID:
#   ALLOWED_USER_IDS=111111111,222222222
ALLOWED_USER_IDS = os.getenv("ALLOWED_USER_IDS", "")
# rate limiting: 0/false = vypnuté
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "0").lower() in (
    "1", "true", "yes", "on")
RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", "20"))
RATE_LIMIT_WINDOW_SEC = int(os.getenv("RATE_LIMIT_WINDOW_SEC", "60"))
