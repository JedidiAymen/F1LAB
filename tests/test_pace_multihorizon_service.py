import hashlib
import json

import pytest

from f1_racelab.ml.pace.multihorizon_service import load


def test_study_checksums_and_horizon_contract(tmp_path):
    summary = json.dumps({'horizons': {'1': {}, '3': {}, '5': {}}, 'population': {'1': {}, '3': {}, '5': {}}}).encode()
    (tmp_path / 'summary.json').write_bytes(summary)
    manifest = json.dumps({'summary_sha256': hashlib.sha256(summary).hexdigest(), 'pace_sha256': 'source',
                           'source_revision': 'revision'}).encode()
    (tmp_path / 'manifest.json').write_bytes(manifest)
    expected = hashlib.sha256(manifest).hexdigest()
    assert load(tmp_path, expected)['source_sha256'] == 'source'
    (tmp_path / 'summary.json').write_bytes(b'{}')
    with pytest.raises(ValueError, match='summary checksum'):
        load(tmp_path, expected)
    with pytest.raises(ValueError, match='manifest checksum'):
        load(tmp_path, 'incorrect')


def test_bundled_study_api_is_read_only_and_reports_missing_data(monkeypatch):
    from fastapi.testclient import TestClient

    from f1_racelab.api import create_app
    from f1_racelab.ml.pace import multihorizon_service

    client = TestClient(create_app())
    response = client.get('/api/v1/research/pace-multihorizon')
    assert response.status_code == 200
    assert set(response.json()['summary']['horizons']) == {'1', '3', '5'}
    assert client.post('/api/v1/research/pace-multihorizon').status_code == 405
    def unavailable():
        raise FileNotFoundError('missing local evidence')
    monkeypatch.setattr(multihorizon_service, 'load', unavailable)
    assert client.get('/api/v1/research/pace-multihorizon').status_code == 503
