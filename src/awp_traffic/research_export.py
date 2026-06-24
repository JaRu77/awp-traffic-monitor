"""Create a portable research dataset from the monitoring database."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


MEASUREMENT_EXCLUDED_FIELDS = {"raw_json"}
ROUTE_EXCLUDED_FIELDS = {"raw_json"}


def create_research_package(
    *,
    output_path: str | Path,
    measurements: list[dict[str, Any]],
    route_measurements: list[dict[str, Any]],
    fetch_runs: list[dict[str, Any]],
    points: list[dict[str, Any]],
    routes: list[dict[str, Any]],
    project_name: str,
    timezone_name: str,
) -> Path:
    """Write analysis-ready CSV files and metadata into one ZIP archive."""

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(ZoneInfo(timezone_name)).isoformat(
        timespec="seconds"
    )
    dates = sorted(
        {
            str(row.get("timestamp_local"))[:10]
            for row in measurements
            if row.get("timestamp_local")
        }
    )
    metadata = {
        "project": project_name,
        "generated_at": generated_at,
        "timezone": timezone_name,
        "date_from": dates[0] if dates else None,
        "date_to": dates[-1] if dates else None,
        "measurement_rows": len(measurements),
        "route_estimate_rows": len(route_measurements),
        "fetch_run_rows": len(fetch_runs),
        "points": len(points),
        "routes": len(routes),
        "raw_json_included": False,
    }

    with zipfile.ZipFile(
        output_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
    ) as archive:
        archive.writestr(
            "measurements.csv",
            _rows_to_csv(measurements, excluded=MEASUREMENT_EXCLUDED_FIELDS),
        )
        archive.writestr(
            "route_estimates.csv",
            _rows_to_csv(route_measurements, excluded=ROUTE_EXCLUDED_FIELDS),
        )
        archive.writestr("fetch_runs.csv", _rows_to_csv(fetch_runs))
        archive.writestr("points.csv", _rows_to_csv(points))
        archive.writestr("routes.csv", _route_config_to_csv(routes))
        archive.writestr(
            "metadata.json",
            json.dumps(metadata, ensure_ascii=False, indent=2),
        )
        archive.writestr("README.txt", _package_readme(metadata))
    return output_path


def _rows_to_csv(
    rows: list[dict[str, Any]],
    *,
    excluded: set[str] | None = None,
) -> str:
    excluded = excluded or set()
    fieldnames = _fieldnames(rows, excluded)
    buffer = io.StringIO(newline="")
    buffer.write("\ufeff")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                key: _csv_value(value)
                for key, value in row.items()
                if key not in excluded
            }
        )
    return buffer.getvalue()


def _route_config_to_csv(routes: list[dict[str, Any]]) -> str:
    normalized = []
    for route in routes:
        normalized.append(
            {
                "id": route.get("id"),
                "name": route.get("name"),
                "direction": route.get("direction"),
                "corridor_order": route.get("corridor_order"),
                "point_ids": "|".join(str(value) for value in route.get("point_ids", [])),
                "coordinates_json": json.dumps(
                    route.get("coordinates", []),
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            }
        )
    return _rows_to_csv(normalized)


def _fieldnames(rows: list[dict[str, Any]], excluded: set[str]) -> list[str]:
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in excluded and key not in fieldnames:
                fieldnames.append(key)
    return fieldnames or ["no_data"]


def _csv_value(value: Any) -> Any:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return value


def _package_readme(metadata: dict[str, Any]) -> str:
    return f"""PAKIET BADAWCZY AWP

Projekt: {metadata['project']}
Wygenerowano: {metadata['generated_at']}
Zakres dat: {metadata['date_from']} - {metadata['date_to']}
Strefa czasowa: {metadata['timezone']}

PLIKI
- measurements.csv: wszystkie pomiary punktow Flow Segment Data.
- route_estimates.csv: estymowane czasy przejazdu obu kierunkow.
- fetch_runs.csv: log cykli, bledow i kompletnosci pobierania.
- points.csv: konfiguracja punktow i role doplywu/odplywu.
- routes.csv: konfiguracja tras i przypisanie punktow.
- metadata.json: liczba rekordow i zakres danych.

UWAGI
- raw_json nie jest dolaczony do lekkiego pakietu analitycznego.
- V swobodna nie jest administracyjnym ograniczeniem predkosci.
- estymacje tras sa pochodne z predkosci Flow, wazonych odlegloscia.
- dane nie mierza liczby pojazdow na godzine.
"""
