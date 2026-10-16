"""Synthetic driving lines prove geometry contracts, not real circuit accuracy."""

import math
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from f1_racelab.session.geometry import CircuitGeometry, build_circuit_geometry

ORIGIN = datetime(2025, 1, 1, tzinfo=UTC)


def _points() -> list[list[float]]:
    return [[i / 2, 1000 * math.cos(i * 2 * math.pi / 120),
             1000 * math.sin(i * 2 * math.pi / 120)] for i in range(120)]


def _lap(driver: int = 1) -> dict:
    return {"driver_number": driver, "lap_number": 2,
            "date_start": ORIGIN.isoformat(), "lap_duration": 60.0,
            "is_pit_out_lap": False}


def _build(points: list[list[float]] | None = None) -> CircuitGeometry:
    return build_circuit_geometry({"1": _points() if points is None else points}, [_lap()],
        clock_origin=ORIGIN, session_key=123, layout_id="synthetic-circle")


def test_geometry_preserves_measured_line_and_unknown_physical_quantities() -> None:
    geometry = _build()
    assert geometry.centerline_xy[:-1] == [tuple(point[1:]) for point in _points()]
    assert geometry.centerline_xy[-1] == geometry.centerline_xy[0]
    assert geometry.provenance.closure == "first_point_appended"
    assert geometry.provenance.source_shape == "measured_driving_line"
    assert geometry.quality == "estimated"
    assert geometry.lap_length_meters is None
    assert geometry.width_meters is None
    assert geometry.pit_lane_xy is None
    assert geometry.corners == geometry.sectors == []
    assert geometry.diagnostics.retained_source_points == 120
    assert geometry.diagnostics.inferred_closure_length_provider_units > 0
    assert geometry.start_line.basis == "first retained point of timed source lap"
    assert geometry.cumulative_distance_provider_units[-1] == geometry.lap_length_provider_units
    assert 6200 < geometry.lap_length_provider_units < 6300
    for (x, y), (nx, ny) in zip(geometry.centerline_xy, geometry.normalized_centerline_xy,
                               strict=True):
        assert math.isclose(x, nx / geometry.transform.scale + geometry.transform.origin_x,
                            abs_tol=1e-9)
        assert math.isclose(y, ny / geometry.transform.scale + geometry.transform.origin_y,
                            abs_tol=1e-9)
    assert max(abs(value) for point in geometry.normalized_centerline_xy for value in point) <= .5
    assert CircuitGeometry.model_validate_json(geometry.model_dump_json()) == geometry


def test_selection_is_order_independent_and_excludes_pit_laps() -> None:
    locations = {str(driver): _points() for driver in (1, 4, 16)}
    pit_out = {**_lap(1), "is_pit_out_lap": True}
    laps = [pit_out, _lap(16), _lap(4)]
    kwargs = {"clock_origin": ORIGIN, "session_key": 123, "layout_id": "synthetic-circle"}
    first = build_circuit_geometry(locations, laps, **kwargs)
    second = build_circuit_geometry(dict(reversed(list(locations.items()))), list(reversed(laps)),
                                    **kwargs)
    assert first == second
    assert first.provenance.driver_id == "4"
    assert first.diagnostics.rejected_laps_by_reason == {"pit_lap": 1}
    assert first.diagnostics.candidate_laps == 3
    assert first.diagnostics.accepted_laps == 2
    excluded = build_circuit_geometry(locations, laps,
        pit_stops=[{"driver_number": 4, "lap_number": 2}], **kwargs)
    assert excluded.provenance.driver_id == "16"
    assert excluded.diagnostics.rejected_laps_by_reason == {"pit_lap": 2}


@pytest.mark.parametrize(("kind", "reason"), [
    ("sparse", "too_few_points"), ("gap", "sample_gap"),
    ("boundary", "boundary_gap"), ("open", "open_trace"),
    ("jump", "coordinate_jump"), ("stationary", "zero_length"),
])
def test_incomplete_or_corrupt_trace_is_rejected_instead_of_force_closed(kind: str,
                                                                        reason: str) -> None:
    points = _points()
    if kind == "sparse":
        points = points[:90]
    elif kind == "gap":
        del points[30:40]
    elif kind == "boundary":
        points = points[4:]
    elif kind == "open":
        points = [[i / 2, float(i), 0.] for i in range(120)]
    elif kind == "jump":
        points[30][1] = 100_000
    else:
        points = [[i / 2, 10., 20.] for i in range(120)]
    with pytest.raises(ValueError, match=reason):
        _build(points)


@pytest.mark.parametrize("kind", ["nan", "duplicate_time", "reversed_time"])
def test_bad_source_arrays_fail_before_time_indexing(kind: str) -> None:
    points = _points()
    if kind == "nan":
        points[10][1] = math.nan
    elif kind == "duplicate_time":
        points[10][0] = points[9][0]
    else:
        points.reverse()
    with pytest.raises(ValueError, match="Invalid geometry|timestamps must increase"):
        _build(points)


def test_geometry_contract_rejects_corrupted_parallel_arrays_or_coordinate_transform() -> None:
    data = _build().model_dump(mode="json")
    data["heading_radians"].pop()
    with pytest.raises(ValidationError, match="equal lengths"):
        CircuitGeometry.model_validate(data)
    data = _build().model_dump(mode="json")
    data["cumulative_distance_provider_units"][10] += 1
    with pytest.raises(ValidationError, match="Arc distance"):
        CircuitGeometry.model_validate(data)
    data = _build().model_dump(mode="json")
    data["normalized_centerline_xy"][10][0] += .001
    with pytest.raises(ValidationError, match="transform disagree"):
        CircuitGeometry.model_validate(data)


def test_geometry_identity_changes_when_measurements_or_layout_change() -> None:
    first = _build()
    points = _points()
    points[10][1] += 1
    changed = _build(points)
    assert first.geometry_id != changed.geometry_id
    assert first.provenance.source_samples_sha256 != changed.provenance.source_samples_sha256
    assert first.provenance.source_lap_sha256 == changed.provenance.source_lap_sha256
    other_layout = build_circuit_geometry({"1": _points()}, [_lap()], clock_origin=ORIGIN,
                                          session_key=123, layout_id="other-layout")
    assert first.geometry_id != other_layout.geometry_id
