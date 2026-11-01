import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('track_pace', Path(__file__).parents[1] / 'scripts/track_pace_multihorizon.py')
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_tracking_rejects_remote_and_existing_receipt(tmp_path):
    with pytest.raises(ValueError, match='local HTTP'):
        module.track(tmp_path, 'https://example.com')
    (tmp_path / 'mlflow_import.json').write_text('{}')
    with pytest.raises(FileExistsError, match='duplicate'):
        module.track(tmp_path, 'http://127.0.0.1:5000')


def test_tracking_fails_before_network_if_summary_changed(tmp_path):
    (tmp_path / 'manifest.json').write_text(json.dumps({'summary_sha256': 'bad'}))
    (tmp_path / 'summary.json').write_text('{}')
    with pytest.raises(ValueError, match='checksum'):
        module.track(tmp_path, 'http://127.0.0.1:5000')
