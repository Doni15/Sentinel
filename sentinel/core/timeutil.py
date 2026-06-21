"""Čas a dátum vždy v slovenskom pásme (Europe/Bratislava).

Nikde v kóde nepoužívať `datetime.date.today()` — to berie pásmo servera (často
UTC) a notifikácie by chodili v nesprávny čas. Vždy `timeutil.today()`.
"""
from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Bratislava")


def now() -> datetime.datetime:
    return datetime.datetime.now(TZ)


def today() -> datetime.date:
    return now().date()
