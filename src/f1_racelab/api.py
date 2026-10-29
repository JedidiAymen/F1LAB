"""Local read-only API for the indexed historical replay source.

The API exposes one canonical RaceState for a requested session time. The
browser owns the playback clock; every visible panel consumes that response.
"""

from __future__ import annotations

import json
import math
import os
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from f1_racelab.live.ingest import _registry as live_registry
from f1_racelab.ml.common.registry import ArtifactUnavailable
from f1_racelab.ml.driver_dna import service as dna_service
from f1_racelab.ml.overtake import benchmark as overtake_benchmark
from f1_racelab.ml.pace import inference as pace_inference
from f1_racelab.ml.pace import service as pace_service
from f1_racelab.models.prediction_lab import load_prediction_lab, prediction_event
from f1_racelab.models.qualifying_phase_lab import (
    load_phase_prediction_lab,
    phase_prediction_event,
)
from f1_racelab.models.walkforward_lab import load_walkforward_lab, walkforward_event
from f1_racelab.session.catalog import DEFAULT_SESSION, SESSIONS
from f1_racelab.session.contracts import WeatherPayload
from f1_racelab.session.location_history import build_location_context
from f1_racelab.session.replay_source import ReplaySource
from f1_racelab.session.timeline import MAX_STEP, MIN_STEP, build_timeline
from f1_racelab.strategy import ml_overlay
from f1_racelab.strategy.models import CIRCUIT_COMPOUNDS, RACE_SPECS
from f1_racelab.strategy.monte_carlo import mc_compare
from f1_racelab.strategy.optimizer import best_strategies, compare_strategies
from f1_racelab.strategy.simulator import PitStop, Strategy
from f1_racelab.strategy.whatif import branch as whatif_branch
from f1_racelab.telemetry.artifacts import COMPARISONS
from f1_racelab.telemetry.contracts import LapComparison
from f1_racelab.telemetry.lap_library import (
    LIBRARY_ROOT,
    LapSelection,
    compare_library_laps,
    load_library,
)

