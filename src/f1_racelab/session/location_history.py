"""Bounded display trail and movement direction on the canonical replay clock.

Historical vertices are measured source samples. The only possible estimated
vertex is the current position already computed by ReplaySource; this module
never interpolates a second car position or advances a separate clock.
"""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from itertools import pairwise
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from f1_racelab.session.replay_source import (
    MAX_LOCATION_BRACKET_SECONDS,
    MAX_LOCATION_COORD_UNITS_PER_SECOND,
)

TRAIL_WINDOW_SECONDS = 12.0


class TrailPoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    session_time_seconds: float = Field(ge=0)
    track_x: float
    track_y: float
    quality: Literal["measured", "estimated"]


def _connected(left: TrailPoint, right: TrailPoint) -> bool:
    gap = right.session_time_seconds - left.session_time_seconds
    return 0 < gap <= MAX_LOCATION_BRACKET_SECONDS and math.hypot(
        right.track_x - left.track_x, right.track_y - left.track_y,
    ) / gap <= MAX_LOCATION_COORD_UNITS_PER_SECOND


class LocationContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    schema_version: Literal[1] = 1
    driver_id: str
    session_time_seconds: float = Field(ge=0)
    window_seconds: float = Field(default=TRAIL_WINDOW_SECONDS, ge=12, le=12)
    coordinate_system: Literal["openf1_approx_cartesian_unknown_unit"] = (
        "openf1_approx_cartesian_unknown_unit")
    segments: list[list[TrailPoint]]
    heading_radians: float | None = Field(default=None, ge=-math.pi, le=math.pi)
    heading_quality: Literal["estimated"] | None = None
    location_available: bool

    @model_validator(mode="after")
    def validate_timeline(self) -> LocationContext:
        previous = -math.inf
        for segment in self.segments:
            if not segment:
                raise ValueError("Trail segments must contain a point")
            for point in segment:
                if not max(0.0, self.session_time_seconds - self.window_seconds) <= (
                    point.session_time_seconds
                ) <= self.session_time_seconds:
                    raise ValueError("Trail point lies outside canonical trailing window")
                if point.session_time_seconds <= previous:
                    raise ValueError("Trail points must increase across all segments")
                if point.quality == "estimated" and point.session_time_seconds != (
                    self.session_time_seconds
                ):
                    raise ValueError("Only canonical current trail point can be estimated")
                previous = point.session_time_seconds
            if any(not _connected(left, right) for left, right in pairwise(segment)):
                raise ValueError("Trail segment bridges a dropout or coordinate jump")
        if (self.heading_radians is None) != (self.heading_quality is None):
            raise ValueError("Heading and heading quality must be present together")
        if self.heading_radians is not None:
            if not self.location_available or not self.segments or len(self.segments[-1]) < 2:
                raise ValueError("Heading requires a connected current movement pair")
            left, right = self.segments[-1][-2:]
            if right.session_time_seconds != self.session_time_seconds or (
                left.track_x, left.track_y
            ) == (right.track_x, right.track_y):
                raise ValueError("Heading requires movement ending at canonical current time")
            expected = math.atan2(right.track_y - left.track_y, right.track_x - left.track_x)
            if not math.isclose(self.heading_radians, expected, abs_tol=1e-12):
                raise ValueError("Heading disagrees with current movement direction")
        return self


def build_location_context(rows: list[list[float]], *, driver_id: str,
                           session_time_seconds: float, track_x: float | None,
                           track_y: float | None,
                           location_quality: str | None,
                           source_times: list[float] | None = None) -> LocationContext:
    """Slice validated indexed source rows and attach the existing canonical point.

    Direction is atan2(dy, dx) in provider XY, estimated from displacement;
    it is not measured chassis yaw. Missing/stationary/dropout cases have none.
    The optional source_times is ReplaySource's existing validated time index.
    """
    if not math.isfinite(session_time_seconds) or session_time_seconds < 0:
        raise ValueError("Canonical location time must be finite and nonnegative")
    times = source_times if source_times is not None else [float(row[0]) for row in rows]
    if len(times) != len(rows):
        raise ValueError("Location time index must match source rows")
    start = bisect_left(times, max(0.0, session_time_seconds - TRAIL_WINDOW_SECONDS))
    end = bisect_right(times, session_time_seconds)
    points = [TrailPoint(session_time_seconds=float(t), track_x=float(x), track_y=float(y),
                         quality="measured") for t, x, y in rows[start:end]]
    available = track_x is not None and track_y is not None and location_quality in (
        "measured", "estimated",
    )
    if track_x is not None and track_y is not None and location_quality in ("measured", "estimated"):
        current = TrailPoint(session_time_seconds=session_time_seconds, track_x=track_x,
                             track_y=track_y,
                             quality="measured" if location_quality == "measured" else "estimated")
        if points and points[-1].session_time_seconds == session_time_seconds:
            points[-1] = current
        else:
            points.append(current)
    segments: list[list[TrailPoint]] = []
    for point in points:
        if not segments or not _connected(segments[-1][-1], point):
            segments.append([point])
        else:
            segments[-1].append(point)
    heading = None
    if available and segments and len(segments[-1]) >= 2:
        left, right = segments[-1][-2:]
        if (left.track_x, left.track_y) != (right.track_x, right.track_y):
            heading = math.atan2(right.track_y - left.track_y, right.track_x - left.track_x)
    return LocationContext(driver_id=driver_id, session_time_seconds=session_time_seconds,
                           segments=segments, location_available=available,
                           heading_radians=heading,
                           heading_quality="estimated" if heading is not None else None)
