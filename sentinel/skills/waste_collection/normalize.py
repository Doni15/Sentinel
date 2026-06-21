"""
Normalizácia adries pre spoľahlivé párovanie používateľského vstupu na dáta z PDF.

Rieši: diakritiku (Čermáň→cerman), veľkosť písmen, bodky a interpunkciu
(„8.mája" / „8. mája" → „8 maja"), viacnásobné medzery, a aliasy mestských častí
a ulíc. Ten istý normalizátor sa púšťa na vstup používateľa aj na dáta z PDF, takže
sa stretnú v rovnakom tvare.
"""
from __future__ import annotations

import re
import unicodedata


def strip_diacritics(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize(s: str) -> str:
    """Všeobecná normalizácia textu (ulica, časť): bez diakritiky, malé písmená,
    interpunkcia → medzera, zložené medzery zlúčené.
    „8.mája" → „8 maja";  „A. Žarnova" → „a zarnova";  „Staré Mesto" → „stare mesto".
    """
    s = strip_diacritics(s).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def normalize_num(s: str | None) -> str:
    """Normalizácia čísla domu — bez oddeľovačov: „9/A" / „9 a" / „9A" → „9a"."""
    return re.sub(r"[^a-z0-9]+", "", strip_diacritics(s or "").lower())


def split_street_number(s: str) -> tuple[str, str | None]:
    """Oddelí KONCOVÉ číslo domu od názvu ulice (číslo na začiatku je súčasť názvu).
    „Frana Mojtu 29"   → („Frana Mojtu", „29")
    „Hlavná 12/B"      → („Hlavná", „12/B")
    „8. mája"          → („8. mája", None)   # číslo je na začiatku, je to názov
    „Frana Mojtu"      → („Frana Mojtu", None)
    „29"               → („29", None)        # samotné číslo nechaj tak
    """
    s = (s or "").strip()
    m = re.search(r"[\s,]+(\d+\s*[a-zA-Z]?(?:\s*/\s*\d*\s*[a-zA-Z]?)?)\s*$", s)
    if not m:
        return s, None
    num = re.sub(r"\s+", "", m.group(1))
    street = s[:m.start()].rstrip(" ,").strip()
    if not street:
        return s, None
    return street, num


def normalize_zone_key(s: str) -> str:
    """Kľúč pre zóny Zobor zo strany 2 PDF. Odreže zátvorkové/čiarkové upresnenia
    a koncové čísla domov (napr. „Dolnohorská (od ... )" → „dolnohorska",
    „Hornočermánska 57/A, 51/A" → „hornocermanska")."""
    base = re.split(r"[(,]", s or "")[0]
    n = normalize(base)
    tokens = n.split()
    while tokens and re.fullmatch(r"[0-9]+[a-z]?|[a-z]", tokens[-1]):
        tokens.pop()
    return " ".join(tokens)


# --- aliasy mestských častí → triedený district (12 oblastí), kľúče normalizované ---
PART_TO_TRIEDENY: dict[str, str] = {
    "stare mesto": "Kalvária / Staré mesto",
    "kalvaria": "Kalvária / Staré mesto",
    "dolne krskany": "Dolné / Krškany / Párovské Háje",
    "parovske haje": "Dolné / Krškany / Párovské Háje",
    "janikovce": "Janíkovce",
    "kynek": "Klokočina / Mlynárce / Kynek",
    "klokocina": "Klokočina / Mlynárce / Kynek",
    "mlynarce": "Klokočina / Mlynárce / Kynek",
    "chrenova": "Chrenová",
    "drazovce": "Dražovce / Prameň",
    "pramen": "Dražovce / Prameň",
    "horne krskany": "Horné / Krškany / Horný Čermáň",
    "dolny cerman": "Dolný Čermáň / Šúdol",
    "sudol": "Dolný Čermáň / Šúdol",
    "horny cerman": "Horné / Krškany / Horný Čermáň",
}

# aliasy mestských častí (rôzne pomenovania toho istého) → kanonický vstup
PART_ALIASES: dict[str, str] = {
    "stare mesto nitra": "stare mesto",
    "centrum": "stare mesto",
    "zobor nitra": "zobor",
    "cerman": "cerman",  # samotný Čermáň ostáva nejednoznačný (Dolný/Horný)
}

# aliasy ulíc (skratky, varianty) → normalizovaný kanonický názov ulice
STREET_ALIASES: dict[str, str] = {
    "sng": "svatoplukova",          # ukážkový alias; rozširovať podľa potreby
    "ul 1 maja": "1 maja",
}


def canon_part(s: str) -> str:
    n = normalize(s)
    return PART_ALIASES.get(n, n)


def canon_street(s: str) -> str:
    n = normalize(s)
    return STREET_ALIASES.get(n, n)
