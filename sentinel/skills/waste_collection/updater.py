"""
Updater zdrojových PDF + self-scheduling.

Tok pre každý zdroj:
  1. nájdi a stiahni aktuálne PDF z NKS (scraper)
  2. porovnaj hash s uloženou verziou
     - rovnaký → nič nemeň, len posuň ďalšiu kontrolu
     - iný/prvý raz → over parsovaním; ak OK, archivuj staré, nahraď aktívne,
       ulož verziu; ak parsovanie ZLYHÁ, nechaj staré dáta a nahlás chybu
  3. naplánuj ďalšiu kontrolu:
     - triedený: valid_to (z textu stránky) − 6 dní   (≈ raz ročne, tesne pred koncom)
     - komunál:  today + 30 dní                        (periodická poistka, nemá platnosť)

Logika je čistá a testovateľná — sieť sa dá podstrčiť cez `fetcher`.
"""
from __future__ import annotations

import datetime
import os
import shutil
from dataclasses import dataclass
from typing import Callable

from ...core import timeutil
from ...core.db import Database, PdfVersion
from . import komunal_parser, parser, scraper

KOMUNAL_CHECK_INTERVAL_DAYS = 30
TRIEDENY_LEAD_DAYS = 6  # začne kontrolovať 6 dní pred koncom platnosti (napr. 25.3.)
KOMUNAL_MIN_RECORDS = 1000  # sanity prah na úspešný parse komunálu


@dataclass
class SourceSpec:
    key: str            # 'triedeny' | 'komunal'
    page_url: str
    link_pattern: str   # regex názvu súboru na stránke
    active_path: str    # kde žije aktívne PDF
    archive_dir: str


@dataclass
class FetchResult:
    url: str | None
    path: str                       # stiahnuté PDF (temp)
    valid_from: datetime.date | None   # z TEXTU stránky (autoritatívne)
    valid_to: datetime.date | None


@dataclass
class UpdateResult:
    source: str
    status: str         # 'unchanged' | 'updated' | 'failed' | 'skipped'
    message: str
    valid_to: str | None = None

    @property
    def changed(self) -> bool:
        return self.status == "updated"


