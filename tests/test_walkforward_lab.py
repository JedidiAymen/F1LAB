import json

import numpy as np
import pytest
from fastapi.testclient import TestClient
from test_qualifying_walkforward import synthetic

from f1_racelab.api import create_app
from f1_racelab.models import qualifying_walkforward as wf
from f1_racelab.models.walkforward_lab import load_walkforward_lab, walkforward_event


@pytest.fixture(scope="module")
def artifacts(tmp_path_factory):
    import hashlib

    root = tmp_path_factory.mktemp("wf")
    result = wf.run(synthetic(events=20), warmup_events=8, draws=300)
    result["summary"].to_csv(root / "summary.csv", index=False)
    result["bootstrap"].to_csv(root / "bootstrap.csv", index=False)
    result["audit"]["reliability"].to_csv(root / "reliability.csv", index=False)
    result["predictions"].to_parquet(root / "predictions.parquet", index=False)
    (root / "experiment.json").write_text(json.dumps({
        "candidate": "ensemble", "models": list(wf.MODELS), "evaluated_years": [2024],
        "predictions_sha256": hashlib.sha256((root / "predictions.parquet").read_bytes()).hexdigest(),
    }))
    return root


def test_loader_and_event_projection(artifacts):
    lab = load_walkforward_lab(artifacts)
    event = lab["events"][-1]
    out = walkforward_event(lab, year=event["year"], round_no=event["round"])
    assert out["probabilistic"] and len(out["drivers"]) == 10
    assert np.isclose(sum(d["p_pole"] for d in out["drivers"]), 1.0)
    assert "q1_gap_pct" not in json.dumps(out)  # target never leaks to the client


def test_checksum_mismatch_fails_closed(artifacts, tmp_path):
    for f in artifacts.iterdir():
        (tmp_path / f.name).write_bytes(f.read_bytes())
    (tmp_path / "predictions.parquet").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="SHA-256"):
        load_walkforward_lab(tmp_path)


def test_api_endpoints_and_missing_artifacts(artifacts, tmp_path):
    client = TestClient(create_app(qualifying_walkforward_path=artifacts))
    manifest = client.get("/api/v1/predictions/qualifying/walkforward").json()
    first = manifest["events"][0]
    event = client.get("/api/v1/predictions/qualifying/walkforward/event",
                       params={"year": first["year"], "round": first["round"]})
    assert event.status_code == 200
    assert client.get("/api/v1/predictions/qualifying/walkforward/event",
                      params={"year": 2030, "round": 1}).status_code == 404
    missing = TestClient(create_app(qualifying_walkforward_path=tmp_path / "none"))
    assert missing.get("/api/v1/predictions/qualifying/walkforward").status_code == 503
