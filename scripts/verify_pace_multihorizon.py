"""Recompute a saved pace study from trusted-local hashed fold artifacts.

Joblib can execute code: hashes detect changes, they do not authenticate inputs.
Do not run this verifier on untrusted model files.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from f1_racelab.ml.pace.multihorizon import (
    CATEGORICAL,
    KEYS,
    NUMERIC,
    last_observed_delta,
    make_population,
    sha,
    summarise,
)


def verify(pace: Path, run: Path) -> dict:
    manifest = json.loads((run / 'manifest.json').read_text())
    if (sha(pace) != manifest['pace_sha256'] or sha(run / 'predictions.parquet') != manifest['prediction_sha256']
            or sha(run / 'summary.json') != manifest['summary_sha256']):
        raise ValueError('Study input or report checksum mismatch')
    source = pd.read_parquet(pace)
    predictions = pd.read_parquet(run / 'predictions.parquet')
    if predictions.duplicated(['horizon', *KEYS]).any():
        raise ValueError('Duplicate predictions')
    saved_summary = json.loads((run / 'summary.json').read_text())
    if summarise(predictions) != saved_summary['horizons']:
        raise ValueError('Summary does not match predictions')
    checked, maximum = 0, 0.0
    for horizon in sorted(predictions.horizon.unique()):
        frame, counts = make_population(source, int(horizon))
        if counts != saved_summary['population'][str(horizon)]:
            raise ValueError('Population does not match source')
        for fold in sorted(predictions.loc[predictions.horizon == horizon, 'fold'].unique()):
            name = f'h{horizon}-fold-{fold:02d}.joblib'
            path = run / 'models' / name
            if path.is_symlink() or sha(path) != manifest['models'][name]:
                raise ValueError('Fold model checksum mismatch')
            artifact = joblib.load(path)  # Trusted-local file only.
            recorded = predictions[(predictions.horizon == horizon) & (predictions.fold == fold)]
            if set(recorded.race_id.unique()) != set(artifact['test_ids']):
                raise ValueError('Fold test races differ')
            if set(artifact['train_ids']) & set(artifact['test_ids']):
                raise ValueError('Train and test race overlap')
            training = frame[frame.race_id.isin(artifact['train_ids'])]
            testing = frame[frame.race_id.isin(artifact['test_ids'])]
            if training.empty or testing.empty or training.race_start.max() >= testing.race_start.min():
                raise ValueError('Fold is not strictly chronological')
            if artifact['model'].numeric != NUMERIC or artifact['model'].categorical != CATEGORICAL:
                raise ValueError('Model feature contract mismatch')
            joined = recorded.merge(frame, on=KEYS, how='left', validate='one_to_one', suffixes=('_saved', ''))
            if joined.target_delta.isna().any() or not np.allclose(joined.target_seconds_saved, joined.target_seconds):
                raise ValueError('Recorded targets differ from source')
            model, anchor = artifact['model'], joined.anchor_seconds.to_numpy(float)
            x = model._x(joined)
            actual = {'anchor': anchor, 'last_observed': anchor + last_observed_delta(joined),
                      'lightgbm': anchor + model.median.predict(x), 'q10': anchor + model.q10.predict(x),
                      'q90': anchor + model.q90.predict(x)}
            for name, values in actual.items():
                difference = float(np.max(np.abs(joined[name].to_numpy(float) - values)))
                maximum = max(maximum, difference)
                if difference > 1e-10:
                    raise ValueError(f'{name} prediction mismatch')
            checked += len(joined)
    return {'fold_models': len(manifest['models']), 'prediction_rows': checked,
            'max_absolute_difference_seconds': maximum}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pace', type=Path, required=True)
    parser.add_argument('--run', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.pace, args.run), indent=2))


if __name__ == '__main__':
    main()
