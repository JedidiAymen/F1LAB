"""Serve stored Driver DNA evaluation results (no live inference; there is no deployed model)."""
from __future__ import annotations

import json

from f1_racelab.ml.driver_dna.dataset import OUT

REPRODUCE = ("uv sync --extra dl && uv run python -m f1_racelab.ml.driver_dna.dataset && "
             "uv run python -m f1_racelab.ml.driver_dna.baselines && uv run python -m f1_racelab.ml.driver_dna.evaluate_nets")
FILES = ("dataset_summary.json", "baselines.json", "nets.json")


class DnaUnavailable(RuntimeError):
    pass


def summary(root=OUT) -> dict:
    missing = [name for name in FILES if not (root / name).is_file()]
    if missing:
        raise DnaUnavailable(f"Driver DNA results missing ({', '.join(missing)}). Run: {REPRODUCE}")
    data, base, nets = (json.loads((root / name).read_text()) for name in FILES)
    task_a = [{"model": f"{m} (handcrafted)", "accuracy": r["task_a"]["accuracy"]} for m, r in base["models"].items()]
    task_a += [{"model": m, "accuracy": r["mean"]} for m, r in nets["task_a"].items()]
    task_b = [{"model": f"{m} (handcrafted)", "accuracy": r["task_b"]["mean_accuracy"], "ci": r["task_b"]["ci"]}
              for m, r in base["models"].items()]
    task_b += [{"model": m, "accuracy": r["mean_accuracy"], "ci": r["ci"]} for m, r in nets["task_b"].items()]
    chance = next(iter(base["models"].values()))["task_a"]["chance"]
    majority = next(iter(base["models"].values()))["task_b"]["mean_majority_baseline"]
    return {"evidence": "ml_evaluation_real", "laps": data["laps"], "per_circuit": data["per_session"],
            "shared_drivers": data["shared_drivers_all_sessions"], "chance_task_a": chance,
            "majority_task_b": majority, "task_a": task_a, "task_b": task_b,
            "task_b_controls": base["task_b_controls"], "seeds": nets["seeds"], "device": nets["device"],
            "limits": ["Only three races have local full-race telemetry (Monaco 2023, Brazil 2024, Monza 2025).",
                       "Task A is confounded for drivers who kept the same car; Task B by set-up and tyre state.",
                       "Neural models are not clearly better than handcrafted features plus logistic regression.",
                       "This measures separability in sampled laps, not a driver's innate style."]}
