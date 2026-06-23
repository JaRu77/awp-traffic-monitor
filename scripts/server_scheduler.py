#!/usr/bin/env python
"""Long-running scheduler for VPS/server deployments."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Uruchom serwerowy scheduler monitoringu AWP.")
    parser.add_argument("--settings", default="config/settings.yaml", help="Sciezka do settings.yaml.")
    parser.add_argument("--once", action="store_true", help="Wykonaj jeden cykl od razu i zakoncz.")
    parser.add_argument("--skip-routes", action="store_true", help="Nie uruchamiaj pomiarow tras Routing API.")
    parser.add_argument("--skip-dashboard", action="store_true", help="Nie generuj dashboardu po cyklu.")
    parser.add_argument("--skip-daily-report", action="store_true", help="Nie generuj raportu dobowego.")
    args = parser.parse_args()

    os.chdir(PROJECT_ROOT)
    settings = _load_yaml(PROJECT_ROOT / args.settings)
    project_settings = settings.get("project", {})
    server_settings = settings.get("server", {})
    routing_settings = settings.get("routing", {})
    timezone_name = project_settings.get("timezone", "Europe/Warsaw")
    local_zone = ZoneInfo(timezone_name)
    interval_minutes = int(project_settings.get("measurement_interval_minutes", 15))
    routes_enabled = bool(routing_settings.get("enabled", False)) and not args.skip_routes
    dashboard_enabled = bool(server_settings.get("generate_dashboard_after_cycle", True)) and not args.skip_dashboard
    daily_enabled = bool(server_settings.get("generate_daily_report", True)) and not args.skip_daily_report
    daily_report_time = str(server_settings.get("daily_report_time", "00:20"))

    _log("Start serwerowego schedulera AWP.")
    _log(f"Strefa: {timezone_name}; interwal: {interval_minutes} min; trasy Routing API: {'tak' if routes_enabled else 'nie'}.")

    if args.once:
        return _run_cycle(
            routes_enabled=routes_enabled,
            dashboard_enabled=dashboard_enabled,
            daily_enabled=daily_enabled,
            daily_report_time=daily_report_time,
            local_zone=local_zone,
            last_daily_report_date=None,
        )[0]

    last_daily_report_date: str | None = None
    while True:
        now_local = datetime.now(local_zone)
        next_slot = _next_slot(now_local, interval_minutes)
        sleep_seconds = max(1, int((next_slot - now_local).total_seconds()))
        _log(f"Nastepny slot pomiarowy: {next_slot.isoformat(timespec='seconds')}. Spie {sleep_seconds}s.")
        time.sleep(sleep_seconds)

        _, last_daily_report_date = _run_cycle(
            routes_enabled=routes_enabled,
            dashboard_enabled=dashboard_enabled,
            daily_enabled=daily_enabled,
            daily_report_time=daily_report_time,
            local_zone=local_zone,
            last_daily_report_date=last_daily_report_date,
        )


def _run_cycle(
    *,
    routes_enabled: bool,
    dashboard_enabled: bool,
    daily_enabled: bool,
    daily_report_time: str,
    local_zone: ZoneInfo,
    last_daily_report_date: str | None,
) -> tuple[int, str | None]:
    started = datetime.now(local_zone)
    _log(f"Start cyklu: {started.isoformat(timespec='seconds')}")

    exit_codes = []
    exit_codes.append(_run_command([sys.executable, "scripts/fetch_traffic.py"]))

    if routes_enabled:
        exit_codes.append(_run_command([sys.executable, "scripts/fetch_routes.py"]))

    if dashboard_enabled:
        exit_codes.append(_run_command([sys.executable, "scripts/make_dashboard.py"]))

    if daily_enabled and _should_make_daily_report(started, daily_report_time, last_daily_report_date):
        report_date = (started.date() - timedelta(days=1)).isoformat()
        exit_codes.append(_run_command([sys.executable, "scripts/make_daily_report.py", "--date", report_date]))
        last_daily_report_date = report_date

    failed = [code for code in exit_codes if code != 0]
    if failed:
        _log(f"Cykl zakonczony z bledami: {failed}")
        return 1, last_daily_report_date

    _log("Cykl zakonczony poprawnie.")
    return 0, last_daily_report_date


def _run_command(command: list[str]) -> int:
    _log("Uruchamiam: " + " ".join(command))
    completed = subprocess.run(command, cwd=PROJECT_ROOT)
    _log(f"Kod wyjscia: {completed.returncode}")
    return int(completed.returncode)


def _next_slot(now_local: datetime, interval_minutes: int) -> datetime:
    if interval_minutes <= 0:
        return now_local + timedelta(minutes=1)

    current_minutes = now_local.hour * 60 + now_local.minute
    next_minutes = ((current_minutes // interval_minutes) + 1) * interval_minutes
    next_date = now_local.date()
    if next_minutes >= 24 * 60:
        next_minutes -= 24 * 60
        next_date = next_date + timedelta(days=1)

    return datetime(
        next_date.year,
        next_date.month,
        next_date.day,
        next_minutes // 60,
        next_minutes % 60,
        2,
        tzinfo=now_local.tzinfo,
    )


def _should_make_daily_report(
    now_local: datetime,
    daily_report_time: str,
    last_daily_report_date: str | None,
) -> bool:
    try:
        hour_text, minute_text = daily_report_time.split(":", 1)
        report_time = now_local.replace(
            hour=int(hour_text),
            minute=int(minute_text),
            second=0,
            microsecond=0,
        )
    except ValueError:
        report_time = now_local.replace(hour=0, minute=20, second=0, microsecond=0)

    report_date = (now_local.date() - timedelta(days=1)).isoformat()
    return now_local >= report_time and last_daily_report_date != report_date


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _log(message: str) -> None:
    timestamp = datetime.now().isoformat(timespec="seconds")
    print(f"[{timestamp}] {message}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
