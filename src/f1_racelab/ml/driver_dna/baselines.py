"""Classical baselines for the Driver DNA protocol (`protocol.py`): handcrafted features + logistic / LightGBM.

Command: ``uv run python -m f1_racelab.ml.driver_dna.baselines`` -> ``data/processed/driver_dna/baselines.json``.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from f1_racelab.ml.driver_dna import handcrafted, protocol
from f1_racelab.ml.driver_dna.dataset import OUT, SCALES

MODELS = {
    "logistic": lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=0.5)),
    "lightgbm": lambda: LGBMClassifier(n_estimators=200, learning_rate=0.05, num_leaves=15, min_child_samples=10,
                                       subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbosity=-1,
                                       random_state=42, n_jobs=4),
}


def load() -> tuple[np.ndarray, pd.DataFrame]:
    x = np.load(OUT / "laps.npz")["x"]
    return x, pd.read_parquet(OUT / "laps_meta.parquet")


def features(x: np.ndarray, meta: pd.DataFrame) -> np.ndarray:
    """Handcrafted descriptors, z-scored per circuit (label-free) so track character cancels."""
    raw = handcrafted.describe(x, SCALES)
    out = np.empty_like(raw)
    for circuit in meta.circuit.unique():
        idx = np.flatnonzero((meta.circuit == circuit).to_numpy())
        out[idx] = (raw[idx] - raw[idx].mean(0)) / (raw[idx].std(0) + 1e-6)
    return out


def task_a(feat: np.ndarray, meta: pd.DataFrame, make) -> dict:
    drivers = protocol.shared_drivers(meta)
    rows = []
    for train, test, circuit in protocol.circuit_folds(meta, drivers):
        model = make().fit(feat[train], meta.driver.iloc[train])
        pred = model.predict(feat[test])
        truth = meta.driver.iloc[test].to_numpy()
        rows.append(pd.DataFrame({"circuit": circuit, "driver": truth, "correct": pred == truth}))
    frame = pd.concat(rows)
    return {"drivers": len(drivers), "chance": 1 / len(drivers), "accuracy": float(frame.correct.mean()),
            "by_circuit": frame.groupby("circuit").correct.mean().to_dict(),
            "by_driver": frame.groupby("driver").correct.mean().round(3).to_dict(), "n_test": len(frame)}


def task_b(feat: np.ndarray, meta: pd.DataFrame, make) -> dict:
    results = []
    for split in protocol.teammate_splits(meta):
        model = make().fit(feat[split["train"]], meta.driver.loc[split["train"]])
        pred = model.predict(feat[split["test"]])
        truth = meta.driver.loc[split["test"]].to_numpy()
        results.append({"circuit": split["circuit"], "team": split["team"], "n_test": len(truth),
                        "accuracy": float((pred == truth).mean()),
                        "majority": float(max((truth == d).mean() for d in split["drivers"]))})
    acc = np.array([r["accuracy"] for r in results])
    mean, low, high = protocol.bootstrap_mean(acc)
    return {"pairs": len(results), "mean_accuracy": mean, "ci": [low, high],
            "mean_majority_baseline": float(np.mean([r["majority"] for r in results])), "per_pair": results}


LEVEL = {"speed_mean", "speed_p10", "speed_p90", "rpm_mean", "rpm_p90"}


def controls(feat: np.ndarray, meta: pd.DataFrame) -> dict:
    """Task B confound checks: what do stint/pace metadata alone, or shape-only features, achieve?"""
    make = MODELS["logistic"]
    metadata = np.stack([meta.lap_number.to_numpy(float), meta.lap_seconds.to_numpy(float)], axis=1)
    shape = feat[:, [i for i, n in enumerate(handcrafted.NAMES) if n not in LEVEL]]
    rng = np.random.default_rng(42)
    shuffled = meta.assign(driver=meta.groupby(["session_key", "team"]).driver.transform(
        lambda v: rng.permutation(v.to_numpy())))
    return {"metadata_only_lap_number_and_lap_seconds": task_b(metadata, meta, make),
            "shape_features_without_absolute_level": task_b(shape, meta, make),
            "label_permutation_sanity": task_b(feat, shuffled, make)}


def main() -> None:
    x, meta = load()
    feat = features(x, meta)
    extra = {k: {"mean_accuracy": v["mean_accuracy"], "ci": v["ci"], "pairs": v["pairs"]}
             for k, v in controls(feat, meta).items()}
    report = {"laps": len(meta), "feature_names": handcrafted.NAMES, "task_b_controls": extra,
              "models": {name: {"task_a": task_a(feat, meta, make), "task_b": task_b(feat, meta, make)}
                         for name, make in MODELS.items()}}
    (OUT / "baselines.json").write_text(json.dumps(report, indent=2, default=float))
    print("controls", json.dumps(extra, default=float))
    for name, r in report["models"].items():
        print(name, "A", round(r["task_a"]["accuracy"], 3), "chance", round(r["task_a"]["chance"], 3),
              "| B", round(r["task_b"]["mean_accuracy"], 3), r["task_b"]["ci"], "majority",
              round(r["task_b"]["mean_majority_baseline"], 3), "pairs", r["task_b"]["pairs"])
        print("  A by driver", r["task_a"]["by_driver"])


if __name__ == "__main__":
    main()
