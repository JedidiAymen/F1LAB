"""Read-only diagnostic evidence summary for batch-vs-live forecast incidents.

All indicators are descriptive. They neither determine a root cause nor certify an
LLM diagnosis. Actual outcomes are used only for retrospective bias checks.
"""
from __future__ import annotations

from collections.abc import Mapping
from numbers import Real
from typing import Any

import numpy as np
import pandas as pd

KEYS = ["race_id", "driver", "lap"]
EXPECTED_CONFIG_KEYS = ("model_version", "green_laps_only", "output_unit")


def _column(frame: pd.DataFrame, name: str) -> pd.Series:
    return frame[name] if name in frame else pd.Series(pd.NA, index=frame.index, dtype=object)


def _known(values: pd.Series, *, numeric: bool = False) -> pd.Series:
    if numeric:
        return pd.Series(np.isfinite(pd.to_numeric(values, errors="coerce").to_numpy(dtype=float, na_value=np.nan)),
                         index=values.index)
    return values.map(lambda x: False if pd.isna(x) else (
        bool(np.isfinite(float(x))) if isinstance(x, Real) else bool(str(x).strip())))


def _quality(values: pd.Series, *, numeric: bool = False) -> dict[str, int]:
    missing = values.isna() | values.map(lambda x: isinstance(x, str) and not x.strip())
    infinite = values.map(lambda x: isinstance(x, Real) and not pd.isna(x) and not np.isfinite(float(x)))
    known = _known(values, numeric=numeric)
    return {"known": int(known.sum()), "missing": int(missing.sum()), "nonfinite": int(infinite.sum()),
            "invalid": int((~known & ~missing & ~infinite).sum())}


def _identity_known(values: pd.Series) -> pd.Series:
    placeholders = {"unknown", "none", "null", "nan", "n/a"}
    return _known(values) & ~values.map(lambda x: isinstance(x, str) and x.strip().casefold() in placeholders)


def config_evidence(configs: pd.DataFrame) -> dict[str, Any]:
    """Treat absent, conflicting and unknown values separately from differences."""
    missing_columns = sorted({"pipeline", "key", "value"} - set(configs.columns))
    keys = sorted(set(EXPECTED_CONFIG_KEYS) | {str(x) for x in _column(configs, "key") if pd.notna(x)})
    differences, unknown, conflicts = [], [], []
    compared = 0
    for key in keys:
        observed: dict[str, str | None] = {}
        for pipeline in ("batch", "live"):
            rows = configs.loc[_column(configs, "key").eq(key).fillna(False)
                               & _column(configs, "pipeline").eq(pipeline).fillna(False)]
            values = _column(rows, "value")
            known = _identity_known(values) if key == "model_version" else _known(values)
            distinct = sorted(set(values[known].astype(str)))
            complete = bool(len(values)) and bool(known.all()) and len(distinct) == 1
            observed[pipeline] = distinct[0] if complete else None
            if len(distinct) > 1:
                conflicts.append({"key": key, "pipeline": pipeline, "values": distinct[:10],
                                  "values_truncated": len(distinct) > 10})
        if any(value is None for value in observed.values()):
            unknown.append({"key": key, **observed})
        else:
            compared += 1
            if observed["batch"] != observed["live"]:
                differences.append({"key": key, **observed})
    return {"config_differences": differences, "config_unknown_values": unknown,
            "config_conflicts": conflicts, "config_coverage": {
                "missing_columns": missing_columns, "compared_keys": compared,
                "expected_keys_in_diagnostic_schema": list(EXPECTED_CONFIG_KEYS),
                "unknown_keys": len(unknown), "unscoped_rows": int((
                    ~_column(configs, "pipeline").isin(["batch", "live"]) | ~_known(_column(configs, "key"))).sum())}}


def _finite(value: float | None) -> float | None:
    if value is None or not np.isfinite(value):
        return None
    return round(float(value), 5)


