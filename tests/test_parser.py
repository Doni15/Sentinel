import datetime

import config
from sentinel.skills.waste_collection import parser


def test_triedeny_counts_and_range():
    r = parser.parse(config.TRIEDENY_PDF)
    assert len(r.collections) == 627
    assert len(r.areas) == 12
    assert r.valid_from == datetime.date(2026, 4, 1)
    assert r.valid_to == datetime.date(2027, 3, 31)


def test_no_invalid_dates():
    r = parser.parse(config.TRIEDENY_PDF)
    invalid = [w for w in r.warnings if "Neplatný" in w]
    assert invalid == []


def test_kalvaria_plast_known_date():
    r = parser.parse(config.TRIEDENY_PDF)
    dates = {c.date for c in r.collections
             if c.area == "Kalvária / Staré mesto" and c.waste_type == "plast"}
    assert datetime.date(2026, 6, 15) in dates


def test_bio_twice_as_frequent_as_plast():
    r = parser.parse(config.TRIEDENY_PDF)
    area = "Kalvária / Staré mesto"
    plast = [c for c in r.collections if c.area == area and c.waste_type == "plast"]
    bio = [c for c in r.collections if c.area == area and c.waste_type == "bio"]
    assert len(bio) == 2 * len(plast)
