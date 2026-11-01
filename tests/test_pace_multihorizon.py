import numpy as np
import pandas as pd
import pytest

from f1_racelab.ml.pace.multihorizon import last_observed_delta, make_population


def frame():
    return pd.DataFrame([{'race_id': 'r', 'driver_number': 1, 'lap': lap, 'cutoff': f'2025-01-01T12:{lap:02d}:00Z',
                          'neutral_in_last3': 0, 'yellow_in_last1': 0, 'regime_next': 'green',
                          'next_is_in_lap': False, 'next_is_out_lap': False, 'eligible_green_next': True,
                          'compound_next': 'MEDIUM' if lap < 4 else 'HARD', 'stint_number_next': 1,
                          'tyre_age_next': lap + 1, 'anchor_seconds': 90., 'next_lap_seconds': 90. + lap}
                         for lap in range(1, 9)])


def test_exact_target_horizons_keep_decision_time_inputs():
    source = frame()
    result, counts = make_population(source, 3)
    row = result.set_index('lap').loc[3]
    assert row.target_seconds == 95  # lap 6 time, stored at source row 5
    assert row.anchor_seconds == 91.5  # recorded laps 2 and 3
    assert counts['decision_rows'] == 6 and counts['missing_target'] == 2
    altered = source.copy()
    altered.loc[altered.lap >= 3, 'next_lap_seconds'] += 1000
    assert make_population(altered, 3)[0].set_index('lap').loc[3, 'anchor_seconds'] == row.anchor_seconds


def test_censor_intermediate_gaps_and_reject_duplicate_or_missing_cutoff():
    source = frame().query('lap != 4')
    result, counts = make_population(source, 3)
    assert 3 not in result.lap.tolist()
    assert counts['target_present_missing_intermediate'] > 0
    with pytest.raises(ValueError, match='duplicate'):
        make_population(pd.concat([source, source.iloc[[0]]]), 1)
    source.loc[source.lap == 2, 'cutoff'] = np.nan
    with pytest.raises(ValueError, match='cutoff'):
        make_population(source, 1)


def test_last_observed_baseline_uses_recent_history_or_anchor():
    data = pd.DataFrame({'last1': [1., np.nan, np.nan, np.nan], 'last2': [2., 2., np.nan, np.nan],
                         'last3': [3., 3., 3., np.nan]})
    assert last_observed_delta(data).tolist() == [1., 2., 3., 0.]


def test_nonmonotonic_cutoffs_fail_closed():
    source = frame()
    source.loc[source.lap == 4, 'cutoff'] = '2025-01-01T12:01:00Z'
    with pytest.raises(ValueError, match='Nonmonotonic'):
        make_population(source, 3)


def test_model_features_exclude_retrospective_fields_and_future_outcomes():
    from f1_racelab.ml.pace.multihorizon import CATEGORICAL, NUMERIC

    forbidden = {'laps_remaining', 'laps_in_stint', 'stint_best_delta', 'tyre_age_next', 'compound_next',
                 'stint_number_next', 'neutral_in_last3', 'yellow_in_last1', 'laps_since_neutral',
                 'next_is_in_lap', 'next_is_out_lap', 'eligible_green_next', 'target_seconds', 'target_outcome'}
    assert not (set(NUMERIC) | set(CATEGORICAL)) & forbidden
