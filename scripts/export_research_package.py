#!/usr/bin/env python
"""Export all collected measurements as a browser-downloadable ZIP package."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from awp_traffic.database import (
    get_all_fetch_runs,
    get_all_measurements,
    get_all_route_measurements,
)
from awp_traffic.research_export import create_research_package
from awp_traffic.route_estimation import (
    estimate_route_measurements,
    merge_route_measurements,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Eksportuj caly pakiet badawczy AWP.")
    parser.add_argument("--settings", default="config/settings.yaml")
    parser.add_argument("--points", default="config/points.yaml")
    parser.add_argument("--routes", default="config/routes.yaml")
    parser.add_argument("--database", default=None)
    parser.add_argument(
        "--output",
        default="reports/downloads/awp_research_latest.zip",
    )
    args = parser.parse_args()

    settings = _load_yaml(PROJECT_ROOT / args.settings)
    points = _load_yaml(PROJECT_ROOT / args.points).get("points", [])
    routes = _load_yaml(PROJECT_ROOT / args.routes).get("routes", [])
    db_path = PROJECT_ROOT / (
        args.database
        or settings.get("database", {}).get("path", "data/awp_traffic.sqlite")
    )
    measurements = get_all_measurements(db_path)
    direct_routes = get_all_route_measurements(db_path)
    estimation_settings = settings.get("route_estimation", {})
    estimates = estimate_route_measurements(
        routes=routes,
        points=points,
        measurements=measurements,
        require_all_points=bool(
            estimation_settings.get("require_all_points", True)
        ),
    )
    route_measurements = merge_route_measurements(estimates, direct_routes)
    output_path = PROJECT_ROOT / args.output
    package_path = create_research_package(
        output_path=output_path,
        measurements=measurements,
        route_measurements=route_measurements,
        fetch_runs=get_all_fetch_runs(db_path),
        points=points,
        routes=routes,
        project_name=settings.get("project", {}).get("name", "AWP traffic monitor"),
        timezone_name=settings.get("project", {}).get("timezone", "Europe/Warsaw"),
    )
    print(f"Pakiet badawczy: {package_path}")
    print(f"Pomiary punktow: {len(measurements)}")
    print(f"Estymacje tras: {len(route_measurements)}")
    return 0


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


if __name__ == "__main__":
    raise SystemExit(main())
