import pytest

from awp_traffic.route_estimation import (
    estimate_route_measurements,
    merge_route_measurements,
)


POINTS = [
    {"id": "p1", "latitude": 0.0, "longitude": 0.0},
    {"id": "p2", "latitude": 0.0, "longitude": 0.009},
    {"id": "p3", "latitude": 0.0, "longitude": 0.018},
]

ROUTES = [
    {
        "id": "r1",
        "name": "Trasa testowa",
        "direction": "A -> B",
        "point_ids": ["p1", "p2", "p3"],
    }
]


def _measurement(point_id: str, current_speed: float = 36) -> dict:
    point = next(point for point in POINTS if point["id"] == point_id)
    return {
        "point_id": point_id,
        "measurement_slot_local": "2026-06-24T09:30:00+02:00",
        "measurement_slot_utc": "2026-06-24T07:30:00+00:00",
        "timestamp_local": "2026-06-24T09:30:05+02:00",
        "timestamp_utc": "2026-06-24T07:30:05+00:00",
        "latitude": point["latitude"],
        "longitude": point["longitude"],
        "current_speed": current_speed,
        "free_flow_speed": 72,
        "confidence": 1,
    }


def test_estimates_route_time_from_distance_weighted_speeds():
    estimates = estimate_route_measurements(
        routes=ROUTES,
        points=POINTS,
        measurements=[_measurement("p1"), _measurement("p2"), _measurement("p3")],
    )

    assert len(estimates) == 1
    estimate = estimates[0]
    assert estimate["length_meters"] == pytest.approx(2001.5, rel=0.01)
    assert estimate["travel_time_seconds"] == pytest.approx(200.15, rel=0.01)
    assert estimate["no_traffic_travel_time_seconds"] == pytest.approx(100.08, rel=0.01)
    assert estimate["delay_ratio"] == pytest.approx(2)
    assert estimate["congestion_index"] == pytest.approx(0.5)
    assert estimate["points_used"] == 3
    assert estimate["source"] == "flow_point_estimate"


def test_requires_complete_route_when_configured():
    estimates = estimate_route_measurements(
        routes=ROUTES,
        points=POINTS,
        measurements=[_measurement("p1"), _measurement("p2")],
        require_all_points=True,
    )

    assert estimates == []


def test_direct_api_measurement_overrides_estimate_for_same_slot():
    estimate = estimate_route_measurements(
        routes=ROUTES,
        points=POINTS,
        measurements=[_measurement("p1"), _measurement("p2"), _measurement("p3")],
    )[0]
    api_measurement = {
        **estimate,
        "travel_time_seconds": 123,
        "source": "routing_api",
    }

    merged = merge_route_measurements([estimate], [api_measurement])

    assert len(merged) == 1
    assert merged[0]["travel_time_seconds"] == 123
    assert merged[0]["source_label"] == "TomTom Routing API"
