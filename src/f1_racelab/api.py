"""Local read-only API for the indexed historical replay source.

The API exposes one canonical RaceState for a requested session time. The
browser owns the playback clock; every visible panel consumes that response.
"""

from __future__ import annotations

import math
import os
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from pydantic import ValidationError

from f1_racelab.models.prediction_lab import load_prediction_lab, prediction_event
from f1_racelab.models.qualifying_phase_lab import (
    load_phase_prediction_lab,
    phase_prediction_event,
)
from f1_racelab.session.catalog import DEFAULT_SESSION, SESSIONS
from f1_racelab.session.contracts import WeatherPayload
from f1_racelab.session.location_history import build_location_context
from f1_racelab.session.replay_source import ReplaySource
from f1_racelab.telemetry.artifacts import COMPARISONS
from f1_racelab.telemetry.contracts import LapComparison

DEFAULT_PACK = DEFAULT_SESSION.pack_path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PREDICTION_ARTIFACTS = PROJECT_ROOT / "data/processed/qualifying_backtest"
DEFAULT_PHASE_PREDICTION_ARTIFACTS = PROJECT_ROOT / "data/processed/qualifying_phases"


def _rainfall_changes(replay: ReplaySource) -> list[dict]:
    changes = []
    previous = None
    for event in replay.events:
        reading = event.payload
        if isinstance(reading, WeatherPayload) and reading.rainfall is not None and (
            reading.rainfall != previous
        ):
            changes.append({"event_id": event.event_id,
                            "session_time_seconds": event.session_time_seconds,
                            "rainfall": reading.rainfall})
            previous = reading.rainfall
    return changes


