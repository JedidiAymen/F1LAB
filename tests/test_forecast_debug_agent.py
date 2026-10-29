"""Forecast-debugging agent: scenarios, read-only tools, agent loop and evaluation harness (no LLM, no network)."""
import json

import pytest

pytest.importorskip("duckdb")

from f1_racelab.agents.forecast_debug import evaluate as ev
from f1_racelab.agents.forecast_debug.agent import (
    run_agent,
    system_prompt,
)
from f1_racelab.agents.forecast_debug.llm import (
    ScriptedChat,
    extract_json,
)
from f1_racelab.agents.forecast_debug.reference import diagnose
from f1_racelab.agents.forecast_debug.scenarios import (
    LABELS,
    build_scenario,
)
from f1_racelab.agents.forecast_debug.tools import (
    ForecastTools,
    ToolError,
    guard_sql,
)


@pytest.mark.parametrize("label", LABELS)
def test_reference_diagnoser_solves_every_planted_cause(label):
    for seed in (1, 2, 3):
        result = diagnose(ForecastTools(build_scenario(label, seed).tables))
        assert result.root_cause == label and result.evidence


def test_ground_truth_never_appears_in_tables():
    for label in LABELS:
        tables = build_scenario(label, 1).tables
        text = " ".join(df.to_csv(index=False) for df in tables.values())
        assert label not in text


def test_scenarios_are_reproducible_and_seed_dependent():
    a, b, c = (build_scenario("missing_live_data", s) for s in (4, 4, 5))
    assert a.notes == b.notes and a.tables["live_forecasts"].equals(b.tables["live_forecasts"])
    assert len(a.tables["live_forecasts"]) != len(c.tables["live_forecasts"]) or a.notes != c.notes


@pytest.mark.parametrize("query", [
    "DROP TABLE laps", "select 1; delete from laps", "CREATE TABLE x AS SELECT 1", "COPY laps TO 'x.csv'",
    "PRAGMA version", "ATTACH 'x.db'", "", "  -- only a comment"])
def test_sql_guard_rejects_non_read_queries(query):
    with pytest.raises(ToolError):
        guard_sql(query)


def test_sql_guard_accepts_select_and_cte():
    assert guard_sql("WITH a AS (SELECT 1 AS x) SELECT x FROM a;") .startswith("WITH")
    assert guard_sql("/* note */ select * from laps").lower().startswith("select")


def test_tools_block_file_access_and_report_errors():
    tools = ForecastTools(build_scenario("no_material_discrepancy", 1).tables)
    assert "error" in tools.call("run_sql", {"query": "SELECT * FROM read_csv('/etc/passwd')"})
    assert "error" in tools.call("describe_table", {"name": "secrets"})
    assert "error" in tools.call("no_such_tool")
    assert "error" in tools.call("compare_forecasts", {"group_by": "1; drop"})
    rows = tools.call("run_sql", {"query": "SELECT * FROM laps"})
    assert rows["truncated"] and len(rows["rows"]) == 50


def test_compare_forecasts_shows_the_planted_signal():
    clean = ForecastTools(build_scenario("no_material_discrepancy", 2).tables).call("compare_forecasts")["rows"]
    shifted = ForecastTools(build_scenario("regime_shift", 2).tables).call("compare_forecasts")["rows"]
    assert all(abs(r["batch_bias_green"]) < 0.1 for r in clean)
    assert shifted[-1]["year"] == 2026 and shifted[-1]["batch_bias_green"] > 0.2
    assert abs(shifted[-1]["mean_abs_live_minus_batch"]) < 0.01  # batch and live agree; actuals moved


def test_extract_json_handles_think_blocks_fences_and_noise():
    assert extract_json('<think>{"x": 1}</think>```json\n{"action": "list_tables"}\n```') == {
        "action": "list_tables"}
    assert extract_json('noise {"a": "brace } in string", "b": {"c": 2}} tail') == {
        "a": "brace } in string", "b": {"c": 2}}
    assert extract_json("no json here") is None


def test_agent_loop_cites_only_evidence_it_produced():
    tools = ForecastTools(build_scenario("stale_model_version", 1).tables)
    model = ScriptedChat([
        {"thought": "check versions", "action": "run_sql",
         "args": {"query": "SELECT DISTINCT model_version FROM live_forecasts"}},
        "this is not json",
        {"final": {"root_cause": "stale_model_version", "evidence": ["t1", "t9"], "explanation": "v1 live",
                   "confidence": 0.8}},
    ])
    result = run_agent(model, tools)
    assert result.root_cause == "stale_model_version"
    assert result.evidence == ["t1"]  # t9 was never produced
    assert result.invalid_replies == 1 and result.steps == 3
    observation = model.seen[1][-1]["content"]
    assert observation.startswith("Observation t1:") and "pace-v1" in observation


def test_agent_rejects_unknown_labels_and_stops_at_budget():
    tools = ForecastTools(build_scenario("no_material_discrepancy", 1).tables)
    bad = run_agent(ScriptedChat([{"final": {"root_cause": "gremlins", "evidence": []}}]), tools)
    assert bad.root_cause == "invalid_label"
    looping = run_agent(ScriptedChat([{"action": "list_tables", "args": {}}] * 5), tools, max_steps=3)
    assert looping.root_cause == "undetermined" and looping.steps == 3


def test_system_prompt_lists_every_tool_and_label():
    prompt = system_prompt()
    assert all(label in prompt for label in LABELS)
    assert all(spec["name"] in prompt for spec in ForecastTools.specs())


def test_evaluation_scores_and_writes_reports(tmp_path):
    result = ev.evaluate(diagnose, labels=["unit_mismatch", "feature_skew"], seeds=[1])
    assert result["summary"]["accuracy"] == 1.0 and result["summary"]["correct_and_grounded"] == 1.0
    always_wrong = ev.evaluate(lambda tools: run_agent(ScriptedChat([
        {"final": {"root_cause": "regime_shift", "evidence": []}}]), tools), labels=["unit_mismatch"], seeds=[1])
    assert always_wrong["summary"]["accuracy"] == 0.0 and always_wrong["summary"]["grounded_rate"] == 0.0
    target = ev.write("reference", result, tmp_path)
    assert json.loads((target / "results.json").read_text())["summary"]["cases"] == 2
    assert "Root-cause accuracy | 100.0%" in (target / "report.md").read_text()
    assert len((target / "traces.jsonl").read_text().splitlines()) == 2
