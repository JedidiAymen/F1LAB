"""Expose the frozen offline evidence-gate experiment, never execute an agent."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4] / 'docs/research/evidence/agent_gate_20261101'
REPORT_SHA256 = '7b86b57cca741a75c510d71adfaaca32f81bc65c7c8c8a605c4bb81247157f44'


def load(root: Path = ROOT) -> dict:
    payload = (root / 'report.json').read_bytes()
    if hashlib.sha256(payload).hexdigest() != REPORT_SHA256:
        raise ValueError('Evidence-gate report checksum mismatch')
    report = json.loads(payload)
    if len(report['cases']) != report['summary']['cases'] or len({row['scenario_id'] for row in report['cases']}) != 16:
        raise ValueError('Incomplete or duplicate evaluation cases')
    return {**report, 'report_sha256': REPORT_SHA256}
