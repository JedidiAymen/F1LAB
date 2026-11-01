"""Exercise the actual corrected paired evidence and failure-closed API."""
from __future__ import annotations

import hashlib
import json
import shutil

import pytest
from fastapi.testclient import TestClient

from f1_racelab.agents.forecast_debug.service import CORRECTED_RUN, load_corrected
from f1_racelab.api import create_app


def test_corrected_results_are_paired_and_partial_review_is_explicit():
    report = load_corrected()
    assert report['summary']['arms']['baseline']['accuracy'] == .375
    assert report['summary']['arms']['candidate']['false_no_discrepancy'] == 10
    assert report['summary']['family_bootstrap_95'] == [-.375, .375]
    assert len(report['cases']) == 32
    assert sum(case['support'] is not None for case in report['cases']) == 6
    assert all('thought' not in step for case in report['cases'] for step in case['trace'])
    case = next(x for x in report['cases'] if x['arm'] == 'candidate' and x['scenario_id'] == 'feature_skew-s1')
    observation = json.loads(next(step['observation'] for step in case['trace'] if step['tool_id'] == 't1'))
    assert observation['feature_comparison']['mismatched_values_on_matched']['tyre_age'] == 4320
    assert case['support']['verdict'] == 'contradicted'


def test_corrected_api_rejects_corruption_and_missing_evidence(tmp_path):
    path = tmp_path / 'study'
    shutil.copytree(CORRECTED_RUN, path)
    client = TestClient(create_app(agent_corrected_path=path))
    assert client.get('/api/v1/research/agent-corrected').status_code == 200
    assert client.post('/api/v1/research/agent-corrected').status_code == 405
    (path / 'results.json').write_text('{}')
    assert client.get('/api/v1/research/agent-corrected').status_code == 503
    (path / 'results.sha256').write_text(hashlib.sha256(b'{}').hexdigest())
    with pytest.raises((KeyError, ValueError)):
        load_corrected(path)
