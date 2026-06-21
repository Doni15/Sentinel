from sentinel.core.access import AccessGuard, parse_ids


def test_parse_ids_mixed_separators():
    assert parse_ids("111, 222;333") == {111, 222, 333}
    assert parse_ids("") == set()
    assert parse_ids(None) == set()
    assert parse_ids("abc, 5, x9") == {5}


def test_allowlist_disabled_allows_everyone():
    g = AccessGuard()  # default: prázdny allowlist
    assert g.allowlist_active is False
    assert g.is_allowed(999) is True
    assert g.is_allowed(None) is True


def test_allowlist_active_blocks_outsiders():
    g = AccessGuard(allowed_ids={111, 222})
    assert g.allowlist_active is True
    assert g.is_allowed(111) is True
    assert g.is_allowed(333) is False


def test_rate_limit_disabled_by_default():
    g = AccessGuard()
    for i in range(100):
        assert g.within_rate(1, now=float(i)) is True


def test_rate_limit_blocks_over_max_then_recovers():
    g = AccessGuard(rate_enabled=True, rate_max=3, rate_window=60.0)
    assert g.within_rate(1, now=0.0) is True
    assert g.within_rate(1, now=1.0) is True
    assert g.within_rate(1, now=2.0) is True
    assert g.within_rate(1, now=3.0) is False      # 4. v okne → blok
    # po vypršaní okna sa to uvoľní
    assert g.within_rate(1, now=70.0) is True


def test_rate_limit_is_per_user():
    g = AccessGuard(rate_enabled=True, rate_max=1, rate_window=60.0)
    assert g.within_rate(1, now=0.0) is True
    assert g.within_rate(2, now=0.0) is True        # iný používateľ má vlastné okno
    assert g.within_rate(1, now=1.0) is False
