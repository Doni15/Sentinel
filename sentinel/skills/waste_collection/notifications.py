"""Notification provider waste skillu — dátové objekty a slovenské formátovanie.

Skill produkuje `Notification` objekty; samotné odoslanie a anti-duplikáciu rieši
Sentinel core dispatcher (notifications_log).
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass

_SK_DAYS = ["pondelok", "utorok", "streda", "štvrtok", "piatok",
            "sobota", "nedeľa"]
_SK_DAYS_SHORT = ["po", "ut", "st", "št", "pi", "so", "ne"]


def fmt_date(d: datetime.date) -> str:
    return f"{_SK_DAYS[d.weekday()]} {d.day}.{d.month}.{d.year}"


def fmt_date_short(d: datetime.date) -> str:
    return f"{_SK_DAYS_SHORT[d.weekday()]} {d.day}.{d.month}."


def relative(d: datetime.date, today: datetime.date) -> str:
    n = (d - today).days
    return {0: "dnes", 1: "zajtra"}.get(n, f"o {n} dní")


def pluralize_kontajner(n: int) -> str:
    """Slovenské skloňovanie: 1 kontajner, 2-4 kontajnery, 5+ kontajnerov."""
    if n == 1:
        return "1 kontajner"
    if 2 <= n <= 4:
        return f"{n} kontajnery"
    return f"{n} kontajnerov"


def group_by_date(events: list[dict]) -> list[tuple[datetime.date, list[dict]]]:
    """Zoskupí eventy (z resolver.events) podľa dátumu, zoradené vzostupne.
    Vďaka tomu vieme povedať „v jeden deň 2 kontajnery"."""
    by_date: dict[datetime.date, list[dict]] = {}
    for e in events:
        by_date.setdefault(e["date"], []).append(e)
    return sorted(by_date.items())


def fmt_bins(items: list[dict]) -> str:
    """„🔵 papier + 🟤 bio" zo zoznamu eventov."""
    return " + ".join(it["label"] for it in items)


@dataclass
class Notification:
    """Jedna pripomienka pre jedného používateľa na jeden deň."""
    user_id: int
    date: datetime.date
    items: list[dict]  # eventy z resolver.events (label, type, date)

    @property
    def waste_types(self) -> list[str]:
        return [it["type"] for it in self.items]

    def message(self) -> str:
        typy = fmt_bins(self.items)
        n = len(self.items)
        kus = f"  ({pluralize_kontajner(n)})" if n > 1 else ""
        return (
            "👋 Tu *Sentinel*, tvoj smetiarsky špión.\n\n"
            f"Zajtra ({fmt_date_short(self.date)}) prídu po:\n"
            f"{typy}{kus}\n\n"
            "Nech ťa auto nezastihne s plným košom doma. 🚛💨"
        )
