"""Reload trusted local fold artifacts after hash checks and independently reproduce predictions.

Checksums establish consistency, not trust: joblib deserialization can execute code.
Never use this verifier on untrusted or externally supplied artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

KEYS = ['race_id', 'lap', 'driver_number', 'a_driver_number']


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(pairs_path: Path, run: Path) -> dict:
    manifest = json.loads((run / 'manifest.json').read_text())
    pred_path = run / 'predictions.parquet'
    if (sha(pairs_path) != manifest['pair_dataset_sha256'] or sha(pred_path) != manifest['prediction_sha256']
            or sha(run / 'summary.json') != manifest['summary_sha256']):
        raise ValueError('Input or prediction checksum mismatch')
    pairs = pd.read_parquet(pairs_path)
    predictions = pd.read_parquet(pred_path)
    if pairs.duplicated(KEYS).any() or predictions.duplicated(['model', *KEYS]).any():
        raise ValueError('Duplicate pair identity')
    max_difference = 0.0
    checked = 0
    for name, expected in sorted(manifest['models'].items()):
        if Path(name).name != name or not name.startswith('fold-') or not name.endswith('.joblib'):
            raise ValueError('Unexpected artifact name')
        path = run / 'models' / name
        if path.is_symlink() or sha(path) != expected:
            raise ValueError('Fold artifact checksum mismatch')
        fold = joblib.load(path)  # trusted local artifact only; checksum is not authentication
        if set(fold['train_ids']) & set(fold['test_ids']):
            raise ValueError('Fold contains overlapping train/test races')
        selected = predictions[(predictions.fold == fold['fold']) & (predictions.model == 'logistic_gap')]
        joined = selected.merge(pairs, on=KEYS, how='left', validate='one_to_one', suffixes=('_prediction', ''))
        if joined.overtake.isna().any() or not joined.y.eq(joined.overtake).all():
            raise ValueError('Prediction rows do not match the pair dataset')
        values = {
            'constant_rate': np.full(len(joined), fold['constant_rate']),
            'logistic_gap': fold['logistic_gap'].predict_proba(joined[fold['gap_features']])[:, 1],
            'logistic_all': fold['logistic_all'].predict_proba(joined[fold['features']])[:, 1],
            'lightgbm_raw': fold['lightgbm'].predict_proba(joined[fold['features']])[:, 1],
        }
        values['lightgbm_calibrated'] = fold['isotonic'].predict(values['lightgbm_raw'])
        for model, computed in values.items():
            reference = predictions[(predictions.fold == fold['fold']) & (predictions.model == model)]
            expected_rows = selected[KEYS].merge(reference[KEYS + ['p']], on=KEYS, how='left', validate='one_to_one')
            if expected_rows.p.isna().any() or len(reference) != len(expected_rows):
                raise ValueError('Incomplete prediction set')
            difference = float(np.max(np.abs(np.clip(computed, 1e-4, 1 - 1e-4) - expected_rows.p.to_numpy())))
            max_difference = max(max_difference, difference)
            checked += len(reference)
            if difference > 1e-10:
                raise ValueError(f'Prediction mismatch for {name}/{model}: {difference}')
    return {'folds': len(manifest['models']), 'prediction_rows_verified': checked,
            'max_abs_probability_difference': max_difference}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pairs', type=Path, required=True)
    parser.add_argument('--run', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.pairs, args.run), indent=2))


if __name__ == '__main__':
    main()
