import numpy as np
import pandas as pd

from f1_racelab.features.historical_qualifying import (
    add_historical_features,
    feature_names,
)
from f1_racelab.models.qualifying_ablation import run_ablation
from f1_racelab.models.qualifying_backtest import COMMON_FEATURES


def sample():
    rows = []
    rng = np.random.default_rng(123)
    for year in range(2022, 2026):
        for round_no in range(1, 7):
            for i in range(10):
                pace = i * 0.055 + rng.normal(0, .007)
                rows.append({"year": year, "round": round_no, "event": f"GP {round_no}",
                             "driver": f"D{i:02d}", "team": f"T{i // 2}",
                             "fp1_gap_pct": pace + .05, "fp2_gap_pct": pace + .02,
                             "fp3_gap_pct": max(0, pace), "fp3_rank": i+1,
                             "fp3_best_seconds": 80+pace,
                             "q1_gap_pct": max(0, pace + rng.normal(0, .012)),
                             "q3_seconds": 78.0 if i < 5 else np.nan,
                             "final_position": i+1})
    return pd.DataFrame(rows)


def test_first_weekend_has_no_historical_form():
    out = add_historical_features(sample())
    first = out[(out.year == 2022) & (out["round"] == 1)]
    assert first[feature_names()].isna().all().all()


def test_changing_current_labels_cannot_change_current_features():
    data = sample()
    baseline = add_historical_features(data)
    data.loc[(data.year == 2025) & (data["round"] == 3), "q1_gap_pct"] = 55.0
    after = add_historical_features(data)
    mask = (baseline.year == 2025) & (baseline["round"] == 3)
    pd.testing.assert_frame_equal(baseline.loc[mask, feature_names()].reset_index(drop=True),
                                  after.loc[mask, feature_names()].reset_index(drop=True))


def test_team_value_uses_previous_weekend_only():
    out = add_historical_features(sample())
    first_r2 = out[(out.year == 2022) & (out["round"] == 2) & (out.team == "T0")]
    assert first_r2["team_q1_gap_last_3"].notna().all()
    assert first_r2["team_q1_gap_last_3"].nunique() == 1
    first_r1 = out[(out.year == 2022) & (out["round"] == 1) & (out.team == "T0")]
    assert np.isclose(first_r2["team_q1_gap_last_3"].iloc[0], first_r1["q1_gap_pct"].mean())


def test_ablation_executes_with_temporal_splits():
    out = run_ablation(sample(), practice_features=COMMON_FEATURES)
    assert set(out["validation"].model) == {"fp3", "ridge", "lightgbm", "form_ridge", "form_lightgbm"}
    assert set(out["test"].model) == {"fp3", "ridge", "lightgbm", "form_ridge", "form_lightgbm"}
    assert out["selected_model"] in set(out["validation"].model)
    assert out["predictions"].query("split == 'test'").year.eq(2025).all()
    assert out["team_label_coverage"] == 1.0


def test_missing_team_still_allows_driver_features():
    df = sample().drop(columns="team")
    out = add_historical_features(df)
    assert out["team_q1_gap_last_3"].isna().all()
    assert out["driver_q1_gap_last_3"].notna().any()
