"""HTTP selection semantics use local validated library artifacts only."""
import pytest
from fastapi.testclient import TestClient
from test_telemetry_library import source_fixture

from f1_racelab.api import create_app
from f1_racelab.telemetry.lap_library import build_library


@pytest.fixture
def library_client(tmp_path):
    cache, root = tmp_path / 'cache', tmp_path / 'library'
    source_fixture(cache)
    library = build_library('monza-2025', cache_root=cache, output_root=root)
    app = create_app(telemetry_library_roots={'monza-2025': root})
    return TestClient(app), root, library


def test_library_catalog_and_same_driver_selection_preserve_replay_contract(library_client):
    client, _, _ = library_client
    catalog = client.get('/api/v1/replay/monza-2025/telemetry/laps')
    assert catalog.status_code == 200
    assert len(catalog.json()['drivers']) == 3
    response = client.get('/api/v1/replay/monza-2025/telemetry/lap-comparison', params={
        'driver_a': 1, 'lap_a': 50, 'driver_b': 1, 'lap_b': 51})
    assert response.status_code == 200
    data = response.json()
    assert (data['lap_a']['driver_number'], data['lap_b']['lap_number']) == (1, 51)
    assert 'points' not in data['lap_a']
    assert len(data['samples']) > 10


@pytest.mark.parametrize('params,status', [
    ({'driver_a': 1}, 422),
    ({'driver_a': 1, 'lap_a': 50, 'driver_b': 1, 'lap_b': 50}, 422),
    ({'driver_a': 1, 'lap_a': 50, 'driver_b': 44, 'lap_b': 50}, 404),
    ({'driver_a': 1, 'lap_a': 52, 'driver_b': 4, 'lap_b': 50}, 404),
    ({'driver_a': -1, 'lap_a': 50, 'driver_b': 4, 'lap_b': 50}, 422),
])
def test_invalid_and_unavailable_selections_never_fall_back(library_client, params, status):
    client, _, _ = library_client
    assert client.get('/api/v1/replay/monza-2025/telemetry/lap-comparison', params=params).status_code == status


def test_missing_and_corrupt_artifacts_return_service_unavailable(library_client):
    client, root, library = library_client
    params = {'driver_a': 1, 'lap_a': 50, 'driver_b': 4, 'lap_b': 50}
    path = root / library.drivers[0].laps[0].filename
    path.write_bytes(b'corrupt')
    response = client.get('/api/v1/replay/monza-2025/telemetry/lap-comparison', params=params)
    assert response.status_code == 503
    assert 'checksum' in response.json()['detail']
    (root / 'manifest.json').unlink()
    assert client.get('/api/v1/replay/monza-2025/telemetry/laps').status_code == 503
    assert client.get('/api/v1/replay/unknown/telemetry/laps').status_code == 404
