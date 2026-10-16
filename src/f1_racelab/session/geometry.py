"""Versioned circuit display geometry extracted from measured driving lines.

Coordinates retain the provider's unknown unit. Arc length here describes the
polyline, not surveyed circuit length or telemetry distance. No track edges,
pit lane, official start line, corners or sectors can be inferred reliably.
"""

from __future__ import annotations

import hashlib
import json
import math
from bisect import bisect_left, bisect_right
from collections import Counter
from datetime import datetime
from itertools import pairwise
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MIN_POINTS = 100
MAX_SAMPLE_GAP_SECONDS = 2.0
MAX_BOUNDARY_GAP_SECONDS = 1.5
MAX_CLOSURE_RATIO = 0.02
MAX_SEGMENT_RATIO = 0.04


class GeometryBounds(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    min_x: float
    max_x: float
    min_y: float
    max_y: float


class GeometryTransform(BaseModel):
    """normalized_xy = (provider_xy - origin_xy) * scale; no rotation."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    origin_x: float
    origin_y: float
    scale: float = Field(gt=0)


class GeometryProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    provider: Literal["OpenF1 v1"] = "OpenF1 v1"
    source_shape: Literal["measured_driving_line"] = "measured_driving_line"
    session_key: int = Field(gt=0)
    driver_id: str
    lap_number: int = Field(gt=0)
    source_samples_sha256: str
    source_lap_sha256: str
    closure: Literal["first_point_appended", "already_closed"]


class GeometryDiagnostics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    candidate_laps: int = Field(ge=0)
    accepted_laps: int = Field(ge=1)
    rejected_laps_by_reason: dict[str, int]
    retained_source_points: int = Field(ge=MIN_POINTS)
    max_sample_gap_seconds: float = Field(ge=0, le=MAX_SAMPLE_GAP_SECONDS)
    start_boundary_gap_seconds: float = Field(ge=0, le=MAX_BOUNDARY_GAP_SECONDS)
    end_boundary_gap_seconds: float = Field(ge=0, le=MAX_BOUNDARY_GAP_SECONDS)
    closure_ratio: float = Field(ge=0, le=MAX_CLOSURE_RATIO)
    max_segment_ratio: float = Field(ge=0, le=MAX_SEGMENT_RATIO)
    inferred_closure_length_provider_units: float = Field(ge=0)


class GeometryStartLine(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    xy: tuple[float, float]
    quality: Literal["estimated"] = "estimated"
    basis: Literal["first retained point of timed source lap"] = (
        "first retained point of timed source lap")


class CircuitGeometry(BaseModel):
    """Shared 2D/3D display geometry; missing physical measurements stay null."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    schema_version: Literal[1] = 1
    geometry_id: str
    layout_id: str
    source: str
    quality: Literal["estimated"] = "estimated"
    coordinate_system: Literal["openf1_approx_cartesian_unknown_unit"] = (
        "openf1_approx_cartesian_unknown_unit")
    coordinate_unit: Literal["unknown_provider_unit"] = "unknown_provider_unit"
    lap_start_seconds: float
    lap_end_seconds: float
    centerline_xy: list[tuple[float, float]] = Field(min_length=MIN_POINTS)
    normalized_centerline_xy: list[tuple[float, float]]
    cumulative_distance_provider_units: list[float]
    heading_radians: list[float]
    bounds: GeometryBounds
    transform: GeometryTransform
    closed: Literal[True] = True
    lap_length_provider_units: float = Field(gt=0)
    lap_length_meters: None = None
    width_meters: None = None
    pit_lane_xy: None = None
    corners: list = Field(default_factory=list, max_length=0)
    sectors: list = Field(default_factory=list, max_length=0)
    start_line: GeometryStartLine
    provenance: GeometryProvenance
    diagnostics: GeometryDiagnostics

    @model_validator(mode="after")
    def validate_geometry(self) -> CircuitGeometry:
        points = self.centerline_xy
        if points[0] != points[-1]:
            raise ValueError("Circuit display polyline must close explicitly")
        if self.lap_end_seconds <= self.lap_start_seconds:
            raise ValueError("Source lap end must follow start")
        if any(len(values) != len(points) for values in (
            self.normalized_centerline_xy, self.cumulative_distance_provider_units,
            self.heading_radians,
        )):
            raise ValueError("Geometry arrays must have equal lengths")
        distance = self.cumulative_distance_provider_units
        if distance[0] != 0 or any(b < a for a, b in pairwise(distance)):
            raise ValueError("Polyline arc distance must be nondecreasing from zero")
        if not math.isclose(distance[-1], self.lap_length_provider_units):
            raise ValueError("Polyline length must equal final arc distance")
        for index, ((x, y), (nx, ny)) in enumerate(zip(
            points, self.normalized_centerline_xy, strict=True,
        )):
            if not (math.isclose(nx, (x - self.transform.origin_x) * self.transform.scale,
                                 abs_tol=1e-12)
                    and math.isclose(ny, (y - self.transform.origin_y) * self.transform.scale,
                                     abs_tol=1e-12)):
                raise ValueError("Normalized geometry and transform disagree")
            if not (self.bounds.min_x <= x <= self.bounds.max_x
                    and self.bounds.min_y <= y <= self.bounds.max_y):
                raise ValueError("Geometry point outside reported bounds")
            if index:
                expected = math.hypot(x - points[index - 1][0], y - points[index - 1][1])
                if not math.isclose(distance[index] - distance[index - 1], expected,
                                    abs_tol=1e-8):
                    raise ValueError("Arc distance disagrees with source polyline")
        return self


def _sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, separators=(",", ":"), sort_keys=True,
                                     allow_nan=False).encode()).hexdigest()


