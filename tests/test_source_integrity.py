import json
from pathlib import Path

import pytest

from f1_racelab.data.source_integrity import (
    archive,
    audit_laps,
    audit_telemetry,
    dataset_manifest,
    gated_lap_snapshot,
    publish_dataset_manifest,
    require_research_input,
    verify_dataset_manifest,
)


def sample(laps=(1, 2, 3)):
    return json.dumps([{"session_key": 1, "driver_number": driver, "lap_number": lap,
                        "date_start": f"2025-01-01T00:{lap:02d}:00Z", "lap_duration": 90.0}
                       for driver in (1, 2) for lap in laps]).encode()


def test_late_and_sparse_laps_are_review_not_complete():
    source = sample((4, 8, 11))
    result = audit_laps(source, 1, reference_completed={1: 12, 2: 12})
    assert result["status"] == "review" and result["completeness"] == "unknown"
    assert result["late_start_drivers"] == [1, 2] and result["sparse_key_drivers"] == [1, 2]
    assert result["drivers"][0]["observed_keys_within_reference"] == 3
    with pytest.raises(ValueError, match="requires review"):
        require_research_input(result, acknowledge_unknown="not enough")


def test_no_screening_flags_does_not_prove_completeness():
    result = audit_laps(sample(), 1)
    assert result["status"] == "unknown" and result["completeness"] == "unknown"
    with pytest.raises(ValueError, match="explicit scoped rationale"):
        require_research_input(result)
    require_research_input(result, acknowledge_unknown="Retrospective exploratory population only")


def test_duplicate_nonfinite_and_wrong_session_fail_closed():
    rows = json.loads(sample())
    rows.append(dict(rows[0]))
    rows[0]["lap_duration"] = float("inf")
    rows[1]["session_key"] = 2
    result = audit_laps(json.dumps(rows).encode(), 1)
    assert result["status"] == "broken"
    assert result["duplicate_keys"] == 1 and result["duration_invalid"] == 1 and result["wrong_session_rows"] == 1
    with pytest.raises(ValueError, match="requires review"):
        require_research_input(result, acknowledge_unknown="ignored")


def test_snapshot_is_content_addressed_and_tampering_is_rejected(tmp_path):
    source = sample((4, 8, 11))
    result = audit_laps(source, 1)
    record = archive(tmp_path, source, provider="OpenF1", endpoint="laps", parameters={"session_key": 1},
                     retrieved_at_utc=None, report=result)
    assert record["retrieved_at_utc"] is None and "/quarantine/" in record["snapshot"]
    assert archive(tmp_path, source, provider="OpenF1", endpoint="laps", parameters={"session_key": 1},
                   retrieved_at_utc=None, report=result)["snapshot"] == record["snapshot"]
    snapshot = tmp_path / "quarantine" / (result["content_sha256"] + ".json")
    snapshot.chmod(0o644)
    snapshot.write_bytes(b"altered")
    with pytest.raises(ValueError, match="checksum mismatch"):
        archive(tmp_path, source, provider="OpenF1", endpoint="laps", parameters={"session_key": 1},
                retrieved_at_utc=None, report=result)


def test_failed_research_gate_keeps_quarantine_and_legacy_timestamp_unknown(tmp_path):
    with pytest.raises(ValueError, match="requires review"):
        gated_lap_snapshot(tmp_path, sample((4, 8, 11)), 1, retrieved_at_utc=None)
    assert len(list((tmp_path / "quarantine").glob("*.json"))) == 1
    record = json.loads(next((tmp_path / "records").glob("*.json")).read_text())
    assert record["retrieved_at_utc"] is None and record["audit"]["status"] == "review"


def test_verified_client_preserves_invalid_cache_and_quarantines_copy(tmp_path):
    import hashlib

    from f1_racelab.data.openf1_qualifying import OpenF1Client

    cache = tmp_path / "cache"
    path = cache / "laps" / (hashlib.sha256(b"laps?session_key=1").hexdigest()[:20] + ".json")
    path.parent.mkdir(parents=True)
    path.write_bytes(b"bad json")
    with OpenF1Client(cache, offline=True) as client, pytest.raises(ValueError, match="original preserved"):
        client.get_verified_laps(1, snapshot_store=tmp_path / "evidence")
    assert path.read_bytes() == b"bad json"
    assert len(list((tmp_path / "evidence/quarantine").glob("*.json"))) == 1


