import datetime

from sentinel.skills.waste_collection.notifications import (
    Notification, fmt_bins, group_by_date, pluralize_kontajner,
)
from sentinel.skills.waste_collection.service import WasteService

D = datetime.date(2026, 6, 29)
D2 = datetime.date(2026, 7, 13)
TODAY = datetime.date(2026, 6, 21)


def _ev(date, t):
    icon = {"plast": "🟡", "papier": "🔵", "bio": "🟤"}[t]
    return {"date": date, "type": t, "label": f"{icon} {t}"}


def test_pluralize_kontajner():
    assert pluralize_kontajner(1) == "1 kontajner"
    assert pluralize_kontajner(2) == "2 kontajnery"
    assert pluralize_kontajner(4) == "4 kontajnery"
    assert pluralize_kontajner(5) == "5 kontajnerov"


def test_group_by_date():
    evs = [_ev(D2, "plast"), _ev(D, "papier"), _ev(D, "bio")]
    groups = group_by_date(evs)
    assert groups[0][0] == D                      # zoradené vzostupne
    assert {e["type"] for e in groups[0][1]} == {"papier", "bio"}
    assert groups[1][0] == D2


def test_notification_message_counts_bins():
    n = Notification(42, D, [_ev(D, "papier"), _ev(D, "bio")])
    msg = n.message()
    assert "papier" in msg and "bio" in msg
    assert "2 kontajnery" in msg


def test_notification_single_bin_no_count():
    n = Notification(42, D, [_ev(D, "plast")])
    assert "kontajner" not in n.message()


# --- answer_waste_query so zoskupením rovnakého dňa ---
class _FakeResolver:
    def __init__(self, events):
        self._ev = events

    def events(self, *a, **k):
        return self._ev

    def resolve(self, *a, **k):  # answer_waste_query ho nevolá
        raise NotImplementedError


class _Profile:
    cast = "Staré mesto"
    ulica = "Frana Mojtu"
    cislo = "29"
    komunal_desc = None


def test_answer_general_groups_same_day():
    svc = WasteService(_FakeResolver([_ev(D, "papier"), _ev(D, "bio"),
                                      _ev(D2, "plast")]))
    ans = svc.answer_waste_query(_Profile(), "kedy zvoz?")
    assert "papier" in ans and "bio" in ans
    assert "2 kontajnery" in ans


def test_answer_specific_type_mentions_same_day_others():
    svc = WasteService(_FakeResolver([_ev(D, "papier"), _ev(D, "bio")]))
    ans = svc.answer_waste_query(_Profile(), "kedy papier?")
    assert "papier" in ans
    assert "bio" in ans          # spomenie aj druhú nádobu v ten deň
