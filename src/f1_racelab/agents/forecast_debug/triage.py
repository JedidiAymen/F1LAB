"""Read-only diagnostic evidence summary for batch-vs-live forecast incidents.

All indicators are descriptive. They neither determine a root cause nor certify an
LLM diagnosis. Actual outcomes are used only for retrospective bias checks.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

KEYS = ["race_id", "driver", "lap"]


def _finite(value: float | None) -> float | None:
    if value is None or not np.isfinite(value):
        return None
    return round(float(value), 5)


def summarize(tables: Mapping[str, pd.DataFrame]) -> dict[str, Any]:
    """Summarize coverage, model identity, feature skew, timing and factual bias.

    Reject duplicate forecast/feature keys rather than silently multiplying
    matches. Do not mutate input frames.
    """
    batch = tables["batch_forecasts"]
    live = tables["live_forecasts"]
    joined = batch.merge(live, on=KEYS, how="outer", suffixes=("_batch", "_live"),
                         indicator=True, validate="one_to_one")
    both = joined.loc[joined["_merge"] == "both"].copy()
    abs_gap = (both.pred_seconds_live - both.pred_seconds_batch).abs()
    versions = {
        "batch": sorted(str(x) for x in batch.model_version.dropna().unique()),
        "live": sorted(str(x) for x in live.model_version.dropna().unique()),
    }
    out: dict[str, Any] = {
        "forecast_coverage": {
            "batch_rows": len(batch), "live_rows": len(live),
            "matched_keys": len(both),
            "batch_only_keys": int((joined._merge == "left_only").sum()),
            "live_only_keys": int((joined._merge == "right_only").sum()),
        },
        "prediction_comparison_seconds": {
            "mean_abs_gap_on_matched": _finite(float(abs_gap.mean())),
            "max_abs_gap_on_matched": _finite(float(abs_gap.max())),
            "max_abs_batch_value": _finite(float(batch.pred_seconds.abs().max())),
            "max_abs_live_value": _finite(float(live.pred_seconds.abs().max())),
        },
        "model_versions": versions,
        "model_version_disagreements_on_matched": int((
            both.model_version_batch != both.model_version_live).sum()),
    }
    configs = tables["pipeline_config"]
    cfg = configs.pivot(index="key", columns="pipeline", values="value")
    common = cfg.dropna(subset=["batch", "live"])
    out["config_differences"] = [
        {"key": str(key), "batch": str(row.batch), "live": str(row.live)}
        for key, row in common.iterrows() if row.batch != row.live
    ]
    left = tables["features_batch"]
    right = tables["features_live"]
    feature_join = left.merge(right, on=KEYS, how="outer", suffixes=("_batch", "_live"),
                              indicator=True, validate="one_to_one")
    feature_both = feature_join.loc[feature_join._merge == "both"]
    skew: dict[str, int] = {}
    for name in ("tyre_age", "compound", "eligible_green"):
        a, b = feature_both[f"{name}_batch"], feature_both[f"{name}_live"]
        if pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b):
            mismatched = ~np.isclose(a.to_numpy(dtype=float), b.to_numpy(dtype=float),
                                     equal_nan=True, atol=1e-9, rtol=0)
        else:
            mismatched = ~(a.eq(b) | (a.isna() & b.isna())).to_numpy()
        skew[name] = int(np.sum(mismatched))
    out["feature_comparison"] = {
        "matched_keys": len(feature_both),
        "batch_only_keys": int((feature_join._merge == "left_only").sum()),
        "live_only_keys": int((feature_join._merge == "right_only").sum()),
        "mismatched_values_on_matched": skew,
    }

    # Possible shifted lap keys: this is a clue, not a definitive diagnosis.
    prev = batch[KEYS + ["pred_seconds"]].copy()
    prev["lap"] = prev["lap"] + 1
    prev = prev.rename(columns={"pred_seconds": "previous_batch_pred_seconds"})
    alignment = both.merge(prev, on=KEYS, how="left", validate="one_to_one")
    alignment_hints: list[str] = []
    for race, group in alignment.groupby("race_id", sort=True):
        same = (group.pred_seconds_live - group.pred_seconds_batch).abs().lt(0.02)
        previous = (group.pred_seconds_live - group.previous_batch_pred_seconds).abs().lt(0.02)
        if float(previous.mean()) > 0.8 and float(same.mean()) < 0.2:
            alignment_hints.append(str(race))
    out["possible_previous_lap_alignment_races"] = alignment_hints[:20]

    laps = tables["laps"][KEYS + ["year", "actual_seconds", "eligible_green"]]
    factual = batch[KEYS + ["pred_seconds"]].merge(laps, on=KEYS, validate="one_to_one")
    factual = factual.loc[factual.eligible_green]
    bias = factual.assign(error=factual.pred_seconds - factual.actual_seconds).groupby("year").error.mean()
    out["batch_bias_on_observed_green_seconds_by_year"] = {
        str(year): _finite(float(value)) for year, value in bias.items()
    }
    out["limitations"] = (
        "Retrospective incident evidence, not a causal diagnosis. "
        "Observed future lap times appear only in factual bias checks. "
        "No-discrepancy conclusions still require investigation."
    )
    return out
