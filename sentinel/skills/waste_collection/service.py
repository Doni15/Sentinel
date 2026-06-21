"""
Service API waste skillu — jediné rozhranie, ktoré Sentinel core volá.

Exportuje čisté funkcie nad deterministickým resolverom:
  - resolve_address(cast, ulica, cislo)
  - events_for_address(cast, ulica, cislo, start, end)
  - answer_waste_query(user_profile, text)
  - daily_notifications(today)

DÔLEŽITÉ: dátumy pochádzajú VÝLUČNE z resolvera. LLM (cez `intent_parser`) smie
len pochopiť, na čo sa používateľ pýta (typ odpadu / časové okno). Nikdy negeneruje
dátumy.
"""
from __future__ import annotations

import datetime
from typing import Callable, Protocol

from ...core import timeutil
from .notifications import (
    Notification, fmt_bins, fmt_date, group_by_date, pluralize_kontajner,
    relative,
)
from .resolver import ICON, WasteResolver


class _Profile(Protocol):
    cast: str
    ulica: str
    cislo: str | None
    komunal_desc: str | None


class _SubscriptionSource(Protocol):
    def all_subscriptions(self) -> list: ...


# --- intent z otázky (keyword; sem sa neskôr napojí lokálny LLM) ---
_KEYWORDS = {
    "plast": "plast", "zlt": "plast",
    "papier": "papier", "modr": "papier",
    "bio": "bio", "hnedy": "bio",
    "komunal": "komunál", "zmesov": "komunál", "ciern": "komunál",
}


def parse_waste_intent(text: str) -> str | None:
    """Vráti typ odpadu, na ktorý sa otázka pýta, alebo None (= všetko).
    Náhrada za LLM: keyword matching nad normalizovaným textom."""
    from .normalize import normalize
    n = normalize(text)
    for key, wt in _KEYWORDS.items():
        if key in n:
            return wt
    return None


class WasteService:
    """Doménový skill — Sentinel ho drží ako jednu inštanciu."""

    def __init__(self, resolver: WasteResolver,
                 subscriptions: _SubscriptionSource | None = None,
                 intent_parser: Callable[[str], str | None] = parse_waste_intent):
        self.resolver = resolver
        self.subs = subscriptions
        self.intent_parser = intent_parser

    def set_resolver(self, resolver: WasteResolver) -> None:
        """Vymení resolver za nový (po stiahnutí aktualizovaného PDF)."""
        self.resolver = resolver

    # --- čisté funkcie nad adresou ---
    def resolve_address(self, cast: str, ulica: str, cislo: str | None = None):
        return self.resolver.resolve(cast, ulica, cislo, today=timeutil.today())

    def events_for_address(self, cast: str, ulica: str, cislo: str | None,
                           start: datetime.date, end: datetime.date,
                           komunal_desc: str | None = None) -> list[dict]:
        return self.resolver.events(cast, ulica, cislo, start, end, komunal_desc)

    # --- odpoveď na otázku (dátumy len z resolvera) ---
    def answer_waste_query(self, user_profile: _Profile, text: str) -> str:
        today = timeutil.today()
        end = today + datetime.timedelta(days=40)
        events = self.events_for_address(
            user_profile.cast, user_profile.ulica, user_profile.cislo,
            today, end, getattr(user_profile, "komunal_desc", None))
        if not events:
            return "Pre tvoju adresu nemám najbližšie žiadny zvoz."
        wanted = self.intent_parser(text)
        if wanted:
            nxt = next((e for e in events if e["type"] == wanted), None)
            if not nxt:
                return f"Pre {wanted} nemám najbližšie termín."
            # ak v ten istý deň idú aj iné nádoby, spomeň ich
            same_day = [e for e in events
                        if e["date"] == nxt["date"] and e["type"] != wanted]
            extra = (f" (v ten deň aj {fmt_bins(same_day)} — spolu "
                     f"{pluralize_kontajner(len(same_day) + 1)})"
                     if same_day else "")
            return (f"{nxt['label']}: {fmt_date(nxt['date'])} "
                    f"({relative(nxt['date'], today)}).{extra}")
        # všeobecná otázka → najbližší DEŇ so všetkými nádobami v ňom
        d, evs = group_by_date(events)[0]
        if len(evs) > 1:
            return (f"Najbližší zvoz {fmt_date(d)} ({relative(d, today)}): "
                    f"{fmt_bins(evs)} — pristav {pluralize_kontajner(len(evs))}.")
        return (f"Najbližší zvoz — {fmt_bins(evs)}: {fmt_date(d)} "
                f"({relative(d, today)}).")

    # --- denné notifikácie (kandidáti; dispatcher rieši dedup + odoslanie) ---
    def daily_notifications(self, today: datetime.date | None = None
                            ) -> list[Notification]:
        if self.subs is None:
            return []
        today = today or timeutil.today()
        tomorrow = today + datetime.timedelta(days=1)
        out: list[Notification] = []
        for sub in self.subs.all_subscriptions():
            events = self.events_for_address(
                sub.cast, sub.ulica, sub.cislo, tomorrow, tomorrow,
                sub.komunal_desc)
            if events:
                out.append(Notification(sub.user_id, tomorrow, events))
        return out
