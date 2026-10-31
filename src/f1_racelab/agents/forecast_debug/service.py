"""Read-only projection of a saved local LLM evaluation; never executes an agent."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_RUN = ROOT / "data/processed/agents/forecast_debug/20261031/ollama_qwen3_8b"
BUNDLED_RUN = ROOT / "docs/research/evidence/forecast_debug_20261031"


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
