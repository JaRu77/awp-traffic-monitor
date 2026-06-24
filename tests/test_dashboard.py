import pytest

from awp_traffic.dashboard import (
    _access_point_statistics,
    _expected_daily_requests,
    _route_speed_statistics,
)


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


def test_route_speed_statistics_calculate_daily_mean_min_and_max():
    statistics = _route_speed_statistics(
        [
            {"route_id": "r1", "average_speed_kmh": 20},
            {"route_id": "r1", "average_speed_kmh": 30},
            {"route_id": "r1", "average_speed_kmh": 40},
        ]
    )

    assert statistics["r1"]["average_speed_mean"] == pytest.approx(30)
    assert statistics["r1"]["average_speed_min"] == 20
    assert statistics["r1"]["average_speed_max"] == 40
    assert statistics["r1"]["measurements"] == 3


def test_access_point_statistics_do_not_claim_vehicle_counts():
    points = [
        {
            "id": "p1",
            "name": "Wjazd",
            "direction": "A -> AWP",
            "corridor_order": 1,
            "traffic_role": "side_inflow",
            "connection_name": "ul. A",
        },
        {
            "id": "p2",
            "name": "Punkt wewnetrzny",
            "corridor_order": 2,
        },
    ]
    measurements = [
        {
            "point_id": "p1",
            "measurement_slot_local": "2026-06-24T10:00:00+02:00",
            "current_speed": 20,
            "congestion_index": 0.5,
        },
        {
            "point_id": "p1",
            "measurement_slot_local": "2026-06-24T10:15:00+02:00",
            "current_speed": 30,
            "congestion_index": 0.75,
        },
    ]

    result = _access_point_statistics(points, measurements)

    assert len(result) == 1
    assert result[0]["average_speed_today"] == pytest.approx(25)
    assert result[0]["current_speed"] == 30
    assert result[0]["measurements"] == 2
    assert "vehicle_count" not in result[0]
