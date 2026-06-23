"""SQLite persistence for traffic monitoring measurements."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable


MEASUREMENT_FIELDS = [
    "timestamp_utc",
    "timestamp_local",
    "measurement_slot_utc",
    "measurement_slot_local",
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

FETCH_RUN_FIELDS = [
    "started_at_utc",
    "started_at_local",
    "scheduled_slot_utc",
    "scheduled_slot_local",
    "finished_at_utc",
    "finished_at_local",
    "status",
    "trigger",
    "dry_run",
    "monitoring_enabled",
    "points_total",
    "requests_attempted",
    "successes",
    "failures",
    "daily_requests_before",
    "daily_request_soft_limit",
    "message",
]


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def init_db(db_path: str | Path) -> None:
    """Create the SQLite schema if it does not already exist."""

    with connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS points (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                direction TEXT,
                location_description TEXT,
                corridor_order INTEGER
            );

            CREATE TABLE IF NOT EXISTS measurements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp_utc TEXT NOT NULL,
                timestamp_local TEXT NOT NULL,
                measurement_slot_utc TEXT,
                measurement_slot_local TEXT,
                point_id TEXT NOT NULL,
                point_name TEXT,
                direction TEXT,
                latitude REAL,
                longitude REAL,
                current_speed REAL,
                free_flow_speed REAL,
                current_travel_time REAL,
                free_flow_travel_time REAL,
                confidence REAL,
                road_closure INTEGER,
                congestion_index REAL,
                delay_ratio REAL,
                delay_seconds REAL,
                raw_json TEXT,
                FOREIGN KEY(point_id) REFERENCES points(id)
            );

            CREATE INDEX IF NOT EXISTS idx_measurements_local_date
                ON measurements(timestamp_local);
            CREATE INDEX IF NOT EXISTS idx_measurements_point_date
                ON measurements(point_id, timestamp_local);

            CREATE TABLE IF NOT EXISTS fetch_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at_utc TEXT NOT NULL,
                started_at_local TEXT NOT NULL,
                scheduled_slot_utc TEXT,
                scheduled_slot_local TEXT,
                finished_at_utc TEXT,
                finished_at_local TEXT,
                status TEXT NOT NULL,
                trigger TEXT,
                dry_run INTEGER NOT NULL DEFAULT 0,
                monitoring_enabled INTEGER NOT NULL DEFAULT 1,
                points_total INTEGER NOT NULL DEFAULT 0,
                requests_attempted INTEGER NOT NULL DEFAULT 0,
                successes INTEGER NOT NULL DEFAULT 0,
                failures INTEGER NOT NULL DEFAULT 0,
                daily_requests_before INTEGER NOT NULL DEFAULT 0,
                daily_request_soft_limit INTEGER,
                message TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_fetch_runs_started_local
                ON fetch_runs(started_at_local);
            CREATE INDEX IF NOT EXISTS idx_fetch_runs_status
                ON fetch_runs(status);
            """
        )
        _ensure_column(connection, "measurements", "measurement_slot_utc", "TEXT")
        _ensure_column(connection, "measurements", "measurement_slot_local", "TEXT")
        _ensure_column(connection, "fetch_runs", "scheduled_slot_utc", "TEXT")
        _ensure_column(connection, "fetch_runs", "scheduled_slot_local", "TEXT")


def upsert_points(db_path: str | Path, points: Iterable[dict[str, Any]]) -> None:
    """Insert or update measurement point metadata."""

    init_db(db_path)
    with connect(db_path) as connection:
        connection.executemany(
            """
            INSERT INTO points (
                id, name, latitude, longitude, direction,
                location_description, corridor_order
            )
            VALUES (
                :id, :name, :latitude, :longitude, :direction,
                :location_description, :corridor_order
            )
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                latitude = excluded.latitude,
                longitude = excluded.longitude,
                direction = excluded.direction,
                location_description = excluded.location_description,
                corridor_order = excluded.corridor_order;
            """,
            [_normalize_point(point) for point in points],
        )


def insert_measurement(db_path: str | Path, measurement: dict[str, Any]) -> int:
    """Persist one normalized measurement and return its database id."""

    init_db(db_path)
    record = dict(measurement)
    raw_json = record.get("raw_json")
    if raw_json is not None and not isinstance(raw_json, str):
        record["raw_json"] = json.dumps(raw_json, ensure_ascii=False)
    record["road_closure"] = int(bool(record.get("road_closure")))

    placeholders = ", ".join(f":{field}" for field in MEASUREMENT_FIELDS)
    columns = ", ".join(MEASUREMENT_FIELDS)
    sql = f"INSERT INTO measurements ({columns}) VALUES ({placeholders})"

    with connect(db_path) as connection:
        cursor = connection.execute(sql, {field: record.get(field) for field in MEASUREMENT_FIELDS})
        return int(cursor.lastrowid)


