from datetime import datetime
from zoneinfo import ZoneInfo

from scripts.server_scheduler import _is_interval_due


WARSAW = ZoneInfo("Europe/Warsaw")


def test_hourly_routes_run_at_full_hour():
    assert _is_interval_due(datetime(2026, 6, 24, 6, 0, 2, tzinfo=WARSAW), 60)


def test_hourly_routes_do_not_run_at_quarter_hour():
    assert not _is_interval_due(datetime(2026, 6, 24, 6, 15, 2, tzinfo=WARSAW), 60)
    assert not _is_interval_due(datetime(2026, 6, 24, 6, 30, 2, tzinfo=WARSAW), 60)
    assert not _is_interval_due(datetime(2026, 6, 24, 6, 45, 2, tzinfo=WARSAW), 60)


def test_invalid_route_interval_is_disabled():
    assert not _is_interval_due(datetime(2026, 6, 24, 6, 0, 2, tzinfo=WARSAW), 0)
