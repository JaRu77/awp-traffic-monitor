#!/usr/bin/env python
"""Send a daily AWP traffic report by email."""

from __future__ import annotations

import argparse
import mimetypes
import os
import smtplib
import subprocess
import sys
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def main() -> int:
    parser = argparse.ArgumentParser(description="Wyslij dobowy raport AWP mailem.")
    parser.add_argument("--date", default=None, help="Data raportu YYYY-MM-DD.")
    parser.add_argument("--days-back", type=int, default=1, help="Liczba dni wstecz, domyslnie wczoraj.")
    parser.add_argument("--settings", default="config/settings.yaml", help="Sciezka do settings.yaml.")
    parser.add_argument("--force", action="store_true", help="Wyslij nawet gdy email.enabled=false.")
    parser.add_argument("--no-generate", action="store_true", help="Nie generuj raportow przed wyslaniem.")
    args = parser.parse_args()

    os.chdir(PROJECT_ROOT)
    _load_dotenv_if_available(PROJECT_ROOT / ".env")
    settings = _load_yaml(PROJECT_ROOT / args.settings)
    email_settings = settings.get("email", {})
    enabled = _bool_env("EMAIL_ENABLED", bool(email_settings.get("enabled", False)))
    if not enabled and not args.force:
        print("Wysylka email jest wylaczona. Ustaw EMAIL_ENABLED=true w .env albo uzyj --force.")
        return 0

    timezone_name = settings.get("project", {}).get("timezone", "Europe/Warsaw")
    local_zone = ZoneInfo(timezone_name)
    date_iso = args.date or (datetime.now(local_zone).date() - timedelta(days=args.days_back)).isoformat()

    if not args.no_generate:
        _run([sys.executable, "scripts/make_daily_report.py", "--date", date_iso])
        _run([sys.executable, "scripts/export_csv.py", "--date", date_iso])

    attachments = _collect_attachments(settings, email_settings, date_iso)
    message = _build_message(settings, email_settings, date_iso, attachments)
    _send_message(message)
    print(f"Wyslano raport email dla daty {date_iso} do: {os.getenv('EMAIL_TO')}")
    return 0


def _collect_attachments(
    settings: dict,
    email_settings: dict,
    date_iso: str,
) -> list[Path]:
    report_settings = settings.get("report", {})
    output_dir = PROJECT_ROOT / report_settings.get("output_dir", "reports/daily")
    processed_dir = PROJECT_ROOT / "data" / "processed"
    candidates: list[tuple[bool, Path]] = [
        (bool(email_settings.get("attach_markdown", True)), output_dir / f"awp_daily_{date_iso}.md"),
        (bool(email_settings.get("attach_html", True)), output_dir / f"awp_daily_{date_iso}.html"),
        (bool(email_settings.get("attach_csv", True)), processed_dir / f"awp_traffic_{date_iso}.csv"),
    ]
    return [path for enabled, path in candidates if enabled and path.exists()]


def _build_message(
    settings: dict,
    email_settings: dict,
    date_iso: str,
    attachments: list[Path],
) -> EmailMessage:
    sender = _required_env("EMAIL_FROM")
    recipients = _split_recipients(_required_env("EMAIL_TO"))
    subject_prefix = str(email_settings.get("subject_prefix", "[AWP traffic]"))
    project_name = settings.get("project", {}).get("name", "AWP traffic monitor")

    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message["Subject"] = f"{subject_prefix} raport dobowy {date_iso}"
    message.set_content(
        "\n".join(
            [
                f"Raport dobowy: {date_iso}",
                "",
                str(project_name),
                "",
                "W zalacznikach sa pliki raportu i eksport CSV, jesli byly dostepne.",
                "Ta wiadomosc zostala wyslana automatycznie z serwera VPS.",
                "",
            ]
        )
    )

    for path in attachments:
        content_type, _ = mimetypes.guess_type(path.name)
        if content_type:
            maintype, subtype = content_type.split("/", 1)
        else:
            maintype, subtype = "application", "octet-stream"
        message.add_attachment(
            path.read_bytes(),
            maintype=maintype,
            subtype=subtype,
            filename=path.name,
        )
    return message


def _send_message(message: EmailMessage) -> None:
    host = _required_env("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    use_ssl = _bool_env("SMTP_USE_SSL", False)
    use_tls = _bool_env("SMTP_USE_TLS", not use_ssl)

    if use_ssl:
        server: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=30)
    else:
        server = smtplib.SMTP(host, port, timeout=30)

    with server:
        server.ehlo()
        if use_tls and not use_ssl:
            server.starttls()
            server.ehlo()
        if username:
            server.login(username, password or "")
        server.send_message(message)


def _run(command: list[str]) -> None:
    print("Uruchamiam: " + " ".join(command))
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Brak wymaganej zmiennej w .env: {name}")
    return value


def _split_recipients(value: str) -> list[str]:
    return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "tak", "on"}


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _load_dotenv_if_available(path: Path) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(path)


if __name__ == "__main__":
    raise SystemExit(main())
