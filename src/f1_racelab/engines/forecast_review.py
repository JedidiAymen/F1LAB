"""Forecast accuracy review (MAE, MAPE, bias by season and model) as SQL plus a Markdown report.

Command: ``uv run python -m f1_racelab.engines.forecast_review`` -> ``data/processed/engines/forecast_review.md``.
Input: out-of-fold predictions from ``ml.pace.benchmark``. Needs ``uv sync --extra engines``.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from f1_racelab.engines import transforms

ROOT = Path(__file__).resolve().parents[3]
PREDICTIONS = ROOT / "data/processed/race_pace/predictions.parquet"
OUT = ROOT / "data/processed/engines/forecast_review.md"
COLUMNS = ["year", "model", "pred_seconds", "next_lap_seconds", "eligible_green_next"]


def review(predictions: pd.DataFrame) -> pd.DataFrame:
    return transforms.run_duckdb("forecast_review", predictions[COLUMNS])


def to_markdown(table: pd.DataFrame) -> str:
    lines = ["# Race-pace forecast review", "",
             "Green-eligible laps, out-of-fold forecasts. Bias = prediction minus truth (positive = too slow).", "",
             "| Season | Model | Laps | MAE (s) | MAPE (%) | Bias (s) |", "|---|---|---:|---:|---:|---:|"]
    lines += [f"| {r.year} | {r.model} | {r.n} | {r.mae_s:.3f} | {r.mape_pct:.3f} | {r.bias_s:+.3f} |"
              for r in table.itertuples()]
    return "\n".join(lines) + "\n"


def main() -> None:
    table = review(pd.read_parquet(PREDICTIONS))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(to_markdown(table))
    print(OUT.read_text())


if __name__ == "__main__":
    main()
