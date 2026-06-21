from .conftest import TODAY


def test_cerman_alone_is_ambiguous(resolver):
    res = resolver.resolve("Čermáň", "Hlavná", today=TODAY)
    assert res.triedeny_area is None
    assert any("Čermáň" in w for w in res.warnings)


def test_dolny_cerman_resolves(resolver):
    res = resolver.resolve("Dolný Čermáň", "Akákoľvek", today=TODAY)
    assert res.triedeny_area == "Dolný Čermáň / Šúdol"


def test_horny_cerman_resolves(resolver):
    res = resolver.resolve("Horný Čermáň", "Akákoľvek", today=TODAY)
    assert res.triedeny_area == "Horné / Krškany / Horný Čermáň"


def test_cerman_no_diacritics_ambiguous(resolver):
    res = resolver.resolve("cerman", "Hlavná", today=TODAY)
    assert res.triedeny_area is None
