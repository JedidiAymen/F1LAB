# F1LAB Sprint 3 — historical driver/team form, Neovim workflow, ablations

## Baseline

Sprint 2 already implements `build_dataset`, Ridge, LightGBM and FP3 selection using **2024 validation / untouched 2025 test**. Sprint 3 **adds** features instead of replacing or retuning those models.

## What the code adds

1. `historical_qualifying.py`: strict previous-weekend driver Q1 pace, FP3→Q1 gain, average classification, Q3 appearance, performance relative to teammate, and team Q1 performance. Rolling 3 and 5 prior appearances only. All qualifying-dependent values use `shift(1)` before they reach the current row.
2. `enrich_team_metadata.py`: extracts team labels from already-cached FP3 data (may contact FastF1 only when needed), updates local per-event Parquet and reconstructs the combined dataset. Does not overwrite your original feature-extraction code.
3. `qualifying_ablation.py`: reruns the unchanged original FP3/Ridge/LightGBM benchmark, fits two augmented models with historical form, chooses from **five candidates using only 2024**, and then reports 2025 test scores for all models.
4. Notebook 03: inspects result tables, feature coverage and validation/test plots.
5. Tests: assert first weekend has no history, changing current qualifying labels does not modify current historical inputs, shared teammate/team logic, offline fit, and missing team robustness.

## The actual target and trade-off

The model currently predicts **Q1 gap %** and is ranked against **final qualifying position**. These are related but not identical because Q2 and Q3 change track conditions and driver opportunity. We are benchmarking this proxy, **not** claiming full-session Q1/Q2/Q3 simulation.

The historical features use **previous results**, but a 2025 Round 10 prediction may use the *already completed* 2025 Rounds 1–9. This is a realistic walk-forward prediction timestamp and not a frozen December 2024 forecast.

## Commands

```bash
cd ~/Documents/projects/F1LAB
uv sync --dev
uv add --dev jupytext pynvim jupyter-client
uv run pytest tests/test_qualifying_backtest.py tests/test_historical_qualifying.py -q

# Prerequisite if not done: populate conventional weekends, 2022 through 2025.
uv run python -m f1_racelab.data.qualifying_dataset --years 2022 2023 2024 2025

# Attach team information for teammate/team historical form.
uv run python -m f1_racelab.data.enrich_team_metadata --years 2022 2023 2024 2025

# Run the FIVE-model ablation using the same chronological split.
uv run python -m f1_racelab.models.qualifying_ablation

# View notebook cells locally.
uv run bash scripts/make_nvim_pairs.sh
nvim notebooks/03_qualifying_form_ablation.py
# Or browser rendering: uv run jupyter lab
```

**No realistic score is claimed until the real FastF1 ingestion and benchmark have actually run**. Examine `data/processed/qualifying_ingestion_*.csv` for missing weekends, and `data/processed/qualifying_ablation/feature_coverage.csv` for missing historical values. `team_label_coverage` should be high after enrichment; if not, do not interpret teammate-related features as genuinely evaluated.

## Feature meanings

| Feature | Meaning | Time policy |
|---|---|---|
| driver_q1_gap_last_3/5 | Average driver's past normalized Q1 gap | previous 3/5 driver events |
| driver_fp3_to_q1_gain_last_3/5 | How much relative pace improves from FP3 to Q1 | previous events only |
| driver_position_last_3/5 | Historical qualifying classification | previous events only |
| driver_q3_rate_last_3/5 | Fraction of previous sessions with a recorded Q3 time | previous events only |
| driver_vs_teammate_q1_last_3/5 | Driver's historical Q1 gap minus other team car(s)' Q1 gap | previous events only |
| team_q1_gap_last_3/5 | Rolling mean of **one team result per previous weekend**, not per driver | previous team weekends |

`driver_vs_teammate_q1` is positive when the driver was slower than teammate. The code intentionally does not fabricate teammates when a team label is absent.

## Interpretation

- If `form_ridge` beats `ridge` on both validation and test, the extra historical features plausibly add generalizable signal.
- If 2024 improves but 2025 gets worse, the improvement probably overfit to an earlier era; do not tune on 2025 to repair it.
- If FP3 remains strongest, keep it as the production baseline and test smaller feature subsets instead of increasing complexity.
- If missingness is large, fix data coverage before increasing model complexity.

## Next experiment

Proper rolling walk-forward cross-validation and a **2026 regulation-era** transfer test. Then a phase-aware qualifying simulator with calibrated uncertainties—only after honest ranking/pacing validation.
