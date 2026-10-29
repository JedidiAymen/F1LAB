# Enhancement plan: ML, ingestion, full stack, visualisation

Evidence-first: items say what exists (done), what this checkpoint adds, and what
is still open. Inspection on 2026-10-29 found three concrete problems:
1. ML: Ridge/LightGBM never beat the FP3 baseline with confidence; no probabilities.
2. Ingestion: OpenF1 client retried only on HTTP status codes, trusted corrupt cache
   files, and nothing audited data quality; sprint weekends are excluded.
3. UI: the replay grid had four children in three columns (right column wrapped
   under the timing tower, large dead area); top bar overflowed on phones, failing
   two e2e tests that predate this work.

## Delivered in this checkpoint
| Area | Change | Evidence |
|---|---|---|
| ML | Walk-forward ensemble (Ridge+LightGBM+LambdaRank), same-weekend team features, causal calibrated rank probabilities | `ML_WALKFORWARD.md`; pooled MAE −0.274 [−0.544, −0.042] vs latest practice |
| ML UI | `ForecastPanel`: P(pole)/P(top-3), P10–P90 rank bars with actual finish, reliability plots, evidence strip | browser screenshot with real 2025 Abu Dhabi forecast |
| Ingestion | `data/quality.py` audit (errors/warnings, coverage matrix, CLI `--strict`) | real run: 1,418 rows, 71 weekends, 0 errors, 37 warnings (mostly wet qualifying) |
| Ingestion | OpenF1 client: transport-error retry, jittered backoff, Retry-After, corrupt-cache quarantine | 3 new offline tests |
| Full stack | Walk-forward artifact loader + 2 API endpoints, SHA-256 fail-closed | 3 API tests |
| UI | Home grid: map + 3D stacked, tower and focus column full height; mobile top bar wraps | page 2,713→2,158 px at 1440; e2e 15/15 |

## Next, in priority order
1. **ML — track-evolution aware target.** Use Q3/Q2 phase times for the label so
   the model targets the classification, and down-weight wet Q1 rows flagged by
   `data_quality`. Add teammate-correlated Monte Carlo (shared team shock).
2. **ML — race model.** Reuse the walk-forward engine for race finishing order
   (grid, long-run pace from FP2, tyre stint features) with the same Brier/coverage audit.
3. **Ingestion — sprint weekends and publication time.** Support Sprint
   Qualifying formats; record per-feature `observed_at` so the cutoff claim can be
   proven, not assumed. Add a single `f1-racelab ingest` CLI with a run manifest.
4. **Ingestion — scheduled refresh.** Incremental OpenF1 sync (new sessions only),
   CI job running `data.quality --strict`.
5. **Full stack — one workstation shell.** Replace the five view-switch buttons
   with a router and persistent session context; consistent tokens in one CSS file
   (`App.css` is 1,200 lines of mixed concerns); split `ReplayWorkspace`.
6. **Visualisation — pit-wall polish.** Gap-evolution and position-chart panels,
   tyre-strategy strip, sector deltas, corner annotations; fix the clipped
   "SOURCE DATA" tag on the tyre panel; keep one clock for all panels.
7. **Quality gates.** Fix the 3 pre-existing React-hooks lint errors
   (`StrategyLab`, `WhatIfLab`, `use-live-session`), add CI.
