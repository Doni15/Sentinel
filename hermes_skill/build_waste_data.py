"""
Predpočíta dáta zvozu z PDF do malého JSON-u pre Hermes skill.
Beží v Sentinel repo prostredí (má pdfplumber). Spúšťa sa raz a pri zmene PDF.
Výstup: hermes_skill/nitra-waste/scripts/waste_data.json (stdlib-only skill ho číta).
"""
from __future__ import annotations

import json
import os
import sys

# pridaj repo root do path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import config  # noqa: E402
from sentinel.skills.waste_collection.resolver import WasteResolver  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "nitra-waste", "scripts", "waste_data.json")


def main() -> None:
    print("⏳ Načítavam PDF (pdfplumber, ~1.7 GB peak) ...")
    r = WasteResolver(config.TRIEDENY_PDF, config.KOMUNAL_PDF)
    data = {
        "valid_from": r._triedeny.valid_from.isoformat(),
        "valid_to": r._triedeny.valid_to.isoformat(),
        "collections": [
            {"area": c.area, "type": c.waste_type, "date": c.date.isoformat()}
            for c in r._triedeny.collections
        ],
        "zones": r._zones,
        "komunal": [
            {"weekdays": list(k.weekdays), "parity": k.parity,
             "interval": k.interval, "cast": k.cast, "ulica": k.ulica,
             "cislo": k.cislo, "popis": k.describe()}
            for k in r._komunal
        ],
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    size = os.path.getsize(OUT) / 1024
    print(f"✅ {OUT}")
    print(f"   {len(data['collections'])} triedených zvozov, "
          f"{len(data['komunal'])} komunál adries, "
          f"{len(data['zones'])} zón — {size:.0f} kB")


if __name__ == "__main__":
    main()