class WasteUpdater:
    def __init__(self, db: Database, specs: list[SourceSpec],
                 fetcher: Callable[[SourceSpec], FetchResult] | None = None):
        self.db = db
        self.specs = specs
        self.fetcher = fetcher or self._default_fetch

    # --- sieť (prepíše sa v testoch) ---
    def _default_fetch(self, spec: SourceSpec) -> FetchResult:
        html = scraper.fetch_html(spec.page_url)
        url = scraper.find_pdf_link(spec.page_url, spec.link_pattern, html=html)
        if not url:
            raise RuntimeError(f"Na stránke {spec.page_url} sa nenašiel PDF odkaz.")
        tmp = spec.active_path + ".tmp"
        scraper.download(url, tmp)
        # platnosť VŽDY z textu stránky (autoritatívne); komunál ju nemá
        period = (scraper.find_validity_period(spec.page_url, html=html)
                  if spec.key == "triedeny" else None)
        vf, vt = period if period else (None, None)
        return FetchResult(url=url, path=tmp, valid_from=vf, valid_to=vt)

    # --- verejné API ---
    def check_due(self, today: datetime.date | None = None,
                  force: bool = False) -> list[UpdateResult]:
        """Skontroluje zdroje, ktorým už nastal `next_check_date` (alebo všetky,
        ak force). Vráti výsledky."""
        today = today or timeutil.today()
        results = []
        for spec in self.specs:
            ver = self.db.get_pdf_version(spec.key)
            if not force and ver and today < _date(ver.next_check_date):
                results.append(UpdateResult(spec.key, "skipped",
                                            f"ďalšia kontrola {ver.next_check_date}"))
                continue
            results.append(self._check_source(spec, today))
        return results

    def _check_source(self, spec: SourceSpec,
                      today: datetime.date) -> UpdateResult:
        now = timeutil.now().isoformat()
        try:
            fr = self.fetcher(spec)
        except Exception as exc:
            return UpdateResult(spec.key, "failed", f"sťahovanie zlyhalo: {exc}")

        new_hash = scraper.sha256_file(fr.path)
        ver = self.db.get_pdf_version(spec.key)

        if ver and ver.file_hash == new_hash:
            next_check = self._next_check(spec.key, ver.valid_to, today)
            self.db.touch_pdf_version(spec.key, now, next_check)
            _silent_remove(fr.path)
            return UpdateResult(spec.key, "unchanged", "bez zmeny", ver.valid_to)

        # zmena alebo prvý raz → over, že sa PDF dá naparsovať (+ dáta na kríž. kontrolu)
        try:
            data_from, data_to = self._validate(spec.key, fr.path)
        except Exception as exc:
            _silent_remove(fr.path)
            # NECHAJ staré dáta, len posuň kontrolu a nahlás
            if ver:
                self.db.touch_pdf_version(spec.key, now,
                                          self._next_check(spec.key, ver.valid_to, today))
            return UpdateResult(spec.key, "failed",
                                f"nové PDF sa nepodarilo naparsovať: {exc}")

        # PLATNOSŤ: prednostne z TEXTU stránky (autoritatívne); fallback na dáta z PDF
        extra = ""
        if spec.key == "triedeny":
            valid_from = fr.valid_from.isoformat() if fr.valid_from else data_from
            valid_to = fr.valid_to.isoformat() if fr.valid_to else data_to
            if fr.valid_to is None:
                extra = " (platnosť na stránke nenájdená → odvodená z dát)"
            elif data_to and fr.valid_to.isoformat() != data_to:
                extra = (f" ⚠️ platnosť stránky {fr.valid_to.isoformat()} "
                         f"≠ posledný zvoz v PDF {data_to}")
        else:
            valid_from = valid_to = None

        # úspech → archivuj staré aktívne (ak sa reálne mení) a nahraď
        if not _same_file_hash(spec.active_path, new_hash):
            self._archive(spec)
            os.replace(fr.path, spec.active_path)
        else:
            _silent_remove(fr.path)

        next_check = self._next_check(spec.key, valid_to, today)
        self.db.upsert_pdf_version(PdfVersion(
            source=spec.key, url=fr.url, file_hash=new_hash,
            valid_from=valid_from, valid_to=valid_to,
            next_check_date=next_check, downloaded_at=now,
            last_checked=now, status="parsed"))
        return UpdateResult(spec.key, "updated",
                            f"aktualizované, ďalšia kontrola {next_check}{extra}",
                            valid_to)

    # --- pomocné ---
    def _validate(self, key: str, path: str) -> tuple[str | None, str | None]:
        """Overí, že PDF je parsovateľné. Vráti dátový rozsah (min/max zvozov) na
        krížovú kontrolu s platnosťou zo stránky. Pre komunál (None, None)."""
        if key == "triedeny":
            r = parser.parse(path)
            return r.valid_from.isoformat(), r.valid_to.isoformat()
        recs = komunal_parser.parse(path)
        if len(recs) < KOMUNAL_MIN_RECORDS:
            raise ValueError(f"komunál má len {len(recs)} adries (čak. >{KOMUNAL_MIN_RECORDS})")
        return None, None

    def _next_check(self, key: str, valid_to: str | None,
                    today: datetime.date) -> str:
        if key == "triedeny" and valid_to:
            return (_date(valid_to) - datetime.timedelta(days=TRIEDENY_LEAD_DAYS)).isoformat()
        return (today + datetime.timedelta(days=KOMUNAL_CHECK_INTERVAL_DAYS)).isoformat()

    def _archive(self, spec: SourceSpec) -> None:
        if not os.path.exists(spec.active_path):
            return
        os.makedirs(spec.archive_dir, exist_ok=True)
        stamp = timeutil.now().strftime("%Y%m%d-%H%M%S")
        base = os.path.basename(spec.active_path)
        shutil.copy2(spec.active_path,
                     os.path.join(spec.archive_dir, f"{stamp}-{base}"))


def _date(iso: str) -> datetime.date:
    return datetime.date.fromisoformat(iso)


def _silent_remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _same_file_hash(path: str, h: str) -> bool:
    return os.path.exists(path) and scraper.sha256_file(path) == h
