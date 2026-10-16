"""Synthetic API fixture verifies one time-indexed RaceState contract."""

import gzip
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from f1_racelab.api import create_app
from f1_racelab.session.contracts import RaceState
from f1_racelab.session.replay_source import ReplaySource
from f1_racelab.telemetry.distance_alignment import build_lap_telemetry, compare_laps


def _write_telemetry_comparison(path: Path) -> None:
    start = datetime(2025, 9, 7, 14, tzinfo=UTC)
    laps = []
    for driver_number, base_speed in ((1, 72), (4, 54)):
        rows = [
            {
                "date": (start + timedelta(seconds=second)).isoformat(),
                "session_key": 9912,
                "meeting_key": 1268,
                "driver_number": driver_number,
                "speed": base_speed,
                "throttle": 70,
                "brake": 0,
                "rpm": 9000,
                "n_gear": 5,
                "drs": 0,
            }
            for second in range(3)
        ]
        lap_row = {
            "session_key": 9912,
            "meeting_key": 1268,
            "driver_number": driver_number,
            "lap_number": 50,
            "date_start": start.isoformat(),
            "lap_duration": 2,
            "is_pit_out_lap": False,
        }
        laps.append(build_lap_telemetry(
            rows, lap_row, session_key=9912, meeting_key=1268,
            driver_number=driver_number,
        ))
    comparison = compare_laps(
        laps[0], laps[1],
        source_hashes={"laps": "a" * 64, "car_a": "b" * 64, "car_b": "c" * 64},
        spacing_m=5,
    )
    path.write_text(comparison.model_dump_json())


def test_missing_replay_pack_is_reported(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "missing.json.gz"))
    response = client.get("/api/v1/replay/monza-2025/manifest")
    assert response.status_code == 503
    assert "openf1_replay" in response.json()["detail"]


def test_manifest_and_state_share_clock(tmp_path: Path) -> None:
    pack = {
        "schema_version": 1,
        "session": {"season": 2025, "round": 16, "kind": "race", "provider_key": "test"},
        "session_name": "fixture", "clock_origin_utc": "2025-09-07T13:00:00Z",
        "provider": "synthetic", "capabilities": ["positions", "pit_stops"], "coverage": {},
        "drivers": [{"driver_id": "1", "number": 1, "acronym": "ONE", "name": "One",
                     "team": "Fixture", "team_color": "FFFFFF"}],
        "events": [], "locations": {"1": [[0, 10, 20], [1, 20, 20]]},
        "intervals": {"1": []},
        "geometry": {"source": "fixture", "quality": "estimated", "centerline_xy": [[10, 20]]},
    }
    path = tmp_path / "pack.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(pack, handle)
    other_path = tmp_path / "monaco.json.gz"
    other = {**pack, "session": {"season": 2023, "round": 6, "kind": "race"},
             "clock_origin_utc": "2023-05-28T13:00:00Z",
             "capabilities": ["positions"],
             "locations": {"1": [[0, 100, 20], [1, 110, 20]]}}
    with gzip.open(other_path, "wt", encoding="utf-8") as handle:
        json.dump(other, handle)
    comparison_path = tmp_path / "telemetry.json"
    _write_telemetry_comparison(comparison_path)
    client = TestClient(create_app(
        path,
        pack_paths={"monaco-2023": other_path},
        telemetry_comparison_paths={"monza-2025": comparison_path},
    ))
    catalog = client.get("/api/v1/replays").json()
    assert next(row for row in catalog if row["slug"] == "monaco-2023")["available"]
    assert client.get("/api/v1/replay/unknown/manifest").status_code == 404
    manifest = client.get("/api/v1/replay/monza-2025/manifest")
    assert manifest.status_code == 200
    assert manifest.json()["duration_seconds"] == 1
    assert manifest.json()["weather_changes"] == []
    assert manifest.json()["telemetry_comparisons"] == [{
        "id": "driver-1-lap-50-vs-driver-4-lap-50",
        "label": "#1 L50 vs #4 L50",
        "available": True,
        "quality": "estimated",
    }]
    comparison = client.get("/api/v1/replay/monza-2025/telemetry/lap-comparison")
    assert comparison.status_code == 200
    assert comparison.json()["distance_quality"] == "estimated"
    assert len(comparison.json()["samples"]) == 7
    state = client.get("/api/v1/replay/monza-2025/state", params={"seconds": .5})
    assert state.status_code == 200
    assert state.json()["schema_version"] == 3
    assert state.json()["weather"] is None
    assert state.json()["session_time_seconds"] == .5
    assert state.json()["drivers"]["1"]["track_x"] == 15
    assert state.json()["drivers"]["1"]["location_quality"] == "estimated"
    assert "applied_event_hashes" not in state.json()
    assert "location_context" not in state.json()
    assert RaceState.model_validate(state.json()).session_time_seconds == .5
    focused = client.get("/api/v1/replay/monza-2025/state",
                         params={"seconds": .5, "focus_driver": "1"})
    assert focused.status_code == 200
    focused_payload = focused.json()
    context = focused_payload.pop("location_context")
    assert focused_payload == state.json()
    assert context["session_time_seconds"] == focused_payload["session_time_seconds"] == .5
    assert context["driver_id"] == "1"
    assert context["segments"][0][-1] == {
        "session_time_seconds": .5, "track_x": 15., "track_y": 20., "quality": "estimated",
    }
    assert context["heading_radians"] == 0
    assert context["location_available"]
    assert client.get("/api/v1/replay/monza-2025/state",
        params={"seconds": .5, "focus_driver": "unknown"}).status_code == 404
    assert client.get("/api/v1/replay/monza-2025/state",
        params={"seconds": 1.1, "focus_driver": "unknown"}).status_code == 422

    other_state = client.get("/api/v1/replay/monaco-2023/state", params={"seconds": .5}).json()
    assert other_state["session"]["season"] == 2023
    assert "pit_stops" in state.json()["capabilities"]
    assert "pit_stops" not in other_state["capabilities"]
    assert other_state["drivers"]["1"]["track_x"] == 105
    assert client.get("/api/v1/replay/monza-2025/state", params={"seconds": .5}).json() == state.json()
    assert client.get("/api/v1/replay/monza-2025/state", params={"seconds": 1.1}).status_code == 422


def test_frozen_provider_points_are_hidden_after_fifteen_seconds(tmp_path: Path) -> None:
    pack = {
        "schema_version": 1,
        "session": {"season": 2025, "round": 16, "kind": "race"},
        "clock_origin_utc": "2025-09-07T13:00:00Z",
        "drivers": [{"driver_id": "1"}], "events": [],
        "locations": {"1": [[float(t), 10, 20] for t in range(20)]},
        "intervals": {"1": []},
    }
    path = tmp_path / "frozen.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(pack, handle)
    replay = ReplaySource.from_file(path)
    assert replay.state_at(14).drivers["1"].track_x == 10
    assert replay.state_at(15).drivers["1"].track_x is None


def test_missing_telemetry_artifact_is_reported_without_fetching(tmp_path: Path) -> None:
    client = TestClient(create_app(
        telemetry_comparison_paths={"monza-2025": tmp_path / "missing.json"},
    ))
    response = client.get("/api/v1/replay/monza-2025/telemetry/lap-comparison")
    assert response.status_code == 503
    assert "openf1_lap_comparison" in response.json()["detail"]
