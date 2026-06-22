#!/usr/bin/env python3
"""
Strážca prístupu — sleduje journal Hermes gateway a keď niekto neoprávnený skúsi
napísať botovi, pošle ADMINOVI na Telegram upozornenie s príkazom na vpustenie.

Gateway loguje zamietnutie v tvare:
  WARNING gateway.run: Unauthorized user: 677758312 (Lubík) on telegram

Beží ako systemd služba (Restart=always), číta NOVÉ riadky cez
`journalctl _UID=<uid> -f`. Dedup: jeden alert na (id) za deň, nech to nespamuje.

Cesty / nastavenia (override cez env):
  HERMES_ENV           default /home/hermes/.hermes/.env  (TELEGRAM_BOT_TOKEN)
  WASTE_ADMIN_CHAT_ID  default 677758312
  WASTE_ACCESS_STATE   default /home/hermes/.hermes/waste_access_state.json
  HERMES_UID           default 1000  (UID hermes usera pre journalctl)
"""
from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request

ENV_FILE = os.environ.get("HERMES_ENV", "/home/hermes/.hermes/.env")
ADMIN_CHAT_ID = os.environ.get("WASTE_ADMIN_CHAT_ID", "677758312")
STATE_FILE = os.environ.get("WASTE_ACCESS_STATE",
                            "/home/hermes/.hermes/waste_access_state.json")
HERMES_UID = os.environ.get("HERMES_UID", "1000")

DENIED_RE = re.compile(r"Unauthorized user:\s*(\d+)\s*\(([^)]*)\)\s*on\s*(\w+)")


def _token() -> str:
    for line in open(ENV_FILE, encoding="utf-8"):
        if line.startswith("TELEGRAM_BOT_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("TELEGRAM_BOT_TOKEN nenájdený v " + ENV_FILE)


def _load(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return default


def send_telegram(token: str, chat_id, text: str) -> bool:
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage", data=data)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r).get("ok", False)
    except Exception as e:  # noqa: BLE001
        print("send error:", e, flush=True)
        return False


def handle(token: str, uid: str, name: str, platform: str) -> None:
    state = _load(STATE_FILE, {})
    today = datetime.date.today().isoformat()
    if state.get(uid) == today:
        return  # dnes už upozornené na toto ID
    msg = (f"🔔 Pokus o kontakt s botom\n\n"
           f"Meno: {name or '?'}\n"
           f"Telegram ID: {uid}\n"
           f"Platforma: {platform}\n\n"
           f"Pustiť k botovi:  /allow {uid}\n"
           f"Ignorovať:        /deny {uid}")
    if send_telegram(token, ADMIN_CHAT_ID, msg):
        state[uid] = today
        if len(state) > 200:
            state = dict(sorted(state.items(), key=lambda kv: kv[1])[-200:])
        try:
            json.dump(state, open(STATE_FILE, "w", encoding="utf-8"),
                      ensure_ascii=False)
        except OSError as e:
            print("state write error:", e, flush=True)
        print(f"alert sent for {uid} ({name})", flush=True)


def main() -> None:
    if "--test" in sys.argv:
        token = _token()
        ok = send_telegram(token, ADMIN_CHAT_ID,
                           "🧪 TEST strážcu prístupu — toto upozornenie príde, "
                           "keď sa neznámy pokúsi napísať botovi.")
        print("test", "OK" if ok else "FAIL", flush=True)
        return

    token = _token()
    proc = subprocess.Popen(
        ["journalctl", f"_UID={HERMES_UID}", "-f", "-n", "0", "-o", "cat"],
        stdout=subprocess.PIPE, text=True)
    print("access_watch beží, sledujem gateway log…", flush=True)
    assert proc.stdout is not None
    for line in proc.stdout:
        m = DENIED_RE.search(line)
        if m:
            handle(token, m.group(1), m.group(2).strip(), m.group(3))


if __name__ == "__main__":
    main()
