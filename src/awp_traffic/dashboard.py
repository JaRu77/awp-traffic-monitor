"""Static HTML dashboard for the AWP traffic monitor."""

from __future__ import annotations

import json
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from awp_traffic.metrics import interpret_conditions


def generate_dashboard(
    *,
    date_iso: str,
    settings: dict[str, Any],
    points: list[dict[str, Any]],
    measurements: list[dict[str, Any]],
    fetch_runs: list[dict[str, Any]],
    latest_run: dict[str, Any] | None,
    request_total: int,
    output_dir: str | Path,
    routes: list[dict[str, Any]] | None = None,
    route_measurements: list[dict[str, Any]] | None = None,
) -> tuple[Path, Path]:
    """Generate dashboard HTML and a compact JSON status file."""

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    routes = routes or []
    route_measurements = route_measurements or []

    dashboard_settings = settings.get("dashboard", {})
    monitoring_settings = settings.get("monitoring", {})
    project_settings = settings.get("project", {})
    routing_settings = settings.get("routing", {})
    timezone_name = project_settings.get("timezone", "Europe/Warsaw")
    local_zone = ZoneInfo(timezone_name)
    title = dashboard_settings.get("title", "Pulpit monitoringu AWP")
    refresh_seconds = int(dashboard_settings.get("refresh_seconds", 300))
    request_limit_reference = int(dashboard_settings.get("request_limit_reference", 2500))
    soft_limit = monitoring_settings.get("daily_request_soft_limit")
    soft_limit = int(soft_limit) if soft_limit is not None else None
    interval_minutes = int(project_settings.get("measurement_interval_minutes", 15))
    routes_interval_minutes = int(routing_settings.get("measurement_interval_minutes", 60))
    expected_daily_requests = _expected_daily_requests(
        points_count=len(points),
        point_interval_minutes=interval_minutes,
        routes_count=len(routes),
        route_interval_minutes=routes_interval_minutes,
        routes_enabled=bool(routing_settings.get("enabled", False)),
    )
    now_local = datetime.now(local_zone)
    slot_count = _completed_slot_count(measurements, interval_minutes)
    expected_slots_so_far = _expected_slots_so_far(date_iso, now_local, interval_minutes)
    missing_slots_so_far = max(0, expected_slots_so_far - slot_count)
    latest_measurements = _latest_measurements_by_point(measurements)
    latest_route_measurements = _latest_measurements_by_route(route_measurements)
    latest_timestamp = _latest_timestamp(measurements)
    latest_route_timestamp = _latest_route_timestamp(route_measurements)
    latest_slot = _latest_slot(measurements, latest_run)
    stale_minutes = _stale_minutes(latest_timestamp, now_local)
    errors_today = sum(int(run.get("failures") or 0) for run in fetch_runs)
    successful_requests_today = sum(int(run.get("successes") or 0) for run in fetch_runs)
    worst_point = _worst_latest_point(latest_measurements)
    generated_at = now_local.strftime("%Y-%m-%d %H:%M:%S")

    status = {
        "date": date_iso,
        "generated_at": generated_at,
        "monitoring_enabled": bool(monitoring_settings.get("enabled", True)),
        "points": len(points),
        "routes": len(routes),
        "interval_minutes": interval_minutes,
        "route_interval_minutes": routes_interval_minutes,
        "expected_daily_requests": expected_daily_requests,
        "request_total": request_total,
        "request_limit_reference": request_limit_reference,
        "soft_limit": soft_limit,
        "successful_requests_today": successful_requests_today,
        "errors_today": errors_today,
        "completed_slots_today": slot_count,
        "expected_slots_so_far": expected_slots_so_far,
        "missing_slots_so_far": missing_slots_so_far,
        "stale_minutes": stale_minutes,
        "latest_measurement": latest_timestamp,
        "latest_route_measurement": latest_route_timestamp,
        "latest_scheduled_slot": latest_slot,
        "latest_run_status": latest_run.get("status") if latest_run else None,
        "worst_point": worst_point,
    }

    html = _build_html(
        title=title,
        refresh_seconds=refresh_seconds,
        settings=settings,
        points=points,
        routes=routes,
        date_iso=date_iso,
        generated_at=generated_at,
        latest_measurements=latest_measurements,
        latest_route_measurements=latest_route_measurements,
        latest_run=latest_run,
        fetch_runs=fetch_runs,
        request_total=request_total,
        request_limit_reference=request_limit_reference,
        soft_limit=soft_limit,
        interval_minutes=interval_minutes,
        expected_daily_requests=expected_daily_requests,
        slot_count=slot_count,
        expected_slots_so_far=expected_slots_so_far,
        missing_slots_so_far=missing_slots_so_far,
        stale_minutes=stale_minutes,
        successful_requests_today=successful_requests_today,
        errors_today=errors_today,
        latest_timestamp=latest_timestamp,
        latest_slot=latest_slot,
        worst_point=worst_point,
    )

    html_path = output_dir / "index.html"
    json_path = output_dir / "status.json"
    html_path.write_text(html, encoding="utf-8")
    json_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    return html_path, json_path


