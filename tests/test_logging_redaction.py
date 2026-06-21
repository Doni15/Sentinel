import logging

from sentinel.core.logging_setup import (
    _RedactTokenFilter, configure_logging, redact_token,
)

# Úplne fiktívny token (len na test redakčného vzoru) — nie je to reálny bot token.
TOKEN = "1234567890:AAFAKE-fictional-test-token-DO-NOT-USE-0000"
BOT_ID = TOKEN.split(":")[0]
REDACTED = f"{BOT_ID}:<REDACTED>"


def test_redact_token_in_url():
    url = f"https://api.telegram.org/bot{TOKEN}/getMe"
    out = redact_token(url)
    assert TOKEN not in out
    assert f"bot{REDACTED}" in out


def test_redact_bare_token():
    out = redact_token(f"token is {TOKEN} ok")
    assert TOKEN not in out
    assert REDACTED in out


def test_redact_leaves_normal_text():
    assert redact_token("no secrets here 12:34") == "no secrets here 12:34"


def test_filter_scrubs_record_msg():
    f = _RedactTokenFilter()
    rec = logging.LogRecord("x", logging.INFO, "p", 1,
                            f"POST https://api.telegram.org/bot{TOKEN}/getUpdates",
                            None, None)
    assert f.filter(rec) is True
    assert TOKEN not in rec.getMessage()


def test_filter_scrubs_record_args():
    f = _RedactTokenFilter()
    rec = logging.LogRecord("x", logging.INFO, "p", 1, "request %s",
                            (f"bot{TOKEN}/getMe",), None)
    f.filter(rec)
    assert TOKEN not in rec.getMessage()


def test_configure_silences_httpx():
    configure_logging(logging.INFO)
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING
