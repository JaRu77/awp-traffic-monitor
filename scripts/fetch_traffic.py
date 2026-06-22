#!/usr/bin/env python
"""Fetch current TomTom traffic conditions for all configured AWP points."""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from awp_traffic.database import (
    create_fetch_run,
    get_daily_request_total,
    insert_measurement,
    update_fetch_run,
    upsert_points,
)
from awp_traffic.metrics import calculate_metrics
from awp_traffic.tomtom_client import TomTomAPIError, TomTomClient


def main() -> int:
    parser = argparse.ArgumentParser(description="Pobierz pomiary z TomTom Traffic API.")
    parser.add_argument("--points", default="config/points.yaml", help="Sciezka do points.yaml.")
    parser.add_argument("--settings", default="config/settings.yaml", help="Sciezka do settings.yaml.")
    parser.add_argument("--database", default=None, help="Sciezka do bazy SQLite.")
    parser.add_argument("--raw-dir", default="data/raw", help="Katalog na surowe odpowiedzi JSON.")
    parser.add_argument("--dry-run", action="store_true", help="Pobierz dane, ale nie zapisuj do SQLite.")
    parser.add_argument("--log-dry-run", action="store_true", help="Zapisz dry-run w tabeli fetch_runs.")
    args = parser.parse_args()

    _load_dotenv_if_available(PROJECT_ROOT / ".env")
    settings = _load_yaml(PROJECT_ROOT / args.settings)
    points = _load_yaml(PROJECT_ROOT / args.points)["points"]
    project_settings = settings.get("project", {})
    monitoring_settings = settings.get("monitoring", {})
    tomtom_settings = settings.get("tomtom", {})
    timezone_name = project_settings.get("timezone", "Europe/Warsaw")
    local_zone = ZoneInfo(timezone_name)
    db_path = PROJECT_ROOT / (args.database or settings.get("database", {}).get("path", "data/awp_traffic.sqlite"))
    raw_dir = PROJECT_ROOT / args.raw_dir
    request_delay_seconds = float(tomtom_settings.get("request_delay_seconds", 0))
    sorted_points = sorted(points, key=lambda item: item.get("corridor_order", 0))
    monitoring_enabled = bool(monitoring_settings.get("enabled", True))
    daily_request_soft_limit = monitoring_settings.get("daily_request_soft_limit")
    daily_request_soft_limit = int(daily_request_soft_limit) if daily_request_soft_limit is not None else None
    started_utc = datetime.now(timezone.utc)
    started_local = started_utc.astimezone(local_zone)
    local_date = started_local.date().isoformat()
    daily_requests_before = get_daily_request_total(db_path, local_date)
    should_log_run = not args.dry_run or args.log_dry_run
    run_id: int | None = None

    if should_log_run:
        run_id = create_fetch_run(
            db_path,
            {
                "started_at_utc": started_utc.isoformat(),
                "started_at_local": started_local.isoformat(),
                "finished_at_utc": None,
                "finished_at_local": None,
                "status": "started",
                "trigger": os.getenv("GITHUB_EVENT_NAME", "local"),
                "dry_run": args.dry_run,
                "monitoring_enabled": monitoring_enabled,
                "points_total": len(sorted_points),
                "requests_attempted": 0,
                "successes": 0,
                "failures": 0,
                "daily_requests_before": daily_requests_before,
                "daily_request_soft_limit": daily_request_soft_limit,
                "message": "run started",
            },
        )

    if not monitoring_enabled and not args.dry_run:
        message = "Monitoring jest wylaczony w config/settings.yaml."
        print(message)
        _finish_run(db_path, run_id, local_zone, "skipped_disabled", 0, 0, 0, message)
        return 0

    if (
        daily_request_soft_limit is not None
        and not args.dry_run
        and daily_requests_before + len(sorted_points) > daily_request_soft_limit
    ):
        message = (
            "Pominieto cykl, bo przekroczylby dzienny limit miekki: "
            f"{daily_requests_before} + {len(sorted_points)} > {daily_request_soft_limit}."
        )
        print(message)
        _finish_run(db_path, run_id, local_zone, "skipped_limit", 0, 0, 0, message)
        return 0

    if not args.dry_run:
        upsert_points(db_path, points)

    try:
        client = TomTomClient(
            endpoint_base=tomtom_settings.get("endpoint_base", "https://api.tomtom.com/traffic/services/4/flowSegmentData"),
            style=tomtom_settings.get("style", "absolute"),
            zoom=int(tomtom_settings.get("zoom", 10)),
            unit=tomtom_settings.get("unit", "KMPH"),
            timeout_seconds=int(tomtom_settings.get("timeout_seconds", 20)),
        )
    except TomTomAPIError as exc:
        message = f"Nie mozna uruchomic klienta TomTom: {exc}"
        print(message, file=sys.stderr)
        _finish_run(db_path, run_id, local_zone, "failed", 0, 0, len(sorted_points), message)
        return 1

    successes = 0
    failures = 0
    requests_attempted = 0
    for index, point in enumerate(sorted_points):
        if index > 0 and request_delay_seconds > 0:
            time.sleep(request_delay_seconds)
        try:
            requests_attempted += 1
            measurement = client.fetch_flow_segment(
                latitude=float(point["latitude"]),
                longitude=float(point["longitude"]),
                point_id=point["id"],
                point_name=point["name"],
                direction=point.get("direction", ""),
                raw_dir=raw_dir,
            )
            timestamp_utc = datetime.fromisoformat(measurement["timestamp_utc"])
            if timestamp_utc.tzinfo is None:
                timestamp_utc = timestamp_utc.replace(tzinfo=timezone.utc)
            measurement["timestamp_local"] = timestamp_utc.astimezone(local_zone).isoformat()

            metrics = calculate_metrics(
                measurement["current_speed"],
                measurement["free_flow_speed"],
                measurement["current_travel_time"],
                measurement["free_flow_travel_time"],
                confidence=measurement["confidence"],
                road_closure=measurement["road_closure"],
                thresholds=settings.get("thresholds"),
            )
            measurement.update(metrics.as_dict())
            measurement.pop("interpretation", None)

            if not args.dry_run:
                insert_measurement(db_path, measurement)

            successes += 1
            print(
                f"OK {point['id']}: current_speed={measurement['current_speed']} km/h, "
                f"congestion_index={_fmt(measurement['congestion_index'])}, "
                f"delay_ratio={_fmt(measurement['delay_ratio'])}"
            )
        except TomTomAPIError as exc:
            failures += 1
            print(f"BLAD {point['id']}: {exc}", file=sys.stderr)
        except Exception as exc:
            failures += 1
            print(f"BLAD {point['id']}: nieoczekiwany problem: {exc}", file=sys.stderr)

    if failures == 0:
        status = "success"
    elif successes > 0:
        status = "partial"
    else:
        status = "failed"
    message = f"Sukcesy: {successes}, bledy: {failures}."
    _finish_run(db_path, run_id, local_zone, status, requests_attempted, successes, failures, message)
    print(f"Zakonczono pobieranie. Sukcesy: {successes}, bledy: {failures}.")
    return 1 if successes == 0 and failures > 0 else 0


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _load_dotenv_if_available(path: Path) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(path)


def _fmt(value: float | None) -> str:
    return "brak" if value is None else f"{value:.2f}"


def _finish_run(
    db_path: Path,
    run_id: int | None,
    local_zone: ZoneInfo,
    status: str,
    requests_attempted: int,
    successes: int,
    failures: int,
    message: str,
) -> None:
    if run_id is None:
        return
    finished_utc = datetime.now(timezone.utc)
    update_fetch_run(
        db_path,
        run_id,
        {
            "finished_at_utc": finished_utc.isoformat(),
            "finished_at_local": finished_utc.astimezone(local_zone).isoformat(),
            "status": status,
            "requests_attempted": requests_attempted,
            "successes": successes,
            "failures": failures,
            "message": message,
        },
    )


if __name__ == "__main__":
    raise SystemExit(main())
