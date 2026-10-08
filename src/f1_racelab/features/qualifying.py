from functools import reduce

import numpy as np
import pandas as pd

from f1_racelab.data.fastf1_source import load_session


REPRESENTATIVE_THRESHOLD = 1.03


def _seconds(value) -> float:
    if pd.isna(value):
        return np.nan
    return value.total_seconds()


def representative_laps(
    laps: pd.DataFrame,
    threshold: float = REPRESENTATIVE_THRESHOLD,
) -> pd.DataFrame:
    """
    V1 push-lap approximation.

    1. Require a lap time.
    2. Remove deleted laps.
    3. Remove pit-in and pit-out laps.
    4. For each driver, retain laps within 3% of that driver's
       fastest remaining lap.

    The 3% threshold is OUR V1 heuristic, not ground truth.
    """

    clean = laps[laps["LapTime"].notna()].copy()

    if "Deleted" in clean.columns:
        clean = clean[~clean["Deleted"].fillna(False)].copy()

    clean = clean[
        clean["PitInTime"].isna()
        & clean["PitOutTime"].isna()
    ].copy()

    clean["lap_seconds"] = clean["LapTime"].dt.total_seconds()

    representative = []

    for driver, driver_laps in clean.groupby("Driver"):
        if driver_laps.empty:
            continue

        fastest = driver_laps["lap_seconds"].min()

        selected = driver_laps[
            driver_laps["lap_seconds"]
            <= fastest * threshold
        ].copy()

        representative.append(selected)

    if not representative:
        return clean.iloc[0:0].copy()

    return pd.concat(representative, ignore_index=True)


def build_practice_features(
    session,
    prefix: str,
) -> pd.DataFrame:
    laps = representative_laps(session.laps)

    rows = []

    for driver, driver_laps in laps.groupby("Driver"):
        driver_laps = driver_laps.sort_values("lap_seconds")

        if driver_laps.empty:
            continue

        best_row = driver_laps.iloc[0]
        top3 = driver_laps.head(3)

        sector_bests = []

        for sector in (
            "Sector1Time",
            "Sector2Time",
            "Sector3Time",
        ):
            values = driver_laps[sector].dropna()

            if values.empty:
                sector_bests.append(np.nan)
            else:
                sector_bests.append(
                    values.min().total_seconds()
                )

        theoretical_best = (
            sum(sector_bests)
            if all(pd.notna(x) for x in sector_bests)
            else np.nan
        )

        soft_laps = driver_laps[
            driver_laps["Compound"].astype(str).str.upper()
            == "SOFT"
        ]

        soft_best = (
            soft_laps["lap_seconds"].min()
            if not soft_laps.empty
            else np.nan
        )

        rows.append(
            {
                "driver": driver,

                f"{prefix}_best_seconds":
                    best_row["lap_seconds"],

                f"{prefix}_top3_median_seconds":
                    top3["lap_seconds"].median(),

                f"{prefix}_representative_laps":
                    len(driver_laps),

                f"{prefix}_soft_best_seconds":
                    soft_best,

                f"{prefix}_theoretical_best_seconds":
                    theoretical_best,

                f"{prefix}_best_vs_theoretical":
                    (
                        best_row["lap_seconds"]
                        - theoretical_best
                        if pd.notna(theoretical_best)
                        else np.nan
                    ),

                f"{prefix}_best_tyre_life":
                    best_row.get("TyreLife", np.nan),

                f"{prefix}_best_speed_trap":
                    best_row.get("SpeedST", np.nan),
            }
        )

    features = pd.DataFrame(rows)

    if features.empty:
        return features

    best_column = f"{prefix}_best_seconds"

    reference = features[best_column].min()

    features[f"{prefix}_gap_seconds"] = (
        features[best_column] - reference
    )

    features[f"{prefix}_gap_pct"] = (
        features[f"{prefix}_gap_seconds"]
        / reference
        * 100.0
    )

    features[f"{prefix}_rank"] = (
        features[best_column]
        .rank(method="min")
        .astype(int)
    )

    return features


def build_qualifying_targets(session) -> pd.DataFrame:
    """
    Targets available AFTER qualifying.

    These must NEVER be used as pre-qualifying input features.
    """

    results = session.results.copy()

    targets = pd.DataFrame(
        {
            "driver": results["Abbreviation"],
            "final_position": pd.to_numeric(
                results["Position"],
                errors="coerce",
            ),
            "q1_seconds": results["Q1"].dt.total_seconds(),
            "q2_seconds": results["Q2"].dt.total_seconds(),
            "q3_seconds": results["Q3"].dt.total_seconds(),
        }
    )

    q1_reference = targets["q1_seconds"].min()

    targets["q1_gap_pct"] = (
        (targets["q1_seconds"] - q1_reference)
        / q1_reference
        * 100.0
    )

    return targets


def build_weekend_dataset(
    year: int,
    event: str,
) -> pd.DataFrame:
    fp1 = load_session(year, event, "FP1")
    fp2 = load_session(year, event, "FP2")
    fp3 = load_session(year, event, "FP3")
    qualifying = load_session(year, event, "Q")

    feature_frames = [
        build_practice_features(fp1, "fp1"),
        build_practice_features(fp2, "fp2"),
        build_practice_features(fp3, "fp3"),
    ]

    features = reduce(
        lambda left, right: left.merge(
            right,
            on="driver",
            how="outer",
        ),
        feature_frames,
    )

    targets = build_qualifying_targets(qualifying)

    dataset = features.merge(
        targets,
        on="driver",
        how="inner",
    )

    dataset.insert(0, "event", event)
    dataset.insert(0, "year", year)

    # Weekend progression.
    dataset["fp1_to_fp3_improvement_pct"] = (
        dataset["fp1_gap_pct"]
        - dataset["fp3_gap_pct"]
    )

    dataset["fp2_to_fp3_improvement_pct"] = (
        dataset["fp2_gap_pct"]
        - dataset["fp3_gap_pct"]
    )

    return dataset.sort_values("final_position")
