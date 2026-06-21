"""
Prístupová kontrola (Sentinel core) — rodinný allowlist + rate limiting.

OBE sú DEFAULTNE VYPNUTÉ (audit #8: navrhnuté, ale neaktivované bez potvrdenia):
  - prázdny allowlist  → povolení sú všetci,
  - rate_enabled=False → bez obmedzenia frekvencie.

Aktivuje sa cez .env (ALLOWED_USER_IDS, RATE_LIMIT_*). Čistá, testovateľná logika.
"""
from __future__ import annotations

from collections import defaultdict, deque


def parse_ids(raw: str | None) -> set[int]:
    """„111, 222;333" → {111, 222, 333}. Nečíselné položky ignoruje."""
    if not raw:
        return set()
    out: set[int] = set()
    for tok in raw.replace(";", ",").split(","):
        tok = tok.strip()
        if tok.lstrip("-").isdigit():
            out.add(int(tok))
    return out


class AccessGuard:
    def __init__(self, allowed_ids: set[int] | None = None,
                 rate_enabled: bool = False, rate_max: int = 20,
                 rate_window: float = 60.0):
        self.allowed = set(allowed_ids or set())
        self.rate_enabled = rate_enabled
        self.rate_max = rate_max
        self.rate_window = rate_window
        self._hits: dict[int, deque] = defaultdict(deque)

    @property
    def allowlist_active(self) -> bool:
        return bool(self.allowed)

    def is_allowed(self, user_id: int | None) -> bool:
        """Prázdny allowlist = vypnuté (všetci povolení)."""
        if not self.allowed:
            return True
        return user_id in self.allowed

    def within_rate(self, user_id: int, now: float) -> bool:
        """True ak smie poslať (a zaráta hit). Vypnuté → vždy True."""
        if not self.rate_enabled:
            return True
        dq = self._hits[user_id]
        cutoff = now - self.rate_window
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= self.rate_max:
            return False
        dq.append(now)
        return True
