"""Event-grouped, practice-phase qualifying research from cached OpenF1 data.

Each snapshot uses only features from practices completed by its phase. The
recorded cutoff is the provider's scheduled practice end, not a claim about
when the provider published its final session result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from f1_racelab.data.openf1_qualifying import RAW_ROOT
from f1_racelab.models.qualifying_backtest import (
    COMMON_FEATURES,
    audit_prequalifying_cutoff,
    prepare_dataset,
    run_backtest,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MIXED_DATA_FILE = PROJECT_ROOT / "data/processed/qualifying_mixed_2022_2023_2024_2025.parquet"
RESULT_DIR = PROJECT_ROOT / "data/processed/qualifying_phases"
PHASES: dict[str, dict[str, Any]] = {
    "after_fp1": {
        "label": "After FP1",
        "practice_session": "Practice 1",
        "baseline": "fp1",
        "baseline_column": "fp1_best_seconds",
        "features": ["fp1_gap_pct", "fp1_rank"],
    },
    "after_fp2": {
        "label": "After FP2",
        "practice_session": "Practice 2",
        "baseline": "fp2",
        "baseline_column": "fp2_best_seconds",
        "features": ["fp1_gap_pct", "fp2_gap_pct", "fp1_rank", "fp2_rank"],
    },
    "pre_qualifying": {
        "label": "Before qualifying",
        "practice_session": "Practice 3",
        "baseline": "fp3",
        "baseline_column": "fp3_best_seconds",
        "features": COMMON_FEATURES,
    },
}
PRACTICE_ORDER = ("Practice 1", "Practice 2", "Practice 3", "Qualifying")
SPLITS = (("validation", 2024), ("test", 2025))


def cached_openf1_sessions(cache_root: Path = RAW_ROOT) -> list[dict]:
    """Load session schedules already cached locally; never makes a request."""
    session_root = Path(cache_root) / "sessions"
    if not session_root.is_dir():
        raise FileNotFoundError(f"OpenF1 session cache is missing: {session_root}")
    rows: list[dict] = []
    for path in sorted(session_root.glob("*.json")):
        payload = json.loads(path.read_text())
        if not isinstance(payload, list):
            raise TypeError(f"OpenF1 session cache is not a list: {path.name}")
        rows.extend(row for row in payload if isinstance(row, dict))
    if not rows:
        raise ValueError("OpenF1 session schedule cache is empty")
    return rows


def _session_lookup(sessions: list[dict]) -> dict[tuple[int, str], dict]:
    lookup: dict[tuple[int, str], dict] = {}
    for row in sessions:
        if row.get("session_name") not in PRACTICE_ORDER:
            continue
        key = (int(row["meeting_key"]), str(row["session_name"]))
        previous = lookup.get(key)
        if previous is not None and any(
            previous.get(field) != row.get(field)
            for field in ("session_key", "date_start", "date_end")
        ):
            raise ValueError(f"Conflicting cached session schedule rows for {key}")
        lookup[key] = row
    return lookup


def _utc_timestamp(value: Any, *, field: str) -> pd.Timestamp:
    timestamp = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(timestamp):
        raise ValueError(f"OpenF1 schedule has an invalid {field}: {value!r}")
    return timestamp


def phase_event_schedule(dataset: pd.DataFrame, sessions: list[dict]) -> tuple[pd.DataFrame, str]:
    """Resolve source meeting keys to scheduled end-of-practice cutoffs.

    Only OpenF1 events are accepted so train, validation, and holdout use the
    same source. Every practice end must precede the following session start.
    """
    required = {"year", "round", "event", "provider", "source_meeting_key",
                "source_session_key", "available_at", "session"}
    missing = required - set(dataset.columns)
    if missing:
        raise ValueError(f"Dataset is missing phase schedule keys: {sorted(missing)}")
    source = dataset.loc[dataset["provider"].eq("OpenF1") & dataset["year"].isin((2023, 2024, 2025))].copy()
    if source.empty:
        raise ValueError("No OpenF1 2023–2025 source rows are available")
    if source["source_meeting_key"].isna().any():
        raise ValueError("OpenF1 phase rows require source meeting keys")
    if not source["session"].eq("Qualifying").all() or source["source_session_key"].isna().any():
        raise ValueError("Phase rows require qualifying session provenance")
    events = source[["year", "round", "event", "source_meeting_key",
                     "source_session_key", "available_at"]].drop_duplicates()
    if events.duplicated(["year", "round"]).any():
        raise ValueError("A year/round maps to multiple OpenF1 meetings")

    lookup = _session_lookup(sessions)
    scheduled_rows: list[dict] = []
    schedule_hash_rows: set[tuple[str, ...]] = set()
    for event in events.sort_values(["year", "round"], kind="stable").itertuples(index=False):
        meeting_key = int(event.source_meeting_key)
        required_sessions: dict[str, dict] = {}
        for name in PRACTICE_ORDER:
            row = lookup.get((meeting_key, name))
            if row is None or int(row.get("year", -1)) != int(event.year):
                raise ValueError(f"Missing {name} schedule for {event.year} R{event.round} (meeting {meeting_key})")
            if row.get("is_cancelled"):
                raise ValueError(f"Cancelled {name} schedule in {event.year} R{event.round}")
            start = _utc_timestamp(row.get("date_start"), field=f"{name} date_start")
            end = _utc_timestamp(row.get("date_end"), field=f"{name} date_end")
            if start >= end:
                raise ValueError(f"Invalid session start/end order for {name}")
            required_sessions[name] = row
            schedule_hash_rows.add((str(row.get("year")), str(row.get("meeting_key")),
                                    str(row.get("session_key")), name,
                                    str(row.get("date_start")), str(row.get("date_end"))))

        qualifying = required_sessions["Qualifying"]
        if int(event.source_session_key) != int(qualifying["session_key"]) or (
            _utc_timestamp(event.available_at, field="source qualifying cutoff")
            != _utc_timestamp(qualifying["date_start"], field="qualifying date_start")
        ):
            raise ValueError(f"Qualifying source provenance disagrees with schedule in {event.year} R{event.round}")

        phase_ids = ("after_fp1", "after_fp2", "pre_qualifying")
        for index, name in enumerate(PRACTICE_ORDER[:-1]):
            practice = required_sessions[name]
            following = required_sessions[PRACTICE_ORDER[index + 1]]
            scheduled_end = _utc_timestamp(practice.get("date_end"), field=f"{name} date_end")
            following_start = _utc_timestamp(following.get("date_start"), field="next session date_start")
            if scheduled_end > following_start:
                raise ValueError(f"{name} overlaps the next scheduled session in {event.year} R{event.round}")
            scheduled_rows.append({
                "year": int(event.year), "round": int(event.round), "event": str(event.event),
                "meeting_key": meeting_key, "phase": phase_ids[index],
                "practice_session": name,
                "cutoff_at_utc": scheduled_end.isoformat(),
                "next_session_start_utc": following_start.isoformat(),
                "schedule_session_key": int(practice["session_key"]),
            })

    schedule = pd.DataFrame(scheduled_rows)
    if set(schedule["phase"].unique()) != set(PHASES):
        raise ValueError("Cached schedules do not cover all three practice phases")
    canonical = "\n".join("|".join(row) for row in sorted(schedule_hash_rows)).encode()
    return schedule, hashlib.sha256(canonical).hexdigest()


def _phase_registry(dataset: pd.DataFrame, feature_names: list[str]) -> list[dict]:
    audit = audit_prequalifying_cutoff(dataset, feature_names)
    return audit["features"]


def run_phase_experiment(dataset: pd.DataFrame, sessions: list[dict]) -> dict[str, Any]:
    schedule, schedule_sha256 = phase_event_schedule(dataset, sessions)
    source = dataset.loc[dataset["provider"].eq("OpenF1") & dataset["year"].isin((2023, 2024, 2025))].copy()
    source["year"] = pd.to_numeric(source["year"], errors="raise").astype(int)
    source["round"] = pd.to_numeric(source["round"], errors="raise").astype(int)
    predictions: list[pd.DataFrame] = []
    summaries: list[pd.DataFrame] = []
    event_metrics: list[pd.DataFrame] = []
    bootstrap: list[pd.DataFrame] = []
    phase_manifest: dict[str, dict] = {}

    for key, spec in PHASES.items():
        phase_schedule = schedule.loc[schedule["phase"].eq(key)]
        model_data = source.merge(
            phase_schedule.drop(columns="phase"),
            on=["year", "round", "event"], how="inner", validate="many_to_one",
        )
        if model_data.empty or model_data[["year", "round"]].drop_duplicates().shape[0] != phase_schedule.shape[0]:
            raise ValueError(f"Incomplete source rows for {key} schedule")
        # The phase comparator is the measured best lap from that practice.
        # Missing phase measurements are excluded; they are never imputed.
        model_data = model_data.dropna(subset=[spec["baseline_column"]]).copy()
        eligible = prepare_dataset(model_data, baseline_column=spec["baseline_column"])
        field_sizes = eligible.groupby(["year", "round"])["driver"].nunique()
        if len(field_sizes) != len(phase_schedule) or (field_sizes < 5).any():
            raise ValueError(f"{key} has a weekend with fewer than five eligible measured-baseline drivers")
        result = run_backtest(
            model_data,
            train_years=(2023,),
            val_year=2024,
            test_year=2025,
            feature_cols=list(spec["features"]),
            baseline_name=spec["baseline"],
            baseline_column=spec["baseline_column"],
        )
        event_time = phase_schedule[["year", "round", "event", "cutoff_at_utc"]]
        phase_predictions = result["predictions"].merge(
            event_time, on=["year", "round", "event"], how="left", validate="many_to_one",
        )
        phase_predictions["phase"] = key
        predictions.append(phase_predictions)
        for split in ("validation", "test"):
            summary = result[f"{split}_summary"].copy()
            summary["phase"] = key
            summary["split"] = split
            summaries.append(summary)
            metrics = result[f"{split}_events"].copy()
            metrics["phase"] = key
            metrics["split"] = split
            event_metrics.append(metrics)
            interval = result[f"{split}_bootstrap"].copy()
            interval["phase"] = key
            interval["split"] = split
            bootstrap.append(interval)
        feature_registry = _phase_registry(source, list(spec["features"]))
        phase_manifest[key] = {
            "label": spec["label"],
            "practice_session": spec["practice_session"],
            "cutoff_status": "scheduled_practice_end",
            "baseline": spec["baseline"],
            "features": feature_registry,
            "selected_model": result["winner"],
            "training": {
                "years": [2023], "validation_year": 2024, "held_out_year": 2025,
                "n_training_events": result["n_training_events"],
                "n_training_rows": result["n_training_rows"],
                "n_validation_events": result["n_validation_events"],
                "n_validation_rows": result["n_validation_rows"],
                "n_test_events": result["n_test_events"],
                "n_test_rows": result["n_test_rows"],
            },
            "cutoff_coverage": {
                "events": int(phase_schedule[["year", "round"]].drop_duplicates().shape[0]),
                "minimum_utc": phase_schedule["cutoff_at_utc"].min(),
                "maximum_utc": phase_schedule["cutoff_at_utc"].max(),
            },
        }

    return {
        "phases": phase_manifest,
        "predictions": pd.concat(predictions, ignore_index=True),
        "summary": pd.concat(summaries, ignore_index=True),
        "event_metrics": pd.concat(event_metrics, ignore_index=True),
        "bootstrap": pd.concat(bootstrap, ignore_index=True),
        "source_rows": source,
        "schedule_sha256": schedule_sha256,
        "schedule_events": schedule,
    }


def write_experiment(dataset_path: Path, output_dir: Path = RESULT_DIR,
                     cache_root: Path = RAW_ROOT) -> dict[str, Any]:
    dataset_path = Path(dataset_path)
    output_dir = Path(output_dir)
    raw = pd.read_parquet(dataset_path)
    result = run_phase_experiment(raw, cached_openf1_sessions(cache_root))
    output_dir.mkdir(parents=True, exist_ok=True)
    result["predictions"].to_parquet(output_dir / "phase_predictions.parquet", index=False)
    result["summary"].to_csv(output_dir / "phase_summary.csv", index=False)
    result["event_metrics"].to_csv(output_dir / "phase_event_metrics.csv", index=False)
    result["bootstrap"].to_csv(output_dir / "phase_bootstrap.csv", index=False)
    artifact_names = (
        "phase_predictions.parquet", "phase_summary.csv",
        "phase_event_metrics.csv", "phase_bootstrap.csv",
    )
    manifest = {
        "schema_version": 1,
        "source_provider": "OpenF1",
        "source_years": [2023, 2024, 2025],
        "source_rows": len(result["source_rows"]),
        "source_dataset": str(dataset_path),
        "source_dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "source_schedule_sha256": result["schedule_sha256"],
        "selection_year": 2024,
        "held_out_year": 2025,
        "target": "q1_gap_pct",
        "evaluation_label": "final_position",
        "cutoff_contract": "scheduled_practice_end",
        "feature_observed_at": "not_recorded_individually",
        "timing_limit": (
            "cutoff_at_utc is the scheduled end of the latest included practice; "
            "the cached schedule does not establish the provider publication time of each result"
        ),
        "phase_definitions": result["phases"],
        "artifact_sha256": {
            name: hashlib.sha256((output_dir / name).read_bytes()).hexdigest()
            for name in artifact_names
        },
    }
    (output_dir / "experiment.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps({
        "source_rows": manifest["source_rows"],
        "source_dataset_sha256": manifest["source_dataset_sha256"],
        "source_schedule_sha256": manifest["source_schedule_sha256"],
        "phases": {
            key: {
                "selected_model": value["selected_model"],
                "training": value["training"],
                "cutoff_coverage": value["cutoff_coverage"],
                "validation": result["summary"].loc[
                    result["summary"]["phase"].eq(key) & result["summary"]["split"].eq("validation")
                ].to_dict(orient="records"),
                "test": result["summary"].loc[
                    result["summary"]["phase"].eq(key) & result["summary"]["split"].eq("test")
                ].to_dict(orient="records"),
            }
            for key, value in result["phases"].items()
        },
        "artifacts": manifest["artifact_sha256"],
    }, indent=2, default=str))
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=MIXED_DATA_FILE)
    parser.add_argument("--out", type=Path, default=RESULT_DIR)
    parser.add_argument("--cache", type=Path, default=RAW_ROOT)
    args = parser.parse_args()
    if not args.dataset.is_file():
        parser.error(f"Missing {args.dataset}; build the mixed qualifying dataset first")
    write_experiment(args.dataset, args.out, args.cache)


if __name__ == "__main__":
    main()
