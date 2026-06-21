"""
Scraper NKS Nitra — dynamicky nájde odkaz na PDF na stránke (nie natvrdo URL),
stiahne ho a zahashuje. Bez externých závislostí (stdlib urllib).

BEZPEČNOSŤ (sťahujeme externý obsah, preto obrana do hĺbky):
  - len HTTPS a doména v allowliste (nks.sk),
  - validácia cieľa pri KAŽDOM redirecte aj finálnej URL po redirecte,
  - limit veľkosti HTML aj PDF (ochrana pred zahltením),
  - kontrola Content-Type a `%PDF-` magic hlavičky,
  - streamované sťahovanie (nie celé do RAM naraz),
  - zápis cez bezpečný dočasný súbor + atomické nahradenie.

Použité v `updater.py` na detekciu, kedy NKS nahral nový harmonogram.
"""
from __future__ import annotations

import datetime
import hashlib
import os
import re
import tempfile
import urllib.parse
import urllib.request

BASE = "https://www.nks.sk"
ALLOWED_SUFFIX = "nks.sk"            # povolená doména (a jej subdomény)
MAX_HTML_BYTES = 5 * 1024 * 1024     # 5 MB — stránka NKS má rádovo desiatky kB
MAX_PDF_BYTES = 30 * 1024 * 1024     # 30 MB — reálne PDF má ~1 MB
PDF_MAGIC = b"%PDF-"
_UA = {"User-Agent": "Mozilla/5.0 (SentinelBot; +waste schedule checker)"}
_TIMEOUT = 30
_CHUNK = 65536


class SecurityError(Exception):
    """Porušenie bezpečnostnej kontroly pri sťahovaní externého obsahu."""


# ---------- bezpečné sieťové primitívy ----------
def _host_allowed(host: str | None) -> bool:
    h = (host or "").lower().split(":")[0]
    return h == ALLOWED_SUFFIX or h.endswith("." + ALLOWED_SUFFIX)


def _check_url(url: str) -> str:
    p = urllib.parse.urlparse(url)
    if p.scheme != "https":
        raise SecurityError(f"povolené je len HTTPS, nie {p.scheme!r}: {url}")
    if not _host_allowed(p.hostname):
        raise SecurityError(
            f"doména mimo allowlistu ({ALLOWED_SUFFIX}): {p.hostname!r}")
    return url


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Pred nasledovaním redirectu overí, že cieľ je tiež HTTPS + v allowliste."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_SafeRedirectHandler)


def _open(url: str):
    """Otvorí URL bezpečne: validuje vstup, redirecty aj finálnu URL."""
    _check_url(url)
    req = urllib.request.Request(url, headers=_UA)
    resp = _OPENER.open(req, timeout=_TIMEOUT)
    _check_url(resp.geturl())   # finálna URL po prípadných redirectoch
    return resp


def _silent_remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


# ---------- verejné API ----------
def fetch_html(page_url: str) -> str:
    with _open(page_url) as resp:
        raw = resp.read(MAX_HTML_BYTES + 1)
    if len(raw) > MAX_HTML_BYTES:
        raise SecurityError(f"HTML väčšie ako {MAX_HTML_BYTES} bajtov: {page_url}")
    return raw.decode("utf-8", errors="replace")


def find_pdf_link(page_url: str, filename_pattern: str,
                  html: str | None = None) -> str | None:
    """Nájde absolútnu URL prvého PDF, ktorého href vyhovuje `filename_pattern`
    (regex, case-insensitive). `html` sa dá podstrčiť v testoch."""
    if html is None:
        html = fetch_html(page_url)
    rx = re.compile(
        r'href=["\']([^"\']*?' + filename_pattern + r'[^"\']*?\.pdf)["\']',
        re.IGNORECASE)
    m = rx.search(html)
    if not m:
        return None
    url = urllib.parse.urljoin(BASE, m.group(1))
    return _check_url(url)       # aj odkaz zo stránky musí byť HTTPS + nks.sk


_VALIDITY_RX = re.compile(
    r"od\s+(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})\s+do\s+"
    r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})",
    re.IGNORECASE)


def find_validity_period(page_url: str, html: str | None = None
                         ) -> tuple[datetime.date, datetime.date] | None:
    """Vyčíta obdobie platnosti z TEXTU stránky (autoritatívne), napr.
    „platný od 1. 4. 2026 do 31. 3. 2027" → (date(2026,4,1), date(2027,3,31)).
    Vráti None, ak sa text nenájde."""
    if html is None:
        html = fetch_html(page_url)
    m = _VALIDITY_RX.search(html)
    if not m:
        return None
    d1, m1, y1, d2, m2, y2 = (int(x) for x in m.groups())
    try:
        return datetime.date(y1, m1, d1), datetime.date(y2, m2, d2)
    except ValueError:
        return None


def download(url: str, dest_path: str) -> str:
    """Stiahne PDF z `url` do `dest_path` bezpečne: overí doménu/redirect,
    Content-Type, `%PDF-` magic, limit veľkosti; streamuje cez dočasný súbor."""
    with _open(url) as resp:
        ctype = (resp.headers.get("Content-Type") or "").lower()
        if "pdf" not in ctype and "octet-stream" not in ctype:
            raise SecurityError(f"neočakávaný Content-Type pre PDF: {ctype!r}")

        dest_dir = os.path.dirname(os.path.abspath(dest_path)) or "."
        os.makedirs(dest_dir, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=dest_dir, suffix=".part")
        total = 0
        first = True
        try:
            with os.fdopen(fd, "wb") as f:
                while True:
                    chunk = resp.read(_CHUNK)
                    if not chunk:
                        break
                    if first:
                        if not chunk.startswith(PDF_MAGIC):
                            raise SecurityError(
                                "súbor nie je PDF (chýba %PDF- hlavička)")
                        first = False
                    total += len(chunk)
                    if total > MAX_PDF_BYTES:
                        raise SecurityError(
                            f"PDF väčšie ako {MAX_PDF_BYTES} bajtov")
                    f.write(chunk)
            if first:
                raise SecurityError("prázdna odpoveď (žiadne dáta)")
            os.replace(tmp, dest_path)
        except BaseException:
            _silent_remove(tmp)
            raise
    return dest_path


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()
