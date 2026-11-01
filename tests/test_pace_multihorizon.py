import numpy as np
import pandas as pd
import pytest

from f1_racelab.ml.pace.multihorizon import last_clean_delta, make_population


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
    row = result.set_index('lap').loc[2]
    assert row.target_seconds == 94  # lap 5 time, stored at decision row 4
    assert row.compound_next == 'MEDIUM'  # from lap 1, not a future tyre
    assert counts['decision_rows'] == 7 and counts['missing_target'] == 2
    altered = source.copy()
    altered.loc[altered.lap == 4, 'compound_next'] = 'WET'
    assert make_population(altered, 3)[0].set_index('lap').loc[2, 'compound_next'] == 'MEDIUM'


def test_censor_intermediate_gaps_and_reject_duplicate_or_missing_cutoff():
    source = frame().query('lap != 4')
    result, counts = make_population(source, 3)
    assert 2 not in result.lap.tolist()
    assert counts['target_present_missing_intermediate'] > 0
    with pytest.raises(ValueError, match='duplicate'):
        make_population(pd.concat([source, source.iloc[[0]]]), 1)
    source.loc[source.lap == 2, 'cutoff'] = np.nan
    with pytest.raises(ValueError, match='cutoff'):
        make_population(source, 1)


def test_last_clean_baseline_uses_recent_history_or_anchor():
    data = pd.DataFrame({'last1': [1., np.nan, np.nan, np.nan], 'last2': [2., 2., np.nan, np.nan],
                         'last3': [3., 3., 3., np.nan]})
    assert last_clean_delta(data).tolist() == [1., 2., 3., 0.]
