"""Read saved out-of-fold timing-order forecasts for retrospective investigation.

No model is loaded or executed. Selection depends on later outcomes and is not a
live forecast population. Checksums detect accidental inconsistency, not hostile
artifact replacement or source authentication.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from f1_racelab.ml.overtake.dataset import ROOT

DATASET = ROOT / 'data/processed/overtake/cutoff_strict_20261101_dataset/pairs.parquet'
RUN = ROOT / 'data/processed/overtake/cutoff_strict_20261101_run'
PACE = ROOT / 'data/processed/race_pace/pace_frame.parquet'
KEYS = ['race_id', 'lap', 'driver_number', 'a_driver_number']
MODELS = ['constant_rate', 'logistic_gap', 'logistic_all', 'lightgbm_raw', 'lightgbm_calibrated']


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load(pace: Path, pairs: Path, run: Path, expected_pace_sha: str) -> pd.DataFrame:
    """Validate the fixed source lineage before joining saved predictions."""
    manifest = json.loads((run / 'manifest.json').read_text())
    pred_path = run / 'predictions.parquet'
    if (_sha(pace) != expected_pace_sha or _sha(pairs) != manifest['pair_dataset_sha256']
            or _sha(pred_path) != manifest['prediction_sha256'] or _sha(run / 'summary.json') != manifest['summary_sha256']):
        raise ValueError('Historical artifact checksum mismatch')
    source = pd.read_parquet(pace, columns=['race_id', 'lap', 'driver_number', 'cutoff'])
    dataset = pd.read_parquet(pairs)
    predictions = pd.read_parquet(pred_path)
    if source.duplicated(['race_id', 'lap', 'driver_number']).any() or dataset.duplicated(KEYS).any():
        raise ValueError('Duplicate source or pair identities')
    if predictions.duplicated(['model', *KEYS]).any() or set(predictions.model.unique()) != set(MODELS):
        raise ValueError('Duplicate predictions or unexpected model set')
    if not predictions.p.between(0, 1).all():
        raise ValueError('Invalid probability')
    truth = predictions.groupby(KEYS, dropna=False).y.nunique(dropna=False)
    if not truth.eq(1).all():
        raise ValueError('Prediction labels disagree between models')
    labels = predictions.drop_duplicates(KEYS)[KEYS + ['y']]
    wide = predictions.pivot(index=KEYS, columns='model', values='p').reset_index()
    if wide[MODELS].isna().any().any():
        raise ValueError('Incomplete model predictions')
    result = dataset.merge(wide, on=KEYS, how='inner', validate='one_to_one').merge(labels, on=KEYS, validate='one_to_one')
    if not result.y.eq(result.overtake).all() or len(result) != len(wide):
        raise ValueError('Prediction population does not match saved pairs')
    follower = source.rename(columns={'cutoff': 'follower_cutoff'})
    leader = source.rename(columns={'driver_number': 'a_driver_number', 'cutoff': 'leader_cutoff'})
    result = result.merge(follower, on=['race_id', 'lap', 'driver_number'], how='left', validate='many_to_one')
    result = result.merge(leader, on=['race_id', 'lap', 'a_driver_number'], how='left', validate='many_to_one')
    a = pd.to_datetime(result.leader_cutoff, utc=True, errors='coerce', format='mixed')
    b = pd.to_datetime(result.follower_cutoff, utc=True, errors='coerce', format='mixed')
    if a.isna().any() or b.isna().any() or (a > b).any():
        raise ValueError('Historical cutoff contract violated')
    result['leader_cutoff'], result['follower_cutoff'] = a, b
    return result


def catalog(frame: pd.DataFrame) -> list[dict]:
    events = frame.groupby(['race_id', 'event', 'year', 'race_start'], as_index=False).size().sort_values('race_start')
    return [{'race_id': str(row.race_id), 'event': str(row.event), 'year': int(row.year), 'pairs': int(row.size)}
            for row in events.itertuples(index=False)]


def cases(frame: pd.DataFrame, race_id: str) -> list[dict]:
    selected = frame[frame.race_id.astype(str) == race_id].sort_values(['lap', 'driver_number', 'a_driver_number'])
    if selected.empty:
        raise KeyError('Race is not in the saved walk-forward evaluation')
    if len(selected) > 2000:
        raise ValueError('Race result exceeds the local response limit')
    return [{'lap': int(row.lap), 'follower': int(row.driver_number), 'leader': int(row.a_driver_number),
             'cutoff_utc': pd.Timestamp(row.follower_cutoff).isoformat(),
             'leader_cutoff_utc': pd.Timestamp(row.leader_cutoff).isoformat(),
             'interval_seconds': float(row.interval), 'interval_age_seconds': None if pd.isna(row.intervals_age_s) else float(row.intervals_age_s),
             'timing_order_swapped': bool(row.overtake),
             'probabilities': {name: float(getattr(row, name)) for name in MODELS}}
            for row in selected.itertuples(index=False)]
