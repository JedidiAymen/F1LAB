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

from f1_racelab.session.replay_source import ReplaySource

DEFAULT_PACK = Path(__file__).resolve().parents[2] / "data/processed/replay_packs/monza_2025_race.json.gz"


def create_app(pack_path: Path | None = None) -> FastAPI:
    """Create an API bound to a local replay pack, allowing isolated fixtures."""
    path = pack_path or Path(os.environ.get("F1LAB_REPLAY_PACK", DEFAULT_PACK))
    app = FastAPI(title="F1LAB local replay API", version="0.1.0")

    @lru_cache(maxsize=1)
    def source() -> ReplaySource:
        if not path.is_file():
            raise HTTPException(
                status_code=503,
                detail=f"Replay pack unavailable at {path}. Run python -m f1_racelab.session.openf1_replay.",
            )
        try:
            return ReplaySource.from_file(path)
        except (OSError, KeyError, ValueError) as exc:
            raise HTTPException(status_code=503, detail=f"Invalid replay pack: {exc}") from exc

    @app.get("/api/v1/replay/monza-2025/manifest")
    def manifest() -> dict:
        replay = source()
        pack = replay.pack
        return {
            "schema_version": pack["schema_version"],
            "session": pack["session"],
            "session_name": pack["session_name"],
            "clock_origin_utc": pack["clock_origin_utc"],
            "duration_seconds": replay.duration_seconds,
            "provider": pack["provider"],
            "capabilities": pack["capabilities"],
            "drivers": pack["drivers"],
            "geometry": pack["geometry"],
            "coverage": pack["coverage"],
            "race_control": [event for event in pack["events"] if event["type"] == "race_control"],
        }

    @app.get("/api/v1/replay/monza-2025/state")
    def state(seconds: float = Query(ge=0)) -> dict:
        replay = source()
        if not math.isfinite(seconds) or seconds > replay.duration_seconds:
            raise HTTPException(status_code=422, detail="Seek time is outside the replay")
        return replay.state_at(seconds).model_dump(
            mode="json",
            exclude={"applied_event_ids", "applied_event_hashes", "event_log", "race_control_messages"},
        )

    return app


app = create_app()
