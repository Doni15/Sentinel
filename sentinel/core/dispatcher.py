"""
Notification dispatcher (Sentinel core). Berie notifikácie od skillov, deduplikuje
cez `notifications_log` a odosiela ich cez injektovaný `send_func`.

`send_func(user_id, text)` je async (Telegram adapter dodá `bot.send_message`).
V testoch sa dá podstrčiť fake, ktorý správy len zbiera.
"""
from __future__ import annotations

from typing import Awaitable, Callable, Iterable

from .db import Database


class NotificationDispatcher:
    def __init__(self, db: Database,
                 send_func: Callable[[int, str], Awaitable[None]]):
        self.db = db
        self.send = send_func

    async def dispatch(self, notifications: Iterable) -> int:
        """Pošle nové notifikácie, preskočí už odoslané. Vráti počet odoslaných."""
        sent = 0
        for n in notifications:
            date_iso = n.date.isoformat()
            new_items = [it for it in n.items
                         if not self.db.was_notified(n.user_id, date_iso, it["type"])]
            if not new_items:
                continue
            payload = _replace_items(n, new_items)
            await self.send(n.user_id, payload.message())
            for it in new_items:
                self.db.mark_notified(n.user_id, date_iso, it["type"])
            sent += 1
        return sent


def _replace_items(notification, items):
    """Kópia notifikácie len s novými položkami (kvôli správe)."""
    from ..skills.waste_collection.notifications import Notification
    return Notification(notification.user_id, notification.date, items)
