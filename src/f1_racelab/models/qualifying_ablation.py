"""Sprint 3: compare baseline models with strictly lagged driver/team form.

Selection is made only with 2024 validation events; 2025 is an untouched test.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from f1_racelab.features.historical_qualifying import (
    add_historical_features,
    feature_names,
)
from f1_racelab.models.qualifying_backtest import (
    CATEGORICAL,
    COMMON_FEATURES,
    DATA_FILE,
    FEATURES,
    TARGET,
    evaluate,
    paired_event_bootstrap,
    prepare_dataset,
    run_backtest,
    scored_positions,
)

OUT = Path(__file__).resolve().parents[3] / "data/processed/qualifying_ablation"


def _fit_form_models(data: pd.DataFrame, practice_features: list[str]):
    form_cols = feature_names()
    xcols = practice_features + form_cols + CATEGORICAL + ["team"]
    train = data.loc[data.year.isin([2022, 2023])]
    if train.empty:
        raise ValueError("No 2022–2023 training data")

    def preprocessing():
        return ColumnTransformer([
            ("num", Pipeline([
                ("fill", SimpleImputer(strategy="median", keep_empty_features=True)),
                ("scale", StandardScaler()),
            ]), practice_features + form_cols),
            ("cat", Pipeline([
                ("fill", SimpleImputer(strategy="most_frequent")),
                ("onehot", OneHotEncoder(handle_unknown="ignore")),
            ]), CATEGORICAL + ["team"]),
        ])
    models = {
        "form_ridge": Pipeline([
            ("preprocess", preprocessing()),
            ("regressor", Ridge(alpha=20.0)),
        ]),
        "form_lightgbm": Pipeline([
            ("preprocess", preprocessing()),
            ("regressor", LGBMRegressor(
                n_estimators=150, learning_rate=0.035, num_leaves=12,
                min_child_samples=25, reg_lambda=5.0,
                verbosity=-1, random_state=42, n_jobs=2,
            )),
        ]),
    }
    for model in models.values():
        model.fit(train[xcols], train[TARGET])
    return models, xcols


def _summary(predictions: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    detail = evaluate(predictions)
    summary = detail.groupby("model", as_index=False).agg(
        events=("round", "count"),
        position_mae=("position_mae", "mean"),
        spearman=("spearman", "mean"),
        pole_hit_rate=("pole_hit", "mean"),
        top3_overlap=("top3_overlap", "mean"),
    )
    return detail, summary


def run_ablation(raw: pd.DataFrame, practice_features: list[str] = FEATURES):
    # Replay Sprint 2 without changing any hyperparameters, so comparison is fair.
    old = run_backtest(raw, feature_cols=practice_features)
    enriched = add_historical_features(raw)
    prepared = prepare_dataset(enriched)
    prepared["team"] = prepared["team"].fillna("__UNKNOWN__").astype(str)
    cols = feature_names()
    for name in cols:
        prepared[name] = pd.to_numeric(prepared[name], errors="coerce").replace([np.inf, -np.inf], np.nan)
    models, xcols = _fit_form_models(prepared, practice_features)

    extra_predictions = []
    for split, yr in (("validation", 2024), ("test", 2025)):
        part = prepared.loc[prepared.year == yr]
        if part.empty:
            raise ValueError(f"Missing held-out year {yr}")
        for name, model in models.items():
            piece = scored_positions(part, model.predict(part[xcols]), name)
            piece["split"] = split
            extra_predictions.append(piece)
    predictions = pd.concat([old["predictions"], *extra_predictions], ignore_index=True)
    by_event = {}; summaries = {}
    for split in ("validation", "test"):
        by_event[split], summaries[split] = _summary(predictions[predictions.split == split])
    # Pick ONLY on 2024, not on the test table.
    selected = str(summaries["validation"].sort_values(
        ["position_mae", "model"], kind="stable"
    ).iloc[0].model)

    coverage = (prepared[cols].notna().mean().sort_values(ascending=False)
                .rename("fraction_available").reset_index().rename(columns={"index": "feature"}))
    return {"selected_model": selected, "validation": summaries["validation"],
            "test": summaries["test"], "validation_events": by_event["validation"],
            "test_events": by_event["test"], "predictions": predictions,
            "validation_bootstrap": paired_event_bootstrap(by_event["validation"]),
            "test_bootstrap": paired_event_bootstrap(by_event["test"]),
            "sample_coverage": old["sample_coverage"],
            "feature_coverage": coverage, "team_label_coverage": float((prepared.team != "__UNKNOWN__").mean())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DATA_FILE)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--feature-set", choices=("full", "common"), default="full")
    args = parser.parse_args()
    if not args.dataset.exists():
        parser.error(f"No dataset: {args.dataset}. Run the Sprint 2 ingester first.")
    practice_features = COMMON_FEATURES if args.feature_set == "common" else FEATURES
    out = run_ablation(pd.read_parquet(args.dataset), practice_features=practice_features)
    args.out.mkdir(parents=True, exist_ok=True)
    for key in ["validation", "test", "validation_events", "test_events", "feature_coverage",
                "validation_bootstrap", "test_bootstrap", "sample_coverage"]:
        out[key].to_csv(args.out / f"{key}.csv", index=False)
    out["predictions"].to_parquet(args.out / "predictions.parquet", index=False)
    (args.out / "experiment.json").write_text(json.dumps({
        "selected_model": out["selected_model"],
        "team_label_coverage": out["team_label_coverage"],
        "selection_year": 2024,
        "held_out_year": 2025,
        "feature_set": args.feature_set,
        "practice_features": practice_features,
        "dataset": str(args.dataset),
    }, indent=2))
    print("\n=== 2024 VALIDATION — choose winner here ===")
    print(out["validation"].sort_values("position_mae").to_string(index=False))
    print("Selected:", out["selected_model"])
    print("\n=== 2025 HELD-OUT TEST — NO tuning here ===")
    print(out["test"].sort_values("position_mae").to_string(index=False))
    print(f"Team metadata coverage: {out['team_label_coverage']:.1%}")
    print("Results:", args.out)

if __name__ == "__main__":
    main()
