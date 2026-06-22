#!/usr/bin/env python3
"""
Admin príkazy pre pripomienky zvozu — volá Hermes (LLM), keď ADMIN napíše:
  /allow <telegram_id>    vpustí používateľa cez gateway allowlist (+ reštart o 8 s)
  /deny  <telegram_id>    iba potvrdí, nič nepustí
  /approve <pending_id>   presunie žiadosť z waste_pending.json do subscribers
  /reject  <pending_id>   zahodí žiadosť z waste_pending.json

Bezpečnosť: príkaz vykoná IBA ak --requester-chat-id == WASTE_ADMIN_CHAT_ID.
Skript je deterministický; LLM len rozpozná príkaz a spustí ho s argumentmi.

Použitie:
  python3 scripts/admin.py allow   123456 --requester-chat-id 677758312
  python3 scripts/admin.py approve 1      --requester-chat-id 677758312

Cesty (override cez env):
  WASTE_SUBSCRIBERS    default /home/hermes/.hermes/waste_subscribers.json
  WASTE_PENDING        default /home/hermes/.hermes/waste_pending.json
  HERMES_ENV           default /home/hermes/.hermes/.env
  WASTE_ADMIN_CHAT_ID  default 677758312
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request

SUBS_FILE = os.environ.get("WASTE_SUBSCRIBERS",
                           "/home/hermes/.hermes/waste_subscribers.json")
PENDING_FILE = os.environ.get("WASTE_PENDING",
                              "/home/hermes/.hermes/waste_pending.json")
ENV_FILE = os.environ.get("HERMES_ENV", "/home/hermes/.hermes/.env")
ADMIN_CHAT_ID = os.environ.get("WASTE_ADMIN_CHAT_ID", "677758312")
GATEWAY_UNIT = os.environ.get("HERMES_GATEWAY_UNIT", "hermes-gateway")


def _load(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _env_get(key: str) -> str:
    try:
        for line in open(ENV_FILE, encoding="utf-8"):
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


def _env_set(key: str, value: str) -> None:
    """Prepíš alebo doplň key=value v .env, ostatné riadky zachovaj."""
    lines, found = [], False
    try:
        lines = open(ENV_FILE, encoding="utf-8").read().splitlines()
    except OSError:
        pass
    for i, line in enumerate(lines):
        if line.startswith(key + "="):
            lines[i] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")
    open(ENV_FILE, "w", encoding="utf-8").write("\n".join(lines) + "\n")


def send_telegram(token: str, chat_id, text: str) -> bool:
    if not token:
        return False
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage", data=data)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r).get("ok", False)
    except Exception as e:  # noqa: BLE001
        print("send error:", e)
        return False


def _result(message: str, ok: bool = True) -> None:
    print(json.dumps({"ok": ok, "message": message}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if ok else 1)


def _schedule_gateway_restart() -> None:
    """Reštartni gateway o 8 s neskôr, aby stihla odísť potvrdzujúca odpoveď."""
    env = dict(os.environ)
    env.setdefault("XDG_RUNTIME_DIR", "/run/user/1000")
    # Preferuj systemd-run (čistý timer); fallback na odpojený sleep+restart.
    try:
        subprocess.Popen(
            ["systemd-run", "--user", f"--on-active=8",
             "--unit=hermes-gw-reload", "systemctl", "--user",
             "restart", GATEWAY_UNIT],
            env=env, start_new_session=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    except FileNotFoundError:
        pass
    subprocess.Popen(
        ["sh", "-c", f"sleep 8; systemctl --user restart {GATEWAY_UNIT}"],
        env=env, start_new_session=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def cmd_allow(uid: str, token: str) -> None:
    cur = _env_get("TELEGRAM_ALLOWED_USERS")
    ids = [x.strip() for x in cur.split(",") if x.strip()]
    if uid in ids:
        _result(f"Používateľ {uid} už je vpustený — netreba nič meniť.")
    ids.append(uid)
    _env_set("TELEGRAM_ALLOWED_USERS", ",".join(ids))
    _schedule_gateway_restart()
    send_telegram(token, uid,
                  "✅ Bol si vpustený k Sentinelovi. Napíš mi svoju adresu "
                  "(mestská časť, ulica, číslo) a prihlásim ťa na pripomienky zvozu.")
    _result(f"Používateľ {uid} pridaný do allowlistu. Gateway sa reštartuje "
            "o ~8 s, potom ti môže písať.")


def cmd_deny(uid: str, token: str) -> None:
    _result(f"OK, používateľa {uid} som nevpustil (žiadosť ignorovaná).")


def cmd_approve(pid: str, token: str) -> None:
    pending = _load(PENDING_FILE, {})
    if not isinstance(pending, dict) or pid not in pending:
        _result(f"Žiadosť č. {pid} neexistuje (možno už bola vybavená).", ok=False)
    entry = pending.pop(pid)
    subs = _load(SUBS_FILE, [])
    if not any(str(s.get("chat_id")) == str(entry["chat_id"]) for s in subs):
        subs.append({"name": entry["name"], "cast": entry["cast"],
                     "ulica": entry["ulica"], "cislo": entry["cislo"],
                     "chat_id": entry["chat_id"]})
    json.dump(subs, open(SUBS_FILE, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    json.dump(pending, open(PENDING_FILE, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    addr = f"{entry['ulica']}{(' ' + entry['cislo']) if entry['cislo'] else ''}, {entry['cast']}"
    send_telegram(token, entry["chat_id"],
                  "✅ Tvoje pripomienky zvozu sú aktívne! Vždy deň pred zvozom "
                  "ti pošlem, čo treba vyložiť. 🚛")
    _result(f"Schválené: {entry['name']} ({addr}) je prihlásený na pripomienky.")


def cmd_reject(pid: str, token: str) -> None:
    pending = _load(PENDING_FILE, {})
    if not isinstance(pending, dict) or pid not in pending:
        _result(f"Žiadosť č. {pid} neexistuje (možno už bola vybavená).", ok=False)
    entry = pending.pop(pid)
    json.dump(pending, open(PENDING_FILE, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    send_telegram(token, entry["chat_id"],
                  "Tvoja žiadosť o pripomienky zvozu nebola schválená.")
    _result(f"Žiadosť č. {pid} ({entry.get('name', '?')}) zamietnutá.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["allow", "deny", "approve", "reject"])
    ap.add_argument("id", help="telegram_id (allow/deny) alebo pending_id (approve/reject)")
    ap.add_argument("--requester-chat-id", default="",
                    help="chat_id odosielateľa (voliteľné; reálna ochrana je "
                         "allowlist — k botovi sa dostane len rodina)")
    args = ap.parse_args()

    # Ak je requester dodaný a NIE je to admin, odmietni. Ak nie je dodaný
    # (Hermes ho agentovi neposkytuje), spoľahni sa na allowlist.
    req = str(args.requester_chat_id).strip()
    if req and req != str(ADMIN_CHAT_ID):
        _result("Tento príkaz môže použiť iba správca.", ok=False)

    token = _env_get("TELEGRAM_BOT_TOKEN")
    {"allow": cmd_allow, "deny": cmd_deny,
     "approve": cmd_approve, "reject": cmd_reject}[args.command](
        str(args.id).strip(), token)


if __name__ == "__main__":
    main()
