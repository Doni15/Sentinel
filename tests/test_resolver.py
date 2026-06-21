import datetime

from .conftest import TODAY


def test_resolve_stare_mesto(resolver):
    res = resolver.resolve("Staré mesto", "8.mája", "5", today=TODAY)
    assert res.triedeny_area == "Kalvária / Staré mesto"
    assert res.triedeny["plast"] == datetime.date(2026, 6, 15)
    assert res.komunal, "očakávam komunál rozvrh"


def test_resolve_without_diacritics(resolver):
    """Adresa bez diakritiky a s inou medzerou musí dať rovnaký výsledok."""
    res = resolver.resolve("stare mesto", "8. maja", "5", today=TODAY)
    assert res.triedeny_area == "Kalvária / Staré mesto"
    assert res.triedeny["plast"] == datetime.date(2026, 6, 15)
    assert res.komunal


def test_events_sorted_and_within_window(resolver):
    start = TODAY
    end = TODAY + datetime.timedelta(days=14)
    events = resolver.events("Staré mesto", "8.mája", "5", start, end)
    assert events
    dates = [e["date"] for e in events]
    assert dates == sorted(dates)
    assert all(start <= d <= end for d in dates)


def test_unknown_address_warns(resolver):
    res = resolver.resolve("Staré mesto", "Neexistujúca", "1", today=TODAY)
    assert any("nenájdená" in w for w in res.warnings)