def create_fetch_run(db_path: str | Path, run: dict[str, Any]) -> int:
    """Create a run log entry and return its id."""

    init_db(db_path)
    record = dict(run)
    record["dry_run"] = int(bool(record.get("dry_run")))
    record["monitoring_enabled"] = int(bool(record.get("monitoring_enabled", True)))
    placeholders = ", ".join(f":{field}" for field in FETCH_RUN_FIELDS)
    columns = ", ".join(FETCH_RUN_FIELDS)
    sql = f"INSERT INTO fetch_runs ({columns}) VALUES ({placeholders})"

    with connect(db_path) as connection:
        cursor = connection.execute(sql, {field: record.get(field) for field in FETCH_RUN_FIELDS})
        return int(cursor.lastrowid)


def update_fetch_run(db_path: str | Path, run_id: int, updates: dict[str, Any]) -> None:
    """Update a run log entry."""

    if not updates:
        return
    init_db(db_path)
    record = dict(updates)
    if "dry_run" in record:
        record["dry_run"] = int(bool(record["dry_run"]))
    if "monitoring_enabled" in record:
        record["monitoring_enabled"] = int(bool(record["monitoring_enabled"]))

    allowed = [field for field in FETCH_RUN_FIELDS if field in record]
    if not allowed:
        return

    assignments = ", ".join(f"{field} = :{field}" for field in allowed)
    record["id"] = run_id
    with connect(db_path) as connection:
        connection.execute(
            f"UPDATE fetch_runs SET {assignments} WHERE id = :id",
            {field: record[field] for field in allowed + ["id"]},
        )


def get_measurements_for_date(
    db_path: str | Path,
    date_iso: str,
) -> list[dict[str, Any]]:
    """Return all measurements whose local timestamp starts with YYYY-MM-DD."""

    init_db(db_path)
    with connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM measurements
            WHERE substr(timestamp_local, 1, 10) = ?
            ORDER BY timestamp_local, point_id
            """,
            (date_iso,),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def get_fetch_runs_for_date(
    db_path: str | Path,
    date_iso: str,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return run log entries whose local start timestamp is on YYYY-MM-DD."""

    init_db(db_path)
    sql = """
        SELECT *
        FROM fetch_runs
        WHERE substr(started_at_local, 1, 10) = ?
        ORDER BY started_at_local DESC
    """
    params: tuple[Any, ...] = (date_iso,)
    if limit is not None:
        sql += " LIMIT ?"
        params = (date_iso, limit)

    with connect(db_path) as connection:
        rows = connection.execute(sql, params).fetchall()
    return [_row_to_dict(row) for row in rows]


def get_latest_fetch_run(db_path: str | Path) -> dict[str, Any] | None:
    init_db(db_path)
    with connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT *
            FROM fetch_runs
            ORDER BY started_at_utc DESC
            LIMIT 1
            """
        ).fetchone()
    return _row_to_dict(row) if row else None


def get_daily_request_total(db_path: str | Path, date_iso: str) -> int:
    """Return the number of API requests attempted for a local calendar day."""

    init_db(db_path)
    with connect(db_path) as connection:
        value = connection.execute(
            """
            SELECT COALESCE(SUM(requests_attempted), 0)
            FROM fetch_runs
            WHERE substr(started_at_local, 1, 10) = ?
            """,
            (date_iso,),
        ).fetchone()[0]
    return int(value or 0)


def get_measurement_count_for_date(db_path: str | Path, date_iso: str) -> int:
    init_db(db_path)
    with connect(db_path) as connection:
        value = connection.execute(
            """
            SELECT COUNT(*)
            FROM measurements
            WHERE substr(timestamp_local, 1, 10) = ?
            """,
            (date_iso,),
        ).fetchone()[0]
    return int(value or 0)


def get_points(db_path: str | Path) -> list[dict[str, Any]]:
    init_db(db_path)
    with connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM points
            ORDER BY corridor_order, id
            """
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def _normalize_point(point: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": point["id"],
        "name": point["name"],
        "latitude": point["latitude"],
        "longitude": point["longitude"],
        "direction": point.get("direction"),
        "location_description": point.get("location_description"),
        "corridor_order": point.get("corridor_order"),
    }


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    if "road_closure" in result:
        result["road_closure"] = bool(result["road_closure"])
    for key in ("dry_run", "monitoring_enabled"):
        if key in result:
            result[key] = bool(result[key])
    return result


def _ensure_column(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_type: str,
) -> None:
    columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