def create_app(
    pack_path: Path | None = None,
    *,
    pack_paths: dict[str, Path] | None = None,
    telemetry_comparison_paths: dict[str, Path] | None = None,
    qualifying_prediction_path: Path | None = None,
    qualifying_phase_prediction_path: Path | None = None,
) -> FastAPI:
    """Create an API bound to a local replay pack, allowing isolated fixtures."""
    paths = {slug: spec.pack_path for slug, spec in SESSIONS.items()}
    paths.update(pack_paths or {})
    telemetry_paths = {slug: comparison.path for slug, comparison in COMPARISONS.items()}
    telemetry_paths.update(telemetry_comparison_paths or {})
    prediction_path = Path(qualifying_prediction_path or DEFAULT_PREDICTION_ARTIFACTS)
    phase_prediction_path = Path(
        qualifying_phase_prediction_path or DEFAULT_PHASE_PREDICTION_ARTIFACTS
    )
    if pack_path or os.environ.get("F1LAB_REPLAY_PACK"):
        paths[DEFAULT_SESSION.slug] = pack_path or Path(os.environ["F1LAB_REPLAY_PACK"])
    app = FastAPI(title="F1LAB local replay API", version="0.1.0")

    @lru_cache(maxsize=3)
    def source(slug: str) -> ReplaySource:
        if slug not in SESSIONS:
            raise HTTPException(status_code=404, detail="Unknown replay session")
        path = paths[slug]
        if not path.is_file():
            raise HTTPException(
                status_code=503,
                detail=f"Replay pack unavailable. Run python -m f1_racelab.session.openf1_replay --session {slug}.",
            )
        try:
            replay = ReplaySource.from_file(path)
            if replay.pack.get("slug", slug) != slug:
                raise ValueError("Replay slug does not match requested session")
            return replay
        except (OSError, KeyError, ValueError) as exc:
            raise HTTPException(status_code=503, detail=f"Invalid replay pack: {exc}") from exc

    @app.get("/api/v1/replays")
    def sessions() -> list[dict]:
        return [{"slug": slug, "season": spec.season, "round": spec.round,
                 "title": spec.title, "display_name": spec.display_name, "circuit": spec.circuit,
                 "available": paths[slug].is_file()} for slug, spec in SESSIONS.items()]

    @app.get("/api/v1/replay/{slug}/manifest")
    def manifest(slug: str) -> dict:
        replay = source(slug)
        pack = replay.pack
        return {
            "slug": slug,
            "schema_version": pack["schema_version"],
            "session": pack["session"],
            "session_name": pack["session_name"],
            "circuit_name": pack.get("circuit_name", SESSIONS[slug].circuit),
            "scheduled_laps": pack.get("scheduled_laps", SESSIONS[slug].scheduled_laps),
            "clock_origin_utc": pack["clock_origin_utc"],
            "duration_seconds": replay.duration_seconds,
            "provider": pack["provider"],
            "capabilities": pack["capabilities"],
            "drivers": pack["drivers"],
            "geometry": pack["geometry"],
            "coverage": pack["coverage"],
            "race_control": [event for event in pack["events"] if event["type"] == "race_control"],
            "weather_changes": _rainfall_changes(replay),
            "telemetry_comparisons": ([{
                "id": COMPARISONS[slug].comparison_id,
                "label": COMPARISONS[slug].label,
                "available": telemetry_paths[slug].is_file(),
                "quality": "estimated",
            }] if slug in COMPARISONS and slug in telemetry_paths else []),
        }

    @app.get("/api/v1/replay/{slug}/state")
    def state(slug: str, seconds: float = Query(ge=0),
              focus_driver: str | None = Query(default=None)) -> dict:
        replay = source(slug)
        if not math.isfinite(seconds) or seconds > replay.duration_seconds:
            raise HTTPException(status_code=422, detail="Seek time is outside the replay")
        if focus_driver is not None and focus_driver not in {
            driver["driver_id"] for driver in replay.pack["drivers"]
        }:
            raise HTTPException(status_code=404, detail="Unknown focused driver")
        canonical = replay.state_at(seconds)
        payload = canonical.model_dump(
            mode="json",
            exclude={"applied_event_ids", "applied_event_hashes", "event_log", "race_control_messages"},
        )
        if focus_driver is not None:
            driver = canonical.drivers[focus_driver]
            payload["location_context"] = build_location_context(
                replay.locations.get(focus_driver, []), driver_id=focus_driver,
                session_time_seconds=canonical.session_time_seconds,
                track_x=driver.track_x, track_y=driver.track_y,
                location_quality=str(driver.location_quality) if driver.location_quality else None,
                source_times=replay.location_times.get(focus_driver, []),
            ).model_dump(mode="json")
        return payload

    @app.get("/api/v1/replay/{slug}/telemetry/lap-comparison")
    def lap_comparison(slug: str) -> dict:
        if slug not in SESSIONS:
            raise HTTPException(status_code=404, detail="Unknown replay session")
        path = telemetry_paths.get(slug)
        if path is None:
            raise HTTPException(status_code=404, detail="No telemetry comparison is configured")
        if not path.is_file():
            raise HTTPException(
                status_code=503,
                detail="Telemetry comparison artifact unavailable. Run python -m "
                "f1_racelab.telemetry.openf1_lap_comparison.",
            )
        try:
            comparison = LapComparison.model_validate_json(path.read_bytes())
        except (OSError, ValidationError) as exc:
            raise HTTPException(status_code=503, detail=f"Invalid telemetry artifact: {exc}") from exc
        spec = SESSIONS[slug]
        if (comparison.session_key, comparison.meeting_key) != (spec.session_key, spec.meeting_key):
            raise HTTPException(status_code=503, detail="Telemetry artifact belongs to a different session")
        expected = COMPARISONS.get(slug)
        if expected is not None and (
            comparison.lap_a.driver_number, comparison.lap_a.lap_number,
            comparison.lap_b.driver_number, comparison.lap_b.lap_number,
        ) != (expected.driver_a, expected.lap_a, expected.driver_b, expected.lap_b):
            raise HTTPException(status_code=503, detail="Telemetry artifact differs from comparison catalog")
        return comparison.model_dump(
            mode="json", exclude={"lap_a": {"points"}, "lap_b": {"points"}},
        )

    def prediction_artifacts() -> dict:
        try:
            return load_prediction_lab(prediction_path)
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=503,
                detail="Qualifying Prediction Lab artifacts unavailable. Run python -m "
                "f1_racelab.models.qualifying_backtest --dataset "
                "data/processed/qualifying_mixed_2022_2023_2024_2025.parquet --feature-set common.",
            ) from exc
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(status_code=503, detail=f"Invalid Prediction Lab artifacts: {exc}") from exc

    @app.get("/api/v1/predictions/qualifying")
    def qualifying_prediction_manifest() -> dict:
        lab = prediction_artifacts()
        experiment = lab["experiment"]
        return {
            "task": "historical_pre_qualifying_rank",
            "selected_model": experiment["winner"],
            "feature_set": experiment["feature_set"],
            "features": experiment["features"],
            "cutoff_audit": experiment["cutoff_audit"],
            "dataset_sha256": experiment["dataset_sha256"],
            "predictions_sha256": experiment["predictions_sha256"],
            "training": {key: experiment[key] for key in (
                "n_training_events", "n_training_rows", "n_validation_events",
                "n_validation_rows", "n_test_events", "n_test_rows",
            )},
            "summaries": lab["summaries"],
            "uncertainty": lab["uncertainty"],
            "events": lab["events"],
        }

    @app.get("/api/v1/predictions/qualifying/event")
    def qualifying_prediction_weekend(
        year: int = Query(ge=2022, le=2035),
        round_no: int = Query(alias="round", ge=1, le=30),
        split: str = Query(pattern="^(validation|test)$"),
    ) -> dict:
        lab = prediction_artifacts()
        try:
            return prediction_event(lab, year=year, round_no=round_no, split=split)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=503, detail=f"Invalid Prediction Lab event: {exc}") from exc

    def phase_prediction_artifacts() -> dict:
        try:
            return load_phase_prediction_lab(phase_prediction_path)
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=503,
                detail="Phase-aware qualifying artifacts unavailable. Run python -m "
                "f1_racelab.models.qualifying_phases --dataset "
                "data/processed/qualifying_mixed_2022_2023_2024_2025.parquet.",
            ) from exc
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(status_code=503, detail=f"Invalid phase-aware artifacts: {exc}") from exc

    @app.get("/api/v1/predictions/qualifying/phases")
    def qualifying_phase_manifest() -> dict:
        lab = phase_prediction_artifacts()
        experiment = lab["experiment"]
        definitions = lab["definitions"]
        phases = []
        for key, definition in definitions.items():
            phases.append({
                "key": key,
                **definition,
                "models": [definition["baseline"], "ridge", "lightgbm"],
                "summaries": lab["summaries"][key],
                "uncertainty": lab["uncertainty"][key],
                "events": lab["events"][key],
            })
        return {
            "task": "historical_phase_aware_qualifying_rank",
            "source_provider": experiment["source_provider"],
            "source_years": experiment["source_years"],
            "source_rows": experiment["source_rows"],
            "dataset_sha256": experiment["source_dataset_sha256"],
            "schedule_sha256": experiment["source_schedule_sha256"],
            "selection_year": experiment["selection_year"],
            "held_out_year": experiment["held_out_year"],
            "cutoff_contract": experiment["cutoff_contract"],
            "feature_observed_at": experiment["feature_observed_at"],
            "timing_limit": experiment["timing_limit"],
            "phases": phases,
        }

    @app.get("/api/v1/predictions/qualifying/phases/event")
    def qualifying_phase_weekend(
        phase: str = Query(pattern="^(after_fp1|after_fp2|pre_qualifying)$"),
        year: int = Query(ge=2023, le=2035),
        round_no: int = Query(alias="round", ge=1, le=30),
        split: str = Query(pattern="^(validation|test)$"),
    ) -> dict:
        lab = phase_prediction_artifacts()
        try:
            return phase_prediction_event(
                lab, phase=phase, year=year, round_no=round_no, split=split,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=503, detail=f"Invalid phase prediction event: {exc}") from exc

    return app


app = create_app()
