import numpy as np
import pandas as pd
import pytest

from f1_racelab.models.qualifying_backtest import (
    COMMON_FEATURES,
    FEATURES,
    evaluate,
    paired_event_bootstrap,
    prepare_dataset,
    run_backtest,
    scored_positions,
)


def fake_dataset():
    rows = []
    rng = np.random.default_rng(42)
    for year in [2022, 2023, 2024, 2025]:
        for rd in [1, 2, 3, 4, 5, 6]:
            # 10 eligible drivers each weekend; every weekend is a complete group.
            for k in range(10):
                pace = float(k) * 0.06 + rng.normal(0, 0.005)
                rows.append({
                    "year": year, "round": rd, "event": f"GP {rd}",
                    "driver": f"D{k:02}", "fp3_best_seconds": 80.0 + pace,
                    "fp3_gap_pct": pace, "fp3_rank": k + 1,
                    "fp1_gap_pct": pace + 0.04, "fp2_gap_pct": pace + 0.02,
                    "q1_gap_pct": max(0.0, pace + rng.normal(0, 0.005)),
                    "final_position": k + 1,
                    "q2_seconds": 78.0, "q3_seconds": 77.0,
                })
    return pd.DataFrame(rows)


def test_never_use_qualifying_targets_as_features():
    assert "q1_gap_pct" not in FEATURES
    assert "q2_seconds" not in FEATURES
    assert "q3_seconds" not in FEATURES
    assert "final_position" not in FEATURES
    assert "year" not in FEATURES


def test_normalization_is_within_weekend_only():
    data = fake_dataset()
    data.loc[data.year == 2025, "fp3_top3_median_seconds"] = 100.0
    data.loc[data.year != 2025, "fp3_top3_median_seconds"] = 80.0
    processed = prepare_dataset(data)
    assert (processed.fp3_top3_gap_pct == 0).all()


def test_phase_baseline_does_not_require_future_fp3_measurement():
    data = fake_dataset().assign(fp1_best_seconds=80.0)
    data.loc[data.index[:5], "fp3_best_seconds"] = np.nan
    fp1 = prepare_dataset(data, baseline_column="fp1_best_seconds")
    fp3 = prepare_dataset(data)
    assert len(fp1) == len(data)
    assert len(fp3) == len(data) - 5


def test_positions_rank_within_each_event():
    data = prepare_dataset(fake_dataset())
    sample = data.loc[data.year == 2025]
    scored = scored_positions(sample, sample.fp3_best_seconds.to_numpy(), "fp3")
    assert set(scored.groupby(["year", "round"]).size()) == {10}
    assert set(scored.loc[scored["round"] == 1, "predicted_rank"]) == set(range(1, 11))
    assert (evaluate(scored).position_mae == 0).all()


def test_season_split_and_models_execute():
    results = run_backtest(fake_dataset())
    assert results["n_training_events"] == 12
    assert results["n_validation_events"] == 6
    assert results["n_test_events"] == 6
    assert set(results["test_summary"].model) == {"fp3", "ridge", "lightgbm"}
    assert results["predictions"].query("split == 'test'").year.eq(2025).all()
    assert results["winner"] in {"fp3", "ridge", "lightgbm"}


def test_common_provider_features_execute_without_richer_lap_columns():
    data = fake_dataset().drop(columns=["q2_seconds", "q3_seconds"])
    results = run_backtest(data, feature_cols=COMMON_FEATURES)
    assert results["n_training_events"] == 12
    assert set(results["test_summary"].model) == {"fp3", "ridge", "lightgbm"}
    assert set(COMMON_FEATURES).issubset(FEATURES)


def test_bootstrap_pairs_models_by_whole_event_and_is_seeded():
    by_event = pd.DataFrame([
        {"year": 2024, "round": rd, "model": model, "position_mae": value}
        for rd, baseline, candidate in [(1, 2.0, 1.0), (2, 3.0, 2.0), (3, 4.0, 3.0)]
        for model, value in [("fp3", baseline), ("ridge", candidate)]
    ])
    first = paired_event_bootstrap(by_event, draws=200, seed=7)
    second = paired_event_bootstrap(by_event, draws=200, seed=7)
    pd.testing.assert_frame_equal(first, second)
    assert first.loc[0, "events"] == 3
    assert first.loc[0, "mean_delta"] == -1.0
    assert first.loc[0, "ci_low"] == first.loc[0, "ci_high"] == -1.0


def test_bootstrap_interval_does_not_change_when_other_model_is_added():
    events = pd.DataFrame([
        {"year": 2025, "round": rd, "model": model, "position_mae": value}
        for rd, baseline, candidate in [(1, 2.0, 1.0), (2, 3.0, 2.5), (3, 4.0, 2.0)]
        for model, value in [("fp3", baseline), ("ridge", candidate)]
    ])
    alone = paired_event_bootstrap(events, draws=200, seed=7)
    other = events.loc[events.model.eq("ridge")].assign(model="form_ridge")
    together = paired_event_bootstrap(pd.concat([events, other]), draws=200, seed=7)
    pd.testing.assert_series_equal(
        alone.loc[alone.model.eq("ridge")].iloc[0],
        together.loc[together.model.eq("ridge")].iloc[0],
        check_names=False,
    )


def test_no_duplicate_driver_rows():
    data = fake_dataset()
    with pytest.raises(ValueError, match="Duplicate"):
        prepare_dataset(pd.concat([data, data.iloc[[0]]], ignore_index=True))
