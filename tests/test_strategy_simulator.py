"""Tests for the strategy simulator.

Split into deterministic model tests, simulator contract tests,
optimizer contract tests, MC stability tests and real-data calibration tests.
All simulated results are labelled; no historical lap times are mixed in.
"""
from __future__ import annotations

import pytest

from f1_racelab.strategy.models import (
    CIRCUIT_COMPOUNDS,
    CIRCUIT_FUEL,
    CIRCUIT_PIT,
    RACE_SPECS,
    FuelModel,
    PitModel,
    RaceSpec,
    TyreCompoundModel,
)
from f1_racelab.strategy.simulator import (
    LapState,
    PitStop,
    Strategy,
    gap_history,
    race_time,
    simulate_race,
    undercut_window,
)
from f1_racelab.strategy.optimizer import (
    best_strategies,
    compare_strategies,
    enumerate_strategies,
    evaluate_strategy,
)
from f1_racelab.strategy.monte_carlo import mc_compare


# ---------------------------------------------------------------------------
# Model unit tests
# ---------------------------------------------------------------------------

def test_tyre_fresh_offset_increases_monotonically():
    model = TyreCompoundModel(compound='MEDIUM', lap_time_offset_s=0.0,
                               linear_s_per_lap=0.010, quadratic_s_per_lap2=0.0005,
                               warm_up_laps=1, warm_up_offset_s=0.3)
    # After warm-up (age >=2) degradation should be non-decreasing
    deltas = [model.degradation_delta(age) for age in range(2, 30)]
    for i in range(1, len(deltas)):
        assert deltas[i] >= deltas[i - 1] - 1e-9


def test_tyre_warm_up_only_on_first_lap():
    model = TyreCompoundModel(compound='SOFT', lap_time_offset_s=0.0,
                               linear_s_per_lap=0.0, warm_up_laps=1, warm_up_offset_s=0.5)
    assert model.degradation_delta(1) == pytest.approx(0.5)
    assert model.degradation_delta(2) == pytest.approx(0.0)


def test_fuel_model_decreases_lap_time():
    fuel = FuelModel(total_fuel_kg=100.0, burn_rate_kg_per_lap=2.0,
                     lap_time_sensitivity_s_per_kg=0.03)
    # Later laps should have lower (more negative) delta (car is lighter = faster)
    assert fuel.lap_time_delta(50) < fuel.lap_time_delta(10)
    # At lap 1, delta is 0 (reference)
    assert fuel.lap_time_delta(1) == pytest.approx(0.0)


def test_pit_model_total_loss():
    pit = PitModel(circuit_name='Test', entry_delta_s=14.0,
                   stationary_s=2.5, exit_delta_s=8.5)
    assert pit.total_pit_loss_s == pytest.approx(25.0)


# ---------------------------------------------------------------------------
# Simulator contract tests
# ---------------------------------------------------------------------------

def _simple_spec():
    return RaceSpec(circuit_name='Test', scheduled_laps=10, base_lap_time_s=80.0)


def _simple_fuel():
    return FuelModel(total_fuel_kg=30.0, burn_rate_kg_per_lap=3.0,
                     lap_time_sensitivity_s_per_kg=0.03)


def _simple_pit():
    return PitModel(circuit_name='Test', entry_delta_s=10.0,
                    stationary_s=3.0, exit_delta_s=7.0)


def _simple_compounds():
    return CIRCUIT_COMPOUNDS['monza-2025']


def test_lap_count_matches_scheduled_laps():
    spec = _simple_spec()
    strategy = Strategy(driver_number=1, start_compound='MEDIUM')
    results = simulate_race(spec=spec, strategies=[strategy],
                            compounds=_simple_compounds(),
                            fuel=_simple_fuel(), pit=_simple_pit())
    assert len(results[1]) == spec.scheduled_laps


def test_cumulative_time_is_non_decreasing():
    spec = _simple_spec()
    strategy = Strategy(driver_number=1, start_compound='MEDIUM',
                        pit_stops=(PitStop(lap=5, compound='HARD'),))
    results = simulate_race(spec=spec, strategies=[strategy],
                            compounds=_simple_compounds(),
                            fuel=_simple_fuel(), pit=_simple_pit())
    times = [lap.cumulative_race_time_s for lap in results[1]]
    for i in range(1, len(times)):
        assert times[i] > times[i - 1]


def test_pit_lap_has_correct_flag_and_extra_time():
    spec = _simple_spec()
    pit_lap = 5
    strategy = Strategy(driver_number=1, start_compound='MEDIUM',
                        pit_stops=(PitStop(lap=pit_lap, compound='HARD'),))
    results = simulate_race(spec=spec, strategies=[strategy],
                            compounds=_simple_compounds(),
                            fuel=_simple_fuel(), pit=_simple_pit())
    laps = results[1]
    assert laps[pit_lap - 1].pitted_this_lap
    assert laps[pit_lap - 1].pit_loss_s == pytest.approx(20.0)
    assert not laps[pit_lap].pitted_this_lap


