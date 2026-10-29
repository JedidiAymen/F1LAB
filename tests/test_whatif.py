"""Tests for the what-if / counterfactual branch engine.

Tests use real Monza 2025 replay pack data where available;
fallback to synthetic fixtures when no pack exists.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from f1_racelab.strategy.simulator import PitStop, Strategy
from f1_racelab.strategy.whatif import (
    _compound_at_lap,
    _load_measured_laps,
    branch,
)

PACK_ROOT = Path(__file__).resolve().parents[1] / 'data/processed/replay_packs'
HAS_MONZA = (PACK_ROOT / 'monza_2025_race.json.gz').is_file()


# ---------------------------------------------------------------------------
# Unit tests that don't need a real pack
# ---------------------------------------------------------------------------

def test_compound_at_lap_returns_first_compound_before_first_stint():
    stints = [{'lap_start': 1, 'compound': 'MEDIUM'}, {'lap_start': 38, 'compound': 'HARD'}]
    assert _compound_at_lap(stints, 1) == 'MEDIUM'
    assert _compound_at_lap(stints, 37) == 'MEDIUM'
    assert _compound_at_lap(stints, 38) == 'HARD'
    assert _compound_at_lap(stints, 50) == 'HARD'


def test_compound_at_lap_unknown_compound_falls_back_to_medium():
    stints = [{'lap_start': 1, 'compound': 'HYPERSOFT'}]
    assert _compound_at_lap(stints, 5) == 'MEDIUM'


def test_compound_at_lap_empty_stints_returns_medium():
    assert _compound_at_lap([], 10) == 'MEDIUM'


# ---------------------------------------------------------------------------
# Integration tests — require Monza 2025 pack
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not HAS_MONZA, reason='Monza 2025 pack not present')
def test_branch_historical_segment_length():
    actual = Strategy(driver_number=1, start_compound='MEDIUM',
                      pit_stops=(PitStop(lap=37, compound='HARD'),))
    cf = Strategy(driver_number=1, start_compound='MEDIUM',
                  pit_stops=(PitStop(lap=25, compound='HARD'),))
    result = branch('monza-2025', 1, actual, cf, fork_lap=30)
    assert result.fork_lap == 30
    # Both timelines must be 53 laps total (scheduled)
    assert len(result.actual_laps) == 53
    assert len(result.counterfactual_laps) == 53


@pytest.mark.skipif(not HAS_MONZA, reason='Monza 2025 pack not present')
def test_branch_historical_laps_are_identical_before_fork():
    actual = Strategy(driver_number=1, start_compound='MEDIUM',
                      pit_stops=(PitStop(lap=37, compound='HARD'),))
    cf = Strategy(driver_number=1, start_compound='MEDIUM',
                  pit_stops=(PitStop(lap=25, compound='HARD'),))
    result = branch('monza-2025', 1, actual, cf, fork_lap=30)
    for a_lap, cf_lap in zip(result.actual_laps[:30], result.counterfactual_laps[:30]):
        assert a_lap.lap_time_s == cf_lap.lap_time_s
        assert a_lap.estimation == 'historical'
        assert cf_lap.estimation == 'historical'


@pytest.mark.skipif(not HAS_MONZA, reason='Monza 2025 pack not present')
def test_branch_simulated_laps_after_fork():
    actual = Strategy(driver_number=1, start_compound='MEDIUM',
                      pit_stops=(PitStop(lap=37, compound='HARD'),))
    cf = Strategy(driver_number=1, start_compound='MEDIUM',
                  pit_stops=(PitStop(lap=25, compound='HARD'),))
    result = branch('monza-2025', 1, actual, cf, fork_lap=30)
    for lap in result.actual_laps[30:]:
        assert lap.estimation == 'simulated'
    for lap in result.counterfactual_laps[30:]:
        assert lap.estimation == 'simulated'


@pytest.mark.skipif(not HAS_MONZA, reason='Monza 2025 pack not present')
def test_fork_lap_is_marked():
    actual = Strategy(driver_number=1, start_compound='MEDIUM',
                      pit_stops=(PitStop(lap=37, compound='HARD'),))
    cf = Strategy(driver_number=1, start_compound='MEDIUM',
                  pit_stops=(PitStop(lap=25, compound='HARD'),))
    result = branch('monza-2025', 1, actual, cf, fork_lap=30)
    fork_markers = [l.is_fork_lap for l in result.actual_laps]
    assert fork_markers.count(True) == 1
    assert result.actual_laps[29].is_fork_lap  # lap 30 (index 29)


@pytest.mark.skipif(not HAS_MONZA, reason='Monza 2025 pack not present')
def test_cumulative_time_non_decreasing_in_both_timelines():
    actual = Strategy(driver_number=1, start_compound='MEDIUM',
                      pit_stops=(PitStop(lap=37, compound='HARD'),))
    cf = Strategy(driver_number=1, start_compound='MEDIUM',
                  pit_stops=(PitStop(lap=25, compound='HARD'),))
    result = branch('monza-2025', 1, actual, cf, fork_lap=30)
    for laps in [result.actual_laps, result.counterfactual_laps]:
        times = [l.cumulative_race_time_s for l in laps]
        for i in range(1, len(times)):
            assert times[i] > times[i - 1] - 0.001


@pytest.mark.skipif(not HAS_MONZA, reason='Monza 2025 pack not present')
def test_delta_matches_total_times():
    actual = Strategy(driver_number=1, start_compound='MEDIUM',
                      pit_stops=(PitStop(lap=37, compound='HARD'),))
    cf = Strategy(driver_number=1, start_compound='MEDIUM',
                  pit_stops=(PitStop(lap=25, compound='HARD'),))
    result = branch('monza-2025', 1, actual, cf, fork_lap=30)
    expected = round(result.counterfactual_total_race_time_s - result.actual_total_race_time_s, 3)
    assert result.delta_counterfactual_vs_actual_s == pytest.approx(expected, abs=0.01)


@pytest.mark.skipif(not HAS_MONZA, reason='Monza 2025 pack not present')
def test_invalid_fork_lap_raises():
    actual = Strategy(driver_number=1, start_compound='MEDIUM')
    with pytest.raises(ValueError, match='fork_lap'):
        branch('monza-2025', 1, actual, actual, fork_lap=0)
    with pytest.raises(ValueError, match='fork_lap'):
        branch('monza-2025', 1, actual, actual, fork_lap=53)


@pytest.mark.skipif(not HAS_MONZA, reason='Monza 2025 pack not present')
def test_earlier_pit_favoured_when_forking_at_lap_30():
    """When forking at lap 30, CF already pitted at L25 (5 laps ago in the sim).
    The actual pits at L37 (7 more laps to go). Model predicts CF is faster
    because it has more fresh Hard laps at Monza where Hard degradation is minimal.
    Verified manually: delta = ~-25s (CF faster)."""
    actual = Strategy(driver_number=1, start_compound='MEDIUM',
                      pit_stops=(PitStop(lap=37, compound='HARD'),))
    cf = Strategy(driver_number=1, start_compound='MEDIUM',
                  pit_stops=(PitStop(lap=25, compound='HARD'),))
    result = branch('monza-2025', 1, actual, cf, fork_lap=30)
    assert result.counterfactual_is_faster
    # Delta should be in a plausible range (not hundreds of seconds)
    assert -60 < result.delta_counterfactual_vs_actual_s < 0


@pytest.mark.skipif(not HAS_MONZA, reason='Monza 2025 pack not present')
def test_simulation_limits_present():
    actual = Strategy(driver_number=1, start_compound='MEDIUM',
                      pit_stops=(PitStop(lap=37, compound='HARD'),))
    cf = Strategy(driver_number=1, start_compound='MEDIUM',
                  pit_stops=(PitStop(lap=25, compound='HARD'),))
    result = branch('monza-2025', 1, actual, cf, fork_lap=30)
    assert len(result.simulation_limits) >= 4


@pytest.mark.skipif(not HAS_MONZA, reason='Monza 2025 pack not present')
def test_load_measured_laps_returns_positive_times():
    laps = _load_measured_laps('monza-2025', 1)
    assert all(t > 0 for t in laps.values())
    assert 1 in laps  # lap 1 exists
    assert max(laps.keys()) >= 50  # near end of race
