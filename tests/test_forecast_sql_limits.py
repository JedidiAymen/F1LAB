"""Adversarial SQL resource checks; all data is synthetic and in memory."""
import pytest

pytest.importorskip("duckdb")

from f1_racelab.agents.forecast_debug.tools import ForecastTools, ToolError, guard_sql


def test_query_size_and_result_bounds():
    with pytest.raises(ToolError, match="12000"):
        guard_sql("select " + "1" * 12000)
    tools = ForecastTools({})
    try:
        result = tools.run_sql("SELECT * FROM range(1000000000)")
        assert len(result["rows"]) == 50 and result["truncated"]
        assert result["row_count"] == 51 and not result["row_count_is_exact"]
        assert tools.run_sql("SELECT 1 AS n")["row_count_is_exact"]
        query = "SELECT " + ",".join(f"{i} as c{i}" for i in range(33))
        assert "error" in tools.call("run_sql", {"query": query})
        assert "error" in tools.call("run_sql", {"query": "select 1 as x, 2 as x"})
    finally:
        tools.close()


def test_timeout_cancels_query_and_connection_recovers():
    tools = ForecastTools({}, timeout_seconds=0.05)
    try:
        result = tools.call("run_sql", {"query": "SELECT sum(sqrt(i)) FROM range(100000000000) t(i)"})
        assert "execution limit" in result["error"]
        assert tools.run_sql("SELECT 42 as answer")["rows"] == [{"answer": 42}]
    finally:
        tools.close()


@pytest.mark.parametrize("query", [
    "select * from read_text('/etc/passwd')",
    "select * from read_parquet('https://example.com/private.parquet')",
    "select * from glob('/tmp/*')",
    "WITH x AS (SELECT 1) DELETE FROM x",
    "SELECT 1; /* conceal */ SELECT 2",
])
def test_no_files_network_or_mutation(query):
    tools = ForecastTools({})
    try:
        assert "error" in tools.call("run_sql", {"query": query})
    finally:
        tools.close()
