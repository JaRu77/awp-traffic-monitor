#!/usr/bin/env python
"""Export one local day of measurements from SQLite to CSV."""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from awp_traffic.database import get_measurements_for_date


def main() -> int:
    parser = argparse.ArgumentParser(description="Eksportuj pomiary z wybranej daty do CSV.")
    parser.add_argument("--date", default=None, help="Data YYYY-MM-DD. Domyslnie dzisiaj lokalnie.")
    parser.add_argument("--settings", default="config/settings.yaml", help="Sciezka do settings.yaml.")
    parser.add_argument("--database", default=None, help="Sciezka do bazy SQLite.")
    parser.add_argument("--output", default=None, help="Sciezka pliku wynikowego CSV.")
    args = parser.parse_args()

    settings = _load_yaml(PROJECT_ROOT / args.settings)
    timezone_name = settings.get("project", {}).get("timezone", "Europe/Warsaw")
    target_date = args.date or datetime.now(ZoneInfo(timezone_name)).date().isoformat()
    db_path = PROJECT_ROOT / (args.database or settings.get("database", {}).get("path", "data/awp_traffic.sqlite"))
    rows = get_measurements_for_date(db_path, target_date)

    output_path = Path(args.output) if args.output else PROJECT_ROOT / "data" / "processed" / f"awp_traffic_{target_date}.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if rows:
        fieldnames = list(rows[0].keys())
    else:
        fieldnames = [
            "id",
            "timestamp_utc",
            "timestamp_local",
            "point_id",
            "point_name",
            "direction",
            "latitude",
            "longitude",
            "current_speed",
            "free_flow_speed",
            "current_travel_time",
            "free_flow_travel_time",
            "confidence",
            "road_closure",
            "congestion_index",
            "delay_ratio",
            "delay_seconds",
            "raw_json",
        ]

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Zapisano {len(rows)} rekordow do {output_path}")
    return 0


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


if __name__ == "__main__":
    raise SystemExit(main())
