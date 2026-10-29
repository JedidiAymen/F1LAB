"""Serve out-of-fold race-pace forecasts (every race scored by models fitted on earlier races only)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from f1_racelab.ml.common.contracts import read_card

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "data/processed/race_pace"
CARD = ROOT / "data/processed/models/race_pace/race_pace_lightgbm.card.json"
REPRODUCE = "uv run python -m f1_racelab.ml.pace.benchmark"
TOP_CONTRIBUTIONS = 6


class PaceUnavailable(RuntimeError):
    pass


def load(root: Path = OUT, card_path: Path = CARD) -> dict:
    needed = [root / name for name in ("predictions.parquet", "summary.json", "contributions.parquet")]
    if not all(p.is_file() for p in needed) or not card_path.is_file():
        raise PaceUnavailable(f"Race pace artifacts missing. Run: {REPRODUCE}")
    predictions = pd.read_parquet(needed[0])
    return {"predictions": predictions[predictions.model.isin(["lightgbm", "anchor_median3"])],
            "contrib": pd.read_parquet(needed[2]), "summary": json.loads(needed[1].read_text()),
            "card": read_card(card_path)}


def races(lab: dict) -> list[dict]:
    p = lab["predictions"]
    table = (p.groupby("race_id", as_index=False)
             .agg(year=("year", "first"), event=("event", "first"), circuit=("circuit", "first"),
                  laps=("lap", "max"), drivers=("driver_number", lambda v: sorted(int(x) for x in v.unique()))))
    return table.sort_values(["year", "event"]).to_dict("records")


def forecast(lab: dict, race_id: str, driver: int) -> dict:
    p = lab["predictions"]
    part = p[(p.race_id == race_id) & (p.driver_number == driver)]
    if part.empty:
        raise KeyError(f"no out-of-fold forecasts for race {race_id} driver {driver}")
    wide = part.pivot_table(index="lap", columns="model", values="pred_seconds")
    meta = part[part.model == "lightgbm"].set_index("lap")
    contrib = lab["contrib"]
    contrib = contrib[(contrib.race_id == race_id) & (contrib.driver_number == driver)].set_index("lap")
    cols = [c for c in contrib.columns if c.startswith("c_") and c != "c_bias"]
    rows = []
    for lap, row in meta.iterrows():  # `lap` is the cutoff lap L; the forecast target is lap L+1
        top = []
        if lap in contrib.index:
            values = contrib.loc[lap, cols].astype(float)
            top = [{"feature": name[2:], "seconds": float(v)}
                   for name, v in values.reindex(values.abs().sort_values(ascending=False).index)
                   .head(TOP_CONTRIBUTIONS).items()]
        rows.append({"cutoff_lap": int(lap), "target_lap": int(lap) + 1,
                     "forecast_seconds": float(row.pred_seconds), "q10_seconds": float(row.q10_seconds),
                     "q90_seconds": float(row.q90_seconds), "baseline_seconds": float(wide.loc[lap, "anchor_median3"]),
                     "actual_seconds": float(row.next_lap_seconds), "compound": row.compound_next,
                     "tyre_age": float(row.tyre_age_next), "regime": row.regime_next,
                     "green_clean": bool(row.eligible_green_next), "contributions": top})
    return {"evidence": "ml_prediction_out_of_fold", "model_id": lab["card"].model_id,
            "race_id": race_id, "driver_number": driver, "laps": rows,
            "note": "Forecasts use only data at the end of the cutoff lap; actual shown retrospectively. "
                    "Tyre compound/age are scenario inputs. Non-green laps are out of distribution."}
