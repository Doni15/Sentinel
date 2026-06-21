"""Vstupný bod Sentinela — načíta waste skill, spustí Telegram core + self-update."""
from __future__ import annotations

import sys

import config
from sentinel.core.access import AccessGuard, parse_ids
from sentinel.core.db import Database
from sentinel.core.scheduler import register_source_check
from sentinel.core.telegram_adapter import build_application
from sentinel.skills.waste_collection.resolver import WasteResolver
from sentinel.skills.waste_collection.service import WasteService
from sentinel.skills.waste_collection.updater import SourceSpec, WasteUpdater


def main() -> None:
    if not config.TELEGRAM_TOKEN:
        sys.exit("❌ Chýba TELEGRAM_TOKEN — vlož ho do .env (vzor v .env.example).")

    print("⏳ Načítavam harmonogramy z PDF ...")
    resolver = WasteResolver(config.TRIEDENY_PDF, config.KOMUNAL_PDF)
    db = Database(config.DB_PATH)
    waste = WasteService(resolver, subscriptions=db)
    print("✅ Dáta načítané. Spúšťam Sentinel (Ctrl+C ukončí).")

    guard = AccessGuard(
        allowed_ids=parse_ids(config.ALLOWED_USER_IDS),
        rate_enabled=config.RATE_LIMIT_ENABLED,
        rate_max=config.RATE_LIMIT_MAX,
        rate_window=config.RATE_LIMIT_WINDOW_SEC)
    app = build_application(config.TELEGRAM_TOKEN, waste, db,
                            config.NOTIFY_HOUR, config.NOTIFY_MINUTE, guard)

    # self-update: denná kontrola zdrojov NKS (koná len keď nastal next_check_date)
    specs = [SourceSpec(s["key"], s["page_url"], s["link_pattern"],
                        s["active_path"], config.ARCHIVE_DIR)
             for s in config.WASTE_SOURCES]
    updater = WasteUpdater(db, specs)

    def reload_data() -> None:
        waste.set_resolver(WasteResolver(config.TRIEDENY_PDF, config.KOMUNAL_PDF))

    register_source_check(app.job_queue, updater, reload_data,
                          config.SOURCE_CHECK_HOUR)

    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
