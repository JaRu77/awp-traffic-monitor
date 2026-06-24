"""Estimate corridor travel times from existing Flow Segment point measurements."""

from __future__ import annotations

from collections import defaultdict
from math import asin, cos, radians, sin, sqrt
from typing import Any


def estimate_route_measurements(
    *,
    routes: list[dict[str, Any]],
    points: list[dict[str, Any]],
    measurements: list[dict[str, Any]],
    require_all_points: bool = True,
) -> list[dict[str, Any]]:
    """Return reproducible route estimates without making additional API calls."""

    points_by_id = {str(point["id"]): point for point in points}
    measurements_by_slot: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)

    for measurement in measurements:
        point_id = str(measurement.get("point_id") or "")
        slot = str(
            measurement.get("measurement_slot_local")
            or measurement.get("timestamp_local")
            or ""
        )
        if point_id and slot:
            measurements_by_slot[slot][point_id] = measurement

    estimates: list[dict[str, Any]] = []
    for route in routes:
        point_ids = [str(point_id) for point_id in route.get("point_ids") or []]
        if len(point_ids) < 2:
            continue
        route_points = [points_by_id.get(point_id) for point_id in point_ids]
        if any(point is None for point in route_points):
            continue
        point_weights = _point_length_weights(route_points)

        for slot, slot_measurements in measurements_by_slot.items():
            estimate = _estimate_route_for_slot(
                route=route,
                point_ids=point_ids,
                point_weights=point_weights,
                slot=slot,
                slot_measurements=slot_measurements,
                require_all_points=require_all_points,
            )
            if estimate:
                estimates.append(estimate)

    return sorted(
        estimates,
        key=lambda row: (
            str(row.get("measurement_slot_local") or ""),
            str(row.get("route_id") or ""),
        ),
    )


