#!/usr/bin/env python3
"""
Denné pripomienky zvozu — DETERMINISTICKÉ, posielané priamo cez Telegram Bot API
(nezávislé od LLM, aby vždy odišli správne, aj keď je free model vyčerpaný).

Spúšťa systemd timer každý deň o 18:00. Pre každého odberateľa zistí zajtrajší
zvoz (cez query logiku nad waste_data.json) a ak nejaký je, pošle pripomienku.
Dedup cez state súbor — nepošle dvakrát to isté.

Cesty (override cez env):
  WASTE_SUBSCRIBERS  default /home/hermes/.hermes/waste_subscribers.json
  WASTE_NOTIFY_STATE default /home/hermes/.hermes/waste_notify_state.json
  HERMES_ENV         default /home/hermes/.hermes/.env  (TELEGRAM_BOT_TOKEN)
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import query  # reuse: events(), ICON, SK_DAYS, pluralize, fmt_date, split_street_number  # noqa: E402

SUBS_FILE = os.environ.get("WASTE_SUBSCRIBERS",
                           "/home/hermes/.hermes/waste_subscribers.json")
STATE_FILE = os.environ.get("WASTE_NOTIFY_STATE",
                            "/home/hermes/.hermes/waste_notify_state.json")
ENV_FILE = os.environ.get("HERMES_ENV", "/home/hermes/.hermes/.env")


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
        print("send error:", e)
        return False


def build_message(day: datetime.date, types: list[str], today: datetime.date) -> str:
    labels = " + ".join(f"{query.ICON[t]} {t}" for t in types)
    rel = "Zajtra" if (day - today).days == 1 else query.fmt_date(day).capitalize()
    pocet = f"  ({query.pluralize(len(types))})" if len(types) > 1 else ""
    return (f"🔔 Sentinel pripomína\n\n"
            f"{rel} ({query.fmt_date(day)}) ide zvoz:\n{labels}{pocet}\n\n"
            f"Nezabudni vyložiť nádoby. 🚛💨")


def main() -> None:
    test = "--test" in sys.argv
    token = _token()
    subs = _load(SUBS_FILE, [])
    if not subs:
        print("žiadni odberatelia v", SUBS_FILE)
        return
    state = _load(STATE_FILE, {})
    today = datetime.date.today()
    target = today + datetime.timedelta(days=1)   # zvoz je ZAJTRA
    sent = 0

    for s in subs:
        street, num_in = query.split_street_number(s["ulica"])
        cislo = str(s.get("cislo", "")).strip() or num_in
        evs, _area, _k = query.events(s["cast"], street, cislo, target, target)
        types = [e["type"] for e in evs]

        if test:
            # testovacia správa: ak zajtra nič, ukáž najbližší deň
            if not types:
                end = today + datetime.timedelta(days=40)
                ev2, _, _ = query.events(s["cast"], street, cislo, today, end)
                if ev2:
                    d0 = ev2[0]["date"]
                    t0 = [e["type"] for e in ev2 if e["date"] == d0]
                    msg = "🧪 TEST pripomienky\n\n" + build_message(d0, t0, today)
                else:
                    msg = "🧪 TEST: pre tvoju adresu som nenašiel zvoz."
            else:
                msg = "🧪 TEST pripomienky\n\n" + build_message(target, types, today)
            ok = send_telegram(token, s["chat_id"], msg)
            print(f"{s.get('name', s['chat_id'])}: test {'OK' if ok else 'FAIL'}")
            sent += ok
            continue

        if not types:
            continue
        key = f"{s['chat_id']}:{target.isoformat()}"
        if state.get(key):
            continue  # už poslané
        if send_telegram(token, s["chat_id"], build_message(target, types, today)):
            state[key] = datetime.datetime.now().isoformat(timespec="seconds")
            sent += 1
            print(f"{s.get('name', s['chat_id'])}: pripomienka odoslaná ({types})")

    # zachovaj len posledných ~60 záznamov state
    if len(state) > 60:
        state = dict(sorted(state.items())[-60:])
    json.dump(state, open(STATE_FILE, "w", encoding="utf-8"))
    print(f"hotovo, odoslaných: {sent}")


if __name__ == "__main__":
    main()
