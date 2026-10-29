import json

import pytest
from fastapi.testclient import TestClient

from f1_racelab.ml.driver_dna import service


def _write(root):
    (root / "dataset_summary.json").write_text(json.dumps({"laps": 10, "per_session": {"A": 10},
                                                           "shared_drivers_all_sessions": ["VER"]}))
    model = {"task_a": {"accuracy": 0.4, "chance": 0.1},
             "task_b": {"mean_accuracy": 0.8, "ci": [0.7, 0.9], "mean_majority_baseline": 0.5}}
    (root / "baselines.json").write_text(json.dumps({"models": {"logistic": model}, "task_b_controls": {}}))
    (root / "nets.json").write_text(json.dumps({"seeds": [1], "device": "cpu",
                                                "task_a": {"tcn": {"mean": 0.41}},
                                                "task_b": {"tcn": {"mean_accuracy": 0.85, "ci": [0.8, 0.9]}}}))


def test_summary_merges_and_labels_models(tmp_path):
    _write(tmp_path)
    out = service.summary(tmp_path)
    assert {r["model"] for r in out["task_a"]} == {"logistic (handcrafted)", "tcn"}
    assert out["chance_task_a"] == 0.1 and out["majority_task_b"] == 0.5 and out["limits"]


def test_missing_results_fail_with_reproduction_command(tmp_path):
    with pytest.raises(service.DnaUnavailable, match="Run:"):
        service.summary(tmp_path)


def test_endpoint_503_when_missing(monkeypatch):
    from f1_racelab.api import create_app
    monkeypatch.setattr(service, "FILES", ("does_not_exist.json",))
    response = TestClient(create_app()).get("/api/v1/driver-dna/summary")
    assert response.status_code == 503 and "Run:" in response.json()["detail"]
