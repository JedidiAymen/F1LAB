"""Retrospective timing-inferred order-swap dataset (OpenF1 laps/intervals, 2023-2026).

Unit: (race, cutoff lap L, follower F, leader A) where A is the car directly ahead of F by gap-to-leader at the end of
lap L and F's interval to A is at most ``MAX_INTERVAL_S``. Label: F is ahead of A at the end of lap L+1 (a
timing-inferred swap, not a verified on-track pass), **excluding** any pair where either car's laps L or L+1 were in/out laps, or where a safety car / VSC
or yellow affected L+1 or the last 3 laps (those orders change for reasons other than racing). Excluded rows are
dropped, not labelled 0.

The excluded cohort depends on later events and is not an unconditional prospective population. The leader's
cutoff must not be later than the follower's, and both next records must be consecutive. Provider publication
latency and physical position are not certified. ``circuit_rate_prior`` is the overtake rate at the same circuit
over strictly earlier races (NaN for the first visit), so no future race leaks.

Command: ``uv run python -m f1_racelab.ml.overtake.dataset``.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
PACE = ROOT / "data/processed/race_pace/pace_frame.parquet"
OUT = ROOT / "data/processed/overtake"
MAX_INTERVAL_S = 3.0
FEATURES = ["interval", "interval_trend", "pace_advantage", "tyre_age_diff", "compound_diff",
            "follower_tyre_age", "leader_tyre_age", "within_drs", "laps_remaining", "circuit_rate_prior",
            "intervals_age_s"]
COMPOUND_RANK = {"SOFT": 0, "MEDIUM": 1, "HARD": 2, "INTERMEDIATE": 3, "WET": 4}


def build(frame: pd.DataFrame) -> pd.DataFrame:
    f = frame.sort_values(["race_id", "driver_number", "lap"]).copy()
    if "cutoff" not in f or f[["race_id", "driver_number", "lap"]].isna().any().any():
        raise ValueError("Race, driver, lap and cutoff are required")
    if f.duplicated(["race_id", "driver_number", "lap"]).any():
        raise ValueError("Duplicate race/driver/lap keys")
    f["cutoff"] = pd.to_datetime(f.cutoff, utc=True, errors="coerce", format="mixed")
    if f.cutoff.isna().any():
        raise ValueError("Every source row requires a valid cutoff")
    g = f.groupby(["race_id", "driver_number"], sort=False)
    f["last_lap_seconds"] = f.anchor_seconds + f.last1
    f["interval_prev"] = g["interval_ahead"].shift(1)
    # lap L in/out flags come from the previous row's "next lap" flags
    f["lap_l_pit"] = (g["next_is_in_lap"].shift(1).fillna(False) | g["next_is_out_lap"].shift(1).fillna(False)).astype(bool)
    f["lap_l1_pit"] = (f.next_is_in_lap | f.next_is_out_lap).astype(bool)
    f["compound_rank"] = f.compound_next.map(COMPOUND_RANK)
    f["order_next"] = g["gap_to_leader"].shift(-1)       # gap at end of lap L+1 for the same driver
    f["next_record_lap"] = g["lap"].shift(-1)
    keep = ["race_id", "year", "event", "circuit", "race_start", "lap", "driver_number", "gap_to_leader",
            "interval_ahead", "interval_prev", "last_lap_seconds", "tyre_age_next", "compound_rank", "laps_remaining",
            "lap_l_pit", "lap_l1_pit", "order_next", "neutral_in_last3", "yellow_in_last1", "regime_next",
            "intervals_age_s", "anchor_seconds", "cutoff", "next_record_lap"]
    f = f[keep].dropna(subset=["gap_to_leader"])
    f["rank"] = f.groupby(["race_id", "lap"]).gap_to_leader.rank(method="first")
    leader = f.rename(columns=lambda c: f"a_{c}" if c not in ("race_id", "lap") else c)
    leader["rank"] = leader["a_rank"] + 1
    pairs = f.merge(leader.drop(columns=["a_rank"]), on=["race_id", "lap", "rank"], how="inner")
    pairs = pairs[pairs.interval_ahead.le(MAX_INTERVAL_S) & pairs.interval_ahead.notna()].copy()
    pairs = pairs[(pairs.a_cutoff <= pairs.cutoff) & pairs.next_record_lap.eq(pairs.lap + 1)
                  & pairs.a_next_record_lap.eq(pairs.lap + 1)]
    pairs = pairs[~(pairs.lap_l_pit | pairs.lap_l1_pit | pairs.a_lap_l_pit | pairs.a_lap_l1_pit)]
    calm = pairs.neutral_in_last3.eq(0) & pairs.yellow_in_last1.eq(0) & pairs.regime_next.eq("green")
    pairs = pairs[calm & pairs.order_next.notna() & pairs.a_order_next.notna()].copy()
    pairs["overtake"] = (pairs.order_next < pairs.a_order_next).astype(int)
    pairs["interval"] = pairs.interval_ahead
    pairs["interval_trend"] = pairs.interval_ahead - pairs.interval_prev
    pairs["pace_advantage"] = pairs.a_last_lap_seconds - pairs.last_lap_seconds   # s, >0: follower lapped faster
    pairs["tyre_age_diff"] = pairs.a_tyre_age_next - pairs.tyre_age_next          # >0: follower on newer tyres
    pairs["compound_diff"] = pairs.compound_rank - pairs.a_compound_rank
    pairs["follower_tyre_age"], pairs["leader_tyre_age"] = pairs.tyre_age_next, pairs.a_tyre_age_next
    pairs["within_drs"] = (pairs.interval <= 1.0).astype(int)
    pairs = pairs.sort_values(["race_start", "race_id", "lap"]).reset_index(drop=True)
    pairs["circuit_rate_prior"] = _prior_circuit_rate(pairs)
    cols = ["race_id", "year", "event", "circuit", "race_start", "lap", "driver_number", "a_driver_number", "overtake"]
    return pairs[cols + FEATURES]


def _prior_circuit_rate(pairs: pd.DataFrame) -> pd.Series:
    """Overtake rate per circuit using only races that started strictly earlier."""
    if pairs[["race_id", "circuit", "race_start", "overtake"]].isna().any().any():
        raise ValueError("Race identity, circuit, start and observed label are required")
    if pairs.groupby("race_id")["circuit"].nunique(dropna=False).gt(1).any() or pairs.groupby("race_id")["race_start"].nunique(dropna=False).gt(1).any():
        raise ValueError("Each race must have one circuit and start time")
    per_race = (pairs.groupby(["circuit", "race_id"], as_index=False)
                .agg(start=("race_start", "first"), n=("overtake", "size"), k=("overtake", "sum")))
    per_race["start"] = pd.to_datetime(per_race.start, utc=True, errors="coerce", format="mixed")
    if per_race.start.isna().any():
        raise ValueError("Each race must have a valid start time")
    prior = {}
    for circuit, part in per_race.groupby("circuit"):
        by_start = part.groupby("start", sort=True)[["k", "n"]].sum()
        cumulative = by_start.cumsum().shift(1)
        for race_id, start in zip(part.race_id, part.start, strict=True):
            k, n = cumulative.loc[start, ["k", "n"]]
            prior[race_id] = k / n if n and n > 0 else np.nan
    return pairs.race_id.map(prior)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pace', type=Path, default=PACE)
    parser.add_argument('--out', type=Path, default=OUT)
    args = parser.parse_args()
    if (args.out / 'pairs.parquet').exists() or (args.out / 'dataset_summary.json').exists():
        raise FileExistsError('Overtake dataset artifacts exist; choose a new --out directory')
    args.out.mkdir(parents=True, exist_ok=True)
    pairs = build(pd.read_parquet(args.pace))
    pairs.to_parquet(args.out / "pairs.parquet", index=False)
    summary = {"pairs": len(pairs), "overtakes": int(pairs.overtake.sum()), "rate": float(pairs.overtake.mean()),
               "races": int(pairs.race_id.nunique()),
               "rate_by_year": pairs.groupby("year").overtake.mean().round(4).to_dict()}
    (args.out / "dataset_summary.json").write_text(json.dumps(summary, indent=2, default=float))
    print(json.dumps(summary, indent=1, default=float))


if __name__ == "__main__":
    main()
