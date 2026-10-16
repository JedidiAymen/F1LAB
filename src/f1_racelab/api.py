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

from f1_racelab.session.catalog import DEFAULT_SESSION, SESSIONS
from f1_racelab.session.contracts import WeatherPayload
from f1_racelab.session.replay_source import ReplaySource

DEFAULT_PACK = DEFAULT_SESSION.pack_path


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


def create_app(pack_path: Path | None = None, *, pack_paths: dict[str, Path] | None = None) -> FastAPI:
    """Create an API bound to a local replay pack, allowing isolated fixtures."""
    paths = {slug: spec.pack_path for slug, spec in SESSIONS.items()}
    paths.update(pack_paths or {})
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
        }

    @app.get("/api/v1/replay/{slug}/state")
    def state(slug: str, seconds: float = Query(ge=0)) -> dict:
        replay = source(slug)
        if not math.isfinite(seconds) or seconds > replay.duration_seconds:
            raise HTTPException(status_code=422, detail="Seek time is outside the replay")
        return replay.state_at(seconds).model_dump(
            mode="json",
            exclude={"applied_event_ids", "applied_event_hashes", "event_log", "race_control_messages"},
        )

    return app


app = create_app()
