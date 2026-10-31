import hashlib
import json

import httpx
import pytest
from test_ml_common import card

from f1_racelab.ml.common.registry import save_artifact
from f1_racelab.ml.common.tracking import numeric_metrics, record_artifact


def test_local_tracking_and_tamper_rejection(tmp_path, monkeypatch):
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    save_artifact(tmp_path, "m", {"weights": [1]}, card())
    manifest = json.loads((tmp_path / "m.run.json").read_text())
    assert manifest["run_kind"] == "training" and manifest["tracking"]["status"] == "disabled"
    assert manifest["files"]["m.joblib"] == (tmp_path / "m.sha256").read_text().strip()
    (tmp_path / "m.joblib").write_bytes(b"modified")
    with pytest.raises(ValueError, match="SHA-256"):
        record_artifact(tmp_path, "m", card())


def test_mlflow_http_contract_uploads_and_finishes(tmp_path, monkeypatch):
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    save_artifact(tmp_path, "m", {}, card())
    requests = []

    def handle(request):
        requests.append(request)
        path = request.url.path
        if path.endswith("get-by-name"):
            return httpx.Response(404)
        if path.endswith("experiments/create"):
            return httpx.Response(200, json={"experiment_id": "1"})
        if path.endswith("runs/create"):
            return httpx.Response(200, json={"run": {"info": {
                "run_id": "abc", "artifact_uri": "mlflow-artifacts:/1/abc/artifacts"}}})
        return httpx.Response(200, json={})

    with httpx.Client(transport=httpx.MockTransport(handle), base_url="http://mlflow") as client:
        result = record_artifact(tmp_path, "m", card(), run_kind="artifact_import", tracking_uri="http://mlflow",
                                 client=client)
    assert result["tracking"]["status"] == "synced"
    assert len([r for r in requests if r.method == "PUT"]) == 4
    assert json.loads(requests[-1].content)["status"] == "FINISHED"
    assert result["run_kind"] == "artifact_import"


def test_tracking_failure_retains_artifact_and_honest_status(tmp_path, monkeypatch):
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    save_artifact(tmp_path, "m", {}, card())
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(503)),
                      base_url="http://mlflow") as client:
        result = record_artifact(tmp_path, "m", card(), tracking_uri="http://mlflow", client=client)
    assert result["tracking"] == {"status": "failed", "error_type": "HTTPStatusError"}
    assert (tmp_path / "m.joblib").is_file()
    assert numeric_metrics({"table": [{"model": "baseline", "mae_s": 1}], "bad": float("nan")}) == {
        "table.baseline.mae_s": 1.0}


def test_tensor_checkpoint_provenance_includes_required_preprocessing(tmp_path, monkeypatch):
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    from f1_racelab.ml.common.contracts import write_card

    (tmp_path / "neural.pt").write_bytes(b"synthetic checkpoint fixture")
    (tmp_path / "neural.sha256").write_text(hashlib.sha256((tmp_path / "neural.pt").read_bytes()).hexdigest())
    (tmp_path / "preprocessing.npz").write_bytes(b"synthetic normalizer fixture")
    write_card(card(), tmp_path / "neural.card.json")
    result = record_artifact(tmp_path, "neural", card(), artifact_suffix=".pt", extra_artifacts=("preprocessing.npz",))
    assert result["model_file"] == "neural.pt"
    assert "preprocessing.npz" in result["files"]
    with pytest.raises(ValueError, match="filenames"):
        record_artifact(tmp_path, "neural", card(), artifact_suffix=".pt", extra_artifacts=("../other",))
