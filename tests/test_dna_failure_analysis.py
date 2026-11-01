import importlib.util
from pathlib import Path

import pandas as pd
import pytest

spec = importlib.util.spec_from_file_location('dna_failure_analysis', Path(__file__).parents[1] / 'scripts/analyze_dna_future_errors.py')
assert spec and spec.loader
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


def test_paired_error_difference_and_event_driver_bootstrap():
    frame = pd.DataFrame({'session_key': [1, 1, 2], 'driver_number': [1, 2, 1],
        'remaining_seconds': [10., 10., 10.], 'last_completed_lap': [12., 10., 8.],
        'tcn_seed7': [11., 11., 9.], 'tcn_no_context_seed42': [12., 10., 8.],
        'tcn_masked_seed42': [10., 10., 10.]})
    result = analysis.summarize(frame)
    assert result['clusters'] == 3
    assert result['models']['last_completed_lap']['mae_s'] == pytest.approx(4 / 3)
    assert result['models']['tcn_seed7']['paired_mae_delta_s'] == pytest.approx(-1 / 3)
    assert result['models']['last_completed_lap']['conditional_cluster_bootstrap_95_s'] == [0, 0]
    assert result['models']['tcn_masked_seed42']['mae_s'] == 0


def test_empty_slice_has_no_invented_metrics():
    frame = pd.DataFrame({'session_key': pd.Series(dtype=int), 'driver_number': pd.Series(dtype=int)})
    assert analysis.summarize(frame) == {'rows': 0, 'clusters': 0, 'models': {}}
