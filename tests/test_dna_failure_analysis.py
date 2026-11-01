import importlib.util
import json
import shutil
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from f1_racelab.api import create_app
from f1_racelab.ml.driver_dna import future_service

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


def test_failure_report_links_to_exact_study_and_rejects_tampering(tmp_path):
    root = tmp_path / 'failures'
    study = tmp_path / 'study'
    shutil.copytree(future_service.FAILURES, root)
    shutil.copytree(future_service.BUNDLED, study)
    result = future_service.failure_analysis(root, study)
    assert result['total_test']['rows'] == 1597
    assert result['slices']['retrospective_lap_change'][0]['rows'] == 1097
    (study / 'study.json').write_text('{}')
    with pytest.raises(ValueError, match='source study mismatch'):
        future_service.failure_analysis(root, study)
    shutil.copyfile(future_service.BUNDLED / 'study.json', study / 'study.json')
    payload = json.loads((root / 'report.json').read_text())
    payload['total_test']['rows'] = 1
    (root / 'report.json').write_text(json.dumps(payload))
    with pytest.raises(ValueError, match='checksum'):
        future_service.failure_analysis(root, study)


def test_failure_analysis_api_returns_bundled_research_evidence():
    response = TestClient(create_app()).get('/api/v1/driver-dna/future-failures')
    assert response.status_code == 200
    assert response.json()['status'] == 'exploratory; previously inspected events'
