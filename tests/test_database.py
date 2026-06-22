from awp_traffic.database import (
    create_fetch_run,
    get_daily_request_total,
    get_fetch_runs_for_date,
    get_latest_fetch_run,
    update_fetch_run,
)


def test_fetch_run_logging_and_daily_request_total(tmp_path):
    db_path = tmp_path / "traffic.sqlite"
    run_id = create_fetch_run(
        db_path,
        {
            "started_at_utc": "2026-06-22T10:00:00+00:00",
            "started_at_local": "2026-06-22T12:00:00+02:00",
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
    assert get_latest_fetch_run(db_path)["requests_attempted"] == 24
