"""Pure event reducer and deterministic seek for one authoritative clock."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from .contracts import (
    DriverState,
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
)


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
    race_control_messages = state.race_control_messages
    payload = event.payload
    if isinstance(payload, FlagPayload):
        flag, flag_message = payload.flag, payload.message
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
            duration = payload.lap_duration_seconds
            best = min(duration, prior.best_lap_seconds) if duration and prior.best_lap_seconds else (
                duration or prior.best_lap_seconds
            )
            drivers[payload.driver_id] = prior.model_copy(update={
                "lap": payload.lap_number, "last_lap_seconds": duration,
                "best_lap_seconds": best, "tyre_age_laps": age,
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
            drivers[payload.driver_id] = prior.model_copy(update={
                "stint_number": payload.stint_number,
                "stint_lap_start": payload.lap_start,
                "tyre_compound": payload.compound,
                "tyre_age_at_stint_start": payload.tyre_age_at_start,
                "tyre_age_laps": payload.tyre_age_at_start,
                "quality": event.quality, "observed_at": event.observed_at,
            })
    return state.model_copy(update={
        "session_time_seconds": event.session_time_seconds,
        "flag": flag, "flag_message": flag_message, "drivers": drivers,
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
