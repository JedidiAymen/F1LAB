"""Read the frozen, aggregate overtake timing audit."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4] / 'docs/research/evidence/overtake_cutoff_20261101'


def load(root: Path = ROOT) -> dict:
    payload = (root / 'report.json').read_bytes()
    if hashlib.sha256(payload).hexdigest() != (root / 'report.sha256').read_text().strip():
        raise ValueError('Overtake audit checksum mismatch')
    return json.loads(payload)
