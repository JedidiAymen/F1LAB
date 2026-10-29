import gzip
import json

import pytest
from fastapi.testclient import TestClient

from f1_racelab.api import create_app
from f1_racelab.session.catalog import SESSIONS
from f1_racelab.session.replay_source import ReplaySource
from f1_racelab.session.timeline import build_timeline


def _pack(duration=100):
    return {
        "schema_version": 1,
        "session": {"season": 2025, "round": 16, "kind": "race", "provider_key": "test"},
        "session_name": "fixture", "clock_origin_utc": "2025-09-07T13:00:00Z",
        "provider": "synthetic", "capabilities": ["positions"], "coverage": {},
        "drivers": [{"driver_id": str(i), "number": i, "acronym": f"D{i}", "name": f"D{i}",
                     "team": "T", "team_color": "FFFFFF"} for i in (1, 2)],
        "events": [], "intervals": {"1": [], "2": []},
        "locations": {"1": [[0, 0, 0], [duration, 1, 1]], "2": [[0, 0, 0], [duration, 1, 1]]},
        "geometry": {"source": "fixture", "quality": "estimated", "centerline_xy": [[0, 0]]},
    }


def test_timeline_shape_and_final_instant(tmp_path):
    path = tmp_path / "pack.json.gz"
    with gzip.open(path, "wt") as handle:
        json.dump(_pack(100), handle)
    out = build_timeline(ReplaySource.from_file(path), 30)
    assert out["times"] == [0.0, 30.0, 60.0, 90.0, 100.0]  # always ends at the pack end
    assert [d["driver_id"] for d in out["drivers"]] == ["1", "2"]
    assert all(len(d["positions"]) == len(out["times"]) == len(d["gaps"]) for d in out["drivers"])


def test_timeline_rejects_out_of_range_step(tmp_path):
    path = tmp_path / "pack.json.gz"
    with gzip.open(path, "wt") as handle:
        json.dump(_pack(), handle)
    client = TestClient(create_app(path))
    assert client.get("/api/v1/replay/monza-2025/timeline", params={"step": 1}).status_code == 422
    ok = client.get("/api/v1/replay/monza-2025/timeline", params={"step": 25})
    assert ok.status_code == 200 and ok.json()["step_seconds"] == 25


@pytest.mark.skipif(not SESSIONS["monza-2025"].pack_path.is_file(), reason="local Monza pack not built")
def test_every_sample_equals_the_canonical_state():
    replay = ReplaySource.from_file(SESSIONS["monza-2025"].pack_path)
    out = build_timeline(replay, 300)
    for index in (0, len(out["times"]) // 2, len(out["times"]) - 1):
        state = replay.state_at(out["times"][index]).drivers
        for driver in out["drivers"]:
            assert driver["positions"][index] == state[driver["driver_id"]].position
            assert driver["gaps"][index] == state[driver["driver_id"]].gap_to_leader_seconds
