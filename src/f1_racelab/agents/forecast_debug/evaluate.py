"""Evaluate a forecast-debugging agent on scenarios with known root causes.

  uv run --extra engines python -m f1_racelab.agents.forecast_debug.evaluate --agent reference
  uv run --extra engines python -m f1_racelab.agents.forecast_debug.evaluate --agent ollama --model qwen3:8b

Metrics per run: root-cause accuracy (overall and per label), grounded-answer rate (a final answer citing at least
one tool observation that exists), undetermined/invalid answers, steps and tool errors. Writes ``results.json``,
``report.md`` and ``traces.jsonl`` to ``data/processed/agents/forecast_debug/<agent>/`` (git-ignored).
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from f1_racelab.agents.forecast_debug.agent import Diagnosis, run_agent
from f1_racelab.agents.forecast_debug.llm import ChatModel, OllamaChat
from f1_racelab.agents.forecast_debug.reference import diagnose
from f1_racelab.agents.forecast_debug.scenarios import LABELS, build_scenario
from f1_racelab.agents.forecast_debug.tools import ForecastTools

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "data/processed/agents/forecast_debug"
Solver = Callable[[ForecastTools], Diagnosis]


def model_solver(model: ChatModel, max_steps: int = 12) -> Solver:
    return lambda tools: run_agent(model, tools, max_steps=max_steps)


def evaluate(solver: Solver, labels: Sequence[str] = LABELS, seeds: Sequence[int] = (1, 2, 3)) -> dict[str, Any]:
    if not labels or not seeds:
        raise ValueError("Evaluation needs at least one label and seed")
    cases: list[dict[str, Any]] = []
    for label in labels:
        for seed in seeds:
            scenario = build_scenario(label, seed)
            started = time.perf_counter()
            tools = ForecastTools(scenario.tables)
            try:
                diagnosis = solver(tools)
            finally:
                tools.close()
            cases.append({"scenario_id": scenario.scenario_id, "expected": label, "predicted": diagnosis.root_cause,
                          "correct": diagnosis.root_cause == label, "grounded": bool(diagnosis.evidence),
                          "steps": diagnosis.steps, "tool_errors": diagnosis.tool_errors,
                          "invalid_replies": diagnosis.invalid_replies, "confidence": diagnosis.confidence,
                          "seconds": round(time.perf_counter() - started, 2), "notes": scenario.notes,
                          "diagnosis": asdict(diagnosis)})
    n = len(cases)
    per_label = {label: sum(c["correct"] for c in cases if c["expected"] == label)
                 / max(1, sum(c["expected"] == label for c in cases)) for label in labels}
    summary = {
        "cases": n,
        "accuracy": sum(c["correct"] for c in cases) / n,
        "correct_and_grounded": sum(c["correct"] and c["grounded"] for c in cases) / n,
        "grounded_rate": sum(c["grounded"] for c in cases) / n,
        "undetermined_or_invalid": sum(c["predicted"] in ("undetermined", "invalid_label") for c in cases) / n,
        "mean_steps": sum(c["steps"] for c in cases) / n,
        "tool_errors": sum(c["tool_errors"] for c in cases),
        "mean_seconds": statistics.mean(c["seconds"] for c in cases),
        "max_seconds": max(c["seconds"] for c in cases),
        "total_seconds": sum(c["seconds"] for c in cases),
        "tool_calls": sum(sum("tool_id" in step for step in c["diagnosis"]["trace"]) for c in cases),
        "false_citation_ids": sum(sum(str(e) not in {t.get("tool_id") for t in c["diagnosis"]["trace"]}
                                      for step in c["diagnosis"]["trace"] for e in step.get("final", {}).get("evidence", []))
                                  for c in cases),
        "per_label_accuracy": per_label,
        "confusions": dict(Counter(f"{c['expected']} -> {c['predicted']}" for c in cases if not c["correct"])),
    }
    return {"summary": summary, "cases": cases}


def to_markdown(name: str, result: dict[str, Any]) -> str:
    s = result["summary"]
    lines = [f"# Forecast-debugging agent evaluation: {name}", "",
             f"{s['cases']} synthetic scenarios with planted root causes (seeds vary magnitude and affected races).",
             "", "| Metric | Value |", "|---|---:|",
             f"| Root-cause accuracy | {s['accuracy']:.1%} |",
             f"| Correct with existing citation IDs (support not adjudicated) | {s['correct_and_grounded']:.1%} |",
             f"| Answers with existing citation IDs | {s['grounded_rate']:.1%} |",
             f"| Undetermined or invalid | {s['undetermined_or_invalid']:.1%} |",
             f"| Mean steps | {s['mean_steps']:.1f} |", f"| Tool errors | {s['tool_errors']} |",
             f"| Mean latency (s) | {s['mean_seconds']:.2f} |", f"| Tool calls | {s['tool_calls']} |",
             f"| False citation IDs | {s['false_citation_ids']} |", "",
             "| Root cause | Accuracy |", "|---|---:|"]
    lines += [f"| {label} | {acc:.0%} |" for label, acc in s["per_label_accuracy"].items()]
    if s["confusions"]:
        lines += ["", "Confusions (expected -> predicted):", ""]
        lines += [f"- {k}: {v}" for k, v in sorted(s["confusions"].items())]
    return "\n".join(lines) + "\n"


def write(name: str, result: dict[str, Any], out: Path) -> Path:
    target = out / name.replace(":", "_").replace("/", "_")
    target.mkdir(parents=True, exist_ok=True)
    (target / "results.json").write_text(json.dumps(
        {"summary": result["summary"], "cases": [{k: v for k, v in c.items() if k != "diagnosis"}
                                                 for c in result["cases"]]}, indent=2, default=str))
    with (target / "traces.jsonl").open("w") as fh:
        for case in result["cases"]:
            fh.write(json.dumps({"scenario_id": case["scenario_id"], **case["diagnosis"]}, default=str) + "\n")
    (target / "report.md").write_text(to_markdown(name, result))
    return target


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--agent", choices=["reference", "ollama"], default="reference")
    parser.add_argument("--model", default="qwen3:8b", help="Ollama model name")
    parser.add_argument("--host", default="http://localhost:11434")
    parser.add_argument("--seeds", type=int, default=3, help="scenarios per root cause")
    parser.add_argument("--labels", nargs="*", choices=LABELS, default=list(LABELS))
    parser.add_argument("--max-steps", type=int, default=12)
    parser.add_argument("--num-ctx", type=int, default=16384)
    parser.add_argument("--num-predict", type=int, default=1024)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)

    solver: Solver
    if args.agent == "reference":
        name, solver = "reference", diagnose
    else:
        model = OllamaChat(args.model, host=args.host, num_ctx=args.num_ctx,
                           num_predict=args.num_predict, timeout=args.timeout)
        name, solver = model.name, model_solver(model, args.max_steps)
    result = evaluate(solver, args.labels, range(1, args.seeds + 1))
    target = write(name, result, args.out)
    print(to_markdown(name, result))
    print(f"Wrote {target}")


if __name__ == "__main__":
    main()
