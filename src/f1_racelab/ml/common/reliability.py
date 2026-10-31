"""Recompute saved out-of-fold comparisons and input drift; never retrain here.

PSI uses reference quantile bins, an explicit missing-value bin, and 0.5-count
smoothing. It describes distribution change, not its cause or significance.
OOF status comes from the benchmark protocol; source files are hash-linked.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from f1_racelab.ml.common.contracts import now_utc
from f1_racelab.ml.common.metrics import cluster_bootstrap_delta
from f1_racelab.ml.common.tracking import source_revision

ROOT = Path(__file__).resolve().parents[4]
PACE = ROOT / "data/processed/race_pace"
OUT = ROOT / "data/processed/reliability/pace.json"
KEY = ["race_id", "driver_number", "lap"]
DRIFT_FEATURES = ["anchor_seconds", "tyre_age_next", "last1", "track_temp", "air_temp",
                  "interval_ahead", "weather_age_s"]


def psi(reference: pd.Series, current: pd.Series) -> float | None:
    a, b = pd.to_numeric(reference, errors="coerce"), pd.to_numeric(current, errors="coerce")
    a, b = a.replace([np.inf, -np.inf], np.nan), b.replace([np.inf, -np.inf], np.nan)
    if not len(a) or not len(b) or not a.notna().any():
        return None
    quantiles = np.unique(np.quantile(a.dropna(), np.linspace(0, 1, 11)))
    edges = (np.r_[-np.inf, np.nextafter(quantiles[0], -np.inf), np.nextafter(quantiles[0], np.inf), np.inf]
             if len(quantiles) == 1 else np.r_[-np.inf, quantiles[1:-1], np.inf])
    ac = np.r_[np.histogram(a.dropna(), edges)[0], a.isna().sum()] + 0.5
    bc = np.r_[np.histogram(b.dropna(), edges)[0], b.isna().sum()] + 0.5
    pa, pb = ac / ac.sum(), bc / bc.sum()
    return float(np.sum((pb - pa) * np.log(pb / pa)))


def compare(predictions: pd.DataFrame) -> dict:
    if predictions.duplicated(KEY + ["model"]).any():
        raise ValueError("Duplicate prediction keys; comparison would multiply rows")
    green = predictions[predictions.eligible_green_next].copy()
    if not np.isfinite(green[["pred_seconds", "next_lap_seconds"]].to_numpy()).all():
        raise ValueError("Nonfinite scored predictions or targets")
    base = green[green.model == "persistence_last_lap"][KEY + ["pred_seconds", "next_lap_seconds"]]
    if base.empty:
        raise ValueError("Persistence baseline is required")
    table = []
    for model, group in green.groupby("model"):
        paired = group.merge(base, on=KEY, suffixes=("", "_baseline"), validate="one_to_one")
        if paired.empty or not np.allclose(paired.next_lap_seconds, paired.next_lap_seconds_baseline,
                                           rtol=0, atol=1e-9):
            raise ValueError("Targets must agree across paired models")
        error = paired.pred_seconds - paired.next_lap_seconds
        abs_error = error.abs()
        baseline_error = (paired.pred_seconds_baseline - paired.next_lap_seconds).abs()
        delta = cluster_bootstrap_delta(abs_error.to_numpy(), baseline_error.to_numpy(),
                                         paired.race_id.to_numpy())
        table.append({"model": model, "rows": len(paired), "unmatched_rows": len(group) - len(paired),
                      "mae_s": float(abs_error.mean()), "bias_s": float(error.mean()), "vs_persistence": delta})
    selected = green[green.model == "lightgbm"].copy()
    if selected.empty:
        raise ValueError("LightGBM out-of-fold forecasts are required")
    selected["error_s"] = selected.pred_seconds - selected.next_lap_seconds
    seasons = selected.groupby("year").agg(rows=("lap", "size"), bias_s=("error_s", "mean"),
                                           mae_s=("error_s", lambda x: x.abs().mean())).reset_index()
    races: list[dict] = []
    for race_id, group in selected.groupby("race_id", sort=False):
        races.append({"race_id": str(race_id), "event": str(group.event.iloc[0]), "year": int(group.year.iloc[0]),
                      "rows": len(group), "mae_s": float(group.error_s.abs().mean()),
                      "bias_s": float(group.error_s.mean()), "drivers": sorted(group.driver_number.unique().tolist())})
    return {"comparison": table, "seasons": seasons.to_dict("records"),
            "races": sorted(races, key=lambda row: (row["year"], row["event"])),
            "failures": sorted(races, key=lambda row: -row["mae_s"])[:10]}


def build(pace_root: Path = PACE, out: Path = OUT) -> dict:
    predictions = pd.read_parquet(pace_root / "predictions.parquet")
    frame = pd.read_parquet(pace_root / "pace_frame.parquet")
    reference, current = frame[frame.year < 2026], frame[frame.year == 2026]
    report = {"schema_version": 1, "created_at_utc": now_utc(), "evidence": "real",
              "evaluation": "saved expanding-window out-of-fold forecasts; green-clean outcome cohort",
              "source": source_revision(), "units": "lap-time errors in seconds; PSI dimensionless",
              "sources": {name: hashlib.sha256((pace_root / name).read_bytes()).hexdigest()
                          for name in ("predictions.parquet", "pace_frame.parquet")},
              **compare(predictions),
              "drift": {"reference": "2023-2025", "current": "2026", "reference_rows": len(reference),
                        "current_rows": len(current), "method": "reference deciles + missing bin; 0.5-count smoothing",
                        "features": [{"feature": feature, "psi": psi(reference[feature], current[feature]),
                                      "reference_missing": float(reference[feature].isna().mean()),
                                      "current_missing": float(current[feature].isna().mean())}
                                     for feature in DRIFT_FEATURES]},
              "limitations": ["Repeatedly inspected historical results, not a fresh holdout.",
                              "Outcome-filtered cohort is conditional, not the strict decision-time protocol.",
                              "Input drift is descriptive; it does not prove a root cause or require retraining.",
                              "Only one served binary version exists; table rows compare saved benchmark candidates.",
                              "No monitored live production feed or batch-versus-live incident is claimed."]}
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, indent=2, allow_nan=False).encode()
    out.write_bytes(payload)
    out.with_suffix(".sha256").write_text(hashlib.sha256(payload).hexdigest() + "\n")
    return report


def load(path: Path = OUT) -> dict:
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != path.with_suffix(".sha256").read_text().strip():
        raise ValueError("Reliability report SHA-256 mismatch")
    report = json.loads(payload)
    if report["schema_version"] != 1:
        raise ValueError("Unsupported reliability report schema")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pace-root", type=Path, default=PACE)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    report = build(args.pace_root, args.out)
    print(json.dumps({"out": str(args.out), "comparison": report["comparison"], "drift": report["drift"]}, indent=2))


if __name__ == "__main__":
    main()
