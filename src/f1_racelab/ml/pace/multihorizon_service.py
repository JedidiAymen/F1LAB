"""Read a checksummed saved study; no model deserialization or inference."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BUNDLED = ROOT / 'docs/research/evidence/pace_multihorizon_20261101'
# Set from the completed published report; checksums are not authenticity.
EXPECTED_MANIFEST_SHA256 = 'b1ad9a44c4d18a6fcfa09662078a3f686d7636c256c8fe82e2fd0b693410ae70'


def load(root: Path = BUNDLED, expected_manifest: str = EXPECTED_MANIFEST_SHA256) -> dict:
    manifest_bytes = (root / 'manifest.json').read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != expected_manifest:
        raise ValueError('Multi-horizon manifest checksum mismatch')
    manifest = json.loads(manifest_bytes)
    report = (root / 'summary.json').read_bytes()
    if hashlib.sha256(report).hexdigest() != manifest['summary_sha256']:
        raise ValueError('Multi-horizon summary checksum mismatch')
    summary = json.loads(report)
    if set(summary['horizons']) != {'1', '3', '5'} or set(summary['population']) != {'1', '3', '5'}:
        raise ValueError('Unexpected horizon study')
    return {'summary': summary, 'source_sha256': manifest['pace_sha256'],
            'source_revision': manifest['source_revision'], 'manifest_sha256': expected_manifest,
            'evidence': 'retrospective recorded-lap selected; no live inference'}
