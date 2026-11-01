"""Synthetic incident-summary coverage tests. No model, network, or DuckDB required."""
import json

import numpy as np
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


@pytest.mark.parametrize("value", [None, np.nan, pd.NA, "", np.inf, "unknown", "UNKNOWN", "None", "nan"])
def test_unknown_versions_are_not_disagreements(value):
    tables = build_scenario("no_material_discrepancy", 4).tables
    for name in ("batch_forecasts", "live_forecasts"):
        tables[name]["model_version"] = value
    result = summarize(tables)
    assert result["model_version_disagreements_on_matched"] == 0
    assert result["model_version_coverage"] == {"known_pairs": 0, "unknown_pairs": 3972}
    assert result["model_versions"] == {"batch": [], "live": []}
    json.dumps(result, allow_nan=False)


def test_only_observed_identity_pairs_count_as_disagreements():
    tables = build_scenario("no_material_discrepancy", 4).tables
    tables["live_forecasts"].loc[0, "model_version"] = None
    tables["live_forecasts"].loc[1, "model_version"] = "pace-other"
    result = summarize(tables)
    assert result["model_version_disagreements_on_matched"] == 1
    assert result["model_version_coverage"]["unknown_pairs"] == 1


@pytest.mark.parametrize("damage", ["key", "pipeline_column", "pipeline_rows", "table"])
def test_missing_configuration_is_explicit_not_equal(damage):
    tables = build_scenario("no_material_discrepancy", 4).tables
    config = tables["pipeline_config"]
    if damage == "key":
        tables["pipeline_config"] = config.loc[~((config.pipeline == "live") & (config.key == "green_laps_only"))]
    elif damage == "pipeline_column":
        tables["pipeline_config"] = config.drop(columns="pipeline")
    elif damage == "pipeline_rows":
        tables["pipeline_config"] = config.loc[config.pipeline != "live"]
    else:
        del tables["pipeline_config"]
    result = summarize(tables)
    assert result["config_differences"] == []
    assert result["config_coverage"]["unknown_keys"] >= 1
    assert any(row["key"] == "green_laps_only" and row["live"] is None for row in result["config_unknown_values"])


def test_conflicting_config_does_not_choose_a_convenient_value():
    tables = build_scenario("no_material_discrepancy", 4).tables
    tables["pipeline_config"] = pd.concat([tables["pipeline_config"], pd.DataFrame([
        {"pipeline": "live", "key": "green_laps_only", "value": "false"}])], ignore_index=True)
    result = summarize(tables)
    assert result["config_differences"] == []
    assert result["config_conflicts"][0]["values"] == ["false", "true"]
    assert result["config_coverage"]["unknown_keys"] == 1


def test_missing_and_nonfinite_features_are_unknown_not_skew_or_equal():
    tables = build_scenario("no_material_discrepancy", 4).tables
    for name in ("features_batch", "features_live"):
        tables[name]["tyre_age"] = tables[name].tyre_age.astype(object)
        tables[name].loc[0, "tyre_age"] = np.inf
        tables[name].loc[1, "tyre_age"] = np.nan
    tables["features_live"].loc[2, "tyre_age"] = "invalid numeric"
    tables["features_live"] = tables["features_live"].drop(columns="compound")
    result = summarize(tables)["feature_comparison"]
    quality = result["value_coverage_on_matched"]
    assert result["mismatched_values_on_matched"]["tyre_age"] == 0
    assert quality["tyre_age"]["unknown_pairs"] == 3
    assert quality["tyre_age"]["live"] == {"known": 4317, "nonfinite": 1, "missing": 1, "invalid": 1}
    assert quality["compound"]["known_pairs"] == 0
    assert quality["compound"]["unknown_pairs"] == 4320


def test_prediction_gaps_require_two_finite_values():
    tables = build_scenario("no_material_discrepancy", 4).tables
    tables["live_forecasts"].loc[0, "pred_seconds"] = np.inf
    tables["live_forecasts"].loc[1, "pred_seconds"] = np.nan
    result = summarize(tables)
    comparison = result["prediction_comparison_seconds"]
    assert comparison["unknown_pairs"] == 2
    assert comparison["finite_pairs"] == 3970
    assert comparison["max_abs_gap_on_matched"] < 0.01
    assert comparison["input_quality"]["live"]["nonfinite"] == 1
    json.dumps(result, allow_nan=False)
    assert "root_cause" not in result


def test_config_tool_uses_the_same_missing_evidence_policy():
    pytest.importorskip("duckdb")
    from f1_racelab.agents.forecast_debug.tools import ForecastTools

    tables = build_scenario("no_material_discrepancy", 4).tables
    tables["pipeline_config"] = tables["pipeline_config"].drop(columns="pipeline")
    tool = ForecastTools(tables)
    try:
        result = tool.call("config_diff")
        assert result["differences"] == [] and len(result["unknown_values"]) == 3
        assert result["coverage"]["missing_columns"] == ["pipeline"]
    finally:
        tool.close()
