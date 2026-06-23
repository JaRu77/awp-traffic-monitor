#!/usr/bin/env python
"""Small local control panel for the AWP traffic monitor."""

from __future__ import annotations

import argparse
import html
import json
import mimetypes
import os
import subprocess
import sys
import webbrowser
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_ROOT / "reports"
STATUS_PATH = REPORTS_DIR / "dashboard" / "status.json"
GITHUB_ACTIONS_URL = "https://github.com/JaRu77/awp-traffic-monitor/actions"


class ControlPanelServer(ThreadingHTTPServer):
    last_action: dict[str, str] | None = None


class ControlPanelHandler(BaseHTTPRequestHandler):
    server_version = "AWPControlPanel/1.0"

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._send_html(_render_home(self.server.last_action))
            return
        if path == "/github-actions":
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", GITHUB_ACTIONS_URL)
            self.end_headers()
            return
        if path.startswith("/dashboard/"):
            relative = path.removeprefix("/dashboard/") or "index.html"
            self._send_file(REPORTS_DIR / "dashboard", relative)
            return
        if path.startswith("/maps/"):
            relative = path.removeprefix("/maps/")
            self._send_file(REPORTS_DIR / "maps", relative)
            return
        if path.startswith("/daily/"):
            relative = path.removeprefix("/daily/")
            self._send_file(REPORTS_DIR / "daily", relative)
            return
        if path.startswith("/figures/"):
            relative = path.removeprefix("/figures/")
            self._send_file(REPORTS_DIR / "figures", relative)
            return
        if path.startswith("/processed/"):
            relative = path.removeprefix("/processed/")
            self._send_file(PROJECT_ROOT / "data" / "processed", relative)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Nie znaleziono strony.")

    def do_POST(self) -> None:
        actions = {
            "/action/refresh": ["scripts/sync_from_github.py"],
            "/action/make-dashboard": ["scripts/make_dashboard.py"],
            "/action/make-report": ["scripts/make_daily_report.py"],
            "/action/export-csv": ["scripts/export_csv.py"],
        }
        command = actions.get(self.path)
        if command is None:
            self.send_error(HTTPStatus.NOT_FOUND, "Nieznana akcja.")
            return

        self.server.last_action = _run_python(command)
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", "/")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {format % args}")

    def _send_html(self, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_file(self, base_dir: Path, relative_path: str) -> None:
        try:
            relative = Path(unquote(relative_path))
            target = (base_dir / relative).resolve()
            base = base_dir.resolve()
            if base not in target.parents and target != base:
                raise ValueError("Path traversal")
            if target.is_dir():
                target = target / "index.html"
            payload = target.read_bytes()
        except (OSError, ValueError):
            self.send_error(HTTPStatus.NOT_FOUND, "Nie znaleziono pliku.")
            return

        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if target.suffix.lower() in {".html", ".json", ".csv", ".md", ".txt"}:
            content_type += "; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Uruchom lokalna appke kontrolna AWP.")
    parser.add_argument("--host", default="127.0.0.1", help="Adres nasluchiwania.")
    parser.add_argument("--port", type=int, default=8010, help="Port HTTP.")
    parser.add_argument("--no-open", action="store_true", help="Nie otwieraj przegladarki.")
    args = parser.parse_args()

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    server = ControlPanelServer((args.host, args.port), ControlPanelHandler)
    url = f"http://{args.host}:{args.port}/"

    print(f"Appka kontrolna AWP: {url}")
    print("Zatrzymanie: Ctrl+C")
    if not args.no_open:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
        print("Zatrzymano appke kontrolna.")
    finally:
        server.server_close()
    return 0


