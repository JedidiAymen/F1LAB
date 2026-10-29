"""Pandas, DuckDB and Spark implementations of the same transformations, and a registry that declares the engine.

Each transformation has one SQL text (``sql/<name>.sql``) that runs unchanged on DuckDB and on Spark (source view
``src``), plus a pandas reference used by the equivalence tests. Optional dependencies: ``uv sync --extra engines``
(duckdb, pyspark with Java 17+, deltalake).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

SQL_DIR = Path(__file__).parent / "sql"
ENGINES = ("pandas", "duckdb", "spark")
# Pipeline contract: every step declares the engine it runs on (the orchestration reads this table).
REGISTRY: dict[str, str] = {"race_summary": "duckdb", "compound_wear": "duckdb"}


def sql_text(name: str) -> str:
    return (SQL_DIR / f"{name}.sql").read_text()


def pandas_race_summary(df: pd.DataFrame) -> pd.DataFrame:
    g = df.assign(green=df.eligible_green_next.astype(bool))
    g["abs_green"] = np.where(g.green, g.delta_seconds.abs(), np.nan)
    g["outlier"] = (g.green & (g.delta_seconds.abs() > 8)).astype(int)
    out = g.groupby("race_id").agg(rows_total=("race_id", "size"), rows_green=("green", "sum"),
                                   mean_abs_delta_green=("abs_green", "mean"), outliers_gt_8s=("outlier", "sum"))
    return out.reset_index().astype({"rows_green": "int64", "outliers_gt_8s": "int64"})


def pandas_compound_wear(df: pd.DataFrame) -> pd.DataFrame:
    g = df[df.eligible_green_next.astype(bool) & df.tyre_age_next.notna()].copy()
    g["tyre_age_bucket"] = (np.floor(g.tyre_age_next / 5).astype(int) * 5)
    out = g.groupby(["year", "compound_next", "tyre_age_bucket"]).delta_seconds.agg(
        n="size", mean_delta_seconds="mean", std_delta_seconds="std").reset_index()
    return out.sort_values(["year", "compound_next", "tyre_age_bucket"]).reset_index(drop=True)


PANDAS = {"race_summary": pandas_race_summary, "compound_wear": pandas_compound_wear}


def run_duckdb(name: str, df: pd.DataFrame) -> pd.DataFrame:
    import duckdb
    con = duckdb.connect()
    con.register("src", df)
    try:
        return con.execute(sql_text(name)).df()
    finally:
        con.close()


_SPARK = None


def spark_session():
    global _SPARK
    if _SPARK is None:
        from pyspark.sql import SparkSession
        _SPARK = (SparkSession.builder.master("local[4]").appName("f1lab").config("spark.ui.enabled", "false")
                  .config("spark.sql.shuffle.partitions", "4").config("spark.sql.session.timeZone", "UTC").getOrCreate())
        _SPARK.sparkContext.setLogLevel("ERROR")
    return _SPARK


def run_spark(name: str, df: pd.DataFrame) -> pd.DataFrame:
    spark = spark_session()
    spark.createDataFrame(df).createOrReplaceTempView("src")
    return spark.sql(sql_text(name)).toPandas()


def run(name: str, df: pd.DataFrame, engine: str | None = None) -> pd.DataFrame:
    engine = engine or REGISTRY[name]
    if engine == "pandas":
        return PANDAS[name](df)
    if engine == "duckdb":
        return run_duckdb(name, df)
    if engine == "spark":
        return run_spark(name, df)
    raise ValueError(f"unknown engine {engine!r}; choose from {ENGINES}")


def frames_equal(a: pd.DataFrame, b: pd.DataFrame, *, rtol: float = 1e-9) -> bool:
    """Same columns, same rows in the same order, numerics equal to ``rtol`` (NaN equals NaN)."""
    if list(a.columns) != list(b.columns) or len(a) != len(b):
        return False
    for col in a.columns:
        x, y = a[col].reset_index(drop=True), b[col].reset_index(drop=True)
        if pd.api.types.is_numeric_dtype(x) and pd.api.types.is_numeric_dtype(y):
            if not np.allclose(x.astype(float), y.astype(float), rtol=rtol, atol=1e-12, equal_nan=True):
                return False
        elif not (x.astype(str) == y.astype(str)).all():
            return False
    return True


def write_delta(df: pd.DataFrame, path: str | Path) -> int:
    """Write a result as a Delta table (delta-rs, no Spark needed) and return the committed table version."""
    from deltalake import DeltaTable, write_deltalake
    write_deltalake(str(path), df, mode="overwrite")
    return DeltaTable(str(path)).version()


def read_delta(path: str | Path) -> pd.DataFrame:
    from deltalake import DeltaTable
    return DeltaTable(str(path)).to_pandas()
