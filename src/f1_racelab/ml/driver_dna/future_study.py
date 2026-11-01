"""Fixed classical/neural remaining-lap study; inspectable artifacts, no promotion."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Literal

import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from f1_racelab.ml.common.contracts import (
    FeatureSpec,
    ModelCard,
    SplitSpec,
    dependency_versions,
    now_utc,
    write_card,
)
from f1_racelab.ml.common.tracking import record_artifact
from f1_racelab.ml.driver_dna.future_data import (
    CONTEXT,
    OUT,
    ROOT,
    WINDOW_S,
    write_json,
)
from f1_racelab.ml.driver_dna.protocol import (
    apply_train_normalization,
    fit_train_normalization,
)

NAMES = [f"{channel}_{stat}" for stat in ("mean", "std") for channel in ("speed", "throttle", "brake", "gear", "rpm")] + ["brake_events", "gear_changes", "throttle_changes"]


def describe_prefix(x: np.ndarray) -> np.ndarray:
    return np.column_stack([x.mean(-1), x.std(-1), (np.diff((x[:, 2] > 20).astype(int), axis=1) == 1).sum(1),
                            (np.diff(x[:, 3], axis=1) != 0).sum(1),
                            (np.abs(np.diff(x[:, 1], axis=1)) > 20).sum(1)]).astype(np.float32)


def metrics(actual: np.ndarray, predicted: np.ndarray) -> dict:
    error = predicted - actual
    return {"mae_s": float(np.abs(error).mean()), "median_ae_s": float(np.median(np.abs(error))),
            "rmse_s": float(np.sqrt(np.mean(error**2))), "bias_s": float(error.mean())}


def run(out: Path = OUT) -> dict:
    import torch

    from f1_racelab.ml.driver_dna.future_nets import RemainingLapNet, fit, predict

    if (out / "study.json").exists():
        raise ValueError("Study already exists; preserve it and choose a new dataset/run directory")
    card = json.loads((out / "dataset_card.json").read_text())
    for name, checksum in card["files"].items():
        if hashlib.sha256((out / name).read_bytes()).hexdigest() != checksum:
            raise ValueError("Dataset integrity mismatch")
    x = np.load(out / "prefixes.npz")["x"]
    meta = pd.read_parquet(out / "prefixes_meta.parquet")
    train = np.flatnonzero(meta.split == "train")
    val = np.flatnonzero(meta.split == "validation")
    test = np.flatnonzero(meta.split == "test")
    context = meta[list(CONTEXT)].to_numpy(np.float32)
    handcrafted = np.column_stack([context, describe_prefix(x)])
    actual = meta.remaining_seconds.to_numpy()
    baseline = np.maximum(meta.last_lap_seconds.to_numpy() - WINDOW_S, 0)
    residual = actual - baseline
    predictions = {"last_completed_lap": baseline,
                   "recent_three_median": np.maximum(meta.recent_three_seconds.to_numpy() - WINDOW_S, 0)}
    model_dir = out / "models"
    model_dir.mkdir(exist_ok=True)
    curves, artifacts = {}, {}
    settings: dict = {"ridge_alpha": 10, "lightgbm": {"n_estimators": 200, "num_leaves": 15,
                "min_child_samples": 30, "learning_rate": 0.03, "n_jobs": 2, "random_state": 42,
                "verbosity": -1}, "neural_seeds": [7, 42, 123], "neural_max_epochs": 25}
    write_json(out / "frozen_settings.json", settings)
    for name, features, model in [
        ("context_ridge", context, make_pipeline(StandardScaler(), Ridge(alpha=10))),
        ("prefix_ridge", handcrafted, make_pipeline(StandardScaler(), Ridge(alpha=10))),
        ("prefix_lightgbm", handcrafted, LGBMRegressor(**settings["lightgbm"]))]:
        model.fit(features[train], residual[train])
        path = model_dir / f"{name}.joblib"
        joblib.dump(model, path)
        loaded = joblib.load(path)
        predictions[name] = np.maximum(baseline + loaded.predict(features), 0)
        artifacts[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    xn_stats = fit_train_normalization(x, train)
    xn = apply_train_normalization(x, xn_stats)
    cn_stats = fit_train_normalization(context, train)
    cn = apply_train_normalization(context, cn_stats)
    target_mean, target_scale = float(residual[train].mean()), float(residual[train].std() + 1e-6)
    target = ((residual - target_mean) / target_scale).astype(np.float32)
    np.savez(model_dir / "preprocessing.npz", x_mean=xn_stats.mean, x_scale=xn_stats.scale,
             context_mean=cn_stats.mean, context_scale=cn_stats.scale,
             target_mean=target_mean, target_scale=target_scale)
    embeddings = None
    variants = [(f"tcn_seed{seed}", seed, True, False) for seed in (7, 42, 123)]
    variants += [("tcn_no_context_seed42", 42, False, False), ("tcn_masked_seed42", 42, True, True)]
    for name, seed, use_context, masked in variants:
        model, history = fit(xn, cn, target, train, val, seed=seed, use_context=use_context, masked=masked)
        path = model_dir / f"{name}.pt"
        torch.save(model.state_dict(), path)
        loaded = RemainingLapNet(use_context)
        loaded.load_state_dict(torch.load(path, weights_only=True))
        delta, z = predict(loaded, xn, cn)
        predictions[name] = np.maximum(baseline + delta * target_scale + target_mean, 0)
        if name == "tcn_seed42":
            embeddings = z
        curves[name] = history
        artifacts[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        print(f"Trained {name}: {len(history)} recorded epochs", flush=True)
    if embeddings is not None:
        np.savez_compressed(out / "embeddings.npz", z=embeddings, reference_indices=train)
    frame = meta.copy()
    for name, values in predictions.items():
        frame[name] = values
    frame.to_parquet(out / "predictions.parquet", index=False)
    results = []
    for name, values in predictions.items():
        by_driver = pd.DataFrame({"driver": meta.iloc[test].driver.to_numpy(),
                                  "delta": np.abs(values[test] - actual[test]) - np.abs(baseline[test] - actual[test])})
        groups = [g.delta.to_numpy() for _, g in by_driver.groupby("driver")]
        rng = np.random.default_rng(42)
        draws = [float(np.concatenate([groups[i] for i in rng.integers(len(groups), size=len(groups))]).mean())
                 for _ in range(5000)]
        results.append({"model": name, "validation": metrics(actual[val], values[val]),
                        "test": metrics(actual[test], values[test]),
                        "by_session": {str(key): metrics(actual[idx], values[idx]) for key in meta.iloc[test].session_key.unique()
                                       for idx in [np.flatnonzero(meta.session_key == key)]},
                        "paired_vs_persistence_s": float(by_driver.delta.mean()),
                        "conditional_driver_bootstrap_95_s": np.quantile(draws, [0.025, 0.975]).tolist()})
    artifacts["preprocessing.npz"] = hashlib.sha256((model_dir / "preprocessing.npz").read_bytes()).hexdigest()
    fingerprint = hashlib.sha256((card["metadata_fingerprint"] + card["tensor_sha256"]).encode()).hexdigest()
    dependencies = dependency_versions("torch", "numpy", "pandas", "scikit-learn", "lightgbm")
    for row in results:
        if row["model"] in {"last_completed_lap", "recent_three_median"}:
            continue
        model_card = ModelCard(
            model_id=f"dna_remaining_{row['model']}", version="1", task="remaining-lap regression",
            target="remaining_seconds at elapsed 20 s", dataset_fingerprint=fingerprint, dataset_rows=len(meta),
            features=[FeatureSpec(name=name, unit=unit, available_at="lap start +20 s observation cutoff")
                      for name, unit in [("prefix_speed[64]", "km/h"), ("prefix_throttle[64]", "%"),
                                         ("prefix_brake[64]", "%"), ("prefix_gear[64]", "gear"),
                                         ("prefix_rpm[64]", "rpm"),
                                         ("last_lap_seconds", "s"), ("recent_three_seconds", "s"),
                                         ("lap_number", "lap")]],
            split=SplitSpec(policy="fixed chronological sessions; training-only normalization",
                            train_groups=3, validation_groups=1, test_groups=2, group_key="session_key",
                            notes="Two test circuits and season boundary confounded; prior lap facts were inspected in pace work"),
            hyperparameters={**settings, "variant": row["model"], "preprocessing_sha256": artifacts["preprocessing.npz"],
                             "feature_contract": "prefix+context raw schema; variant uses subset/handcrafted descriptors"},
            seed=int(row["model"].split("seed")[-1]) if "seed" in row["model"] else 42,
            metrics={"validation": row["validation"], "test": row["test"]}, dependencies=dependencies,
            runtime={"device": "cpu", "threads": 2}, data_license="OpenF1 CC BY-NC-SA 4.0; upstream timing rights caveat",
            data_provenance="https://openf1.org/docs/; source hashes in dataset_card.json",
            limitations=["Completed target laps only; no operational provider publication timestamp guarantee",
                         "Future pit/SC disruptions retained; no intrinsic driver-style interpretation"],
            intended_use="Offline research; no promoted production replacement", created_at_utc=now_utc())
        name = row["model"]
        card_path = model_dir / f"{name}.card.json"
        artifacts[card_path.name] = write_card(model_card, card_path)
        suffix: Literal[".pt", ".joblib"] = ".pt" if name.startswith("tcn_") else ".joblib"
        (model_dir / f"{name}.sha256").write_text(artifacts[f"{name}{suffix}"] + "\n")
        record_artifact(model_dir, name, model_card, artifact_suffix=suffix,
                        extra_artifacts=("preprocessing.npz",) if suffix == ".pt" else ())
    report = {"schema_version": 1, "created_at_utc": now_utc(), "evidence": "real OpenF1 telemetry",
              "task": "remaining completed-lap seconds after observing 20 seconds", "dataset": card,
              "settings": settings, "results": results, "training_curves": curves,
              "features": [*CONTEXT, *NAMES], "artifacts_sha256": artifacts,
              "prediction_sha256": hashlib.sha256((out / "predictions.parquet").read_bytes()).hexdigest(),
              "source_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "source_dirty": bool(subprocess.check_output(["git", "diff", "HEAD"], cwd=ROOT)),
              "source_files": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in (ROOT / "src/f1_racelab/ml/driver_dna").glob("*.py")},
              "dependencies": dependencies,
              "limitations": ["Two new test circuits and the 2026 boundary are confounded.",
                              "Driver bootstrap conditions on these two events; not a new-circuit population interval.",
                              "No provider publication timestamp contract; retrospective observation-time features.",
                              "Completed targets only; future pit/SC disruptions are retained, censored laps unscored.",
                              "Predictive telemetry is not proof of intrinsic driving style."],
              "data_license": "OpenF1 CC BY-NC-SA 4.0; non-commercial research; upstream rights caveat",
              "intended_use": "Offline research, no promoted/deployed replacement"}
    write_json(out / "study.json", report)
    (out / "study.sha256").write_text(hashlib.sha256((out / "study.json").read_bytes()).hexdigest() + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    result = run(parser.parse_args().out)
    print(json.dumps(result["results"], indent=2))
