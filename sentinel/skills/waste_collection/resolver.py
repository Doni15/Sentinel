"""
Resolver adresy → kompletný rozvrh zvozu (plast/papier/bio + komunál).

Deterministické: dátumy pochádzajú výlučne z parserov (triedený PDF) a z výpočtu
komunálu (deň + parita + interval). LLM sa tu nepoužíva. Spája:
  - parser.py            → plast/papier/bio podľa mestskej časti
  - komunal_parser.py    → komunál podľa ulice + čísla
  - strana 2 triedeného  → mapovanie ulíc na zóny Zobor 1–4
Párovanie vstupu prebieha cez normalizované adresy (viď normalize.py).
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field

import pdfplumber

from . import komunal_parser, parser
from .normalize import (
    PART_TO_TRIEDENY, canon_part, canon_street, normalize, normalize_num,
    normalize_zone_key,
)

ICON = {"plast": "🟡", "papier": "🔵", "bio": "🟤"}


@dataclass
class ResolveResult:
    cast: str
    ulica: str
    cislo: str | None
    triedeny_area: str | None
    triedeny: dict[str, datetime.date | None] = field(default_factory=dict)
    komunal: list[dict] = field(default_factory=list)  # {popis, next, record}
    warnings: list[str] = field(default_factory=list)


class WasteResolver:
    """Načíta oba PDF raz a odpovedá na dopyty (čisto z dát, bez LLM)."""

    def __init__(self, triedeny_pdf: str, komunal_pdf: str):
        self._triedeny = parser.parse(triedeny_pdf)
        self._komunal = komunal_parser.parse(komunal_pdf)
        self._zones = self._load_zones(triedeny_pdf)

    @staticmethod
    def _load_zones(triedeny_pdf: str) -> dict[str, str]:
        cols = {1: "Zobor 1", 4: "Zobor 2", 7: "Zobor 3", 10: "Zobor 4",
                13: "Zobor 3"}
        zones: dict[str, str] = {}
        with pdfplumber.open(triedeny_pdf) as pdf:
            table = pdf.pages[1].extract_tables()[0]
        for row in table[1:]:
            for ci, zone in cols.items():
                if ci < len(row) and row[ci] and row[ci].strip():
                    key = normalize_zone_key(row[ci])
                    if key:
                        zones[key] = zone
        return zones

    def _resolve_triedeny_area(self, cast: str, ulica: str,
                               warnings: list[str]) -> str | None:
        key = canon_part(cast)
        if key in PART_TO_TRIEDENY:
            return PART_TO_TRIEDENY[key]
        if "zobor" in key:
            zone = self._zones.get(canon_street(ulica))
            if zone:
                return zone
            warnings.append(
                f"Ulica '{ulica}' sa nenašla v zónach Zobor 1–4 — over zaradenie."
            )
            return None
        if "cerman" in key:  # samotný Čermáň bez Dolný/Horný
            warnings.append(
                "Čermáň: triedený delí na 'Dolný Čermáň/Šúdol' a 'Horný Čermáň' — "
                "spýtaj sa používateľa, ktorá časť (napr. 'Dolný Čermáň')."
            )
            return None
        warnings.append(f"Neznáma mestská časť '{cast}' pre triedený odpad.")
        return None

    def resolve(self, cast: str, ulica: str, cislo: str | None = None,
                today: datetime.date | None = None) -> ResolveResult:
        from ...core import timeutil
        today = today or timeutil.today()
        warnings: list[str] = []

        area = self._resolve_triedeny_area(cast, ulica, warnings)
        triedeny: dict[str, datetime.date | None] = {}
        if area:
            for wt in ("plast", "papier", "bio"):
                up = sorted(c.date for c in self._triedeny.collections
                            if c.area == area and c.waste_type == wt
                            and c.date >= today)
                triedeny[wt] = up[0] if up else None

        # komunál: zhoda podľa ulice + voľná zhoda časti (Dolný Čermáň ~ Čermáň)
        ncast = canon_part(cast)
        nulica = canon_street(ulica)
        ncislo = normalize_num(cislo) if cislo else None
        cand = [r for r in self._komunal
                if normalize(r.ulica) == nulica
                and (normalize(r.cast) == ncast
                     or normalize(r.cast) in ncast or ncast in normalize(r.cast))]
        if ncislo:
            exact = [r for r in cand if normalize_num(r.cislo) == ncislo]
            if exact:
                cand = exact
        komunal: list[dict] = []
        seen = set()
        for r in cand:
            if r.describe() in seen:
                continue
            seen.add(r.describe())
            komunal.append({
                "popis": r.describe(),
                "next": komunal_parser.next_date(r, today),
                "record": r,
            })
        if not cand:
            warnings.append(
                f"Komunál: adresa '{ulica} {cislo or ''}, {cast}' nenájdená."
            )
        elif cislo and len(komunal) > 1:
            warnings.append(
                "Na tomto čísle je viac nádob — spýtaj sa, ktorá je tvoja."
            )

        return ResolveResult(
            cast=cast, ulica=ulica, cislo=cislo,
            triedeny_area=area, triedeny=triedeny,
            komunal=komunal, warnings=warnings,
        )

    def events(self, cast: str, ulica: str, cislo: str | None,
               start: datetime.date, end: datetime.date,
               komunal_desc: str | None = None) -> list[dict]:
        """Všetky zvozy (všetkých typov) v intervale [start, end], zoradené.
        Ak je daný `komunal_desc`, komunál sa obmedzí na zvolenú nádobu."""
        res = self.resolve(cast, ulica, cislo, today=start)
        events: list[dict] = []
        if res.triedeny_area:
            for wt in ("plast", "papier", "bio"):
                for c in self._triedeny.collections:
                    if (c.area == res.triedeny_area and c.waste_type == wt
                            and start <= c.date <= end):
                        events.append({"date": c.date, "type": wt,
                                       "label": f"{ICON[wt]} {wt}"})
        for k in res.komunal:
            if komunal_desc and k["popis"] != komunal_desc:
                continue
            for d in komunal_parser.generate_dates(k["record"], start, end):
                events.append({"date": d, "type": "komunál",
                               "label": "⚫ komunál"})
        events.sort(key=lambda e: e["date"])
        return events
