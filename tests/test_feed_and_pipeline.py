import pandas as pd
import pytest

from f1_racelab.engines import feed_check, pipeline, run


def _good():
    return pd.DataFrame({"race_id": ["a"] * 4, "year": 2025, "driver_number": [1, 1, 2, 2], "lap": [1, 2, 1, 2],
                         "anchor_seconds": 90.0, "next_lap_seconds": 91.0, "delta_seconds": 1.0,
                         "compound_next": "HARD", "tyre_age_next": 3.0, "eligible_green_next": True,
                         "regime_next": "green"})


def _errors(df):
    return {f["rule"] for f in feed_check.check(df) if f["severity"] == "error"}


def test_clean_feed_has_no_errors():
    assert _errors(_good()) == set()


def test_feed_check_catches_each_contract_violation():
    assert "required_columns" in _errors(_good().drop(columns=["lap"]))
    assert "compound_mapping" in _errors(_good().assign(compound_next="PURPLE"))
    assert "regime_mapping" in _errors(_good().assign(regime_next="rain"))
    assert "unique_key" in _errors(pd.concat([_good(), _good()]))
    assert "completeness" in _errors(_good().assign(anchor_seconds=None))
    assert "target_consistency" in _errors(_good().assign(delta_seconds=5.0))
    assert "plausibility" in _errors(_good().assign(next_lap_seconds=5.0, delta_seconds=-85.0))
    red = _good().assign(next_lap_seconds=900.0, delta_seconds=810.0, eligible_green_next=False, regime_next="red")
    assert _errors(red) == set()  # red-flag laps are a warning, not an error
    assert any(f["rule"] == "plausibility_non_green" for f in feed_check.check(red))


def test_pipeline_runs_declared_engines_and_blocks_bad_feed(tmp_path):
    pytest.importorskip("duckdb")
    manifest = pipeline.execute(run.sample_frame(), out_dir=tmp_path, check_feed=False)
    assert {s["step"] for s in manifest["steps"]} == {"race_summary", "compound_wear"}
    assert all(s["engine_used"] == s["declared_engine"] for s in manifest["steps"]) and (tmp_path / "manifest.json").exists()
    with pytest.raises(ValueError, match="feed check failed"):
        pipeline.execute(_good().assign(compound_next="PURPLE"), out_dir=tmp_path)
