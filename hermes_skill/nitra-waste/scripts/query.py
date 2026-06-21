#!/usr/bin/env python3
"""
Light query nad predpočítaným waste_data.json — BEZ pdfplumber (stdlib only).
Vstup: adresa (mestská časť, ulica, číslo). Výstup: najbližšie zvozy zoskupené
po dňoch (vrátane počtu kontajnerov v jeden deň) + JSON pre agenta.

Dáta sú deterministické z PDF; tento skript NIKDY nevymýšľa dátumy.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from normalize import (  # noqa: E402
    PART_TO_TRIEDENY, canon_part, canon_street, normalize, normalize_num,
    split_street_number,
)

DATA = json.load(open(os.path.join(HERE, "waste_data.json"), encoding="utf-8"))
ICON = {"plast": "🟡", "papier": "🔵", "bio": "🟤", "komunál": "⚫"}
SK_DAYS = ["pondelok", "utorok", "streda", "štvrtok", "piatok", "sobota", "nedeľa"]


def _date(s: str) -> datetime.date:
    return datetime.date.fromisoformat(s)


def fmt_date(d: datetime.date) -> str:
    return f"{SK_DAYS[d.weekday()]} {d.day}.{d.month}.{d.year}"


def relative(d: datetime.date, today: datetime.date) -> str:
    n = (d - today).days
    return {0: "dnes", 1: "zajtra"}.get(n, f"o {n} dní")


def pluralize(n: int) -> str:
    if n == 1:
        return "1 kontajner"
    if 2 <= n <= 4:
        return f"{n} kontajnery"
    return f"{n} kontajnerov"


def resolve_area(cast: str, ulica: str) -> str | None:
    key = canon_part(cast)
    if key in PART_TO_TRIEDENY:
        return PART_TO_TRIEDENY[key]
    if "zobor" in key:
        return DATA["zones"].get(canon_street(ulica))
    return None  # napr. samotný "Čermáň" je nejednoznačný (Dolný/Horný)


def gen_komunal(rec: dict, start: datetime.date,
                end: datetime.date) -> list[datetime.date]:
    out, d, wd = [], start, set(rec["weekdays"])
    while d <= end:
        if d.weekday() in wd:
            if rec["parity"] is None:
                out.append(d)
            else:
                iso_even = d.isocalendar()[1] % 2 == 0
                if (rec["parity"] == "even") == iso_even:
                    out.append(d)
        d += datetime.timedelta(days=1)
    return out


def events(cast, ulica, cislo, start, end):
    area = resolve_area(cast, ulica)
    evs = []
    if area:
        for c in DATA["collections"]:
            if c["area"] == area:
                d = _date(c["date"])
                if start <= d <= end:
                    evs.append({"date": d, "type": c["type"]})
    ncast, nulica = canon_part(cast), canon_street(ulica)
    ncislo = normalize_num(cislo) if cislo else None
    cand = [r for r in DATA["komunal"]
            if normalize(r["ulica"]) == nulica
            and (normalize(r["cast"]) == ncast
                 or normalize(r["cast"]) in ncast or ncast in normalize(r["cast"]))]
    if ncislo:
        ex = [r for r in cand if normalize_num(r["cislo"]) == ncislo]
        if ex:
            cand = ex
    seen = set()
    for r in cand:
        if r["popis"] in seen:
            continue
        seen.add(r["popis"])
        for d in gen_komunal(r, start, end):
            evs.append({"date": d, "type": "komunál"})
    evs.sort(key=lambda e: e["date"])
    return evs, area, sorted(seen)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cast", required=True)
    ap.add_argument("--ulica", required=True)
    ap.add_argument("--cislo", default="")
    ap.add_argument("--days", type=int, default=40)
    args = ap.parse_args()

    street, num_in_street = split_street_number(args.ulica)
    cislo = args.cislo.strip() or num_in_street

    today = datetime.date.today()
    end = today + datetime.timedelta(days=args.days)
    evs, area, komunal = events(args.cast, street, cislo, today, end)

    addr = f"{street}{(' ' + cislo) if cislo else ''}, {args.cast}"
    if not evs:
        out = {"address": addr, "found": False,
               "message": f"Pre adresu {addr} som nenašiel žiadny zvoz. "
                          "Skontroluj mestskú časť alebo ulicu."}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    by_date: dict[datetime.date, list[str]] = {}
    for e in evs:
        by_date.setdefault(e["date"], []).append(e["type"])
    groups = sorted(by_date.items())

    lines, struct = [], []
    for d, types in groups:
        labels = " + ".join(f"{ICON[t]} {t}" for t in types)
        extra = f" — {pluralize(len(types))}" if len(types) > 1 else ""
        lines.append(f"{fmt_date(d)} ({relative(d, today)}): {labels}{extra}")
        struct.append({"date": d.isoformat(), "weekday": SK_DAYS[d.weekday()],
                       "in_days": (d - today).days, "types": types,
                       "count": len(types)})

    out = {
        "address": addr,
        "found": True,
        "valid_to": DATA["valid_to"],
        "upcoming": struct,
        "human_sk": "Najbližšie zvozy pre " + addr + ":\n" + "\n".join(lines),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
