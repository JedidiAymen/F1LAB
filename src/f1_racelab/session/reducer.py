"""Pure event reducer and deterministic seek for one authoritative clock."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from .contracts import (
    DriverState,
    Flag,
    FlagPayload,
    LapPayload,
    PitPayload,
    PitStopPayload,
    PositionPayload,
    RaceControlPayload,
    RaceState,
    RetirementPayload,
    SessionEvent,
    SessionId,
    StintPayload,
    TrackStatusObservation,
    TrackStatusPayload,
    TyreStintState,
    WeatherObservation,
    WeatherPayload,
)

FLAG_BY_STATUS: dict[str, Flag] = {
    "green": "green", "yellow": "yellow", "red": "red", "safety_car": "safety_car",
    "vsc": "vsc", "chequered": "chequered",
}


def _observation_metadata(event: SessionEvent) -> dict:
    return {"event_id": event.event_id, "source": event.source,
            "observed_at": event.observed_at, "session_time_seconds": event.session_time_seconds,
            "quality": event.quality}


def reduce_event(state: RaceState, event: SessionEvent) -> RaceState:
    """Apply one ordered event; duplicate IDs are idempotent.

    Reject nonmonotonic sequence/time so a late live packet must first be
    reordered into a replayable source timeline. The reducer never guesses
    official timing, lap progression or missing driver positions.
    """
    if state.session != event.session:
        raise ValueError("Event belongs to another session")
    fingerprint = hashlib.sha256(event.model_dump_json().encode()).hexdigest()
    if event.event_id in state.applied_event_ids:
        if state.applied_event_hashes[event.event_id] != fingerprint:
            raise ValueError("Event ID was reused with different content")
        return state
    if event.sequence <= state.last_sequence:
        raise ValueError("Event sequence is not strictly increasing")
    if event.session_time_seconds < state.session_time_seconds:
        raise ValueError("Event time moves backwards")

    drivers = dict(state.drivers)
    flag = state.flag
    flag_message = state.flag_message
    track_status = state.track_status
    weather = state.weather
    race_control_messages = state.race_control_messages
    payload = event.payload
    if isinstance(payload, FlagPayload):
        flag, flag_message = payload.flag, payload.message
        signal = TrackStatusPayload(status=payload.flag, message=payload.message or payload.flag,
                                    basis="canonical_flag_event")
        track_status = TrackStatusObservation.model_validate(
            _observation_metadata(event) | {"signal": signal})
    elif isinstance(payload, TrackStatusPayload):
        # Pending endings/restarts do not establish a steady global flag.
        flag, flag_message = FLAG_BY_STATUS.get(payload.status), payload.message
        track_status = TrackStatusObservation.model_validate(
            _observation_metadata(event) | {"signal": payload})
    elif isinstance(payload, WeatherPayload):
        weather = WeatherObservation.model_validate(
            _observation_metadata(event) | {"values": payload})
    elif isinstance(payload, RaceControlPayload):
        race_control_messages = (*race_control_messages, payload)
    else:
        prior = drivers.get(payload.driver_id, DriverState(driver_id=payload.driver_id))
        if isinstance(payload, PositionPayload):
            drivers[payload.driver_id] = prior.model_copy(update={
                "position": payload.position, "lap": payload.lap if payload.lap is not None else prior.lap,
                "position_quality": event.quality,
                "position_observed_at": event.observed_at,
                "gap_to_leader_seconds": (
                    payload.gap_to_leader_seconds if payload.gap_to_leader_seconds is not None
                    else prior.gap_to_leader_seconds
                ),
                "quality": event.quality, "observed_at": event.observed_at,
            })
        elif isinstance(payload, PitPayload):
            drivers[payload.driver_id] = prior.model_copy(update={
                "in_pit": payload.in_pit,
                "tyre_compound": payload.tyre_compound or prior.tyre_compound,
                "tyre_age_laps": payload.tyre_age_laps if payload.tyre_age_laps is not None else prior.tyre_age_laps,
                "quality": event.quality, "observed_at": event.observed_at,
            })
        elif isinstance(payload, RetirementPayload):
            drivers[payload.driver_id] = prior.model_copy(update={
                "retired": True, "quality": event.quality, "observed_at": event.observed_at,
            })
        elif isinstance(payload, LapPayload):
            if prior.lap is not None and payload.lap_number < prior.lap:
                raise ValueError("Driver lap number moves backwards")
            age = prior.tyre_age_laps
            if prior.stint_lap_start is not None and prior.tyre_age_at_stint_start is not None:
                age = prior.tyre_age_at_stint_start + payload.lap_number - prior.stint_lap_start + 1
            stint_history = prior.tyre_stints
            if stint_history:
                active_stint = stint_history[-1]
                if (active_stint.closed_by_event_id is None
                        and payload.lap_number >= active_stint.lap_start
                        and (active_stint.lap_end is None or payload.lap_number > active_stint.lap_end)):
                    stint_history = (*stint_history[:-1], active_stint.model_copy(
                        update={"lap_end": payload.lap_number,
                                "lap_end_quality": event.quality}))
            duration = payload.lap_duration_seconds
            best = min(duration, prior.best_lap_seconds) if duration and prior.best_lap_seconds else (
                duration or prior.best_lap_seconds
            )
            drivers[payload.driver_id] = prior.model_copy(update={
                "lap": payload.lap_number, "last_lap_seconds": duration,
                "best_lap_seconds": best, "tyre_age_laps": age,
                "tyre_stints": stint_history,
                "quality": event.quality, "observed_at": event.observed_at,
            })
        elif isinstance(payload, PitStopPayload):
            drivers[payload.driver_id] = prior.model_copy(update={
                "pit_count": prior.pit_count + 1,
                "last_pit_lane_seconds": payload.lane_duration_seconds,
                "last_pit_stop_seconds": payload.stop_duration_seconds,
                "quality": event.quality, "observed_at": event.observed_at,
            })
        elif isinstance(payload, StintPayload):
            stint_history_list = list(prior.tyre_stints)
            if stint_history_list:
                previous = stint_history_list[-1]
                if payload.stint_number <= previous.stint_number or payload.lap_start < previous.lap_start:
                    raise ValueError("Stint number and lap start cannot move backwards")
                last_completed_lap = prior.lap if prior.lap is not None else previous.lap_start
                end_lap = max(previous.lap_start, last_completed_lap)
                stint_history_list[-1] = previous.model_copy(update={
                    "lap_end": max(previous.lap_end or previous.lap_start, end_lap),
                    "lap_end_quality": prior.quality or event.quality,
                    "closed_by_event_id": event.event_id,
                })
            stint_history_list.append(TyreStintState(
                stint_number=payload.stint_number, lap_start=payload.lap_start,
                compound=payload.compound, tyre_age_at_start=payload.tyre_age_at_start,
                source_event_id=event.event_id,
                session_time_seconds=event.session_time_seconds,
                quality=event.quality, observed_at=event.observed_at,
            ))
            drivers[payload.driver_id] = prior.model_copy(update={
                "stint_number": payload.stint_number,
                "stint_lap_start": payload.lap_start,
                "tyre_compound": payload.compound,
                "tyre_age_at_stint_start": payload.tyre_age_at_start,
                "tyre_age_laps": payload.tyre_age_at_start,
                "tyre_stints": tuple(stint_history_list),
                "quality": event.quality, "observed_at": event.observed_at,
            })
    return state.model_copy(update={
        "schema_version": 3,
        "session_time_seconds": event.session_time_seconds,
        "flag": flag, "flag_message": flag_message, "drivers": drivers,
        "track_status": track_status, "weather": weather,
        "race_control_messages": race_control_messages,
        "last_sequence": event.sequence,
        "applied_event_ids": state.applied_event_ids | {event.event_id},
        "applied_event_hashes": state.applied_event_hashes | {event.event_id: fingerprint},
        "event_log": (*state.event_log, event.event_id),
    })


def seek_state(session: SessionId, events: Iterable[SessionEvent], at_seconds: float) -> RaceState:
    """Reconstruct state from the start at an exact session-clock cutoff."""
    if at_seconds < 0:
        raise ValueError("Seek time must be nonnegative")
    state = RaceState(session=session)
    for event in sorted(events, key=lambda item: (item.session_time_seconds, item.sequence)):
        if event.session_time_seconds > at_seconds:
            break
        state = reduce_event(state, event)
    return state.model_copy(update={"session_time_seconds": at_seconds})