def _run_python(args: list[str]) -> dict[str, str]:
    command = [sys.executable, *args]
    started = datetime.now()
    try:
        result = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=180,
        )
        output = result.stdout.strip() or "Brak komunikatow."
        status = "ok" if result.returncode == 0 else "blad"
        return {
            "status": status,
            "title": " ".join(args),
            "time": started.strftime("%Y-%m-%d %H:%M:%S"),
            "output": output[-5000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "blad",
            "title": " ".join(args),
            "time": started.strftime("%Y-%m-%d %H:%M:%S"),
            "output": f"Przekroczono limit czasu. {exc}",
        }


def _render_home(last_action: dict[str, str] | None) -> str:
    status = _read_status()
    latest_daily = _latest_file(REPORTS_DIR / "daily", "*.html")
    latest_csv = _latest_file(PROJECT_ROOT / "data" / "processed", "*.csv")
    latest_action_html = _render_last_action(last_action)

    return f"""<!doctype html>
<html lang="pl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Kontrola badania AWP</title>
  <style>
    :root {{
      --bg: #f4f6f9;
      --panel: #ffffff;
      --ink: #172033;
      --muted: #637083;
      --line: #d8deea;
      --accent: #075db3;
      --ok: #127a4d;
      --bad: #b42318;
      --warn: #9a5a00;
    }}
    body {{ margin: 0; background: var(--bg); color: var(--ink); font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }}
    header {{ padding: 24px 30px 12px; }}
    main {{ padding: 0 30px 32px; max-width: 1180px; }}
    h1 {{ margin: 0 0 4px; font-size: 30px; }}
    h2 {{ margin: 0 0 14px; font-size: 18px; }}
    .muted {{ color: var(--muted); }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin-bottom: 16px; }}
    .card, section {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; }}
    .card {{ padding: 14px 16px; }}
    .label {{ color: var(--muted); font-size: 13px; }}
    .value {{ margin-top: 6px; font-size: 22px; font-weight: 750; overflow-wrap: anywhere; }}
    section {{ margin-top: 16px; padding: 18px; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 10px; }}
    button, a.button {{ border: 1px solid var(--accent); background: var(--accent); color: white; border-radius: 6px; padding: 10px 14px; font-weight: 700; cursor: pointer; text-decoration: none; display: inline-block; }}
    a.button.secondary, button.secondary {{ background: white; color: var(--accent); }}
    form {{ display: inline; }}
    pre {{ white-space: pre-wrap; background: #101828; color: #e5e7eb; padding: 14px; border-radius: 8px; overflow-x: auto; }}
    .ok {{ color: var(--ok); }}
    .bad {{ color: var(--bad); }}
    .warn {{ color: var(--warn); }}
    @media (max-width: 700px) {{
      header, main {{ padding-left: 14px; padding-right: 14px; }}
      h1 {{ font-size: 23px; }}
      .value {{ font-size: 18px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Kontrola badania AWP</h1>
    <div class="muted">Lokalna appka do podgladu i odswiezania wynikow z GitHuba.</div>
  </header>
  <main>
    <div class="grid">
      {_card("Status cyklu", status.get("latest_run_status", "brak"), _status_class(status.get("latest_run_status")))}
      {_card("Requesty dzis", f"{status.get('request_total', 'brak')} / {status.get('request_limit_reference', 2500)}", "ok")}
      {_card("Punkty", status.get("points", "brak"), "ok")}
      {_card("Bledy dzis", status.get("errors_today", "brak"), "ok" if status.get("errors_today", 0) == 0 else "warn")}
      {_card("Slot pomiaru", _short_time(status.get("latest_scheduled_slot") or status.get("latest_measurement")), "ok")}
      {_card("Pobrano", _short_time(status.get("latest_measurement")), "ok")}
    </div>

    <section>
      <h2>Akcje</h2>
      <div class="actions">
        <form method="post" action="/action/refresh"><button type="submit">Odswiez z GitHuba</button></form>
        <a class="button secondary" href="/dashboard/">Pulpit HTML</a>
        <a class="button secondary" href="/maps/awp_points.html">Mapa punktow</a>
        <a class="button secondary" href="/dashboard/status.json">Status JSON</a>
        <a class="button secondary" href="/github-actions">GitHub Actions</a>
      </div>
    </section>

    <section>
      <h2>Raporty i eksport</h2>
      <div class="actions">
        <form method="post" action="/action/make-report"><button type="submit">Generuj raport dzienny</button></form>
        <form method="post" action="/action/export-csv"><button type="submit" class="secondary">Eksportuj CSV</button></form>
        {_optional_link("Ostatni raport HTML", latest_daily, REPORTS_DIR / "daily", "/daily/")}
        {_optional_link("Ostatni CSV", latest_csv, PROJECT_ROOT / "data" / "processed", "/processed/")}
      </div>
    </section>

    {latest_action_html}

    <section>
      <h2>Jak tego uzywac</h2>
      <p>Przycisk <strong>Odswiez z GitHuba</strong> pobiera ostatnie dane juz zapisane przez workflow. Nie zuzywa limitu TomTom API.</p>
      <p>Nowy pomiar teraz wykonujesz w GitHub Actions przez <strong>Run workflow</strong>. To zuzywa 24 requesty, po jednym na punkt.</p>
    </section>
  </main>
</body>
</html>
"""


def _read_status() -> dict[str, object]:
    try:
        return json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _card(label: str, value: object, css_class: str) -> str:
    return (
        '<div class="card">'
        f'<div class="label">{html.escape(str(label))}</div>'
        f'<div class="value {css_class}">{html.escape(str(value))}</div>'
        "</div>"
    )


def _render_last_action(last_action: dict[str, str] | None) -> str:
    if not last_action:
        return ""
    css_class = "ok" if last_action.get("status") == "ok" else "bad"
    return (
        "<section>"
        "<h2>Ostatnia akcja</h2>"
        f'<p class="{css_class}">{html.escape(last_action.get("title", ""))} - {html.escape(last_action.get("status", ""))} - {html.escape(last_action.get("time", ""))}</p>'
        f"<pre>{html.escape(last_action.get('output', ''))}</pre>"
        "</section>"
    )


def _optional_link(label: str, path: Path | None, base: Path, prefix: str) -> str:
    if path is None:
        return ""
    relative = path.relative_to(base).as_posix()
    return f'<a class="button secondary" href="{prefix}{html.escape(relative)}">{html.escape(label)}</a>'


def _latest_file(directory: Path, pattern: str) -> Path | None:
    if not directory.exists():
        return None
    files = [path for path in directory.glob(pattern) if path.is_file()]
    if not files:
        return None
    return max(files, key=lambda path: path.stat().st_mtime)


def _status_class(value: object) -> str:
    if value in {"success", "partial"}:
        return "ok"
    if value in {"failed"}:
        return "bad"
    return "warn"


def _short_time(value: object) -> str:
    if not value:
        return "brak"
    text = str(value)
    if "T" in text:
        date_part, time_part = text.split("T", 1)
        return f"{date_part} {time_part[:5]}"
    return text[:16]


if __name__ == "__main__":
    os.chdir(PROJECT_ROOT)
    raise SystemExit(main())
