"""Synthetic trail tests exercise temporal honesty and disconnected coverage."""

import math

import pytest
from pydantic import ValidationError

from f1_racelab.session.location_history import LocationContext, build_location_context


def _context(rows: list[list[float]], *, time: float = 2., x: float | None = 20.,
             y: float | None = 0., quality: str | None = "measured") -> LocationContext:
    return build_location_context(rows, driver_id="1", session_time_seconds=time,
                                  track_x=x, track_y=y, location_quality=quality)


def test_trail_uses_past_samples_and_existing_estimated_current_point() -> None:
    rows = [[0., 0., 0.], [1., 10., 10.], [2., 20., 20.], [3., 30., 30.]]
    result = _context(rows, time=1.5, x=15., y=15., quality="estimated")
    assert result.session_time_seconds == 1.5
    assert [p.session_time_seconds for p in result.segments[0]] == [0., 1., 1.5]
    assert [p.quality for p in result.segments[0]] == ["measured", "measured", "estimated"]
    assert result.segments[0][-1].track_x == 15.
    assert result.heading_radians == math.pi / 4
    assert result.heading_quality == "estimated"
    assert result.coordinate_system == "openf1_approx_cartesian_unknown_unit"
    assert result.location_available
    assert rows[-1] == [3., 30., 30.]  # never mutate source or include future measurement
    assert LocationContext.model_validate_json(result.model_dump_json()) == result


def test_exact_source_time_has_one_current_vertex() -> None:
    result = _context([[0., 0., 0.], [1., 10., 0.], [2., 20., 0.]])
    assert [p.session_time_seconds for p in result.segments[0]] == [0, 1, 2]
    assert all(point.quality == "measured" for point in result.segments[0])
    assert result.heading_radians == 0


def test_window_is_bounded_and_repeated_seek_is_independent_of_call_order() -> None:
    rows = [[float(i), float(i * 10), 0.] for i in range(30)]
    first = _context(rows, time=20, x=200)
    _context(rows, time=3, x=30)
    second = _context(rows, time=20, x=200)
    assert first == second
    assert [p.session_time_seconds for p in first.segments[0]] == list(range(8, 21))
    assert first.window_seconds == 12


@pytest.mark.parametrize("rows", [
    [[0., 0., 0.], [2., 20., 0.]],  # absent temporal coverage
    [[1., 0., 0.], [2., 3000., 0.]],  # implausible coordinate discontinuity
])
def test_trail_does_not_bridge_dropouts_or_coordinate_jumps(rows: list[list[float]]) -> None:
    result = _context(rows, x=rows[-1][1])
    assert len(result.segments) == 2
    assert all(len(segment) == 1 for segment in result.segments)
    assert result.heading_radians is None
    assert result.heading_quality is None


def test_a_later_valid_movement_pair_can_resume_heading_after_a_gap() -> None:
    result = _context([[0., 0., 0.], [3., 30., 0.], [4., 40., 0.]], time=4., x=40.)
    assert [len(segment) for segment in result.segments] == [1, 2]
    assert result.heading_radians == 0


def test_stationary_or_missing_current_point_has_no_heading() -> None:
    stationary = _context([[1., 20., 0.], [2., 20., 0.]])
    assert stationary.location_available
    assert stationary.heading_radians is None
    missing = _context([[0., 0., 0.], [1., 10., 0.]], x=None, y=None, quality=None)
    assert not missing.location_available
    assert [p.session_time_seconds for p in missing.segments[0]] == [0., 1.]
    assert missing.heading_radians is None
    isolated = _context([])
    assert isolated.location_available
    assert len(isolated.segments[0]) == 1
    assert isolated.heading_radians is None


def test_contract_rejects_future_points_estimated_past_and_bridged_gaps() -> None:
    result = _context([[0., 0., 0.], [1., 10., 0.], [2., 20., 0.]])
    for field, value, match in [("session_time_seconds", 3., "outside canonical"),
                                ("quality", "estimated", "Only canonical")]:
        payload = result.model_dump(mode="json")
        payload["heading_radians"] = payload["heading_quality"] = None
        payload["segments"][0][0][field] = value
        with pytest.raises(ValidationError, match=match):
            LocationContext.model_validate(payload)
    payload = result.model_dump(mode="json")
    payload["segments"][0][1]["track_x"] = 10_000.
    with pytest.raises(ValidationError, match="bridges a dropout"):
        LocationContext.model_validate(payload)


def test_context_rejects_invalid_clock_and_inconsistent_index() -> None:
    with pytest.raises(ValueError, match="finite and nonnegative"):
        _context([], time=math.nan)
    with pytest.raises(ValueError, match="index must match"):
        build_location_context([[0., 0., 0.]], driver_id="1", session_time_seconds=0.,
            track_x=0., track_y=0., location_quality="measured", source_times=[])
