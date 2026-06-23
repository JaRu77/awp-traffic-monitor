#!/usr/bin/env python
"""Create a safe SQLite backup for server deployments."""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Utworz bezpieczna kopie bazy SQLite.")
    parser.add_argument("--settings", default="config/settings.yaml", help="Sciezka do settings.yaml.")
    parser.add_argument("--output-dir", default="backups", help="Katalog kopii.")
    parser.add_argument("--keep", type=int, default=14, help="Ile najnowszych kopii zostawic.")
    args = parser.parse_args()

    settings = _load_yaml(PROJECT_ROOT / args.settings)
    db_path = PROJECT_ROOT / settings.get("database", {}).get("path", "data/awp_traffic.sqlite")
    output_dir = PROJECT_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    if not db_path.exists():
        print(f"Brak bazy do backupu: {db_path}")
        return 0

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = output_dir / f"awp_traffic_{timestamp}.sqlite"
    with sqlite3.connect(db_path) as source:
        with sqlite3.connect(backup_path) as destination:
            source.backup(destination)

    _prune_old_backups(output_dir, args.keep)
    print(f"Backup SQLite: {backup_path}")
    return 0


def _prune_old_backups(output_dir: Path, keep: int) -> None:
    if keep <= 0:
        return
    backups = sorted(output_dir.glob("awp_traffic_*.sqlite"), reverse=True)
    for path in backups[keep:]:
        path.unlink(missing_ok=True)


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


if __name__ == "__main__":
    raise SystemExit(main())