def _candidate(samples: list[list[float]], start: float, end: float) -> tuple[list, dict] | str:
    """Reject rather than silently repair absent points, jumps or missing arcs."""
    times = [sample[0] for sample in samples]
    points = samples[bisect_left(times, start):bisect_right(times, end)]
    if len(points) < MIN_POINTS:
        return "too_few_points"
    if any(len(point) != 3 or not all(math.isfinite(v) for v in point) for point in points):
        return "invalid_point"
    gaps = [b[0] - a[0] for a, b in pairwise(points)]
    if min(gaps) <= 0:
        return "nonmonotonic_timestamps"
    if max(gaps) > MAX_SAMPLE_GAP_SECONDS:
        return "sample_gap"
    start_gap, end_gap = points[0][0] - start, end - points[-1][0]
    if max(start_gap, end_gap) > MAX_BOUNDARY_GAP_SECONDS:
        return "boundary_gap"
    segments = [math.hypot(b[1] - a[1], b[2] - a[2]) for a, b in pairwise(points)]
    length = sum(segments)
    if length <= 0:
        return "zero_length"
    closure_length = math.hypot(points[-1][1] - points[0][1],
                                points[-1][2] - points[0][2])
    closure_ratio = closure_length / length
    if closure_ratio > MAX_CLOSURE_RATIO:
        return "open_trace"
    max_segment_ratio = max(segments) / length
    if max_segment_ratio > MAX_SEGMENT_RATIO:
        return "coordinate_jump"
    return points, {"retained_source_points": len(points),
                    "max_sample_gap_seconds": max(gaps),
                    "start_boundary_gap_seconds": start_gap,
                    "end_boundary_gap_seconds": end_gap,
                    "closure_ratio": closure_ratio,
                    "max_segment_ratio": max_segment_ratio,
                    "inferred_closure_length_provider_units": closure_length}


