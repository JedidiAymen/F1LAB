"""Import a completed local study into local MLflow, explicitly after training."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

from f1_racelab.ml.pace.multihorizon import sha


def track(run_dir: Path, uri: str) -> dict:
    parsed = urlparse(uri)
    if parsed.scheme != 'http' or parsed.hostname not in {'localhost', '127.0.0.1', '::1'} or parsed.username or parsed.password:
        raise ValueError('Tracking endpoint must be local HTTP without credentials')
    tracking_path = run_dir / 'mlflow_import.json'
    if tracking_path.exists():
        raise FileExistsError('Existing tracking receipt; do not duplicate the import')
    manifest = json.loads((run_dir / 'manifest.json').read_text())
    if sha(run_dir / 'summary.json') != manifest['summary_sha256']:
        raise ValueError('Summary checksum mismatch')
    report = json.loads((run_dir / 'summary.json').read_text())
    with httpx.Client(base_url=uri, timeout=30) as client:
        def post(endpoint: str, data: dict) -> dict:
            response = client.post('/api/2.0/mlflow/' + endpoint, json=data)
            response.raise_for_status()
            return response.json()
        experiment_name = 'F1LAB/race-pace-multihorizon'
        response = client.get('/api/2.0/mlflow/experiments/get-by-name', params={'experiment_name': experiment_name})
        if response.status_code == 404:
            experiment_id = post('experiments/create', {'name': experiment_name})['experiment_id']
        else:
            response.raise_for_status()
            experiment_id = response.json()['experiment']['experiment_id']
        tags = {'mlflow.runName': 'recorded-lap-horizons-20261101', 'f1lab.run_kind': 'completed_study_import',
                'f1lab.source_revision': manifest['source_revision'], 'f1lab.dataset_sha256': manifest['pace_sha256'],
                'f1lab.evidence': 'previously inspected, outcome-selected historical records'}
        run = post('runs/create', {'experiment_id': experiment_id, 'start_time': int(time.time() * 1000),
                                   'tags': [{'key': key, 'value': value} for key, value in tags.items()]})['run']
        run_id = run['info']['run_id']
        try:
            metrics = []
            timestamp = int(time.time() * 1000)
            for horizon, result in report['horizons'].items():
                for model, values in result['models'].items():
                    for metric, value in values.items():
                        metrics.append({'key': f'h{horizon}.{model}.{metric}', 'value': value,
                                        'timestamp': timestamp, 'step': 0})
                metrics.append({'key': f'h{horizon}.raw_interval_coverage', 'value': result['interval']['coverage'],
                                'timestamp': timestamp, 'step': 0})
            params = {'horizons': '1,3,5', 'seed': '42', 'initial_train_races': '20', 'test_races_per_fold': '3',
                      'data_contract': 'recorded_lap_selected', 'source_revision': manifest['source_revision']}
            post('runs/log-batch', {'run_id': run_id, 'metrics': metrics,
                                    'params': [{'key': key, 'value': value} for key, value in params.items()]})
            artifact_uri = run['info']['artifact_uri']
            if not artifact_uri.startswith('mlflow-artifacts:/'):
                raise ValueError('Local MLflow artifact proxy is required')
            artifact_path = artifact_uri.removeprefix('mlflow-artifacts:/').strip('/')
            for name in ('manifest.json', 'summary.json'):
                response = client.put(f'/api/2.0/mlflow-artifacts/artifacts/{artifact_path}/{name}',
                                      content=(run_dir / name).read_bytes(),
                                      headers={'Content-Type': 'application/octet-stream'})
                response.raise_for_status()
            post('runs/update', {'run_id': run_id, 'status': 'FINISHED', 'end_time': int(time.time() * 1000)})
        except Exception:
            try:
                post('runs/update', {'run_id': run_id, 'status': 'FAILED', 'end_time': int(time.time() * 1000)})
            except httpx.HTTPError:
                pass
            raise
    receipt = {'run_id': run_id, 'experiment_id': experiment_id, 'kind': 'completed_study_import',
               'manifest_sha256': sha(run_dir / 'manifest.json'), 'tracking_uri': uri}
    tracking_path.write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--uri', default='http://127.0.0.1:5000')
    args = parser.parse_args()
    print(json.dumps(track(args.run, args.uri), indent=2))


if __name__ == '__main__':
    main()
