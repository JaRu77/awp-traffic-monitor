#!/usr/bin/env python
"""Upload local SQLite backups to a remote rclone target."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REMOTE_PATH = "gdrive:AWP-Traffic-Backups/backups"


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")

    parser = argparse.ArgumentParser(
        description="Utworz lokalny backup SQLite i wyslij go przez rclone."
    )
    parser.add_argument(
        "--local-dir",
        default=os.getenv("LOCAL_BACKUP_DIR", "backups"),
        help="Katalog lokalnych kopii wzgledem katalogu projektu.",
    )
    parser.add_argument(
        "--remote-path",
        default=os.getenv("RCLONE_REMOTE_PATH", DEFAULT_REMOTE_PATH),
        help="Docelowa sciezka rclone, np. gdrive:AWP-Traffic-Backups/backups.",
    )
    parser.add_argument(
        "--keep-days",
        type=int,
        default=int(os.getenv("REMOTE_BACKUP_KEEP_DAYS", "120")),
        help="Usun zdalne kopie starsze niz podana liczba dni; 0 wylacza czyszczenie.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Uruchom nawet gdy REMOTE_BACKUP_ENABLED nie jest true.",
    )
    parser.add_argument(
        "--skip-local-backup",
        action="store_true",
        help="Nie tworz nowej kopii lokalnej przed wysylka.",
    )
    args = parser.parse_args()

    enabled = os.getenv("REMOTE_BACKUP_ENABLED", "false").strip().lower()
    if enabled not in {"1", "true", "yes", "on"} and not args.force:
        print("Zdalny backup jest wylaczony: ustaw REMOTE_BACKUP_ENABLED=true.")
        return 0

    rclone_path = shutil.which("rclone")
    if not rclone_path:
        print("Brak programu rclone. Zainstaluj: sudo apt install -y rclone", file=sys.stderr)
        return 2

    local_dir = PROJECT_ROOT / args.local_dir

    if not args.skip_local_backup:
        backup_cmd = [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "backup_sqlite.py"),
            "--output-dir",
            args.local_dir,
            "--keep",
            "7",
        ]
        _run(backup_cmd)

    if not local_dir.exists():
        print(f"Brak lokalnego katalogu backupow: {local_dir}", file=sys.stderr)
        return 1

    local_backups = sorted(local_dir.glob("awp_traffic_*.sqlite"))
    if not local_backups:
        print(f"Brak lokalnych plikow awp_traffic_*.sqlite w {local_dir}")
        return 0

    remote_path = args.remote_path.rstrip("/")
    _run([rclone_path, "mkdir", remote_path])
    _run(
        [
            rclone_path,
            "copy",
            str(local_dir),
            remote_path,
            "--include",
            "awp_traffic_*.sqlite",
            "--transfers",
            "1",
            "--checkers",
            "4",
            "--log-level",
            "INFO",
        ]
    )

    if args.keep_days > 0:
        _run(
            [
                rclone_path,
                "delete",
                remote_path,
                "--min-age",
                f"{args.keep_days}d",
                "--include",
                "awp_traffic_*.sqlite",
                "--log-level",
                "INFO",
            ]
        )

    print(f"Zdalny backup zakonczony: {remote_path}")
    print(f"Lokalne kopie wyslane: {len(local_backups)}")
    return 0


def _run(command: list[str]) -> None:
    completed = subprocess.run(command, cwd=PROJECT_ROOT, text=True)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
