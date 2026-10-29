# Data engines: pandas vs DuckDB vs Spark (and Delta)

Goal (modelled on a "move small Spark jobs to DuckDB" brief): faster, cheaper runs and a shorter develop/test loop, **one version of each transformation that runs on a laptop and in the cloud**, with tests proving identical output.

## What exists
* `src/f1_racelab/engines/sql/*.sql`: each transformation written once as portable SQL against a view `src`. The same text runs on **DuckDB** and on **Spark** (`spark.sql`); a **pandas** reference implementation backs the equivalence tests.
* `engines/transforms.py`: registry `REGISTRY` where every step **declares its engine** (`duckdb`, `spark` or `pandas`), plus Delta helpers (`write_delta`, `read_delta`, via delta-rs, no Spark needed).
* One command: `uv run python -m f1_racelab.engines.run race_summary --engine duckdb --sample` (synthetic sample) or `--input <parquet>` (local or remote path read by DuckDB); `--compare` times all engines and checks equality; `--delta-out PATH` also writes a Delta table.
* Metrics for forecast review: `ml.common.metrics.mape` (percent, zero targets excluded) and `bias` (prediction minus truth).
* Optional dependencies: `uv sync --extra engines` (duckdb 2.0.0, pyspark, deltalake; Spark needs Java 17+, tested with Temurin 21).

## Real-data comparison (83,523 rows, `pace_frame.parquet`, 20-core laptop, Spark `local[4]`)
| Transformation | pandas | DuckDB | Spark | Equal to pandas |
|---|---|---|---|---|
| `race_summary` (85 rows out) | 0.010 s | 0.066 s | 5.63 s | yes, all engines |
| `compound_wear` (176 rows out) | 0.011 s | 0.070 s | 5.81 s | yes, all engines |

Single runs, not a rigorous benchmark; Spark time is dominated by JVM and session start-up, DuckDB time includes registering the DataFrame. **At this data size pandas is fastest**; DuckDB's case here is SQL portability, out-of-core and direct Parquet/object-storage reads rather than speed. Choose which steps to move by size: small steps go to DuckDB, genuinely large ones stay on Spark.

## Tests (`tests/test_engines.py`)
DuckDB equals pandas and Spark equals pandas and DuckDB for each transformation (tolerance 1e-9 / 1e-6), engine registry validity, MAPE/bias definitions, Delta round trip. They skip when the optional packages are missing, so CI without the extra stays green.

## Not verified
* **Databricks:** nothing was run on a Databricks cluster. The intended route is `%pip install duckdb` on the cluster and reading Parquet from a Unity Catalog Volume path with the same `.sql` files; compute type, dependency pinning and storage access remain to be tested there.
* Remote object-storage reads need the DuckDB `httpfs` extension and credentials; not exercised.
* No external scheduler (Airflow/Databricks Jobs) integration; `engines/pipeline.py` is a local runner only.

## Pipeline and feed check (added)
`uv run python -m f1_racelab.engines.pipeline` runs `engines/feed_check.py` first, then each registered step on its **declared engine** (`--engine-override` to force one), writing Parquet outputs and `manifest.json` (engine, rows, seconds, SHA-256) under git-ignored `data/processed/engines/`. Real run on 83,523 rows: `race_summary` 0.07 s and `compound_wear` 0.02 s on DuckDB.

The feed check (completeness, compound/regime mappings, unique key, target consistency, plausibility) found one real issue on first run: 53 rows with next-lap times of 468-2,588 s, 51 of them red-flag laps and none green-eligible. The rule is now an error only for green-eligible rows and a warning otherwise, so red-flag stoppages cannot fail the pipeline but remain visible.
