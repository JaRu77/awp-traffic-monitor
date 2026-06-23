from datetime import datetime, timezone

from awp_traffic.tomtom_client import normalize_route


def test_normalize_route_calculates_route_indicators():
    payload = {
        "routes": [
            {
                "summary": {
                    "lengthInMeters": 3000,
                    "travelTimeInSeconds": 300,
                    "noTrafficTravelTimeInSeconds": 200,
                    "historicTrafficTravelTimeInSeconds": 220,
                    "liveTrafficIncidentsTravelTimeInSeconds": 300,
                    "trafficDelayInSeconds": 100,
                    "trafficLengthInMeters": 900,
                    "departureTime": "2026-06-22T12:00:00+02:00",
                    "arrivalTime": "2026-06-22T12:05:00+02:00",
                }
            }
        ]
    }

    result = normalize_route(
        payload,
        route_id="r1",
        route_name="Trasa testowa",
        direction="A -> B",
        coordinates=[
            {"latitude": 53.4, "longitude": 14.5},
            {"latitude": 53.45, "longitude": 14.55},
            {"latitude": 53.5, "longitude": 14.6},
        ],
        requested_at=datetime(2026, 6, 22, 10, 0, tzinfo=timezone.utc),
    )

    assert result["route_id"] == "r1"
    assert result["waypoint_count"] == 1
    assert result["travel_time_seconds"] == 300
    assert result["no_traffic_travel_time_seconds"] == 200
    assert result["delay_seconds"] == 100
    assert result["delay_ratio"] == 1.5
    assert round(result["congestion_index"], 3) == 0.667
    assert result["average_speed_kmh"] == 36