def _build_html(
    *,
    title: str,
    refresh_seconds: int,
    settings: dict[str, Any],
    points: list[dict[str, Any]],
    routes: list[dict[str, Any]],
    date_iso: str,
    generated_at: str,
    latest_measurements: list[dict[str, Any]],
    latest_route_measurements: list[dict[str, Any]],
    latest_run: dict[str, Any] | None,
    fetch_runs: list[dict[str, Any]],
    request_total: int,
    request_limit_reference: int,
    soft_limit: int | None,
    interval_minutes: int,
    expected_daily_requests: int,
    slot_count: int,
    expected_slots_so_far: int,
    missing_slots_so_far: int,
    stale_minutes: int | None,
    successful_requests_today: int,
    errors_today: int,
    latest_timestamp: str | None,
    latest_slot: str | None,
    worst_point: dict[str, Any] | None,
) -> str:
    monitoring_settings = settings.get("monitoring", {})
    monitoring_enabled = bool(monitoring_settings.get("enabled", True))
    soft_limit_label = str(soft_limit) if soft_limit is not None else "brak"
    reference_pct = _percent(request_total, request_limit_reference)
    soft_pct = _percent(request_total, soft_limit) if soft_limit else None
    latest_status = latest_run.get("status") if latest_run else "brak"
    status_class = "ok" if latest_status in {"success", "partial"} and monitoring_enabled else "warn"
    if latest_status in {"failed", "skipped_limit", "skipped_disabled"} or not monitoring_enabled:
        status_class = "bad" if latest_status == "failed" else "warn"

    cards = [
        _card("Monitoring", "wlaczony" if monitoring_enabled else "wylaczony", "ok" if monitoring_enabled else "warn"),
        _card("Ostatni cykl", latest_status, status_class),
        _card("Requesty dzis", f"{request_total} / {request_limit_reference}", _usage_class(reference_pct)),
        _card("Limit miekki", soft_limit_label, _usage_class(soft_pct)),
        _card("Punkty", str(len(points)), "ok"),
        _card("Trasy", str(len(routes)), "ok" if routes else "warn"),
        _card("Bledy dzis", str(errors_today), "ok" if errors_today == 0 else "warn"),
        _card("Sloty dzis", f"{slot_count} / {expected_slots_so_far}", "ok" if missing_slots_so_far == 0 else "warn"),
        _card("Braki slotow", str(missing_slots_so_far), "ok" if missing_slots_so_far == 0 else "bad"),
        _card("Wiek danych", _age_label(stale_minutes), _stale_class(stale_minutes, interval_minutes)),
        _card("Slot pomiaru", _short_datetime(latest_slot), "ok" if latest_slot else "warn"),
        _card("Pobrano faktycznie", _short_datetime(latest_timestamp), "ok" if latest_timestamp else "warn"),
        _card("Plan dzienny", str(expected_daily_requests), _usage_class(_percent(expected_daily_requests, request_limit_reference))),
    ]

    worst_html = "Brak danych z dzisiaj."
    if worst_point:
        worst_html = (
            f"{escape(str(worst_point.get('point_name', 'brak')))}: "
            f"indeks {_fmt(worst_point.get('congestion_index'))}, "
            f"opoznienie {_fmt(worst_point.get('delay_ratio'))}."
        )

    return f"""<!doctype html>
<html lang="pl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="{refresh_seconds}">
  <title>{escape(title)}</title>
  <style>
    :root {{
      --bg: #f5f7fb;
      --panel: #ffffff;
      --ink: #172033;
      --muted: #5d667a;
      --line: #d8deea;
      --ok: #117a4d;
      --warn: #a15c00;
      --bad: #b42318;
      --accent: #1f5eff;
    }}
    body {{ margin: 0; background: var(--bg); color: var(--ink); font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }}
    header {{ padding: 24px 28px 10px; }}
    main {{ padding: 0 28px 32px; }}
    h1 {{ margin: 0 0 6px; font-size: 28px; letter-spacing: 0; }}
    h2 {{ margin: 0 0 14px; font-size: 18px; letter-spacing: 0; }}
    .muted {{ color: var(--muted); }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(185px, 1fr)); gap: 12px; }}
    .card, section {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; }}
    .card {{ padding: 14px 16px; }}
    .label {{ color: var(--muted); font-size: 13px; }}
    .value {{ margin-top: 6px; font-size: 22px; font-weight: 700; overflow-wrap: anywhere; }}
    .ok {{ color: var(--ok); }}
    .warn {{ color: var(--warn); }}
    .bad {{ color: var(--bad); }}
    section {{ margin-top: 16px; padding: 18px; overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ padding: 9px 10px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-weight: 700; white-space: nowrap; }}
    tr:hover td {{ background: #f9fbff; }}
    .bar {{ width: 100%; height: 10px; border-radius: 999px; overflow: hidden; background: #e7ebf3; margin-top: 10px; }}
    .fill {{ height: 100%; background: var(--accent); width: {min(reference_pct, 100):.1f}%; }}
    .note {{ line-height: 1.5; max-width: 1100px; }}
    .links a {{ display: inline-block; margin-right: 16px; color: var(--accent); text-decoration: none; font-weight: 700; }}
    @media (max-width: 700px) {{
      header, main {{ padding-left: 14px; padding-right: 14px; }}
      h1 {{ font-size: 22px; }}
      .value {{ font-size: 18px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>{escape(title)}</h1>
    <div class="muted">Data lokalna: {escape(date_iso)} &middot; wygenerowano: {escape(generated_at)} &middot; auto-odswiezanie: {refresh_seconds}s</div>
  </header>
  <main>
    <div class="grid">
      {''.join(cards)}
    </div>

    <section>
      <h2>Zuzycie API</h2>
      <div class="note">
        Dzis zapisano {request_total} prob zapytan do TomTom. Plan dla obecnej konfiguracji to
        {expected_daily_requests} requestow na dobe. Limit referencyjny Freemium: {request_limit_reference};
        limit miekki projektu: {soft_limit_label}.
        Wykonane sloty pomiarowe dzisiaj: {slot_count}; oczekiwane do tej chwili: {expected_slots_so_far};
        braki: {missing_slots_so_far}.
      </div>
      <div class="bar"><div class="fill"></div></div>
    </section>

    <section>
      <h2>Najgorszy punkt w ostatnich danych</h2>
      <div class="note">{worst_html}</div>
    </section>

    <section>
      <h2>Estymowane czasy przejazdu odcinkow</h2>
      <p class="muted">Wyniki pochodne z predkosci Flow w punktach korytarzowych; bez dodatkowych zapytan do API.</p>
      {_routes_table(routes, latest_route_measurements)}
    </section>

    <section>
      <h2>Ostatnie pomiary wg punktow</h2>
      {_latest_table(points, latest_measurements)}
    </section>

    <section>
      <h2>Ostatnie cykle pobierania</h2>
      {_runs_table(fetch_runs)}
    </section>

    <section>
      <h2>Linki operacyjne</h2>
      <div class="links">
        <a href="../daily/">Raporty dobowe</a>
        <a href="../maps/awp_points.html">Mapa punktow</a>
        <a href="status.json">Status JSON</a>
      </div>
      <p class="muted">Sterowanie harmonogramem odbywa sie w GitHub Actions. Zatrzymanie awaryjne: ustaw monitoring.enabled: false w config/settings.yaml.</p>
    </section>
  </main>
</body>
</html>
"""


