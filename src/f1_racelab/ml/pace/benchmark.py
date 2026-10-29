"""Chronological, race-grouped benchmark for next-lap pace forecasting.

Protocol (docs/research/RACE_PACE_INTELLIGENCE.md):
* Races are ordered by start time. Fold *k* trains on every earlier race and
  scores the next ``STEP`` races (expanding window); no race is ever in both.
* Only green-flag clean targets are used for training and the headline metric.
  Rows whose next lap is yellow / SC-VSC / red are scored separately as
  out-of-distribution, with models still trained on green laps only.
* Models predict ``delta_seconds`` (lap L+1 minus a 3-lap median anchor); all
  reported errors are on the absolute lap time in seconds (identical error).
* Hyper-parameters are fixed constants. Nothing is tuned on scored folds.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from f1_racelab.ml.common import metrics
from f1_racelab.ml.common.contracts import (
    ModelCard,
    SplitSpec,
    dependency_versions,
    fingerprint_frame,
    now_utc,
)
from f1_racelab.ml.common.guards import (
    assert_chronological,
    assert_disjoint_groups,
    assert_no_forbidden_columns,
    chronological_group_folds,
)
from f1_racelab.ml.common.registry import save_artifact
from f1_racelab.ml.pace import dataset as ds

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "data/processed/race_pace"
ARTIFACTS = ROOT / "data/processed/models/race_pace"
SEED = 42
MIN_TRAIN_RACES = 20
STEP = 3
TARGET = "delta_seconds"
GROUPS = {
    "tyre": ["tyre_age_next", "laps_in_stint", "stint_number_next", "compound_next"],
    "previous_pace": ["last1", "last2", "last3", "slope5", "stint_best_delta", "n_clean_history"],
    "weather": ["track_temp", "air_temp", "humidity", "wind_speed", "rainfall", "weather_age_s"],
    "traffic": ["interval_ahead", "gap_to_leader", "intervals_age_s"],
    "regime_history": ["neutral_in_last3", "yellow_in_last1", "laps_since_neutral"],
    "race_progress": ["lap", "laps_remaining"],
}
LGBM_PARAMS = dict(n_estimators=400, learning_rate=0.05, num_leaves=31, min_child_samples=40,
                   subsample=0.7, subsample_freq=1, colsample_bytree=0.8, reg_lambda=5.0,
                   verbosity=-1, n_jobs=4)


def _columns(drop: list[str] | None = None, identity: bool = False) -> tuple[list[str], list[str]]:
    drop = set(drop or [])
    numeric = [c for c in ds.NUMERIC if c not in drop]
    categorical = [c for c in ds.CATEGORICAL if c not in drop]
    if identity:
        categorical = categorical + ds.IDENTITY
    return numeric, categorical


def _prep(numeric: list[str], categorical: list[str]) -> ColumnTransformer:
    return ColumnTransformer([
        ("num", Pipeline([("fill", SimpleImputer(strategy="median", keep_empty_features=True)),
                          ("scale", StandardScaler())]), numeric),
        ("cat", OneHotEncoder(handle_unknown="ignore"), categorical),
    ])


def _lgbm_frame(frame: pd.DataFrame, numeric: list[str], categorical: list[str],
                categories: dict[str, list] | None = None) -> pd.DataFrame:
    out = frame[numeric].astype(float).copy()
    for col in categorical:
        known = categories[col] if categories else sorted(frame[col].astype(str).unique())
        out[col] = pd.Categorical(frame[col].astype(str), categories=known)
    return out


class LgbmBundle:
    """Median + 10%/90% quantile LightGBM models sharing one feature schema."""

    def __init__(self, numeric: list[str], categorical: list[str], seed: int = SEED, quantiles: bool = True):
        self.numeric, self.categorical, self.seed, self.quantiles = numeric, categorical, seed, quantiles

    def fit(self, frame: pd.DataFrame, y: np.ndarray) -> LgbmBundle:
        self.categories = {c: sorted(frame[c].astype(str).unique()) for c in self.categorical}
        x = _lgbm_frame(frame, self.numeric, self.categorical, self.categories)
        self.median = LGBMRegressor(objective="l1", random_state=self.seed, **LGBM_PARAMS).fit(x, y)
        if self.quantiles:
            self.q10 = LGBMRegressor(objective="quantile", alpha=0.1, random_state=self.seed, **LGBM_PARAMS).fit(x, y)
            self.q90 = LGBMRegressor(objective="quantile", alpha=0.9, random_state=self.seed, **LGBM_PARAMS).fit(x, y)
        return self

    def _x(self, frame: pd.DataFrame) -> pd.DataFrame:
        return _lgbm_frame(frame, self.numeric, self.categorical, self.categories)

    def predict(self, frame: pd.DataFrame) -> dict[str, np.ndarray]:
        x = self._x(frame)
        out = {"median": self.median.predict(x)}
        if self.quantiles:
            low, high = self.q10.predict(x), self.q90.predict(x)
            out["q10"], out["q90"] = np.minimum(low, out["median"]), np.maximum(high, out["median"])
        return out

    def contributions(self, frame: pd.DataFrame) -> np.ndarray:
        """Per-feature additive contributions to the median delta (LightGBM TreeSHAP) + bias last."""
        return self.median.predict(self._x(frame), pred_contrib=True)


def _fit_ols(train: pd.DataFrame) -> Pipeline:
    numeric = ["tyre_age_next", "laps_remaining"]
    model = Pipeline([("pre", ColumnTransformer([
        ("num", Pipeline([("fill", SimpleImputer(strategy="median", keep_empty_features=True))]), numeric),
        ("cat", OneHotEncoder(handle_unknown="ignore"), ["compound_next"])])),
        ("ols", LinearRegression())])
    return model.fit(train[numeric + ["compound_next"]], train[TARGET])


def _fit_ridge(train: pd.DataFrame) -> Pipeline:
    numeric, categorical = _columns()
    return Pipeline([("pre", _prep(numeric, categorical)), ("ridge", Ridge(alpha=30.0))]).fit(
        train[numeric + categorical], train[TARGET])


def prepare(frame: pd.DataFrame) -> pd.DataFrame:
    assert_no_forbidden_columns(ds.NUMERIC + ds.CATEGORICAL, ds.FORBIDDEN_AS_FEATURES)
    frame = frame.dropna(subset=["delta_seconds", "anchor_seconds"]).copy()
    frame["race_start"] = pd.to_datetime(frame["race_start"])
    return frame.sort_values(["race_start", "driver_number", "lap"]).reset_index(drop=True)


def walk_forward(frame: pd.DataFrame, *, min_train: int = MIN_TRAIN_RACES, step: int = STEP,
                 ablations: bool = True, seeds: tuple[int, ...] = (42, 7, 123)) -> dict:
    races = frame.groupby("race_id", as_index=False)["race_start"].first()
    folds = chronological_group_folds(races, group_col="race_id", time_col="race_start",
                                      min_train=min_train, step=step)
    pieces, timings, ablation_rows, seed_rows = [], {"fit_s": {}, "predict_ms_per_row": {}}, [], []
    contributions = []
    for fold, (train_ids, test_ids) in enumerate(folds):
        train_all = frame[frame.race_id.isin(train_ids)]
        test = frame[frame.race_id.isin(test_ids)]
        assert_disjoint_groups(train_ids, test_ids, name="race")
        assert_chronological(train_all["race_start"].tolist(), test["race_start"].tolist())
        train = train_all[train_all.eligible_green_next]
        if train.empty or test.empty:
            continue
        preds = {"anchor_median3": np.zeros(len(test)),
                 "persistence_last_lap": np.nan_to_num(test["last1"].to_numpy(float), nan=0.0)}
        t = time.perf_counter()
        ols = _fit_ols(train)
        timings["fit_s"].setdefault("fuel_tyre_ols", []).append(time.perf_counter() - t)
        preds["fuel_tyre_ols"] = ols.predict(test[["tyre_age_next", "laps_remaining", "compound_next"]])
        t = time.perf_counter()
        ridge = _fit_ridge(train)
        timings["fit_s"].setdefault("ridge", []).append(time.perf_counter() - t)
        numeric, categorical = _columns()
        preds["ridge"] = ridge.predict(test[numeric + categorical])
        t = time.perf_counter()
        bundle = LgbmBundle(numeric, categorical).fit(train, train[TARGET].to_numpy())
        timings["fit_s"].setdefault("lightgbm", []).append(time.perf_counter() - t)
        t = time.perf_counter()
        out = bundle.predict(test)
        timings["predict_ms_per_row"].setdefault("lightgbm", []).append(
            (time.perf_counter() - t) * 1000 / len(test))
        preds["lightgbm"], low, high = out["median"], out["q10"], out["q90"]
        contrib = bundle.contributions(test)
        contributions.append(pd.DataFrame(contrib, columns=numeric + categorical + ["bias"], index=test.index)
                             .add_prefix("c_"))
        if ablations:
            for name, cols in GROUPS.items():
                n, c = _columns(drop=cols)
                p = LgbmBundle(n, c, quantiles=False).fit(train, train[TARGET].to_numpy()).predict(test)["median"]
                ablation_rows.append(pd.DataFrame({"fold": fold, "ablation": f"minus_{name}",
                                                   "race_id": test.race_id.to_numpy(),
                                                   "eligible": test.eligible_green_next.to_numpy(),
                                                   "abs_err": np.abs(test[TARGET].to_numpy() - p)}))
            n, c = _columns(identity=True)
            p = LgbmBundle(n, c, quantiles=False).fit(train, train[TARGET].to_numpy()).predict(test)["median"]
            ablation_rows.append(pd.DataFrame({"fold": fold, "ablation": "plus_identity",
                                               "race_id": test.race_id.to_numpy(),
                                               "eligible": test.eligible_green_next.to_numpy(),
                                               "abs_err": np.abs(test[TARGET].to_numpy() - p)}))
            for seed in seeds:
                p = LgbmBundle(numeric, categorical, seed=seed, quantiles=False).fit(
                    train, train[TARGET].to_numpy()).predict(test)["median"]
                seed_rows.append(pd.DataFrame({"fold": fold, "seed": seed, "race_id": test.race_id.to_numpy(),
                                               "eligible": test.eligible_green_next.to_numpy(),
                                               "abs_err": np.abs(test[TARGET].to_numpy() - p)}))
        base = test[["race_id", "year", "circuit", "event", "driver_number", "lap", "compound_next",
                     "regime_next", "eligible_green_next", "anchor_seconds", "next_lap_seconds",
                     "tyre_age_next"]].copy()
        for model, delta in preds.items():
            piece = base.assign(model=model, fold=fold, pred_seconds=test["anchor_seconds"].to_numpy() + delta)
            if model == "lightgbm":
                piece["q10_seconds"] = test["anchor_seconds"].to_numpy() + low
                piece["q90_seconds"] = test["anchor_seconds"].to_numpy() + high
            pieces.append(piece)
    predictions = pd.concat(pieces, ignore_index=True)
    return {"predictions": predictions,
            "contributions": pd.concat(contributions) if contributions else pd.DataFrame(),
            "ablations": pd.concat(ablation_rows, ignore_index=True) if ablation_rows else pd.DataFrame(),
            "seeds": pd.concat(seed_rows, ignore_index=True) if seed_rows else pd.DataFrame(),
            "timings": {k: {m: float(np.mean(v)) for m, v in d.items()} for k, d in timings.items()},
            "folds": len(folds), "train_races_first_fold": min_train}


def summarise(predictions: pd.DataFrame, ablations: pd.DataFrame, seeds: pd.DataFrame) -> dict:
    p = predictions.assign(err=predictions.pred_seconds - predictions.next_lap_seconds)
    p["abs_err"] = p.err.abs()
    green = p[p.eligible_green_next]
    table = green.groupby("model").agg(n=("err", "size"), mae=("abs_err", "mean"),
                                       rmse=("err", lambda e: float(np.sqrt((e ** 2).mean()))),
                                       median_ae=("abs_err", "median")).reset_index()
    base = green[green.model == "anchor_median3"].set_index(["race_id", "driver_number", "lap"])["abs_err"]
    deltas = []
    for model in table.model:
        if model == "anchor_median3":
            continue
        cand = green[green.model == model].set_index(["race_id", "driver_number", "lap"])["abs_err"]
        joined = pd.concat([cand.rename("a"), base.rename("b")], axis=1, join="inner")
        out = metrics.cluster_bootstrap_delta(joined.a.to_numpy(), joined.b.to_numpy(),
                                              joined.index.get_level_values(0).to_numpy())
        deltas.append({"model": model, "vs": "anchor_median3", **out})
    gl = green[green.model == "lightgbm"]
    coverage = {"nominal": 0.8,
                "empirical": metrics.interval_coverage(gl.next_lap_seconds, gl.q10_seconds, gl.q90_seconds),
                "mean_width_s": float((gl.q90_seconds - gl.q10_seconds).mean())}
    slices = {}
    for key in ("compound_next", "regime_next"):
        sub = p[p.model.isin(["anchor_median3", "lightgbm"])]
        slices[key] = sub.groupby([key, "model"]).agg(n=("abs_err", "size"), mae=("abs_err", "mean")) \
            .reset_index().to_dict("records")
    slices["circuit"] = green[green.model.isin(["anchor_median3", "lightgbm"])] \
        .groupby(["circuit", "model"]).abs_err.mean().unstack().assign(n=green[green.model == "lightgbm"]
        .groupby("circuit").size()).reset_index().to_dict("records")
    out = {"green_table": table.to_dict("records"), "paired_vs_anchor": deltas, "interval": coverage,
           "slices": slices, "green_rows": len(green[green.model == "lightgbm"]),
           "races_scored": int(green.race_id.nunique())}
    if len(ablations):
        full = green[green.model == "lightgbm"].set_index(["race_id", "driver_number", "lap"])["abs_err"]
        rows = []
        for name, group in ablations[ablations.eligible].groupby("ablation"):
            rows.append({"ablation": name, "mae": float(group.abs_err.mean()),
                         "delta_vs_full": float(group.abs_err.mean() - full.mean())})
        out["ablations"] = rows
        sg = seeds[seeds.eligible].groupby("seed").abs_err.mean()
        out["seed_variability"] = {"seeds": [int(s) for s in sg.index], "mae": [float(v) for v in sg.values],
                                   "std": float(sg.std(ddof=0))}
    return out


def final_model(frame: pd.DataFrame) -> tuple[LgbmBundle, pd.DataFrame]:
    train = frame[frame.eligible_green_next]
    numeric, categorical = _columns()
    return LgbmBundle(numeric, categorical).fit(train, train[TARGET].to_numpy()), train


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", type=int, nargs="+", default=[2023, 2024, 2025, 2026])
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--no-ablations", action="store_true")
    args = parser.parse_args()
    raw, coverage = ds.build_dataset(args.years)
    frame = prepare(raw)
    args.out.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(args.out / "pace_frame.parquet", index=False)
    (args.out / "coverage.json").write_text(json.dumps(coverage, indent=2, default=str))
    result = walk_forward(frame, ablations=not args.no_ablations)
    predictions = result["predictions"]
    predictions.to_parquet(args.out / "predictions.parquet", index=False)
    contrib = result["contributions"]
    if len(contrib):
        contrib.assign(race_id=frame.loc[contrib.index, "race_id"], driver_number=frame.loc[contrib.index, "driver_number"],
                       lap=frame.loc[contrib.index, "lap"]).to_parquet(args.out / "contributions.parquet")
    summary = summarise(predictions, result["ablations"], result["seeds"])
    summary["timings"] = result["timings"]
    summary["dataset"] = {"rows": len(frame), "races": int(frame.race_id.nunique()),
                          "fingerprint": fingerprint_frame(frame[ds.NUMERIC + ds.CATEGORICAL + [TARGET]])}
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2, default=float))
    bundle, train = final_model(frame)
    card = ModelCard(
        model_id="race_pace_lightgbm", version="1", task="next-lap pace forecast (green-flag clean laps)",
        target="delta_seconds = lap(L+1) - median of last 3 clean laps", dataset_fingerprint=summary["dataset"]["fingerprint"],
        dataset_rows=len(train), features=ds.FEATURES,
        split=SplitSpec(policy="expanding-window chronological by race", train_groups=int(train.race_id.nunique()),
                        test_groups=summary["races_scored"], group_key="race_id",
                        notes="Served model is fitted on all races; UI shows out-of-fold forecasts instead."),
        hyperparameters={**LGBM_PARAMS, "objective": "l1 + quantile 0.1/0.9"}, seed=SEED,
        metrics={"green_table": summary["green_table"], "interval": summary["interval"]},
        dependencies=dependency_versions("lightgbm", "scikit-learn", "pandas", "numpy"),
        data_license="OpenF1 data; CC BY-NC-SA 4.0 terms of the OpenF1 project (non-commercial); raw data not redistributed",
        data_provenance="OpenF1 API v1 laps/stints/weather/race_control/intervals, 2023-2026 Race sessions",
        limitations=["Trained and scored on green-flag clean laps only", "Fuel mass is not observed",
                     "Tyre compound/age at L+1 are scenario inputs", "2026 regulation change = domain shift"],
        intended_use="Historical research and Strategy Lab comparison; not a live decision system",
        created_at_utc=now_utc())
    hashes = save_artifact(ARTIFACTS, "race_pace_lightgbm", bundle, card)
    summary["artifact"] = hashes
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2, default=float))
    print(pd.DataFrame(summary["green_table"]).to_string(index=False))
    print(json.dumps(summary["paired_vs_anchor"], indent=1)[:1500])
    print(summary["interval"], summary.get("ablations"), summary.get("seed_variability"))


if __name__ == "__main__":
    main()
