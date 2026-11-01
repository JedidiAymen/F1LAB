"""Copy a local synthetic paired run for review, omitting model scratch text.

This is a projection, not an evaluation or a way to authenticate artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def publish(source: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError('Choose a new destination; existing evidence is immutable')
    raw = (source / 'results.json').read_bytes()
    expected = (source / 'results.sha256').read_text().strip()
    if digest(raw) != expected:
        raise ValueError('Source results checksum mismatch')
    results = json.loads(raw)
    for case in results['cases']:
        case.pop('implementation_path', None)
        for step in case.get('diagnosis', {}).get('trace', []):
            step.pop('thought', None)
    results['raw_results_sha256'] = expected
    protocol = (source / 'protocol.json').read_bytes()
    destination.mkdir(parents=True)
    for name, payload in [('protocol', protocol), ('results', (json.dumps(results, indent=2) + '\n').encode())]:
        (destination / f'{name}.json').write_bytes(payload)
        (destination / f'{name}.sha256').write_text(digest(payload) + '\n')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    publish(args.source, args.out)


if __name__ == '__main__':
    main()
