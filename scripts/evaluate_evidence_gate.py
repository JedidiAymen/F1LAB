"""Evaluate the frozen observational gate on previously inspected synthetic traces."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from f1_racelab.agents.forecast_debug import evidence_gate

RESULTS_SHA = '455e24c16c887b0408278d2f640b4de1b5bb6d857db94b7ed018c7c71fe9c797'
PROTOCOL_SHA = 'bbc53caed4aa8077f36619e9c155480ad6afb2734357e9aa651fb18b9ee2ed46'
GATE_REVISION = '174e74bdd8ff775e44d65a34f76e38e521dea5ea'
GATE_FILE_SHA = 'fd488c570c196ecf9d84446ae99c41ca56c9c5bbcb65ba4f74c640ce56a3ef12'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def evaluate(results_path: Path, protocol_path: Path) -> dict:
    if not evidence_gate.__file__ or sha(Path(evidence_gate.__file__).read_bytes()) != GATE_FILE_SHA:
        raise ValueError('Gate implementation differs from the recorded revision')
    results_bytes, protocol_bytes = results_path.read_bytes(), protocol_path.read_bytes()
    if sha(results_bytes) != RESULTS_SHA or sha(protocol_bytes) != PROTOCOL_SHA:
        raise ValueError('Not the registered prior evaluation evidence')
    results, protocol = json.loads(results_bytes), json.loads(protocol_bytes)
    if results['protocol_sha256'] != protocol['protocol_sha256']:
        raise ValueError('Protocol mismatch')
    if protocol['sources']['candidate']['commit'] != '486bba76f092ce1bd0862a9ac2ff41c0640fd96e':
        raise ValueError('Unexpected candidate revision')
    cases = []
    for row in results['cases']:
        if row['arm'] != 'candidate':
            continue
        diagnosis = row['diagnosis']
        verdict = evidence_gate.assess(row['predicted'], diagnosis['evidence'], diagnosis['trace'])
        cases.append({'scenario_id': row['scenario_id'], 'expected': row['expected'], 'proposed': row['predicted'],
                      'original_correct': row['correct'], 'decision': verdict['decision'],
                      'status': verdict['status'], 'signals': verdict['signals']})
    if len(cases) != 16 or len({c['scenario_id'] for c in cases}) != 16:
        raise ValueError('Expected exactly 16 unique candidate cases')
    clean = [row for row in cases if row['proposed'] == 'no_material_discrepancy']
    return {'scope': 'actual Qwen3 outputs on previously inspected synthetic scenarios; no new LLM run',
            'gate_revision': GATE_REVISION, 'results_sha256': RESULTS_SHA, 'protocol_sha256': PROTOCOL_SHA,
            'raw_results_sha256': results['raw_results_sha256'],
            'summary': {'cases': len(cases), 'original_correct': sum(c['original_correct'] for c in cases),
                        'clean_proposals': len(clean), 'false_clean_proposals': sum(c['expected'] != 'no_material_discrepancy' for c in clean),
                        'true_clean_proposals': sum(c['expected'] == 'no_material_discrepancy' for c in clean),
                        'false_clean_withheld': sum(c['expected'] != 'no_material_discrepancy' and c['decision'] == 'abstain' for c in clean),
                        'true_clean_withheld': sum(c['expected'] == 'no_material_discrepancy' and c['decision'] == 'abstain' for c in clean),
                        'clean_statuses': dict(Counter(c['status'] for c in clean)),
                        'all_decisions': dict(Counter(c['decision'] for c in cases))},
            'cases': cases, 'limitations': 'The gate withholds every clean proposal by design and never approves a cause. '
                      'Withholding is not a root-cause accuracy gain; these cases were already inspected.'}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError('Choose a new output file')
    report = evaluate(args.results, args.protocol)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(report, indent=2) + '\n').encode()
    args.out.write_bytes(data)
    print('report_sha256', sha(data))
    print(json.dumps(report['summary'], indent=2))


if __name__ == '__main__':
    main()
