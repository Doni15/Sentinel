from .conftest import TODAY


def test_zobor_zone_resolution(resolver):
    res = resolver.resolve("Zobor", "Gaštanová", today=TODAY)
    assert res.triedeny_area == "Zobor 3"


def test_zobor_zone_without_diacritics(resolver):
    res = resolver.resolve("zobor", "gastanova", today=TODAY)
    assert res.triedeny_area == "Zobor 3"


def test_zobor_multiple_zones(resolver):
    # Broskyňová -> Zobor 1, Bartókova -> Zobor 2, Astrová -> Zobor 4
    assert resolver.resolve("Zobor", "Broskyňová", today=TODAY).triedeny_area == "Zobor 1"
    assert resolver.resolve("Zobor", "Bartókova", today=TODAY).triedeny_area == "Zobor 2"
    assert resolver.resolve("Zobor", "Astrová", today=TODAY).triedeny_area == "Zobor 4"


def test_zobor_unknown_street_warns(resolver):
    res = resolver.resolve("Zobor", "Neznáma", today=TODAY)
    assert res.triedeny_area is None
    assert any("Zobor" in w for w in res.warnings)
