"""Synthetic provider rows test replay normalization without network access."""

from datetime import UTC, datetime

from f1_racelab.session.contracts import Quality, SessionId
from f1_racelab.session.openf1_replay import (
    CLOCK_ORIGIN,
    _interval_samples,
    _location_samples,
    _timed_events,
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
