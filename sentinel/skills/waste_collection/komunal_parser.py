"""
Parser harmonogramu zvozu KOMUNÁLNEHO odpadu (čierny smetiak) NKS Nitra.

Zdroj: PDF "Stanovištia v meste" (~212 strán, ~14 000 adries). Na rozdiel od
triedeného odpadu komunál NEMÁ pevný kalendár — každá adresa má:
  - deň v týždni (pondelok ... piatok)
  - paritu týždňa (párny / nepárny ISO-týždeň), len pri 1x14
  - interval (1x7 týždenne, 1x14 každý druhý týždeň, 2x7 / 3x7 viackrát týždenne)

Z toho sa konkrétne dátumy **dopočítavajú** (`generate_dates`). Parsovanie je
deterministické (pdfplumber, bez OCR/LLM).

⚠️ Konvencia parity: predpokladáme párny/nepárny = párne/nepárne číslo ISO-týždňa
(slovenský štandard). Oplatí sa raz overiť proti reálnemu zvozu.
"""
from __future__ import annotations

import datetime
import hashlib
import re
from dataclasses import dataclass

import pdfplumber

# korene názvov dní -> Python weekday (pondelok=0)
_WEEKDAY_ROOTS = {
    "pondel": 0, "utor": 1, "stred": 2, "štvrt": 3, "stvrt": 3, "piat": 4,
}
# krátke tokeny v kombináciách (napr. "pon,str,pia")
_WEEKDAY_SHORT = {
    "pon": 0, "ut": 1, "str": 2, "štv": 3, "stv": 3, "pia": 4,
}
WEEKDAY_NAME = ["pondelok", "utorok", "streda", "štvrtok", "piatok",
                "sobota", "nedeľa"]

HEADER_FIRST_CELL = "Základný deň zvozu"


@dataclass
class KomunalRecord:
    day_raw: str            # pôvodný text, napr. "nepár.utorok"
    weekdays: tuple[int, ...]
    parity: str | None      # 'even' | 'odd' | None
    interval: str           # '1x7' | '1x14 dní' | '2x7' | '3x7'
    cast: str               # mestská časť (bez "Nitra - ")
    ulica: str
    cislo: str

    def describe(self) -> str:
        dni = ", ".join(WEEKDAY_NAME[w] for w in self.weekdays)
        par = {"even": "párny", "odd": "nepárny"}.get(self.parity, "")
        return f"{par + ' ' if par else ''}{dni} ({self.interval})".strip()


def parse_day(raw: str) -> tuple[tuple[int, ...], str | None]:
    """Rozparsuje pole 'Základný deň zvozu' na (weekdays, parita)."""
    raw = (raw or "").strip()
    if "," in raw:  # kombinácia viacerých dní (2x7 / 3x7), bez parity
        wds = set()
        for tok in re.split(r"[,\s]+", raw.lower()):
            for root, wd in _WEEKDAY_SHORT.items():
                if tok.startswith(root):
                    wds.add(wd)
                    break
        return tuple(sorted(wds)), None
    parity = None
    low = raw.lower()
    if low.startswith("pár"):
        parity = "even"
    elif low.startswith("nepár"):
        parity = "odd"
    for root, wd in _WEEKDAY_ROOTS.items():
        if root in low:
            return (wd,), parity
    return tuple(), parity


def generate_dates(rec: KomunalRecord, start: datetime.date,
                   end: datetime.date) -> list[datetime.date]:
    """Vygeneruje konkrétne dátumy zvozu v intervale [start, end]."""
    out: list[datetime.date] = []
    d = start
    while d <= end:
        if d.weekday() in rec.weekdays:
            if rec.parity is None:
                out.append(d)
            else:
                iso_even = d.isocalendar()[1] % 2 == 0
                if (rec.parity == "even") == iso_even:
                    out.append(d)
        d += datetime.timedelta(days=1)
    return out


def next_date(rec: KomunalRecord, today: datetime.date) -> datetime.date | None:
    horizon = today + datetime.timedelta(days=60)
    dates = generate_dates(rec, today, horizon)
    return dates[0] if dates else None


def file_hash(pdf_path: str) -> str:
    h = hashlib.sha256()
    with open(pdf_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def parse(pdf_path: str) -> list[KomunalRecord]:
    """Prečíta celé PDF a vráti zoznam adresných záznamov."""
    records: list[KomunalRecord] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                for row in table:
                    if not row or len(row) < 5:
                        continue
                    if row[0] == HEADER_FIRST_CELL:
                        continue
                    day_raw, interval, mesto, ulica, cislo = row[:5]
                    if not (day_raw and mesto and ulica):
                        continue
                    weekdays, parity = parse_day(day_raw)
                    if not weekdays:
                        continue  # nepodarilo sa určiť deň -> preskoč (zriedkavé)
                    cast = mesto.replace("Nitra -", "").strip()
                    records.append(KomunalRecord(
                        day_raw=day_raw.strip(),
                        weekdays=weekdays,
                        parity=parity,
                        interval=(interval or "").strip(),
                        cast=cast,
                        ulica=ulica.strip(),
                        cislo=(cislo or "").strip(),
                    ))
    if not records:
        raise ValueError("Z komunál PDF sa nevyparsovala žiadna adresa.")
    return records


if __name__ == "__main__":
    import sys
    from collections import Counter

    path = (sys.argv[1] if len(sys.argv) > 1
            else "data/pdfs/Komunal-Stanovistia-2026.pdf")
    recs = parse(path)
    print(f"Adresných záznamov: {len(recs)}")
    print(f"Mestských častí: {len(set(r.cast for r in recs))}")
    print(f"Intervaly: {dict(Counter(r.interval for r in recs))}")
    # ukážka: Staré mesto, Andreja Šulgana
    today = datetime.date(2026, 6, 7)
    print("\nUkážka — Staré mesto, ANDREJA ŠULGANA:")
    seen = set()
    for r in recs:
        if r.cast == "Staré mesto" and r.ulica.upper() == "ANDREJA ŠULGANA":
            if r.describe() in seen:
                continue
            seen.add(r.describe())
            print(f"  {r.describe():35} -> najbližší: "
                  f"{next_date(r, today):%a %d.%m.%Y}")
