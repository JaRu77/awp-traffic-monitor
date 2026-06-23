#!/usr/bin/env python
"""Fetch TomTom Routing API travel times for configured AWP route sections."""

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
    get_route_ids_for_slot,
    insert_route_measurement,
    update_fetch_run,
    upsert_routes,
)
from awp_traffic.tomtom_client import TomTomAPIError, TomTomClient


def main() -> int:
    parser = argparse.ArgumentParser(description="Pobierz czasy przejazdu tras z TomTom Routing API.")
    parser.add_argument("--routes", default="config/routes.yaml", help="Sciezka do routes.yaml.")
    parser.add_argument("--settings", default="config/settings.yaml", help="Sciezka do settings.yaml.")
    parser.add_argument("--database", default=None, help="Sciezka do bazy SQLite.")
    parser.add_argument("--dry-run", action="store_true", help="Pobierz dane, ale nie zapisuj do SQLite.")
    parser.add_argument("--force", action="store_true", help="Uruchom nawet gdy routing.enabled=false.")
    parser.add_argument("--log-dry-run", action="store_true", help="Zapisz dry-run w tabeli fetch_runs.")
    args = parser.parse_args()

    _load_dotenv_if_available(PROJECT_ROOT / ".env")
    settings = _load_yaml(PROJECT_ROOT / args.settings)
    routes_path = PROJECT_ROOT / args.routes
    routes = _load_yaml(routes_path).get("routes", [])
    project_settings = settings.get("project", {})
    monitoring_settings = settings.get("monitoring", {})
    tomtom_settings = settings.get("tomtom", {})
    routing_settings = settings.get("routing", {})

    timezone_name = project_settings.get("timezone", "Europe/Warsaw")
    interval_minutes = int(project_settings.get("measurement_interval_minutes", 15))
    local_zone = ZoneInfo(timezone_name)
    db_path = PROJECT_ROOT / (args.database or settings.get("database", {}).get("path", "data/awp_traffic.sqlite"))
    raw_dir = PROJECT_ROOT / routing_settings.get("raw_dir", "data/raw_routes")
    request_delay_seconds = float(tomtom_settings.get("request_delay_seconds", 0))
    sorted_routes = sorted(routes, key=lambda item: item.get("corridor_order", 0))
    routing_enabled = bool(routing_settings.get("enabled", False))
    daily_request_soft_limit = monitoring_settings.get("daily_request_soft_limit")
    daily_request_soft_limit = int(daily_request_soft_limit) if daily_request_soft_limit is not None else None

    started_utc = datetime.now(timezone.utc)
    started_local = started_utc.astimezone(local_zone)
    scheduled_slot_utc = _floor_to_interval(started_utc, interval_minutes)
    scheduled_slot_local = scheduled_slot_utc.astimezone(local_zone)
    scheduled_slot_local_text = scheduled_slot_local.isoformat()
    scheduled_slot_utc_text = scheduled_slot_utc.isoformat()
    local_date = started_local.date().isoformat()
    daily_requests_before = get_daily_request_total(db_path, local_date)
    existing_route_ids = (
        get_route_ids_for_slot(db_path, scheduled_slot_local_text)
        if not args.dry_run
        else set()
    )
    remaining_routes = [
        route
        for route in sorted_routes
        if route["id"] not in existing_route_ids
    ]
    should_log_run = not args.dry_run or args.log_dry_run
    run_id: int | None = None

    if should_log_run:
        run_id = create_fetch_run(
            db_path,
            {
                "started_at_utc": started_utc.isoformat(),
                "started_at_local": started_local.isoformat(),
                "scheduled_slot_utc": scheduled_slot_utc_text,
                "scheduled_slot_local": scheduled_slot_local_text,
                "finished_at_utc": None,
                "finished_at_local": None,
                "status": "started_routes",
                "trigger": f"{os.getenv('GITHUB_EVENT_NAME', 'local')}:routes",
                "dry_run": args.dry_run,
                "monitoring_enabled": routing_enabled or args.force,
                "points_total": len(sorted_routes),
                "requests_attempted": 0,
                "successes": 0,
                "failures": 0,
                "daily_requests_before": daily_requests_before,
                "daily_request_soft_limit": daily_request_soft_limit,
                "message": "route run started",
            },
        )

    if not routing_enabled and not args.force:
        message = "Routing API jest wylaczone w config/settings.yaml. Uzyj --force do testu."
        print(message)
        _finish_run(db_path, run_id, local_zone, "skipped_routes_disabled", 0, 0, 0, message)
        return 0

    if not sorted_routes:
        message = f"Brak tras w {routes_path}."
        print(message)
        _finish_run(db_path, run_id, local_zone, "skipped_no_routes", 0, 0, 0, message)
        return 0

    if (
        daily_request_soft_limit is not None
        and not args.dry_run
        and daily_requests_before + len(remaining_routes) > daily_request_soft_limit
    ):
        message = (
            "Pominieto cykl tras, bo przekroczylby dzienny limit miekki: "
            f"{daily_requests_before} + {len(remaining_routes)} > {daily_request_soft_limit}."
        )
        print(message)
        _finish_run(db_path, run_id, local_zone, "skipped_limit", 0, 0, 0, message)
        return 0

    if not remaining_routes and not args.dry_run:
        message = f"Slot tras jest juz kompletny: {scheduled_slot_local_text}. Nie zuzyto API."
        print(message)
        _finish_run(db_path, run_id, local_zone, "skipped_complete", 0, 0, 0, message)
        return 0

    if not args.dry_run:
        upsert_routes(db_path, sorted_routes)

    try:
        client = TomTomClient(
            endpoint_base=tomtom_settings.get("endpoint_base", "https://api.tomtom.com/traffic/services/4/flowSegmentData"),
            routing_endpoint_base=tomtom_settings.get("routing_endpoint_base", "https://api.tomtom.com/routing/1/calculateRoute"),
            style=tomtom_settings.get("style", "absolute"),
            zoom=int(tomtom_settings.get("zoom", 10)),
            unit=tomtom_settings.get("unit", "KMPH"),
            timeout_seconds=int(tomtom_settings.get("timeout_seconds", 20)),
        )
    except TomTomAPIError as exc:
        message = f"Nie mozna uruchomic klienta TomTom: {exc}"
        print(message, file=sys.stderr)
        _finish_run(db_path, run_id, local_zone, "failed", 0, 0, len(sorted_routes), message)
        return 1

    successes = 0
    failures = 0
    requests_attempted = 0
    for index, route in enumerate(remaining_routes):
        if index > 0 and request_delay_seconds > 0:
            time.sleep(request_delay_seconds)
        try:
            requests_attempted += 1
            measurement = client.fetch_route(
                route_id=route["id"],
                route_name=route["name"],
                direction=route.get("direction", ""),
                coordinates=route["coordinates"],
                raw_dir=raw_dir,
                travel_mode=routing_settings.get("travel_mode", "car"),
                route_type=routing_settings.get("route_type", "fastest"),
                traffic=bool(routing_settings.get("traffic", True)),
            )
            timestamp_utc = datetime.fromisoformat(measurement["timestamp_utc"])
            if timestamp_utc.tzinfo is None:
                timestamp_utc = timestamp_utc.replace(tzinfo=timezone.utc)
            measurement["timestamp_local"] = timestamp_utc.astimezone(local_zone).isoformat()
            measurement["measurement_slot_utc"] = scheduled_slot_utc_text
            measurement["measurement_slot_local"] = scheduled_slot_local_text

            if not args.dry_run:
                insert_route_measurement(db_path, measurement)

            successes += 1
            print(
                f"OK {route['id']}: travel_time={_fmt(measurement['travel_time_seconds'])} s, "
                f"delay={_fmt(measurement['delay_seconds'])} s, "
                f"delay_ratio={_fmt(measurement['delay_ratio'])}"
            )
        except TomTomAPIError as exc:
            failures += 1
            print(f"BLAD {route['id']}: {exc}", file=sys.stderr)
        except Exception as exc:
            failures += 1
            print(f"BLAD {route['id']}: nieoczekiwany problem: {exc}", file=sys.stderr)

    if failures == 0:
        status = "success"
    elif successes > 0:
        status = "partial"
    else:
        status = "failed"
    skipped_existing = len(existing_route_ids)
    message = f"Trasy: sukcesy {successes}, bledy {failures}, pominiete istniejace {skipped_existing}."
    _finish_run(db_path, run_id, local_zone, status, requests_attempted, successes, failures, message)
    print(f"Zakonczono pobieranie tras. Sukcesy: {successes}, bledy: {failures}.")
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


def _floor_to_interval(value: datetime, interval_minutes: int) -> datetime:
    if interval_minutes <= 0:
        return value.replace(second=0, microsecond=0)
    total_minutes = value.hour * 60 + value.minute
    floored_minutes = (total_minutes // interval_minutes) * interval_minutes
    return value.replace(
        hour=floored_minutes // 60,
        minute=floored_minutes % 60,
        second=0,
        microsecond=0,
    )


if __name__ == "__main__":
    raise SystemExit(main())
