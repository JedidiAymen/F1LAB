"""Direct exploratory multi-horizon forecasts on the prior pace frame.

The inherited frame already requires a consecutive next lap with an end time;
a further future target and intermediate source records are required for scoring. This conditions
results on future survival/record availability, not unconditional live use.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_pinball_loss

from f1_racelab.ml.common.guards import (
    assert_chronological,
    assert_disjoint_groups,
    chronological_group_folds,
)
from f1_racelab.ml.common.metrics import cluster_bootstrap_delta
from f1_racelab.ml.pace import dataset as ds
from f1_racelab.ml.pace.bundle import LgbmBundle
from f1_racelab.ml.pace.strict import decision_frame

KEYS = ['race_id', 'driver_number', 'lap']
HORIZONS = (1, 3, 5)
NUMERIC = [c for c in ds.NUMERIC if c != 'laps_in_stint_next']
CATEGORICAL = ds.CATEGORICAL


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def make_population(frame: pd.DataFrame, horizon: int) -> tuple[pd.DataFrame, dict]:
    """Join the exact future recorded target; count target and intermediate gaps."""
    if horizon not in HORIZONS:
        raise ValueError('Unsupported horizon')
    if frame[KEYS].isna().any().any() or frame.duplicated(KEYS).any():
        raise ValueError('Missing or duplicate source identities')
    times = frame[KEYS].copy()
    times['time'] = pd.to_datetime(frame.cutoff, utc=True, errors='coerce')
    if times.time.isna().any():
        raise ValueError('Missing or invalid decision cutoff')
    times = times.sort_values(KEYS)
    if times.groupby(['race_id', 'driver_number']).time.diff().le(pd.Timedelta(0)).any():
        raise ValueError('Nonmonotonic source cutoffs')
    base = decision_frame(frame).dropna(subset=['anchor_seconds']).copy()
    # Exact joins, not row offsets, distinguish absent source records from horizons.
    target = frame[KEYS + ['next_lap_seconds', 'regime_next', 'next_is_out_lap',
                           'next_is_in_lap', 'eligible_green_next']].copy()
    target['lap'] = target['lap'] - horizon + 1
    target = target.rename(columns={'next_lap_seconds': 'target_seconds', 'regime_next': 'target_regime',
                                    'next_is_out_lap': 'target_out', 'next_is_in_lap': 'target_in',
                                    'eligible_green_next': 'target_green'})
    merged = base.merge(target, on=KEYS, how='left', validate='one_to_one')
    recorded = pd.to_numeric(merged.target_seconds, errors='coerce')
    has_target = np.isfinite(recorded) & recorded.gt(0)
    complete = pd.Series(True, index=merged.index)
    for step in range(1, horizon):
        available = frame[KEYS].copy()
        available['lap'] = available['lap'] - step
        available[f'_present_{step}'] = True
        merged = merged.merge(available, on=KEYS, how='left', validate='one_to_one')
        complete &= merged[f'_present_{step}'].fillna(False).astype(bool)
    keep = has_target & complete
    counts = {'decision_rows': len(merged), 'missing_target': int((~has_target).sum()),
              'target_present_missing_intermediate': int((has_target & ~complete).sum()),
              'scored_eligible': int(keep.sum())}
    result = merged.loc[keep].copy()
    result['target_delta'] = result.target_seconds - result.anchor_seconds
    result['target_outcome'] = np.select([result.target_out.fillna(False).astype(bool),
                                          result.target_in.fillna(False).astype(bool),
                                          result.target_green.fillna(False).astype(bool)],
                                         ['out_lap', 'in_lap', 'green_clean'], default=result.target_regime)
    return result, counts


def last_clean_delta(frame: pd.DataFrame) -> np.ndarray:
    """Most recent clean lap among L..L-2; fall back to the median anchor."""
    return frame[['last1', 'last2', 'last3']].bfill(axis=1).iloc[:, 0].fillna(0.0).to_numpy(float)


def walk_forward(frame: pd.DataFrame, horizon: int, output: Path) -> pd.DataFrame:
    races = frame.groupby('race_id', as_index=False).race_start.first()
    parts = []
    for fold, (train_ids, test_ids) in enumerate(chronological_group_folds(
            races, group_col='race_id', time_col='race_start', min_train=20, step=3)):
        assert_disjoint_groups(train_ids, test_ids, name='race')
        train, test = frame[frame.race_id.isin(train_ids)], frame[frame.race_id.isin(test_ids)]
        assert_chronological(train.race_start.tolist(), test.race_start.tolist())
        model = LgbmBundle(NUMERIC, CATEGORICAL, quantiles=True).fit(train, train.target_delta.to_numpy())
        x = model._x(test)
        anchor = test.anchor_seconds.to_numpy(float)
        median = anchor + model.median.predict(x)
        # Use raw quantiles so crossings remain visible in the study.
        q10, q90 = anchor + model.q10.predict(x), anchor + model.q90.predict(x)
        last = anchor + last_clean_delta(test)
        baseline = last.copy()
        if horizon == 1:
            pitted = train.just_pitted
            adjustment = float(train.loc[pitted, 'target_delta'].median()) if pitted.any() else 0.0
            baseline = np.where(test.just_pitted.to_numpy(), anchor + adjustment, last)
        part = test[KEYS + ['year', 'event', 'circuit', 'target_seconds', 'target_outcome']].copy()
        part = part.assign(horizon=horizon, fold=fold, anchor=anchor, last_clean=last,
                           pit_rule=baseline, lightgbm=median, q10=q10, q90=q90)
        parts.append(part)
        joblib.dump({'model': model, 'train_ids': train_ids, 'test_ids': test_ids}, output / f'h{horizon}-fold-{fold:02d}.joblib')
    if not parts:
        raise ValueError('No chronological folds available')
    return pd.concat(parts, ignore_index=True)


def summarise(predictions: pd.DataFrame) -> dict:
    result = {}
    for horizon, frame in predictions.groupby('horizon'):
        y = frame.target_seconds.to_numpy(float)
        stats = {}
        for name in ('anchor', 'last_clean', 'pit_rule', 'lightgbm'):
            err = np.abs(y - frame[name].to_numpy(float))
            stats[name] = {'mae': float(err.mean()), 'median_ae': float(np.median(err)),
                           'rmse': float(np.sqrt(np.mean(err ** 2)))}
        low, high = frame.q10.to_numpy(float), frame.q90.to_numpy(float)
        delta = cluster_bootstrap_delta(np.abs(y - frame.lightgbm), np.abs(y - frame.last_clean),
                                        frame.race_id.to_numpy(), draws=5000, seed=42)
        def groups(column: str, subset: pd.DataFrame = frame) -> dict:
            return {str(key): {'n': len(group), 'lightgbm_mae': float((group.target_seconds - group.lightgbm).abs().mean()),
                               'last_clean_mae': float((group.target_seconds - group.last_clean).abs().mean())}
                    for key, group in subset.groupby(column)}
        result[str(horizon)] = {'rows': len(frame), 'races': int(frame.race_id.nunique()), 'models': stats,
                                'paired_lightgbm_vs_last_clean': delta,
                                'interval': {'coverage': float(((y >= low) & (y <= high)).mean()),
                                             'mean_width_raw': float((high - low).mean()),
                                             'crossings': int((low > high).sum()),
                                             'pinball_q10': float(mean_pinball_loss(y, low, alpha=.1)),
                                             'pinball_q90': float(mean_pinball_loss(y, high, alpha=.9))},
                                'by_year': groups('year'), 'by_race': groups('race_id'),
                                'by_outcome_retrospective': groups('target_outcome')}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pace', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError('Choose a new output directory; never overwrite research artifacts')
    frame = pd.read_parquet(args.pace)
    args.out.mkdir(parents=True)
    models = args.out / 'models'
    models.mkdir()
    start = time.perf_counter()
    data, populations = [], {}
    for horizon in HORIZONS:
        population, populations[str(horizon)] = make_population(frame, horizon)
        data.append(walk_forward(population, horizon, models))
    predictions = pd.concat(data, ignore_index=True)
    predictions.to_parquet(args.out / 'predictions.parquet', index=False)
    (args.out / 'summary.json').write_text(json.dumps({'population': populations, 'horizons': summarise(predictions)}, indent=2))
    manifest = {'source_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                'pace_sha256': sha(args.pace), 'prediction_sha256': sha(args.out / 'predictions.parquet'),
                'summary_sha256': sha(args.out / 'summary.json'), 'models': {p.name: sha(p) for p in sorted(models.iterdir())},
                'python': platform.python_version(), 'platform': platform.platform(),
                'dependencies': {name: importlib.metadata.version(name) for name in ('numpy', 'pandas', 'scikit-learn', 'lightgbm', 'joblib')},
                'elapsed_seconds': time.perf_counter() - start,
                'note': 'Local trusted joblib only; hashes are not authenticity. Exploratory previously inspected races.'}
    (args.out / 'manifest.json').write_text(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
