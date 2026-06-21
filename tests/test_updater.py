import datetime
import shutil

import config
from sentinel.core.db import Database
from sentinel.skills.waste_collection import scraper
from sentinel.skills.waste_collection.updater import (
    FetchResult, SourceSpec, WasteUpdater,
)

TODAY = datetime.date(2026, 6, 8)


def _triedeny_spec(tmp_path):
    active = tmp_path / "trie.pdf"
    shutil.copy(config.TRIEDENY_PDF, active)
    return SourceSpec("triedeny", "http://x", r"Harmonogram-TZ",
                      str(active), str(tmp_path / "archive"))


def _fetch_copy(src_pdf, tmp_path, period=None):
    """Fake fetcher: skopíruje PDF a vráti FetchResult. `period` = (vf, vt) ako keby
    z textu stránky; None = stránka platnosť neuvádza (fallback na dáta)."""
    def fetch(spec):
        dl = str(tmp_path / "download.pdf")
        shutil.copy(src_pdf, dl)
        vf, vt = period if period else (None, None)
        return FetchResult("http://x/file.pdf", dl, vf, vt)
    return fetch


def test_first_run_seeds_and_self_schedules(tmp_path):
    """Bez platnosti na stránke → valid_to sa odvodí z dát (max zvoz)."""
    spec = _triedeny_spec(tmp_path)
    db = Database(":memory:")
    up = WasteUpdater(db, [spec], fetcher=_fetch_copy(config.TRIEDENY_PDF, tmp_path))

    res = up.check_due(TODAY)[0]
    assert res.status == "updated"

    ver = db.get_pdf_version("triedeny")
    assert ver.valid_to == "2027-03-31"
    assert ver.next_check_date == "2027-03-25"   # valid_to − 6 dní
    assert ver.status == "parsed"


def test_validity_from_page_text_used(tmp_path):
    """Platnosť z textu stránky sa zhoduje s dátami → žiadne upozornenie."""
    spec = _triedeny_spec(tmp_path)
    db = Database(":memory:")
    period = (datetime.date(2026, 4, 1), datetime.date(2027, 3, 31))
    up = WasteUpdater(db, [spec],
                      fetcher=_fetch_copy(config.TRIEDENY_PDF, tmp_path, period))

    res = up.check_due(TODAY)[0]
    ver = db.get_pdf_version("triedeny")
    assert ver.valid_to == "2027-03-31"
    assert ver.next_check_date == "2027-03-25"
    assert "⚠️" not in res.message


def test_page_validity_overrides_and_warns_on_mismatch(tmp_path):
    """Platnosť zo stránky je autoritatívna; pri nesúlade s dátami sa nahlási."""
    spec = _triedeny_spec(tmp_path)
    db = Database(":memory:")
    period = (datetime.date(2026, 4, 1), datetime.date(2027, 4, 30))  # ≠ dáta
    up = WasteUpdater(db, [spec],
                      fetcher=_fetch_copy(config.TRIEDENY_PDF, tmp_path, period))

    res = up.check_due(TODAY)[0]
    ver = db.get_pdf_version("triedeny")
    assert ver.valid_to == "2027-04-30"          # platnosť zo stránky
    assert ver.next_check_date == "2027-04-24"   # 30.4 − 6 dní
    assert "⚠️" in res.message                    # krížová kontrola hlási nesúlad


def test_skips_until_next_check_due(tmp_path):
    spec = _triedeny_spec(tmp_path)
    db = Database(":memory:")
    up = WasteUpdater(db, [spec], fetcher=_fetch_copy(config.TRIEDENY_PDF, tmp_path))
    up.check_due(TODAY)

    res = up.check_due(TODAY)[0]
    assert res.status == "skipped"


def test_unchanged_when_hash_same(tmp_path):
    spec = _triedeny_spec(tmp_path)
    db = Database(":memory:")
    up = WasteUpdater(db, [spec], fetcher=_fetch_copy(config.TRIEDENY_PDF, tmp_path))
    up.check_due(TODAY)

    res = up.check_due(TODAY, force=True)[0]
    assert res.status == "unchanged"


def test_failed_parse_keeps_old_active(tmp_path):
    spec = _triedeny_spec(tmp_path)
    db = Database(":memory:")
    up = WasteUpdater(db, [spec], fetcher=_fetch_copy(config.TRIEDENY_PDF, tmp_path))
    up.check_due(TODAY)
    good_hash = scraper.sha256_file(spec.active_path)

    def bad_fetch(s):
        dl = str(tmp_path / "bad.pdf")
        with open(dl, "wb") as f:
            f.write(b"toto nie je platne PDF")
        return FetchResult("http://x/bad.pdf", dl, None, None)
    up.fetcher = bad_fetch

    res = up.check_due(TODAY, force=True)[0]
    assert res.status == "failed"
    assert scraper.sha256_file(spec.active_path) == good_hash


def test_komunal_periodic_schedule(tmp_path):
    active = tmp_path / "kom.pdf"
    shutil.copy(config.KOMUNAL_PDF, active)
    spec = SourceSpec("komunal", "http://x", r"Stanovi",
                      str(active), str(tmp_path / "archive"))
    db = Database(":memory:")
    up = WasteUpdater(db, [spec], fetcher=_fetch_copy(config.KOMUNAL_PDF, tmp_path))

    res = up.check_due(TODAY)[0]
    assert res.status == "updated"
    ver = db.get_pdf_version("komunal")
    assert ver.next_check_date == (TODAY + datetime.timedelta(days=30)).isoformat()
