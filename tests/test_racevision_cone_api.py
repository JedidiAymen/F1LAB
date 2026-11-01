"""Synthetic local artifacts test the read-only gallery and integrity boundaries."""
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from f1_racelab.api import create_app


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def artifacts(tmp_path):
    dataset, run = tmp_path / 'data', tmp_path / 'run'
    dataset.mkdir()
    run.mkdir()
    image = dataset / 'frame.png'
    image.write_bytes(b'synthetic image bytes')
    annotation = dataset / 'frame.json'
    annotation.write_text(json.dumps({'size': {'width': 20, 'height': 10}, 'objects': [
        {'geometryType': 'rectangle', 'classTitle': 'blue_cone', 'points': {'exterior': [[1, 2], [5, 8]]}},
    ]}))
    manifest = dataset / 'manifest.json'
    manifest.write_text(json.dumps({'records': [{'split': 'test', 'filename_prefix': 'synthetic',
        'image': {'path': image.name, 'sha256': sha(image)},
        'annotation': {'path': annotation.name, 'sha256': sha(annotation)}}]}))
    model = run / 'detector.pth'
    model.write_bytes(b'synthetic weights; never loaded')
    predictions = run / 'test_predictions.json'
    predictions.write_text(json.dumps({'baseline': [], 'fine_tuned': [
        {'image_id': 1, 'bbox': [1, 2, 4, 6], 'score': 0.8},
    ]}))
    metrics = run / 'metrics.json'
    metrics.write_text(json.dumps({'dataset_manifest_sha256': sha(manifest), 'model_sha256': sha(model),
        'test_predictions_sha256': sha(predictions), 'fine_tuned': {'images': 1}}))
    return dataset, run


def test_cone_gallery_serves_only_hashed_local_artifacts(artifacts):
    dataset, run = artifacts
    client = TestClient(create_app(racevision_dataset_path=dataset, racevision_run_path=run))
    assert client.get('/api/v1/research/racevision/cones').json()['frame_count'] == 1
    result = client.get('/api/v1/research/racevision/cones/1').json()
    assert result['ground_truth'][0]['bbox'] == [1, 2, 4, 6]
    assert result['predictions']['fine_tuned'][0]['score'] == 0.8
    assert client.get('/api/v1/research/racevision/cones/1/image').content == b'synthetic image bytes'
    assert client.get('/api/v1/research/racevision/cones/2').status_code == 404
    (dataset / 'frame.png').write_bytes(b'tampered')
    assert client.get('/api/v1/research/racevision/cones/1/image').status_code == 503
    assert client.get('/api/v1/research/racevision/cones/1').status_code == 503


def test_cone_gallery_rejects_unavailable_artifacts_and_path_traversal(artifacts, tmp_path):
    dataset, run = artifacts
    client = TestClient(create_app(racevision_dataset_path=tmp_path / 'missing', racevision_run_path=run))
    assert client.get('/api/v1/research/racevision/cones').status_code == 503
    manifest = dataset / 'manifest.json'
    data = json.loads(manifest.read_text())
    data['records'][0]['image']['path'] = '../run/detector.pth'
    manifest.write_text(json.dumps(data))
    metrics = run / 'metrics.json'
    values = json.loads(metrics.read_text())
    values['dataset_manifest_sha256'] = sha(manifest)
    metrics.write_text(json.dumps(values))
    client = TestClient(create_app(racevision_dataset_path=dataset, racevision_run_path=run))
    assert client.get('/api/v1/research/racevision/cones/1/image').status_code == 503