def test_compound_changes_after_pit():
    spec = _simple_spec()
    strategy = Strategy(driver_number=1, start_compound='MEDIUM',
                        pit_stops=(PitStop(lap=5, compound='HARD'),))
    results = simulate_race(spec=spec, strategies=[strategy],
                            compounds=_simple_compounds(),
                            fuel=_simple_fuel(), pit=_simple_pit())
    laps = results[1]
    assert laps[3].compound == 'MEDIUM'
    assert laps[5].compound == 'HARD'  # lap 6 (index 5) uses Hard


def test_stint_lap_resets_to_one_after_pit():
    spec = _simple_spec()
    strategy = Strategy(driver_number=1, start_compound='MEDIUM',
                        pit_stops=(PitStop(lap=5, compound='HARD'),))
    results = simulate_race(spec=spec, strategies=[strategy],
                            compounds=_simple_compounds(),
                            fuel=_simple_fuel(), pit=_simple_pit())
    laps = results[1]
    assert laps[4].stint_lap == 5  # lap 5 = 5th on Medium
    assert laps[5].stint_lap == 1  # lap 6 = 1st on Hard


def test_simulation_is_deterministic():
    spec = _simple_spec()
    strategies = [Strategy(driver_number=1, start_compound='MEDIUM',
                           pit_stops=(PitStop(lap=5, compound='HARD'),))]
    r1 = simulate_race(spec=spec, strategies=strategies,
                       compounds=_simple_compounds(),
                       fuel=_simple_fuel(), pit=_simple_pit())
    r2 = simulate_race(spec=spec, strategies=strategies,
                       compounds=_simple_compounds(),
                       fuel=_simple_fuel(), pit=_simple_pit())
    for l1, l2 in zip(r1[1], r2[1]):
        assert l1 == l2


def test_all_laps_labelled_simulated():
    spec = _simple_spec()
    strategy = Strategy(driver_number=1, start_compound='MEDIUM')
    results = simulate_race(spec=spec, strategies=[strategy],
                            compounds=_simple_compounds(),
                            fuel=_simple_fuel(), pit=_simple_pit())
    assert all(lap.estimation == 'simulated' for lap in results[1])


def test_gap_history_length_and_sign():
    spec = _simple_spec()
    s1 = Strategy(driver_number=1, start_compound='MEDIUM')
    s2 = Strategy(driver_number=2, start_compound='SOFT')
    results = simulate_race(spec=spec, strategies=[s1, s2],
                            compounds=_simple_compounds(),
                            fuel=_simple_fuel(), pit=_simple_pit())
    gaps = gap_history(results[1], results[2])
    assert len(gaps) == spec.scheduled_laps
    # SOFT is generally faster, so driver 2 should be ahead (negative gap)
    assert gaps[-1] < 0


def test_undercut_window_identifies_feasible_gaps():
    spec = _simple_spec()
    pit = _simple_pit()
    s1 = Strategy(driver_number=1, start_compound='MEDIUM')
    s2 = Strategy(driver_number=2, start_compound='MEDIUM',
                  pit_stops=(PitStop(lap=7, compound='HARD'),))
    results = simulate_race(spec=spec, strategies=[s1, s2],
                            compounds=_simple_compounds(),
                            fuel=_simple_fuel(), pit=pit)
    windows = undercut_window(results[1], results[2], pit)
    feasible = [w for w in windows if w['undercut_feasible']]
    # Result is that some laps are within pit loss range
    for w in feasible:
        assert 0.0 < w['gap_s'] < pit.total_pit_loss_s


# ---------------------------------------------------------------------------
# Optimizer tests
# ---------------------------------------------------------------------------

def test_evaluate_strategy_returns_evaluation():
    strategy = Strategy(driver_number=1, start_compound='MEDIUM',
                        pit_stops=(PitStop(lap=30, compound='HARD'),))
    ev = evaluate_strategy('monza-2025', strategy)
    assert ev.driver_number == 1
    assert ev.stops == 1
    assert ev.total_race_time_s > 0


def test_compare_strategies_sorted_ascending():
    strategies = [
        Strategy(driver_number=1, start_compound='SOFT'),
        Strategy(driver_number=1, start_compound='HARD'),
        Strategy(driver_number=1, start_compound='MEDIUM'),
    ]
    results = compare_strategies('monza-2025', strategies)
    times = [r.total_race_time_s for r in results]
    assert times == sorted(times)
    assert results[0].delta_vs_reference_s == pytest.approx(0.0)


