"""Fetch a preregistered, bounded prefix-held-out subset via ZIP byte ranges.

Source files stay local. An unencrypted origin cannot authenticate publisher identity.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

URL = 'http://fsoco.cs.uni-freiburg.de/datasets/fsoco_bounding_boxes_train.zip'
ARCHIVE_SIZE = 24_839_341_525
ETAG = '"5c88a45d5-5f5717cd27c44"'
MAX_TRANSFER = 300_000_000
PREFIXES = {'train': ('amz', 'BME', 'mms', 'ff'), 'val': ('ka',), 'test': ('gfr',)}
LIMITS = {'train': 25, 'val': 20, 'test': 20}


class RemoteZip(io.RawIOBase):
    def __init__(self) -> None:
        self.pos = 0
        self.total = 0

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = 0) -> int:
        self.pos = offset if whence == 0 else self.pos + offset if whence == 1 else ARCHIVE_SIZE + offset
        if self.pos < 0:
            raise ValueError('Negative offset')
        return self.pos

    def read(self, size: int = -1) -> bytes:
        size = min(ARCHIVE_SIZE - self.pos, ARCHIVE_SIZE - self.pos if size < 0 else size)
        if size <= 0:
            return b''
        if size > 40_000_000 or self.total + size > MAX_TRANSFER:
            raise ValueError('Remote download budget exceeded')
        start = self.pos
        end = start + size - 1
        request = urllib.request.Request(URL, headers={'Range': f'bytes={start}-{end}', 'If-Match': ETAG})
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status != 206 or response.headers.get('Content-Range') != f'bytes {start}-{end}/{ARCHIVE_SIZE}':
                raise ValueError('Origin did not honor exact range')
            if response.headers.get('ETag') != ETAG:
                raise ValueError('Archive version changed')
            payload = response.read(size + 1)
        if len(payload) != size:
            raise ValueError('Truncated range response')
        self.pos += size
        self.total += size
        time.sleep(0.02)
        return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True, help='New local artifact directory; no public distribution')
    args = parser.parse_args()
    root = args.out
    root.mkdir(parents=True, exist_ok=True)
    reader = RemoteZip()
    with zipfile.ZipFile(reader) as archive:
        infos = {entry.filename: entry for entry in archive.infolist()}
        records = []
        for split, prefixes in PREFIXES.items():
            for prefix in prefixes:
                images = sorted(name for name in infos if re.fullmatch(
                    rf'[A-Za-z0-9_-]+/img/{prefix}_[A-Za-z0-9_.-]+\.(jpg|png)', name, re.IGNORECASE))
                names = [name for name in images if f'{name.split("/")[0]}/ann/{Path(name).name}.json' in infos][:LIMITS[split]]
                if len(names) != LIMITS[split]:
                    raise ValueError(f'Insufficient pairs in {prefix}: {len(names)}')
                for image in names:
                    team = image.split('/')[0]
                    annotation = f'{team}/ann/{Path(image).name}.json'
                    files = []
                    for name in (image, annotation):
                        info = infos[name]
                        if info.file_size > 10_000_000:
                            raise ValueError(f'File exceeds limit: {name}')
                        destination = root / name
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        if destination.exists():
                            data = destination.read_bytes()
                            if len(data) != info.file_size or zipfile.crc32(data) != info.CRC:
                                raise ValueError(f'Existing file differs from source: {destination}')
                        else:
                            data = archive.read(info)  # zipfile verifies CRC
                            fd, temporary = tempfile.mkstemp(prefix='.partial-', dir=destination.parent)
                            try:
                                with os.fdopen(fd, 'wb') as handle:
                                    handle.write(data)
                                    handle.flush()
                                    os.fsync(handle.fileno())
                                os.link(temporary, destination)
                            finally:
                                Path(temporary).unlink(missing_ok=True)
                        files.append({'path': name, 'sha256': hashlib.sha256(data).hexdigest(),
                                      'bytes': len(data), 'archive_crc32': f'{info.CRC:08x}'})
                    records.append({'split': split, 'source_directory': team, 'filename_prefix': prefix,
                                    'image': files[0], 'annotation': files[1]})
                    if len(records) % 10 == 0:
                        print(f'{len(records)} pairs; {reader.total} remote bytes', flush=True)
        manifest = {'schema_version': 1, 'source_url': URL, 'archive_bytes': ARCHIVE_SIZE, 'etag': ETAG,
                    'protocol': 'docs/research/FSOCO_CONE_PROTOCOL.md', 'records': records}
        payload = (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode()
        manifest_path = root / 'manifest.json'
        if manifest_path.exists() and manifest_path.read_bytes() != payload:
            raise ValueError('Existing manifest differs; use a new output directory')
        if not manifest_path.exists():
            manifest_path.write_bytes(payload)
        print(f'Complete: {len(records)} pairs, {reader.total} downloaded bytes, manifest SHA-256 '
              f'{hashlib.sha256(payload).hexdigest()}')


if __name__ == '__main__':
    main()
