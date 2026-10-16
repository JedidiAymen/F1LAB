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


@pytest.mark.parametrize(("field", "replacement", "message"), [
    ("bounded_point_count", 99, "Bounded point count"),
    ("maximum_sample_gap_seconds", 0.5, "Reported sample gap"),
])
def test_serialized_lap_rejects_inconsistent_quality_metadata(field, replacement, message):
    from f1_racelab.telemetry.contracts import LapTelemetry

    payload = comparison_lap(1, (72, 72, 72)).model_dump()
    payload[field] = replacement
    with pytest.raises(ValueError, match=message):
        LapTelemetry.model_validate(payload)


@pytest.mark.parametrize(("mutation", "message"), [
    ("delta", "delta must equal"),
    ("grid", "stated distance grid"),
    ("truncated", "complete uniform common grid"),
    ("shared_end", "shorter integrated lap"),
    ("elapsed_order", "elapsed times must increase"),
    ("elapsed_bound", "elapsed times must increase"),
])
def test_serialized_comparison_rejects_inconsistent_math(mutation, message):
    from f1_racelab.telemetry.contracts import LapComparison

    result = compare_laps(
        comparison_lap(1, (72, 72, 72)), comparison_lap(4, (72, 72, 72)),
        spacing_m=10, source_hashes={"laps": "a", "car_a": "b", "car_b": "c"},
    )
    payload = result.model_dump(mode="json")
    if mutation == "delta":
        payload["samples"][1]["delta_time_b_minus_a_seconds"] = 1
    elif mutation == "grid":
        payload["samples"][1]["distance_m"] = 11
    elif mutation == "truncated":
        payload["samples"].pop()
    elif mutation == "shared_end":
        payload["common_distance_end_m"] += 1
    elif mutation == "elapsed_order":
        payload["samples"][1]["elapsed_a_seconds"] = 0
    elif mutation == "elapsed_bound":
        payload["samples"][-1]["elapsed_b_seconds"] = 3
    with pytest.raises(ValueError, match=message):
        LapComparison.model_validate(payload)


@pytest.mark.parametrize("source_field", ["n_gear", "drs"])
def test_fractional_discrete_source_codes_are_rejected(source_field):
    rows = [car_row(1, i, speed=72) for i in range(3)]
    rows[1][source_field] = 2.5
    with pytest.raises(ValueError, match="must be an integer"):
        build_lap_telemetry(rows, lap_row(1), session_key=SESSION_KEY,
                            meeting_key=MEETING_KEY, driver_number=1)


def test_missing_channel_samples_stay_missing_on_shared_distance_grid():
    rows = [car_row(1, i, speed=72) for i in range(3)]
    rows[1]["throttle"] = None
    rows[1]["brake"] = None
    rows[1]["rpm"] = None
    rows[1]["n_gear"] = None
    rows[1]["drs"] = None
    lap_a = build_lap_telemetry(rows, lap_row(1), session_key=SESSION_KEY,
                                meeting_key=MEETING_KEY, driver_number=1)
    result = compare_laps(lap_a, comparison_lap(4, (72, 72, 72)), spacing_m=5,
                          source_hashes={"laps": "a", "car_a": "b", "car_b": "c"})
    at_missing = result.samples[4]  # 20 metres == one elapsed second
    assert at_missing.speed_a_kmh == 72
    assert at_missing.throttle_a_percent is None
    assert at_missing.brake_a_source_value is None
    assert at_missing.rpm_a is None
    assert at_missing.gear_a is None
    assert at_missing.drs_a_code is None
    assert at_missing.throttle_b_percent == 50
    assert result.samples[3].throttle_a_percent is None  # no interpolation across missing channel
    assert result.samples[3].gear_a == 5  # previous discrete source state
