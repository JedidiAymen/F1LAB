"""Read-only investigation tools over a scenario's tables, backed by DuckDB.

Every tool returns a JSON-serialisable dict. ``run_sql`` accepts a single SELECT/WITH statement only, runs on an
in-memory DuckDB connection with external file access disabled, and truncates results, so an agent can explore but
never modify data or reach the filesystem or network.
"""
from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable
from typing import Any

import pandas as pd

MAX_ROWS = 50
MAX_QUERY_CHARS = 12_000
MAX_COLUMNS = 32
MAX_VALUE_CHARS = 1000
_WRITE = re.compile(
    r"\b(insert|update|delete|merge|create|drop|alter|truncate|copy|attach|detach|install|load|pragma|set|reset|"
    r"export|import|call|checkpoint|vacuum|grant|revoke|use)\b", re.IGNORECASE)
_COMMENTS = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)
GROUPINGS = {
    "year": "a.year",
    "race_id": "race_id",
    "driver": "driver",
    "compound": "f.compound",
    "tyre_age_bucket": "CAST(FLOOR(f.tyre_age / 10) * 10 AS INTEGER)",
}


class ToolError(ValueError):
    """A tool was called with invalid arguments; the message is shown to the agent."""


def guard_sql(query: str) -> str:
    """Return the query if it is one read-only SELECT/WITH statement, else raise ``ToolError``."""
    if not isinstance(query, str) or len(query) > MAX_QUERY_CHARS:
        raise ToolError(f"query must be text of at most {MAX_QUERY_CHARS} characters")
    text = _COMMENTS.sub(" ", query).strip().rstrip(";").strip()
    if not text:
        raise ToolError("empty query")
    if ";" in text:
        raise ToolError("only one statement is allowed")
    if not re.match(r"(?is)^(select|with)\b", text):
        raise ToolError("only SELECT or WITH queries are allowed")
    match = _WRITE.search(text)
    if match:
        raise ToolError(f"read-only tools: keyword {match.group(0).upper()!r} is not allowed")
    return text


def _records(df: pd.DataFrame, limit: int = MAX_ROWS) -> dict[str, Any]:
    clipped = df.head(limit)
    rows = [{k: (None if pd.isna(v) else (round(v, 4) if isinstance(v, float) else v)) for k, v in r.items()}
            for r in clipped.to_dict(orient="records")]
    return {"columns": list(df.columns), "rows": rows, "row_count": len(df), "truncated": len(df) > limit}


