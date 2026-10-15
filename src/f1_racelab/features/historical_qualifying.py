"""Strictly pre-qualifying historical form: one row per driver-weekend.

Everything derived from qualifying results is shifted to prior weekends.
A team's per-event strength is aggregated before rolling, so both drivers
see the same PREVIOUS team results and neither sees this event's target.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

WINDOWS = (3, 5)


def feature_names(windows=WINDOWS) -> list[str]:
    stems = (
        "driver_q1_gap", "driver_fp3_to_q1_gain", "driver_position",
        "driver_q3_rate", "driver_vs_teammate_q1", "team_q1_gap",
    )
    return [f"{stem}_last_{w}" for w in windows for stem in stems]


def add_historical_features(data: pd.DataFrame, windows=WINDOWS) -> pd.DataFrame:
    """Compute strictly lagged features using completed PRIOR events only.

    A dataset built through 2025 can safely contain its labels because every
    historical label is shifted before it appears as a predictor. The test
    season may use results from its earlier rounds (prequential semantics).
    """
    required = {"year", "round", "driver", "q1_gap_pct", "fp3_gap_pct", "final_position"}
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    out = data.copy()
    if out.duplicated(["year", "round", "driver"]).any():
        raise ValueError("Duplicate driver-weekend row")
    if "team" not in out.columns:
        out["team"] = pd.NA
    out["team"] = out["team"].astype("string").str.strip().replace("", pd.NA)
    out = out.sort_values(["year", "round", "driver"], kind="stable").reset_index(drop=True)
    for c in ("q1_gap_pct", "fp3_gap_pct", "final_position"):
        out[c] = pd.to_numeric(out[c], errors="coerce")

    out["_fp3_to_q1_gain"] = out["fp3_gap_pct"] - out["q1_gap_pct"]
    if "q3_seconds" in out.columns:
        q3 = pd.to_numeric(out["q3_seconds"], errors="coerce")
        out["_q3_flag"] = np.where(out["final_position"].notna(), q3.notna().astype(float), np.nan)
    else:
        out["_q3_flag"] = np.nan

    def lagged_per_driver(source: str, destination: str, w: int) -> None:
        out[destination] = out.groupby("driver", sort=False)[source].transform(
            lambda values: values.shift(1).rolling(w, min_periods=1).mean()
        )

    # Other-driver comparison exists only when an actual team label and at
    # least TWO drivers are present at the same Grand Prix.
    teams = out["team"].notna()
    work = out.loc[teams, ["year", "round", "team", "driver", "q1_gap_pct"]].copy()
    key = ["year", "round", "team"]
    aggregate = work.groupby(key)["q1_gap_pct"].agg(["sum", "count"])
    work = work.join(aggregate, on=key)
    work["_vs_mate"] = np.where(
        (work["count"] >= 2) & work["q1_gap_pct"].notna(),
        work["q1_gap_pct"] - (work["sum"] - work["q1_gap_pct"]) / (work["count"] - 1),
        np.nan,
    )
    out["_vs_mate"] = np.nan
    out.loc[work.index, "_vs_mate"] = work["_vs_mate"]

    for w in windows:
        lagged_per_driver("q1_gap_pct", f"driver_q1_gap_last_{w}", w)
        lagged_per_driver("_fp3_to_q1_gain", f"driver_fp3_to_q1_gain_last_{w}", w)
        lagged_per_driver("final_position", f"driver_position_last_{w}", w)
        lagged_per_driver("_q3_flag", f"driver_q3_rate_last_{w}", w)
        lagged_per_driver("_vs_mate", f"driver_vs_teammate_q1_last_{w}", w)

    # One row PER TEAM / WEEKEND (never one row per driver), to prevent
    # intra-weekend leakage when using a groupby('team').shift(1).
    team_weekends = (
        out.loc[teams]
        .groupby(key, as_index=False)["q1_gap_pct"]
        .mean()
        .sort_values(["team", "year", "round"], kind="stable")
    )
    for w in windows:
        col = f"team_q1_gap_last_{w}"
        team_weekends[col] = team_weekends.groupby("team")["q1_gap_pct"].transform(
            lambda values, window=w: values.shift(1).rolling(window, min_periods=1).mean()
        )
    keep = key + [f"team_q1_gap_last_{w}" for w in windows]
    out = out.merge(team_weekends[keep], on=key, how="left", validate="many_to_one", sort=False)
    return out.drop(columns=["_fp3_to_q1_gain", "_q3_flag", "_vs_mate"])
