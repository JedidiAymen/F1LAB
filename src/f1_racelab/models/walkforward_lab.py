"""Serve walk-forward qualifying forecasts (probabilities included) from artifacts.

Fails closed: the predictions Parquet must match the SHA-256 recorded in
``experiment.json``. Target columns of the evaluated event (Q1 pace) are never
returned; ``actual_rank`` is labelled retrospective scoring by the UI.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from f1_racelab.models.qualifying_walkforward import MODELS

REQUIRED = ("experiment.json", "predictions.parquet", "summary.csv", "bootstrap.csv", "reliability.csv")


def _records(frame: pd.DataFrame) -> list[dict]:
    return frame.astype(object).where(pd.notna(frame), None).to_dict(orient="records")


def load_walkforward_lab(root: Path) -> dict:
    root = Path(root)
    for name in REQUIRED:
        if not (root / name).is_file():
            raise FileNotFoundError(f"walk-forward artifact missing: {name}")
    experiment = json.loads((root / "experiment.json").read_text())
    digest = hashlib.sha256((root / "predictions.parquet").read_bytes()).hexdigest()
    if digest != experiment.get("predictions_sha256"):
        raise ValueError("walk-forward predictions SHA-256 does not match the experiment manifest")
    if experiment.get("candidate") != "ensemble" or tuple(experiment.get("models", ())) != MODELS:
        raise ValueError("walk-forward model contract mismatch")
    predictions = pd.read_parquet(root / "predictions.parquet")
    predictions = predictions.loc[predictions.year.isin(experiment["evaluated_years"])]
    events = (predictions.loc[predictions.model == "ensemble", ["year", "round", "event"]]
              .drop_duplicates().sort_values(["year", "round"]))
    return {
        "experiment": experiment,
        "summary": _records(pd.read_csv(root / "summary.csv")),
        "bootstrap": _records(pd.read_csv(root / "bootstrap.csv")),
        "reliability": _records(pd.read_csv(root / "reliability.csv")),
        "events": _records(events),
        "predictions": predictions,
    }


def walkforward_event(lab: dict, *, year: int, round_no: int) -> dict:
    part = lab["predictions"]
    part = part.loc[(part.year == year) & (part["round"] == round_no)]
    if part.empty:
        raise KeyError(f"no walk-forward event {year} R{round_no}")
    ranks = part.pivot(index="driver", columns="model", values="predicted_rank")
    ens = part.loc[part.model == "ensemble"].set_index("driver")
    drivers = []
    for driver, row in ens.sort_values("predicted_rank").iterrows():
        drivers.append({
            "driver": driver,
            "predicted_rank": {m: int(ranks.loc[driver, m]) for m in MODELS},
            "actual_rank": int(row["actual_rank"]),
            **{k: (None if pd.isna(row[k]) else float(row[k]))
               for k in ("p_pole", "p_top3", "expected_rank", "rank_p10", "rank_p90", "sigma")},
        })
    return {"year": year, "round": round_no, "event": str(part["event"].iloc[0]),
            "probabilistic": bool(ens["p_pole"].notna().all()), "drivers": drivers}
