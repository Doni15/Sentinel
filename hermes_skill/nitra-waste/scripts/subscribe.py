#!/usr/bin/env python3
"""
Žiadosť o prihlásenie na pripomienky zvozu — volá Hermes (LLM), keď už vpustený
používateľ povie svoju adresu a chce dostávať denné pripomienky.

Skript NIKDY nezapíše odberateľa natrvalo. Iba:
  1. overí adresu proti dátam (musí existovať aspoň jeden zvoz do 40 dní),
  2. odloží žiadosť do waste_pending.json,
  3. pošle adminovi na Telegram žiadosť o schválenie (/approve <id> / /reject <id>).

Použitie (z priečinka skillu):
  python3 scripts/subscribe.py --name "Manželka" --cast "Staré mesto" \
      --ulica "Frana Mojtu 29" --chat-id 123456789

Cesty (override cez env):
  WASTE_SUBSCRIBERS    default /home/hermes/.hermes/waste_subscribers.json
  WASTE_PENDING        default /home/hermes/.hermes/waste_pending.json
  HERMES_ENV           default /home/hermes/.hermes/.env  (TELEGRAM_BOT_TOKEN)
  WASTE_ADMIN_CHAT_ID  default 677758312  (komu chodia žiadosti na schválenie)
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import query  # reuse: events(), ICON, fmt_date, split_street_number  # noqa: E402

SUBS_FILE = os.environ.get("WASTE_SUBSCRIBERS",
                           "/home/hermes/.hermes/waste_subscribers.json")
PENDING_FILE = os.environ.get("WASTE_PENDING",
                              "/home/hermes/.hermes/waste_pending.json")
ENV_FILE = os.environ.get("HERMES_ENV", "/home/hermes/.hermes/.env")
ADMIN_CHAT_ID = os.environ.get("WASTE_ADMIN_CHAT_ID", "677758312")


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


def _result(ok: bool, message: str, **extra) -> None:
    """Vypíš JSON pre LLM, nech ho prerozpráva žiadateľovi."""
    out = {"ok": ok, "message": message}
    out.update(extra)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    raise SystemExit(0 if ok else 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, help="meno žiadateľa")
    ap.add_argument("--cast", required=True, help="mestská časť")
    ap.add_argument("--ulica", required=True, help="ulica (môže obsahovať číslo)")
    ap.add_argument("--cislo", default="", help="číslo domu (voliteľné)")
    ap.add_argument("--chat-id", required=True, help="Telegram chat_id žiadateľa")
    args = ap.parse_args()

    street, num_in = query.split_street_number(args.ulica)
    cislo = args.cislo.strip() or num_in
    chat_id = str(args.chat_id).strip()

    # už prihlásený?
    subs = _load(SUBS_FILE, [])
    if any(str(s.get("chat_id")) == chat_id for s in subs):
        _result(True, "Túto adresu už máš prihlásenú na pripomienky — netreba nič robiť.",
                already_subscribed=True)

    # over adresu proti dátam (aspoň 1 zvoz do 40 dní)
    today = datetime.date.today()
    end = today + datetime.timedelta(days=40)
    evs, _area, _k = query.events(args.cast, street, cislo, today, end)
    addr = f"{street}{(' ' + cislo) if cislo else ''}, {args.cast}"
    if not evs:
        _result(False,
                f"Pre adresu {addr} som nenašiel žiadny zvoz — skontroluj "
                "mestskú časť alebo ulicu a skús to znova.",
                found=False)

    # zapíš do pending (dict {id: entry}); ak ten istý chat_id už čaká, prepíš
    pending = _load(PENDING_FILE, {})
    if not isinstance(pending, dict):
        pending = {}
    for pid, e in list(pending.items()):
        if str(e.get("chat_id")) == chat_id:
            del pending[pid]  # nahradíme novou žiadosťou
    new_id = str(max((int(k) for k in pending), default=0) + 1)
    pending[new_id] = {
        "name": args.name.strip(),
        "cast": args.cast.strip(),
        "ulica": street,
        "cislo": cislo,
        "chat_id": chat_id,
        "requested": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    json.dump(pending, open(PENDING_FILE, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    # najbližší zvoz na ukážku v žiadosti adminovi
    d0 = evs[0]["date"]
    t0 = [query.ICON[e["type"]] + " " + e["type"] for e in evs if e["date"] == d0]
    nearest = f"{query.fmt_date(d0)} — {' + '.join(t0)}"

    token = _token()
    admin_msg = (
        f"🆕 Žiadosť o pripomienky zvozu\n\n"
        f"Meno: {args.name.strip()}\n"
        f"Adresa: {addr}\n"
        f"Telegram ID: {chat_id}\n"
        f"Najbližší zvoz: {nearest}\n\n"
        f"Napíš mi (BEZ lomky):\n"
        f"Schváliť:  approve {new_id}\n"
        f"Zamietnuť: reject {new_id}")
    send_telegram(token, ADMIN_CHAT_ID, admin_msg)

    _result(True,
            "Žiadosť o pripomienky som odoslal na schválenie. Keď ju admin "
            "potvrdí, začneš dostávať pripomienku vždy deň pred zvozom.",
            pending_id=new_id, address=addr)


if __name__ == "__main__":
    main()
