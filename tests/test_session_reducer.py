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
    LapPayload,
    PitPayload,
    PitStopPayload,
    PositionPayload,
    Quality,
    StintPayload,
)
from f1_racelab.session.replay_source import ReplaySource

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
    with pytest.raises(ValueError, match="reused"):
        reduce_event(state, first.model_copy(update={"payload": PositionPayload(driver_id="VER", position=2)}))
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


def test_lap_stint_and_pit_transitions_keep_units_and_order() -> None:
    timeline = [
        event(0, 0, "stint", StintPayload(driver_id="VER", stint_number=1,
                                          lap_start=1, compound="MEDIUM", tyre_age_at_start=0)),
        event(1, 90, "lap", LapPayload(driver_id="VER", lap_number=1,
                                       lap_duration_seconds=90.0)),
        event(2, 100, "pit_stop", PitStopPayload(driver_id="VER", lap_number=1,
                                                  lane_duration_seconds=24.0,
                                                  stop_duration_seconds=2.5)),
        event(3, 101, "stint", StintPayload(driver_id="VER", stint_number=2,
                                            lap_start=2, compound="HARD", tyre_age_at_start=0)),
        event(4, 189, "lap", LapPayload(driver_id="VER", lap_number=2,
                                        lap_duration_seconds=88.0)),
    ]
    state = seek_state(SESSION, timeline, 189).drivers["VER"]
    assert (state.lap, state.tyre_compound, state.tyre_age_laps) == (2, "HARD", 1)
    assert [(stint.stint_number, stint.lap_start, stint.lap_end, stint.compound)
            for stint in state.tyre_stints] == [
                (1, 1, 1, "MEDIUM"), (2, 2, 2, "HARD")]
    assert state.tyre_stints[0].quality == Quality.MEASURED
    before_second_stint = seek_state(SESSION, timeline, 100).drivers["VER"]
    assert [(stint.stint_number, stint.lap_end)
            for stint in before_second_stint.tyre_stints] == [(1, 1)]
    assert (state.pit_count, state.last_pit_lane_seconds, state.last_pit_stop_seconds) == (1, 24.0, 2.5)
    assert (state.last_lap_seconds, state.best_lap_seconds) == (88.0, 88.0)
    with pytest.raises(ValueError, match="lap number moves backwards"):
        reduce_event(seek_state(SESSION, timeline, 189),
                     event(5, 200, "lap", LapPayload(driver_id="VER", lap_number=1)))


def test_same_lap_stint_starts_are_retained_without_future_end_leakage() -> None:
    timeline = [
        event(0, 0, "stint", StintPayload(driver_id="VER", stint_number=1,
                                          lap_start=1, compound="MEDIUM")),
        event(1, 0, "stint", StintPayload(driver_id="VER", stint_number=2,
                                          lap_start=1, compound="HARD")),
        event(2, 90, "lap", LapPayload(driver_id="VER", lap_number=1,
                                        lap_duration_seconds=90.0)),
    ]
    at_start = seek_state(SESSION, timeline, 0).drivers["VER"].tyre_stints
    assert [(stint.compound, stint.lap_start, stint.lap_end) for stint in at_start] == [
        ("MEDIUM", 1, 1), ("HARD", 1, None)]
    assert at_start[0].closed_by_event_id == "test-1"
    before_lap_end = seek_state(SESSION, timeline, 89.999).drivers["VER"].tyre_stints
    assert before_lap_end[-1].lap_end is None
    after_lap_end = seek_state(SESSION, timeline, 90).drivers["VER"].tyre_stints
    assert after_lap_end[-1].lap_end == 1
    assert after_lap_end[-1].lap_end_quality == Quality.MEASURED


def test_replay_source_checkpoint_and_location_quality() -> None:
    events = [event(0, 0, "position", PositionPayload(driver_id="VER", position=1))]
    events.extend(event(i, float(i), "flag", FlagPayload(flag="yellow")) for i in range(1, 70))
    pack = {
        "schema_version": 2,
        "session": SESSION.model_dump(mode="json"),
        "clock_origin_utc": START.isoformat(),
        "events": [item.model_dump(mode="json") for item in events],
        "drivers": [{"driver_id": "VER"}],
        "locations": {"VER": [[0.0, 5, 5], [1.0, 25, 5], [20.0, 30, 5], [69.0, 50, 5]]},
        "intervals": {"VER": [[0.0, 0.0, 0.0, None, None]]},
    }
    source = ReplaySource(pack)
    assert len(source.checkpoint_indices) == 2
    assert source.state_at(0).drivers["VER"].location_quality == Quality.MEASURED
    middle = source.state_at(.5).drivers["VER"]
    assert (middle.track_x, middle.track_y, middle.location_quality) == (15.0, 5.0, Quality.ESTIMATED)
    assert source.state_at(5).drivers["VER"].track_x is None
    assert source.state_at(69).event_log == seek_state(SESSION, events, 69).event_log
    with pytest.raises(ValueError, match="outside"):
        source.state_at(70)
    bad = pack | {"locations": {"VER": [[1.0, 1, 1], [0.0, 2, 2]]}}
    with pytest.raises(ValueError, match="Unsorted"):
        ReplaySource(bad)
