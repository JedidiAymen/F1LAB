"""Synthetic contract tests; real provider replay fixtures follow in P1."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from f1_racelab.session import (
    RaceState,
    SessionEvent,
    SessionId,
    reduce_event,
    seek_state,
)
from f1_racelab.session.contracts import (
    FlagPayload,
    PitPayload,
    PositionPayload,
    Quality,
)

SESSION = SessionId(season=2025, round=16, kind="race", provider_key="openf1:2025:16")
START = datetime(2025, 9, 7, 13, 0, tzinfo=UTC)


def event(seq: int, seconds: float, kind: str, payload: object, **overrides: object) -> SessionEvent:
    values = {"session": SESSION, "event_id": f"test-{seq}", "type": kind,
              "source": "test-fixture", "source_timestamp": START + timedelta(seconds=seconds),
              "observed_at": START + timedelta(seconds=seconds),
              "ingested_at": START + timedelta(seconds=seconds + 1),
              "session_time_seconds": seconds, "sequence": seq,
              "quality": Quality.MEASURED, "payload": payload}
    return SessionEvent.model_validate(values | overrides)


def test_reducer_idempotence_order_and_session_guard() -> None:
    first = event(0, 10, "position", PositionPayload(driver_id="VER", position=1, lap=1))
    second = event(1, 20, "flag", FlagPayload(flag="safety_car", message="SC deployed"))
    state = reduce_event(RaceState(session=SESSION), first)
    assert reduce_event(state, first) is state
    assert state.drivers["VER"].position == 1
    assert reduce_event(state, second).flag == "safety_car"
    with pytest.raises(ValueError, match="sequence"):
        reduce_event(state, event(0, 15, "flag", FlagPayload(flag="yellow"), event_id="new"))
    with pytest.raises(ValueError, match="backwards"):
        reduce_event(state, event(2, 5, "flag", FlagPayload(flag="yellow")))
    with pytest.raises(ValueError, match="another session"):
        reduce_event(state, event(2, 25, "flag", FlagPayload(flag="yellow"),
                                  session=SessionId(season=2024, round=16, kind="race")))


def test_seek_is_deterministic_and_keeps_all_panels_on_one_time() -> None:
    timeline = [
        event(0, 10, "position", PositionPayload(driver_id="VER", position=1, lap=1)),
        event(1, 15, "pit", PitPayload(driver_id="VER", in_pit=True)),
        event(2, 20, "flag", FlagPayload(flag="vsc", message="Virtual safety car")),
        event(3, 25, "pit", PitPayload(driver_id="VER", in_pit=False, tyre_compound="HARD")),
    ]
    forward = RaceState(session=SESSION)
    for item in timeline[:3]:
        forward = reduce_event(forward, item)
    at_20 = seek_state(SESSION, reversed(timeline), 20)
    assert at_20 == forward
    assert at_20.drivers["VER"].in_pit
    assert at_20.flag == "vsc"
    assert seek_state(SESSION, timeline, 24).drivers["VER"].in_pit
    assert not seek_state(SESSION, timeline, 25).drivers["VER"].in_pit


def test_event_contract_rejects_payload_mismatch_and_naive_time() -> None:
    with pytest.raises(ValidationError, match="requires PositionPayload"):
        event(0, 0, "position", FlagPayload(flag="green"))
    with pytest.raises(ValidationError, match="timezone"):
        event(0, 0, "flag", FlagPayload(flag="green"), observed_at=START.replace(tzinfo=None))
