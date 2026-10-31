import json

from fastapi.testclient import TestClient

from f1_racelab.api import create_app


def test_saved_investigation_is_read_only_and_keeps_provenance(tmp_path):
    with TestClient(create_app(agent_evaluation_path=tmp_path)) as client:
        assert client.get("/api/v1/research/agent-evaluation").status_code == 503
        case = {"scenario_id": "fault-s1", "expected": "feature_skew", "predicted": "no_material_discrepancy"}
        (tmp_path / "results.json").write_text(json.dumps({"summary": {"cases": 1}, "cases": [case]}))
        trace = {"scenario_id": "fault-s1", "explanation": "wrong diagnosis", "evidence": ["t1"],
                 "trace": [{"tool_id": "t1", "action": "list_tables", "thought": "internal text",
                            "observation": '{"tables":[]}'}]}
        (tmp_path / "traces.jsonl").write_text(json.dumps(trace) + "\n")
        response = client.get("/api/v1/research/agent-evaluation")
        assert response.status_code == 200
        data = response.json()
        assert "synthetic" in data["evidence"] and len(data["source_sha256"]["traces.jsonl"]) == 64
        assert "thought" not in data["cases"][0]["trace"][0]
        assert client.post("/api/v1/research/agent-evaluation", json={"query": "drop"}).status_code == 405
