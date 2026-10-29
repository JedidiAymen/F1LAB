import numpy as np
import pandas as pd

from f1_racelab.ml.pace import audit


def _frame(seed=0, folds=4, per_fold=400):
    rng = np.random.default_rng(seed)
    rows = []
    for fold in range(folds):
        y = rng.normal(90, 1, per_fold)
        for model, noise in (("lightgbm", 0.5), ("persistence_last_lap", 0.8)):
            pred = y + rng.normal(0, noise, per_fold)
            rows.append(pd.DataFrame({
                "model": model, "fold": fold, "race_id": [f"r{fold}_{i % 5}" for i in range(per_fold)],
                "driver_number": np.arange(per_fold) % 20, "lap": np.arange(per_fold) // 20,
                "year": 2024, "event": "x", "next_lap_seconds": y, "pred_seconds": pred,
                "q10_seconds": pred - 0.3, "q90_seconds": pred + 0.3, "eligible_green_next": True,
                "compound_next": "HARD", "regime_next": "green"}))
    return pd.concat(rows, ignore_index=True)


def test_persistence_comparison_detects_better_model():
    result = audit.compare_to_persistence(_frame())
    assert result["abs_diff"] < 0 and result["ci"][1] < 0
    assert result["races"] == 20


def test_cqr_uses_only_earlier_folds_and_widens_overconfident_intervals():
    cal = audit.cqr_calibrate(_frame())
    first = cal[cal.fold == 0]
    assert not first.calibrated.any() and (first.cal_q10 == first.q10_seconds).all()
    later = cal[cal.fold > 0]
    assert later.calibrated.all() and (later.cal_q90 - later.cal_q10 > later.q90_seconds - later.q10_seconds).all()


def test_cqr_reaches_nominal_coverage():
    report = audit.interval_report(_frame())
    assert report["raw"]["coverage"] < 0.6
    assert abs(report["cqr"]["coverage"] - 0.8) < 0.05
