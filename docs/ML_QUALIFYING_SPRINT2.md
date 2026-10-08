# F1LAB / ML Sprint 2 — Multi-season qualifying benchmark

## Goal

Create one reproducible dataset for **conventional** F1 weekends from 2022–2025, and compare the simplest honest predictor (FP3 lap ranking) against Ridge and LightGBM regression.

> **Status:** Code package ready to run locally. Real historical backtest metrics are **not** reported until the pipeline has run against FastF1 data on your machine. This is NOT a claim of model performance.

## What each file does

| File | Purpose |
|---|---|
| `src/f1_racelab/data/qualifying_dataset.py` | Enumerate race weekends, skip Sprint weekends, call the existing feature extractor, save per-weekend Parquet files and ingestion/error log |
| `src/f1_racelab/models/qualifying_backtest.py` | Prepare legal pre-qualifying features; fit Ridge and LightGBM on 2022–23; select by 2024 validation; evaluate untouched 2025 |
| `notebooks/02_qualifying_backtest.ipynb` | Examine dataset quality, prediction tables, metrics, and error plots. The reusable functions live in `src/`, not notebooks |
| `tests/test_qualifying_backtest.py` | Synthetic offline checks: no target leakage, correct event grouping, chronological splits and model pipeline |

## Install

The packages used here (FastF1, pandas, sklearn, LightGBM, Jupyter) are **already in your GitHub `pyproject.toml`**. No further `uv add` is required unless your local environment differs. At the repo root:

```bash
uv sync --dev
```

## Commands

From `~/Documents/projects/F1LAB`:

```bash
# 1. Run fast local-only tests (no downloads)
uv run pytest tests/test_qualifying_backtest.py -q

# 2. Download/build all conventional weekends from 2022 through 2025
uv run python -m f1_racelab.data.qualifying_dataset --years 2022 2023 2024 2025

# 3. Compare FP3/Ridge/LightGBM; output tables under data/processed/
uv run python -m f1_racelab.models.qualifying_backtest

# 4. Explore charts/diagnostics
uv run jupyter lab notebooks/02_qualifying_backtest.ipynb
```

To inspect the pipeline quickly before the full historical run, use `--max-events-per-year 2` but **do not run a benchmark from that small sample**; it is only a technical smoke test. Cached weekend Parquet files are reused by default, so interrupted or failed runs are resumable. Add `--refresh` to rebuild already cached weekends.

## Pre-qualifying cutoff / leakage

- An input is legal only if available **before that weekend's qualifying begins**.
- `q1_gap_pct` is the supervised training **target**, calculated after qualifying. It never enters `FEATURES`.
- `final_position` is used **only for ranking evaluation**.
- `q2_seconds`, `q3_seconds`, championship end-of-year outcomes, post-qualifying weather, final starting grid must not be input features.
- FP3 practice numbers are normalized **within the same weekend**, never across other weekends or years.
- Entire weekends stay together in one train/validation/test partition.
- The current model uses the predicted Q1 pace as a simple **proxy** to rank drivers against the final qualifying classification; Q1 is not identical to final Q3 potential. A future phase-aware model is needed.

## Split policy

| Stage | Data | Purpose |
|---|---|---|
| Train | 2022–2023 | Fit parameters |
| Validation | 2024 | Choose among FP3/Ridge/LightGBM without looking at test outcomes |
| Test | 2025 | Held-out estimate of generalization |

We report **mean of per-event** absolute position error and Spearman correlation, plus pole-hit and Top-3-overlap rates. The `winner` is chosen ONLY by 2024 validation MAE. We still report every model's held-out test performance for learning and transparency.

## Limitations and next improvements

1. **Sprint weekends skipped in V1.** They do not necessarily have FP2 and FP3. Later, build a separate predictor based on the information that exists at that cutoff.
2. **Heuristic push laps.** Original extractor uses 3% of each driver's best non-pit, non-deleted lap. It is not a certified qualifying-run detector.
3. **Incomplete session data.** FastF1 occasionally fails on individual historical sessions: every error is logged in `data/processed/qualifying_ingestion_*.csv`. Check error counts and coverage before believing metrics.
4. **FP3/Q1 coverage.** Metrics restrict to drivers with valid FP3 and Q1 data; rank predictions are within that evaluated subset.
5. **Uncalibrated probabilities.** No P(pole) claims yet. First validate a point/ranking model; then estimate residual distributions and calibration.
6. **Selection bias.** `fp3_best_seconds` is the primary baseline. We should measure whether soft-only pace, sectors, historical driver form, and teammate form outperform it via ablation studies.
7. **Outdated era.** A 2026 regulation transition should receive separate walk-forward analysis, not be folded into 2025 test data indiscriminately.
8. **Missingness.** Numeric features are median-imputed using training data only inside an sklearn pipeline. This prevents cross-year leakage through imputation statistics.

## Revision: tools and models

- **FastF1:** loads historical session information.
- **pandas:** manipulates driver/weekend tables in memory.
- **Parquet:** compact columnar file for resumable local storage (eventual MinIO candidate).
- **scikit-learn Pipeline:** ensures preprocessing is learned on training data and identically applied to future data.
- **OneHotEncoder:** encodes driver and circuit names without inventing numeric order.
- **SimpleImputer:** fills missing values using *training-set-only* statistics.
- **Ridge:** linear regression with L2 penalty; our first learnable baseline.
- **LightGBM:** gradient-boosted decision trees; models nonlinear feature interactions.
- **MAE:** average absolute position error, aggregated equally by weekend.
- **Spearman:** rank-order agreement.
- **Chronological validation:** train on the past, select using the next year, evaluate on the year after that.

## Git checkpoint

After verifying tests, ingestion report, and backtest tables:

```bash
git status --short
git add src/f1_racelab/data/qualifying_dataset.py src/f1_racelab/models/qualifying_backtest.py src/f1_racelab/models/__init__.py notebooks/02_qualifying_backtest.ipynb tests/test_qualifying_backtest.py docs/ML_QUALIFYING_SPRINT2.md
git diff --cached --stat
git commit -m "feat(ml): add multi-season qualifying dataset and temporal benchmark"
git push origin feat/foundation
```

Generated historical datasets and prediction tables are ignored under `data/processed/`. **Do not commit the raw FastF1 cache or downloaded datasets by default.**