DEFAULT_PACK = DEFAULT_SESSION.pack_path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PREDICTION_ARTIFACTS = PROJECT_ROOT / "data/processed/qualifying_backtest"
DEFAULT_PHASE_PREDICTION_ARTIFACTS = PROJECT_ROOT / "data/processed/qualifying_phases"
DEFAULT_WALKFORWARD_ARTIFACTS = PROJECT_ROOT / "data/processed/qualifying_walkforward"


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
    telemetry_library_roots: dict[str, Path] | None = None,
    qualifying_prediction_path: Path | None = None,
    qualifying_phase_prediction_path: Path | None = None,
    qualifying_walkforward_path: Path | None = None,
) -> FastAPI:
    """Create an API bound to a local replay pack, allowing isolated fixtures."""
    paths = {slug: spec.pack_path for slug, spec in SESSIONS.items()}
    paths.update(pack_paths or {})
    telemetry_paths = {slug: comparison.path for slug, comparison in COMPARISONS.items()}
    telemetry_paths.update(telemetry_comparison_paths or {})
    library_roots = {slug: LIBRARY_ROOT / slug for slug in SESSIONS}
    library_roots.update(telemetry_library_roots or {})
    prediction_path = Path(qualifying_prediction_path or DEFAULT_PREDICTION_ARTIFACTS)
    phase_prediction_path = Path(
        qualifying_phase_prediction_path or DEFAULT_PHASE_PREDICTION_ARTIFACTS
    )
    walkforward_path = Path(qualifying_walkforward_path or DEFAULT_WALKFORWARD_ARTIFACTS)
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

    @lru_cache(maxsize=8)
    def cached_timeline(slug: str, step: float) -> dict:
        return build_timeline(source(slug), step)

    @app.get("/api/v1/replay/{slug}/timeline")
    def timeline(slug: str, step: float = Query(default=30.0, ge=MIN_STEP, le=MAX_STEP)) -> dict:
        return cached_timeline(slug, step)

    def telemetry_library(slug: str):
        if slug not in SESSIONS:
            raise HTTPException(status_code=404, detail="Unknown replay session")
        try:
            return load_library(library_roots[slug], slug)
        except (OSError, ValueError, KeyError) as exc:
            raise HTTPException(status_code=503, detail="Telemetry lap library unavailable or invalid. "
                                "Run python -m f1_racelab.telemetry.lap_library --all --offline. "
                                f"{exc}") from exc

    @app.get("/api/v1/replay/{slug}/telemetry/laps")
    def telemetry_laps(slug: str) -> dict:
        return telemetry_library(slug).model_dump(mode="json")

    @app.get("/api/v1/replay/{slug}/telemetry/lap-comparison")
    def lap_comparison(
        slug: str, driver_a: int | None = Query(default=None, gt=0),
        lap_a: int | None = Query(default=None, ge=1),
        driver_b: int | None = Query(default=None, gt=0),
        lap_b: int | None = Query(default=None, ge=1),
    ) -> dict:
        if slug not in SESSIONS:
            raise HTTPException(status_code=404, detail="Unknown replay session")
        selection_values = (driver_a, lap_a, driver_b, lap_b)
        if any(value is not None for value in selection_values):
            if any(value is None for value in selection_values):
                raise HTTPException(status_code=422, detail="All four driver/lap selections are required")
            if (driver_a, lap_a) == (driver_b, lap_b):
                raise HTTPException(status_code=422, detail="A lap cannot be compared with itself")
            library = telemetry_library(slug)
            assert driver_a is not None and lap_a is not None and driver_b is not None and lap_b is not None
            selection = LapSelection(driver_a=driver_a, lap_a=lap_a, driver_b=driver_b, lap_b=lap_b)
            try:
                # Resolve unknown selections before opening any artifact files.
                library.entry(selection.driver_a, selection.lap_a)
                library.entry(selection.driver_b, selection.lap_b)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            try:
                comparison = compare_library_laps(library_roots[slug], library, selection)
            except (OSError, ValueError, KeyError, EOFError) as exc:
                raise HTTPException(status_code=503, detail=f"Invalid telemetry lap artifact: {exc}") from exc
            return comparison.model_dump(mode="json", exclude={"lap_a": {"points"}, "lap_b": {"points"}})

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

    @lru_cache(maxsize=1)
    def walkforward_artifacts() -> dict:
        try:
            return load_walkforward_lab(walkforward_path)
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=503,
                detail="Walk-forward artifacts unavailable. Run python -m "
                "f1_racelab.models.qualifying_walkforward.",
            ) from exc
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(status_code=503, detail=f"Invalid walk-forward artifacts: {exc}") from exc

    @app.get("/api/v1/predictions/qualifying/walkforward")
    def qualifying_walkforward_manifest() -> dict:
        lab = walkforward_artifacts()
        return {key: lab[key] for key in ("experiment", "summary", "bootstrap", "reliability", "events")}

    @app.get("/api/v1/predictions/qualifying/walkforward/event")
    def qualifying_walkforward_weekend(
        year: int = Query(ge=2022, le=2035),
        round_no: int = Query(alias="round", ge=1, le=30),
    ) -> dict:
        try:
            return walkforward_event(walkforward_artifacts(), year=year, round_no=round_no)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @lru_cache(maxsize=1)
    def pace_lab() -> dict:
        try:
            return pace_service.load()
        except (pace_service.PaceUnavailable, OSError, ValueError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/v1/pace/races")
    def pace_races() -> dict:
        lab = pace_lab()
        return {"model": lab["card"].model_dump(mode="json", include={"model_id", "version", "limitations", "metrics"}),
                "summary": {k: lab["summary"][k] for k in ("green_table", "paired_vs_anchor", "interval", "ablations")
                            if k in lab["summary"]}, "races": pace_service.races(lab)}

    @app.get("/api/v1/pace/forecast")
    def pace_forecast(race_id: str = Query(min_length=1, max_length=16), driver: int = Query(ge=1, le=99)) -> dict:
        try:
            return pace_service.forecast(pace_lab(), race_id, driver)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/driver-dna/summary")
    def driver_dna_summary() -> dict:
        try:
            return dna_service.summary()
        except (dna_service.DnaUnavailable, OSError, ValueError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/v1/overtake/summary")
    def overtake_summary() -> dict:
        path = overtake_benchmark.OUT / "summary.json"
        if not path.is_file():
            raise HTTPException(status_code=503, detail="Overtake results missing. Run: "
                                "uv run python -m f1_racelab.ml.overtake.dataset && "
                                "uv run python -m f1_racelab.ml.overtake.benchmark")
        return {"evidence": "ml_evaluation_real", **json.loads(path.read_text())}

    @app.post("/api/v1/pace/predict")
    def pace_predict(features: pace_inference.PaceFeatures) -> dict:
        try:
            return pace_inference.predict(features)
        except (ArtifactUnavailable, OSError, ValueError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    # ------------------------------------------------------------------ #
    # P5 Strategy Lab endpoints                                            #
    # ------------------------------------------------------------------ #

    @app.get("/api/v1/strategy/{slug}/info")
    def strategy_info(slug: str) -> dict:
        """Return available compounds and race spec for a session."""
        if slug not in RACE_SPECS:
            raise HTTPException(status_code=404, detail=f"No strategy model for session {slug!r}")
        spec = RACE_SPECS[slug]
        compounds = CIRCUIT_COMPOUNDS[slug]
        return {
            "session_slug": slug,
            "scheduled_laps": spec.scheduled_laps,
            "base_lap_time_s": spec.base_lap_time_s,
            "safety_car_laps": list(spec.safety_car_laps),
            "available_compounds": [
                {"compound": c, "lap_time_offset_s": m.lap_time_offset_s,
                 "linear_s_per_lap": m.linear_s_per_lap}
                for c, m in compounds.items()
            ],
            "simulation_limits": [
                "Tyre coefficients are per-circuit fits; uncertainty grows on long stints.",
                "Traffic interaction is a heuristic penalty, not aerodynamic simulation.",
                "Fuel burn rate is assumed constant; no fuel-save modes modelled.",
                "SC timing is fixed from the replay pack; MC does not sample new SC events.",
                "Simulated lap times are labelled estimation='simulated' throughout.",
            ],
        }

    @app.post("/api/v1/strategy/{slug}/ml-pace")
    def strategy_ml_pace(slug: str, body: ml_overlay.StintRequest) -> dict:
        """Opt-in ML pace curve for one stint next to the deterministic simulator curve (baseline unchanged)."""
        if slug not in RACE_SPECS:
            raise HTTPException(status_code=404, detail=f"No strategy model for session {slug!r}")
        try:
            return ml_overlay.stint_overlay(slug, body)
        except ArtifactUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/v1/strategy/{slug}/compare")
    def strategy_compare(slug: str, body: dict) -> dict:
        """Compare explicit strategies by race time.

        Body: { "strategies": [{"start_compound": "MEDIUM", "pit_stops":
            [{"lap": 30, "compound": "HARD"}], "driver_number": 1}, ...] }
        """
        if slug not in RACE_SPECS:
            raise HTTPException(status_code=404, detail=f"No strategy model for session {slug!r}")
        try:
            raw = body.get("strategies", [])
            strategies = [
                Strategy(
                    driver_number=s.get("driver_number", 1),
                    start_compound=s["start_compound"],
                    pit_stops=tuple(
                        PitStop(lap=p["lap"], compound=p["compound"])
                        for p in s.get("pit_stops", [])
                    ),
                )
                for s in raw
            ]
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=f"Invalid strategy payload: {exc}") from exc
        if not strategies:
            raise HTTPException(status_code=422, detail="At least one strategy is required")
        results = compare_strategies(slug, strategies)
        return {
            "session_slug": slug,
            "ranked": [
                {
                    "label": r.label,
                    "stops": r.stops,
                    "total_race_time_s": r.total_race_time_s,
                    "delta_vs_reference_s": r.delta_vs_reference_s,
                    "pit_laps": list(r.pit_laps),
                    "compounds": list(r.compounds),
                    "simulation_limits": list(r.simulation_limits),
                }
                for r in results
            ],
        }

    @app.get("/api/v1/strategy/{slug}/best")
    def strategy_best(
        slug: str,
        max_stops: int = Query(default=2, ge=0, le=3),
        top_n: int = Query(default=10, ge=1, le=30),
        pit_step: int = Query(default=3, ge=1, le=10),
        compounds: str = Query(default="SOFT,MEDIUM,HARD",
                               description="Comma-separated compound names"),
        driver_number: int = Query(default=1, gt=0),
    ) -> dict:
        """Enumerate and rank strategies, returning the top_n fastest."""
        if slug not in RACE_SPECS:
            raise HTTPException(status_code=404, detail=f"No strategy model for session {slug!r}")
        available = [c.strip().upper() for c in compounds.split(",") if c.strip()]
        if not available:
            raise HTTPException(status_code=422, detail="At least one compound is required")
        valid = set(CIRCUIT_COMPOUNDS[slug].keys())
        unknown = [c for c in available if c not in valid]
        if unknown:
            raise HTTPException(status_code=422,
                                detail=f"Unknown compounds: {unknown}. Available: {sorted(valid)}")
        results = best_strategies(slug, driver_number, available,
                                  max_stops=max_stops, top_n=top_n, pit_step=pit_step)
        return {
            "session_slug": slug,
            "driver_number": driver_number,
            "searched_compounds": available,
            "ranked": [
                {
                    "rank": i + 1,
                    "label": r.label,
                    "stops": r.stops,
                    "total_race_time_s": r.total_race_time_s,
                    "delta_vs_reference_s": r.delta_vs_reference_s,
                    "pit_laps": list(r.pit_laps),
                    "compounds": list(r.compounds),
                    "simulation_limits": list(r.simulation_limits),
                }
                for i, r in enumerate(results)
            ],
        }

    @app.post("/api/v1/strategy/{slug}/montecarlo")
    def strategy_montecarlo(slug: str, body: dict) -> dict:
        """Monte Carlo comparison of strategies.

        Body: { "strategies": [...same as /compare...], "n_worlds": 200, "seed": 42 }
        """
        if slug not in RACE_SPECS:
            raise HTTPException(status_code=404, detail=f"No strategy model for session {slug!r}")
        try:
            raw = body.get("strategies", [])
            strategies = [
                Strategy(
                    driver_number=s.get("driver_number", 1),
                    start_compound=s["start_compound"],
                    pit_stops=tuple(
                        PitStop(lap=p["lap"], compound=p["compound"])
                        for p in s.get("pit_stops", [])
                    ),
                )
                for s in raw
            ]
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=f"Invalid strategy payload: {exc}") from exc
        if not strategies:
            raise HTTPException(status_code=422, detail="At least one strategy is required")
        n_worlds = min(int(body.get("n_worlds", 200)), 1000)
        seed = int(body.get("seed", 42))
        results = mc_compare(slug, strategies, n_worlds=n_worlds, seed=seed)
        return {
            "session_slug": slug,
            "n_worlds": n_worlds,
            "seed": seed,
            "ranked": [
                {
                    "rank": i + 1,
                    "strategy_label": r.strategy_label,
                    "driver_number": r.driver_number,
                    "mean_race_time_s": r.mean_race_time_s,
                    "std_race_time_s": r.std_race_time_s,
                    "p5_race_time_s": r.p5_race_time_s,
                    "p50_race_time_s": r.p50_race_time_s,
                    "p95_race_time_s": r.p95_race_time_s,
                    "mean_delta_vs_fastest_s": r.mean_delta_vs_fastest_s,
                    "win_fraction": r.win_fraction,
                    "simulation_limits": list(r.simulation_limits),
                }
                for i, r in enumerate(results)
            ],
        }

    # ------------------------------------------------------------------ #
    # P6 What-if / counterfactual branch endpoint                         #
    # ------------------------------------------------------------------ #

    @app.post("/api/v1/strategy/{slug}/whatif")
    def strategy_whatif(slug: str, body: dict) -> dict:
        """Fork a real race at a chosen lap and compare actual vs counterfactual.

        Body: {
          "driver_number": 1,
          "fork_lap": 30,
          "actual_strategy": {"start_compound": "MEDIUM",
                              "pit_stops": [{"lap": 37, "compound": "HARD"}]},
          "counterfactual_strategy": {"start_compound": "MEDIUM",
                                      "pit_stops": [{"lap": 25, "compound": "HARD"}]}
        }
        """
        if slug not in RACE_SPECS:
            raise HTTPException(status_code=404, detail=f"No strategy model for session {slug!r}")
        try:
            driver_number = int(body.get("driver_number", 1))
            fork_lap = int(body["fork_lap"])

            def _parse_strategy(raw: dict, driver: int) -> Strategy:
                return Strategy(
                    driver_number=driver,
                    start_compound=raw["start_compound"],
                    pit_stops=tuple(
                        PitStop(lap=p["lap"], compound=p["compound"])
                        for p in raw.get("pit_stops", [])
                    ),
                )

            actual = _parse_strategy(body["actual_strategy"], driver_number)
            counterfactual = _parse_strategy(body["counterfactual_strategy"], driver_number)
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=f"Invalid what-if payload: {exc}") from exc

        try:
            result = whatif_branch(
                slug, driver_number, actual, counterfactual, fork_lap
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        def _lap_dict(lap) -> dict:
            return {
                "lap": lap.lap,
                "compound": lap.compound,
                "stint_lap": lap.stint_lap,
                "lap_time_s": lap.lap_time_s,
                "cumulative_race_time_s": lap.cumulative_race_time_s,
                "pitted_this_lap": lap.pitted_this_lap,
                "pit_loss_s": lap.pit_loss_s,
                "estimation": lap.estimation,
                "is_fork_lap": lap.is_fork_lap,
            }

        return {
            "session_slug": slug,
            "driver_number": driver_number,
            "fork_lap": result.fork_lap,
            "actual_strategy_label": result.actual_strategy_label,
            "counterfactual_strategy_label": result.counterfactual_strategy_label,
            "actual_total_race_time_s": result.actual_total_race_time_s,
            "counterfactual_total_race_time_s": result.counterfactual_total_race_time_s,
            "delta_counterfactual_vs_actual_s": result.delta_counterfactual_vs_actual_s,
            "counterfactual_is_faster": result.counterfactual_is_faster,
            "actual_laps": [_lap_dict(l) for l in result.actual_laps],
            "counterfactual_laps": [_lap_dict(l) for l in result.counterfactual_laps],
            "simulation_limits": list(result.simulation_limits),
        }

    # ------------------------------------------------------------------ #
    # P7 Live / simulated-live WebSocket endpoint                         #
    # ------------------------------------------------------------------ #

    @app.websocket("/ws/live/{slug}")
    async def live_ws(
        websocket: WebSocket,
        slug: str,
        speed: float = Query(default=1.0, ge=0.1, le=16.0),
        start: float = Query(default=0.0, ge=0.0),
    ) -> None:
        """Simulated-live WebSocket fan-out for a session.

        Plays back the cached replay pack at real-time speed (adjustable via
        the 'speed' query parameter).  All subscribers share one ingest task.
        Reconnect delivers the current snapshot immediately.

        The client MUST display the SIMULATED LIVE badge whenever mode='simulated'.
        Every message contains a 'badge' field with the required label.
        """
        if slug not in SESSIONS:
            await websocket.close(code=4004, reason='Unknown session')
            return
        await websocket.accept()
        try:
            session = await live_registry.get_or_create(slug, speed=speed)
            async with session.subscribe() as sub:
                async for snapshot in sub:
                    try:
                        await websocket.send_json(snapshot)
                    except Exception:  # noqa: BLE001 - client went away mid-send
                        break
        except WebSocketDisconnect:
            pass
        except Exception as exc:  # noqa: BLE001 - report any ingest failure to the client
            try:
                await websocket.send_json({
                    'type': 'error',
                    'session_slug': slug,
                    'detail': str(exc),
                })
            except Exception:  # noqa: BLE001, S110 - socket already closed
                pass
        finally:
            try:
                await websocket.close()
            except Exception:  # noqa: BLE001, S110 - socket already closed
                pass

    @app.get("/api/v1/live/{slug}/status")
    async def live_status(slug: str) -> dict:
        """Check if a live session is running and how many clients are connected."""
        if slug not in SESSIONS:
            raise HTTPException(status_code=404, detail='Unknown session')
        s = live_registry._sessions.get(slug)
        return {
            'session_slug': slug,
            'running': s._running if s else False,
            'subscriber_count': s.subscriber_count if s else 0,
            'mode': s.mode if s else None,
            'session_time_seconds': round(s._session_time, 3) if s else None,
        }

    return app


app = create_app()
