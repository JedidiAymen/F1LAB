"""Read and validate local artifacts for the historical qualifying lab."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from f1_racelab.models.qualifying_backtest import COMMON_FEATURES

SUPPORTED_MODELS = ("fp3", "ridge", "lightgbm")
SUPPORTED_SPLITS = ("validation", "test")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _records(frame: pd.DataFrame) -> list[dict]:
    """Convert a small report table to JSON-safe records."""
    return frame.astype(object).where(pd.notna(frame), None).to_dict(orient="records")


def load_prediction_lab(artifact_dir: Path) -> dict:
    """Load the reproducible pre-qualifying report and fail closed on bad data."""
    root = Path(artifact_dir)
    experiment_path = root / "experiment.json"
    predictions_path = root / "predictions.parquet"
    if not experiment_path.is_file() or not predictions_path.is_file():
        raise FileNotFoundError("prediction experiment or predictions artifact is missing")
    experiment = json.loads(experiment_path.read_text())
    if (experiment.get("selection_year"), experiment.get("held_out_year")) != (2024, 2025):
        raise ValueError("Prediction experiment split does not match the recorded 2024/2025 contract")
    if (experiment.get("target"), experiment.get("evaluation_label")) != ("q1_gap_pct", "final_position"):
        raise ValueError("Prediction experiment target/label contract is invalid")
    if experiment.get("feature_set") != "common" or experiment.get("features") != COMMON_FEATURES:
        raise ValueError("Prediction Lab requires the recorded common-feature experiment")
    if experiment.get("winner") not in SUPPORTED_MODELS:
        raise ValueError("Prediction experiment selected an unsupported model")
    if experiment.get("dataset_sha256") is None or not _SHA256.fullmatch(experiment["dataset_sha256"]):
        raise ValueError("Prediction experiment is missing a valid source dataset SHA-256")
    recorded_predictions_sha = experiment.get("predictions_sha256")
    actual_predictions_sha = hashlib.sha256(predictions_path.read_bytes()).hexdigest()
    if recorded_predictions_sha != actual_predictions_sha:
        raise ValueError("Prediction Parquet SHA-256 does not match the experiment manifest")
    artifact_names = {
        "predictions.parquet", "validation_summary.csv", "test_summary.csv",
        "validation_bootstrap.csv", "test_bootstrap.csv",
        "validation_events.csv", "test_events.csv",
    }
    artifact_hashes = experiment.get("artifact_sha256")
    if not isinstance(artifact_hashes, dict) or set(artifact_hashes) != artifact_names:
        raise ValueError("Prediction experiment is missing its report artifact checksums")
    if artifact_hashes["predictions.parquet"] != recorded_predictions_sha:
        raise ValueError("Prediction artifact checksums disagree")
    for name in artifact_names:
        path = root / name
        if not path.is_file():
            raise FileNotFoundError(f"Prediction report artifact is missing: {name}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if artifact_hashes[name] != digest:
            raise ValueError(f"Prediction report artifact SHA-256 mismatch: {name}")
    cutoff = experiment.get("cutoff_audit")
    if not isinstance(cutoff, dict) or cutoff.get("prediction_cutoff") != "immediately_before_qualifying":
        raise ValueError("Prediction experiment is missing its pre-qualifying cutoff audit")
    if cutoff.get("feature_observed_at") != "not_recorded_individually":
        raise ValueError("Prediction experiment has unsupported per-feature timing metadata")
    if not cutoff.get("feature_allowlist_passed") or cutoff.get("forbidden_target_fields_in_features"):
        raise ValueError("Prediction experiment failed its target-leakage allowlist")
    source_timestamp = cutoff.get("source_timestamp")
    if not isinstance(source_timestamp, dict) or source_timestamp.get("status") != "scheduled_qualifying_start":
        raise ValueError("Prediction experiment is missing its scheduled qualifying cutoff")

    predictions = pd.read_parquet(predictions_path)
    required = {"year", "round", "event", "driver", "model", "predicted_rank", "actual_rank", "split"}
    if not required.issubset(predictions.columns):
        raise ValueError("Prediction artifact is missing required columns")
    if predictions["model"].isna().any() or not set(predictions["model"]).issubset(SUPPORTED_MODELS):
        raise ValueError("Prediction artifact contains unsupported model labels")
    if predictions["split"].isna().any() or not set(predictions["split"]).issubset(SUPPORTED_SPLITS):
        raise ValueError("Prediction artifact contains unsupported split labels")
    if predictions.duplicated(["year", "round", "driver", "model", "split"]).any():
        raise ValueError("Prediction artifact contains duplicate driver/model rows")
    if predictions[["predicted_rank", "actual_rank"]].isna().any().any():
        raise ValueError("Prediction artifact contains missing ranks")
    ranks = predictions[["predicted_rank", "actual_rank"]].to_numpy(dtype=float)
    if (ranks < 1).any() or not (ranks % 1 == 0).all():
        raise ValueError("Prediction artifact contains invalid rank values")

    summaries = {}
    uncertainty = {}
    event_metrics = {}
    for split, stem in (("validation", "validation"), ("test", "test")):
        summary_path = root / f"{stem}_summary.csv"
        bootstrap_path = root / f"{stem}_bootstrap.csv"
        event_path = root / f"{stem}_events.csv"
        if not all(path.is_file() for path in (summary_path, bootstrap_path, event_path)):
            raise FileNotFoundError(f"prediction {split} metrics are missing")
        summaries[split] = _records(pd.read_csv(summary_path))
        uncertainty[split] = _records(pd.read_csv(bootstrap_path))
        event_metrics[split] = pd.read_csv(event_path)
        if {row.get("model") for row in summaries[split]} != set(SUPPORTED_MODELS):
            raise ValueError(f"Prediction {split} metrics do not cover every supported model")
        if any(not pd.notna(row.get("position_mae")) for row in summaries[split]):
            raise ValueError(f"Prediction {split} summary has missing model metrics")
        if not {"year", "round", "model", "position_mae"}.issubset(event_metrics[split].columns):
            raise ValueError(f"Prediction {split} event metrics are missing required fields")

    validation_winner = min(
        summaries["validation"], key=lambda row: (float(row["position_mae"]), row["model"]),
    )["model"]
    if validation_winner != experiment["winner"]:
        raise ValueError("Selected model does not match the 2024 validation metrics")

    for split, year, row_key, event_key in (
        ("validation", experiment["selection_year"], "n_validation_rows", "n_validation_events"),
        ("test", experiment["held_out_year"], "n_test_rows", "n_test_events"),
    ):
        part = predictions.loc[predictions["split"].eq(split)]
        driver_rows = part[["year", "round", "driver"]].drop_duplicates()
        event_rows = part[["year", "round"]].drop_duplicates()
        if set(part["year"]) != {year}:
            raise ValueError(f"Prediction {split} records do not match the declared season")
        if len(driver_rows) != experiment[row_key] or len(event_rows) != experiment[event_key]:
            raise ValueError(f"Prediction {split} coverage does not match the experiment manifest")

    event_index = (predictions[["year", "round", "event", "split"]]
                   .drop_duplicates().sort_values(["year", "round"], kind="stable"))
    events = _records(event_index)
    if not events or not {row["split"] for row in events}.issubset(SUPPORTED_SPLITS):
        raise ValueError("Prediction artifact has no valid held-out events")
    return {"experiment": experiment, "summaries": summaries,
            "uncertainty": uncertainty, "events": events,
            "_predictions": predictions, "_event_metrics": event_metrics}


def prediction_event(lab: dict, *, year: int, round_no: int, split: str) -> dict:
    """Project one historical weekend without exposing the Q1 target column."""
    if split not in SUPPORTED_SPLITS:
        raise ValueError(f"split must be one of {SUPPORTED_SPLITS}")
    predictions: pd.DataFrame = lab["_predictions"]
    event = predictions.loc[
        predictions["year"].eq(year)
        & predictions["round"].eq(round_no)
        & predictions["split"].eq(split)
    ]
    if event.empty:
        raise KeyError(f"No {split} prediction for {year} round {round_no}")
    event_names = event["event"].drop_duplicates().tolist()
    if len(event_names) != 1:
        raise ValueError("Prediction artifact maps a weekend to multiple event names")
    rankings: list[dict[str, Any]] = []
    for driver, part in event.groupby("driver", sort=True):
        models = dict(zip(part["model"], part["predicted_rank"], strict=False))
        if set(models) != set(SUPPORTED_MODELS):
            raise ValueError(f"Incomplete model predictions for {driver}")
        actual = part["actual_rank"].drop_duplicates().tolist()
        if len(actual) != 1:
            raise ValueError(f"Conflicting actual ranks for {driver}")
        rankings.append({"driver": str(driver),
                         "predicted_rank": {name: int(models[name]) for name in SUPPORTED_MODELS},
                         "actual_rank": int(actual[0])})
    selected_model = lab["experiment"]["winner"]
    rankings.sort(key=lambda row: (row["predicted_rank"][selected_model], row["driver"]))

    metrics = lab["_event_metrics"][split]
    metric_rows = metrics.loc[metrics["year"].eq(year) & metrics["round"].eq(round_no)]
    return {"year": year, "round": round_no, "event": event_names[0], "split": split,
            "rankings": rankings, "metrics": _records(metric_rows)}