def merge_route_measurements(
    estimates: list[dict[str, Any]],
    api_measurements: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Prefer direct Routing API records if both sources exist for one slot."""

    merged: dict[tuple[Any, Any], dict[str, Any]] = {}
    for row in estimates:
        key = (row.get("route_id"), row.get("measurement_slot_local"))
        merged[key] = row
    for measurement in api_measurements:
        row = dict(measurement)
        row["source"] = "routing_api"
        row["source_label"] = "TomTom Routing API"
        key = (row.get("route_id"), row.get("measurement_slot_local"))
        merged[key] = row
    return sorted(
        merged.values(),
        key=lambda row: (
            str(row.get("measurement_slot_local") or ""),
            str(row.get("route_id") or ""),
        ),
    )


def _estimate_route_for_slot(
    *,
    route: dict[str, Any],
    point_ids: list[str],
    point_weights: list[float],
    slot: str,
    slot_measurements: dict[str, dict[str, Any]],
    require_all_points: bool,
) -> dict[str, Any] | None:
    available = [
        (point_id, weight, slot_measurements.get(point_id))
        for point_id, weight in zip(point_ids, point_weights)
        if slot_measurements.get(point_id) is not None
    ]
    if require_all_points and len(available) != len(point_ids):
        return None
    if len(available) < 2:
        return None

    usable = []
    for point_id, weight, measurement in available:
        current_speed = _positive_float(measurement.get("current_speed"))
        free_flow_speed = _positive_float(measurement.get("free_flow_speed"))
        if current_speed is None or free_flow_speed is None:
            if require_all_points:
                return None
            continue
        usable.append((point_id, weight, measurement, current_speed, free_flow_speed))

    if len(usable) < 2:
        return None

    length_meters = sum(item[1] for item in usable)
    if length_meters <= 0:
        return None

    travel_time_seconds = sum(
        weight / (current_speed / 3.6)
        for _, weight, _, current_speed, _ in usable
    )
    free_flow_travel_time_seconds = sum(
        weight / (free_flow_speed / 3.6)
        for _, weight, _, _, free_flow_speed in usable
    )
    average_speed_kmh = length_meters / travel_time_seconds * 3.6
    free_flow_average_speed_kmh = (
        length_meters / free_flow_travel_time_seconds * 3.6
    )
    delay_seconds = travel_time_seconds - free_flow_travel_time_seconds
    delay_ratio = travel_time_seconds / free_flow_travel_time_seconds
    congestion_index = average_speed_kmh / free_flow_average_speed_kmh
    confidences = [
        (_to_float(measurement.get("confidence")), weight)
        for _, weight, measurement, _, _ in usable
    ]
    confidence = _weighted_average(confidences)
    latest_measurement = max(
        (item[2] for item in usable),
        key=lambda row: str(row.get("timestamp_local") or ""),
    )
    first_measurement = usable[0][2]
    last_measurement = usable[-1][2]
    used_point_ids = [item[0] for item in usable]

    return {
        "timestamp_utc": latest_measurement.get("timestamp_utc"),
        "timestamp_local": latest_measurement.get("timestamp_local"),
        "measurement_slot_utc": latest_measurement.get("measurement_slot_utc"),
        "measurement_slot_local": slot,
        "route_id": route.get("id"),
        "route_name": route.get("name"),
        "direction": route.get("direction"),
        "origin_latitude": first_measurement.get("latitude"),
        "origin_longitude": first_measurement.get("longitude"),
        "destination_latitude": last_measurement.get("latitude"),
        "destination_longitude": last_measurement.get("longitude"),
        "waypoint_count": max(0, len(used_point_ids) - 2),
        "length_meters": length_meters,
        "travel_time_seconds": travel_time_seconds,
        "no_traffic_travel_time_seconds": free_flow_travel_time_seconds,
        "historic_traffic_travel_time_seconds": None,
        "live_traffic_travel_time_seconds": travel_time_seconds,
        "traffic_delay_seconds": delay_seconds,
        "traffic_length_meters": None,
        "average_speed_kmh": average_speed_kmh,
        "free_flow_average_speed_kmh": free_flow_average_speed_kmh,
        "congestion_index": congestion_index,
        "delay_ratio": delay_ratio,
        "delay_seconds": delay_seconds,
        "departure_time": None,
        "arrival_time": None,
        "confidence": confidence,
        "source": "flow_point_estimate",
        "source_label": "Estymacja z Flow",
        "points_used": len(used_point_ids),
        "points_expected": len(point_ids),
        "raw_json": {
            "method": "distance_weighted_point_speeds",
            "point_ids": used_point_ids,
        },
    }


def _point_length_weights(points: list[dict[str, Any]]) -> list[float]:
    distances = [
        _haversine_meters(
            float(left["latitude"]),
            float(left["longitude"]),
            float(right["latitude"]),
            float(right["longitude"]),
        )
        for left, right in zip(points, points[1:])
    ]
    if not distances:
        return []

    weights = [distances[0] / 2]
    weights.extend(
        (distances[index - 1] + distances[index]) / 2
        for index in range(1, len(points) - 1)
    )
    weights.append(distances[-1] / 2)
    return weights


def _haversine_meters(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    earth_radius_meters = 6_371_000
    lat_a = radians(latitude_a)
    lat_b = radians(latitude_b)
    delta_lat = radians(latitude_b - latitude_a)
    delta_lon = radians(longitude_b - longitude_a)
    value = (
        sin(delta_lat / 2) ** 2
        + cos(lat_a) * cos(lat_b) * sin(delta_lon / 2) ** 2
    )
    return 2 * earth_radius_meters * asin(sqrt(value))


def _positive_float(value: Any) -> float | None:
    converted = _to_float(value)
    return converted if converted is not None and converted > 0 else None


def _to_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _weighted_average(values: list[tuple[float | None, float]]) -> float | None:
    usable = [(value, weight) for value, weight in values if value is not None]
    total_weight = sum(weight for _, weight in usable)
    if not usable or total_weight <= 0:
        return None
    return sum(value * weight for value, weight in usable) / total_weight
