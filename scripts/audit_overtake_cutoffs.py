"""Compare saved retrospective overtake rows with their source observation cutoffs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from f1_racelab.ml.overtake.dataset import build

KEYS = ['race_id', 'lap', 'driver_number', 'a_driver_number']


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(frame: pd.DataFrame, pairs: pd.DataFrame, predictions: pd.DataFrame) -> dict:
    if frame.duplicated(['race_id', 'driver_number', 'lap']).any() or pairs.duplicated(KEYS).any():
        raise ValueError('Duplicate source or pair keys')
    source = frame.sort_values(['race_id', 'driver_number', 'lap']).copy()
    source['next_record_lap'] = source.groupby(['race_id', 'driver_number']).lap.shift(-1)
    source['cutoff'] = pd.to_datetime(source.cutoff, utc=True, errors='coerce', format='mixed')
    observations = source[['race_id', 'driver_number', 'lap', 'cutoff', 'next_record_lap']]
    joined = pairs.merge(observations, on=['race_id', 'driver_number', 'lap'], how='left', validate='many_to_one')
    joined = joined.merge(observations.rename(columns={'driver_number': 'a_driver_number', 'cutoff': 'leader_cutoff',
                                                        'next_record_lap': 'leader_next_record_lap'}),
                          on=['race_id', 'a_driver_number', 'lap'], how='left', validate='many_to_one')
    if joined[['cutoff', 'leader_cutoff']].isna().any().any():
        raise ValueError('Saved pair has missing source cutoff')
    late = joined.leader_cutoff > joined.cutoff
    nonconsecutive = ~joined.next_record_lap.eq(joined.lap + 1) | ~joined.leader_next_record_lap.eq(joined.lap + 1)
    scored_races = set(predictions.race_id.unique())
    late_rows = joined[late].copy()
    late_rows['leader_minus_follower_seconds'] = (late_rows.leader_cutoff - late_rows.cutoff).dt.total_seconds()
    examples = [{'race_id': str(r.race_id), 'year': int(r.year), 'event': str(r.event), 'lap': int(r.lap),
                 'follower': int(r.driver_number), 'leader': int(r.a_driver_number),
                 'leader_minus_follower_seconds': float(r.leader_minus_follower_seconds),
                 'observed_swap': int(r.overtake), 'race_scored': r.race_id in scored_races}
                for r in late_rows.itertuples()]
    rebuilt = build(frame)
    comparison = pairs.merge(rebuilt, on=KEYS, suffixes=('_saved', '_strict'), how='outer', indicator=True,
                             validate='one_to_one')
    shared = comparison[comparison._merge == 'both']
    prior_saved, prior_strict = shared.circuit_rate_prior_saved, shared.circuit_rate_prior_strict
    changed_prior = ~np.isclose(prior_saved, prior_strict, equal_nan=True, rtol=0, atol=1e-12)
    label_changes = shared.overtake_saved.ne(shared.overtake_strict)
    return {'saved_pair_rows': len(pairs), 'strict_pair_rows': len(rebuilt), 'late_leader_rows': int(late.sum()),
            'late_leader_rows_in_scored_races': int((late & joined.race_id.isin(scored_races)).sum()),
            'nonconsecutive_next_rows': int(nonconsecutive.sum()),
            'removed_saved_rows': int((comparison._merge == 'left_only').sum()),
            'new_strict_rows': int((comparison._merge == 'right_only').sum()),
            'shared_rows_with_changed_prior_rate': int(changed_prior.sum()),
            'shared_rows_with_changed_prior_rate_in_scored_races': int((changed_prior & shared.race_id.isin(scored_races)).sum()),
            'shared_rows_with_changed_label': int(label_changes.sum()), 'late_examples': examples,
            'limitations': ['Gap-order changes are timing-inferred, not verified passes.',
                            'Future pit and neutralization exclusions define a retrospective selected cohort.',
                            'Cutoffs do not prove provider publication times or exact track positions.',
                            'No model was retrained and no revised prediction metrics were calculated.']}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pace', type=Path, required=True)
    parser.add_argument('--pairs', type=Path, required=True)
    parser.add_argument('--predictions', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = audit(pd.read_parquet(args.pace), pd.read_parquet(args.pairs), pd.read_parquet(args.predictions))
    result['source_sha256'] = {name: sha(getattr(args, name)) for name in ('pace', 'pairs', 'predictions')}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x') as output:
        json.dump(result, output, indent=2, sort_keys=True, allow_nan=False)
        output.write('\n')
    print(json.dumps(result, indent=2))
    print('audit_sha256', sha(args.out))


if __name__ == '__main__':
    main()
