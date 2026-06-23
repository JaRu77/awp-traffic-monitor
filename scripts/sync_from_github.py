#!/usr/bin/env python
"""Synchronize local dashboard files with the latest GitHub state."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REMOTE = "origin"
BRANCH = "main"

SYNC_PATHS = [
    "data/awp_traffic.sqlite",
    "reports/dashboard/index.html",
    "reports/dashboard/status.json",
    "reports/maps/awp_points.html",
    "reports/dashboard/maps/awp_points.html",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Pobierz najnowszy stan dashboardu z GitHuba.")
    parser.add_argument("--remote", default=REMOTE, help="Nazwa remote git.")
    parser.add_argument("--branch", default=BRANCH, help="Nazwa brancha.")
    args = parser.parse_args()

    safe_dir = PROJECT_ROOT.as_posix()
    ref = f"{args.remote}/{args.branch}"

    print("Pobieram najnowszy stan z GitHuba...")
    fetch = _run_git(["fetch", args.remote, args.branch], safe_dir=safe_dir)
    if fetch.returncode != 0:
        _print_git_error(fetch)
        return fetch.returncode

    copied = []
    for relative_path in SYNC_PATHS:
        target = PROJECT_ROOT / relative_path
        blob = _git_blob(ref, relative_path, safe_dir=safe_dir)
        if blob is None:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)
        copied.append(relative_path)

    if not copied:
        print("Nie znaleziono plikow dashboardu do synchronizacji.")
        return 1

    print("Zsynchronizowano:")
    for path in copied:
        print(f"  - {path}")

    _print_status_summary(PROJECT_ROOT / "reports" / "dashboard" / "status.json")
    return 0


def _run_git(args: list[str], *, safe_dir: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-c", f"safe.directory={safe_dir}", *args],
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _git_blob(ref: str, relative_path: str, *, safe_dir: str) -> bytes | None:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={safe_dir}", "cat-file", "blob", f"{ref}:{relative_path}"],
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def _print_git_error(result: subprocess.CompletedProcess[str]) -> None:
    print("Nie udalo sie pobrac danych z GitHuba.", file=sys.stderr)
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    elif result.stdout.strip():
        print(result.stdout.strip(), file=sys.stderr)


def _print_status_summary(status_path: Path) -> None:
    if not status_path.exists():
        return
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return

    print()
    print("Stan badania:")
    print(f"  data: {status.get('date', 'brak')}")
    print(f"  status ostatniego cyklu: {status.get('latest_run_status', 'brak')}")
    print(f"  requesty dzis: {status.get('request_total', 'brak')}")
    print(f"  sloty dzis: {status.get('completed_slots_today', 'brak')} / {status.get('expected_slots_so_far', 'brak')}")
    print(f"  braki slotow: {status.get('missing_slots_so_far', 'brak')}")
    print(f"  wiek danych: {_age_label(status.get('stale_minutes'))}")
    slot = status.get("latest_scheduled_slot") or status.get("latest_measurement")
    print(f"  slot pomiaru: {_short_time(slot)}")
    print(f"  pobrano faktycznie: {_short_time(status.get('latest_measurement'))}")


def _short_time(value: object) -> str:
    if not value:
        return "brak"
    text = str(value)
    if "T" in text:
        date_part, time_part = text.split("T", 1)
        return f"{date_part} {time_part[:5]}"
    return text[:16]


def _age_label(value: object) -> str:
    if value is None:
        return "brak"
    return f"{value} min"


if __name__ == "__main__":
    raise SystemExit(main())
