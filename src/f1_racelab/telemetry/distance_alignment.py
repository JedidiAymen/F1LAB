"""Build same-event lap comparisons on an estimated distance axis."""

from __future__ import annotations

from bisect import bisect_right
from datetime import datetime, timedelta
from itertools import pairwise
from math import floor, isfinite
from typing import Any, cast

from .contracts import (
    DistanceComparisonPoint,
    LapComparison,
    LapTelemetry,
    LapTelemetryPoint,
    _aware_timestamp,
)

DEFAULT_MAX_SAMPLE_GAP_SECONDS = 1.0
DEFAULT_DISTANCE_SPACING_M = 5.0
CONTINUOUS_FIELDS = ("speed_kmh", "throttle_percent", "rpm")
DISCRETE_FIELDS = ("brake_source_value", "gear", "drs_code")


def _number(value: object, field: str, *, optional: bool = False) -> float | None:
    if value is None and optional:
        return None
    try:
        number = float(cast(str | int | float, value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Telemetry field {field} is not numeric: {value!r}") from exc
    if not isfinite(number):
        raise ValueError(f"Telemetry field {field} must be finite")
    return number


def _raw_point(
    row: dict,
    start_utc: datetime,
    when: datetime | None = None,
) -> tuple[datetime, dict]:
    when = when or _aware_timestamp(row.get("date"), "car_data.date")
    values = {
        "speed_kmh": _number(row.get("speed"), "speed"),
        "throttle_percent": _number(row.get("throttle"), "throttle", optional=True),
        "brake_source_value": _number(row.get("brake"), "brake", optional=True),
        "rpm": _number(row.get("rpm"), "rpm", optional=True),
        "gear": row.get("n_gear"),
        "drs_code": row.get("drs"),
    }
    for field in ("throttle_percent", "brake_source_value"):
        value = values[field]
        if value is not None and value < 0:
            raise ValueError(f"Telemetry field {field} cannot be negative")
    for field in ("gear", "drs_code"):
        value = values[field]
        if value is not None:
            numeric = _number(value, field)
            if numeric is None or not numeric.is_integer():
                raise ValueError(f"Telemetry field {field} must be an integer")
            values[field] = int(numeric)
    return when, {**values, "elapsed_seconds": (when - start_utc).total_seconds()}


def _interpolate_time(
    rows: list[tuple[datetime, dict]],
    timestamps: list[datetime],
    target: datetime,
    start_utc: datetime,
    max_gap_seconds: float,
) -> dict:
    index = bisect_right(timestamps, target)
    if index and timestamps[index - 1] == target:
        values = rows[index - 1][1]
        return {**values, "elapsed_seconds": (target - start_utc).total_seconds()}
    if index == 0 or index >= len(rows):
        raise ValueError("Lap boundary is not bracketed by car_data samples")
    before_time, before = rows[index - 1]
    after_time, after = rows[index]
    gap = (after_time - before_time).total_seconds()
    if gap <= 0 or gap > max_gap_seconds:
        raise ValueError(f"Car-data gap {gap:.3f}s exceeds {max_gap_seconds:.3f}s limit")
    fraction = (target - before_time).total_seconds() / gap
    interpolated: dict[str, Any] = {}
    for field in CONTINUOUS_FIELDS:
        left, right = before[field], after[field]
        interpolated[field] = (
            None if left is None or right is None else float(left) + fraction * (float(right) - float(left))
        )
    # Discrete pedal/gear/DRS states use the last source value at or before the
    # requested instant. They are never averaged into fractional states.
    for field in DISCRETE_FIELDS:
        interpolated[field] = before[field]
    interpolated["elapsed_seconds"] = (target - start_utc).total_seconds()
    return interpolated


def build_lap_telemetry(
    car_data_rows: list[dict],
    lap_row: dict,
    *,
    session_key: int,
    meeting_key: int,
    driver_number: int,
    max_sample_gap_seconds: float = DEFAULT_MAX_SAMPLE_GAP_SECONDS,
) -> LapTelemetry:
    """Validate source rows, bound one lap and integrate speed into metres.

    `laps.date_start` is approximate in the provider contract; the lap interval
    and both interpolated boundary samples therefore remain estimated.
    """
    if not isfinite(max_sample_gap_seconds) or not 0 < max_sample_gap_seconds <= 5:
        raise ValueError("max_sample_gap_seconds must be in (0, 5]")
    if int(lap_row.get("session_key", -1)) != session_key:
        raise ValueError("Lap row has a different session_key")
    if int(lap_row.get("meeting_key", -1)) != meeting_key:
        raise ValueError("Lap row has a different meeting_key")
    if int(lap_row.get("driver_number", -1)) != driver_number:
        raise ValueError("Lap row has a different driver_number")
    if lap_row.get("is_pit_out_lap") is True:
        raise ValueError("Pit-out laps are excluded from clean lap comparison")
    start = _aware_timestamp(lap_row.get("date_start"), "laps.date_start")
    duration = _number(lap_row.get("lap_duration"), "lap_duration")
    if duration is None or duration <= 0:
        raise ValueError("Lap duration must be positive")
    end = start + timedelta(seconds=duration)
    normalized: list[tuple[datetime, dict]] = []
    lower_bound = start - timedelta(seconds=max_sample_gap_seconds)
    upper_bound = end + timedelta(seconds=max_sample_gap_seconds)
    for row in car_data_rows:
        if int(row.get("session_key", -1)) != session_key:
            raise ValueError("car_data row has a different session_key")
        if int(row.get("meeting_key", -1)) != meeting_key:
            raise ValueError("car_data row has a different meeting_key")
        if int(row.get("driver_number", -1)) != driver_number:
            raise ValueError("car_data row has a different driver_number")
        when = _aware_timestamp(row.get("date"), "car_data.date")
        if lower_bound <= when <= upper_bound:
            normalized.append(_raw_point(row, start, when))
    normalized.sort(key=lambda item: item[0])
    if len(normalized) < 2:
        raise ValueError("At least two car_data samples are required")
    times = [item[0] for item in normalized]
    if any(right <= left for left, right in pairwise(times)):
        raise ValueError("car_data timestamps must be unique")

    first = _interpolate_time(normalized, times, start, start, max_sample_gap_seconds)
    last = _interpolate_time(normalized, times, end, start, max_sample_gap_seconds)
    bounded = [first]
    bounded.extend(
        values for when, values in normalized if start < when < end
    )
    bounded.append(last)
    if len(bounded) < 3:
        raise ValueError("Lap window contains fewer than three bounded telemetry samples")
    points: list[LapTelemetryPoint] = []
    distance = 0.0
    for index, values in enumerate(bounded):
        elapsed = float(values["elapsed_seconds"])
        speed = float(values["speed_kmh"])
        if index:
            previous = points[-1]
            delta_seconds = elapsed - previous.elapsed_seconds
            if delta_seconds <= 0 or delta_seconds > max_sample_gap_seconds:
                raise ValueError(
                    f"Car-data interval {delta_seconds:.3f}s exceeds {max_sample_gap_seconds:.3f}s limit"
                )
            distance += (previous.speed_kmh + speed) / 2 / 3.6 * delta_seconds
            if distance <= previous.distance_m:
                raise ValueError("Integrated distance is not strictly increasing")
        points.append(LapTelemetryPoint(
            elapsed_seconds=elapsed,
            distance_m=distance,
            speed_kmh=speed,
            throttle_percent=values["throttle_percent"],
            brake_source_value=values["brake_source_value"],
            rpm=values["rpm"],
            gear=values["gear"],
            drs_code=values["drs_code"],
        ))
    intervals = [b.elapsed_seconds - a.elapsed_seconds for a, b in pairwise(points)]
    source_sample_count = sum(start <= when <= end for when in times)
    return LapTelemetry(
        session_key=session_key,
        meeting_key=meeting_key,
        driver_number=driver_number,
        lap_number=int(lap_row["lap_number"]),
        start_utc=start,
        lap_duration_seconds=duration,
        is_pit_out_lap=bool(lap_row.get("is_pit_out_lap", False)),
        source_sample_count=source_sample_count,
        bounded_point_count=len(points),
        interpolated_boundary_count=int(start not in times) + int(end not in times),
        maximum_sample_gap_seconds=max(intervals),
        integrated_distance_m=distance,
        points=tuple(points),
    )


def _at_distance(lap: LapTelemetry, target_m: float) -> dict[str, Any]:
    distances = [point.distance_m for point in lap.points]
    index = bisect_right(distances, target_m)
    if index == 0:
        return lap.points[0].model_dump()
    if index >= len(lap.points):
        return lap.points[-1].model_dump()
    before, after = lap.points[index - 1], lap.points[index]
    span = after.distance_m - before.distance_m
    fraction = (target_m - before.distance_m) / span
    left, right = before.model_dump(), after.model_dump()
    values: dict[str, Any] = {"distance_m": target_m}
    for field in ("elapsed_seconds", *CONTINUOUS_FIELDS):
        a, b = left[field], right[field]
        values[field] = None if a is None or b is None else float(a) + fraction * (float(b) - float(a))
    for field in DISCRETE_FIELDS:
        values[field] = left[field]
    return values


def compare_laps(
    lap_a: LapTelemetry,
    lap_b: LapTelemetry,
    *,
    source_hashes: dict[str, str],
    spacing_m: float = DEFAULT_DISTANCE_SPACING_M,
) -> LapComparison:
    """Interpolate two laps onto a uniform common integrated-distance grid."""
    if (lap_a.session_key, lap_a.meeting_key) != (lap_b.session_key, lap_b.meeting_key):
        raise ValueError("Lap comparison currently requires one shared session and meeting")
    if not isfinite(spacing_m) or not 0 < spacing_m <= 100:
        raise ValueError("spacing_m must be in (0, 100]")
    common_end = min(lap_a.integrated_distance_m, lap_b.integrated_distance_m)
    step_count = floor(common_end / spacing_m)
    if step_count < 1:
        raise ValueError("Common lap distance is too short for the requested spacing")
    comparison_points = []
    for step in range(step_count + 1):
        distance = step * spacing_m
        a, b = _at_distance(lap_a, distance), _at_distance(lap_b, distance)
        elapsed_a = float(a["elapsed_seconds"])
        elapsed_b = float(b["elapsed_seconds"])
        comparison_points.append(DistanceComparisonPoint(
            distance_m=distance,
            elapsed_a_seconds=elapsed_a,
            elapsed_b_seconds=elapsed_b,
            delta_time_b_minus_a_seconds=elapsed_b - elapsed_a,
            speed_a_kmh=a["speed_kmh"], speed_b_kmh=b["speed_kmh"],
            throttle_a_percent=a["throttle_percent"], throttle_b_percent=b["throttle_percent"],
            brake_a_source_value=a["brake_source_value"],
            brake_b_source_value=b["brake_source_value"],
            rpm_a=a["rpm"], rpm_b=b["rpm"],
            gear_a=a["gear"], gear_b=b["gear"],
            drs_a_code=a["drs_code"], drs_b_code=b["drs_code"],
        ))
    return LapComparison(
        session_key=lap_a.session_key,
        meeting_key=lap_a.meeting_key,
        lap_a=lap_a,
        lap_b=lap_b,
        sample_spacing_m=spacing_m,
        common_distance_end_m=common_end,
        source_hashes=source_hashes,
        samples=tuple(comparison_points),
    )
