"""Expose the frozen offline evidence-gate experiment, never execute an agent."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4] / 'docs/research/evidence/agent_gate_20261101'
REPORT_SHA256 = '70e073da86f04d96b73eba12f6fa6610269b787981b749023705d79143e403de'


def load(root: Path = ROOT) -> dict:
    payload = (root / 'report_final.json').read_bytes()
    if hashlib.sha256(payload).hexdigest() != REPORT_SHA256:
        raise ValueError('Evidence-gate report checksum mismatch')
    report = json.loads(payload)
    if len(report['cases']) != report['summary']['cases'] or len({row['scenario_id'] for row in report['cases']}) != 16:
        raise ValueError('Incomplete or duplicate evaluation cases')
    return {**report, 'report_sha256': REPORT_SHA256}
