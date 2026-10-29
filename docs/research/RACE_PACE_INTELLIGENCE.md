# Race Pace Intelligence

## 1. Research question
Given everything known at the end of lap L, how well can the next green-flag clean lap
duration (lap L+1) be forecast, and does ML beat transparent baselines? Matters for
strategy (undercut windows, tyre-cliff detection) and for the What-If Lab.

## 2. Data
OpenF1 API v1 (https://openf1.org), Race sessions 2023–2026: `laps`, `stints`, `weather`,
`race_control`, `intervals` (fetched with `python -m f1_racelab.ml.pace.fetch`, 2.1 s pacing,
exact-response cache, raw data git-ignored). 88 of 93 races fetched; the 5 missing are 2026
races whose results are not yet published (HTTP 404). Assembled: 85 races, 83,523
driver-lap rows, 74,077 green-flag clean targets. Terms: OpenF1 data is
CC BY-NC-SA 4.0 (non-commercial); raw responses are not redistributed.
Limitations: no fuel mass (proxies: `lap`, `laps_remaining`); `intervals` sampled ~4 s;
a few unneutralised laps survive as "green" (Saudi 2023 lap 27, +56 s).

## 3. Architecture / contract
`ml/pace/dataset.py` builds one row per (driver, lap L) with cutoff = end of lap L.
Features are as-of the cutoff (laps ≤ L; latest weather/interval observation ≤ cutoff;
race-control messages ≤ cutoff) except two labelled **scenario inputs**: tyre compound and
age at lap L+1. Target `delta_seconds = lap(L+1) − median(last 3 clean laps)`; the forecast is
anchor + delta. Green clean = not lap 1, not in/out-lap, regime green (no yellow, SC/VSC with
one-lap restart buffer, or red). Non-green targets are kept and scored separately.
Serving: `ml/pace/service.py`, `GET /api/v1/pace/races`, `GET /api/v1/pace/forecast`
(out-of-fold forecasts + q10/q90 + top-6 TreeSHAP contributions). Model card:
`data/processed/models/race_pace/race_pace_lightgbm.card.json` (SHA-256-verified artifact).

## 4. Method
Expanding-window chronological folds by race: first 20 races train-only, then 3 races per
fold (22 folds, 65 races scored). Fixed hyper-parameters, nothing tuned on scored folds.
Models: rolling-median anchor; last-lap persistence; per-compound OLS (tyre age + laps
remaining); Ridge; LightGBM (L1) with 10/90% quantile models. CatBoost not run (not installed;
no reason to expect gains over LightGBM, documented not claimed). Uncertainty: race-clustered
bootstrap (5,000 draws, seed 42).

## 5. Results (green-flag clean laps, 65 races, 57,679 laps; seconds)
| model | MAE | RMSE | median AE |
|---|---|---|---|
| anchor median-3 | 0.682 | 2.412 | 0.273 |
| fuel/tyre OLS | 0.701 | 2.405 | 0.322 |
| last-lap persistence | 0.593 | 2.043 | 0.246 |
| ridge | 0.603 | 1.887 | 0.305 |
| **LightGBM** | **0.575** | 2.141 | 0.246 |

Paired MAE vs anchor (clustered over 65 races): LightGBM −0.107 [−0.138, −0.076]; persistence
−0.089 [−0.153, −0.037]; ridge −0.079 [−0.146, −0.028]; OLS +0.019 [+0.005, +0.031] (worse).
80% interval coverage 75.2% (mean width 1.29 s): slightly under-covering.
Seed std of MAE over 3 seeds: 0.0026. LightGBM fit 3.0 s/fold, 0.018 ms/row inference.

## 6. Analysis
* Most skill is "recent pace": removing previous-pace features costs +0.123 s MAE.
* **Weather features hurt** (removing them improves MAE by 0.017 s); regime history −0.006;
  identity (driver, circuit) −0.004 (no help); tyre and traffic ≈ 0. Reported as found.
* Persistence is nearly as good as LightGBM in MAE and Ridge wins RMSE: the gain over a good
  heuristic is modest (~3% MAE vs persistence). SC/VSC laps are unforecastable (MAE ≈ 30 s
  for both); yellow laps 6.1 s; wet-compound laps are poor.
* The 0.8% of "green" laps with |delta| > 8 s are mostly wet races (Belgium 2025, Dutch 2026,
  British 2024, Monaco 2023). They were not filtered (target-based filtering would leak).

## 7. Integration
FastAPI endpoints above (503 with reproduction command if artifacts are missing). **React
workspace not built yet.** Strategy Lab is not yet wired to this forecast; the existing
deterministic model is untouched. Comparison against the Strategy Lab tyre model is not done.

## 8. Reproduction
```
uv run python -m f1_racelab.ml.pace.fetch        # ~40 min, polite pacing, cached
uv run python -m f1_racelab.ml.pace.benchmark    # ~6 min; writes data/processed/race_pace/
uv run pytest tests/test_ml_common.py tests/test_pace_dataset.py tests/test_pace_service.py
```
Hardware: CPU only (20 cores used; no GPU). Python 3.12, lightgbm 4.7.0, scikit-learn 1.9.1.
Artifact SHA-256 `530fec6215acf927a5f7d204de87c0fd146ea18b79eff6365b5a8ed71f80739f`.

## 9. Limitations
Tyre compound/age at L+1 are scenario inputs. Multi-lap (direct/recursive) forecasting is
**not implemented**. 2026 regulation shift is not isolated in the metrics. The served model is
fitted on all races, so the API shows out-of-fold forecasts instead. Only green-flag clean laps
carry the headline result.
