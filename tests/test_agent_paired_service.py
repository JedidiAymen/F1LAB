"""Synthetic API fixtures exercise integrity, pairing, and read-only trace projection."""
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from f1_racelab.agents.forecast_debug.paired import paired_summary
from f1_racelab.agents.forecast_debug.service import load_paired
from f1_racelab.api import create_app


def save(root, name, data):
    payload = json.dumps(data, sort_keys=True).encode()
    (root / f"{name}.json").write_bytes(payload)
    checksum = hashlib.sha256(payload).hexdigest()
    (root / f"{name}.sha256").write_text(checksum)
    return checksum


@pytest.fixture
def study(tmp_path):
    protocol = {"settings": {"model": "synthetic"}, "sources": {}, "model_digest": "fixture"}
    identity = hashlib.sha256(json.dumps(protocol, sort_keys=True).encode()).hexdigest()
    save(tmp_path, "protocol", {**protocol, "protocol_sha256": identity, "created_at_utc": "fixture"})
    cases = [{"scenario_id": "feature_skew-s1", "expected": "feature_skew", "seed": 1, "arm": arm,
              "predicted": "feature_skew", "correct": True, "seconds": 1, "status": "ok", "tool_calls": 1,
              "tool_errors": 0, "false_citation_ids": 0, "input_fingerprints": {"table": "fixture"},
              "diagnosis": {"explanation": "fixture", "evidence": ["t1"], "trace": [
                  {"tool_id": "t1", "action": "sql", "args": {}, "observation": "fixture", "thought": "private"}]}}
             for arm in ("baseline", "candidate")]
    result = {"protocol_sha256": identity, "cases": cases, "summary": paired_summary(cases), "evidence": "synthetic fixture"}
    checksum = save(tmp_path, "results", result)
    save(tmp_path, "adjudications", {"results_sha256": checksum, "method": "fixture",
                                    "cases": [{"scenario_id": row["scenario_id"], "arm": row["arm"],
                                               "verdict": "insufficient", "reason": "fixture", "cited_ids": ["t1"]} for row in cases]})
    return tmp_path


def test_paired_api_projects_observations_and_is_read_only(study):
    with TestClient(create_app(agent_paired_path=study)) as client:
        response = client.get("/api/v1/research/agent-paired")
        assert response.status_code == 200
        case = response.json()["cases"][0]
        assert case["trace"][0]["observation"] == "fixture"
        assert "thought" not in case["trace"][0]
        assert case["support"]["verdict"] == "insufficient"
        assert client.post("/api/v1/research/agent-paired", json={"sql": "drop"}).status_code == 405


def test_tampering_returns_unavailable_instead_of_presenting_scores(study):
    (study / "results.json").write_text('{}')
    with TestClient(create_app(agent_paired_path=study)) as client:
        assert client.get("/api/v1/research/agent-paired").status_code == 503


def test_changed_scores_or_annotation_binding_are_rejected(study):
    result = json.loads((study / "results.json").read_text())
    result["summary"]["arms"]["baseline"]["accuracy"] = 0
    save(study, "results", result)
    with pytest.raises(ValueError, match="different results"):
        load_paired(study)
    annotations = json.loads((study / "adjudications.json").read_text())
    annotations["results_sha256"] = (study / "results.sha256").read_text()
    save(study, "adjudications", annotations)
    with pytest.raises(ValueError, match="scores"):
        load_paired(study)


def test_bundled_actual_inference_study_has_matching_pairs_and_complete_review():
    report = load_paired()
    assert len(report["cases"]) == 32
    assert report["summary"]["fault_families"] == 8
    assert report["protocol"]["settings"]["model"] == "qwen3:8b"
    assert all(case["support"]["reason"] and case["input_fingerprints"] for case in report["cases"])
    assert "synthetic" in report["evidence"]


def test_annotation_cannot_silently_review_different_citations(study):
    annotations = json.loads((study / "adjudications.json").read_text())
    annotations["cases"][0]["cited_ids"] = ["invented"]
    save(study, "adjudications", annotations)
    with pytest.raises(ValueError, match="different observations"):
        load_paired(study)
