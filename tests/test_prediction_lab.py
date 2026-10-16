"""Prediction Lab exposes only checksum-verified retrospective rank outputs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from f1_racelab.api import create_app
from f1_racelab.models.qualifying_backtest import (
    COMMON_FEATURES,
    audit_prequalifying_cutoff,
)


def _write_artifacts(root: Path) -> None:
    rows = []
    for split, year in (("validation", 2024), ("test", 2025)):
        for driver, actual, fp3, ridge, lightgbm in (
            ("AAA", 1, 2, 1, 2), ("BBB", 2, 1, 2, 1),
        ):
            for model, rank in (("fp3", fp3), ("ridge", ridge), ("lightgbm", lightgbm)):
                rows.append({"year": year, "round": 1, "event": "Fixture Grand Prix",
                             "driver": driver, "model": model, "predicted_rank": rank,
                             "actual_rank": actual, "split": split,
                             "q1_gap_pct": 0.1, "final_position": actual})
    predictions_path = root / "predictions.parquet"
    pd.DataFrame(rows).to_parquet(predictions_path, index=False)
    for split in ("validation", "test"):
        year = 2024 if split == "validation" else 2025
        summaries = []
        event_metrics = []
        for model, mae in (("fp3", 1.0), ("ridge", 0.0), ("lightgbm", 1.0)):
            summary = {"model": model, "events": 1, "position_mae": mae,
                       "spearman": 1.0 if model == "ridge" else -1.0,
                       "pole_hit_rate": 1.0 if model == "ridge" else 0.0,
                       "top3_overlap": 1.0}
            summaries.append(summary)
            event_metrics.append({**summary, "year": year, "round": 1,
                                  "event": "Fixture Grand Prix", "drivers": 2})
        pd.DataFrame(summaries).to_csv(root / f"{split}_summary.csv", index=False)
        pd.DataFrame(event_metrics).to_csv(root / f"{split}_events.csv", index=False)
        pd.DataFrame([{"model": "ridge", "baseline": "fp3", "mean_delta": 0.0,
                       "ci_low": -0.2, "ci_high": 0.2, "events": 1}]).to_csv(
                           root / f"{split}_bootstrap.csv", index=False)
    raw = pd.DataFrame({"available_at": ["2025-03-15T05:00:00+00:00"], "session": ["Qualifying"]})
    cutoff = audit_prequalifying_cutoff(raw, COMMON_FEATURES)
    manifest = {
        "winner": "ridge", "feature_set": "common", "features": COMMON_FEATURES,
        "selection_year": 2024, "held_out_year": 2025,
        "target": "q1_gap_pct", "evaluation_label": "final_position",
        "dataset_sha256": "a" * 64,
        "predictions_sha256": hashlib.sha256(predictions_path.read_bytes()).hexdigest(),
        "cutoff_audit": cutoff,
        "n_training_events": 35, "n_training_rows": 684,
        "n_validation_events": 1, "n_validation_rows": 2,
        "n_test_events": 1, "n_test_rows": 2,
    }
    artifact_names = (
        "predictions.parquet", "validation_summary.csv", "test_summary.csv",
        "validation_bootstrap.csv", "test_bootstrap.csv",
        "validation_events.csv", "test_events.csv",
    )
    manifest["artifact_sha256"] = {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in artifact_names
    }
    (root / "experiment.json").write_text(json.dumps(manifest))


def test_cutoff_audit_records_session_and_discloses_timestamp_limit():
    raw = pd.DataFrame({"available_at": ["2025-03-15T05:00:00Z"], "session": ["Qualifying"]})
    audit = audit_prequalifying_cutoff(raw, COMMON_FEATURES)
    assert audit["prediction_cutoff"] == "immediately_before_qualifying"
    assert audit["feature_observed_at"] == "not_recorded_individually"
    assert audit["source_timestamp"]["status"] == "scheduled_qualifying_start"
    assert len(audit["features"]) == len(COMMON_FEATURES)


def test_cutoff_audit_rejects_target_or_invalid_source_time():
    raw = pd.DataFrame({"available_at": ["not-a-time"], "session": ["Qualifying"]})
    with pytest.raises(ValueError, match="subset"):
        audit_prequalifying_cutoff(raw, ["q1_gap_pct"])
    with pytest.raises(ValueError, match="timestamps"):
        audit_prequalifying_cutoff(raw, COMMON_FEATURES)
    wrong_session = pd.DataFrame({"available_at": ["2025-03-15T05:00:00Z"], "session": ["Race"]})
    with pytest.raises(ValueError, match="qualifying cutoff session"):
        audit_prequalifying_cutoff(wrong_session, COMMON_FEATURES)


def test_prediction_api_serves_checksum_checked_retrospective_ranks(tmp_path: Path):
    _write_artifacts(tmp_path)
    client = TestClient(create_app(qualifying_prediction_path=tmp_path))

    manifest = client.get("/api/v1/predictions/qualifying")
    assert manifest.status_code == 200
    assert manifest.json()["selected_model"] == "ridge"
    assert manifest.json()["training"]["n_test_events"] == 1
    assert manifest.json()["cutoff_audit"]["feature_observed_at"] == "not_recorded_individually"

    result = client.get("/api/v1/predictions/qualifying/event?year=2025&round=1&split=test")
    assert result.status_code == 200
    body = result.json()
    assert body["event"] == "Fixture Grand Prix"
    assert body["rankings"][0] == {
        "driver": "AAA", "predicted_rank": {"fp3": 2, "ridge": 1, "lightgbm": 2}, "actual_rank": 1,
    }
    assert "q1_gap_pct" not in str(body)
    assert "final_position" not in str(body)
    assert client.get("/api/v1/predictions/qualifying/event?year=2025&round=2&split=test").status_code == 404


def test_prediction_api_reports_missing_and_tampered_artifacts(tmp_path: Path):
    client = TestClient(create_app(qualifying_prediction_path=tmp_path / "missing"))
    assert client.get("/api/v1/predictions/qualifying").status_code == 503

    _write_artifacts(tmp_path)
    (tmp_path / "predictions.parquet").write_bytes(b"tampered")
    client = TestClient(create_app(qualifying_prediction_path=tmp_path))
    response = client.get("/api/v1/predictions/qualifying")
    assert response.status_code == 503
    assert "SHA-256" in response.json()["detail"]

    _write_artifacts(tmp_path)
    (tmp_path / "test_summary.csv").write_text("tampered")
    client = TestClient(create_app(qualifying_prediction_path=tmp_path))
    response = client.get("/api/v1/predictions/qualifying")
    assert response.status_code == 503
    assert "SHA-256 mismatch: test_summary.csv" in response.json()["detail"]
