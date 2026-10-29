import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from f1_racelab.api import create_app
from f1_racelab.ml.pace import service


def test_forecast_projection_from_synthetic_artifacts():
    rows = []
    for lap in (5, 6):
        for model, pred in (("lightgbm", 91.0), ("anchor_median3", 90.5)):
            rows.append({"race_id": "r", "year": 2025, "circuit": "X", "event": "E", "driver_number": 1,
                         "lap": lap, "compound_next": "SOFT", "regime_next": "green",
                         "eligible_green_next": True, "anchor_seconds": 90.5, "next_lap_seconds": 91.2,
                         "tyre_age_next": 4.0, "model": model, "fold": 0, "pred_seconds": pred,
                         "q10_seconds": 90.0 if model == "lightgbm" else np.nan,
                         "q90_seconds": 92.0 if model == "lightgbm" else np.nan})
    contrib = pd.DataFrame({"c_tyre_age_next": [0.2, 0.3], "c_last1": [-0.1, 0.05], "c_bias": [0.0, 0.0],
                            "race_id": "r", "driver_number": 1, "lap": [5, 6]})
    lab = {"predictions": pd.DataFrame(rows), "contrib": contrib, "summary": {},
           "card": type("C", (), {"model_id": "m"})()}
    out = service.forecast(lab, "r", 1)
    assert [r["target_lap"] for r in out["laps"]] == [6, 7]
    first = out["laps"][0]
    assert first["q10_seconds"] <= first["forecast_seconds"] <= first["q90_seconds"]
    assert first["contributions"][0]["feature"] == "tyre_age_next"
    assert out["evidence"] == "ml_prediction_out_of_fold"
    with pytest.raises(KeyError):
        service.forecast(lab, "r", 99)


def test_missing_artifacts_return_503_with_reproduction_command(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "OUT", tmp_path)
    monkeypatch.setattr(service, "load", lambda: service.load.__wrapped__() if False else (_ for _ in ()).throw(
        service.PaceUnavailable(f"Race pace artifacts missing. Run: {service.REPRODUCE}")))
    client = TestClient(create_app())
    response = client.get("/api/v1/pace/races")
    assert response.status_code == 503 and "ml.pace.benchmark" in response.json()["detail"]