def build_circuit_geometry(locations: dict[str, list[list[float]]], laps: list[dict], *,
                           clock_origin: datetime, session_key: int, layout_id: str,
                           pit_stops: list[dict] | None = None) -> CircuitGeometry:
    """Choose a validated measured lap without combining unrelated racing lines.

    Source selection is independent of row order: minimum closure ratio, then
    sample gap, boundary gap, driver number and lap number. All source points of
    the selected lap survive; only a short, explicitly inferred closing segment
    may be added. No smoothing or additional measurement is manufactured.
    """
    if clock_origin.tzinfo is None:
        raise ValueError("Geometry clock origin must include timezone")
    for driver, samples in locations.items():
        if any(len(point) != 3 or not all(math.isfinite(v) for v in point)
               for point in samples):
            raise ValueError(f"Invalid geometry source coordinates for driver {driver}")
        if any(b[0] <= a[0] for a, b in pairwise(samples)):
            raise ValueError(f"Geometry source timestamps must increase for driver {driver}")
    rejected: Counter[str] = Counter()
    accepted: list[tuple[tuple, list, dict, dict, float, float]] = []
    pit_laps = {(str(row["driver_number"]), int(row["lap_number"]))
                for row in pit_stops or [] if row.get("lap_number") is not None}
    for lap in laps:
        driver, number = str(lap.get("driver_number")), lap.get("lap_number")
        if lap.get("is_pit_out_lap") or (driver, number) in pit_laps:
            rejected["pit_lap"] += 1
            continue
        duration = lap.get("lap_duration")
        if not lap.get("date_start") or not isinstance(duration, (int, float)) or (
            not math.isfinite(duration) or duration <= 0 or not isinstance(number, int)
            or number < 1
        ):
            rejected["missing_timed_lap"] += 1
            continue
        when = datetime.fromisoformat(lap["date_start"])
        if when.tzinfo is None:
            raise ValueError("Geometry source lap timestamp must include timezone")
        start = (when - clock_origin).total_seconds()
        end = start + duration
        result = _candidate(locations.get(driver, []), start, end)
        if isinstance(result, str):
            rejected[result] += 1
            continue
        points, diagnostics = result
        score = (diagnostics["closure_ratio"], diagnostics["max_sample_gap_seconds"],
                 diagnostics["start_boundary_gap_seconds"] + diagnostics["end_boundary_gap_seconds"],
                 int(driver), number)
        accepted.append((score, points, diagnostics, lap, start, end))
    if not accepted:
        raise ValueError(f"No usable measured circuit driving line: {dict(rejected)}")
    _, samples, diagnostic, lap, start, end = min(accepted, key=lambda item: item[0])
    xy = [(float(x), float(y)) for _, x, y in samples]
    closure: Literal["first_point_appended", "already_closed"] = "already_closed"
    if xy[-1] != xy[0]:
        xy.append(xy[0])
        closure = "first_point_appended"
    distances = [0.0]
    headings = []
    for a, b in pairwise(xy):
        distances.append(distances[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
        headings.append(math.atan2(b[1] - a[1], b[0] - a[0]))
    headings.append(headings[0])
    bounds = GeometryBounds(min_x=min(x for x, _ in xy), max_x=max(x for x, _ in xy),
                            min_y=min(y for _, y in xy), max_y=max(y for _, y in xy))
    transform = GeometryTransform(origin_x=(bounds.min_x + bounds.max_x) / 2,
                                  origin_y=(bounds.min_y + bounds.max_y) / 2,
                                  scale=1 / max(bounds.max_x - bounds.min_x,
                                                bounds.max_y - bounds.min_y))
    normalized = [((x - transform.origin_x) * transform.scale,
                   (y - transform.origin_y) * transform.scale) for x, y in xy]
    provenance = GeometryProvenance(session_key=session_key, driver_id=str(lap["driver_number"]),
                                    lap_number=lap["lap_number"], source_samples_sha256=_sha(samples),
                                    source_lap_sha256=_sha(lap), closure=closure)
    identity = _sha({"schema_version": 1, "layout_id": layout_id,
                     "provenance": provenance.model_dump(mode="json"), "centerline_xy": xy})
    return CircuitGeometry(geometry_id=f"openf1-driving-line:{identity}", layout_id=layout_id,
        source=f"OpenF1 location, driver {lap['driver_number']} lap {lap['lap_number']} driving line",
        lap_start_seconds=start, lap_end_seconds=end, centerline_xy=xy,
        normalized_centerline_xy=normalized, cumulative_distance_provider_units=distances,
        heading_radians=headings, bounds=bounds, transform=transform,
        lap_length_provider_units=distances[-1], start_line=GeometryStartLine(xy=xy[0]),
        provenance=provenance, diagnostics=GeometryDiagnostics(candidate_laps=len(laps),
            accepted_laps=len(accepted), rejected_laps_by_reason=dict(sorted(rejected.items())),
            **diagnostic))