def summarize(tables: Mapping[str, pd.DataFrame]) -> dict[str, Any]:
    """Summarize coverage, model identity, feature skew, timing and factual bias.

    Reject duplicate forecast/feature keys rather than silently multiplying
    matches. Do not mutate input frames.
    """
    for name in ("batch_forecasts", "live_forecasts", "features_batch", "features_live", "laps"):
        if name not in tables or not set(KEYS) <= set(tables[name].columns) or tables[name][KEYS].isna().any().any():
            raise ValueError(f"{name} requires nonmissing race_id/driver/lap keys")
    batch = tables["batch_forecasts"].reindex(columns=KEYS + ["pred_seconds", "model_version"]).copy()
    live = tables["live_forecasts"].reindex(columns=KEYS + ["pred_seconds", "model_version"]).copy()
    prediction_quality = {name: _quality(frame.pred_seconds, numeric=True) for name, frame in (("batch", batch), ("live", live))}
    for frame in (batch, live):
        frame["pred_seconds"] = pd.to_numeric(frame.pred_seconds, errors="coerce").where(_known(frame.pred_seconds, numeric=True))
    joined = batch.merge(live, on=KEYS, how="outer", suffixes=("_batch", "_live"),
                         indicator=True, validate="one_to_one")
    both = joined.loc[joined["_merge"] == "both"].copy()
    comparable = _known(both.pred_seconds_live, numeric=True) & _known(both.pred_seconds_batch, numeric=True)
    abs_gap = (both.loc[comparable, "pred_seconds_live"] - both.loc[comparable, "pred_seconds_batch"]).abs()
    version_known = _identity_known(both.model_version_batch) & _identity_known(both.model_version_live)
    versions = {
        "batch": sorted(str(x) for x in batch.loc[_identity_known(batch.model_version), "model_version"].unique()),
        "live": sorted(str(x) for x in live.loc[_identity_known(live.model_version), "model_version"].unique()),
    }
    out: dict[str, Any] = {
        "schema_version": 2,
        "forecast_coverage": {
            "batch_rows": len(batch), "live_rows": len(live),
            "matched_keys": len(both),
            "batch_only_keys": int((joined._merge == "left_only").sum()),
            "live_only_keys": int((joined._merge == "right_only").sum()),
        },
        "prediction_comparison_seconds": {
            "finite_pairs": int(comparable.sum()), "unknown_pairs": int((~comparable).sum()),
            "input_quality": prediction_quality,
            "mean_abs_gap_on_matched": _finite(float(abs_gap.mean())),
            "max_abs_gap_on_matched": _finite(float(abs_gap.max())),
            "max_abs_batch_value": _finite(float(batch.pred_seconds.abs().max())),
            "max_abs_live_value": _finite(float(live.pred_seconds.abs().max())),
        },
        "model_versions": versions,
        "model_version_disagreements_on_matched": int((
            both.loc[version_known, "model_version_batch"] != both.loc[version_known, "model_version_live"]).sum()),
        "model_version_coverage": {"known_pairs": int(version_known.sum()), "unknown_pairs": int((~version_known).sum())},
    }
    out.update(config_evidence(tables.get("pipeline_config", pd.DataFrame())))
    feature_names = ("tyre_age", "compound", "eligible_green")
    left = tables["features_batch"].reindex(columns=KEYS + list(feature_names))
    right = tables["features_live"].reindex(columns=KEYS + list(feature_names))
    feature_join = left.merge(right, on=KEYS, how="outer", suffixes=("_batch", "_live"),
                              indicator=True, validate="one_to_one")
    feature_both = feature_join.loc[feature_join._merge == "both"]
    skew: dict[str, int] = {}
    quality = {}
    for name in feature_names:
        a, b = feature_both[f"{name}_batch"], feature_both[f"{name}_live"]
        numeric = name == "tyre_age"
        known = _known(a, numeric=numeric) & _known(b, numeric=numeric)
        if numeric:
            mismatched = ~np.isclose(pd.to_numeric(a[known]).to_numpy(dtype=float), pd.to_numeric(b[known]).to_numpy(dtype=float), atol=1e-9, rtol=0)
        else:
            mismatched = ~a[known].eq(b[known]).to_numpy()
        skew[name] = int(np.sum(mismatched))
        quality[name] = {"known_pairs": int(known.sum()), "unknown_pairs": int((~known).sum()),
                         "batch": _quality(a, numeric=numeric), "live": _quality(b, numeric=numeric)}
    out["feature_comparison"] = {
        "matched_keys": len(feature_both),
        "batch_only_keys": int((feature_join._merge == "left_only").sum()),
        "live_only_keys": int((feature_join._merge == "right_only").sum()),
        "mismatched_values_on_matched": skew,
        "value_coverage_on_matched": quality,
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

    laps = tables["laps"].reindex(columns=KEYS + ["year", "actual_seconds", "eligible_green"]).copy()
    laps["actual_seconds"] = pd.to_numeric(laps.actual_seconds, errors="coerce").where(_known(laps.actual_seconds, numeric=True))
    factual = batch[KEYS + ["pred_seconds"]].merge(laps, on=KEYS, validate="one_to_one")
    factual = factual.loc[factual.eligible_green.eq(True).fillna(False)
                          & _known(factual.pred_seconds, numeric=True) & _known(factual.actual_seconds, numeric=True)]
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
