"""Pure event reducer and deterministic seek for one authoritative clock."""

from __future__ import annotations

from collections.abc import Iterable

from .contracts import (
    DriverState,
    FlagPayload,
    PitPayload,
    PositionPayload,
    RaceControlPayload,
    RaceState,
    RetirementPayload,
    SessionEvent,
    SessionId,
)


def reduce_event(state: RaceState, event: SessionEvent) -> RaceState:
    """Apply one ordered event; duplicate IDs are idempotent.

    Reject nonmonotonic sequence/time so a late live packet must first be
    reordered into a replayable source timeline. The reducer never guesses
    official timing, lap progression or missing driver positions.
    """
    if state.session != event.session:
        raise ValueError("Event belongs to another session")
    if event.event_id in state.applied_event_ids:
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
                "gap_to_leader_seconds": payload.gap_to_leader_seconds,
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
    return state.model_copy(update={
        "session_time_seconds": event.session_time_seconds,
        "flag": flag, "flag_message": flag_message, "drivers": drivers,
        "race_control_messages": race_control_messages,
        "last_sequence": event.sequence,
        "applied_event_ids": state.applied_event_ids | {event.event_id},
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
