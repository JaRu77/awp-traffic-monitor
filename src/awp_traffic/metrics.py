"""Traffic condition indicators used by the monitoring scripts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


DEFAULT_THRESHOLDS = {
    "low_confidence_below": 0.5,
    "congestion_index": {
        "free_flow_min": 0.85,
        "light_slowdown_min": 0.65,
        "significant_slowdown_min": 0.40,
    },
    "delay_ratio": {
        "light_slowdown_min": 1.15,
        "significant_slowdown_min": 1.50,
        "severe_congestion_min": 2.00,
    },
}


INTERPRETATIONS = {
    "no_data": "brak danych lub niska wiarygodnosc",
    "free_flow": "ruch plynny",
    "light": "lekkie spowolnienie",
    "significant": "wyrazne spowolnienie",
    "severe": "silne przeciazenie",
}


@dataclass(frozen=True)
class TrafficMetrics:
    """Calculated indicators for a single TomTom flow segment measurement."""

    congestion_index: float | None
    delay_ratio: float | None
    delay_seconds: float | None
    interpretation: str

    def as_dict(self) -> dict[str, float | str | None]:
        return {
            "congestion_index": self.congestion_index,
            "delay_ratio": self.delay_ratio,
            "delay_seconds": self.delay_seconds,
            "interpretation": self.interpretation,
        }


def calculate_metrics(
    current_speed: float | int | None,
    free_flow_speed: float | int | None,
    current_travel_time: float | int | None,
    free_flow_travel_time: float | int | None,
    *,
    confidence: float | int | None = None,
    road_closure: bool | None = False,
    thresholds: Mapping[str, Any] | None = None,
) -> TrafficMetrics:
    """Calculate congestion and delay indicators from one flow segment record."""

    merged_thresholds = _merge_thresholds(thresholds)
    current_speed_value = _to_float(current_speed)
    free_flow_speed_value = _to_float(free_flow_speed)
    current_time_value = _to_float(current_travel_time)
    free_flow_time_value = _to_float(free_flow_travel_time)
    confidence_value = _to_float(confidence)

    congestion_index = _safe_divide(current_speed_value, free_flow_speed_value)
    delay_ratio = _safe_divide(current_time_value, free_flow_time_value)
    delay_seconds = None
    if current_time_value is not None and free_flow_time_value is not None:
        delay_seconds = current_time_value - free_flow_time_value

    interpretation = interpret_conditions(
        congestion_index,
        delay_ratio,
        confidence=confidence_value,
        road_closure=bool(road_closure),
        thresholds=merged_thresholds,
    )

    return TrafficMetrics(
        congestion_index=congestion_index,
        delay_ratio=delay_ratio,
        delay_seconds=delay_seconds,
        interpretation=interpretation,
    )


def interpret_conditions(
    congestion_index: float | None,
    delay_ratio: float | None,
    *,
    confidence: float | None = None,
    road_closure: bool = False,
    thresholds: Mapping[str, Any] | None = None,
) -> str:
    """Return a Polish textual interpretation for calculated indicators."""

    merged_thresholds = _merge_thresholds(thresholds)
    low_confidence_below = merged_thresholds["low_confidence_below"]

    if congestion_index is None or delay_ratio is None:
        return INTERPRETATIONS["no_data"]

    if confidence is not None and confidence < low_confidence_below:
        return INTERPRETATIONS["no_data"]

    if road_closure:
        return INTERPRETATIONS["severe"]

    severity = max(
        _severity_from_congestion_index(congestion_index, merged_thresholds),
        _severity_from_delay_ratio(delay_ratio, merged_thresholds),
    )

    if severity == 0:
        return INTERPRETATIONS["free_flow"]
    if severity == 1:
        return INTERPRETATIONS["light"]
    if severity == 2:
        return INTERPRETATIONS["significant"]
    return INTERPRETATIONS["severe"]


def _severity_from_congestion_index(value: float, thresholds: Mapping[str, Any]) -> int:
    congestion_thresholds = thresholds["congestion_index"]
    if value >= congestion_thresholds["free_flow_min"]:
        return 0
    if value >= congestion_thresholds["light_slowdown_min"]:
        return 1
    if value >= congestion_thresholds["significant_slowdown_min"]:
        return 2
    return 3


def _severity_from_delay_ratio(value: float, thresholds: Mapping[str, Any]) -> int:
    delay_thresholds = thresholds["delay_ratio"]
    if value < delay_thresholds["light_slowdown_min"]:
        return 0
    if value < delay_thresholds["significant_slowdown_min"]:
        return 1
    if value < delay_thresholds["severe_congestion_min"]:
        return 2
    return 3


def _safe_divide(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _to_float(value: float | int | str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _merge_thresholds(thresholds: Mapping[str, Any] | None) -> dict[str, Any]:
    merged = {
        "low_confidence_below": DEFAULT_THRESHOLDS["low_confidence_below"],
        "congestion_index": dict(DEFAULT_THRESHOLDS["congestion_index"]),
        "delay_ratio": dict(DEFAULT_THRESHOLDS["delay_ratio"]),
    }
    if not thresholds:
        return merged

    for key, value in thresholds.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return merged
