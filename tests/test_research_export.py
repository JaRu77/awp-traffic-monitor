import csv
import io
import json
import zipfile

from awp_traffic.research_export import create_research_package


def test_research_package_contains_analysis_ready_files(tmp_path):
    output_path = tmp_path / "research.zip"
    create_research_package(
        output_path=output_path,
        measurements=[
            {
                "id": 1,
                "timestamp_local": "2026-06-24T10:00:00+02:00",
                "point_id": "p1",
                "current_speed": 30,
                "raw_json": {"secret": "not included"},
            }
        ],
        route_measurements=[
            {
                "route_id": "r1",
                "measurement_slot_local": "2026-06-24T10:00:00+02:00",
                "average_speed_kmh": 25,
                "raw_json": {"large": True},
            }
        ],
        fetch_runs=[{"status": "success", "requests_attempted": 24}],
        points=[{"id": "p1", "name": "Punkt 1"}],
        routes=[{"id": "r1", "point_ids": ["p1", "p2"], "coordinates": []}],
        project_name="Test AWP",
        timezone_name="Europe/Warsaw",
    )

    with zipfile.ZipFile(output_path) as archive:
        assert set(archive.namelist()) == {
            "README.txt",
            "fetch_runs.csv",
            "measurements.csv",
            "metadata.json",
            "points.csv",
            "route_estimates.csv",
            "routes.csv",
        }
        measurement_text = archive.read("measurements.csv").decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(measurement_text)))
        assert rows[0]["point_id"] == "p1"
        assert "raw_json" not in rows[0]
        metadata = json.loads(archive.read("metadata.json"))
        assert metadata["measurement_rows"] == 1
        assert metadata["raw_json_included"] is False
