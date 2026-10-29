"""Opt-in ML pace overlay for one stint; the deterministic simulator remains the baseline.

The race-pace model forecasts one lap ahead from recent laps. To draw a whole stint it is rolled forward on its
own predictions (autoregressive), so errors compound and the curve is a model-implied trend, not a forecast with
a stated error. Unknown context (weather, traffic) uses explicit defaults returned with the result. The overlay
never changes simulator inputs or race-time rankings. Evidence label: ``ml_prediction_rollout``.
"""
from __future__ import annotations

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from f1_racelab.ml.pace import inference
from f1_racelab.strategy.models import CIRCUIT_COMPOUNDS, CIRCUIT_FUEL, RACE_SPECS
from f1_racelab.strategy.models import Compound as SimCompound

CONTEXT_DEFAULTS = {"track_temp": 35.0, "air_temp": 25.0, "humidity": 50.0, "wind_speed": 2.0, "rainfall": 0.0,
                    "interval_ahead": 5.0, "gap_to_leader": 10.0}
CAVEAT = ("Autoregressive rollout of a next-lap model: errors compound. At decision time this model is not "
          "significantly better than persistence (docs/research/RACE_PACE_INTELLIGENCE.md). Compare shapes, "
          "not absolute seconds. Weather and traffic are assumed values.")


class StintRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    compound: SimCompound
    start_lap: int = Field(ge=1, le=100)
    laps: int = Field(ge=2, le=60)
    start_age: int = Field(default=1, ge=1, le=60, description="tyre age (laps) on the first stint lap")
    stint_number: int = Field(default=1, ge=1, le=6)
    context: dict[str, float] = Field(default_factory=dict)


def _sim_seconds(slug: str, req: StintRequest) -> list[float]:
    spec, tyre, fuel = RACE_SPECS[slug], CIRCUIT_COMPOUNDS[slug][req.compound], CIRCUIT_FUEL[slug]
    return [spec.base_lap_time_s + tyre.net_pace_offset(req.start_age + i) + fuel.lap_time_delta(req.start_lap + i)
            for i in range(req.laps)]


def stint_overlay(slug: str, req: StintRequest, model_dir=None) -> dict:
    if slug not in RACE_SPECS:
        raise KeyError(slug)
    unknown = set(req.context) - set(CONTEXT_DEFAULTS)
    if unknown:
        raise ValueError(f"unknown context keys: {sorted(unknown)}")
    ctx = {**CONTEXT_DEFAULTS, **req.context}
    sim = _sim_seconds(slug, req)
    scheduled = RACE_SPECS[slug].scheduled_laps
    times: list[float] = [sim[0]]                   # lap 1 of the stint is seeded from the simulator
    deltas: list[float] = []
    for i in range(1, req.laps):
        anchor = float(np.median(times[-3:]))
        history = [t - anchor for t in times[-5:]]
        recent_first = history[::-1] + [None] * 3
        slope = float(np.polyfit(range(len(history)), history, 1)[0]) if len(history) >= 3 else None
        feature = inference.PaceFeatures(
            anchor_seconds=anchor, lap=req.start_lap + i - 1, laps_remaining=max(scheduled - (req.start_lap + i - 1), 0),
            tyre_age_next=req.start_age + i, stint_number_next=req.stint_number, compound_next=req.compound,
            laps_in_stint=i, last1=recent_first[0], last2=recent_first[1], last3=recent_first[2], slope5=slope,
            stint_best_delta=min(history), n_clean_history=len(times), weather_age_s=30.0, intervals_age_s=5.0,
            neutral_in_last3=0, yellow_in_last1=0, laps_since_neutral=50, **ctx)
        out = inference.predict(feature, model_dir)
        times.append(out["forecast_seconds"])
        deltas.append(out["delta_seconds"])
    rows = [{"stint_lap": i + 1, "tyre_age": req.start_age + i, "sim_seconds": sim[i], "ml_seconds": times[i],
             "sim_rel": sim[i] - sim[0], "ml_rel": times[i] - times[0]} for i in range(req.laps)]
    gap = float(np.mean([abs(r["ml_rel"] - r["sim_rel"]) for r in rows]))
    return {"evidence": "ml_prediction_rollout", "baseline": "deterministic_simulator", "session_slug": slug,
            "model_id": inference.NAME, "assumed_context": ctx, "laps": rows,
            "summary": {"sim_stint_seconds": float(sum(sim)), "ml_stint_seconds": float(sum(times)),
                        "mean_abs_shape_gap_seconds": gap},
            "caveat": CAVEAT}
