#!/usr/bin/env python
"""Generate the static monitoring dashboard."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from awp_traffic.dashboard import generate_dashboard
from awp_traffic.database import (
    get_daily_request_total,
    get_fetch_runs_for_date,
    get_latest_fetch_run,
    get_measurements_for_date,
    upsert_points,
)
from awp_traffic.maps import create_points_map


def main() -> int:
    parser = argparse.ArgumentParser(description="Wygeneruj statyczny pulpit monitoringu.")
    parser.add_argument("--date", default=None, help="Data YYYY-MM-DD. Domyslnie dzisiaj lokalnie.")
    parser.add_argument("--points", default="config/points.yaml", help="Sciezka do points.yaml.")
    parser.add_argument("--settings", default="config/settings.yaml", help="Sciezka do settings.yaml.")
    parser.add_argument("--database", default=None, help="Sciezka do bazy SQLite.")
    parser.add_argument("--skip-map", action="store_true", help="Nie generuj mapy punktow.")
    args = parser.parse_args()

    settings = _load_yaml(PROJECT_ROOT / args.settings)
    points = _load_yaml(PROJECT_ROOT / args.points)["points"]
    timezone_name = settings.get("project", {}).get("timezone", "Europe/Warsaw")
    local_zone = ZoneInfo(timezone_name)
    date_iso = args.date or datetime.now(local_zone).date().isoformat()
    db_path = PROJECT_ROOT / (args.database or settings.get("database", {}).get("path", "data/awp_traffic.sqlite"))

    upsert_points(db_path, points)

    report_settings = settings.get("report", {})
    dashboard_settings = settings.get("dashboard", {})
    maps_dir = PROJECT_ROOT / report_settings.get("maps_dir", "reports/maps")
    if not args.skip_map:
        create_points_map(points, maps_dir / "awp_points.html")

    html_path, json_path = generate_dashboard(
        date_iso=date_iso,
        settings=settings,
        points=points,
        measurements=get_measurements_for_date(db_path, date_iso),
        fetch_runs=get_fetch_runs_for_date(db_path, date_iso, limit=32),
        latest_run=get_latest_fetch_run(db_path),
        request_total=get_daily_request_total(db_path, date_iso),
        output_dir=PROJECT_ROOT / dashboard_settings.get("output_dir", "reports/dashboard"),
    )
    print(f"Pulpit HTML: {html_path}")
    print(f"Status JSON: {json_path}")
    return 0


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


if __name__ == "__main__":
    raise SystemExit(main())
