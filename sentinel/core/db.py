"""
Spoločná Sentinel DB (SQLite). Vlastní ju Sentinel core, skilly ju zdieľajú cez
namespacované tabuľky.

Tabuľky:
  profiles            – používatelia Sentinela (user_id = telegram chat_id)
  waste_subscriptions – adresa sledovaná waste skillom (namespace skillu)
  notifications_log   – odoslané notifikácie (anti-duplikácia)
"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass

from . import timeutil

_SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    user_id    INTEGER PRIMARY KEY,
    name       TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS waste_subscriptions (
    user_id      INTEGER PRIMARY KEY REFERENCES profiles(user_id) ON DELETE CASCADE,
    cast         TEXT NOT NULL,
    ulica        TEXT NOT NULL,
    cislo        TEXT,
    komunal_desc TEXT,
    -- notify_hour: zatiaľ NEPOUŽÍVANÉ schedulerom (ten beží na globálnom NOTIFY_HOUR).
    -- TODO(future): per-user scheduling + príkaz /nastav HH:MM. Pole ponechané ako
    -- príprava; kým nie je implementované, help text /nastav nesľubuje.
    notify_hour  INTEGER NOT NULL DEFAULT 18,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS notifications_log (
    user_id         INTEGER NOT NULL,
    collection_date TEXT NOT NULL,
    waste_type      TEXT NOT NULL,
    sent_at         TEXT NOT NULL,
    PRIMARY KEY (user_id, collection_date, waste_type)
);
CREATE TABLE IF NOT EXISTS waste_pdf_versions (
    source          TEXT PRIMARY KEY,   -- 'triedeny' | 'komunal'
    url             TEXT,
    file_hash       TEXT,
    valid_from      TEXT,               -- z dát (len triedeny)
    valid_to        TEXT,               -- z dát (len triedeny)
    next_check_date TEXT NOT NULL,      -- self-scheduling: kedy znova kontrolovať
    downloaded_at   TEXT,               -- kedy sa naposledy zmenil
    last_checked    TEXT,
    status          TEXT                -- 'parsed' | 'failed'
);
"""


@dataclass
class PdfVersion:
    source: str
    url: str | None
    file_hash: str | None
    valid_from: str | None
    valid_to: str | None
    next_check_date: str
    downloaded_at: str | None
    last_checked: str | None
    status: str | None


@dataclass
class WasteSubscription:
    user_id: int
    cast: str
    ulica: str
    cislo: str | None
    komunal_desc: str | None
    notify_hour: int = 18  # future work: per-user scheduling, zatiaľ globálny čas


class Database:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(_SCHEMA)
        self.conn.commit()
        # bezpečnosť (#4): DB obsahuje adresy → len vlastník smie čítať/písať (600)
        if path != ":memory:" and os.path.exists(path):
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass

    # --- profiles ---
    def ensure_profile(self, user_id: int, name: str | None = None) -> None:
        self.conn.execute(
            "INSERT INTO profiles(user_id, name) VALUES(?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET name=COALESCE(excluded.name, name)",
            (user_id, name),
        )
        self.conn.commit()

    # --- waste_subscriptions ---
    def upsert_subscription(self, sub: WasteSubscription) -> None:
        self.ensure_profile(sub.user_id)
        self.conn.execute(
            """INSERT INTO waste_subscriptions
                 (user_id, cast, ulica, cislo, komunal_desc, notify_hour)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                 cast=excluded.cast, ulica=excluded.ulica, cislo=excluded.cislo,
                 komunal_desc=excluded.komunal_desc, notify_hour=excluded.notify_hour""",
            (sub.user_id, sub.cast, sub.ulica, sub.cislo,
             sub.komunal_desc, sub.notify_hour),
        )
        self.conn.commit()

    def get_subscription(self, user_id: int) -> WasteSubscription | None:
        r = self.conn.execute(
            "SELECT * FROM waste_subscriptions WHERE user_id=?", (user_id,)
        ).fetchone()
        return self._sub(r) if r else None

    def all_subscriptions(self) -> list[WasteSubscription]:
        rows = self.conn.execute("SELECT * FROM waste_subscriptions").fetchall()
        return [self._sub(r) for r in rows]

    def delete_subscription(self, user_id: int) -> None:
        self.conn.execute(
            "DELETE FROM waste_subscriptions WHERE user_id=?", (user_id,))
        self.conn.commit()

    def delete_waste_logs(self, user_id: int) -> None:
        """Zmaže notification logy používateľa. Pozn.: `notifications_log` je teraz
        výlučne pre waste skill; keď budú logovať aj iné skilly, treba do tabuľky
        pridať stĺpec so skillom a mazať len waste riadky."""
        self.conn.execute(
            "DELETE FROM notifications_log WHERE user_id=?", (user_id,))
        self.conn.commit()

    def delete_waste_data(self, user_id: int) -> None:
        """Kompletné zmazanie waste dát používateľa (subscription + notif. logy).
        Profil v `profiles` ostáva — patrí Sentinel core, nie waste skillu."""
        self.delete_subscription(user_id)
        self.delete_waste_logs(user_id)

    # --- notifications_log (anti-duplikácia) ---
    def was_notified(self, user_id: int, collection_date: str,
                     waste_type: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM notifications_log "
            "WHERE user_id=? AND collection_date=? AND waste_type=?",
            (user_id, collection_date, waste_type),
        ).fetchone() is not None

    def mark_notified(self, user_id: int, collection_date: str,
                      waste_type: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO notifications_log"
            "(user_id, collection_date, waste_type, sent_at) VALUES(?,?,?,?)",
            (user_id, collection_date, waste_type, timeutil.now().isoformat()),
        )
        self.conn.commit()

    # --- waste_pdf_versions (scraper + self-scheduling) ---
    def get_pdf_version(self, source: str) -> PdfVersion | None:
        r = self.conn.execute(
            "SELECT * FROM waste_pdf_versions WHERE source=?", (source,)
        ).fetchone()
        return PdfVersion(**dict(r)) if r else None

    def upsert_pdf_version(self, v: PdfVersion) -> None:
        self.conn.execute(
            """INSERT INTO waste_pdf_versions
                 (source, url, file_hash, valid_from, valid_to, next_check_date,
                  downloaded_at, last_checked, status)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(source) DO UPDATE SET
                 url=excluded.url, file_hash=excluded.file_hash,
                 valid_from=excluded.valid_from, valid_to=excluded.valid_to,
                 next_check_date=excluded.next_check_date,
                 downloaded_at=excluded.downloaded_at,
                 last_checked=excluded.last_checked, status=excluded.status""",
            (v.source, v.url, v.file_hash, v.valid_from, v.valid_to,
             v.next_check_date, v.downloaded_at, v.last_checked, v.status),
        )
        self.conn.commit()

    def touch_pdf_version(self, source: str, last_checked: str,
                          next_check_date: str | None = None) -> None:
        if next_check_date:
            self.conn.execute(
                "UPDATE waste_pdf_versions SET last_checked=?, next_check_date=? "
                "WHERE source=?", (last_checked, next_check_date, source))
        else:
            self.conn.execute(
                "UPDATE waste_pdf_versions SET last_checked=? WHERE source=?",
                (last_checked, source))
        self.conn.commit()

    @staticmethod
    def _sub(r: sqlite3.Row) -> WasteSubscription:
        return WasteSubscription(
            user_id=r["user_id"], cast=r["cast"], ulica=r["ulica"],
            cislo=r["cislo"], komunal_desc=r["komunal_desc"],
            notify_hour=r["notify_hour"],
        )
