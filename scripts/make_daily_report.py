#!/usr/bin/env python
"""Create a Markdown and HTML daily traffic report."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from awp_traffic.database import get_measurements_for_date, upsert_points
from awp_traffic.maps import create_points_map
from awp_traffic.reporting import generate_daily_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Wygeneruj raport dobowy.")
    parser.add_argument("--date", default=None, help="Data raportu YYYY-MM-DD. Domyslnie dzisiaj lokalnie.")
    parser.add_argument("--days-back", type=int, default=0, help="Liczba dni wstecz wzgledem daty lokalnej.")
    parser.add_argument("--points", default="config/points.yaml", help="Sciezka do points.yaml.")
    parser.add_argument("--settings", default="config/settings.yaml", help="Sciezka do settings.yaml.")
    parser.add_argument("--database", default=None, help="Sciezka do bazy SQLite.")
    parser.add_argument("--skip-map", action="store_true", help="Nie generuj mapy punktow.")
    args = parser.parse_args()

    settings = _load_yaml(PROJECT_ROOT / args.settings)
    points = _load_yaml(PROJECT_ROOT / args.points)["points"]
    timezone_name = settings.get("project", {}).get("timezone", "Europe/Warsaw")
    local_zone = ZoneInfo(timezone_name)
    target_date = args.date or (datetime.now(local_zone).date() - timedelta(days=args.days_back)).isoformat()

    db_path = PROJECT_ROOT / (args.database or settings.get("database", {}).get("path", "data/awp_traffic.sqlite"))
    upsert_points(db_path, points)
    measurements = get_measurements_for_date(db_path, target_date)

    report_settings = settings.get("report", {})
    output_dir = PROJECT_ROOT / report_settings.get("output_dir", "reports/daily")
    figures_dir = PROJECT_ROOT / report_settings.get("figures_dir", "reports/figures")
    maps_dir = PROJECT_ROOT / report_settings.get("maps_dir", "reports/maps")

    if not args.skip_map and report_settings.get("include_point_map", True):
        map_path = create_points_map(points, maps_dir / "awp_points.html")
        print(f"Mapa punktow: {map_path}")

    markdown_path, html_path = generate_daily_report(
        date_iso=target_date,
        measurements=measurements,
        settings=settings,
        output_dir=output_dir,
        figures_dir=figures_dir,
    )
    print(f"Raport Markdown: {markdown_path}")
    print(f"Raport HTML: {html_path}")
    return 0


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


if __name__ == "__main__":
    raise SystemExit(main())
