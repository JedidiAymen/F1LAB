from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from f1_racelab.telemetry.distance_alignment import build_lap_telemetry, compare_laps

SESSION_KEY = 9912
MEETING_KEY = 1268
START = datetime(2025, 9, 7, 14, tzinfo=UTC)


def car_row(
    driver: int,
    second: float,
    *,
    speed: int,
    throttle: int = 50,
    brake: int = 0,
    rpm: int = 8000,
    gear: int = 5,
    drs: int = 0,
) -> dict:
    when = START + timedelta(seconds=second)
    return {
        "date": when.isoformat(),
        "session_key": SESSION_KEY,
        "meeting_key": MEETING_KEY,
        "driver_number": driver,
        "speed": speed,
        "throttle": throttle,
        "brake": brake,
        "rpm": rpm,
        "n_gear": gear,
        "drs": drs,
    }


def lap_row(driver: int, *, start: datetime = START, duration: float = 2.0,
            pit_out: bool = False, lap: int = 5) -> dict:
    return {
        "session_key": SESSION_KEY,
        "meeting_key": MEETING_KEY,
        "driver_number": driver,
        "lap_number": lap,
        "date_start": start.isoformat(),
        "lap_duration": duration,
        "is_pit_out_lap": pit_out,
    }


def comparison_lap(driver: int, speeds: tuple[int, int, int]):
    rows = [car_row(driver, i, speed=speed) for i, speed in enumerate(speeds)]
    return build_lap_telemetry(
        rows, lap_row(driver), session_key=SESSION_KEY,
        meeting_key=MEETING_KEY, driver_number=driver,
    )


def test_speed_integrates_to_metres_and_channels_stay_source_faithful() -> None:
    lap_a = build_lap_telemetry(
        [
            car_row(1, 0, speed=36, throttle=40, gear=2, drs=0),
            car_row(1, 1, speed=54, throttle=80, brake=104, gear=3, drs=8),
            car_row(1, 2, speed=72, throttle=104, brake=100, gear=4, drs=12),
        ], lap_row(1), session_key=SESSION_KEY,
        meeting_key=MEETING_KEY, driver_number=1,
    )
    lap_b = comparison_lap(4, (54, 54, 54))

    assert lap_a.integrated_distance_m == pytest.approx(30.0)
    assert lap_a.points[0].distance_m == 0
    assert lap_a.points[-1].elapsed_seconds == 2
    assert lap_a.points[1].brake_source_value == 104
    assert lap_a.points[-1].throttle_percent == 104

    comparison = compare_laps(
        lap_a,
        lap_b,
        spacing_m=5,
        source_hashes={"laps": "a" * 64, "car_a": "b" * 64, "car_b": "c" * 64},
    )
    assert len(comparison.samples) == 7
    assert [point.distance_m for point in comparison.samples] == list(range(0, 31, 5))
    assert comparison.samples[0].delta_time_b_minus_a_seconds == 0
    assert comparison.samples[3].delta_time_b_minus_a_seconds == pytest.approx(-1 / 7)
    assert comparison.samples[3].brake_a_source_value == 104
    assert comparison.samples[3].drs_a_code == 8
    assert all(point.quality == "estimated" for point in comparison.samples)


def test_approximate_lap_start_gets_interpolated_boundary_samples() -> None:
    lap = build_lap_telemetry(
        [
            car_row(1, 0, speed=36, throttle=0),
            car_row(1, 1, speed=72, throttle=100),
            car_row(1, 2, speed=36, throttle=0),
        ],
        lap_row(1, start=START + timedelta(seconds=0.25), duration=1.5),
        session_key=SESSION_KEY,
        meeting_key=MEETING_KEY,
        driver_number=1,
    )

    assert lap.points[0].elapsed_seconds == 0
    assert lap.points[0].speed_kmh == pytest.approx(45)
    assert lap.points[-1].elapsed_seconds == pytest.approx(1.5)
    assert lap.points[-1].speed_kmh == pytest.approx(45)
    assert lap.integrated_distance_m == pytest.approx(24.375)


def test_long_sampling_gap_is_rejected_instead_of_bridged() -> None:
    rows = [
        car_row(1, 0, speed=36),
        car_row(1, 1.5, speed=36),
        car_row(1, 2, speed=36),
    ]

    with pytest.raises(ValueError, match="exceeds 1.000s limit"):
        build_lap_telemetry(
            rows, lap_row(1), session_key=SESSION_KEY,
            meeting_key=MEETING_KEY, driver_number=1,
        )


def test_source_identity_and_pit_out_laps_are_checked() -> None:
    rows = [car_row(1, i, speed=72) for i in range(3)]
    with pytest.raises(ValueError, match="Pit-out laps"):
        build_lap_telemetry(
            rows, lap_row(1, pit_out=True), session_key=SESSION_KEY,
            meeting_key=MEETING_KEY, driver_number=1,
        )
    with pytest.raises(ValueError, match="different driver_number"):
        build_lap_telemetry(
            rows, lap_row(4), session_key=SESSION_KEY,
            meeting_key=MEETING_KEY, driver_number=4,
        )


def test_comparison_requires_a_shared_session_and_valid_spacing() -> None:
    lap_a = comparison_lap(1, (72, 72, 72))
    lap_b = comparison_lap(4, (72, 72, 72))
    with pytest.raises(ValueError, match="requires one shared session"):
        compare_laps(
            lap_a, lap_b.model_copy(update={"session_key": SESSION_KEY + 1}),
            source_hashes={"laps": "a", "car_a": "b", "car_b": "c"},
        )
    with pytest.raises(ValueError, match="spacing_m"):
        compare_laps(
            lap_a, lap_b, spacing_m=0,
            source_hashes={"laps": "a", "car_a": "b", "car_b": "c"},
        )
