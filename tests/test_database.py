from awp_traffic.database import (
    create_fetch_run,
    get_daily_request_total,
    get_fetch_runs_for_date,
    get_latest_fetch_run,
    get_measurement_point_ids_for_slot,
    get_measurements_for_date,
    get_route_ids_for_slot,
    get_route_measurements_for_date,
    insert_measurement,
    insert_route_measurement,
    update_fetch_run,
)


def test_fetch_run_logging_and_daily_request_total(tmp_path):
    db_path = tmp_path / "traffic.sqlite"
    run_id = create_fetch_run(
        db_path,
        {
            "started_at_utc": "2026-06-22T10:00:00+00:00",
            "started_at_local": "2026-06-22T12:00:00+02:00",
            "scheduled_slot_utc": "2026-06-22T10:00:00+00:00",
            "scheduled_slot_local": "2026-06-22T12:00:00+02:00",
            "finished_at_utc": None,
            "finished_at_local": None,
            "status": "started",
            "trigger": "local",
            "dry_run": False,
            "monitoring_enabled": True,
            "points_total": 24,
            "requests_attempted": 0,
            "successes": 0,
            "failures": 0,
            "daily_requests_before": 0,
            "daily_request_soft_limit": 2400,
            "message": "run started",
        },
    )

    update_fetch_run(
        db_path,
        run_id,
        {
            "finished_at_utc": "2026-06-22T10:01:00+00:00",
            "finished_at_local": "2026-06-22T12:01:00+02:00",
            "status": "success",
            "requests_attempted": 24,
            "successes": 24,
            "failures": 0,
            "message": "ok",
        },
    )

    assert get_daily_request_total(db_path, "2026-06-22") == 24
    runs = get_fetch_runs_for_date(db_path, "2026-06-22")
    assert len(runs) == 1
    assert runs[0]["status"] == "success"
    assert runs[0]["monitoring_enabled"] is True
    assert runs[0]["dry_run"] is False
    assert runs[0]["scheduled_slot_local"] == "2026-06-22T12:00:00+02:00"
    assert get_latest_fetch_run(db_path)["requests_attempted"] == 24


def test_measurement_slot_fields_are_persisted(tmp_path):
    db_path = tmp_path / "traffic.sqlite"
    insert_measurement(
        db_path,
        {
            "timestamp_utc": "2026-06-22T10:08:00+00:00",
            "timestamp_local": "2026-06-22T12:08:00+02:00",
            "measurement_slot_utc": "2026-06-22T10:00:00+00:00",
            "measurement_slot_local": "2026-06-22T12:00:00+02:00",
            "point_id": "p1",
            "point_name": "Punkt testowy",
            "direction": "A -> B",
            "latitude": 53.4,
            "longitude": 14.5,
            "current_speed": 30,
            "free_flow_speed": 40,
            "current_travel_time": 120,
            "free_flow_travel_time": 90,
            "confidence": 1,
            "road_closure": False,
            "congestion_index": 0.75,
            "delay_ratio": 1.333,
            "delay_seconds": 30,
            "raw_json": {"ok": True},
        },
    )

    rows = get_measurements_for_date(db_path, "2026-06-22")
    assert len(rows) == 1
    assert rows[0]["measurement_slot_local"] == "2026-06-22T12:00:00+02:00"
    assert rows[0]["timestamp_local"] == "2026-06-22T12:08:00+02:00"
    assert get_measurement_point_ids_for_slot(db_path, "2026-06-22T12:00:00+02:00") == {"p1"}


def test_route_measurement_slot_fields_are_persisted(tmp_path):
    db_path = tmp_path / "traffic.sqlite"
    insert_route_measurement(
        db_path,
        {
            "timestamp_utc": "2026-06-22T10:08:00+00:00",
            "timestamp_local": "2026-06-22T12:08:00+02:00",
            "measurement_slot_utc": "2026-06-22T10:00:00+00:00",
            "measurement_slot_local": "2026-06-22T12:00:00+02:00",
            "route_id": "r1",
            "route_name": "Trasa testowa",
            "direction": "A -> B",
            "origin_latitude": 53.4,
            "origin_longitude": 14.5,
            "destination_latitude": 53.5,
            "destination_longitude": 14.6,
            "waypoint_count": 1,
            "length_meters": 3000,
            "travel_time_seconds": 300,
            "no_traffic_travel_time_seconds": 200,
            "historic_traffic_travel_time_seconds": 220,
            "live_traffic_travel_time_seconds": 300,
            "traffic_delay_seconds": 100,
            "traffic_length_meters": 900,
            "average_speed_kmh": 36,
            "free_flow_average_speed_kmh": 54,
            "congestion_index": 0.666,
            "delay_ratio": 1.5,
            "delay_seconds": 100,
            "departure_time": "2026-06-22T12:08:00+02:00",
            "arrival_time": "2026-06-22T12:13:00+02:00",
            "raw_json": {"ok": True},
        },
    )

    rows = get_route_measurements_for_date(db_path, "2026-06-22")
    assert len(rows) == 1
    assert rows[0]["measurement_slot_local"] == "2026-06-22T12:00:00+02:00"
    assert rows[0]["route_id"] == "r1"
    assert get_route_ids_for_slot(db_path, "2026-06-22T12:00:00+02:00") == {"r1"}
