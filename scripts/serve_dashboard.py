#!/usr/bin/env python
"""Serve the static dashboard and report files in a local browser."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_ROOT / "reports"


def main() -> int:
    parser = argparse.ArgumentParser(description="Uruchom lokalny podglad pulpitu HTML.")
    parser.add_argument("--host", default="127.0.0.1", help="Adres nasluchiwania.")
    parser.add_argument("--port", type=int, default=8000, help="Port HTTP.")
    parser.add_argument("--no-generate", action="store_true", help="Nie generuj panelu przed startem.")
    parser.add_argument("--no-open", action="store_true", help="Nie otwieraj przegladarki automatycznie.")
    args = parser.parse_args()

    if not args.no_generate:
        subprocess.run([sys.executable, str(PROJECT_ROOT / "scripts" / "make_dashboard.py")], check=True)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    handler = partial(SimpleHTTPRequestHandler, directory=str(REPORTS_DIR))
    server = ThreadingHTTPServer((args.host, args.port), handler)
    url = f"http://{args.host}:{args.port}/dashboard/"

    print(f"Pulpit monitoringu: {url}")
    print("Mapa punktow: " + f"http://{args.host}:{args.port}/maps/awp_points.html")
    print("Zatrzymanie: Ctrl+C")
    if not args.no_open:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
        print("Zatrzymano pulpit.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    os.chdir(PROJECT_ROOT)
    raise SystemExit(main())
