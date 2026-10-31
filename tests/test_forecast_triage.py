"""Synthetic incident-summary coverage tests. No model, network, or DuckDB required."""
import json

import pandas as pd
import pytest

from f1_racelab.agents.forecast_debug.scenarios import LABELS, build_scenario
from f1_racelab.agents.forecast_debug.triage import summarize


@pytest.mark.parametrize("label", LABELS)
def test_incident_checks_emit_serializable_evidence_without_leaking_label(label):
    tables = build_scenario(label, 2).tables
    before = {name: frame.copy(deep=True) for name, frame in tables.items()}
    report = summarize(tables)
    json.dumps(report, allow_nan=False)
    assert "root_cause" not in report
    assert report["forecast_coverage"]["batch_rows"] > 0
    assert report["batch_bias_on_observed_green_seconds_by_year"]
    for name, frame in tables.items():
        pd.testing.assert_frame_equal(frame, before[name])

    if label == "stale_model_version":
        assert report["model_version_disagreements_on_matched"] > 0
    elif label == "feature_skew":
        assert report["feature_comparison"]["mismatched_values_on_matched"]["tyre_age"] > 0
    elif label == "missing_live_data":
        assert report["forecast_coverage"]["batch_only_keys"] > 0
    elif label == "unit_mismatch":
        assert report["prediction_comparison_seconds"]["max_abs_live_value"] > 1000
    elif label == "config_drift":
        assert any(row["key"] == "green_laps_only" for row in report["config_differences"])
    elif label == "lap_misalignment":
        assert report["forecast_coverage"]["batch_only_keys"] > 0
        assert report["possible_previous_lap_alignment_races"]
    elif label == "regime_shift":
        assert abs(report["batch_bias_on_observed_green_seconds_by_year"]["2026"]) > 0.15
    else:
        assert label == "no_material_discrepancy"
        assert report["config_differences"] == []
        assert report["model_version_disagreements_on_matched"] == 0
        assert report["forecast_coverage"]["batch_only_keys"] == 0
        assert report["feature_comparison"]["mismatched_values_on_matched"]["tyre_age"] == 0
        assert abs(report["batch_bias_on_observed_green_seconds_by_year"]["2026"]) < 0.15


def test_reject_duplicate_forecast_keys():
    tables = build_scenario("no_material_discrepancy", 1).tables
    batch = tables["batch_forecasts"]
    tables["batch_forecasts"] = pd.concat([batch, batch.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="not unique"):
        summarize(tables)


def test_agent_tool_exposes_same_structured_signals():
    pytest.importorskip("duckdb")
    from f1_racelab.agents.forecast_debug.tools import ForecastTools

    tables = build_scenario("stale_model_version", 3).tables
    tool = ForecastTools(tables)
    try:
        result = tool.call("incident_checks")
        assert result["model_version_disagreements_on_matched"] > 0
        assert result == summarize(tables)
        assert "incident_checks" in {spec["name"] for spec in tool.specs()}
    finally:
        tool.close()
