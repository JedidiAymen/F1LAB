import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from f1_racelab.ml.common.contracts import ModelCard, SplitSpec, dependency_versions
from f1_racelab.ml.common.registry import ArtifactUnavailable, save_artifact
from f1_racelab.ml.pace import dataset as ds
from f1_racelab.ml.pace import inference
from f1_racelab.ml.pace.benchmark import LgbmBundle

VALID = dict(anchor_seconds=92.0, lap=20, laps_remaining=30, tyre_age_next=10, stint_number_next=1,
             compound_next="MEDIUM", laps_in_stint=10, last1=0.2, last2=0.1, last3=0.0, slope5=0.03,
             stint_best_delta=-0.1, n_clean_history=8, track_temp=40, air_temp=25, humidity=50, wind_speed=2,
             rainfall=0, weather_age_s=30, interval_ahead=1.5, gap_to_leader=12, intervals_age_s=5,
             neutral_in_last3=0, yellow_in_last1=0, laps_since_neutral=50)


def _train(root, deps=None):
    rng = np.random.default_rng(0)
    frame = pd.DataFrame({c: rng.normal(size=300) for c in ds.NUMERIC})
    frame["compound_next"] = rng.choice(["SOFT", "MEDIUM", "HARD"], 300)
    bundle = LgbmBundle(ds.NUMERIC, ds.CATEGORICAL).fit(frame, rng.normal(size=300))
    card = ModelCard(model_id="race_pace_lightgbm", version="test", task="t", target="t", dataset_fingerprint="f",
                     dataset_rows=300, features=ds.FEATURES,
                     split=SplitSpec(policy="p", train_groups=1, test_groups=1, group_key="race_id"),
                     dependencies=deps or dependency_versions(*inference.CHECKED_LIBRARIES), evidence="synthetic",
                     data_provenance="synthetic", data_license="n/a", intended_use="test", limitations=["test"],
                     metrics={}, hyperparameters={}, seed=0, runtime={}, created_at_utc="2026-01-01T00:00:00Z")
    save_artifact(root, inference.NAME, bundle, card)


@pytest.fixture(autouse=True)
def _clear():
    inference.load.cache_clear()


def test_schema_rejects_out_of_range_and_extra_fields():
    with pytest.raises(ValidationError):
        inference.PaceFeatures(**{**VALID, "humidity": 140})
    with pytest.raises(ValidationError):
        inference.PaceFeatures(**{**VALID, "surprise": 1})
    with pytest.raises(ValidationError):
        inference.PaceFeatures(**{**VALID, "compound_next": "PURPLE"})


def test_predict_returns_forecast_version_and_ordered_interval(tmp_path):
    _train(tmp_path)
    out = inference.predict(inference.PaceFeatures(**VALID), tmp_path)
    assert out["model_version"] == "test" and out["q10_seconds"] <= out["forecast_seconds"] <= out["q90_seconds"]
    assert out["forecast_seconds"] == pytest.approx(92.0 + out["delta_seconds"])


def test_tampered_artifact_and_version_mismatch_fail_closed(tmp_path):
    _train(tmp_path)
    (tmp_path / "race_pace_lightgbm.joblib").write_bytes(b"not a model")
    with pytest.raises(ArtifactUnavailable, match="SHA-256"):
        inference.load(tmp_path)
    other = tmp_path / "b"
    _train(other, deps={**dependency_versions(*inference.CHECKED_LIBRARIES), "lightgbm": "0.0.1"})
    with pytest.raises(ArtifactUnavailable, match="version mismatch"):
        inference.load(other)


def test_api_validates_and_reports_unavailable(monkeypatch, tmp_path):
    from f1_racelab.api import create_app
    client = TestClient(create_app())
    assert client.post("/api/v1/pace/predict", json={**VALID, "humidity": 999}).status_code == 422
    monkeypatch.setattr(inference, "MODEL_DIR", tmp_path / "missing")
    response = client.post("/api/v1/pace/predict", json=VALID)
    assert response.status_code == 503 and "Run:" in response.json()["detail"]
    _train(tmp_path / "ok")
    monkeypatch.setattr(inference, "MODEL_DIR", tmp_path / "ok")
    response = client.post("/api/v1/pace/predict", json=VALID)
    assert response.status_code == 200 and response.json()["model_version"] == "test"
