"""Typed contracts for source-labelled distance-aligned lap telemetry."""

from __future__ import annotations

from datetime import datetime
from math import floor, isclose
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class LapTelemetryPoint(BaseModel):
    """One telemetry sample with distance integrated from its reported speed."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    elapsed_seconds: float = Field(ge=0)
    distance_m: float = Field(ge=0)
    speed_kmh: float = Field(ge=0, le=450)
    throttle_percent: float | None = Field(default=None, ge=0)
    brake_source_value: float | None = Field(default=None, ge=0)
    rpm: float | None = Field(default=None, ge=0)
    gear: int | None = Field(default=None, ge=0, le=8)
    drs_code: int | None = Field(default=None, ge=0)


class LapTelemetry(BaseModel):
    """One source lap bounded by the provider's approximate start timestamp."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    session_key: int = Field(gt=0)
    meeting_key: int = Field(gt=0)
    driver_number: int = Field(gt=0)
    lap_number: int = Field(ge=1)
    start_utc: AwareDatetime
    lap_duration_seconds: float = Field(gt=0)
    is_pit_out_lap: bool = False
    start_quality: Literal["estimated"] = "estimated"
    source_sample_count: int = Field(ge=1)
    bounded_point_count: int = Field(ge=2)
    interpolated_boundary_count: int = Field(ge=0, le=2)
    maximum_sample_gap_seconds: float = Field(gt=0)
    integrated_distance_m: float = Field(gt=0)
    points: tuple[LapTelemetryPoint, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def ordered_samples(self) -> LapTelemetry:
        previous_time = -1.0
        previous_distance = -1.0
        for point in self.points:
            if point.elapsed_seconds <= previous_time:
                raise ValueError("Lap telemetry times must increase")
            if point.distance_m <= previous_distance:
                raise ValueError("Lap telemetry distance must increase")
            previous_time = point.elapsed_seconds
            previous_distance = point.distance_m
        if abs(self.points[0].elapsed_seconds) > 1e-6:
            raise ValueError("Lap telemetry must begin at elapsed time zero")
        if abs(self.points[0].distance_m) > 1e-6:
            raise ValueError("Lap telemetry distance must begin at zero")
        if self.bounded_point_count != len(self.points):
            raise ValueError("Bounded point count must match telemetry points")
        largest_gap = max(b.elapsed_seconds - a.elapsed_seconds
                          for a, b in zip(self.points, self.points[1:]))
        if not isclose(largest_gap, self.maximum_sample_gap_seconds, abs_tol=1e-6):
            raise ValueError("Reported sample gap disagrees with telemetry points")
        if abs(self.points[-1].elapsed_seconds - self.lap_duration_seconds) > 1e-6:
            raise ValueError("Lap telemetry must end at its lap duration")
        if abs(self.points[-1].distance_m - self.integrated_distance_m) > 1e-6:
            raise ValueError("Integrated distance must match the final point")
        return self


class DistanceComparisonPoint(BaseModel):
    """Both laps sampled at one shared, estimated distance from their starts."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    distance_m: float = Field(ge=0)
    elapsed_a_seconds: float = Field(ge=0)
    elapsed_b_seconds: float = Field(ge=0)
    delta_time_b_minus_a_seconds: float
    speed_a_kmh: float = Field(ge=0, le=450)
    speed_b_kmh: float = Field(ge=0, le=450)
    throttle_a_percent: float | None = Field(default=None, ge=0)
    throttle_b_percent: float | None = Field(default=None, ge=0)
    brake_a_source_value: float | None = Field(default=None, ge=0)
    brake_b_source_value: float | None = Field(default=None, ge=0)
    rpm_a: float | None = Field(default=None, ge=0)
    rpm_b: float | None = Field(default=None, ge=0)
    gear_a: int | None = Field(default=None, ge=0, le=8)
    gear_b: int | None = Field(default=None, ge=0, le=8)
    drs_a_code: int | None = Field(default=None, ge=0)
    drs_b_code: int | None = Field(default=None, ge=0)
    quality: Literal["estimated"] = "estimated"


class LapComparison(BaseModel):
    """Reproducible two-lap artifact with provenance and a shared distance grid."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    session_key: int = Field(gt=0)
    meeting_key: int = Field(gt=0)
    source: Literal["OpenF1 v1"] = "OpenF1 v1"
    lap_a: LapTelemetry
    lap_b: LapTelemetry
    alignment_method: Literal["trapezoidal_speed_integral"] = "trapezoidal_speed_integral"
    distance_quality: Literal["estimated"] = "estimated"
    sample_spacing_m: float = Field(gt=0)
    common_distance_end_m: float = Field(gt=0)
    source_hashes: dict[str, str] = Field(min_length=3)
    samples: tuple[DistanceComparisonPoint, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def valid_comparison(self) -> LapComparison:
        if (self.lap_a.session_key, self.lap_a.meeting_key) != (self.session_key, self.meeting_key):
            raise ValueError("Lap A does not belong to the comparison session")
        if (self.lap_b.session_key, self.lap_b.meeting_key) != (self.session_key, self.meeting_key):
            raise ValueError("Lap B does not belong to the comparison session")
        if self.lap_a.driver_number == self.lap_b.driver_number and self.lap_a.lap_number == self.lap_b.lap_number:
            raise ValueError("A lap cannot be compared with itself")
        expected_end = min(self.lap_a.integrated_distance_m, self.lap_b.integrated_distance_m)
        if not isclose(self.common_distance_end_m, expected_end, abs_tol=1e-6):
            raise ValueError("Shared distance must equal the shorter integrated lap")
        if len(self.samples) != floor(expected_end / self.sample_spacing_m) + 1:
            raise ValueError("Comparison must cover the complete uniform common grid")
        previous = -1.0
        previous_a = previous_b = -1.0
        for index, point in enumerate(self.samples):
            if point.distance_m <= previous:
                raise ValueError("Comparison distances must strictly increase")
            if not isclose(point.distance_m, index * self.sample_spacing_m, abs_tol=1e-6):
                raise ValueError("Comparison samples must follow the stated distance grid")
            if not (previous_a < point.elapsed_a_seconds <= self.lap_a.lap_duration_seconds
                    and previous_b < point.elapsed_b_seconds <= self.lap_b.lap_duration_seconds):
                raise ValueError("Comparison elapsed times must increase inside their source laps")
            if not isclose(point.delta_time_b_minus_a_seconds,
                           point.elapsed_b_seconds - point.elapsed_a_seconds, abs_tol=1e-9):
                raise ValueError("Comparison delta must equal elapsed B minus elapsed A")
            previous = point.distance_m
            previous_a, previous_b = point.elapsed_a_seconds, point.elapsed_b_seconds
        if self.samples[0].elapsed_a_seconds != 0 or self.samples[0].elapsed_b_seconds != 0:
            raise ValueError("Comparison must begin at both lap starts")
        if self.samples[-1].distance_m > self.common_distance_end_m + 1e-6:
            raise ValueError("Comparison grid extends beyond shared lap distance")
        return self


def _aware_timestamp(value: object, field_name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"Invalid {field_name} timestamp: {value}") from exc
    else:
        raise TypeError(f"Missing {field_name} timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} timestamp must include a timezone")
    return parsed
