"""
Parser harmonogramu zvozu odpadu NKS Nitra (PDF -> štruktúrované dáta).

Stratégia: PDF je pravidelná mriežka (strana 1), ktorú pdfplumber spoľahlivo
prečíta podľa súradníc. Parsovanie je preto plne **deterministické** — žiadny
LLM, žiadne hádanie. Súčasťou je self-validácia, ktorá označí nezvyčajné údaje.

Mriežka strany 1:
  riadok 0  -> roky (2026 / 2027)
  riadok 1  -> mesiace (Apríl ... Marec)
  stĺpec 0  -> mestská časť (môže byť viacriadková: "Kalvária\nStaré mesto")
  stĺpec 1  -> typ odpadu (PLA / PAP / BIO)
  bunky     -> dni v mesiaci (BIO ~2x mesačne)
"""
from __future__ import annotations

import datetime
import hashlib
from dataclasses import dataclass, field

import pdfplumber

# --- konštanty harmonogramu ---
MONTHS = {
    "Január": 1, "Február": 2, "Marec": 3, "Apríl": 4, "Máj": 5, "Jún": 6,
    "Júl": 7, "August": 8, "September": 9, "Október": 10, "November": 11,
    "December": 12,
}
WASTE_TYPES = {"PLA": "plast", "PAP": "papier", "BIO": "bio"}

# očakávaný cyklus zvozu v dňoch (pre self-validáciu)
EXPECTED_CYCLE = {"plast": 28, "papier": 28, "bio": 14}
CYCLE_TOLERANCE = 4  # ± dní, kým to označíme za anomáliu


@dataclass
class Collection:
    """Jeden zvoz: kedy, čo, pre ktorú mestskú časť."""
    area: str
    waste_type: str       # 'plast' | 'papier' | 'bio'
    date: datetime.date


@dataclass
class ParseResult:
    collections: list[Collection]
    valid_from: datetime.date
    valid_to: datetime.date
    areas: list[str]
    source_hash: str
    pdf_moddate: str | None
    warnings: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return (
            f"ParseResult({len(self.collections)} zvozov, "
            f"{len(self.areas)} častí, "
            f"{self.valid_from:%d.%m.%Y}–{self.valid_to:%d.%m.%Y}, "
            f"{len(self.warnings)} upozornení)"
        )


def file_hash(pdf_path: str) -> str:
    """SHA-256 obsahu PDF — na detekciu zmeny harmonogramu."""
    h = hashlib.sha256()
    with open(pdf_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _column_lookup(cols: list[tuple[int, int]], col_index: int) -> int:
    """Pre daný stĺpec vráti hodnotu (rok alebo mesiac) podľa najbližšej
    hlavičky vľavo. `cols` je [(col_index, hodnota), ...] zoradené vzostupne."""
    value = cols[0][1]
    for ci, v in cols:
        if col_index >= ci:
            value = v
    return value


def parse(pdf_path: str) -> ParseResult:
    """Prečíta PDF a vráti štruktúrované, zvalidované dáta.

    Vyvolá ValueError, ak má PDF neočakávaný formát (zmena štruktúry zo
    strany NKS) — to je signál na manuálnu kontrolu, nie tichú chybu.
    """
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        tables = page.extract_tables()
        moddate = pdf.metadata.get("ModDate")
        if not tables:
            raise ValueError("V PDF sa nenašla žiadna tabuľka — zmenil sa formát?")
        table = tables[0]

    if len(table) < 3:
        raise ValueError(f"Tabuľka má len {len(table)} riadkov — neočakávaný formát.")

    year_row, month_row = table[0], table[1]
    month_cols = [(i, MONTHS[v]) for i, v in enumerate(month_row) if v in MONTHS]
    year_cols = [(i, int(v)) for i, v in enumerate(year_row)
                 if v and v.strip().isdigit()]

    if len(month_cols) != 12:
        raise ValueError(
            f"Našlo sa {len(month_cols)} mesiacov namiesto 12 — zmenil sa formát?"
        )
    if not year_cols:
        raise ValueError("Nenašiel sa žiadny rok v hlavičke — zmenil sa formát?")

    collections: list[Collection] = []
    warnings: list[str] = []
    area: str | None = None

    for row in table[2:]:
        if row[0] and row[0].strip():
            area = row[0].replace("\n", " / ").strip()
        waste = WASTE_TYPES.get(row[1])
        if waste is None:
            continue  # riadok, ktorý nie je PLA/PAP/BIO
        if area is None:
            warnings.append(f"Riadok '{row[1]}' bez priradenej mestskej časti.")
            continue
        for c in range(2, len(row)):
            cell = row[c]
            if not (cell and cell.strip().isdigit()):
                continue
            day = int(cell)
            month = _column_lookup(month_cols, c)
            year = _column_lookup(year_cols, c)
            try:
                d = datetime.date(year, month, day)
            except ValueError:
                warnings.append(
                    f"Neplatný dátum {day}.{month}.{year} ({area}/{waste}) — preskočené."
                )
                continue
            collections.append(Collection(area, waste, d))

    if not collections:
        raise ValueError("Z PDF sa nevyparsoval žiadny zvoz — neočakávaný formát.")

    warnings += _validate_cycles(collections)

    dates = [c.date for c in collections]
    areas = sorted({c.area for c in collections})
    return ParseResult(
        collections=collections,
        valid_from=min(dates),
        valid_to=max(dates),
        areas=areas,
        source_hash=file_hash(pdf_path),
        pdf_moddate=moddate,
        warnings=warnings,
    )


def _validate_cycles(collections: list[Collection]) -> list[str]:
    """Poistka: pre každú (časť, typ) skontroluje, či sú medzery medzi zvozmi
    blízko očakávaného cyklu. Nezvyčajné medzery len OZNAČÍ (nezhadzuje) —
    môžu byť reálne, ale chceme o nich vedieť."""
    from collections import defaultdict

    groups: dict[tuple[str, str], list[datetime.date]] = defaultdict(list)
    for c in collections:
        groups[(c.area, c.waste_type)].append(c.date)

    warnings: list[str] = []
    for (area, waste), dates in groups.items():
        ds = sorted(dates)
        expected = EXPECTED_CYCLE[waste]
        for i in range(len(ds) - 1):
            gap = (ds[i + 1] - ds[i]).days
            if abs(gap - expected) > CYCLE_TOLERANCE:
                warnings.append(
                    f"Nezvyčajná medzera {gap}d (čak. {expected}d) "
                    f"v {area}/{waste}: {ds[i]:%d.%m.}–{ds[i+1]:%d.%m.}"
                )
    return warnings


if __name__ == "__main__":
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else "data/pdfs/Harmonogram-TZ-2026-27.pdf"
    result = parse(path)
    print(result)
    print(f"\nMestské časti ({len(result.areas)}):")
    for a in result.areas:
        print("  -", a)
    if result.warnings:
        print(f"\nUpozornenia ({len(result.warnings)}):")
        for w in result.warnings:
            print("  !", w)
    # ukážka
    print("\nUkážka — Zobor 1:")
    for waste in ("plast", "papier", "bio"):
        dts = sorted(c.date for c in result.collections
                     if c.area == "Zobor 1" and c.waste_type == waste)
        print(f"  {waste:7} ({len(dts):2}): "
              + ", ".join(d.strftime("%d.%m.%Y") for d in dts))
