"""Synthetic bookkeeping and real-source worker isolation; no model/network required."""
import fcntl

import pytest

from f1_racelab.agents.forecast_debug.paired import (
    paired_summary,
    run,
    validate_case,
    write_json,
)


def case(arm, label="feature_skew", seed=1, correct=False, **kwargs):
    return {"scenario_id": f"{label}-s{seed}", "expected": label, "seed": seed, "arm": arm,
            "predicted": label if correct else "no_material_discrepancy", "correct": correct, "seconds": 1.0,
            "status": "ok", "tool_calls": 2, "tool_errors": 0, "false_citation_ids": 0,
            "input_fingerprints": {"table": "abc"}, "table_fingerprints": {"table": "abc"},
            "protocol_sha256": "fixed", **kwargs}


def test_pairing_bootstraps_families_and_reports_false_clean_diagnoses():
    rows = [case(arm, label, seed, correct=arm == "candidate") for label in ("feature_skew", "regime_shift")
            for seed in (1, 4) for arm in ("baseline", "candidate")]
    report = paired_summary(rows)
    assert report["paired_accuracy_delta"] == 1
    assert report["family_bootstrap_95"] == [1, 1]
    assert report["fault_families"] == 2
    assert report["arms"]["baseline"]["false_no_discrepancy"] == 4
    assert report["arms"]["candidate"]["accuracy"] == 1


def test_failed_worker_is_not_dropped_or_falsely_assigned_zero_tool_usage():
    report = paired_summary([case("baseline", correct=True),
                             case("candidate", status="worker_failed", predicted="undetermined", tool_calls=None)])
    assert report["arms"]["candidate"]["cases"] == 1
    assert report["arms"]["candidate"]["accuracy"] == 0
    assert report["arms"]["candidate"]["failed_workers"] == 1
    assert report["arms"]["candidate"]["unknown_tool_measurements"] == 1
    assert report["paired_accuracy_delta"] == -1


def test_missing_duplicate_or_different_pair_fails():
    with pytest.raises(ValueError, match="exactly one"):
        paired_summary([case("baseline")])
    with pytest.raises(ValueError, match="Duplicate"):
        paired_summary([case("baseline"), case("baseline")])
    with pytest.raises(ValueError, match="fingerprints"):
        paired_summary([case("baseline"), case("candidate", input_fingerprints={"table": "changed"})])


def test_case_validation_rejects_changed_identity_protocol_and_tables():
    params = {"label": "feature_skew", "seed": 1, "arm": "candidate", "protocol_sha256": "fixed"}
    validate_case(case("candidate"), params, {"table": "abc"})
    for change in ({"seed": 4}, {"arm": "baseline"}, {"protocol_sha256": "other"},
                   {"input_fingerprints": {}}, {"table_fingerprints": {}}):
        altered = {**case("candidate"), **change}
        with pytest.raises(ValueError):
            validate_case(altered, params, {"table": "abc"})


def test_checkpoint_json_is_atomic_and_rejects_nonfinite_values(tmp_path):
    path = tmp_path / "case.json"
    write_json(path, {"passed": True})
    assert path.read_text().strip().endswith("}") and not list(tmp_path.glob("*.tmp"))
    with pytest.raises(ValueError):
        write_json(path, {"bad": float("nan")})
    assert '"passed": true' in path.read_text()


def test_concurrent_writer_is_rejected_before_model_or_source_access(tmp_path):
    with (tmp_path / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match="Another evaluator"):
            run(tmp_path, tmp_path, tmp_path)
