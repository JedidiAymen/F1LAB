"""Phase cutoff, chronological model and API projection contracts."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from f1_racelab.api import create_app
from f1_racelab.models.qualifying_backtest import evaluate
from f1_racelab.models.qualifying_phase_lab import load_phase_prediction_lab
from f1_racelab.models.qualifying_phases import (
    PHASES,
    phase_event_schedule,
    run_phase_experiment,
)


def _fake_rows() -> tuple[pd.DataFrame, list[dict]]:
    rng = np.random.default_rng(2026)
    rows: list[dict] = []
    sessions: list[dict] = []
    for year, count in ((2023, 8), (2024, 5), (2025, 5)):
        for round_no in range(1, count + 1):
            meeting = year * 100 + round_no
            event = f"Grand Prix {round_no}"
            base = datetime(year, 3, 1, tzinfo=UTC) + timedelta(days=round_no * 7)
            starts = [base + timedelta(hours=10), base + timedelta(hours=15),
                      base + timedelta(days=1, hours=10), base + timedelta(days=1, hours=15)]
            for key, (name, start) in enumerate(zip(
                ("Practice 1", "Practice 2", "Practice 3", "Qualifying"), starts, strict=True,
            ), start=1):
                sessions.append({
                    "year": year, "meeting_key": meeting, "session_key": meeting * 10 + key,
                    "session_name": name, "date_start": start.isoformat(),
                    "date_end": (start + timedelta(hours=1)).isoformat(),
                })
            for driver_no in range(8):
                pace = driver_no * 0.07 + rng.normal(0, 0.004)
                rows.append({
                    "year": year, "round": round_no, "event": event,
                    "provider": "OpenF1", "source_meeting_key": meeting,
                    "source_session_key": meeting * 10 + 4,
                    "available_at": starts[3].isoformat(), "session": "Qualifying",
                    "driver": f"D{driver_no:02d}",
                    "fp1_best_seconds": 80 + pace + 0.06,
                    "fp2_best_seconds": 80 + pace + 0.03,
                    "fp3_best_seconds": 80 + pace,
                    "fp1_gap_pct": pace + 0.06, "fp2_gap_pct": pace + 0.03,
                    "fp3_gap_pct": pace,
                    "fp1_rank": driver_no + 1, "fp2_rank": driver_no + 1,
                    "fp3_rank": driver_no + 1,
                    "q1_gap_pct": max(0, pace + rng.normal(0, 0.005)),
                    "final_position": driver_no + 1,
                })
    return pd.DataFrame(rows), sessions


def _write_phase_artifacts(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    rows = []
    summary = []
    event_metrics = []
    bootstrap = []
    definitions = {}
    phase_feature_names = {
        "after_fp1": ("fp1_gap_pct", "fp1_rank"),
        "after_fp2": ("fp1_gap_pct", "fp2_gap_pct", "fp1_rank", "fp2_rank"),
        "pre_qualifying": (
            "fp1_gap_pct", "fp2_gap_pct", "fp3_gap_pct", "fp1_rank", "fp2_rank", "fp3_rank",
            "fp1_to_fp3_improvement_pct", "fp2_to_fp3_improvement_pct",
        ),
    }
    for phase, baseline in (("after_fp1", "fp1"), ("after_fp2", "fp2"),
                            ("pre_qualifying", "fp3")):
        definitions[phase] = {
            "label": phase, "practice_session": "Practice 1", "cutoff_status": "scheduled_practice_end",
            "baseline": baseline, "features": [
                {"name": name, "unit": "feature unit",
                 "source_sessions": [session.upper() for session in ("fp1", "fp2", "fp3")
                                     if session in name]}
                for name in phase_feature_names[phase]
            ],
            "selected_model": "ridge",
            "training": {"years": [2023], "validation_year": 2024, "held_out_year": 2025,
                         "n_training_events": 8, "n_training_rows": 40, "n_validation_events": 1,
                         "n_validation_rows": 5, "n_test_events": 1, "n_test_rows": 5},
            "cutoff_coverage": {"events": 2, "minimum_utc": "2024-03-01T11:00:00+00:00",
                                "maximum_utc": "2025-03-01T11:00:00+00:00"},
        }
        for split, year, cutoff in (("validation", 2024, "2024-03-01T11:00:00+00:00"),
                                    ("test", 2025, "2025-03-01T11:00:00+00:00")):
            for driver_no in range(5):
                for model, rank in ((baseline, (driver_no + 1) % 5 + 1), ("ridge", driver_no + 1),
                                    ("lightgbm", 5 - driver_no)):
                    rows.append({"phase": phase, "year": year, "round": 1,
                                 "event": "Fixture Grand Prix", "driver": f"D{driver_no}",
                                 "model": model, "predicted_rank": rank,
                                 "actual_rank": driver_no + 1, "split": split,
                                 "final_position": driver_no + 2,
                                 "cutoff_at_utc": cutoff})
            all_rows = pd.DataFrame(rows)
            metrics = evaluate(all_rows.loc[all_rows.phase.eq(phase) & all_rows.split.eq(split)])
            for metric in metrics.to_dict("records"):
                summary.append({"phase": phase, "split": split, "model": metric["model"],
                                "events": 1, "position_mae": metric["position_mae"],
                                "spearman": metric["spearman"], "pole_hit_rate": metric["pole_hit"],
                                "top3_overlap": metric["top3_overlap"]})
                event_metrics.append({**metric, "phase": phase, "split": split})
            for model in ("ridge", "lightgbm"):
                indexed = metrics.set_index("model")
                delta = indexed.loc[model, "position_mae"] - indexed.loc[baseline, "position_mae"]
                bootstrap.append({"phase": phase, "split": split, "baseline": baseline,
                                  "model": model, "mean_delta": delta, "ci_low": delta,
                                  "ci_high": delta, "events": 1})
    pd.DataFrame(rows).to_parquet(root / "phase_predictions.parquet", index=False)
    pd.DataFrame(summary).to_csv(root / "phase_summary.csv", index=False)
    pd.DataFrame(event_metrics).to_csv(root / "phase_event_metrics.csv", index=False)
    pd.DataFrame(bootstrap).to_csv(root / "phase_bootstrap.csv", index=False)
    artifact_names = (
        "phase_predictions.parquet", "phase_summary.csv",
        "phase_event_metrics.csv", "phase_bootstrap.csv",
    )
    manifest = {
        "schema_version": 1, "source_provider": "OpenF1", "source_years": [2023, 2024, 2025],
        "source_rows": 50, "source_dataset_sha256": "a" * 64, "source_schedule_sha256": "b" * 64,
        "selection_year": 2024, "held_out_year": 2025, "target": "q1_gap_pct",
        "evaluation_label": "final_position", "cutoff_contract": "scheduled_practice_end",
        "feature_observed_at": "not_recorded_individually",
        "timing_limit": "Scheduled times only.", "phase_definitions": definitions,
        "artifact_sha256": {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                            for name in artifact_names},
    }
    (root / "experiment.json").write_text(json.dumps(manifest))


def test_phase_schedule_uses_scheduled_practice_end_and_single_provider():
    data, sessions = _fake_rows()
    schedule, digest = phase_event_schedule(data, sessions)
    assert len(schedule) == 18 * 3
    assert set(schedule.phase) == set(PHASES)
    assert schedule.cutoff_at_utc.notna().all()
    assert len(digest) == 64
    with pytest.raises(ValueError, match="overlaps"):
        broken = [dict(row) for row in sessions]
        next(item for item in broken if item["session_name"] == "Practice 2")["date_start"] = (
            "2023-03-08T10:30:00+00:00"
        )
        phase_event_schedule(data, broken)
    with pytest.raises(ValueError, match="OpenF1"):
        phase_event_schedule(data.assign(provider="FastF1"), sessions)
    with pytest.raises(ValueError, match="provenance disagrees"):
        phase_event_schedule(data.assign(source_session_key=-1), sessions)
    undersized = data.copy()
    indices = undersized.loc[undersized.year.eq(2023) & undersized["round"].eq(1)].index[4:]
    undersized.loc[indices, "q1_gap_pct"] = np.nan
    with pytest.raises(ValueError, match="fewer than five eligible"):
        run_phase_experiment(undersized, sessions)


def test_phase_backtest_has_legal_features_and_chronological_holdout():
    data, sessions = _fake_rows()
    result = run_phase_experiment(data, sessions)
    predictions = result["predictions"]
    assert set(result["phases"]) == set(PHASES)
    assert set(predictions.year) == {2024, 2025}
    assert predictions.loc[predictions.split.eq("test"), "year"].eq(2025).all()
    assert result["phases"]["after_fp1"]["training"]["n_training_events"] == 8
    fp2_features = result["phases"]["after_fp2"]["features"]
    assert [feature["name"] for feature in fp2_features] == [
        "fp1_gap_pct", "fp2_gap_pct", "fp1_rank", "fp2_rank",
    ]
    assert all(set(feature["source_sessions"]).issubset({"FP1", "FP2"})
               for feature in fp2_features)
    assert predictions.loc[predictions.phase.eq("after_fp1"), "cutoff_at_utc"].notna().all()


def test_phase_api_projects_rankings_and_rejects_tampered_artifact(tmp_path: Path):
    _write_phase_artifacts(tmp_path)
    client = TestClient(create_app(qualifying_phase_prediction_path=tmp_path))
    manifest = client.get("/api/v1/predictions/qualifying/phases")
    assert manifest.status_code == 200
    body = manifest.json()
    assert body["source_provider"] == "OpenF1"
    assert [phase["key"] for phase in body["phases"]] == [
        "after_fp1", "after_fp2", "pre_qualifying",
    ]
    event = client.get(
        "/api/v1/predictions/qualifying/phases/event",
        params={"phase": "after_fp1", "year": 2025, "round": 1, "split": "test"},
    )
    assert event.status_code == 200
    result = event.json()
    assert result["cutoff_at_utc"] == "2025-03-01T11:00:00+00:00"
    assert result["models"] == ["fp1", "ridge", "lightgbm"]
    assert result["rankings"][0]["driver"] == "D0"
    assert result["rankings"][0]["actual_rank"] == 1
    assert result["rankings"][0]["qualifying_position"] == 2
    assert "q1_gap_pct" not in str(result)
    assert "final_position" not in str(result)
    assert client.get(
        "/api/v1/predictions/qualifying/phases/event",
        params={"phase": "after_fp1", "year": 2025, "round": 9, "split": "test"},
    ).status_code == 404

    manifest_path = tmp_path / "experiment.json"
    original_manifest = manifest_path.read_text()
    invalid_manifest = json.loads(original_manifest)
    invalid_manifest["phase_definitions"]["after_fp1"]["features"][0]["source_sessions"] = ["FP2"]
    manifest_path.write_text(json.dumps(invalid_manifest))
    with pytest.raises(ValueError, match="future practice"):
        load_phase_prediction_lab(tmp_path)
    manifest_path.write_text(original_manifest)

    predictions_path = tmp_path / "phase_predictions.parquet"
    original_predictions = predictions_path.read_bytes()
    incomplete = pd.read_parquet(predictions_path).iloc[1:]
    incomplete.to_parquet(predictions_path, index=False)
    changed_manifest = json.loads(original_manifest)
    changed_manifest["artifact_sha256"]["phase_predictions.parquet"] = hashlib.sha256(predictions_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(changed_manifest))
    with pytest.raises(ValueError, match="driver/model coverage"):
        load_phase_prediction_lab(tmp_path)
    predictions_path.write_bytes(original_predictions)
    manifest_path.write_text(original_manifest)

    summary_path = tmp_path / "phase_summary.csv"
    original_summary = summary_path.read_bytes()
    inconsistent_summary = pd.read_csv(summary_path)
    inconsistent_summary.loc[0, "position_mae"] += 1
    inconsistent_summary.to_csv(summary_path, index=False)
    changed_manifest = json.loads(original_manifest)
    changed_manifest["artifact_sha256"]["phase_summary.csv"] = hashlib.sha256(summary_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(changed_manifest))
    with pytest.raises(ValueError, match="summary metrics disagree"):
        load_phase_prediction_lab(tmp_path)
    summary_path.write_bytes(original_summary)
    manifest_path.write_text(original_manifest)

    predictions_path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        load_phase_prediction_lab(tmp_path)
