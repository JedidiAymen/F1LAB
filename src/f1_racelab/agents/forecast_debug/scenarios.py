"""Synthetic batch-vs-live forecast scenarios with one planted root cause each.

Each scenario is a small warehouse of tables shaped like F1Lab's next-lap pace forecasts:

* ``laps``: actual lap times and the green-flag flag (the ground truth forecasts are scored against);
* ``features_batch`` / ``features_live``: the inputs each pipeline used;
* ``batch_forecasts`` / ``live_forecasts``: the outputs of the nightly batch job and the on-demand service;
* ``model_registry``: the model bundles that exist;
* ``pipeline_config``: the declared configuration of both pipelines.

The planted root cause, its magnitude and the affected races are randomized by ``seed``, so an agent cannot
memorize answers. Ground truth lives only on the ``Scenario`` object and is never placed in a table.
All data is synthetic; nothing here is a real Formula 1 result.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np
import pandas as pd

LABELS: tuple[str, ...] = (
    "regime_shift",
    "stale_model_version",
    "feature_skew",
    "missing_live_data",
    "unit_mismatch",
    "config_drift",
    "lap_misalignment",
    "no_material_discrepancy",
)

DESCRIPTIONS: dict[str, str] = {
    "regime_shift": "Actual pace changed in a recent period that the model was not trained on; batch and live agree "
                    "but both are biased against actuals in that period.",
    "stale_model_version": "The live service runs a different (older) model version than the batch job.",
    "feature_skew": "The live service computes an input feature differently from the batch job.",
    "missing_live_data": "The live service produced no forecasts for some races that the batch job covers.",
    "unit_mismatch": "Some live forecasts are expressed in a different unit than the batch forecasts.",
    "config_drift": "The live pipeline's configuration differs from the batch pipeline's (for example its filters).",
    "lap_misalignment": "Live forecasts are attached to the wrong lap key (shifted by one lap) for some races.",
    "no_material_discrepancy": "Batch and live forecasts agree within noise and neither is materially biased.",
}

YEARS = (2024, 2025, 2026)
RACES_PER_YEAR = 6
DRIVERS = tuple(f"D{i:02d}" for i in range(1, 7))
LAPS = 40
COMPOUND_OFFSET = {"SOFT": -0.6, "MEDIUM": 0.0, "HARD": 0.4}
FUEL_PER_LAP = -0.03
MODELS = {
    "pace-v1": {"intercept": 90.0, "tyre_coef": 0.045, "trained_through_year": 2024, "status": "retired"},
    "pace-v2": {"intercept": 90.0, "tyre_coef": 0.060, "trained_through_year": 2025, "status": "production"},
}
KEYS = ["race_id", "driver", "lap"]


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    root_cause: str
    seed: int
    tables: dict[str, pd.DataFrame]
    notes: str  # hidden ground-truth detail for reports; never shown to an agent


def _base_laps(rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    for year in YEARS:
        for r in range(RACES_PER_YEAR):
            race_id = f"{year}-r{r + 1:02d}"
            for driver in DRIVERS:
                stint_len = int(rng.integers(14, 24))
                compounds = rng.choice(list(COMPOUND_OFFSET), size=LAPS // 10 + 2)
                for lap in range(1, LAPS + 1):
                    stint = (lap - 1) // stint_len
                    rows.append((race_id, year, driver, lap, str(compounds[stint]), (lap - 1) % stint_len + 1))
    laps = pd.DataFrame(rows, columns=["race_id", "year", "driver", "lap", "compound", "tyre_age"])
    laps["eligible_green"] = rng.random(len(laps)) < 0.92
    true = MODELS["pace-v2"]
    clean = (true["intercept"] + laps.compound.map(COMPOUND_OFFSET) + true["tyre_coef"] * laps.tyre_age
             + FUEL_PER_LAP * laps.lap + rng.normal(0, 0.35, len(laps)))
    laps["actual_seconds"] = np.where(laps.eligible_green, clean, clean + rng.uniform(15, 30, len(laps)))
    return laps


def predict(features: pd.DataFrame, version: str) -> pd.Series:
    """The toy production model: one row of features -> next-lap seconds."""
    m = MODELS[version]
    return (m["intercept"] + features.compound.map(COMPOUND_OFFSET) + m["tyre_coef"] * features.tyre_age
            + FUEL_PER_LAP * features.lap)


def _forecasts(features: pd.DataFrame, version: str, green_only: bool) -> pd.DataFrame:
    rows = features[features.eligible_green] if green_only else features
    out = rows[KEYS].copy()
    out["model_version"] = version
    out["pred_seconds"] = predict(rows, version).round(4).to_numpy()
    return out.reset_index(drop=True)


def _registry() -> pd.DataFrame:
    rows = []
    for version, m in MODELS.items():
        sha = hashlib.sha256(f"{version}:{m['tyre_coef']}".encode()).hexdigest()[:16]
        rows.append({"model_version": version, "bundle_sha256": sha, "trained_through_year": m["trained_through_year"],
                     "status": m["status"]})
    return pd.DataFrame(rows)


def _config(live_green_only: bool = True) -> pd.DataFrame:
    rows = []
    for pipeline in ("batch", "live"):
        green = "true" if pipeline == "batch" or live_green_only else "false"
        rows += [{"pipeline": pipeline, "key": "model_version", "value": "pace-v2"},
                 {"pipeline": pipeline, "key": "green_laps_only", "value": green},
                 {"pipeline": pipeline, "key": "output_unit", "value": "seconds"}]
    return pd.DataFrame(rows)


def build_scenario(root_cause: str, seed: int) -> Scenario:
    if root_cause not in LABELS:
        raise ValueError(f"unknown root cause {root_cause!r}")
    rng = np.random.default_rng(seed * 1009 + LABELS.index(root_cause))
    laps = _base_laps(rng)
    features = laps[["race_id", "driver", "lap", "compound", "tyre_age", "eligible_green"]].copy()
    features_batch, features_live = features.copy(), features.copy()
    live_version, live_green_only = "pace-v2", True
    races_2026 = sorted(laps.loc[laps.year == 2026, "race_id"].unique())
    all_races = sorted(laps.race_id.unique())
    notes = "no planted fault"

    if root_cause == "regime_shift":
        shift = float(rng.uniform(0.25, 0.45))
        laps.loc[laps.year == 2026, "actual_seconds"] -= shift
        notes = f"2026 actuals {shift:.3f} s faster than the model's training regime"
    elif root_cause == "stale_model_version":
        live_version = "pace-v1"
        notes = "live service runs pace-v1 while batch and config use pace-v2"
    elif root_cause == "feature_skew":
        offset = int(rng.integers(1, 4))
        features_live["tyre_age"] = features_live.tyre_age + offset
        notes = f"live tyre_age computed {offset} lap(s) later than batch"
    elif root_cause == "config_drift":
        live_green_only = False
        notes = "live pipeline stopped filtering to green-flag laps"

    batch = _forecasts(features_batch, "pace-v2", green_only=True)
    live = _forecasts(features_live, live_version, green_only=live_green_only)

    if root_cause == "missing_live_data":
        dropped = sorted(rng.choice(all_races, size=int(rng.integers(2, 5)), replace=False).tolist())
        live = live[~live.race_id.isin(dropped)].reset_index(drop=True)
        notes = f"no live forecasts for {dropped}"
    elif root_cause == "unit_mismatch":
        start = races_2026[int(rng.integers(1, len(races_2026) - 1))]
        affected = live.race_id >= start
        live.loc[affected, "pred_seconds"] = (live.loc[affected, "pred_seconds"] * 1000).round(1)
        notes = f"live forecasts in milliseconds from {start} onward"
    elif root_cause == "lap_misalignment":
        shifted = sorted(rng.choice(all_races, size=int(rng.integers(3, 6)), replace=False).tolist())
        mask = live.race_id.isin(shifted)
        live.loc[mask, "lap"] = live.loc[mask, "lap"] + 1
        live = live[live.lap <= LAPS].reset_index(drop=True)
        notes = f"live lap keys shifted by +1 for {shifted}"

    # Realistic float jitter between independently computed pipelines, present in every scenario.
    live["pred_seconds"] = (live.pred_seconds + rng.normal(0, 0.002, len(live))).round(4)

    tables = {
        "laps": laps[["race_id", "year", "driver", "lap", "eligible_green", "actual_seconds"]],
        "features_batch": features_batch,
        "features_live": features_live,
        "batch_forecasts": batch,
        "live_forecasts": live,
        "model_registry": _registry(),
        "pipeline_config": _config(live_green_only),
    }
    return Scenario(scenario_id=f"{root_cause}-s{seed}", root_cause=root_cause, seed=seed, tables=tables,
                    notes=notes)
