"""
Scheduler (Sentinel core). Registruje periodické úlohy skillov. Teraz: denné
notifikácie waste skillu o `hour:minute` v pásme Europe/Bratislava.
"""
from __future__ import annotations

import datetime

from telegram.ext import ContextTypes

from . import timeutil
from .dispatcher import NotificationDispatcher


def register_daily_notifications(job_queue, waste_service,
                                 dispatcher: NotificationDispatcher,
                                 hour: int, minute: int) -> None:
    async def _job(ctx: ContextTypes.DEFAULT_TYPE):
        notifications = waste_service.daily_notifications(timeutil.today())
        await dispatcher.dispatch(notifications)

    job_queue.run_daily(
        _job,
        time=datetime.time(hour=hour, minute=minute, tzinfo=timeutil.TZ),
    )


def register_source_check(job_queue, updater, on_change, hour: int) -> None:
    """Denná kontrola zdrojových PDF (self-scheduling). `updater.check_due()`
    väčšinou nič nerobí; pri reálnej zmene zavolá `on_change()` (reload dát)."""
    log = __import__("logging").getLogger("sentinel.scheduler")

    async def _job(ctx: ContextTypes.DEFAULT_TYPE):
        results = updater.check_due(timeutil.today())
        changed = False
        for r in results:
            if r.status == "failed":
                log.warning("Zdroj %s: %s", r.source, r.message)
            elif r.status == "updated":
                changed = True
                log.info("Zdroj %s aktualizovaný (%s)", r.source, r.message)
        if changed:
            on_change()
            log.info("Dáta znovu načítané po aktualizácii zdroja.")

    job_queue.run_daily(
        _job, time=datetime.time(hour=hour, minute=0, tzinfo=timeutil.TZ))
