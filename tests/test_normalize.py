from sentinel.skills.waste_collection import normalize as nz


def test_split_street_number_trailing():
    assert nz.split_street_number("Frana Mojtu 29") == ("Frana Mojtu", "29")
    assert nz.split_street_number("Hlavná 12/B") == ("Hlavná", "12/B")
    assert nz.split_street_number("Janka Kráľa 9 A") == ("Janka Kráľa", "9A")


def test_split_street_number_no_trailing():
    # číslo na začiatku je súčasť názvu ulice — neoddeľuje sa
    assert nz.split_street_number("8. mája") == ("8. mája", None)
    assert nz.split_street_number("Frana Mojtu") == ("Frana Mojtu", None)


def test_split_street_number_bare_number():
    assert nz.split_street_number("29") == ("29", None)
    assert nz.split_street_number("") == ("", None)


def test_diacritics_and_case():
    assert nz.normalize("Staré Mesto") == "stare mesto"
    assert nz.normalize("Čermáň") == "cerman"


def test_dots_and_spaces():
    assert nz.normalize("8.mája") == "8 maja"
    assert nz.normalize("8. mája") == "8 maja"
    assert nz.normalize("  A.  Žarnova ") == "a zarnova"


def test_normalize_num():
    assert nz.normalize_num("9/A") == "9a"
    assert nz.normalize_num("9 A") == "9a"
    assert nz.normalize_num("9A") == "9a"


def test_zone_key_strips_qualifiers():
    assert nz.normalize_zone_key("Dolnohorská (od Klinčekovej po Prvosienkovú)") \
        == "dolnohorska"
    assert nz.normalize_zone_key("Hornočermánska 57/A, 51/A, 51/B") \
        == "hornocermanska"
    assert nz.normalize_zone_key("Gaštanová") == "gastanova"


def test_canon_part_alias():
    assert nz.canon_part("Staré mesto") == "stare mesto"
    assert nz.canon_part("centrum") == "stare mesto"