def test_enumerate_strategies_no_duplicates():
    candidates = enumerate_strategies('monza-2025', 1, ['SOFT', 'MEDIUM', 'HARD'],
                                      max_stops=1, pit_step=5)
    labels = [s.label for s in candidates]
    assert len(labels) == len(set(labels))


def test_best_strategies_top_n_limit():
    results = best_strategies('monza-2025', 1, ['SOFT', 'MEDIUM', 'HARD'],
                              max_stops=1, top_n=5, pit_step=5)
    assert len(results) <= 5


def test_best_strategies_labels_contain_simulation_limits():
    results = best_strategies('monza-2025', 1, ['MEDIUM', 'HARD'],
                              max_stops=1, top_n=3, pit_step=5)
    for r in results:
        assert len(r.simulation_limits) > 0


# ---------------------------------------------------------------------------
# Monte Carlo tests
# ---------------------------------------------------------------------------

def test_mc_compare_returns_same_count_as_strategies():
    strategies = [
        Strategy(driver_number=1, start_compound='MEDIUM',
                 pit_stops=(PitStop(lap=30, compound='HARD'),)),
        Strategy(driver_number=1, start_compound='MEDIUM',
                 pit_stops=(PitStop(lap=25, compound='HARD'),)),
    ]
    results = mc_compare('monza-2025', strategies, n_worlds=50, seed=99)
    assert len(results) == 2


def test_mc_seeded_results_are_stable():
    strategies = [
        Strategy(driver_number=1, start_compound='MEDIUM',
                 pit_stops=(PitStop(lap=30, compound='HARD'),)),
    ]
    r1 = mc_compare('monza-2025', strategies, n_worlds=20, seed=42)
    r2 = mc_compare('monza-2025', strategies, n_worlds=20, seed=42)
    assert r1[0].mean_race_time_s == r2[0].mean_race_time_s
    assert r1[0].std_race_time_s == r2[0].std_race_time_s


def test_mc_win_fraction_sums_to_one():
    strategies = [
        Strategy(driver_number=1, start_compound='MEDIUM',
                 pit_stops=(PitStop(lap=28, compound='HARD'),)),
        Strategy(driver_number=1, start_compound='MEDIUM',
                 pit_stops=(PitStop(lap=35, compound='HARD'),)),
        Strategy(driver_number=1, start_compound='SOFT',
                 pit_stops=(PitStop(lap=25, compound='HARD'),)),
    ]
    results = mc_compare('monza-2025', strategies, n_worlds=50, seed=7)
    total_wins = sum(r.win_fraction for r in results)
    assert abs(total_wins - 1.0) < 0.05  # rounding tolerance


def test_mc_limits_included():
    strategies = [Strategy(driver_number=1, start_compound='MEDIUM',
                           pit_stops=(PitStop(lap=30, compound='HARD'),))]
    results = mc_compare('monza-2025', strategies, n_worlds=10, seed=0)
    assert len(results[0].simulation_limits) >= 2


# ---------------------------------------------------------------------------
# Real-data sanity check (P5 acceptance gate)
# ---------------------------------------------------------------------------

def test_real_data_calibration_monza():
    """Verify calibration against real Monza 2025 lap data."""
    from f1_racelab.strategy.calibration import sanity_check_monza
    result = sanity_check_monza()
    assert result['session_slug'] == 'monza-2025'
    # Calibrated base lap time should be within 1 s of the model value
    assert abs(result['base_lap_time_delta_s']) < 1.0
    # At least 10 clean laps for regression
    assert result['medium_degradation']['stint_laps'] >= 10
    assert result['hard_degradation']['stint_laps'] >= 5
    # Degradation slope should be small and positive (faster at Monza)
    med_slope = result['medium_degradation']['linear_s_per_lap']
    assert -0.05 < med_slope < 0.05
    hard_slope = result['hard_degradation']['linear_s_per_lap']
    assert -0.05 < hard_slope < 0.05
    # R^2 should be reasonable for a linear fit (noise included)
    assert result['medium_degradation']['r2'] > 0.0


def test_real_monza_strategy_a_vs_b():
    """Simulate VER's actual strategy vs an alternative and check race time is positive."""
    actual = Strategy(driver_number=1, start_compound='MEDIUM',
                      pit_stops=(PitStop(lap=37, compound='HARD'),))
    alternative = Strategy(driver_number=1, start_compound='MEDIUM',
                           pit_stops=(PitStop(lap=25, compound='HARD'),))
    results = compare_strategies('monza-2025', [actual, alternative])
    assert results[0].total_race_time_s > 3000  # 53 laps × ~82 s ≈ 4346 s
    assert results[0].total_race_time_s < 5000
    # Both strategies produce valid labels
    assert 'M' in results[0].label or 'S' in results[0].label or 'H' in results[0].label
