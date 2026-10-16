"""Versioned session event and state contracts for replay and simulation.

Every field displayed as timing truth must carry a provider observation. A
renderer may interpolate positions, but that result must use estimated quality.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

type Flag = Literal["green", "yellow", "red", "safety_car", "vsc", "chequered"]
type TrackStatus = Flag | Literal[
    "running_unknown", "suspended", "vsc_ending", "safety_car_ending"
]


class Quality(StrEnum):
    MEASURED = "measured"
    ESTIMATED = "estimated"
    SIMULATED = "simulated"


class SessionId(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    season: int = Field(ge=1950)
    round: int = Field(ge=1)
    kind: Literal["race", "qualifying", "sprint"]
    provider_key: str | None = None


class DriverState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    driver_id: str
    position: int | None = Field(default=None, ge=1)
    position_quality: Quality | None = None
    position_observed_at: datetime | None = None
    lap: int | None = Field(default=None, ge=0)
    last_lap_seconds: float | None = Field(default=None, gt=0)
    best_lap_seconds: float | None = Field(default=None, gt=0)
    gap_to_leader_seconds: float | None = Field(default=None, ge=0)
    gap_to_leader_text: str | None = None
    interval_ahead_seconds: float | None = Field(default=None, ge=0)
    interval_ahead_text: str | None = None
    interval_observed_at: datetime | None = None
    tyre_compound: str | None = None
    tyre_age_laps: int | None = Field(default=None, ge=0)
    stint_number: int | None = Field(default=None, ge=1)
    stint_lap_start: int | None = Field(default=None, ge=1)
    tyre_age_at_stint_start: int | None = Field(default=None, ge=0)
    pit_count: int = Field(default=0, ge=0)
    last_pit_lane_seconds: float | None = Field(default=None, gt=0)
    last_pit_stop_seconds: float | None = Field(default=None, gt=0)
    in_pit: bool = False
    retired: bool = False
    quality: Quality | None = None
    observed_at: datetime | None = None
    track_x: float | None = None
    track_y: float | None = None
    location_quality: Quality | None = None
    location_observed_at: datetime | None = None


class PositionPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    driver_id: str
    position: int = Field(ge=1)
    lap: int | None = Field(default=None, ge=0)
    gap_to_leader_seconds: float | None = Field(default=None, ge=0)


class PitPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    driver_id: str
    in_pit: bool
    tyre_compound: str | None = None
    tyre_age_laps: int | None = Field(default=None, ge=0)


class LapPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    driver_id: str
    lap_number: int = Field(ge=1)
    lap_duration_seconds: float | None = Field(default=None, gt=0)


class PitStopPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    driver_id: str
    lap_number: int = Field(ge=1)
    lane_duration_seconds: float | None = Field(default=None, gt=0)
    stop_duration_seconds: float | None = Field(default=None, gt=0)


class StintPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    driver_id: str
    stint_number: int = Field(ge=1)
    lap_start: int = Field(ge=1)
    compound: str
    tyre_age_at_start: int | None = Field(default=None, ge=0)


class FlagPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    flag: Flag
    message: str | None = None


class RetirementPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    driver_id: str
    reason: str | None = None


class RaceControlPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    category: str
    message: str
    flag: str | None = None
    scope: str | None = None
    sector: int | None = Field(default=None, ge=1)
    driver_id: str | None = None


class WeatherPayload(BaseModel):
    """Provider weather readings; rainfall is presence, not intensity or grip."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    air_temperature_c: float | None = None
    track_temperature_c: float | None = None
    humidity_percent: float | None = Field(default=None, ge=0, le=100)
    pressure_mbar: float | None = Field(default=None, gt=0)
    wind_direction_degrees: float | None = Field(default=None, ge=0, le=359)
    wind_speed_mps: float | None = Field(default=None, ge=0)
    rainfall: bool | None = Field(default=None, strict=True)

    @model_validator(mode="after")
    def has_observation(self) -> WeatherPayload:
        if all(value is None for value in self.model_dump().values()):
            raise ValueError("Weather payload contains no observations")
        return self


class TrackStatusPayload(BaseModel):
    """Last unambiguous track-wide source signal, including pending endings."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    status: TrackStatus
    message: str = Field(min_length=1)
    basis: Literal["track_flag", "safety_car_message", "session_status", "canonical_flag_event"]


class ObservationMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    event_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    observed_at: AwareDatetime
    session_time_seconds: float = Field(ge=0)
    quality: Quality


class WeatherObservation(ObservationMetadata):
    values: WeatherPayload
    # Freshness policy for display/consumers, not a claim of measurement rate.
    max_age_seconds: float = Field(default=120.0, gt=0)


class TrackStatusObservation(ObservationMetadata):
    signal: TrackStatusPayload


class SessionEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1, 2] = 2
    session: SessionId
    event_id: str = Field(min_length=1)
    type: Literal["position", "pit", "lap", "pit_stop", "stint", "flag", "retirement",
                  "race_control", "weather", "track_status"]
    source: str = Field(min_length=1)
    source_timestamp: datetime
    observed_at: datetime
    ingested_at: datetime
    session_time_seconds: float = Field(ge=0)
    sequence: int = Field(ge=0)
    applicable_lap: int | None = Field(default=None, ge=0)
    quality: Quality
    payload: (PositionPayload | PitPayload | LapPayload | PitStopPayload | StintPayload
              | FlagPayload | RetirementPayload | RaceControlPayload | WeatherPayload
              | TrackStatusPayload)

    @model_validator(mode="after")
    def validate_payload(self) -> SessionEvent:
        if self.schema_version == 1 and self.type in {"weather", "track_status"}:
            raise ValueError("Context events require schema_version 2")
        expected = {"position": PositionPayload, "pit": PitPayload,
                    "lap": LapPayload, "pit_stop": PitStopPayload, "stint": StintPayload,
                    "flag": FlagPayload, "retirement": RetirementPayload,
                    "race_control": RaceControlPayload, "weather": WeatherPayload,
                    "track_status": TrackStatusPayload}
        if not isinstance(self.payload, expected[self.type]):
            # Pydantic wraps ValueError into a public ValidationError.
            raise ValueError(f"{self.type} event requires {expected[self.type].__name__}")  # noqa: TRY004
        for name in ("source_timestamp", "observed_at", "ingested_at"):
            if getattr(self, name).tzinfo is None:
                raise ValueError(f"{name} must have timezone information")
        return self


class RaceState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1, 2] = 2
    session: SessionId
    capabilities: tuple[str, ...] = ()
    session_time_seconds: float = Field(default=0, ge=0)
    flag: Flag | None = None
    flag_message: str | None = None
    track_status: TrackStatusObservation | None = None
    weather: WeatherObservation | None = None
    drivers: dict[str, DriverState] = Field(default_factory=dict)
    last_sequence: int = -1
    applied_event_ids: frozenset[str] = frozenset()
    applied_event_hashes: dict[str, str] = Field(default_factory=dict)
    event_log: tuple[str, ...] = ()
    race_control_messages: tuple[RaceControlPayload, ...] = ()
