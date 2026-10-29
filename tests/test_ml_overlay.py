import pytest
from fastapi.testclient import TestClient
from test_pace_inference import _train

from f1_racelab.ml.pace import inference
from f1_racelab.strategy import ml_overlay


@pytest.fixture(autouse=True)
def _model(tmp_path, monkeypatch):
    inference.load.cache_clear()
    _train(tmp_path)
    monkeypatch.setattr(inference, "MODEL_DIR", tmp_path)
    yield
    inference.load.cache_clear()


def test_overlay_is_labelled_and_leaves_the_baseline_curve_untouched():
    req = ml_overlay.StintRequest(compound="MEDIUM", start_lap=5, laps=12)
    out = ml_overlay.stint_overlay("monza-2025", req)
    assert out["evidence"] == "ml_prediction_rollout" and out["baseline"] == "deterministic_simulator"
    assert len(out["laps"]) == 12 and out["laps"][0]["ml_rel"] == 0.0 and out["laps"][0]["sim_rel"] == 0.0
    # Simulator seconds equal the deterministic formula, independent of the ML model.
    assert out["laps"][3]["sim_seconds"] == pytest.approx(ml_overlay._sim_seconds("monza-2025", req)[3])
    assert "errors compound" in out["caveat"]


def test_rejects_unknown_context_and_circuit():
    with pytest.raises(ValueError):
        ml_overlay.stint_overlay("monza-2025", ml_overlay.StintRequest(compound="HARD", start_lap=1, laps=3,
                                                                       context={"banana": 1}))
    with pytest.raises(KeyError):
        ml_overlay.stint_overlay("nowhere", ml_overlay.StintRequest(compound="HARD", start_lap=1, laps=3))


def test_endpoint_200_422_503(monkeypatch, tmp_path):
    from f1_racelab.api import create_app
    client = TestClient(create_app())
    body = {"compound": "HARD", "start_lap": 10, "laps": 6}
    assert client.post("/api/v1/strategy/monza-2025/ml-pace", json=body).status_code == 200
    assert client.post("/api/v1/strategy/monza-2025/ml-pace", json={**body, "laps": 1}).status_code == 422
    assert client.post("/api/v1/strategy/nowhere/ml-pace", json=body).status_code == 404
    inference.load.cache_clear()
    monkeypatch.setattr(inference, "MODEL_DIR", tmp_path / "missing")
    assert client.post("/api/v1/strategy/monza-2025/ml-pace", json=body).status_code == 503
