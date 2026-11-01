"""Recompute exploratory forecast error slices from the frozen PR #4 predictions."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

MODELS = ('last_completed_lap', 'tcn_seed7', 'tcn_no_context_seed42', 'tcn_masked_seed42')
BINS = ((0.0, 1.0, 'at most 1 s'), (1.0, 5.0, 'over 1 to 5 s'), (5.0, float('inf'), 'over 5 s'))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def paired_interval(group: pd.DataFrame, model: str, samples: int = 2000) -> list[float] | None:
    """Resample session/driver clusters, conditional on the inspected events."""
    differences = np.abs(group[model].to_numpy() - group.remaining_seconds.to_numpy()) - np.abs(
        group.last_completed_lap.to_numpy() - group.remaining_seconds.to_numpy())
    keys = list(zip(group.session_key, group.driver_number))
    by_cluster: dict[tuple[int, int], list[float]] = {}
    for key, value in zip(keys, differences):
        by_cluster.setdefault(key, []).append(float(value))
    clusters = [np.asarray(values) for _, values in sorted(by_cluster.items())]
    if len(clusters) < 2:
        return None
    rng = np.random.default_rng(42)
    draws = [np.concatenate([clusters[i] for i in rng.integers(len(clusters), size=len(clusters))]).mean()
             for _ in range(samples)]
    return np.quantile(draws, [0.025, 0.975]).tolist()


def summarize(group: pd.DataFrame) -> dict:
    result = {'rows': len(group), 'clusters': group.groupby(['session_key', 'driver_number']).ngroups, 'models': {}}
    if group.empty:
        return result
    truth = group.remaining_seconds.to_numpy()
    baseline_error = np.abs(group.last_completed_lap.to_numpy() - truth)
    for model in MODELS:
        error = group[model].to_numpy() - truth
        result['models'][model] = {'mae_s': float(np.abs(error).mean()), 'median_ae_s': float(np.median(np.abs(error))),
            'rmse_s': float(np.sqrt(np.mean(error ** 2))), 'bias_s': float(error.mean()),
            'paired_mae_delta_s': float((np.abs(error) - baseline_error).mean()),
            'conditional_cluster_bootstrap_95_s': paired_interval(group, model)}
    return result


def analyze(root: Path) -> dict:
    study_file, predictions_file, card_file = root / 'study.json', root / 'predictions.parquet', root / 'dataset_card.json'
    if sha(study_file) != (root / 'study.sha256').read_text().strip():
        raise ValueError('Study checksum mismatch')
    study = json.loads(study_file.read_text())
    if sha(predictions_file) != study['prediction_sha256'] or json.loads(card_file.read_text()) != study['dataset']:
        raise ValueError('Prediction or dataset card disagrees with the frozen study')
    frame = pd.read_parquet(predictions_file)
    required = ['remaining_seconds', 'lap_seconds', 'last_lap_seconds', 'recent_three_seconds', *MODELS]
    if len(frame) != study['dataset']['rows'] or frame.duplicated(['session_key', 'driver_number', 'lap_number']).any():
        raise ValueError('Prediction population violates the frozen study contract')
    if not np.isfinite(frame[required].to_numpy(dtype=float)).all():
        raise ValueError('Nonfinite forecast values')
    test = frame[frame.split == 'test'].copy()
    if set(test.session_key.unique()) != {11234, 11253}:
        raise ValueError('Unexpected held-out event set')
    retrospective = np.abs(test.lap_seconds - test.last_lap_seconds)
    prior = np.abs(test.last_lap_seconds - test.recent_three_seconds)
    slices = {}
    for name, values in [('retrospective_lap_change', retrospective), ('asof_prior_change', prior)]:
        slices[name] = [{'label': label, **summarize(test[(values > low if low else values >= low) & (values <= high)])}
                        for low, high, label in BINS]
    corrections = []
    for split in ('train', 'validation', 'test'):
        section = frame[frame.split == split]
        for model in MODELS[1:]:
            delta = section[model].to_numpy() - section.last_completed_lap.to_numpy()
            actual = section.remaining_seconds.to_numpy() - section.last_completed_lap.to_numpy()
            correlation = float(np.corrcoef(delta, actual)[0, 1]) if np.std(delta) > 0 and np.std(actual) > 0 else None
            corrections.append({'split': split, 'model': model, 'rows': len(section),
                                'correction_mean_s': float(delta.mean()), 'correction_median_s': float(np.median(delta)),
                                'correction_p05_s': float(np.quantile(delta, 0.05)),
                                'correction_p95_s': float(np.quantile(delta, 0.95)), 'residual_correlation': correlation})
    return {'schema_version': 1, 'status': 'exploratory; previously inspected events',
            'study_sha256': sha(study_file), 'predictions_sha256': sha(predictions_file),
            'total_test': summarize(test),
            'by_session': [{'session_key': int(key), 'circuit': str(g.circuit.iloc[0]), **summarize(g)}
                           for key, g in test.groupby('session_key')],
            'slices': slices, 'corrections': corrections,
            'limits': ['Retrospective lap-change slices use future outcomes and are not model inputs.',
                       'Events were previously inspected; clusters condition on these two circuits.',
                       'As-of features use retrospective provider observation timestamps; publication latency is unknown.',
                       'No causal classification of pit, safety-car, tyres, weather or traffic.']}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    data = analyze(args.input)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x') as handle:
        json.dump(data, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write('\n')
    print(f'Wrote {args.out}; SHA-256 {sha(args.out)}')


if __name__ == '__main__':
    main()
