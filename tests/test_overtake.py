import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

from f1_racelab.ml.overtake import benchmark, dataset


def _frame(swap=True, pit_on_l1=False, neutral=0):
    """Two drivers, laps 1-3. Driver 2 starts 0.5 s behind driver 1 and passes during lap 2 if `swap`."""
    rows = []
    for lap in (1, 2, 3):
        for driver, base in ((1, 10.0), (2, 10.5)):
            gap = base if lap == 1 else (base if not swap else (10.6 if driver == 1 else 10.2))
            rows.append({"race_id": "r", "year": 2025, "event": "x", "circuit": "c", "race_start": pd.Timestamp("2025-03-01"),
                         "cutoff": pd.Timestamp("2025-03-01") + pd.Timedelta(seconds=lap * 100 + (0 if driver == 1 else 1)),
                         "lap": lap, "driver_number": driver, "gap_to_leader": gap,
                         "interval_ahead": 0.5 if driver == 2 else 0.0, "anchor_seconds": 90.0, "last1": 0.0,
                         "tyre_age_next": 5.0, "compound_next": "MEDIUM", "laps_remaining": 40.0,
                         "next_is_in_lap": pit_on_l1 and lap == 1 and driver == 1, "next_is_out_lap": False,
                         "neutral_in_last3": neutral, "yellow_in_last1": 0, "regime_next": "green",
                         "intervals_age_s": 0.1})
    return pd.DataFrame(rows)


def test_swap_is_labelled_positive_and_no_swap_negative():
    pairs = dataset.build(_frame(swap=True))
    row = pairs[(pairs.lap == 1) & (pairs.driver_number == 2)]
    assert len(row) == 1 and int(row.overtake.iloc[0]) == 1
    flat = dataset.build(_frame(swap=False))
    assert flat[(flat.lap == 1) & (flat.driver_number == 2)].overtake.iloc[0] == 0


def test_pit_involved_and_neutralised_pairs_are_dropped_not_labelled_negative():
    assert dataset.build(_frame(pit_on_l1=True)).query("lap == 1").empty
    assert dataset.build(_frame(neutral=1)).empty


def test_future_leader_cutoff_and_nonconsecutive_next_lap_are_not_used():
    frame = _frame()
    frame.loc[(frame.driver_number == 1) & (frame.lap == 1), 'cutoff'] += pd.Timedelta(seconds=2)
    assert dataset.build(frame).query('lap == 1').empty
    missing_leader_lap = _frame().query('not (driver_number == 1 and lap == 2)')
    assert dataset.build(missing_leader_lap).query('lap == 1').empty


def test_missing_cutoff_and_duplicate_source_keys_fail_closed():
    import pytest

    frame = _frame()
    frame.loc[0, 'cutoff'] = pd.NaT
    with pytest.raises(ValueError, match='valid cutoff'):
        dataset.build(frame)
    with pytest.raises(ValueError, match='Duplicate'):
        dataset.build(pd.concat([_frame(), _frame().iloc[[0]]], ignore_index=True))


def test_cutoff_audit_finds_a_late_leader_in_previously_scored_race():
    spec = importlib.util.spec_from_file_location('overtake_cutoff_audit', Path(__file__).parents[1] / 'scripts/audit_overtake_cutoffs.py')
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = _frame()
    pairs = dataset.build(original)
    altered = original.copy()
    altered.loc[(altered.driver_number == 1) & (altered.lap == 1), 'cutoff'] += pd.Timedelta(seconds=2)
    result = module.audit(altered, pairs, pd.DataFrame({'race_id': ['r']}))
    assert result['late_leader_rows'] == result['late_leader_rows_in_scored_races'] == 1
    assert result['removed_saved_rows'] == 1 and result['nonconsecutive_next_rows'] == 0


def test_circuit_prior_rate_uses_only_earlier_races():
    pairs = pd.DataFrame({"circuit": ["c"] * 3, "race_id": ["a", "b", "c"], "overtake": [1, 0, 1],
                          "race_start": pd.to_datetime(["2024-01-01", "2024-06-01", "2025-01-01"])})
    prior = dataset._prior_circuit_rate(pairs)
    assert np.isnan(prior.iloc[0]) and prior.iloc[1] == 1.0 and prior.iloc[2] == 0.5


def test_circuit_prior_excludes_all_races_with_equal_start_times():
    pairs = pd.DataFrame({'circuit': ['c'] * 3, 'race_id': ['a', 'b', 'c'], 'overtake': [1, 0, 1],
                          'race_start': pd.to_datetime(['2024-01-01', '2024-01-01', '2025-01-01'])})
    prior = dataset._prior_circuit_rate(pairs)
    assert np.isnan(prior.iloc[0]) and np.isnan(prior.iloc[1]) and prior.iloc[2] == 0.5


def test_ece_zero_for_perfectly_calibrated_and_positive_otherwise():
    y = np.array([0, 1] * 50)
    assert benchmark.ece(y, np.full(100, 0.5)) < 1e-9
    assert benchmark.ece(y, np.full(100, 0.9)) > 0.3


def test_paired_scoring_rejects_reordered_pairs_even_with_same_labels():
    import pytest

    base = pd.DataFrame({'model': ['logistic_gap'] * 4, 'race_id': ['r'] * 4, 'year': [2025] * 4,
                         'lap': [1, 2, 3, 4], 'driver_number': [1] * 4, 'a_driver_number': [2] * 4,
                         'y': [0, 0, 1, 1], 'p': [0.2, 0.3, 0.7, 0.8]})
    other = base.iloc[[1, 0, 2, 3]].copy().assign(model='constant_rate')
    with pytest.raises(ValueError, match='ordered pair identities'):
        benchmark.summarise(pd.concat([base, other], ignore_index=True))


def test_summary_endpoint_503_without_results(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from f1_racelab.api import create_app
    monkeypatch.setattr(benchmark, "OUT", tmp_path)
    response = TestClient(create_app()).get("/api/v1/overtake/summary")
    assert response.status_code == 503 and "Run:" in response.json()["detail"]


def test_bundled_audit_is_exposed_and_checksum_protected(tmp_path):
    import shutil

    import pytest
    from fastapi.testclient import TestClient

    from f1_racelab.api import create_app
    from f1_racelab.ml.overtake import audit_service

    response = TestClient(create_app()).get('/api/v1/overtake/cutoff-audit')
    assert response.status_code == 200
    assert response.json()['late_leader_rows'] == 5
    shutil.copytree(audit_service.ROOT, tmp_path / 'audit')
    (tmp_path / 'audit/report.json').write_text('{}')
    with pytest.raises(ValueError, match='checksum'):
        audit_service.load(tmp_path / 'audit')


def test_research_commands_preserve_existing_artifacts(monkeypatch, tmp_path):
    import pytest

    pairs = tmp_path / 'pairs.parquet'
    pairs.write_bytes(b'old research bytes')
    monkeypatch.setattr('sys.argv', ['dataset', '--out', str(tmp_path)])
    with pytest.raises(FileExistsError, match='new --out'):
        dataset.main()
    assert pairs.read_bytes() == b'old research bytes'
    summary = tmp_path / 'summary.json'
    summary.write_text('old metrics')
    monkeypatch.setattr('sys.argv', ['benchmark', '--pairs', str(pairs), '--out', str(tmp_path)])
    with pytest.raises(FileExistsError, match='new --out'):
        benchmark.main()
    assert summary.read_text() == 'old metrics'
