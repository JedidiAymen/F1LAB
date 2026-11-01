"""Paired, resumable local LLM evaluation against two frozen source checkouts.

The candidate checkout is reviewed/trusted source, not arbitrary untrusted code.
Each worker imports one implementation through PYTHONPATH; the harness itself
is identical across arms. Synthetic table hashes and model/source identities
are checked before comparing results. No model quality is inferred from tests.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx
import numpy as np

CORE = ("agent.py", "tools.py", "llm.py", "scenarios.py")
MODULE_PATH = Path("src/f1_racelab/agents/forecast_debug")
HARNESS = Path(__file__).resolve()


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False, sort_keys=True))
    temporary.replace(path)


@dataclass(frozen=True)
class Settings:
    model: str = "qwen3:8b"
    host: str = "http://127.0.0.1:11434"
    num_ctx: int = 4096
    num_predict: int = 512
    num_thread: int = 2
    model_seed: int = 42
    max_steps: int = 6
    timeout: float = 180
    worker_timeout: float = 240


DEFAULT_SETTINGS = Settings()


def snapshot(root: Path) -> dict:
    root = root.resolve()
    files = [MODULE_PATH / name for name in CORE]
    if (root / MODULE_PATH / "triage.py").exists():
        files.append(MODULE_PATH / "triage.py")
    changed = subprocess.check_output(["git", "diff", "HEAD", "--", *map(str, files)], cwd=root)
    if changed:
        raise ValueError("Agent implementation has uncommitted changes; freeze it before evaluation")
    return {"commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
            "files": {str(path): digest((root / path).read_bytes()) for path in files}}


def paired_summary(cases: list[dict]) -> dict:
    """Pair by scenario identity and bootstrap entire known fault families."""
    indexed: dict[str, dict[str, dict]] = {}
    for case in cases:
        arms = indexed.setdefault(case["scenario_id"], {})
        if case["arm"] in arms:
            raise ValueError("Duplicate scenario/arm result")
        arms[case["arm"]] = case
    if not indexed or any(set(pair) != {"baseline", "candidate"} for pair in indexed.values()):
        raise ValueError("Every scenario needs exactly one result from each arm")
    for pair in indexed.values():
        a, b = pair["baseline"], pair["candidate"]
        if (a["expected"], a["seed"], a.get("input_fingerprints")) != (
                b["expected"], b["seed"], b.get("input_fingerprints")):
            raise ValueError("Paired scenarios differ in ground truth, seed or table fingerprints")
    arms_out = {}
    for arm in ("baseline", "candidate"):
        rows = [pair[arm] for pair in indexed.values()]
        n = len(rows)
        arms_out[arm] = {
            "cases": n, "accuracy": sum(row["correct"] for row in rows) / n,
            "false_no_discrepancy": sum(row["predicted"] == "no_material_discrepancy"
                                        and row["expected"] != "no_material_discrepancy" for row in rows),
            "invalid_or_undetermined": sum(row["predicted"] in {"undetermined", "invalid_label"} for row in rows),
            "failed_workers": sum(row["status"] != "ok" for row in rows),
            "mean_seconds": float(np.mean([row["seconds"] for row in rows])),
            "p95_seconds": float(np.quantile([row["seconds"] for row in rows], 0.95)),
            "tool_calls": sum(row["tool_calls"] or 0 for row in rows),
            "unknown_tool_measurements": sum(row["tool_calls"] is None for row in rows),
            "tool_errors": sum(row["tool_errors"] or 0 for row in rows),
            "false_citation_ids": sum(row["false_citation_ids"] for row in rows),
        }
    families: dict[str, list[float]] = {}
    for pair in indexed.values():
        a, b = pair["baseline"], pair["candidate"]
        families.setdefault(a["expected"], []).append(float(b["correct"]) - float(a["correct"]))
    means = np.array([np.mean(values) for values in families.values()])
    draws = np.random.default_rng(42).choice(means, size=(5000, len(means)), replace=True).mean(axis=1)
    return {"arms": arms_out, "paired_accuracy_delta": float(means.mean()),
            "family_bootstrap_95": np.quantile(draws, [0.025, 0.975]).tolist(),
            "fault_families": len(means), "draws": 5000, "bootstrap_seed": 42}


def worker(params: dict, case_path: Path) -> dict:
    # These imports deliberately resolve from the selected checkout, not the harness directory.
    from f1_racelab.agents.forecast_debug import agent, llm, scenarios, tools
    from f1_racelab.ml.common.contracts import fingerprint_frame

    settings = Settings(**params["settings"])
    scenario = scenarios.build_scenario(params["label"], params["seed"])
    fingerprints = {name: fingerprint_frame(frame) for name, frame in scenario.tables.items()}
    calls: list[dict] = []

    class MeasuredChat(llm.OllamaChat):
        def complete(self, messages):
            started = time.perf_counter()
            try:
                reply = super().complete(messages)
            except Exception as exc:
                calls.append({"seconds": time.perf_counter() - started, "error_type": type(exc).__name__,
                              "messages": messages.copy()})
                write_json(case_path.with_suffix(".calls.json"), {"calls": calls})
                raise
            calls.append({"seconds": time.perf_counter() - started, "messages": messages.copy(), "reply": reply})
            write_json(case_path.with_suffix(".calls.json"), {"calls": calls})
            return reply

    model = MeasuredChat(settings.model, host=settings.host, temperature=0, think=False, num_ctx=settings.num_ctx,
                         timeout=settings.timeout, num_predict=settings.num_predict, num_thread=settings.num_thread)
    model._options["seed"] = settings.model_seed
    engine = tools.ForecastTools(scenario.tables)
    started = time.perf_counter()
    status, error_type = "ok", None
    try:
        diagnosis = agent.run_agent(model, engine, max_steps=settings.max_steps)
    except Exception as exc:  # noqa: BLE001 - preserve failed experiments in the denominator
        status, error_type = "error", type(exc).__name__
        diagnosis = agent.Diagnosis("undetermined", [], "Model/tool transport or worker error", None, len(calls))
    finally:
        engine.close()
    result = asdict(diagnosis)
    produced = {step["tool_id"] for step in diagnosis.trace if "tool_id" in step}
    false_ids = [str(value) for step in diagnosis.trace for value in step.get("final", {}).get("evidence", [])
                 if str(value) not in produced]
    return {"scenario_id": scenario.scenario_id, "expected": params["label"], "seed": params["seed"],
            "arm": params["arm"], "predicted": diagnosis.root_cause, "correct": diagnosis.root_cause == params["label"],
            "status": status, "error_type": error_type, "seconds": time.perf_counter() - started,
            "tool_calls": len(produced), "tool_errors": diagnosis.tool_errors, "false_citation_ids": len(false_ids),
            "table_fingerprints": fingerprints, "diagnosis": result,
            "input_fingerprints": params["input_fingerprints"],
            "implementation_path": str(Path(agent.__file__).resolve()), "protocol_sha256": params["protocol_sha256"]}


def validate_case(result: dict, params: dict, fingerprints: dict) -> None:
    expected = (f"{params['label']}-s{params['seed']}", params["label"], params["seed"], params["arm"])
    actual = tuple(result.get(key) for key in ("scenario_id", "expected", "seed", "arm"))
    if actual != expected or result.get("protocol_sha256") != params["protocol_sha256"]:
        raise ValueError("Case identity or protocol differs from frozen manifest")
    if result.get("input_fingerprints") != fingerprints:
        raise ValueError("Expected scenario table fingerprints differ")
    if result["status"] == "ok" and result.get("table_fingerprints") != fingerprints:
        raise ValueError("Worker used different scenario tables")


def run(baseline: Path, candidate: Path, out: Path, *, settings: Settings = DEFAULT_SETTINGS,
        resume: bool = False) -> dict:
    """Permit one writer per run directory; OS releases the lock after interruption."""
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    with (out / ".lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Another evaluator is writing this run directory") from exc
        return _run(baseline, candidate, out, settings=settings, resume=resume)


def _run(baseline: Path, candidate: Path, out: Path, *, settings: Settings, resume: bool) -> dict:
    from f1_racelab.agents.forecast_debug.scenarios import LABELS, build_scenario
    from f1_racelab.ml.common.contracts import (
        dependency_versions,
        fingerprint_frame,
        now_utc,
    )

    roots = {"baseline": baseline.resolve(), "candidate": candidate.resolve()}
    sources = {arm: snapshot(root) for arm, root in roots.items()}
    key = str(MODULE_PATH / "scenarios.py")
    if sources["baseline"]["files"][key] != sources["candidate"]["files"][key]:
        raise ValueError("Scenario generator source differs between arms")
    with httpx.Client(base_url=settings.host, timeout=15) as client:
        response = client.get("/api/tags")
        response.raise_for_status()
        model = next((row for row in response.json()["models"] if row["name"] == settings.model), None)
        if model is None:
            raise ValueError("Requested model is not installed; no automatic download is allowed")
        version = client.get("/api/version")
        version.raise_for_status()
    protocol = {"schema_version": 1, "settings": asdict(settings), "sources": sources,
                "fixed_chat": {"temperature": 0, "think": False, "stream": False, "format": "json", "keep_alive": "1m"},
                "scenario_seeds": [1, 4], "labels": list(LABELS), "model_digest": model["digest"],
                "ollama_version": version.json(), "harness_sha256": digest(HARNESS.read_bytes()),
                "platform": platform.platform(), "logical_cpus": os.cpu_count(),
                "dependencies": dependency_versions("numpy", "pandas", "duckdb", "httpx")}
    protocol_hash = digest(json.dumps(protocol, sort_keys=True).encode())
    path = out / "protocol.json"
    if path.exists():
        if not resume or json.loads(path.read_text())["protocol_sha256"] != protocol_hash:
            raise ValueError("Existing run differs or resume was not requested; do not overwrite evidence")
    else:
        if any(item.name != ".lock" for item in out.iterdir()):
            raise ValueError("Output directory is not empty")
        write_json(path, {**protocol, "protocol_sha256": protocol_hash, "created_at_utc": now_utc()})
    # Warm the shared model once before timing either arm. No diagnostic labels are supplied.
    with httpx.Client(timeout=settings.timeout) as client:
        warm = client.post(settings.host.rstrip("/") + "/api/chat", json={
            "model": settings.model, "messages": [{"role": "user", "content": 'Return {"ready": true}.'}],
            "format": "json", "stream": False, "think": False, "keep_alive": "1m",
            "options": {"temperature": 0, "seed": settings.model_seed, "num_ctx": settings.num_ctx,
                        "num_predict": settings.num_predict, "num_thread": settings.num_thread}})
        warm.raise_for_status()
        write_json(out / "warmups" / f"{uuid.uuid4().hex}.json", warm.json())
    cases = []
    for index, (label, seed) in enumerate((label, seed) for label in LABELS for seed in (1, 4)):
        scenario = build_scenario(label, seed)
        fingerprints = {name: fingerprint_frame(frame) for name, frame in scenario.tables.items()}
        order = ("baseline", "candidate") if index % 2 == 0 else ("candidate", "baseline")
        for arm in order:
            case_path = out / "cases" / f"{label}-s{seed}-{arm}.json"
            params = {"label": label, "seed": seed, "arm": arm, "settings": asdict(settings),
                      "input_fingerprints": fingerprints,
                      "protocol_sha256": protocol_hash}
            if case_path.exists():
                result = json.loads(case_path.read_text())
                if result["protocol_sha256"] != protocol_hash:
                    raise ValueError("Case protocol differs from frozen manifest")
            else:
                param_path = out / "params.json"
                write_json(param_path, params)
                started = time.perf_counter()
                try:
                    env = {**os.environ, "PYTHONPATH": str(roots[arm] / "src"),
                           "OMP_NUM_THREADS": "2", "OPENBLAS_NUM_THREADS": "2"}
                    subprocess.run([sys.executable, str(HARNESS), "--worker-params", str(param_path),
                                    "--case-path", str(case_path)], env=env, check=True,
                                   capture_output=True, text=True, timeout=settings.worker_timeout)
                    result = json.loads(case_path.read_text())
                except (subprocess.SubprocessError, OSError, ValueError) as exc:
                    result = {"scenario_id": f"{label}-s{seed}", "seed": seed, "expected": label, "arm": arm,
                              "predicted": "undetermined", "correct": False, "status": "worker_failed",
                              "error_type": type(exc).__name__, "seconds": time.perf_counter() - started,
                              "tool_calls": None, "tool_errors": None, "false_citation_ids": 0,
                              "protocol_sha256": protocol_hash}
                    write_json(case_path, result)
                result["worker_wall_seconds"] = time.perf_counter() - started
                result["input_fingerprints"] = fingerprints
                write_json(case_path, result)
            validate_case(result, params, fingerprints)
            if result.get("implementation_path") and Path(result["implementation_path"]) != roots[arm] / MODULE_PATH / "agent.py":
                raise ValueError("Worker imported an implementation outside its selected source checkout")
            if snapshot(roots[arm]) != sources[arm]:
                raise ValueError("Agent source changed during the run; stop rather than mix revisions")
            cases.append(result)
            print(f"{arm} {label}-s{seed}: {result['predicted']} ({result['seconds']:.2f} s)", flush=True)
    with httpx.Client(base_url=settings.host, timeout=15) as client:
        current = client.get("/api/tags")
        current.raise_for_status()
        if not any(row["name"] == settings.model and row["digest"] == model["digest"]
                   for row in current.json()["models"]):
            raise ValueError("Model identity changed during evaluation")
    report = {"schema_version": 1, "protocol_sha256": protocol_hash, "evidence": "synthetic scenarios; actual local LLM",
              "summary": paired_summary(cases), "cases": cases,
              "support_status": "Pending engineering adjudication of cited observations; citation IDs are not support."}
    write_json(out / "results.json", report)
    (out / "results.sha256").write_text(digest((out / "results.json").read_bytes()) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-root", type=Path)
    parser.add_argument("--candidate-root", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--worker-params", type=Path)
    parser.add_argument("--case-path", type=Path)
    args = parser.parse_args()
    if args.worker_params:
        if not args.case_path:
            parser.error("--case-path is required for a worker")
        write_json(args.case_path, worker(json.loads(args.worker_params.read_text()), args.case_path))
        return
    if not all((args.baseline_root, args.candidate_root, args.out)):
        parser.error("--baseline-root, --candidate-root and --out are required")
    report = run(args.baseline_root, args.candidate_root, args.out.resolve(), resume=args.resume)
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
