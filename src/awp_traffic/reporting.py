"""Markdown and HTML daily reporting for collected traffic measurements."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from awp_traffic.metrics import DEFAULT_THRESHOLDS, calculate_metrics


METRIC_LABELS = {
    "current_speed": "Predkosc biezaca [km/h]",
    "congestion_index": "Indeks plynnosci ruchu",
    "delay_ratio": "Wskaznik opoznienia",
}


def generate_daily_report(
    *,
    date_iso: str,
    measurements: list[dict[str, Any]],
    route_measurements: list[dict[str, Any]] | None = None,
    settings: dict[str, Any],
    output_dir: str | Path,
    figures_dir: str | Path,
) -> tuple[Path, Path]:
    """Generate Markdown and HTML reports for one local calendar day."""

    output_dir = Path(output_dir)
    figures_dir = Path(figures_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    if not measurements:
        markdown = _empty_report(date_iso, settings)
        markdown_path = output_dir / f"awp_daily_{date_iso}.md"
        html_path = output_dir / f"awp_daily_{date_iso}.html"
        markdown_path.write_text(markdown, encoding="utf-8")
        html_path.write_text(_markdown_to_html(markdown, settings), encoding="utf-8")
        return markdown_path, html_path

    frame = pd.DataFrame(measurements)
    time_column = _analysis_time_column(frame)
    frame["timestamp_local_dt"] = pd.to_datetime(frame["timestamp_local"], errors="coerce")
    frame["analysis_time_dt"] = pd.to_datetime(frame[time_column], errors="coerce")
    frame["hour"] = frame["analysis_time_dt"].dt.floor("h")

    for column in [
        "current_speed",
        "free_flow_speed",
        "current_travel_time",
        "free_flow_travel_time",
        "confidence",
        "congestion_index",
        "delay_ratio",
        "delay_seconds",
    ]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    figure_paths = _create_hourly_figures(frame, date_iso, figures_dir)
    point_summary = _point_summary(frame)
    route_summary = _route_summary(route_measurements or [])
    worst_hour = _worst_hour(frame)
    worst_point = _worst_point(frame)
    comment = _automatic_comment(frame, worst_hour, worst_point, settings)

    markdown = _build_markdown_report(
        date_iso=date_iso,
        settings=settings,
        frame=frame,
        point_summary=point_summary,
        route_summary=route_summary,
        worst_hour=worst_hour,
        worst_point=worst_point,
        comment=comment,
        figure_paths=figure_paths,
        output_dir=output_dir,
    )

    markdown_path = output_dir / f"awp_daily_{date_iso}.md"
    html_path = output_dir / f"awp_daily_{date_iso}.html"
    markdown_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(_markdown_to_html(markdown, settings), encoding="utf-8")
    return markdown_path, html_path


def _create_hourly_figures(frame: pd.DataFrame, date_iso: str, figures_dir: Path) -> dict[str, Path]:
    import os

    cache_dir = figures_dir / ".matplotlib-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache_dir))

    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    figure_paths: dict[str, Path] = {}
    chart_frame = frame[frame["hour"].notna()].copy()
    hourly = (
        chart_frame.groupby(["hour", "point_name"], dropna=False)[list(METRIC_LABELS)]
        .mean(numeric_only=True)
        .reset_index()
        .sort_values("hour")
    )

    for metric, label in METRIC_LABELS.items():
        fig, ax = plt.subplots(figsize=(10, 5))
        for point_name, group in hourly.groupby("point_name", dropna=False):
            ax.plot(group["hour"], group[metric], marker="o", linewidth=1.6, label=str(point_name))
        ax.set_title(f"{label} - {date_iso}")
        ax.set_xlabel("Godzina")
        ax.set_ylabel(label)
        ax.grid(True, alpha=0.3)
        if metric in {"congestion_index", "delay_ratio"}:
            ax.axhline(1.0, color="#6b7280", linewidth=1, linestyle="--")
        ax.legend(fontsize="small", loc="best")
        fig.autofmt_xdate()
        fig.tight_layout()
        path = figures_dir / f"{metric}_{date_iso}.png"
        fig.savefig(path, dpi=140)
        plt.close(fig)
        figure_paths[metric] = path

    return figure_paths


def _point_summary(frame: pd.DataFrame) -> pd.DataFrame:
    grouped = frame.groupby(["point_id", "point_name", "direction"], dropna=False)
    summary = grouped.agg(
        current_speed_mean=("current_speed", "mean"),
        current_speed_min=("current_speed", "min"),
        current_speed_max=("current_speed", "max"),
        congestion_index_mean=("congestion_index", "mean"),
        congestion_index_min=("congestion_index", "min"),
        congestion_index_max=("congestion_index", "max"),
        delay_ratio_mean=("delay_ratio", "mean"),
        delay_ratio_min=("delay_ratio", "min"),
        delay_ratio_max=("delay_ratio", "max"),
        delay_seconds_mean=("delay_seconds", "mean"),
        confidence_mean=("confidence", "mean"),
        measurements=("id", "count"),
    ).reset_index()
    return summary.sort_values(["congestion_index_mean", "delay_ratio_mean"], ascending=[True, False])


def _route_summary(route_measurements: list[dict[str, Any]]) -> pd.DataFrame:
    columns = [
        "route_name",
        "direction",
        "travel_time_mean",
        "travel_time_min",
        "travel_time_max",
        "delay_seconds_mean",
        "delay_ratio_mean",
        "average_speed_mean",
        "measurements",
        "source",
    ]
    if not route_measurements:
        return pd.DataFrame(columns=columns)

    frame = pd.DataFrame(route_measurements)
    for column in [
        "travel_time_seconds",
        "delay_seconds",
        "delay_ratio",
        "average_speed_kmh",
    ]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["source"] = frame.get("source_label", "Estymacja z Flow")
    summary = (
        frame.groupby(["route_id", "route_name", "direction", "source"], dropna=False)
        .agg(
            travel_time_mean=("travel_time_seconds", "mean"),
            travel_time_min=("travel_time_seconds", "min"),
            travel_time_max=("travel_time_seconds", "max"),
            delay_seconds_mean=("delay_seconds", "mean"),
            delay_ratio_mean=("delay_ratio", "mean"),
            average_speed_mean=("average_speed_kmh", "mean"),
            measurements=("route_id", "count"),
        )
        .reset_index()
    )
    return summary[columns]


def _worst_hour(frame: pd.DataFrame) -> dict[str, Any] | None:
    hourly = frame.groupby("hour", dropna=True).agg(
        congestion_index_mean=("congestion_index", "mean"),
        delay_ratio_mean=("delay_ratio", "mean"),
        delay_seconds_mean=("delay_seconds", "mean"),
        current_speed_mean=("current_speed", "mean"),
    )
    if hourly.empty:
        return None
    hourly = hourly.sort_values(["congestion_index_mean", "delay_ratio_mean"], ascending=[True, False])
    hour, row = next(iter(hourly.iterrows()))
    return {
        "hour": hour,
        "congestion_index_mean": row["congestion_index_mean"],
        "delay_ratio_mean": row["delay_ratio_mean"],
        "delay_seconds_mean": row["delay_seconds_mean"],
        "current_speed_mean": row["current_speed_mean"],
    }


def _worst_point(frame: pd.DataFrame) -> dict[str, Any] | None:
    grouped = frame.groupby(["point_id", "point_name"], dropna=False).agg(
        congestion_index_mean=("congestion_index", "mean"),
        delay_ratio_mean=("delay_ratio", "mean"),
        delay_seconds_mean=("delay_seconds", "mean"),
        current_speed_mean=("current_speed", "mean"),
    )
    if grouped.empty:
        return None
    grouped = grouped.sort_values(["congestion_index_mean", "delay_ratio_mean"], ascending=[True, False])
    (point_id, point_name), row = next(iter(grouped.iterrows()))
    return {
        "point_id": point_id,
        "point_name": point_name,
        "congestion_index_mean": row["congestion_index_mean"],
        "delay_ratio_mean": row["delay_ratio_mean"],
        "delay_seconds_mean": row["delay_seconds_mean"],
        "current_speed_mean": row["current_speed_mean"],
    }


def _automatic_comment(
    frame: pd.DataFrame,
    worst_hour: dict[str, Any] | None,
    worst_point: dict[str, Any] | None,
    settings: dict[str, Any],
) -> str:
    thresholds = settings.get("thresholds", DEFAULT_THRESHOLDS)
    avg_congestion = frame["congestion_index"].mean()
    avg_delay = frame["delay_ratio"].mean()
    avg_confidence = frame["confidence"].mean()
    interpretation = calculate_metrics(
        frame["current_speed"].mean(),
        frame["free_flow_speed"].mean(),
        frame["current_travel_time"].mean(),
        frame["free_flow_travel_time"].mean(),
        confidence=avg_confidence,
        thresholds=thresholds,
    ).interpretation

    parts = [
        f"Srednia dobowa interpretacja warunkow: {interpretation}.",
        f"Sredni indeks plynnosci wyniosl {_format_number(avg_congestion)}, a sredni wskaznik opoznienia {_format_number(avg_delay)}.",
    ]
    if worst_hour:
        parts.append(
            "Najmniej korzystna godzina wystapila okolo "
            f"{worst_hour['hour'].strftime('%H:%M')}, ze srednim indeksem plynnosci "
            f"{_format_number(worst_hour['congestion_index_mean'])}."
        )
    if worst_point:
        parts.append(
            "Najbardziej obciazony punkt pomiarowy to "
            f"{worst_point['point_name']}."
        )
    return " ".join(parts)


def _build_markdown_report(
    *,
    date_iso: str,
    settings: dict[str, Any],
    frame: pd.DataFrame,
    point_summary: pd.DataFrame,
    route_summary: pd.DataFrame,
    worst_hour: dict[str, Any] | None,
    worst_point: dict[str, Any] | None,
    comment: str,
    figure_paths: dict[str, Path],
    output_dir: Path,
) -> str:
    report_settings = settings.get("report", {})
    title = report_settings.get("title", "Dobowy raport warunkow ruchu")
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        f"# {title}: {date_iso}",
        "",
        f"Projekt: {settings.get('project', {}).get('name', 'Monitoring ruchu')}",
        f"Wygenerowano: {generated_at}",
        "",
        "## Podsumowanie",
        "",
        f"Liczba pomiarow: {len(frame)}",
        f"Liczba punktow pomiarowych: {frame['point_id'].nunique()}",
        f"Liczba cykli pomiarowych: {frame['analysis_time_dt'].dropna().nunique()}",
        f"Srednia predkosc biezaca: {_format_number(frame['current_speed'].mean())} km/h",
        f"Sredni indeks plynnosci ruchu: {_format_number(frame['congestion_index'].mean())}",
        f"Sredni wskaznik opoznienia: {_format_number(frame['delay_ratio'].mean())}",
        "",
        "## Najwazniejsze obserwacje",
        "",
        comment,
        "",
    ]

    if worst_hour:
        lines.extend(
            [
                "### Najgorsza godzina",
                "",
                f"- Godzina slotu pomiarowego: {worst_hour['hour'].strftime('%Y-%m-%d %H:%M')}",
                f"- Sredni indeks plynnosci: {_format_number(worst_hour['congestion_index_mean'])}",
                f"- Sredni wskaznik opoznienia: {_format_number(worst_hour['delay_ratio_mean'])}",
                f"- Srednia predkosc: {_format_number(worst_hour['current_speed_mean'])} km/h",
                "",
            ]
        )

    if worst_point:
        lines.extend(
            [
                "### Najbardziej przeciazony punkt",
                "",
                f"- Punkt: {worst_point['point_name']}",
                f"- ID: {worst_point['point_id']}",
                f"- Sredni indeks plynnosci: {_format_number(worst_point['congestion_index_mean'])}",
                f"- Sredni wskaznik opoznienia: {_format_number(worst_point['delay_ratio_mean'])}",
                "",
            ]
        )

    lines.extend(
        [
            "## Estymowane czasy przejazdu odcinkow",
            "",
            (
                _route_summary_to_markdown(route_summary)
                if not route_summary.empty
                else "Brak kompletnego zestawu punktow do estymacji tras."
            ),
            "",
            "Czasy odcinkowe sa estymowane z predkosci Flow Segment Data, wazonych dlugoscia fragmentow pomiedzy punktami. Nie sa bezposrednim wynikiem TomTom Routing API i moga nie obejmowac calego czasu oczekiwania na skrzyzowaniach.",
            "",
            "## Tabela punktow pomiarowych",
            "",
            _dataframe_to_markdown(point_summary),
            "",
            "## Wykresy godzinowe",
            "",
        ]
    )

    for metric, path in figure_paths.items():
        relative_path = path.relative_to(output_dir).as_posix() if path.is_relative_to(output_dir) else Path("..", "figures", path.name).as_posix()
        lines.extend(
            [
                f"### {METRIC_LABELS[metric]}",
                "",
                f"![{METRIC_LABELS[metric]}]({relative_path})",
                "",
            ]
        )

    lines.extend(
        [
            "## Uwagi metodologiczne",
            "",
            "Raport opisuje warunki ruchu na podstawie predkosci, czasu przejazdu oraz wskaznikow opoznienia i przeciazenia. Nie jest to bezposredni pomiar natezenia ruchu w pojazdach na godzine.",
        ]
    )
    return "\n".join(lines) + "\n"


def _empty_report(date_iso: str, settings: dict[str, Any]) -> str:
    title = settings.get("report", {}).get("title", "Dobowy raport warunkow ruchu")
    return "\n".join(
        [
            f"# {title}: {date_iso}",
            "",
            "Brak pomiarow w bazie danych dla wskazanej daty.",
            "",
            "Raport nie zawiera wykresow ani tabel agregacyjnych.",
            "",
        ]
    )


def _analysis_time_column(frame: pd.DataFrame) -> str:
    if (
        "measurement_slot_local" in frame.columns
        and frame["measurement_slot_local"].notna().any()
    ):
        return "measurement_slot_local"
    return "timestamp_local"


def _dataframe_to_markdown(frame: pd.DataFrame) -> str:
    display = frame.copy()
    rename_map = {
        "point_id": "ID punktu",
        "point_name": "Punkt",
        "direction": "Kierunek",
        "current_speed_mean": "Predkosc sr.",
        "current_speed_min": "Predkosc min",
        "current_speed_max": "Predkosc max",
        "congestion_index_mean": "Indeks sr.",
        "congestion_index_min": "Indeks min",
        "congestion_index_max": "Indeks max",
        "delay_ratio_mean": "Opoznienie sr.",
        "delay_ratio_min": "Opoznienie min",
        "delay_ratio_max": "Opoznienie max",
        "delay_seconds_mean": "Sekundy opoznienia sr.",
        "confidence_mean": "Wiarygodnosc sr.",
        "measurements": "Liczba pomiarow",
    }
    display = display.rename(columns=rename_map)
    for column in display.columns:
        if display[column].dtype.kind in "fc":
            display[column] = display[column].map(_format_number)
    headers = list(display.columns)
    rows = display.astype(str).values.tolist()
    separator = ["---"] * len(headers)
    table = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(separator) + " |",
    ]
    table.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(table)


def _route_summary_to_markdown(frame: pd.DataFrame) -> str:
    display = frame.rename(
        columns={
            "route_name": "Trasa",
            "direction": "Kierunek",
            "travel_time_mean": "Czas sr. [s]",
            "travel_time_min": "Czas min [s]",
            "travel_time_max": "Czas max [s]",
            "delay_seconds_mean": "Opoznienie sr. [s]",
            "delay_ratio_mean": "Wskaznik opoznienia sr.",
            "average_speed_mean": "Predkosc sr. [km/h]",
            "measurements": "Liczba estymacji",
            "source": "Zrodlo",
        }
    )
    for column in display.columns:
        if display[column].dtype.kind in "fc":
            display[column] = display[column].map(_format_number)
    headers = list(display.columns)
    rows = display.astype(str).values.tolist()
    table = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    table.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(table)


def _markdown_to_html(markdown_text: str, settings: dict[str, Any]) -> str:
    try:
        import markdown
    except ImportError:
        body = "<pre>" + markdown_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") + "</pre>"
    else:
        body = markdown.markdown(markdown_text, extensions=["tables"])

    title = settings.get("report", {}).get("title", "Raport")
    return f"""<!doctype html>
<html lang="pl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 2rem; line-height: 1.5; color: #111827; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 0.9rem; }}
    th, td {{ border: 1px solid #d1d5db; padding: 0.45rem 0.55rem; text-align: left; }}
    th {{ background: #f3f4f6; }}
    img {{ max-width: 100%; height: auto; }}
    code, pre {{ background: #f3f4f6; }}
  </style>
</head>
<body>
{body}
</body>
</html>
"""


def _format_number(value: Any) -> str:
    try:
        if pd.isna(value):
            return "brak"
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "brak"
