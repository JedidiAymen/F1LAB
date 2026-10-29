"""Scientific audit of the race-pace benchmark, computed from saved out-of-fold predictions.

A. LightGBM vs the strongest baseline (last-lap persistence), race-clustered.
C. Interval calibration: coverage by slice, pinball loss, and chronological conformalized
   quantile regression (CQR) where fold *k* is corrected with residual scores from folds < *k* only.
E. Per-season skill (incl. the 2026 regulation change).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from f1_racelab.ml.common import metrics

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "data/processed/race_pace"
TARGET_COVERAGE = 0.8


def _green(predictions: pd.DataFrame) -> pd.DataFrame:
    return predictions[predictions.eligible_green_next].copy()


def compare_to_persistence(predictions: pd.DataFrame) -> dict:
    green = _green(predictions)
    key = ["race_id", "driver_number", "lap"]
    err = {m: (g.set_index(key).pred_seconds - g.set_index(key).next_lap_seconds).abs()
           for m, g in green.groupby("model")}
    joined = pd.concat([err["lightgbm"].rename("lgbm"), err["persistence_last_lap"].rename("pers")], axis=1,
                       join="inner").reset_index()
    boot = metrics.cluster_bootstrap_delta(joined.lgbm.to_numpy(), joined.pers.to_numpy(),
                                           joined.race_id.to_numpy(), draws=10_000)
    per_race = joined.groupby("race_id")[["lgbm", "pers"]].mean()
    per_race["delta"] = per_race.lgbm - per_race.pers
    meta = green.drop_duplicates("race_id").set_index("race_id")[["year", "event"]]
    per_race = per_race.join(meta)
    by_year = per_race.groupby("year").agg(races=("delta", "size"), lgbm=("lgbm", "mean"), pers=("pers", "mean"),
                                           share_lgbm_better=("delta", lambda d: float((d < 0).mean())))
    worst = per_race.sort_values("delta", ascending=False).head(5)
    return {"n_laps": len(joined), "mae_lgbm": float(joined.lgbm.mean()), "mae_persistence": float(joined.pers.mean()),
            "abs_diff": boot["mean_delta"], "relative_diff": boot["mean_delta"] / float(joined.pers.mean()),
            "ci": [boot["ci_low"], boot["ci_high"]], "races": boot["clusters"],
            "share_races_lgbm_better": float((per_race.delta < 0).mean()),
            "per_race_delta_quantiles": {str(q): float(per_race.delta.quantile(q)) for q in (0.05, 0.25, 0.5, 0.75, 0.95)},
            "by_year": by_year.reset_index().to_dict("records"),
            "worst_races_for_lgbm": worst.reset_index()[["event", "year", "delta"]].to_dict("records")}


def cqr_calibrate(predictions: pd.DataFrame, target: float = TARGET_COVERAGE) -> pd.DataFrame:
    """Add chronologically conformalized interval columns to LightGBM green rows.

    Folds are processed in order. The correction for fold k is the finite-sample quantile of
    CQR scores max(q10 - y, y - q90) over green rows of folds < k; the first fold is uncalibrated.
    """
    lgbm = predictions[(predictions.model == "lightgbm")].copy()
    lgbm["score"] = np.maximum(lgbm.q10_seconds - lgbm.next_lap_seconds, lgbm.next_lap_seconds - lgbm.q90_seconds)
    lgbm["cal_q10"], lgbm["cal_q90"] = lgbm.q10_seconds, lgbm.q90_seconds
    lgbm["calibrated"] = False
    seen: list[np.ndarray] = []
    for fold in sorted(lgbm.fold.unique()):
        mask = lgbm.fold == fold
        if seen:
            scores = np.concatenate(seen)
            level = min(1.0, target * (1 + 1 / len(scores)))
            q_hat = float(np.quantile(scores, level))
            lgbm.loc[mask, "cal_q10"] = lgbm.loc[mask, "q10_seconds"] - q_hat
            lgbm.loc[mask, "cal_q90"] = lgbm.loc[mask, "q90_seconds"] + q_hat
            lgbm.loc[mask, "calibrated"] = True
        seen.append(lgbm.loc[mask & lgbm.eligible_green_next, "score"].to_numpy())
    return lgbm


def interval_report(predictions: pd.DataFrame) -> dict:
    cal = cqr_calibrate(predictions)
    green = cal[cal.eligible_green_next]
    scored = green[green.calibrated]

    def cov(frame, lo, hi):
        return metrics.interval_coverage(frame.next_lap_seconds, frame[lo], frame[hi])

    def pinball_pair(frame, lo, hi):
        return (metrics.pinball(frame.next_lap_seconds, frame[lo], 0.1) + metrics.pinball(frame.next_lap_seconds, frame[hi], 0.9)) / 2

    slices = {}
    for name in ("year", "compound_next", "regime_next"):
        pool = cal[cal.calibrated] if name == "regime_next" else scored
        rows = []
        for value, part in pool.groupby(name):
            if len(part) < 200:
                continue
            rows.append({"value": str(value), "n": len(part), "raw_coverage": cov(part, "q10_seconds", "q90_seconds"),
                         "cqr_coverage": cov(part, "cal_q10", "cal_q90"),
                         "raw_width": float((part.q90_seconds - part.q10_seconds).mean()),
                         "cqr_width": float((part.cal_q90 - part.cal_q10).mean())})
        slices[name] = rows
    per_race = scored.groupby("race_id").apply(lambda g: pd.Series({"raw": cov(g, "q10_seconds", "q90_seconds"),
                                                                    "cqr": cov(g, "cal_q10", "cal_q90")}), include_groups=False)
    return {"target": TARGET_COVERAGE, "calibrated_rows": len(scored),
            "raw": {"coverage": cov(scored, "q10_seconds", "q90_seconds"), "pinball": pinball_pair(scored, "q10_seconds", "q90_seconds"),
                    "width": float((scored.q90_seconds - scored.q10_seconds).mean())},
            "cqr": {"coverage": cov(scored, "cal_q10", "cal_q90"), "pinball": pinball_pair(scored, "cal_q10", "cal_q90"),
                    "width": float((scored.cal_q90 - scored.cal_q10).mean())},
            "per_race_coverage_quantiles": {m: {str(q): float(per_race[m].quantile(q)) for q in (0.1, 0.5, 0.9)} for m in ("raw", "cqr")},
            "slices": slices}


def season_skill(predictions: pd.DataFrame) -> list[dict]:
    green = _green(predictions)
    green = green.assign(abs_err=(green.pred_seconds - green.next_lap_seconds).abs())
    table = green.groupby(["year", "model"]).abs_err.mean().unstack()
    table["n_laps"] = green[green.model == "lightgbm"].groupby("year").size()
    table["races"] = green[green.model == "lightgbm"].groupby("year").race_id.nunique()
    return table.reset_index().to_dict("records")


def run(root: Path = OUT) -> dict:
    predictions = pd.read_parquet(root / "predictions.parquet")
    report = {"vs_persistence": compare_to_persistence(predictions), "intervals": interval_report(predictions),
              "season_skill": season_skill(predictions)}
    (root / "audit.json").write_text(json.dumps(report, indent=2, default=float))
    return report


if __name__ == "__main__":
    r = run()
    v = r["vs_persistence"]
    print(json.dumps({k: v[k] for k in ("n_laps", "mae_lgbm", "mae_persistence", "abs_diff", "relative_diff", "ci", "races", "share_races_lgbm_better")}, indent=1))
    print(json.dumps(v["by_year"], indent=1)); print(json.dumps(r["intervals"]["raw"]), json.dumps(r["intervals"]["cqr"]))
    for k in ("year", "compound_next", "regime_next"):
        print(k, [(s["value"], s["n"], round(s["raw_coverage"], 3), round(s["cqr_coverage"], 3)) for s in r["intervals"]["slices"][k]])
    print(json.dumps(r["season_skill"], default=float, indent=1))
