import datetime
import hashlib
import io

import pytest

from sentinel.skills.waste_collection import scraper

HTML = """
<a href="/s/NKS-letak-2026_2027-b8y8.pdf">Leták</a>
<a href="/s/Harmonogram-TZ-2026-27.pdf">Harmonogram triedeného</a>
<a href="/s/Stanovitia-v-meste-k-1822026-komplet.pdf">Komunál</a>
"""


# ---------- fake sieť pre bezpečnostné testy ----------
class _FakeResp(io.BytesIO):
    def __init__(self, data: bytes, ctype: str, final_url: str):
        super().__init__(data)
        self.headers = {"Content-Type": ctype}
        self._url = final_url

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
        return False


def _fake_opener(data=b"%PDF-1.4 test", ctype="application/pdf",
                 final_url="https://www.nks.sk/s/a.pdf"):
    class _Op:
        def open(self, req, timeout=None):
            return _FakeResp(data, ctype, final_url)
    return _Op()


def test_find_triedeny_link():
    url = scraper.find_pdf_link("http://x", r"Harmonogram-TZ", html=HTML)
    assert url == "https://www.nks.sk/s/Harmonogram-TZ-2026-27.pdf"


def test_find_komunal_link():
    url = scraper.find_pdf_link("http://x", r"Stanovi", html=HTML)
    assert url == "https://www.nks.sk/s/Stanovitia-v-meste-k-1822026-komplet.pdf"


def test_find_link_none_when_missing():
    assert scraper.find_pdf_link("http://x", r"Neexistuje", html=HTML) is None


def test_sha256_file(tmp_path):
    p = tmp_path / "a.bin"
    p.write_bytes(b"hello sentinel")
    assert scraper.sha256_file(str(p)) == hashlib.sha256(b"hello sentinel").hexdigest()


def test_find_validity_period():
    html = "Harmonogram triedeného odpadu, platný od 1. 4. 2026 do 31. 3. 2027."
    assert scraper.find_validity_period("http://x", html=html) == (
        datetime.date(2026, 4, 1), datetime.date(2027, 3, 31))


def test_find_validity_period_title_casing():
    # zvláštne písanie z titulku: „oD ... dO"
    html = "HARMONOGRAM VÝVOZOV oD 1. 4. 2026 dO 31. 3. 2027"
    assert scraper.find_validity_period("http://x", html=html) == (
        datetime.date(2026, 4, 1), datetime.date(2027, 3, 31))


def test_find_validity_period_none():
    assert scraper.find_validity_period("http://x", html="žiadne dátumy") is None


# ---------- bezpečnostné testy (#3) ----------
def test_reject_non_https():
    with pytest.raises(scraper.SecurityError):
        scraper.download("http://www.nks.sk/x.pdf", "/tmp/out.pdf")


def test_reject_external_domain():
    with pytest.raises(scraper.SecurityError):
        scraper.fetch_html("https://evil.example.com/x")


def test_reject_lookalike_domain():
    # nks.sk.evil.com nesmie prejsť ako "nks.sk"
    with pytest.raises(scraper.SecurityError):
        scraper.download("https://nks.sk.evil.com/x.pdf", "/tmp/out.pdf")


def test_find_pdf_link_rejects_offsite(monkeypatch):
    html = '<a href="https://evil.com/Harmonogram-TZ-x.pdf">x</a>'
    with pytest.raises(scraper.SecurityError):
        scraper.find_pdf_link("https://www.nks.sk/p", r"Harmonogram-TZ", html=html)


def test_reject_redirect_to_external(monkeypatch, tmp_path):
    # vstup je nks.sk, ale finálna URL (po redirecte) je mimo allowlistu
    monkeypatch.setattr(scraper, "_OPENER",
                        _fake_opener(final_url="https://evil.com/final.pdf"))
    with pytest.raises(scraper.SecurityError):
        scraper.download("https://www.nks.sk/a.pdf", str(tmp_path / "o.pdf"))


def test_reject_oversized_pdf(monkeypatch, tmp_path):
    monkeypatch.setattr(scraper, "MAX_PDF_BYTES", 100)
    big = b"%PDF-" + b"0" * 500
    monkeypatch.setattr(scraper, "_OPENER", _fake_opener(data=big))
    with pytest.raises(scraper.SecurityError):
        scraper.download("https://www.nks.sk/a.pdf", str(tmp_path / "o.pdf"))


def test_reject_non_pdf_content(monkeypatch, tmp_path):
    monkeypatch.setattr(scraper, "_OPENER",
                        _fake_opener(data=b"<html>nope</html>",
                                     ctype="text/html"))
    with pytest.raises(scraper.SecurityError):
        scraper.download("https://www.nks.sk/a.pdf", str(tmp_path / "o.pdf"))


def test_reject_bad_magic_even_if_ctype_pdf(monkeypatch, tmp_path):
    # Content-Type tvrdí PDF, ale obsah nie je PDF → magic kontrola chytí
    monkeypatch.setattr(scraper, "_OPENER",
                        _fake_opener(data=b"GIF89a not a pdf",
                                     ctype="application/pdf"))
    with pytest.raises(scraper.SecurityError):
        scraper.download("https://www.nks.sk/a.pdf", str(tmp_path / "o.pdf"))


def test_reject_oversized_html(monkeypatch):
    monkeypatch.setattr(scraper, "MAX_HTML_BYTES", 10)
    monkeypatch.setattr(scraper, "_OPENER",
                        _fake_opener(data=b"x" * 50, ctype="text/html"))
    with pytest.raises(scraper.SecurityError):
        scraper.fetch_html("https://www.nks.sk/p")


def test_valid_pdf_download_ok(monkeypatch, tmp_path):
    monkeypatch.setattr(scraper, "_OPENER",
                        _fake_opener(data=b"%PDF-1.4 hello sentinel"))
    out = tmp_path / "ok.pdf"
    scraper.download("https://www.nks.sk/a.pdf", str(out))
    assert out.read_bytes().startswith(b"%PDF-")
    # po úspechu nezostal žiadny .part dočasný súbor
    assert not list(tmp_path.glob("*.part"))