def test_telemetry_reports_missing_channels_gaps_and_preserves_source_values():
    source = json.dumps([
        {"session_key": 1, "driver_number": 1, "date": "2025-01-01T00:00:00Z", "speed": 123, "throttle": 103},
        {"session_key": 1, "driver_number": 1, "date": "2025-01-01T00:00:02Z", "speed": 100, "throttle": None},
    ]).encode()
    result = audit_telemetry(source, 1)
    assert result["status"] == "review" and result["gaps_above_threshold"] == 1
    assert result["channels"]["throttle"]["observed_max"] == 103
    assert result["channels"]["drs"]["column_present"] is False


def test_dataset_identity_binds_source_transform_cutoff_and_output(tmp_path):
    payload = sample()
    source = gated_lap_snapshot(tmp_path / "source", payload, 1, retrieved_at_utc=None,
                                acknowledge_unknown="Exploratory cohort; no completeness guarantee")
    record = json.loads(Path(source["record"]).read_text())
    assert record["gate_decision"]["accepted"] and record["gate_decision"]["unknown_rationale"]
    output = tmp_path / "dataset.parquet"
    output.write_bytes(b"synthetic fixture")
    args = {"transform_sha256": "a" * 64, "feature_contract": {"speed": "km/h"},
            "cutoff": "lap start +20s", "unknown_rationale": "Exploratory cohort"}
    first = dataset_manifest([source], output, **args)
    assert first["dataset_id"] == dataset_manifest([source], output, **args)["dataset_id"]
    saved = publish_dataset_manifest(tmp_path, first)
    assert publish_dataset_manifest(tmp_path, first) == saved
    verify_dataset_manifest(tmp_path / "source", first, output)
    with pytest.raises(ValueError, match="identity"):
        publish_dataset_manifest(tmp_path, {**first, "cutoff": "tampered"})
    assert first["dataset_id"] != dataset_manifest([source], output, **{**args, "cutoff": "lap start +10s"})["dataset_id"]
    output.write_bytes(b"different fixture")
    assert first["dataset_id"] != dataset_manifest([source], output, **args)["dataset_id"]
    with pytest.raises(ValueError, match="output checksum"):
        verify_dataset_manifest(tmp_path / "source", first, output)


def test_naive_timestamps_are_not_silently_treated_as_utc():
    source = json.loads(sample())
    source[0]["date_start"] = "2025-01-01T00:00:00"
    result = audit_laps(json.dumps(source).encode(), 1)
    assert result["status"] == "broken" and result["invalid_timestamps"] == 1


def test_normalized_duplicate_keys_and_implausible_telemetry_are_reported():
    rows = json.loads(sample())
    rows.append({**rows[0], "driver_number": "1", "lap_number": "1"})
    assert audit_laps(json.dumps(rows).encode(), 1)["duplicate_keys"] == 1
    telemetry = [{"session_key": 1, "driver_number": 1, "date": "2025-01-01T00:00:00Z", "speed": -1}]
    result = audit_telemetry(json.dumps(telemetry).encode(), 1)
    assert result["status"] == "review" and result["negative_speed_or_rpm_values"] == 1


def test_large_lap_numbers_do_not_allocate_a_range():
    rows = json.loads(sample((1, 2)))
    rows[1]["lap_number"] = 10**9
    assert audit_laps(json.dumps(rows).encode(), 1)["status"] == "review"


def test_reference_shortfall_cannot_be_released_by_omitting_reference(tmp_path):
    payload = sample()
    report = audit_laps(payload, 1, reference_completed={1: 4, 2: 3})
    assert report["status"] == "review" and report["reference_coverage_shortfall_drivers"] == [1]
    source = archive(tmp_path, payload, provider="OpenF1", endpoint="laps", parameters={"session_key": 1},
                     retrieved_at_utc=None, report=report)
    output = tmp_path / "dataset"
    output.write_bytes(b"synthetic")
    with pytest.raises(ValueError, match="requires review"):
        dataset_manifest([source], output, transform_sha256="a" * 64, feature_contract={"lap": "count"},
                         cutoff="lap start", unknown_rationale="Reference cannot be ignored")
