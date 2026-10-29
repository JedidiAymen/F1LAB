"""Versioned inference for the saved race-pace LightGBM bundle.

Input is one validated feature vector (the card's feature schema) plus ``anchor_seconds`` (median of the
last three clean laps). Output is the forecast lap time for lap L+1, a raw q10/q90 interval and the model
version. The artifact is loaded only through the SHA-256-checked registry, from a trusted local path, and
rejected if installed library versions differ from those recorded in its card.

Caveats: the served bundle is fitted on every available green lap (including 2026), so its accuracy is the
walk-forward figure in the card, not an in-sample one. The interval is the raw quantile output (about 75% for
an 80% target); it is not valid on safety-car / VSC laps.
"""
from __future__ import annotations

from functools import lru_cache
from importlib import metadata
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from f1_racelab.ml.common.registry import ArtifactUnavailable, load_artifact

ROOT = Path(__file__).resolve().parents[4]
MODEL_DIR = ROOT / "data/processed/models/race_pace"
NAME = "race_pace_lightgbm"
REPRODUCE = "uv run python -m f1_racelab.ml.pace.benchmark"
API_VERSION = "v1"
CHECKED_LIBRARIES = ("lightgbm", "numpy", "pandas", "scikit-learn")
Compound = Literal["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET", "UNKNOWN"]


class PaceFeatures(BaseModel):
    """Strict request schema; field names equal ``dataset.NUMERIC`` + ``compound_next``."""
    model_config = ConfigDict(extra="forbid")

    anchor_seconds: float = Field(gt=30, lt=300, description="median of last 3 clean laps, s")
    lap: float = Field(ge=1, le=100)
    laps_remaining: float = Field(ge=0, le=100)
    tyre_age_next: float = Field(ge=0, le=80)
    stint_number_next: float = Field(ge=1, le=8)
    compound_next: Compound
    laps_in_stint: float = Field(ge=0, le=80)
    last1: float | None = Field(default=None, ge=-30, le=60, description="null = not enough clean history")
    last2: float | None = Field(default=None, ge=-30, le=60, description="null = not enough clean history")
    last3: float | None = Field(default=None, ge=-30, le=60, description="null = not enough clean history")
    slope5: float | None = Field(default=None, ge=-5, le=5, description="null = not enough clean history")
    stint_best_delta: float | None = Field(default=None, ge=-30, le=60, description="null = not enough clean history")
    n_clean_history: float = Field(ge=0, le=100)
    track_temp: float = Field(ge=-10, le=80)
    air_temp: float = Field(ge=-10, le=60)
    humidity: float = Field(ge=0, le=100)
    wind_speed: float = Field(ge=0, le=40)
    rainfall: float = Field(ge=0, le=1)
    weather_age_s: float = Field(ge=0)
    interval_ahead: float = Field(ge=0, le=600)
    gap_to_leader: float = Field(ge=0, le=6000)
    intervals_age_s: float = Field(ge=0)
    neutral_in_last3: float = Field(ge=0, le=3)
    yellow_in_last1: float = Field(ge=0, le=1)
    laps_since_neutral: float = Field(ge=0, le=50)


def assert_schema_matches(card) -> None:
    """The request model must cover exactly the features the card says the model was trained on."""
    expected = {f.name for f in card.features}
    provided = set(PaceFeatures.model_fields) - {"anchor_seconds"}
    if expected != provided:
        raise ArtifactUnavailable(f"Feature schema mismatch: card-only={sorted(expected - provided)}, "
                                  f"request-only={sorted(provided - expected)}. Retrain: {REPRODUCE}")


def assert_versions(card) -> None:
    for name in CHECKED_LIBRARIES:
        trained = card.dependencies.get(name)
        try:
            installed = metadata.version(name)
        except metadata.PackageNotFoundError:
            installed = "not-installed"
        if trained != installed:
            raise ArtifactUnavailable(f"{name} version mismatch: trained with {trained}, installed {installed}. "
                                      f"Retrain: {REPRODUCE}")


@lru_cache(maxsize=2)
def load(model_dir: Path = MODEL_DIR):
    bundle, card = load_artifact(model_dir, NAME, reproduce=REPRODUCE)
    assert_schema_matches(card)
    assert_versions(card)
    return bundle, card


def predict(features: PaceFeatures, model_dir: Path | None = None) -> dict:
    bundle, card = load(model_dir or MODEL_DIR)
    row = {k: (np.nan if v is None else v) for k, v in features.model_dump().items()}
    anchor = row.pop("anchor_seconds")
    out = bundle.predict(pd.DataFrame([row]))
    delta, low, high = (float(out[k][0]) for k in ("median", "q10", "q90"))
    return {"api_version": API_VERSION, "model_id": card.model_id, "model_version": card.version,
            "dataset_fingerprint": card.dataset_fingerprint,
            "forecast_seconds": anchor + delta, "q10_seconds": anchor + low, "q90_seconds": anchor + high,
            "delta_seconds": delta, "interval": {"nominal": 0.8, "calibration": "raw quantile (not conformalized)"},
            "evidence": "ml_prediction",
            "warnings": (["rainfall flagged: model is weak on wet running"] if features.rainfall > 0 else [])
            + (["neutralised lap: forecast is out of distribution"] if features.neutral_in_last3 > 0
               or features.yellow_in_last1 > 0 else [])}
