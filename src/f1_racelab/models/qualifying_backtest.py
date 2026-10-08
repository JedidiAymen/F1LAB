"""Leakage-conscious event-grouped qualifying baselines.

We predict Q1 relative pace as a transparent proxy for qualifying potential,
then sort model scores *within each Grand Prix* to compare final classification.
This is deliberately NOT yet a full Q1/Q2/Q3 simulator.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from scipy.stats import spearmanr
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_FILE = PROJECT_ROOT / "data/processed/qualifying_2022_2023_2024_2025.parquet"
RESULT_DIR = PROJECT_ROOT / "data/processed/qualifying_backtest"

# Every feature below can exist before the weekend qualifying session.
# Qualifying targets, Q1/Q2/Q3 times, and 'final_position' are NEVER in this list.
FEATURES = [
    "fp1_gap_pct", "fp2_gap_pct", "fp3_gap_pct",
    "fp1_rank", "fp2_rank", "fp3_rank",
    "fp1_representative_laps", "fp2_representative_laps", "fp3_representative_laps",
    "fp1_best_vs_theoretical", "fp2_best_vs_theoretical", "fp3_best_vs_theoretical",
    "fp1_best_tyre_life", "fp2_best_tyre_life", "fp3_best_tyre_life",
    "fp1_best_speed_trap", "fp2_best_speed_trap", "fp3_best_speed_trap",
    "fp1_to_fp3_improvement_pct", "fp2_to_fp3_improvement_pct",
    "fp1_top3_gap_pct", "fp2_top3_gap_pct", "fp3_top3_gap_pct",
    "fp1_soft_gap_pct", "fp2_soft_gap_pct", "fp3_soft_gap_pct",
    "fp1_theoretical_gap_pct", "fp2_theoretical_gap_pct", "fp3_theoretical_gap_pct",
]
CATEGORICAL = ["driver", "event"]
TARGET = "q1_gap_pct"
LABEL = "final_position"
GROUP = ["year", "round"]


def prepare_dataset(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    needed = set(FEATURES[:3] + [TARGET, LABEL, "driver", "event", "year", "round", "fp3_best_seconds"])
    missing = needed - set(df.columns)
    if missing:
        raise ValueError(f"Missing required source columns: {sorted(missing)}")
    if df.duplicated(["year", "round", "driver"]).any():
        raise ValueError("Duplicate driver row within weekend")
    # Derived PRACTICE-only features. Never compute normalization over the
    # entire dataset: it would mix different circuits and future weekends.
    for prefix in ("fp1", "fp2", "fp3"):
        for name, col in [
            ("top3_gap_pct", f"{prefix}_top3_median_seconds"),
            ("soft_gap_pct", f"{prefix}_soft_best_seconds"),
            ("theoretical_gap_pct", f"{prefix}_theoretical_best_seconds"),
        ]:
            if col not in df.columns:
                df[f"{prefix}_{name}"] = np.nan
                continue
            fastest = df.groupby(GROUP)[col].transform("min")
            df[f"{prefix}_{name}"] = (pd.to_numeric(df[col], errors="coerce") / fastest - 1.0) * 100.0
    for field in FEATURES:
        if field not in df.columns:
            df[field] = np.nan
        df[field] = pd.to_numeric(df[field], errors="coerce")
        df[field] = df[field].replace([np.inf, -np.inf], np.nan)
    for field in [TARGET, LABEL, "fp3_best_seconds"]:
        df[field] = pd.to_numeric(df[field], errors="coerce")
    df["year"] = pd.to_numeric(df["year"], errors="raise").astype(int)
    df["round"] = pd.to_numeric(df["round"], errors="raise").astype(int)
    # Restrict evaluation to participants with BOTH measured FP3 pace and
    # Q1 time. Everyone gets the same set of evaluated participants.
    df = df.dropna(subset=[TARGET, LABEL, "fp3_best_seconds"]).copy()
    df = df.loc[(df[LABEL] > 0) & (df[TARGET] >= 0)].copy()
    if df.empty:
        raise ValueError("No driver rows have both FP3 and Q1 times")
    return df.sort_values(GROUP + [LABEL], kind="stable").reset_index(drop=True)


def model_pipelines() -> dict[str, Pipeline]:
    def prep():
        return ColumnTransformer([
            ("num", Pipeline([("fill", SimpleImputer(strategy="median", keep_empty_features=True)), ("scale", StandardScaler())]), FEATURES),
            ("cat", Pipeline([("fill", SimpleImputer(strategy="most_frequent")), ("encode", OneHotEncoder(handle_unknown="ignore"))]), CATEGORICAL),
        ])
    return {
        "ridge": Pipeline([("features", prep()), ("model", Ridge(alpha=20.0))]),
        "lightgbm": Pipeline([("features", prep()), ("model", LGBMRegressor(
            n_estimators=150, learning_rate=0.035, num_leaves=12,
            min_child_samples=25, reg_lambda=5.0,
            verbosity=-1, random_state=42, n_jobs=2,
        ))]),
    }


def add_ranks(group: pd.DataFrame) -> pd.DataFrame:
    out = group.copy()
    out["predicted_rank"] = out["predicted_score"].rank(method="first", ascending=True).astype(int)
    out["actual_rank"] = out[LABEL].rank(method="first", ascending=True).astype(int)
    return out


def scored_positions(df: pd.DataFrame, scores: np.ndarray | pd.Series, model: str) -> pd.DataFrame:
    result = df[GROUP + ["event", "driver", LABEL, TARGET]].copy()
    result["model"] = model
    result["predicted_score"] = np.asarray(scores, dtype=float)
    if not np.isfinite(result["predicted_score"]).all():
        raise ValueError(f"Non-finite predictions from {model}")
    result = result.sort_values(GROUP + ["predicted_score", "driver"], kind="stable")
    result["predicted_rank"] = result.groupby(GROUP)["predicted_score"].rank(method="first").astype(int)
    result["actual_rank"] = result.groupby(GROUP)[LABEL].rank(method="first").astype(int)
    return result


def evaluate(predictions: pd.DataFrame) -> pd.DataFrame:
    records = []
    for (model, year, round_no), part in predictions.groupby(["model", "year", "round"], sort=True):
        if len(part) < 5:
            continue
        p = part["predicted_rank"].to_numpy()
        a = part["actual_rank"].to_numpy()
        rho = spearmanr(a, p).statistic
        records.append({
            "model": model, "year": int(year), "round": int(round_no),
            "event": part["event"].iloc[0], "drivers": len(part),
            "position_mae": float(np.abs(p-a).mean()),
            "spearman": float(rho),
            "pole_hit": int(part.loc[part["actual_rank"] == 1, "predicted_rank"].iloc[0] == 1),
            "top3_overlap": float(len(set(part.loc[part["actual_rank"] <= 3, "driver"]) & set(part.loc[part["predicted_rank"] <= 3, "driver"])) / 3.0),
        })
    return pd.DataFrame(records)


def run_backtest(dataset: pd.DataFrame, train_years=(2022, 2023), val_year=2024, test_year=2025):
    data = prepare_dataset(dataset)
    train = data.loc[data["year"].isin(train_years)].copy()
    validation = data.loc[data["year"] == val_year].copy()
    test = data.loc[data["year"] == test_year].copy()
    if min(len(train), len(validation), len(test)) == 0:
        raise ValueError("Need populated train, validation and test years; inspect ingestion report")
    if train[GROUP].drop_duplicates().shape[0] < 8 or validation[GROUP].drop_duplicates().shape[0] < 5 or test[GROUP].drop_duplicates().shape[0] < 5:
        raise ValueError("Need at least 8 training weekends and 5 validation/test weekends; smoke datasets are not valid backtests")
    xcols = FEATURES + CATEGORICAL
    models = model_pipelines()
    for name, model in models.items():
        model.fit(train[xcols], train[TARGET])

    def predictions(part: pd.DataFrame, suffix: str) -> pd.DataFrame:
        pieces = [scored_positions(part, part["fp3_best_seconds"].to_numpy(), "fp3")]
        for name, model in models.items():
            pieces.append(scored_positions(part, model.predict(part[xcols]), name))
        combined = pd.concat(pieces, ignore_index=True)
        combined["split"] = suffix
        return combined

    val_predictions = predictions(validation, "validation")
    val_by_event = evaluate(val_predictions)
    if val_by_event.empty:
        raise ValueError("No valid validation weekends")
    val_summary = (val_by_event.groupby("model", as_index=False)
                   .agg(events=("round", "count"), position_mae=("position_mae", "mean"),
                        spearman=("spearman", "mean"), pole_hit_rate=("pole_hit", "mean"), top3_overlap=("top3_overlap", "mean")))
    # Pick the winner on VALIDATION ONLY, including FP3. Do not look at 2025
    # results to decide which model to promote.
    winner = val_summary.sort_values(["position_mae", "model"], kind="stable").iloc[0]["model"]
    test_predictions = predictions(test, "test")
    test_by_event = evaluate(test_predictions)
    test_summary = (test_by_event.groupby("model", as_index=False)
                    .agg(events=("round", "count"), position_mae=("position_mae", "mean"),
                         spearman=("spearman", "mean"), pole_hit_rate=("pole_hit", "mean"), top3_overlap=("top3_overlap", "mean")))
    return {"winner": str(winner), "models": models, "validation_summary": val_summary,
            "test_summary": test_summary, "validation_events": val_by_event,
            "test_events": test_by_event, "predictions": pd.concat([val_predictions, test_predictions], ignore_index=True),
            "n_training_events": int(train[GROUP].drop_duplicates().shape[0]),
            "n_validation_events": int(validation[GROUP].drop_duplicates().shape[0]),
            "n_test_events": int(test[GROUP].drop_duplicates().shape[0])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DATA_FILE)
    parser.add_argument("--out", type=Path, default=RESULT_DIR)
    args = parser.parse_args()
    if not args.dataset.exists():
        parser.error(f"Missing {args.dataset}. Run python -m f1_racelab.data.qualifying_dataset first.")
    out = run_backtest(pd.read_parquet(args.dataset))
    args.out.mkdir(parents=True, exist_ok=True)
    for key in ["validation_summary", "test_summary", "validation_events", "test_events"]:
        out[key].to_csv(args.out / f"{key}.csv", index=False)
    out["predictions"].to_parquet(args.out / "predictions.parquet", index=False)
    with (args.out / "experiment.json").open("w") as fp:
        json.dump({k: out[k] for k in ["winner", "n_training_events", "n_validation_events", "n_test_events"]}, fp, indent=2)
    print("\n=== VALIDATION (2024) ===")
    print(out["validation_summary"].sort_values("position_mae").to_string(index=False))
    print("\nWinner selected using 2024 ONLY:", out["winner"])
    print("\n=== HELD-OUT TEST (2025) ===")
    print(out["test_summary"].sort_values("position_mae").to_string(index=False))
    print("\nSaved results to", args.out)


if __name__ == "__main__":
    main()
