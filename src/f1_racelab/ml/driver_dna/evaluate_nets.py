"""Run TCN and contrastive models through the Driver DNA protocol (Tasks A and B), 3 seeds each.

Task B for networks: one network per race is trained on the train-block laps of all drivers in that race, and a
teammate pair is decided by comparing the two teammates' logits on test-block laps (contrastive: logistic head on
embeddings of an encoder pre-trained without labels on that race's train block).

Command: ``uv run python -m f1_racelab.ml.driver_dna.evaluate_nets`` -> ``data/processed/driver_dna/nets.json``.
"""
from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from f1_racelab.ml.driver_dna import nets, protocol
from f1_racelab.ml.driver_dna.baselines import load
from f1_racelab.ml.driver_dna.dataset import OUT

SEEDS = (42, 7, 123)


def task_a(xn: np.ndarray, meta: pd.DataFrame, seed: int) -> dict:
    drivers = protocol.shared_drivers(meta)
    code = {d: i for i, d in enumerate(drivers)}
    y = meta.driver.map(code).to_numpy()
    out: dict[str, list] = {"tcn": [], "contrastive": []}
    for train, test, circuit in protocol.circuit_folds(meta, drivers):
        model = nets.fit_classifier(xn[train], y[train], len(drivers), seed=seed)
        out["tcn"].append(pd.DataFrame({"circuit": circuit, "driver": meta.driver.iloc[test].to_numpy(),
                                        "correct": nets.predict_logits(model, xn[test]).argmax(1) == y[test]}))
        encoder = nets.fit_contrastive(xn[train], seed=seed)  # labels unused; test circuit never seen
        head = LogisticRegression(max_iter=3000, C=0.5).fit(nets.embed(encoder, xn[train]), y[train])
        out["contrastive"].append(pd.DataFrame({"circuit": circuit, "driver": meta.driver.iloc[test].to_numpy(),
                                                "correct": head.predict(nets.embed(encoder, xn[test])) == y[test]}))
    return {k: pd.concat(v) for k, v in out.items()}


def task_b(xn: np.ndarray, meta: pd.DataFrame, seed: int) -> dict:
    splits = protocol.teammate_splits(meta)
    out: dict[str, list] = {"tcn": [], "contrastive": []}
    for session in sorted({s["session_key"] for s in splits}):
        group = [s for s in splits if s["session_key"] == session]
        train_idx = np.unique(np.concatenate([s["train"] for s in group]))
        names = sorted(meta.driver.loc[train_idx].unique())
        code = {d: i for i, d in enumerate(names)}
        y = meta.driver.loc[train_idx].map(code).to_numpy()
        model = nets.fit_classifier(xn[train_idx], y, len(names), seed=seed)
        encoder = nets.fit_contrastive(xn[train_idx], seed=seed)
        for s in group:
            test = s["test"]
            truth = meta.driver.loc[test].to_numpy()
            a, b = s["drivers"]
            logits = nets.predict_logits(model, xn[test])
            pred = np.where(logits[:, code[a]] >= logits[:, code[b]], a, b)
            out["tcn"].append({"circuit": s["circuit"], "team": s["team"], "accuracy": float((pred == truth).mean())})
            pair_train = s["train"]
            head = LogisticRegression(max_iter=3000, C=0.5).fit(nets.embed(encoder, xn[pair_train]),
                                                                meta.driver.loc[pair_train])
            pred = head.predict(nets.embed(encoder, xn[test]))
            out["contrastive"].append({"circuit": s["circuit"], "team": s["team"],
                                       "accuracy": float((pred == truth).mean())})
    return out


def main() -> None:
    x, meta = load()
    xn = protocol.normalise_per_circuit(x, meta)
    started = time.perf_counter()
    result: dict = {"seeds": list(SEEDS), "device": str(nets.DEVICE), "task_a": {}, "task_b": {}}
    a_runs = [task_a(xn, meta, s) for s in SEEDS]
    b_runs = [task_b(xn, meta, s) for s in SEEDS]
    for model in ("tcn", "contrastive"):
        accs = [float(r[model].correct.mean()) for r in a_runs]
        merged = pd.concat([r[model] for r in a_runs])
        result["task_a"][model] = {"accuracy_per_seed": accs, "mean": float(np.mean(accs)),
                                   "by_circuit": merged.groupby("circuit").correct.mean().to_dict(),
                                   "by_driver": merged.groupby("driver").correct.mean().round(3).to_dict()}
        per_seed = [np.array([p["accuracy"] for p in r[model]]) for r in b_runs]
        pair_mean = np.mean(per_seed, axis=0)       # average seeds first, then bootstrap over pairs
        mean, low, high = protocol.bootstrap_mean(pair_mean)
        result["task_b"][model] = {"pairs": len(pair_mean), "mean_accuracy": mean, "ci": [low, high],
                                   "accuracy_per_seed": [float(a.mean()) for a in per_seed]}
    result["seconds"] = time.perf_counter() - started
    (OUT / "nets.json").write_text(json.dumps(result, indent=2, default=float))
    print(json.dumps({k: result[k] for k in ("task_a", "task_b", "seconds")}, indent=1, default=float)[:3500])


if __name__ == "__main__":
    main()
