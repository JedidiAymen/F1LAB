"""Synthetic checksum/selection fixtures; no model calls or provider requests."""
import hashlib
import json

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from f1_racelab.api import create_app


@pytest.fixture
def saved(tmp_path):
    meta = pd.DataFrame({"split": ["train", "test"], "remaining_seconds": [60., 70.]})
    meta.to_parquet(tmp_path / "prefixes_meta.parquet")
    meta.assign(last_completed_lap=[60., 69.]).to_parquet(tmp_path / "predictions.parquet")
    np.savez_compressed(tmp_path / "prefixes.npz", x=np.zeros((2, 5, 64), dtype=np.float32))
    sha = lambda name: hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
    report = {"dataset": {"files": {name: sha(name) for name in ("prefixes.npz", "prefixes_meta.parquet")},
                          "window_seconds": 20, "grid": 64, "channels": ["speed", "throttle", "brake", "gear", "rpm"]},
              "prediction_sha256": sha("predictions.parquet")}
    (tmp_path / "study.json").write_text(json.dumps(report))
    (tmp_path / "study.sha256").write_text(sha("study.json"))
    return tmp_path


def test_saved_future_api_only_exposes_held_out_rows_and_is_read_only(saved):
    with TestClient(create_app(dna_future_path=saved)) as client:
        response = client.get("/api/v1/driver-dna/future-study")
        assert response.status_code == 200 and len(response.json()["cases"]) == 1
        assert client.get("/api/v1/driver-dna/future-study/0").status_code == 404
        prefix = client.get("/api/v1/driver-dna/future-study/1")
        assert prefix.status_code == 200 and len(prefix.json()["channels"]) == 5
        assert client.get("/api/v1/driver-dna/future-study/-1").status_code == 404
        assert client.post("/api/v1/driver-dna/future-study", json={"train": True}).status_code == 405


def test_prefix_and_prediction_tampering_fail_closed(saved):
    with TestClient(create_app(dna_future_path=saved)) as client:
        (saved / "prefixes.npz").write_bytes(b"tampered")
        assert client.get("/api/v1/driver-dna/future-study/1").status_code == 503
        (saved / "predictions.parquet").write_bytes(b"tampered")
        assert client.get("/api/v1/driver-dna/future-study").status_code == 503


def test_clean_checkout_shows_verified_aggregates_without_claiming_local_prefixes(tmp_path, monkeypatch):
    from f1_racelab.ml.driver_dna import future_service

    monkeypatch.setattr(future_service, "DEFAULT", tmp_path / "missing")
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/driver-dna/future-study")
        assert response.status_code == 200
        assert response.json()["artifact_mode"] == "aggregate_only"
        assert response.json()["cases"] == []
        assert len(response.json()["results"]) == 10
        assert client.get("/api/v1/driver-dna/future-study/1").status_code == 503
