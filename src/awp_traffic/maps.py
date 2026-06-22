"""Map generation for configured measurement points."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable


def create_points_map(points: Iterable[dict[str, Any]], output_path: str | Path) -> Path:
    """Create an OpenStreetMap-based Folium map of all measurement points."""

    try:
        import folium
    except ImportError as exc:
        raise RuntimeError("Do tworzenia map wymagany jest pakiet folium.") from exc

    point_list = sorted(list(points), key=lambda item: item.get("corridor_order") or 0)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if point_list:
        center_lat = sum(float(point["latitude"]) for point in point_list) / len(point_list)
        center_lon = sum(float(point["longitude"]) for point in point_list) / len(point_list)
    else:
        center_lat, center_lon = 53.4285, 14.5528

    traffic_map = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=13,
        tiles="OpenStreetMap",
        control_scale=True,
    )

    corridor_coordinates = []
    for point in point_list:
        lat = float(point["latitude"])
        lon = float(point["longitude"])
        corridor_coordinates.append([lat, lon])
        popup = (
            f"<strong>{point.get('name', point.get('id'))}</strong><br>"
            f"Kierunek: {point.get('direction', 'brak')}<br>"
            f"{point.get('location_description', '')}"
        )
        folium.Marker(
            location=[lat, lon],
            tooltip=f"{point.get('corridor_order', '')}. {point.get('name', point.get('id'))}",
            popup=folium.Popup(popup, max_width=320),
        ).add_to(traffic_map)

    if len(corridor_coordinates) > 1:
        folium.PolyLine(
            corridor_coordinates,
            color="#2563eb",
            weight=4,
            opacity=0.75,
            tooltip="Os pomiarowa al. Wojska Polskiego",
        ).add_to(traffic_map)

    traffic_map.save(output_path)
    return output_path
