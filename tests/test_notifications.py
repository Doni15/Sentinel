import datetime

from sentinel.core.dispatcher import NotificationDispatcher

# 14.6.2026 → zajtra 15.6.2026 má pre 8.mája 5, Staré mesto zvoz (plast/bio/komunál)
DAY_BEFORE = datetime.date(2026, 6, 14)


def test_daily_notifications_produced(service_with_db):
    svc, _db = service_with_db
    notifs = svc.daily_notifications(DAY_BEFORE)
    assert len(notifs) == 1
    n = notifs[0]
    assert n.user_id == 42
    assert n.date == datetime.date(2026, 6, 15)
    assert n.items


def test_no_notifications_on_quiet_day(service_with_db):
    svc, _db = service_with_db
    # 8.6.2026 -> zajtra 9.6.2026: pre túto adresu žiadny zvoz
    assert svc.daily_notifications(datetime.date(2026, 6, 8)) == []


async def test_dispatch_dedup(service_with_db):
    svc, db = service_with_db
    sent: list[tuple[int, str]] = []

    async def fake_send(uid, text):
        sent.append((uid, text))

    disp = NotificationDispatcher(db, fake_send)

    first = await disp.dispatch(svc.daily_notifications(DAY_BEFORE))
    assert first == 1
    assert len(sent) == 1

    # druhý beh v ten istý deň nesmie poslať nič (notifications_log)
    second = await disp.dispatch(svc.daily_notifications(DAY_BEFORE))
    assert second == 0
    assert len(sent) == 1


def test_notifications_log_recorded(service_with_db):
    svc, db = service_with_db
    n = svc.daily_notifications(DAY_BEFORE)[0]
    date_iso = n.date.isoformat()
    for it in n.items:
        assert not db.was_notified(42, date_iso, it["type"])
        db.mark_notified(42, date_iso, it["type"])
        assert db.was_notified(42, date_iso, it["type"])


def test_delete_waste_data_removes_subscription_and_logs(service_with_db):
    svc, db = service_with_db
    db.mark_notified(42, "2026-06-15", "plast")
    assert db.get_subscription(42) is not None
    assert db.was_notified(42, "2026-06-15", "plast")

    db.delete_waste_data(42)

    assert db.get_subscription(42) is None
    assert not db.was_notified(42, "2026-06-15", "plast")
    # profil v Sentinel core ostáva
    row = db.conn.execute(
        "SELECT 1 FROM profiles WHERE user_id=?", (42,)).fetchone()
    assert row is not None
