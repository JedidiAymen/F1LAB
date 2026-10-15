"""Trace one driver's lagged Q1/team feature to actual earlier weekends."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from f1_racelab.features.historical_qualifying import add_historical_features


def audit(dataset: Path, year: int, round_no: int, driver: str, window: int = 3) -> dict:
    raw = pd.read_parquet(dataset)
    enriched = add_historical_features(raw)
    selected = enriched.loc[(enriched.year == year) & (enriched["round"] == round_no)
                            & (enriched.driver == driver)]
    if len(selected) != 1:
        raise ValueError(f"Expected one row for {year} R{round_no} {driver}, got {len(selected)}")
    current = selected.iloc[0]
    chronology = raw.sort_values(["year", "round"], kind="stable")
    before = chronology.loc[(chronology.year < year) |
                            ((chronology.year == year) & (chronology["round"] < round_no))]
    driver_rows = before.loc[before.driver.eq(driver)].tail(window)
    team_events = (before.loc[before.team.eq(current.team)]
                   .groupby(["year", "round", "event"], as_index=False)["q1_gap_pct"].mean()
                   .sort_values(["year", "round"], kind="stable").tail(window))
    driver_value = float(driver_rows.q1_gap_pct.mean())
    team_value = float(team_events.q1_gap_pct.mean())
    feature_driver = f"driver_q1_gap_last_{window}"
    feature_team = f"team_q1_gap_last_{window}"
    if not np.isclose(current[feature_driver], driver_value, equal_nan=True):
        raise AssertionError("Driver history disagrees with independent prior-row mean")
    if not np.isclose(current[feature_team], team_value, equal_nan=True):
        raise AssertionError("Team history disagrees with independent prior-event mean")
    return {"year": year, "round": round_no, "driver": driver, "team": str(current.team),
            "window": window, "driver_feature": feature_driver,
            "driver_value": driver_value,
            "driver_contributors": driver_rows[["year", "round", "event", "q1_gap_pct"]].to_dict("records"),
            "team_feature": feature_team, "team_value": team_value,
            "team_contributors": team_events.to_dict("records")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--round", type=int, default=16)
    parser.add_argument("--driver", default="VER")
    parser.add_argument("--window", type=int, choices=(3, 5), default=3)
    args = parser.parse_args()
    print(json.dumps(audit(args.dataset, args.year, args.round, args.driver, args.window), indent=2))


if __name__ == "__main__":
    main()
