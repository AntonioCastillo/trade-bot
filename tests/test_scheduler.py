from datetime import date, datetime, timezone
import time

from tradebot.scheduler import EventScheduler


def test_scheduler_init():
    sched = EventScheduler(
        report_interval_seconds=900,
        alive_interval_seconds=21600,
        error_notify_interval_seconds=1800,
    )
    assert sched.report_interval == 900
    assert sched.alive_interval == 21600
    assert sched.error_notify_interval == 1800


def test_scheduler_new_utc_day():
    sched = EventScheduler()
    sched.current_day = date(2024, 1, 1)

    # Same day
    dt1 = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert not sched.is_new_utc_day(dt1)
    assert sched.current_day == date(2024, 1, 1)

    # Next day
    dt2 = datetime(2024, 1, 2, 0, 1, tzinfo=timezone.utc)
    assert sched.is_new_utc_day(dt2)
    assert sched.current_day == date(2024, 1, 2)

    # Calling again on same day returns False
    assert not sched.is_new_utc_day(dt2)


def test_scheduler_check_4h_slot():
    sched = EventScheduler()
    sched.last_4h_slot = (date(2024, 1, 1), 0)  # 00:00 - 04:00

    # Same slot (02:30)
    dt1 = datetime(2024, 1, 1, 2, 30, tzinfo=timezone.utc)
    assert not sched.check_4h_slot(dt1)

    # Next slot (04:00)
    dt2 = datetime(2024, 1, 1, 4, 0, tzinfo=timezone.utc)
    assert sched.check_4h_slot(dt2)
    assert sched.last_4h_slot == (date(2024, 1, 1), 1)

    # Another call in same slot returns False
    dt3 = datetime(2024, 1, 1, 5, 0, tzinfo=timezone.utc)
    assert not sched.check_4h_slot(dt3)


def test_scheduler_report_due():
    sched = EventScheduler(report_interval_seconds=100)
    t0 = 1000.0
    sched.last_report_ts = t0

    assert not sched.is_report_due(t_now=t0 + 50)
    assert sched.is_report_due(t_now=t0 + 100)
    assert sched.last_report_ts == t0 + 100
    assert not sched.is_report_due(t_now=t0 + 105)


def test_scheduler_alive_due():
    sched = EventScheduler(alive_interval_seconds=1000)
    t0 = 2000.0
    sched.last_alive_ts = t0

    assert not sched.is_alive_due(t_now=t0 + 500)
    assert sched.is_alive_due(t_now=t0 + 1000)
    assert sched.last_alive_ts == t0 + 1000
    assert not sched.is_alive_due(t_now=t0 + 1050)


def test_scheduler_can_notify_error():
    sched = EventScheduler(error_notify_interval_seconds=300)
    t0 = 5000.0
    sched.last_error_notify_ts = 0.0

    # First error notification is allowed
    assert sched.can_notify_error(t_now=t0)
    assert sched.last_error_notify_ts == t0

    # Subsequent error within interval is blocked
    assert not sched.can_notify_error(t_now=t0 + 100)

    # Error after interval is allowed
    assert sched.can_notify_error(t_now=t0 + 301)
    assert sched.last_error_notify_ts == t0 + 301
