"""Compare original transductive and train-only handcrafted Driver DNA features.

Uses the exact existing retrospective lap cohort and split indices. This
isolates preprocessing availability; it is not a fresh holdout, larger dataset,
future-segment task, or retraining of the original neural models.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np

from f1_racelab.ml.common.contracts import dependency_versions, now_utc
from f1_racelab.ml.common.tracking import source_revision
from f1_racelab.ml.driver_dna import baselines, handcrafted, protocol
from f1_racelab.ml.driver_dna.dataset import OUT, SCALES


def run() -> dict:
    x, meta = baselines.load()
    raw = handcrafted.describe(x, SCALES)
    transductive = baselines.features(x, meta)
    # Both baseline factories already fit any scaler/classifier on train rows;
    # unlike features(), raw descriptors never use held-out circuit moments.
    result = {
        "schema_version": 1, "evidence": "real", "created_at_utc": now_utc(), "source": source_revision(),
        "laps": len(meta), "circuits": int(meta.circuit.nunique()),
        "data_sha256": {name: hashlib.sha256((OUT / name).read_bytes()).hexdigest()
                        for name in ("laps.npz", "laps_meta.parquet")},
        "dependencies": dependency_versions("numpy", "scikit-learn", "lightgbm"),
        "models": {name: {
            "transductive": {"task_a": baselines.task_a(transductive, meta, make),
                             "task_b": baselines.task_b(transductive, meta, make)},
            "inductive_normalization": {"task_a": baselines.task_a(raw, meta, make),
                                        "task_b": baselines.task_b(raw, meta, make)},
        } for name, make in baselines.MODELS.items()},
        "normalization": {"transductive": "Per-circuit moments include held-out circuit/laps (labels unused).",
                          "inductive_normalization": "Raw handcrafted features; all scaler/model fits use train only."},
        "limitations": ["Same inspected three-race cohort, not a fresh generalization estimate.",
                        "Retrospective quality filtering and closed shared-driver vocabulary are unchanged.",
                        "Task A has only three held-out circuits; no significant-gain claim.",
                        "Neural results remain the original transductive protocol; no inductive neural score exists.",
                        "Car/setup/tyre/traffic confounds remain; no innate-style or future-segment claim."],
    }
    # Independent poisoning check on the tensor transform used for future neural work.
    train, test, _ = protocol.circuit_folds(meta, protocol.shared_drivers(meta))[0]
    stats = protocol.fit_train_normalization(x, train)
    poisoned = x.copy()
    poisoned[test] += 100_000
    second = protocol.fit_train_normalization(poisoned, train)
    assert np.array_equal(stats.mean, second.mean) and np.array_equal(stats.scale, second.scale)
    result["held_out_poisoning_check"] = True
    return result


def main() -> None:
    result = run()
    path = OUT / "normalization_study.json"
    payload = json.dumps(result, indent=2, allow_nan=False).encode()
    path.write_bytes(payload)
    path.with_suffix(".sha256").write_text(hashlib.sha256(payload).hexdigest() + "\n")
    for name, model in result["models"].items():
        print(name, {policy: {"task_a": rows["task_a"]["accuracy"], "task_b": rows["task_b"]["mean_accuracy"]}
                     for policy, rows in model.items()})


if __name__ == "__main__":
    main()