class ForecastTools:
    def __init__(self, tables: dict[str, pd.DataFrame], *, timeout_seconds: float = 2.0) -> None:
        import duckdb

        if not 0 < timeout_seconds <= 10:
            raise ValueError("SQL timeout must be in (0, 10] seconds")
        self._timeout = timeout_seconds
        self._lock = threading.Lock()
        self._tables = tables
        self._con = duckdb.connect(":memory:", config={
            "threads": 1, "memory_limit": "128MB", "max_temp_directory_size": "0B",
            "enable_external_access": False, "autoload_known_extensions": False,
            "autoinstall_known_extensions": False,
        })
        for name, frame in tables.items():
            self._con.register(name, frame)
        self._con.execute("SET lock_configuration = true")
        self._handlers: dict[str, Callable[..., dict[str, Any]]] = {
            "list_tables": self.list_tables,
            "describe_table": self.describe_table,
            "run_sql": self.run_sql,
            "compare_forecasts": self.compare_forecasts,
            "config_diff": self.config_diff,
        }

    def close(self) -> None:
        """Release this scenario's registered frames and engine resources."""
        with self._lock:
            self._con.close()

    @staticmethod
    def specs() -> list[dict[str, Any]]:
        return [
            {"name": "list_tables", "args": {}, "description": "Table names, row counts and columns."},
            {"name": "describe_table", "args": {"name": "table name"},
             "description": "Column types, null counts and 5 sample rows of one table."},
            {"name": "run_sql", "args": {"query": "one DuckDB SELECT/WITH statement"},
             "description": f"Read-only SQL over all tables; at most {MAX_ROWS} rows returned."},
            {"name": "compare_forecasts", "args": {"group_by": "|".join(GROUPINGS)},
             "description": "Batch vs live per group: row counts, matched keys, mean |live-batch| and each "
                            "pipeline's bias against actual lap times."},
            {"name": "config_diff", "args": {}, "description": "Configuration keys whose values differ between "
                                                                "the batch and live pipelines."},
        ]

    def call(self, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        handler = self._handlers.get(name)
        if handler is None:
            return {"error": f"unknown tool {name!r}; available: {sorted(self._handlers)}"}
        try:
            return handler(**(args or {}))
        except ToolError as exc:
            return {"error": str(exc)}
        except TypeError as exc:
            return {"error": f"bad arguments for {name}: {exc}"}
        except Exception as exc:  # noqa: BLE001 - surface engine errors (e.g. SQL syntax) to the agent
            return {"error": f"{type(exc).__name__}: {exc}"}

    def list_tables(self) -> dict[str, Any]:
        return {"tables": [{"name": n, "rows": len(df), "columns": list(df.columns)}
                           for n, df in self._tables.items()]}

    def describe_table(self, name: str) -> dict[str, Any]:
        if name not in self._tables:
            raise ToolError(f"unknown table {name!r}")
        df = self._tables[name]
        return {"name": name, "rows": len(df),
                "columns": [{"name": c, "dtype": str(df[c].dtype), "nulls": int(df[c].isna().sum())}
                            for c in df.columns],
                "sample": _records(df, 5)["rows"]}

    def run_sql(self, query: str) -> dict[str, Any]:
        """Bound execution and fetching, not just the returned DataFrame's head.

        Engine cancellation is cooperative; this is defense in depth for a local
        read-only agent, not an OS sandbox for arbitrary hostile tenants.
        """
        import duckdb

        text = guard_sql(query)
        with self._lock:
            started = time.perf_counter()
            timer = threading.Timer(self._timeout, self._con.interrupt)
            timer.daemon = True
            timer.start()
            try:
                statements = self._con.extract_statements(text)
                if len(statements) != 1 or statements[0].type != duckdb.StatementType.SELECT:
                    raise ToolError("parser requires exactly one SELECT statement")
                cursor = self._con.execute(text)
                columns = [column[0] for column in cursor.description]
                if len(columns) > MAX_COLUMNS:
                    raise ToolError(f"at most {MAX_COLUMNS} result columns are allowed")
                if len(set(columns)) != len(columns):
                    raise ToolError("result columns must have unique names; use aliases")
                fetched = cursor.fetchmany(MAX_ROWS + 1)
                result = _records(pd.DataFrame(fetched, columns=columns))
                result["row_count_is_exact"] = len(fetched) <= MAX_ROWS
                result["rows"] = [
                    {key: value[:MAX_VALUE_CHARS] if isinstance(value, str) else value for key, value in row.items()}
                    for row in result["rows"]
                ]
                return {"query": text, **result, "elapsed_seconds": round(time.perf_counter() - started, 6)}
            except duckdb.InterruptException as exc:
                raise ToolError(f"SQL exceeded {self._timeout:g} second execution limit") from exc
            finally:
                timer.cancel()
                timer.join()  # No late interrupt may affect the following query.

    def compare_forecasts(self, group_by: str = "year") -> dict[str, Any]:
        if group_by not in GROUPINGS:
            raise ToolError(f"group_by must be one of {sorted(GROUPINGS)}")
        key = GROUPINGS[group_by]
        sql = f"""
            WITH j AS (
                SELECT COALESCE(b.race_id, l.race_id) AS race_id, COALESCE(b.driver, l.driver) AS driver,
                       COALESCE(b.lap, l.lap) AS lap, b.pred_seconds AS batch_pred, l.pred_seconds AS live_pred
                FROM batch_forecasts b
                FULL OUTER JOIN live_forecasts l ON b.race_id = l.race_id AND b.driver = l.driver AND b.lap = l.lap)
            SELECT {key} AS {group_by},
                   COUNT(batch_pred) AS batch_rows,
                   COUNT(live_pred) AS live_rows,
                   COUNT(*) FILTER (WHERE batch_pred IS NOT NULL AND live_pred IS NOT NULL) AS matched_rows,
                   AVG(ABS(live_pred - batch_pred)) AS mean_abs_live_minus_batch,
                   AVG(batch_pred - a.actual_seconds) FILTER (WHERE a.eligible_green) AS batch_bias_green,
                   AVG(live_pred - a.actual_seconds) FILTER (WHERE a.eligible_green) AS live_bias_green,
                   AVG(ABS(live_pred - a.actual_seconds)) AS live_mae_all_rows
            FROM j
            LEFT JOIN laps a USING (race_id, driver, lap)
            LEFT JOIN features_batch f USING (race_id, driver, lap)
            GROUP BY 1 ORDER BY 1"""
        return {"group_by": group_by, **_records(self._con.execute(sql).df())}

    def config_diff(self) -> dict[str, Any]:
        sql = """SELECT b.key, b.value AS batch_value, l.value AS live_value
                 FROM pipeline_config b JOIN pipeline_config l ON b.key = l.key
                 WHERE b.pipeline = 'batch' AND l.pipeline = 'live' AND b.value <> l.value ORDER BY b.key"""
        return {"differences": _records(self._con.execute(sql).df())["rows"]}
