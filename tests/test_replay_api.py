"""Synthetic API fixture verifies one time-indexed RaceState contract."""

import gzip
import json
from pathlib import Path

from fastapi.testclient import TestClient

from f1_racelab.api import create_app
from f1_racelab.session.replay_source import ReplaySource


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
        "provider": "synthetic", "capabilities": {}, "coverage": {},
        "drivers": [{"driver_id": "1", "number": 1, "acronym": "ONE", "name": "One",
                     "team": "Fixture", "team_color": "FFFFFF"}],
        "events": [], "locations": {"1": [[0, 10, 20], [1, 20, 20]]},
        "intervals": {"1": []},
        "geometry": {"source": "fixture", "quality": "estimated", "centerline_xy": [[10, 20]]},
    }
    path = tmp_path / "pack.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(pack, handle)
    client = TestClient(create_app(path))
    manifest = client.get("/api/v1/replay/monza-2025/manifest")
    assert manifest.status_code == 200
    assert manifest.json()["duration_seconds"] == 1
    state = client.get("/api/v1/replay/monza-2025/state", params={"seconds": .5})
    assert state.status_code == 200
    assert state.json()["session_time_seconds"] == .5
    assert state.json()["drivers"]["1"]["track_x"] == 15
    assert state.json()["drivers"]["1"]["location_quality"] == "estimated"
    assert "applied_event_hashes" not in state.json()
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
