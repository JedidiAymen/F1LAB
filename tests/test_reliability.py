import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from f1_racelab.api import create_app
from f1_racelab.ml.common.reliability import compare, psi


def fixture():
    return pd.DataFrame([{"race_id": f"r{race}", "driver_number": 1, "lap": lap, "model": model,
                          "year": 2025, "event": f"race {race}", "eligible_green_next": True,
                          "pred_seconds": 90 + error, "next_lap_seconds": 90}
                         for race in range(3) for lap in range(2)
                         for model, error in [("lightgbm", 0.5), ("persistence_last_lap", 1)]])


def test_paired_comparison_and_corruption_rejection():
    data = fixture()
    report = compare(data)
    candidate = next(row for row in report["comparison"] if row["model"] == "lightgbm")
    assert candidate["mae_s"] == 0.5 and candidate["rows"] == 6
    assert candidate["vs_persistence"]["mean_delta"] == -0.5
    with pytest.raises(ValueError, match="Duplicate"):
        compare(pd.concat([data, data.iloc[:1]]))
    data.loc[0, "next_lap_seconds"] = 99
    with pytest.raises(ValueError, match="Targets"):
        compare(data)


def test_psi_missingness_and_shift():
    reference = pd.Series(np.arange(100, dtype=float))
    assert psi(reference, reference) == pytest.approx(0)
    assert psi(reference, reference + 100) > 0.5
    assert psi(reference, pd.Series([np.nan] * 100)) > 0.5
    assert psi(pd.Series([5.0] * 100), pd.Series([50.0] * 100)) > 0.5
    assert psi(pd.Series([], dtype=float), reference) is None


def test_report_api_fails_closed_when_missing_or_modified(tmp_path):
    import hashlib
    import json

    path = tmp_path / "report.json"
    with TestClient(create_app(reliability_report_path=path)) as client:
        assert client.get("/api/v1/research/reliability").status_code == 503
        path.write_text(json.dumps({"schema_version": 1, "evidence": "synthetic", **compare(fixture())}))
        path.with_suffix(".sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest())
        assert client.get("/api/v1/research/reliability").json()["evidence"] == "synthetic"
        path.write_text("{}")
        assert client.get("/api/v1/research/reliability").status_code == 503
