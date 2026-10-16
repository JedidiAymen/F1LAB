"""Synthetic provider rows test replay normalization without network access."""

from datetime import UTC, datetime

import pytest

from f1_racelab.session.contracts import Quality, SessionId
from f1_racelab.session.openf1_replay import (
    CLOCK_ORIGIN,
    _interval_samples,
    _location_samples,
    _timed_events,
    _verify_pack_against_results,
)


def test_location_sampling_preserves_only_real_nonzero_points() -> None:
    rows = [
        {"date": "2025-09-07T12:59:59+00:00", "x": 4, "y": 4},
        {"date": "2025-09-07T13:00:00.100+00:00", "x": 0, "y": 0},
        {"date": "2025-09-07T13:00:00.150+00:00", "x": 10, "y": 20},
        {"date": "2025-09-07T13:00:00.300+00:00", "x": 12, "y": 22},
        {"date": "2025-09-07T13:00:00.600+00:00", "x": 30, "y": 40},
    ]
    samples, coverage = _location_samples(rows)
    assert samples == [[0.3, 12, 22], [0.6, 30, 40]]
    assert coverage == {"raw": 5, "sampled": 2, "removed_pre_clock": 1, "removed_zero": 1}


def test_lap_completion_is_estimated_at_end_and_source_start_is_retained() -> None:
    raw = {key: [] for key in ("position", "laps", "pit", "stints", "race_control")}
    raw["position"] = [{"date": "2025-09-07T12:59:00+00:00",
                        "driver_number": 1, "position": 1}]
    raw["laps"] = [{"date_start": "2025-09-07T13:03:00+00:00",
                    "driver_number": 1, "lap_number": 1, "lap_duration": 90.0}]
    raw["stints"] = [{"driver_number": 1, "stint_number": 1, "lap_start": 1,
                      "compound": "MEDIUM", "tyre_age_at_start": 0}]
    session = SessionId(season=2025, round=16, kind="race", provider_key="openf1:9912")
    events, counts = _timed_events(raw, session, datetime(2026, 1, 1, tzinfo=UTC))
    assert counts == {"position_seed": 1, "stint": 1, "lap": 1}
    assert [item.session_time_seconds for item in events] == [0, 180, 270]
    lap = events[-1]
    assert lap.quality == Quality.ESTIMATED
    assert lap.source_timestamp == CLOCK_ORIGIN.replace(minute=3)
    assert lap.observed_at == CLOCK_ORIGIN.replace(minute=4, second=30)


def test_interval_sampling_keeps_lapped_gap_text() -> None:
    rows = [{"date": "2025-09-07T13:00:01+00:00", "driver_number": 4,
             "gap_to_leader": "+1 LAP", "interval": 2.5}]
    assert _interval_samples(rows)["4"] == [[1.0, None, 2.5, "+1 LAP", None]]


def test_another_session_uses_its_own_clock_and_event_identity() -> None:
    raw = {key: [] for key in ("position", "laps", "pit", "stints", "race_control")}
    raw["position"] = [{"date": "2024-11-03T15:31:00Z", "driver_number": 1, "position": 2}]
    raw["stints"] = [{"driver_number": 18, "lap_start": None}]
    origin = datetime(2024, 11, 3, 15, 30, tzinfo=UTC)
    session = SessionId(season=2024, round=21, kind="race", provider_key="openf1:9636")
    events, counts = _timed_events(raw, session, origin, origin)
    assert events[0].session_time_seconds == 60
    assert events[0].event_id == "openf1:9636:position:0"
    assert counts["stints_without_lap_start"] == 1
    samples, _ = _location_samples(
        [{"date": "2024-11-03T15:30:01Z", "x": 10, "y": 20}], clock_origin=origin)
    assert samples == [[1.0, 10, 20]]


def test_result_qa_does_not_turn_missing_disqualified_laps_into_zero() -> None:
    pack = {
        "schema_version": 1, "session": {"season": 2024, "round": 21, "kind": "race"},
        "clock_origin_utc": "2024-11-03T15:30:00Z", "drivers": [{"driver_id": "27"}],
        "events": [], "locations": {"27": [[0, 1, 1], [1, 2, 2]]}, "intervals": {},
    }
    result = {"driver_number": 27, "position": None, "number_of_laps": None, "dsq": True}
    qa = _verify_pack_against_results(pack, [result])
    assert qa["lap_counts_matching"] == 0
    assert qa["unavailable_result_lap_counts"] == 1
    with pytest.raises(ValueError, match="laps"):
        _verify_pack_against_results(pack, [{**result, "number_of_laps": 1}])
