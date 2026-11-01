"""Measure one trusted-local fold's batch inference, excluding feature reconstruction."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import joblib
import pandas as pd

from f1_racelab.ml.pace.multihorizon import make_population, sha


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pace', type=Path, required=True)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--model', default='h5-fold-00.joblib')
    args = parser.parse_args()
    if Path(args.model).name != args.model:
        raise ValueError('Model must be a filename')
    manifest = json.loads((args.run / 'manifest.json').read_text())
    path = args.run / 'models' / args.model
    if path.is_symlink() or sha(path) != manifest['models'][args.model] or sha(args.pace) != manifest['pace_sha256']:
        raise ValueError('Checksum mismatch')
    start = time.perf_counter()
    artifact = joblib.load(path)  # Trusted local artifact only; checksum is not authentication.
    load_seconds = time.perf_counter() - start
    horizon = int(args.model.split('-')[0][1:])
    frame = make_population(pd.read_parquet(args.pace), horizon)[0]
    model = artifact['model']
    x = model._x(frame[frame.race_id.isin(artifact['test_ids'])])
    samples = []
    for _ in range(5):
        start = time.perf_counter()
        for estimator in (model.median, model.q10, model.q90):
            estimator.predict(x)
        samples.append((time.perf_counter() - start) * 1000 / len(x))
    print(json.dumps({'model': args.model, 'rows': len(x), 'trusted_load_seconds': load_seconds,
                      'batch_ms_per_row_mean_5': sum(samples) / len(samples), 'samples': samples}, indent=2))


if __name__ == '__main__':
    main()
