from awp_traffic.dashboard import _expected_daily_requests


def test_daily_request_plan_includes_hourly_routes():
    assert _expected_daily_requests(
        points_count=24,
        point_interval_minutes=15,
        routes_count=2,
        route_interval_minutes=60,
        routes_enabled=True,
    ) == 2352


def test_daily_request_plan_ignores_disabled_routes():
    assert _expected_daily_requests(
        points_count=24,
        point_interval_minutes=15,
        routes_count=2,
        route_interval_minutes=60,
        routes_enabled=False,
    ) == 2304
