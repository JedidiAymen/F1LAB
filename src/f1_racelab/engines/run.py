"""One command to run a transformation on a laptop with any engine, or compare engines.

  uv run python -m f1_racelab.engines.run race_summary --engine duckdb --sample
  uv run python -m f1_racelab.engines.run compound_wear --input data/processed/race_pace/pace_frame.parquet
  uv run python -m f1_racelab.engines.run race_summary --compare          # timings + equivalence vs pandas
  uv run python -m f1_racelab.engines.run race_summary --input s3://bucket/pace_frame.parquet   # remote path via DuckDB httpfs
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from f1_racelab.engines import transforms

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INPUT = ROOT / "data/processed/race_pace/pace_frame.parquet"
COLUMNS = ["race_id", "year", "eligible_green_next", "delta_seconds", "tyre_age_next", "compound_next"]


def sample_frame(rows: int = 5000, seed: int = 42) -> pd.DataFrame:
    """Synthetic data with the real schema, for laptops without the git-ignored parquet. Not real results."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "race_id": rng.choice([f"r{i}" for i in range(12)], rows), "year": rng.choice([2024, 2025, 2026], rows),
        "eligible_green_next": rng.random(rows) < 0.9, "delta_seconds": rng.normal(0, 1.2, rows),
        "tyre_age_next": np.where(rng.random(rows) < 0.03, np.nan, rng.integers(1, 40, rows)).astype(float),
        "compound_next": rng.choice(["SOFT", "MEDIUM", "HARD"], rows)})


def load(path: str | None, sample: bool) -> pd.DataFrame:
    if sample:
        return sample_frame()
    source = path or str(DEFAULT_INPUT)
    if "://" in source:  # remote object storage read directly by DuckDB (needs the httpfs extension and credentials)
        import duckdb
        return duckdb.connect().execute(f"SELECT {', '.join(COLUMNS)} FROM read_parquet(?)", [source]).df()
    return pd.read_parquet(source, columns=COLUMNS)


def compare(name: str, df: pd.DataFrame) -> list[dict]:
    reference = transforms.run(name, df, "pandas")
    rows = []
    for engine in transforms.ENGINES:
        try:
            started = time.perf_counter()
            out = transforms.run(name, df, engine)
            seconds = time.perf_counter() - started
            rows.append({"engine": engine, "seconds": round(seconds, 4), "rows_out": len(out),
                         "equals_pandas": transforms.frames_equal(reference, out, rtol=1e-6)})
        except ImportError as exc:
            rows.append({"engine": engine, "skipped": f"missing dependency: {exc.name}"})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("transform", choices=sorted(transforms.PANDAS))
    parser.add_argument("--engine", choices=transforms.ENGINES)
    parser.add_argument("--input")
    parser.add_argument("--sample", action="store_true", help="use synthetic sample data")
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--delta-out", help="also write the result as a Delta table at this path")
    args = parser.parse_args()
    df = load(args.input, args.sample)
    if args.compare:
        print(json.dumps({"input_rows": len(df), "results": compare(args.transform, df)}, indent=1))
        return
    engine = args.engine or transforms.REGISTRY[args.transform]
    started = time.perf_counter()
    out = transforms.run(args.transform, df, engine)
    print(out.head(15).to_string(index=False))
    if args.delta_out:
        print(f"Delta table written, version {transforms.write_delta(out, args.delta_out)}: {args.delta_out}")
    print(f"\n[{engine}] {len(out)} rows from {len(df)} input rows in {time.perf_counter() - started:.3f}s")


if __name__ == "__main__":
    main()
