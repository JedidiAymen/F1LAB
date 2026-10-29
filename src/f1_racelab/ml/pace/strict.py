"""Strict decision-time protocol for next-lap pace.

The conditional benchmark (`benchmark.py`) answers "given lap L+1 is a clean green lap and its tyre is known,
how well is its time predicted?". That selects rows using the *outcome* of L+1 and feeds the tyre of L+1 (which
reveals a pit stop). This module answers the deployable question instead:

* Population: every (driver, lap L) whose decision-time state is calm (no neutralisation in the last 3 laps,
  no yellow on lap L). Nothing about lap L+1 is used to select rows.
* Features: only information available at the end of lap L. Tyre inputs are "as if the car stays out":
  compound and stint of lap L, age of lap L plus one.
* Targets: every realised outcome, including out-laps, in-laps and neutralisations, scored with absolute error
  (also reported as median absolute error because the tails are heavy).
* Training uses the same decision-time population, L1 loss, earlier races only.

Command: ``uv run python -m f1_racelab.ml.pace.strict``.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from f1_racelab.ml.common import metrics
from f1_racelab.ml.common.guards import (
    assert_chronological,
    assert_disjoint_groups,
    chronological_group_folds,
)
from f1_racelab.ml.pace import dataset as ds
from f1_racelab.ml.pace.benchmark import MIN_TRAIN_RACES, STEP, TARGET
from f1_racelab.ml.pace.bundle import LgbmBundle

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "data/processed/race_pace"
MODELS = ("lightgbm", "persistence", "persistence_rule", "anchor")
SCENARIO = ("compound_next", "stint_number_next", "tyre_age_next")


def decision_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Rebuild tyre inputs from lap L only and keep the calm-at-decision-time population."""
    f = frame.sort_values(["race_id", "driver_number", "lap"]).copy()
    g = f.groupby(["race_id", "driver_number"], sort=False)
    consecutive = g["lap"].shift(1).eq(f["lap"] - 1)
    f["just_pitted"] = g["next_is_in_lap"].shift(1).fillna(False).astype(bool)  # lap L was an in-lap: known at L
    for col in SCENARIO:
        f[f"{col}_scenario"] = f[col]            # keep the L+1 value for the leakage comparison only
        f[col] = g[col].shift(1)
    f["tyre_age_next"] = f["tyre_age_next"] + 1
    f = f[consecutive & f["compound_next"].notna()]
    calm = f["neutral_in_last3"].eq(0) & f["yellow_in_last1"].eq(0)
    f = f[calm].copy()
    f["outcome"] = np.select([f.next_is_out_lap, f.next_is_in_lap, f.eligible_green_next],
                             ["out_lap", "in_lap", "green_clean"], default=f["regime_next"])
    return f


def walk_forward(frame: pd.DataFrame, *, min_train: int = MIN_TRAIN_RACES, step: int = STEP) -> pd.DataFrame:
    races = frame.groupby("race_id", as_index=False)["race_start"].first()
    numeric = [c for c in ds.NUMERIC if c not in ("laps_in_stint_next",)]
    rows = []
    for fold, (train_ids, test_ids) in enumerate(chronological_group_folds(
            races, group_col="race_id", time_col="race_start", min_train=min_train, step=step)):
        assert_disjoint_groups(train_ids, test_ids, name="race")
        train, test = frame[frame.race_id.isin(train_ids)], frame[frame.race_id.isin(test_ids)]
        assert_chronological(train["race_start"].tolist(), test["race_start"].tolist())
        if train.empty or test.empty:
            continue
        model = LgbmBundle(numeric, ds.CATEGORICAL, quantiles=False).fit(train, train[TARGET].to_numpy())
        pred = model.predict(test)["median"]
        persistence = np.nan_to_num(test["last1"].to_numpy(float), nan=0.0)
        # Fair baseline: persistence, except right after an in-lap, where the next lap is an out-lap; there
        # predict the training median delta of such rows (a rule any pit-wall tool has at decision time).
        pitted_train = train["just_pitted"]
        fill = float(train.loc[pitted_train, TARGET].median()) if pitted_train.any() else 0.0
        rule = np.where(test["just_pitted"].to_numpy(), fill, persistence)
        rows.append(pd.DataFrame({
            "fold": fold, "race_id": test.race_id.to_numpy(), "year": test.year.to_numpy(),
            "outcome": test.outcome.to_numpy(), "truth": test[TARGET].to_numpy(),
            "lightgbm": pred, "persistence": persistence, "persistence_rule": rule, "anchor": 0.0}))
    return pd.concat(rows, ignore_index=True)


def summarise(pred: pd.DataFrame) -> dict:
    err = {m: (pred.truth - pred[m]).abs() for m in MODELS}
    boot = {name: metrics.cluster_bootstrap_delta(err["lightgbm"].to_numpy()[mask], err[base].to_numpy()[mask],
                                                  pred.race_id.to_numpy()[mask], draws=10_000)
            for name, base, mask in (
                ("vs_persistence", "persistence", np.ones(len(pred), bool)),
                ("vs_persistence_rule", "persistence_rule", np.ones(len(pred), bool)),
                ("vs_persistence_rule_green_clean_only", "persistence_rule", (pred.outcome == "green_clean").to_numpy()),
                ("vs_persistence_rule_excluding_out_laps", "persistence_rule", (pred.outcome != "out_lap").to_numpy()))}
    by_outcome = {name: {"n": len(part), **{m: float((part.truth - part[m]).abs().mean())
                                                  for m in MODELS}}
                  for name, part in pred.groupby("outcome")}
    return {"rows": len(pred), "races": int(pred.race_id.nunique()),
            "mae": {m: float(e.mean()) for m, e in err.items()},
            "median_abs_error": {m: float(e.median()) for m, e in err.items()},
            "paired": boot, "by_outcome": by_outcome,
            "by_year": {int(y): {m: float((part.truth - part[m]).abs().mean()) for m in ("lightgbm", "persistence", "persistence_rule")}
                        for y, part in pred.groupby("year")}}


def main() -> None:
    frame = pd.read_parquet(OUT / "pace_frame.parquet")
    strict = decision_frame(frame)
    pred = walk_forward(strict)
    report = summarise(pred)
    report["population"] = {"decision_rows": len(strict), "of_total_rows": len(frame),
                            "share_unusual_outcome": float((strict.outcome != "green_clean").mean())}
    (OUT / "strict_protocol.json").write_text(json.dumps(report, indent=2, default=float))
    print(json.dumps(report, indent=1, default=float))


if __name__ == "__main__":
    main()
