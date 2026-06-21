"""
Centrálne nastavenie logovania (Sentinel core).

DÔLEŽITÉ (bezpečnosť): httpx loguje na úrovni INFO každý HTTP request vrátane URL,
v ktorej je Telegram bot token (`.../bot<token>/getMe`). To by zapísalo token do
systemd journalu. Preto:
  1. httpx (a telegram.ext) stíšime na WARNING,
  2. na root logger pripojíme filter, ktorý z KAŽDEJ správy zredaguje bot token
     (obrana do hĺbky — keby ho zalogovalo čokoľvek iné).
"""
from __future__ import annotations

import logging
import re

# `bot123456789:AA...` v URL  alebo holý token `123456789:AA...`
_TOKEN_RX = re.compile(r"(bot)?(\d{6,10}):[A-Za-z0-9_-]{30,}")
_REDACTED = r"\1\2:<REDACTED>"


class _RedactTokenFilter(logging.Filter):
    """Zredaguje Telegram bot token v texte log správy aj v jej argumentoch."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str) and ":" in record.msg:
                record.msg = _TOKEN_RX.sub(_REDACTED, record.msg)
            if record.args:
                record.args = tuple(
                    _TOKEN_RX.sub(_REDACTED, a) if isinstance(a, str) else a
                    for a in record.args
                )
        except Exception:  # logovanie nikdy nesmie zhodiť aplikáciu
            pass
        return True


def redact_token(text: str) -> str:
    """Pomocná funkcia na zredigovanie tokenu v ľubovoľnom reťazci."""
    return _TOKEN_RX.sub(_REDACTED, text or "")


def configure_logging(level: int = logging.INFO) -> None:
    """Nastaví formát + úroveň, stíši ukecané HTTP loggery a zapne redakciu tokenu.
    Idempotentné — dá sa volať viackrát."""
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=level)

    # httpx/httpcore logujú celé URL (s tokenom) na INFO → stíšiť
    for noisy in ("httpx", "httpcore", "telegram.ext.Updater"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # obrana do hĺbky: redakčný filter na root handleroch
    redactor = _RedactTokenFilter()
    root = logging.getLogger()
    for handler in root.handlers:
        if not any(isinstance(f, _RedactTokenFilter) for f in handler.filters):
            handler.addFilter(redactor)
