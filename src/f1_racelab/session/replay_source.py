"""Indexed offline RaceSource over a versioned OpenF1 replay pack.

Sparse events pass through the canonical reducer. Approximate location and
interval sidecars are sampled at the requested clock time and returned in the
same RaceState, with distinct timestamps and quality markers. They never
modify official lap or classification events.
"""

from __future__ import annotations

import gzip
import json
import math
from bisect import bisect_right
from datetime import datetime, timedelta
from pathlib import Path

from f1_racelab.session.contracts import (
    DriverState,
    Quality,
    RaceState,
    SessionEvent,
    SessionId,
)
from f1_racelab.session.reducer import reduce_event

CHECKPOINT_EVENTS = 64
MAX_LOCATION_BRACKET_SECONDS = 1.5
MAX_LOCATION_COORD_UNITS_PER_SECOND = 2500.0
MAX_INTERVAL_AGE_SECONDS = 10.0


class ReplaySource:
    """One offline source with deterministic seek and event-index checkpoints."""

    def __init__(self, pack: dict):
        if pack.get("schema_version") != 1:
            raise ValueError("Unsupported replay pack schema version")
        self.pack = pack
        self.session = SessionId.model_validate(pack["session"])
        self.clock_origin = datetime.fromisoformat(pack["clock_origin_utc"])
        if self.clock_origin.tzinfo is None:
            raise ValueError("Replay clock origin must be timezone-aware")
        self.events = [SessionEvent.model_validate(row) for row in pack["events"]]
        self.event_times = [event.session_time_seconds for event in self.events]
        if self.event_times != sorted(self.event_times):
            raise ValueError("Replay events are not sorted by session time")
        self.locations = pack["locations"]
        self.location_times = {driver: [float(row[0]) for row in rows]
                               for driver, rows in self.locations.items()}
        self.intervals = pack["intervals"]
        self.interval_times = {driver: [float(row[0]) for row in rows]
                               for driver, rows in self.intervals.items()}
        known_drivers = {row["driver_id"] for row in pack["drivers"]}
        if set(self.locations) - known_drivers or set(self.intervals) - known_drivers:
            raise ValueError("Replay sidecar contains an unknown driver")
        for name, sidecar, times, width in (
            ("location", self.locations, self.location_times, 3),
            ("interval", self.intervals, self.interval_times, 5),
        ):
            for driver, rows in sidecar.items():
                if any(len(row) != width for row in rows):
                    raise ValueError(f"Malformed {name} row for {driver}")
                if any(not math.isfinite(value) or value < 0 for value in times[driver]):
                    raise ValueError(f"Invalid {name} timestamp for {driver}")
                if any(left >= right for left, right in zip(times[driver], times[driver][1:])):
                    raise ValueError(f"Unsorted or duplicate {name} timestamps for {driver}")
        self.checkpoint_indices = [0]
        self.checkpoint_states = [RaceState(session=self.session)]
        state = self.checkpoint_states[0]
        for index, event in enumerate(self.events, start=1):
            state = reduce_event(state, event)
            if index % CHECKPOINT_EVENTS == 0:
                self.checkpoint_indices.append(index)
                self.checkpoint_states.append(state)
        self.duration_seconds = max(
            self.event_times[-1] if self.event_times else 0.0,
            *(rows[-1][0] for rows in self.locations.values() if rows),
        )

    @classmethod
    def from_file(cls, path: Path) -> ReplaySource:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return cls(json.load(handle))

    def _location_at(self, driver_id: str, seconds: float) -> dict | None:
        rows = self.locations.get(driver_id, [])
        if not rows:
            return None
        times = self.location_times[driver_id]
        index = bisect_right(times, seconds)
        if index == 0:
            return None
        previous = rows[index - 1]
        before = float(previous[0])
        observed_at = self.clock_origin + timedelta(seconds=before)
        if math.isclose(seconds, before, abs_tol=.001):
            return {"track_x": float(previous[1]), "track_y": float(previous[2]),
                    "location_quality": Quality.MEASURED,
                    "location_observed_at": observed_at}
        if index >= len(rows):
            return None
        following = rows[index]
        after = float(following[0])
        bracket = after - before
        if bracket <= 0 or bracket > MAX_LOCATION_BRACKET_SECONDS:
            return None
        movement = math.hypot(float(following[1]) - float(previous[1]),
                              float(following[2]) - float(previous[2]))
        if movement / bracket > MAX_LOCATION_COORD_UNITS_PER_SECOND:
            return None
        fraction = (seconds - before) / bracket
        return {"track_x": float(previous[1]) + fraction * (float(following[1]) - float(previous[1])),
                "track_y": float(previous[2]) + fraction * (float(following[2]) - float(previous[2])),
                "location_quality": Quality.ESTIMATED,
                "location_observed_at": observed_at}

    def _interval_at(self, driver_id: str, seconds: float) -> dict | None:
        rows = self.intervals.get(driver_id, [])
        if not rows:
            return None
        index = bisect_right(self.interval_times[driver_id], seconds) - 1
        if index < 0:
            return None
        row = rows[index]
        if seconds - float(row[0]) > MAX_INTERVAL_AGE_SECONDS:
            return None
        return {"gap_to_leader_seconds": row[1], "interval_ahead_seconds": row[2],
                "gap_to_leader_text": row[3], "interval_ahead_text": row[4],
                "interval_observed_at": self.clock_origin + timedelta(seconds=float(row[0]))}

    def state_at(self, seconds: float) -> RaceState:
        """Seek from nearest checkpoint, then overlay source samples on one state."""
        if not math.isfinite(seconds) or seconds < 0 or seconds > self.duration_seconds:
            raise ValueError("Seek time is outside the replay")
        event_count = bisect_right(self.event_times, seconds)
        checkpoint = bisect_right(self.checkpoint_indices, event_count) - 1
        start = self.checkpoint_indices[checkpoint]
        state = self.checkpoint_states[checkpoint]
        for event in self.events[start:event_count]:
            state = reduce_event(state, event)
        drivers = dict(state.drivers)
        for metadata in self.pack["drivers"]:
            driver_id = metadata["driver_id"]
            prior = drivers.get(driver_id, DriverState(driver_id=driver_id))
            location = self._location_at(driver_id, seconds)
            interval = self._interval_at(driver_id, seconds)
            drivers[driver_id] = prior.model_copy(update={
                "track_x": None, "track_y": None, "location_quality": None,
                "location_observed_at": None,
                "gap_to_leader_seconds": None, "interval_ahead_seconds": None,
                "gap_to_leader_text": None, "interval_ahead_text": None,
                "interval_observed_at": None,
                **(location or {}), **(interval or {}),
            })
        return state.model_copy(update={"session_time_seconds": seconds, "drivers": drivers})
