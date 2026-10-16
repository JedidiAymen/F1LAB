"""Checksum-verified reads for the phase-aware qualifying research lab."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from f1_racelab.models.qualifying_backtest import evaluate

PHASE_KEYS = ("after_fp1", "after_fp2", "pre_qualifying")
SPLITS = ("validation", "test")
MODELS = {"ridge", "lightgbm"}
EXPECTED_FEATURES = {
    "after_fp1": {"fp1_gap_pct", "fp1_rank"},
    "after_fp2": {"fp1_gap_pct", "fp2_gap_pct", "fp1_rank", "fp2_rank"},
    "pre_qualifying": {
        "fp1_gap_pct", "fp2_gap_pct", "fp3_gap_pct", "fp1_rank", "fp2_rank", "fp3_rank",
        "fp1_to_fp3_improvement_pct", "fp2_to_fp3_improvement_pct",
    },
}
ALLOWED_SESSIONS = {
    "after_fp1": {"FP1"},
    "after_fp2": {"FP1", "FP2"},
    "pre_qualifying": {"FP1", "FP2", "FP3"},
}
ARTIFACTS = {
    "phase_predictions.parquet", "phase_summary.csv",
    "phase_event_metrics.csv", "phase_bootstrap.csv",
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _records(frame: pd.DataFrame) -> list[dict]:
    return frame.astype(object).where(pd.notna(frame), None).to_dict(orient="records")


def load_phase_prediction_lab(artifact_dir: Path) -> dict[str, Any]:
    """Load all three phase snapshots and reject incomplete or modified files."""
    root = Path(artifact_dir)
    manifest_path = root / "experiment.json"
    prediction_path = root / "phase_predictions.parquet"
    if not manifest_path.is_file() or not prediction_path.is_file():
        raise FileNotFoundError("phase-aware qualifying experiment or predictions are missing")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported phase-aware experiment schema")
    if (manifest.get("source_provider"), manifest.get("source_years")) != ("OpenF1", [2023, 2024, 2025]):
        raise ValueError("Phase experiment must use the declared OpenF1 2023–2025 source")
    if (manifest.get("selection_year"), manifest.get("held_out_year")) != (2024, 2025):
        raise ValueError("Phase experiment split does not match the 2024/2025 contract")
    if (manifest.get("target"), manifest.get("evaluation_label")) != ("q1_gap_pct", "final_position"):
        raise ValueError("Phase experiment target/label contract is invalid")
    if manifest.get("cutoff_contract") != "scheduled_practice_end":
        raise ValueError("Phase experiment has an unsupported timestamp contract")
    if manifest.get("feature_observed_at") != "not_recorded_individually":
        raise ValueError("Phase experiment overstates individual feature timestamps")
    if not _SHA256.fullmatch(str(manifest.get("source_dataset_sha256", ""))):
        raise ValueError("Phase experiment is missing the source dataset checksum")
    if not _SHA256.fullmatch(str(manifest.get("source_schedule_sha256", ""))):
        raise ValueError("Phase experiment is missing the source schedule checksum")
    hashes = manifest.get("artifact_sha256")
    if not isinstance(hashes, dict) or set(hashes) != ARTIFACTS:
        raise ValueError("Phase experiment is missing report artifact checksums")
    for name in ARTIFACTS:
        path = root / name
        if not path.is_file():
            raise FileNotFoundError(f"Phase report artifact is missing: {name}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if hashes[name] != actual:
            raise ValueError(f"Phase report artifact SHA-256 mismatch: {name}")

    definitions = manifest.get("phase_definitions")
    if not isinstance(definitions, dict) or set(definitions) != set(PHASE_KEYS):
        raise ValueError("Phase experiment does not define each forecast moment")
    predictions = pd.read_parquet(prediction_path)
    required = {
        "phase", "year", "round", "event", "driver", "model", "predicted_rank",
        "actual_rank", "final_position", "split", "cutoff_at_utc",
    }
    if not required.issubset(predictions.columns):
        raise ValueError("Phase predictions are missing required columns")
    if not set(predictions["phase"]).issubset(PHASE_KEYS):
        raise ValueError("Phase predictions contain unknown forecast moments")
    if not set(predictions["split"]).issubset(SPLITS):
        raise ValueError("Phase predictions contain unknown evaluation splits")
    if predictions.duplicated(["phase", "year", "round", "driver", "model", "split"]).any():
        raise ValueError("Phase predictions contain duplicate driver/model rows")
    if predictions[["predicted_rank", "actual_rank", "final_position", "cutoff_at_utc"]].isna().any().any():
        raise ValueError("Phase predictions contain missing ranks or cutoffs")
    ranks = predictions[["predicted_rank", "actual_rank", "final_position"]].to_numpy(dtype=float)
    if (ranks < 1).any() or not (ranks % 1 == 0).all():
        raise ValueError("Phase predictions contain invalid ranks")
    predictions["cutoff_at_utc"] = pd.to_datetime(predictions["cutoff_at_utc"], utc=True, errors="raise")

    summary_table = pd.read_csv(root / "phase_summary.csv")
    event_table = pd.read_csv(root / "phase_event_metrics.csv")
    bootstrap_table = pd.read_csv(root / "phase_bootstrap.csv")
    summaries: dict[str, dict[str, list[dict]]] = {}
    uncertainty: dict[str, dict[str, list[dict]]] = {}
    events: dict[str, list[dict]] = {}
    for phase in PHASE_KEYS:
        definition = definitions[phase]
        baseline = definition.get("baseline")
        if baseline != dict(zip(PHASE_KEYS, ("fp1", "fp2", "fp3"), strict=True))[phase]:
            raise ValueError(f"Invalid baseline in {phase}")
        training = definition.get("training", {})
        if (training.get("years"), training.get("validation_year"), training.get("held_out_year")) != ([2023], 2024, 2025):
            raise ValueError(f"Invalid chronological training contract in {phase}")
        expected_models = {baseline, *MODELS}
        if definition.get("selected_model") not in expected_models:
            raise ValueError(f"Invalid selected model in {phase}")
        if not definition.get("features") or definition.get("cutoff_status") != "scheduled_practice_end":
            raise ValueError(f"Phase definition is incomplete: {phase}")
        features = definition["features"]
        if {feature.get("name") for feature in features} != EXPECTED_FEATURES[phase]:
            raise ValueError(f"{phase} feature registry does not match its phase allowlist")
        if any(not feature.get("source_sessions")
               or not set(feature["source_sessions"]).issubset(ALLOWED_SESSIONS[phase])
               for feature in features):
            raise ValueError(f"{phase} includes a feature from a future practice session")
        if predictions.loc[predictions["phase"].eq(phase), "model"].isna().any():
            raise ValueError(f"Missing model labels in {phase}")
        for split, year in (("validation", 2024), ("test", 2025)):
            part = predictions.loc[predictions["phase"].eq(phase) & predictions["split"].eq(split)]
            if part.empty or set(part["year"].astype(int)) != {year}:
                raise ValueError(f"{phase} {split} predictions do not match year {year}")
            if set(part["model"]) != expected_models:
                raise ValueError(f"{phase} {split} predictions do not cover all models")
            driver_models = part.groupby(["year", "round", "driver"])["model"].nunique()
            if not driver_models.eq(len(expected_models)).all():
                raise ValueError(f"{phase} {split} has incomplete driver/model coverage")
            if (part.groupby(["year", "round", "driver"])[["actual_rank", "final_position"]]
                    .nunique().ne(1).any().any()):
                raise ValueError(f"{phase} {split} has conflicting actual classifications")
            event_counts = part.groupby(["year", "round"])["driver"].nunique()
            if (event_counts < 5).any():
                raise ValueError(f"{phase} {split} contains an undersized weekend")
            for _, model_event in part.groupby(["year", "round", "model"]):
                expected_ranks = list(range(1, len(model_event) + 1))
                if (sorted(model_event["predicted_rank"].tolist()) != expected_ranks
                        or sorted(model_event["actual_rank"].tolist()) != expected_ranks
                        or model_event["final_position"].duplicated().any()):
                    raise ValueError(f"{phase} {split} contains invalid event rank permutations")
            training = definition["training"]
            count_stem = "validation" if split == "validation" else "test"
            if (len(event_counts) != training[f"n_{count_stem}_events"]
                    or int(event_counts.sum()) != training[f"n_{count_stem}_rows"]):
                raise ValueError(f"{phase} {split} coverage disagrees with its manifest")
            actual_metrics = evaluate(part)
            reported_metrics = event_table.loc[
                event_table["phase"].eq(phase) & event_table["split"].eq(split)
            ]
            keys = ["model", "year", "round"]
            compared = actual_metrics.merge(reported_metrics, on=keys, how="outer",
                                             suffixes=("_actual", "_report"),
                                             validate="one_to_one", indicator=True)
            if not compared["_merge"].eq("both").all():
                raise ValueError(f"{phase} {split} event metrics coverage disagrees with predictions")
            if not compared["event_actual"].eq(compared["event_report"]).all():
                raise ValueError(f"{phase} {split} event metric names disagree with predictions")
            for metric in ("drivers", "position_mae", "spearman", "pole_hit", "top3_overlap"):
                if not np.allclose(compared[f"{metric}_actual"], compared[f"{metric}_report"],
                                   rtol=1e-10, atol=1e-10):
                    raise ValueError(f"{phase} {split} event metrics disagree with predictions: {metric}")

        summaries[phase] = {}
        uncertainty[phase] = {}
        for split in SPLITS:
            summary = summary_table.loc[summary_table["phase"].eq(phase) & summary_table["split"].eq(split)]
            if set(summary["model"]) != expected_models or summary["position_mae"].isna().any():
                raise ValueError(f"{phase} {split} summary has incomplete model metrics")
            reported_events = event_table.loc[event_table["phase"].eq(phase) & event_table["split"].eq(split)]
            for model in expected_models:
                model_events = reported_events.loc[reported_events["model"].eq(model)]
                model_summary = summary.loc[summary["model"].eq(model)]
                if len(model_summary) != 1 or int(model_summary.iloc[0]["events"]) != len(model_events):
                    raise ValueError(f"{phase} {split} summary event counts disagree")
                for metric, event_metric in (("position_mae", "position_mae"), ("spearman", "spearman"),
                                              ("pole_hit_rate", "pole_hit"), ("top3_overlap", "top3_overlap")):
                    if not np.isclose(float(model_summary.iloc[0][metric]), model_events[event_metric].mean(),
                                      rtol=1e-10, atol=1e-10):
                        raise ValueError(f"{phase} {split} summary metrics disagree with event metrics")
            summaries[phase][split] = _records(summary)
            interval = bootstrap_table.loc[
                bootstrap_table["phase"].eq(phase) & bootstrap_table["split"].eq(split)
            ]
            if set(interval["baseline"]) != {baseline}:
                raise ValueError(f"{phase} {split} bootstrap does not use its practice baseline")
            if set(interval["model"]) != MODELS or len(interval) != len(MODELS):
                raise ValueError(f"{phase} {split} bootstrap has incomplete candidate coverage")
            if (not np.isfinite(interval[["mean_delta", "ci_low", "ci_high"]].to_numpy(dtype=float)).all()
                    or (interval["ci_low"] > interval["ci_high"]).any()):
                raise ValueError(f"{phase} {split} bootstrap has invalid intervals")
            indexed_summary = summary.set_index("model")
            for row in interval.itertuples(index=False):
                delta = indexed_summary.loc[row.model, "position_mae"] - indexed_summary.loc[baseline, "position_mae"]
                if not np.isclose(row.mean_delta, delta, rtol=1e-10, atol=1e-10):
                    raise ValueError(f"{phase} {split} bootstrap point estimate disagrees with event metrics")
                if row.events != indexed_summary.loc[row.model, "events"]:
                    raise ValueError(f"{phase} {split} bootstrap event count disagrees")
            uncertainty[phase][split] = _records(interval)
        validation = summaries[phase]["validation"]
        winner = min(validation, key=lambda row: (float(row["position_mae"]), row["model"]))["model"]
        if winner != definition["selected_model"]:
            raise ValueError(f"Selected model does not match 2024 validation for {phase}")

        event_index = (predictions.loc[predictions["phase"].eq(phase),
                                       ["year", "round", "event", "split", "cutoff_at_utc"]]
                       .drop_duplicates().sort_values(["year", "round"], kind="stable"))
        if event_index.duplicated(["year", "round", "split"]).any():
            raise ValueError(f"Event cutoff is inconsistent within {phase}")
        events[phase] = _records(event_index)

    return {
        "experiment": manifest,
        "definitions": definitions,
        "summaries": summaries,
        "uncertainty": uncertainty,
        "events": events,
        "_predictions": predictions,
        "_event_metrics": event_table,
    }


def phase_prediction_event(lab: dict, *, phase: str, year: int, round_no: int, split: str) -> dict:
    """Project ranks and cutoff metadata for one retrospective weekend."""
    if phase not in PHASE_KEYS or split not in SPLITS:
        raise ValueError("Unknown phase or evaluation split")
    predictions: pd.DataFrame = lab["_predictions"]
    event = predictions.loc[
        predictions["phase"].eq(phase) & predictions["year"].eq(year)
        & predictions["round"].eq(round_no) & predictions["split"].eq(split)
    ]
    if event.empty:
        raise KeyError(f"No {phase} {split} prediction for {year} round {round_no}")
    names = event["event"].drop_duplicates().tolist()
    cutoffs = event["cutoff_at_utc"].drop_duplicates().tolist()
    if len(names) != 1 or len(cutoffs) != 1:
        raise ValueError("Weekend event name or scheduled cutoff is inconsistent")
    definition = lab["definitions"][phase]
    models = [definition["baseline"], "ridge", "lightgbm"]
    rankings: list[dict[str, Any]] = []
    for driver, part in event.groupby("driver", sort=True):
        predicted = dict(zip(part["model"], part["predicted_rank"], strict=False))
        actual = part["actual_rank"].drop_duplicates().tolist()
        qualifying_position = part["final_position"].drop_duplicates().tolist()
        if set(predicted) != set(models) or len(actual) != 1 or len(qualifying_position) != 1:
            raise ValueError(f"Incomplete or conflicting ranks for {driver}")
        rankings.append({"driver": str(driver),
                         "predicted_rank": {name: int(predicted[name]) for name in models},
                         "actual_rank": int(actual[0]),
                         "qualifying_position": int(qualifying_position[0])})
    selected_model = str(definition["selected_model"])
    rankings.sort(key=lambda row: (row["predicted_rank"][selected_model], row["driver"]))
    metrics = lab["_event_metrics"]
    metric_rows = metrics.loc[
        metrics["phase"].eq(phase) & metrics["year"].eq(year)
        & metrics["round"].eq(round_no) & metrics["split"].eq(split)
    ]
    return {
        "phase": phase, "year": year, "round": round_no, "event": names[0], "split": split,
        "cutoff_at_utc": cutoffs[0].isoformat(), "selected_model": selected_model,
        "models": models, "rankings": rankings, "metrics": _records(metric_rows),
    }
