"""Client for the TomTom Traffic API Flow Segment Data endpoint."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


class TomTomAPIError(RuntimeError):
    """Raised when the TomTom API request fails or returns malformed data."""


@dataclass
class TomTomClient:
    """Small wrapper around TomTom Flow Segment Data requests."""

    api_key: str | None = None
    endpoint_base: str = "https://api.tomtom.com/traffic/services/4/flowSegmentData"
    style: str = "absolute"
    zoom: int = 10
    unit: str = "KMPH"
    timeout_seconds: int = 20

    def __post_init__(self) -> None:
        self.api_key = self.api_key or os.getenv("TOMTOM_API_KEY")
        if not self.api_key:
            raise TomTomAPIError("Brak zmiennej srodowiskowej TOMTOM_API_KEY.")

    def fetch_flow_segment(
        self,
        *,
        latitude: float,
        longitude: float,
        point_id: str,
        point_name: str,
        direction: str,
        raw_dir: str | Path | None = None,
    ) -> dict[str, Any]:
        """Fetch and normalize one flow segment measurement."""

        requested_at = datetime.now(timezone.utc)
        url = f"{self.endpoint_base.rstrip('/')}/{self.style}/{self.zoom}/json"
        params = {
            "point": f"{latitude},{longitude}",
            "unit": self.unit,
            "key": self.api_key,
        }

        try:
            response = requests.get(url, params=params, timeout=self.timeout_seconds)
            response.raise_for_status()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            body = _short_response_body(exc.response)
            raise TomTomAPIError(f"Blad HTTP TomTom API ({status}): {body}") from exc
        except requests.RequestException as exc:
            raise TomTomAPIError(f"Nieudane polaczenie z TomTom API: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise TomTomAPIError("TomTom API zwrocilo odpowiedz, ktora nie jest JSON.") from exc

        raw_path = None
        if raw_dir is not None:
            raw_path = save_raw_response(
                payload,
                raw_dir=raw_dir,
                point_id=point_id,
                requested_at=requested_at,
            )

        return normalize_flow_segment(
            payload,
            point_id=point_id,
            point_name=point_name,
            direction=direction,
            latitude=latitude,
            longitude=longitude,
            requested_at=requested_at,
            raw_path=raw_path,
        )


def normalize_flow_segment(
    payload: dict[str, Any],
    *,
    point_id: str,
    point_name: str,
    direction: str,
    latitude: float,
    longitude: float,
    requested_at: datetime | None = None,
    raw_path: Path | None = None,
) -> dict[str, Any]:
    """Convert TomTom's API response into the project's measurement shape."""

    requested_at = requested_at or datetime.now(timezone.utc)
    segment = payload.get("flowSegmentData")
    if not isinstance(segment, dict):
        raise TomTomAPIError("Odpowiedz TomTom API nie zawiera obiektu flowSegmentData.")

    road_closure = segment.get("roadClosure", segment.get("road_closure", False))
    return {
        "timestamp_utc": requested_at.isoformat(),
        "point_id": point_id,
        "point_name": point_name,
        "direction": direction,
        "latitude": latitude,
        "longitude": longitude,
        "current_speed": _get_number(segment, "currentSpeed"),
        "free_flow_speed": _get_number(segment, "freeFlowSpeed"),
        "current_travel_time": _get_number(segment, "currentTravelTime"),
        "free_flow_travel_time": _get_number(segment, "freeFlowTravelTime"),
        "confidence": _get_number(segment, "confidence"),
        "road_closure": bool(road_closure),
        "raw_json": payload,
        "raw_file": str(raw_path) if raw_path else None,
    }


def save_raw_response(
    payload: dict[str, Any],
    *,
    raw_dir: str | Path,
    point_id: str,
    requested_at: datetime | None = None,
) -> Path:
    """Persist raw TomTom JSON to disk and return the file path."""

    requested_at = requested_at or datetime.now(timezone.utc)
    raw_dir = Path(raw_dir)
    dated_dir = raw_dir / requested_at.strftime("%Y-%m-%d")
    dated_dir.mkdir(parents=True, exist_ok=True)
    safe_point_id = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in point_id)
    filename = f"{requested_at.strftime('%Y%m%dT%H%M%SZ')}_{safe_point_id}.json"
    path = dated_dir / filename
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _get_number(data: dict[str, Any], key: str) -> float | None:
    value = data.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _short_response_body(response: requests.Response | None) -> str:
    if response is None:
        return "brak tresci odpowiedzi"
    text = response.text.strip()
    if len(text) > 500:
        return f"{text[:500]}..."
    return text or "brak tresci odpowiedzi"
