import datetime

import config
from sentinel.skills.waste_collection import komunal_parser as kp


def test_parse_day_variants():
    assert kp.parse_day("utorok") == ((1,), None)
    assert kp.parse_day("nepár.utorok") == ((1,), "odd")
    assert kp.parse_day("párny pondelok") == ((0,), "even")
    assert kp.parse_day("párna streda") == ((2,), "even")
    wd, par = kp.parse_day("pon,str,pia")
    assert wd == (0, 2, 4) and par is None


def test_generate_dates_weekly():
    rec = kp.KomunalRecord("piatok", (4,), None, "1x7", "Staré mesto", "X", "1")
    ds = kp.generate_dates(rec, datetime.date(2026, 6, 7),
                           datetime.date(2026, 6, 30))
    assert ds == [datetime.date(2026, 6, 12), datetime.date(2026, 6, 19),
                  datetime.date(2026, 6, 26)]


def test_generate_dates_parity_property():
    rec = kp.KomunalRecord("nepár.piatok", (4,), "odd", "1x14 dní",
                           "X", "Y", "1")
    ds = kp.generate_dates(rec, datetime.date(2026, 6, 1),
                           datetime.date(2026, 8, 31))
    assert ds, "očakávam aspoň nejaké dátumy"
    for d in ds:
        assert d.weekday() == 4                      # piatok
        assert d.isocalendar()[1] % 2 == 1           # nepárny ISO týždeň


def test_full_parse_count():
    recs = kp.parse(config.KOMUNAL_PDF)
    assert len(recs) > 13000
    assert any(r.cast == "Staré mesto" for r in recs)
