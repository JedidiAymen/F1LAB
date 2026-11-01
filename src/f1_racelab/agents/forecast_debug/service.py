"""Read-only projection of a saved local LLM evaluation; never executes an agent."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_RUN = ROOT / "data/processed/agents/forecast_debug/20261031/ollama_qwen3_8b"
BUNDLED_RUN = ROOT / "docs/research/evidence/forecast_debug_20261031"
PAIRED_RUN = ROOT / "docs/research/evidence/forecast_debug_paired_20261031"


def load_paired(root: Path = PAIRED_RUN) -> dict:
    """Verify the published manifest, recompute scores and expose observations only."""
    from f1_racelab.agents.forecast_debug.paired import paired_summary

    files = {}
    for name in ("protocol", "results", "adjudications"):
        payload = (root / f"{name}.json").read_bytes()
        checksum = hashlib.sha256(payload).hexdigest()
        if (root / f"{name}.sha256").read_text().strip() != checksum:
            raise ValueError(f"Paired {name} checksum mismatch")
        files[name] = (json.loads(payload), checksum)
    protocol, results, annotations = (files[name][0] for name in ("protocol", "results", "adjudications"))
    frozen = {key: value for key, value in protocol.items() if key not in {"created_at_utc", "protocol_sha256"}}
    if hashlib.sha256(json.dumps(frozen, sort_keys=True).encode()).hexdigest() != protocol["protocol_sha256"]:
        raise ValueError("Protocol identity mismatch")
    if results["protocol_sha256"] != protocol["protocol_sha256"]:
        raise ValueError("Results use a different protocol")
    if annotations["results_sha256"] != files["results"][1]:
        raise ValueError("Adjudications refer to different results")
    summary = paired_summary(results["cases"])
    if summary != results["summary"]:
        raise ValueError("Saved scores do not match cases")
    by_case = {(row["scenario_id"], row["arm"]): row for row in annotations["cases"]}
    expected = {(row["scenario_id"], row["arm"]) for row in results["cases"]}
    if len(by_case) != len(annotations["cases"]) or set(by_case) != expected:
        raise ValueError("Adjudications must cover every case exactly once")
    cases = []
    for row in results["cases"]:
        diagnosis = row.get("diagnosis", {"explanation": "Worker failed; no diagnosis recovered", "evidence": [], "trace": []})
        annotation = by_case[(row["scenario_id"], row["arm"])]
        if annotation["verdict"] not in {"supported", "contradicted", "insufficient"}:
            raise ValueError("Unknown support verdict")
        if annotation["cited_ids"] != diagnosis["evidence"]:
            raise ValueError("Adjudication cites different observations")
        cases.append({**{key: row[key] for key in ("scenario_id", "arm", "expected", "predicted", "correct", "seconds", "status")},
                      "explanation": diagnosis["explanation"], "evidence_ids": diagnosis["evidence"],
                      "trace": [{key: step[key] for key in ("tool_id", "action", "args", "observation") if key in step}
                                for step in diagnosis["trace"] if "tool_id" in step],
                      "support": annotation, "input_fingerprints": row["input_fingerprints"]})
    return {"evidence": results["evidence"], "summary": summary, "cases": cases,
            "protocol": protocol, "source_sha256": {name: value[1] for name, value in files.items()},
            "support_method": annotations["method"]}


def load_run(root: Path = DEFAULT_RUN) -> dict:
    if root == DEFAULT_RUN and not root.is_dir():
        root = BUNDLED_RUN
    results_bytes, traces_bytes = (root / "results.json").read_bytes(), (root / "traces.jsonl").read_bytes()
    results = json.loads(results_bytes)
    traces = {item["scenario_id"]: item for item in map(json.loads, traces_bytes.decode().splitlines())}
    cases = []
    for case in results["cases"]:
        trace = traces[case["scenario_id"]]
        cases.append({**case, "explanation": trace["explanation"], "evidence_ids": trace["evidence"],
                      "trace": [{key: value for key, value in step.items() if key != "thought"}
                                for step in trace["trace"]]})
    if len(cases) != results["summary"]["cases"]:
        raise ValueError("Evaluation count mismatch")
    return {"evidence": "synthetic scenarios; actual local LLM outputs", "solver": "ollama:qwen3:8b",
            "summary": results["summary"], "cases": cases,
            "source_sha256": {"results.json": hashlib.sha256(results_bytes).hexdigest(),
                              "traces.jsonl": hashlib.sha256(traces_bytes).hexdigest()},
            "support_status": "Citation existence is automatic; logical support needs trace review."}
