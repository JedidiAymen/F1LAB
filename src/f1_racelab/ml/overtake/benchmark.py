"""Walk-forward benchmark for next-lap overtake probability (expanding window, grouped by race).

Models: constant training rate; logistic on gap only (interval, DRS window); logistic on all features; LightGBM
with isotonic calibration fitted on the last 20% of the *training* races (chronological), never on test races.
Metrics: Brier, log-loss, ROC-AUC, average precision, ECE (10 equal-count bins); paired race-clustered bootstrap of
the Brier difference against the gap-only logistic. Hyper-parameters are fixed constants; nothing is tuned on test folds.

Command: ``uv run python -m f1_racelab.ml.overtake.benchmark``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
from importlib.metadata import version
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.impute import SimpleImputer
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from f1_racelab.ml.common import metrics
from f1_racelab.ml.common.guards import (
    assert_chronological,
    assert_disjoint_groups,
    chronological_group_folds,
)
from f1_racelab.ml.overtake.dataset import FEATURES, OUT, ROOT

MIN_TRAIN_RACES = 20
STEP = 3
GAP_ONLY = ["interval", "within_drs"]
CLIP = (1e-4, 1 - 1e-4)


def _logistic(cols):
    return cols, make_pipeline(SimpleImputer(strategy="median", keep_empty_features=True), StandardScaler(),
                               LogisticRegression(max_iter=2000, C=0.5))


def _lgbm() -> LGBMClassifier:
    return LGBMClassifier(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=40, subsample=0.7,
                          subsample_freq=1, colsample_bytree=0.8, reg_lambda=5.0, random_state=42, n_jobs=4, verbosity=-1)


def ece(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    order = np.argsort(p)
    return float(sum(len(c) / len(p) * abs(y[c].mean() - p[c].mean()) for c in np.array_split(order, bins)))


def reliability(y: np.ndarray, p: np.ndarray, bins: int = 10) -> list[dict]:
    order = np.argsort(p)
    return [{"n": len(c), "mean_predicted": float(p[c].mean()), "observed": float(y[c].mean())}
            for c in np.array_split(order, bins)]


def walk_forward(pairs: pd.DataFrame, *, artifact_dir: Path | None = None) -> pd.DataFrame:
    identities = ["race_id", "lap", "driver_number", "a_driver_number"]
    if pairs.duplicated(identities).any():
        raise ValueError("Pair identities must be unique")
    races = pairs.groupby("race_id", as_index=False)["race_start"].first()
    rows = []
    for fold, (train_ids, test_ids) in enumerate(chronological_group_folds(
            races, group_col="race_id", time_col="race_start", min_train=MIN_TRAIN_RACES, step=STEP)):
        assert_disjoint_groups(train_ids, test_ids, name="race")
        train, test = pairs[pairs.race_id.isin(train_ids)], pairs[pairs.race_id.isin(test_ids)]
        assert_chronological(train["race_start"].tolist(), test["race_start"].tolist())
        y = train.overtake.to_numpy()
        preds = {"constant_rate": np.full(len(test), y.mean())}
        fitted = {}
        for name, cols in (("logistic_gap", GAP_ONLY), ("logistic_all", FEATURES)):
            _, model = _logistic(cols)
            fitted[name] = model.fit(train[cols], y)
            preds[name] = fitted[name].predict_proba(test[cols])[:, 1]
        cut = train_ids[int(len(train_ids) * 0.8)]
        start = races.set_index("race_id").race_start
        fit_ids = [r for r in train_ids if start[r] < start[cut]]
        fit, cal = train[train.race_id.isin(fit_ids)], train[~train.race_id.isin(fit_ids)]
        model = _lgbm().fit(fit[FEATURES], fit.overtake)
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(np.asarray(model.predict_proba(cal[FEATURES]))[:, 1],
                                                                              cal.overtake)
        preds["lightgbm_raw"] = np.asarray(model.predict_proba(test[FEATURES]))[:, 1]
        preds["lightgbm_calibrated"] = iso.predict(preds["lightgbm_raw"])
        if artifact_dir is not None:
            artifact_dir.mkdir(parents=True, exist_ok=True)
            path = artifact_dir / f"fold-{fold:02d}.joblib"
            if path.exists():
                raise FileExistsError("Fold artifact already exists; choose a new output directory")
            joblib.dump({"fold": fold, "train_ids": train_ids, "test_ids": test_ids,
                         "fit_ids": fit_ids, "constant_rate": float(y.mean()), "logistic_gap": fitted["logistic_gap"],
                         "logistic_all": fitted["logistic_all"], "lightgbm": model, "isotonic": iso,
                         "features": FEATURES, "gap_features": GAP_ONLY}, path)
        for name, p in preds.items():
            rows.append(pd.DataFrame({"fold": fold, "model": name, "race_id": test.race_id.to_numpy(),
                                      "lap": test.lap.to_numpy(), "driver_number": test.driver_number.to_numpy(),
                                      "a_driver_number": test.a_driver_number.to_numpy(),
                                      "year": test.year.to_numpy(), "y": test.overtake.to_numpy(),
                                      "p": np.clip(p, *CLIP)}))
    return pd.concat(rows, ignore_index=True)


def summarise(pred: pd.DataFrame) -> dict:
    table = []
    for model, part in pred.groupby("model"):
        y, p = part.y.to_numpy(), part.p.to_numpy()
        table.append({"model": model, "n": len(part), "brier": brier_score_loss(y, p), "log_loss": log_loss(y, p),
                      "auc": roc_auc_score(y, p), "average_precision": average_precision_score(y, p), "ece": ece(y, p)})
    base = pred[pred.model == "logistic_gap"].reset_index(drop=True)
    paired = []
    for model in ("constant_rate", "logistic_all", "lightgbm_raw", "lightgbm_calibrated"):
        other = pred[pred.model == model].reset_index(drop=True)
        keys = [key for key in ("race_id", "lap", "driver_number", "a_driver_number", "y") if key in base]
        if not base[keys].equals(other[keys]):
            raise ValueError("Predictions do not share the same ordered pair identities and labels")
        boot = metrics.cluster_bootstrap_delta((other.p - other.y) ** 2, (base.p - base.y) ** 2, base.race_id.to_numpy(),
                                               draws=5000)
        paired.append({"model": model, "baseline": "logistic_gap", **boot})
    best = pred[pred.model == "lightgbm_calibrated"]
    by_year = [{"year": int(y), "n": len(p), "rate": float(p.y.mean()), "mean_p": float(p.p.mean()),
                "brier": brier_score_loss(p.y, p.p), "auc": roc_auc_score(p.y, p.p)} for y, p in best.groupby("year")]
    return {"races_scored": int(pred.race_id.nunique()), "table": table, "paired_brier_vs_logistic_gap": paired,
            "reliability_lightgbm_calibrated": reliability(best.y.to_numpy(), best.p.to_numpy()), "by_year": by_year}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pairs', type=Path, default=OUT / 'pairs.parquet')
    parser.add_argument('--out', type=Path, default=OUT)
    args = parser.parse_args()
    if any((args.out / name).exists() for name in ('predictions.parquet', 'summary.json', 'models', 'manifest.json')):
        raise FileExistsError('Overtake benchmark artifacts exist; choose a new --out directory')
    source_revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    training_paths = ('src/f1_racelab/ml/overtake/dataset.py', 'src/f1_racelab/ml/overtake/benchmark.py')
    if subprocess.run(['git', 'diff', '--quiet', 'HEAD', '--', *training_paths], cwd=ROOT, check=False).returncode != 0:
        raise ValueError('Commit training code before running the benchmark')
    args.out.mkdir(parents=True, exist_ok=True)
    pairs = pd.read_parquet(args.pairs)
    pred = walk_forward(pairs, artifact_dir=args.out / 'models')
    pred.to_parquet(args.out / "predictions.parquet", index=False)
    summary = summarise(pred)
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2, default=float))
    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    manifest = {"schema_version": 1, "status": "retrospective, provisional; not live inference",
                "pair_dataset_sha256": digest(args.pairs), "prediction_sha256": digest(args.out / 'predictions.parquet'),
                "summary_sha256": digest(args.out / 'summary.json'),
                "models": {path.name: digest(path) for path in sorted((args.out / 'models').glob('*.joblib'))},
                "source_revision": source_revision,
                "training_code_sha256": {path: digest(ROOT / path) for path in training_paths},
                "python": platform.python_version(),
                "dependencies": {name: version(name) for name in ('numpy', 'pandas', 'scikit-learn', 'lightgbm', 'joblib')},
                "warning": "Joblib artifacts are trusted-local research files; verify hashes and never load untrusted pickles."}
    (args.out / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    print(pd.DataFrame(summary["table"]).round(4).to_string(index=False))
    for r in summary["paired_brier_vs_logistic_gap"]:
        print(r["model"], round(r["mean_delta"], 5), [round(r["ci_low"], 5), round(r["ci_high"], 5)])
    print(pd.DataFrame(summary["by_year"]).round(4).to_string(index=False))


if __name__ == "__main__":
    main()