def _card(label: str, value: str, css_class: str) -> str:
    return (
        '<div class="card">'
        f'<div class="label">{escape(label)}</div>'
        f'<div class="value {css_class}">{escape(value)}</div>'
        "</div>"
    )


def _latest_table(points: list[dict[str, Any]], latest_measurements: list[dict[str, Any]]) -> str:
    by_point = {row.get("point_id"): row for row in latest_measurements}
    rows = []
    for point in sorted(points, key=lambda item: item.get("corridor_order") or 0):
        row = by_point.get(point.get("id"))
        if row:
            interpretation = interpret_conditions(
                _to_float(row.get("congestion_index")),
                _to_float(row.get("delay_ratio")),
                confidence=_to_float(row.get("confidence")),
                road_closure=bool(row.get("road_closure")),
            )
            rows.append(
                "<tr>"
                f"<td>{escape(str(point.get('corridor_order', '')))}</td>"
                f"<td>{escape(str(point.get('name', '')))}</td>"
                f"<td>{escape(str(point.get('direction', '')))}</td>"
                f"<td>{_fmt(row.get('current_speed'))}</td>"
                f"<td>{_fmt(row.get('free_flow_speed'))}</td>"
                f"<td>{_fmt(row.get('congestion_index'))}</td>"
                f"<td>{_fmt(row.get('delay_ratio'))}</td>"
                f"<td>{_fmt(row.get('confidence'))}</td>"
                f"<td>{escape(interpretation)}</td>"
                f"<td>{escape(_short_datetime(row.get('measurement_slot_local') or row.get('timestamp_local')))}</td>"
                f"<td>{escape(_short_datetime(row.get('timestamp_local')))}</td>"
                "</tr>"
            )
        else:
            rows.append(
                "<tr>"
                f"<td>{escape(str(point.get('corridor_order', '')))}</td>"
                f"<td>{escape(str(point.get('name', '')))}</td>"
                f"<td>{escape(str(point.get('direction', '')))}</td>"
                '<td colspan="8" class="muted">Brak pomiaru dzisiaj</td>'
                "</tr>"
            )

    return (
        "<table><thead><tr>"
        "<th>#</th><th>Punkt</th><th>Kierunek</th><th>V teraz</th><th>V swob.</th>"
        "<th>Indeks</th><th>Opozn.</th><th>Conf.</th><th>Interpretacja</th><th>Slot</th><th>Pobrano</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _routes_table(routes: list[dict[str, Any]], latest_route_measurements: list[dict[str, Any]]) -> str:
    if not routes:
        return '<p class="muted">Brak skonfigurowanych tras odcinkowych.</p>'

    by_route = {row.get("route_id"): row for row in latest_route_measurements}
    rows = []
    for route in sorted(routes, key=lambda item: item.get("corridor_order") or 0):
        row = by_route.get(route.get("id"))
        if row:
            interpretation = interpret_conditions(
                _to_float(row.get("congestion_index")),
                _to_float(row.get("delay_ratio")),
                confidence=_to_float(row.get("confidence")),
            )
            rows.append(
                "<tr>"
                f"<td>{escape(str(route.get('corridor_order', '')))}</td>"
                f"<td>{escape(str(route.get('name', '')))}</td>"
                f"<td>{escape(str(route.get('direction', '')))}</td>"
                f"<td>{_fmt(row.get('travel_time_seconds'))}</td>"
                f"<td>{_fmt(row.get('no_traffic_travel_time_seconds'))}</td>"
                f"<td>{_fmt(row.get('delay_seconds'))}</td>"
                f"<td>{_fmt(row.get('delay_ratio'))}</td>"
                f"<td>{_fmt(row.get('average_speed_kmh'))}</td>"
                f"<td>{escape(interpretation)}</td>"
                f"<td>{escape(_route_source_label(row))}</td>"
                f"<td>{escape(_short_datetime(row.get('measurement_slot_local') or row.get('timestamp_local')))}</td>"
                f"<td>{escape(_short_datetime(row.get('timestamp_local')))}</td>"
                "</tr>"
            )
        else:
            rows.append(
                "<tr>"
                f"<td>{escape(str(route.get('corridor_order', '')))}</td>"
                f"<td>{escape(str(route.get('name', '')))}</td>"
                f"<td>{escape(str(route.get('direction', '')))}</td>"
                '<td colspan="9" class="muted">Brak estymacji trasy dzisiaj</td>'
                "</tr>"
            )

    return (
        "<table><thead><tr>"
        "<th>#</th><th>Trasa</th><th>Kierunek</th><th>Czas teraz s</th><th>Czas bez ruchu s</th>"
        "<th>Opozn. s</th><th>Opozn. ratio</th><th>V srednia km/h</th><th>Interpretacja</th>"
        "<th>Zrodlo</th><th>Slot</th><th>Pobrano</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _runs_table(fetch_runs: list[dict[str, Any]]) -> str:
    if not fetch_runs:
        return '<p class="muted">Brak zapisanych cykli pobierania dla tej daty.</p>'

    rows = []
    for run in fetch_runs[:16]:
        rows.append(
            "<tr>"
            f"<td>{escape(_short_datetime(run.get('scheduled_slot_local')))}</td>"
            f"<td>{escape(_short_datetime(run.get('started_at_local')))}</td>"
            f"<td>{escape(str(run.get('status', '')))}</td>"
            f"<td>{escape(str(run.get('requests_attempted', 0)))}</td>"
            f"<td>{escape(str(run.get('successes', 0)))}</td>"
            f"<td>{escape(str(run.get('failures', 0)))}</td>"
            f"<td>{escape(str(run.get('message') or ''))}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr>"
        "<th>Slot planowany</th><th>Start faktyczny</th><th>Status</th><th>Requesty</th><th>Sukcesy</th><th>Bledy</th><th>Komunikat</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _latest_measurements_by_point(measurements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in measurements:
        point_id = row.get("point_id")
        current_ts = str(row.get("measurement_slot_local") or row.get("timestamp_local") or "")
        previous = latest.get(point_id, {})
        previous_ts = str(previous.get("measurement_slot_local") or previous.get("timestamp_local") or "")
        if point_id and current_ts >= previous_ts:
            latest[point_id] = row
    return list(latest.values())


def _latest_measurements_by_route(route_measurements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in route_measurements:
        route_id = row.get("route_id")
        current_ts = str(row.get("measurement_slot_local") or row.get("timestamp_local") or "")
        previous = latest.get(route_id, {})
        previous_ts = str(previous.get("measurement_slot_local") or previous.get("timestamp_local") or "")
        if route_id and current_ts >= previous_ts:
            latest[route_id] = row
    return list(latest.values())


def _latest_timestamp(measurements: list[dict[str, Any]]) -> str | None:
    timestamps = [str(row.get("timestamp_local")) for row in measurements if row.get("timestamp_local")]
    return max(timestamps) if timestamps else None


def _latest_route_timestamp(route_measurements: list[dict[str, Any]]) -> str | None:
    timestamps = [str(row.get("timestamp_local")) for row in route_measurements if row.get("timestamp_local")]
    return max(timestamps) if timestamps else None


def _route_source_label(row: dict[str, Any]) -> str:
    label = str(row.get("source_label") or "TomTom Routing API")
    used = row.get("points_used")
    expected = row.get("points_expected")
    if used is not None and expected is not None:
        return f"{label} ({used}/{expected} pkt)"
    return label


def _expected_daily_requests(
    *,
    points_count: int,
    point_interval_minutes: int,
    routes_count: int,
    route_interval_minutes: int,
    routes_enabled: bool,
) -> int:
    point_runs = (
        (24 * 60) // point_interval_minutes
        if point_interval_minutes > 0
        else 0
    )
    route_runs = (
        (24 * 60) // route_interval_minutes
        if routes_enabled and route_interval_minutes > 0
        else 0
    )
    return points_count * point_runs + routes_count * route_runs


def _completed_slot_count(measurements: list[dict[str, Any]], interval_minutes: int) -> int:
    slots = set()
    for row in measurements:
        slot = row.get("measurement_slot_local")
        if not slot:
            slot = _floor_timestamp_text(row.get("timestamp_local"), interval_minutes)
        if slot:
            slots.add(str(slot)[:16])
    return len(slots)


def _expected_slots_so_far(date_iso: str, now_local: datetime, interval_minutes: int) -> int:
    if interval_minutes <= 0:
        return 0
    try:
        report_date = datetime.strptime(date_iso, "%Y-%m-%d").date()
    except ValueError:
        return 0
    if report_date < now_local.date():
        return int((24 * 60) / interval_minutes)
    if report_date > now_local.date():
        return 0
    minutes = now_local.hour * 60 + now_local.minute
    return (minutes // interval_minutes) + 1


def _stale_minutes(latest_timestamp: str | None, now_local: datetime) -> int | None:
    if not latest_timestamp:
        return None
    try:
        latest = datetime.fromisoformat(latest_timestamp)
    except ValueError:
        return None
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=now_local.tzinfo)
    delta = now_local - latest.astimezone(now_local.tzinfo)
    return max(0, int(delta.total_seconds() // 60))


def _floor_timestamp_text(value: Any, interval_minutes: int) -> str | None:
    if not value:
        return None
    try:
        timestamp = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if interval_minutes <= 0:
        floored = timestamp.replace(second=0, microsecond=0)
    else:
        total_minutes = timestamp.hour * 60 + timestamp.minute
        floored_minutes = (total_minutes // interval_minutes) * interval_minutes
        floored = timestamp.replace(
            hour=floored_minutes // 60,
            minute=floored_minutes % 60,
            second=0,
            microsecond=0,
        )
    return floored.isoformat()


def _latest_slot(
    measurements: list[dict[str, Any]],
    latest_run: dict[str, Any] | None,
) -> str | None:
    slots = [
        str(row.get("measurement_slot_local"))
        for row in measurements
        if row.get("measurement_slot_local")
    ]
    if slots:
        return max(slots)
    if latest_run and latest_run.get("scheduled_slot_local"):
        return str(latest_run["scheduled_slot_local"])
    return _latest_timestamp(measurements)


def _worst_latest_point(latest_measurements: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [
        row
        for row in latest_measurements
        if _to_float(row.get("congestion_index")) is not None
        and _to_float(row.get("delay_ratio")) is not None
    ]
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda row: (
            _to_float(row.get("congestion_index")) or 999,
            -(_to_float(row.get("delay_ratio")) or 0),
        ),
    )[0]


def _usage_class(value: float | None) -> str:
    if value is None:
        return "ok"
    if value >= 95:
        return "bad"
    if value >= 80:
        return "warn"
    return "ok"


def _stale_class(stale_minutes: int | None, interval_minutes: int) -> str:
    if stale_minutes is None:
        return "bad"
    if stale_minutes > interval_minutes * 2:
        return "bad"
    if stale_minutes > interval_minutes:
        return "warn"
    return "ok"


def _age_label(stale_minutes: int | None) -> str:
    if stale_minutes is None:
        return "brak"
    return f"{stale_minutes} min"


def _percent(value: int | float | None, total: int | float | None) -> float:
    if value is None or not total:
        return 0.0
    return max(0.0, float(value) / float(total) * 100.0)


def _fmt(value: Any) -> str:
    number = _to_float(value)
    if number is None:
        return "brak"
    return f"{number:.2f}"


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _short_datetime(value: Any) -> str:
    if not value:
        return "brak"
    text = str(value)
    if "T" in text:
        date_part, time_part = text.split("T", 1)
        return f"{date_part} {time_part[:5]}"
    return text[:16]
