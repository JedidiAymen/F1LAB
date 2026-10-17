"""Synthetic source fixtures exercise the library's publication and trust boundary."""
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from f1_racelab.telemetry.lap_library import (
    LapLibrary,
    LapSelection,
    build_library,
    compare_library_laps,
    load_lap,
    load_library,
)


def cache_response(root: Path, endpoint: str, rows: list[dict], **params: int) -> Path:
    resource = endpoint + '?' + '&'.join(f'{key}={value}' for key, value in sorted(params.items()))
    path = root / endpoint / (hashlib.sha256(resource.encode()).hexdigest()[:20] + '.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows))
    return path


def source_fixture(root: Path, *, pit: bool = True, bad_gap: bool = False) -> None:
    identity = {'session_key': 9912, 'meeting_key': 1268}
    roster = [{**identity, 'driver_number': number, 'full_name': f'Driver {number}',
               'name_acronym': str(number)} for number in (1, 4, 44)]
    cache_response(root, 'drivers', roster, session_key=9912)
    start = datetime(2025, 9, 7, 13, tzinfo=UTC)
    laps = [{**identity, 'driver_number': number, 'lap_number': lap,
             'date_start': (start + timedelta(seconds=(lap - 50) * 10)).isoformat(),
             'lap_duration': 10, 'is_pit_out_lap': lap == 52}
            for number in (1, 4) for lap in (50, 51, 52)]
    cache_response(root, 'laps', laps, session_key=9912)
    if pit:
        cache_response(root, 'pit', [{**identity, 'driver_number': 4, 'lap_number': 51}], session_key=9912)
    for number in (1, 4):
        rows = [{**identity, 'driver_number': number,
                 'date': (start + timedelta(seconds=index / 2)).isoformat(),
                 'speed': 180 + number, 'throttle': 100, 'brake': 0,
                 'rpm': 11000, 'n_gear': 6, 'drs': 8}
                for index in range(-1, 62)
                if not (bad_gap and number == 1 and 7 < index < 12)]
        cache_response(root, 'car_data', rows, session_key=9912, driver_number=number)


@pytest.fixture
def built_library(tmp_path):
    cache = tmp_path / 'cache'
    root = tmp_path / 'library'
    source_fixture(cache)
    library = build_library('monza-2025', cache_root=cache, output_root=root)
    return cache, root, library


def test_offline_build_pit_filters_missing_driver_and_deterministic_content(built_library):
    cache, root, library = built_library
    assert [len(driver.laps) for driver in library.drivers] == [2, 1, 0]
    assert library.drivers[-1].unavailable_reason == 'car_data source is not cached'
    assert 'pit-in' in library.drivers[1].rejected_laps[0].reason
    assert 'Pit-out' in library.drivers[0].rejected_laps[0].reason
    assert library.default_selection == LapSelection(driver_a=1, lap_a=50, driver_b=4, lap_b=50)
    before = (root / 'manifest.json').read_bytes()
    build_library('monza-2025', cache_root=cache, output_root=root)
    assert (root / 'manifest.json').read_bytes() == before
    assert load_library(root, 'monza-2025') == library


def test_same_driver_distinct_laps_and_reverse_delta(built_library):
    _, root, library = built_library
    a = compare_library_laps(root, library, LapSelection(driver_a=1, lap_a=50, driver_b=1, lap_b=51))
    assert len(a.source_hashes) == 3  # laps, one car source and optional pit source
    forward = compare_library_laps(root, library, library.default_selection)
    reverse = compare_library_laps(root, library, LapSelection(driver_a=4, lap_a=50, driver_b=1, lap_b=50))
    assert [point.delta_time_b_minus_a_seconds for point in forward.samples] == [
        -point.delta_time_b_minus_a_seconds for point in reverse.samples]
    with pytest.raises(ValueError, match='itself'):
        compare_library_laps(root, library, LapSelection(driver_a=1, lap_a=50, driver_b=1, lap_b=50))


def test_missing_optional_pit_is_unverified_and_same_driver_needs_only_two_sources(tmp_path):
    source_fixture(tmp_path / 'cache', pit=False)
    library = build_library('monza-2025', cache_root=tmp_path / 'cache', output_root=tmp_path / 'library')
    assert len(library.drivers[1].laps) == 2
    assert all(lap.pit_entry_status == 'unverified' for driver in library.drivers for lap in driver.laps)
    comparison = compare_library_laps(tmp_path / 'library', library,
                                     LapSelection(driver_a=1, lap_a=50, driver_b=1, lap_b=51))
    assert len(comparison.source_hashes) == 2


def test_large_sample_gap_rejected_without_discarding_other_laps(tmp_path):
    source_fixture(tmp_path / 'cache', bad_gap=True)
    library = build_library('monza-2025', cache_root=tmp_path / 'cache', output_root=tmp_path / 'library')
    assert [lap.lap_number for lap in library.drivers[0].laps] == [51]
    assert 'exceeds' in library.drivers[0].rejected_laps[0].reason
    assert library.default_selection is None


@pytest.mark.parametrize('mutation', ['path', 'duplicate_driver', 'duplicate_lap', 'session', 'hash', 'missing_source'])
def test_manifest_rejects_untrusted_identity_and_paths(built_library, mutation):
    _, _, library = built_library
    data = library.model_dump(mode='json')
    if mutation == 'path':
        data['drivers'][0]['laps'][0]['filename'] = '../outside.json.gz'
    elif mutation == 'duplicate_driver':
        data['drivers'].append(data['drivers'][0])
    elif mutation == 'duplicate_lap':
        data['drivers'][0]['laps'].append(data['drivers'][0]['laps'][0])
    elif mutation == 'session':
        data['session_key'] = 9094
    elif mutation == 'hash':
        data['source_hashes']['laps?session_key=9912'] = 'invalid'
    else:
        del data['source_hashes']['car_data?driver_number=1&session_key=9912']
    with pytest.raises(ValidationError):
        LapLibrary.model_validate(data)


def test_lap_bytes_checksum_and_symlink_escape(built_library, tmp_path):
    _, root, library = built_library
    entry = library.drivers[0].laps[0]
    path = root / entry.filename
    payload = path.read_bytes()
    path.write_bytes(payload + b'corrupt')
    with pytest.raises(ValueError, match='checksum'):
        load_lap(root, library, 1, 50)
    path.unlink()
    outside = tmp_path / 'outside.gz'
    outside.write_bytes(payload)
    path.symlink_to(outside)
    with pytest.raises(ValueError, match='escapes'):
        load_lap(root, library, 1, 50)


def test_wrong_source_identity_does_not_replace_published_manifest(built_library):
    cache, root, _ = built_library
    before = (root / 'manifest.json').read_bytes()
    resource = cache / 'laps' / (hashlib.sha256(b'laps?session_key=9912').hexdigest()[:20] + '.json')
    data = json.loads(resource.read_bytes())
    data[0]['meeting_key'] = 999
    resource.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='different session'):
        build_library('monza-2025', cache_root=cache, output_root=root)
    assert (root / 'manifest.json').read_bytes() == before
