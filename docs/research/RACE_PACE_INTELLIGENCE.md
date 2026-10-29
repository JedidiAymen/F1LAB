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
FastAPI endpoints above (503 with reproduction command if artifacts are missing). React
workspace `apps/web/src/components/RacePaceLab.tsx` (nav button "Race Pace"): race/driver
selectors, benchmark evidence strip, actual vs forecast chart with 10–90% band and rolling-median
baseline, per-lap forecast with TreeSHAP contributions, evidence labels ("ML PREDICTION · NOT LIVE").
Browser test: `race pace lab shows out-of-fold forecasts…` (e2e 17/17). Strategy Lab is **not** wired to
this forecast; the deterministic model is untouched and no comparison against its tyre model exists.

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

## Quality-gate audit: LightGBM vs last-lap persistence (Milestone 1, gates A, C, E)

Command: `uv run python -m f1_racelab.ml.pace.audit` (reads `data/processed/race_pace/predictions.parquet`, writes `audit.json`; real data, 65 scored races, 57,679 green laps). Code: `src/f1_racelab/ml/pace/audit.py`, tests: `tests/test_pace_audit.py` (synthetic).

**A. Paired, race-clustered comparison.** MAE LightGBM 0.5749 s vs persistence 0.5929 s: difference -0.018 s (-3.0%), 95% race-clustered bootstrap CI [-0.057, +0.029]. **The CI contains zero, so the earlier claim of beating the strongest baseline is not supported at this strength.** LightGBM wins in 80% of races and the median per-race delta is -0.052 s, but the mean is pulled up by a few races where it loses heavily (95th percentile +0.20 s).

**E. Per season (green laps, MAE s).** 2024: LightGBM 0.491 vs persistence 0.498. 2025: 0.489 vs 0.478 (persistence better). 2026: 0.849 vs 0.923. The pooled gain comes mostly from 2026; in 2025 persistence is better. 2026 lap-time noise is larger for every model. 2026 was part of the walk-forward evaluation, not an untouched holdout.

**C. Interval calibration.** Raw q10-q90 coverage is 75.1% against an 80% target. Chronological conformalized quantile regression (fold k corrected with scores from folds < k only) gives 80.1% at width 1.44 s (raw 1.31 s), with pinball 0.1797 vs 0.1803, so sharpness is essentially unchanged. By compound the coverage is 78-80%. By season it is 77.7% (2024), 83.4% (2025) and 78.8% (2026). By regime, green is 76.2% and yellow 50.3%; safety-car/VSC laps are 5.3% and the intervals are unusable there. Do not present them as valid for neutralised laps.

## Versioned inference service (Milestone 1, gates F and H)

`POST /api/v1/pace/predict` (`src/f1_racelab/ml/pace/inference.py`): strict pydantic schema (`extra="forbid"`, range-checked, compound enum) over the card's feature list plus `anchor_seconds`; returns forecast = anchor + median delta, raw q10/q90, model id/version, dataset fingerprint and warnings (rain, neutralised laps). Load path: SHA-256 check (`load_artifact`), card-vs-schema equality check, and exact match of lightgbm/numpy/pandas/scikit-learn versions against the card; any failure is HTTP 503 with the reproduction command. The artifact is local and trusted only; joblib is never loaded from user input.

**Bug found by this work:** the artifact had been pickled with `LgbmBundle` defined in `__main__` (benchmark run via `python -m`), so it could not be loaded by any other process. The class moved to `ml/pace/bundle.py`, and `python -m f1_racelab.ml.pace.benchmark --refit-only` re-saved the artifact from `pace_frame.parquet` without rerunning the walk-forward. New artifact SHA-256 `98b611f3…adf8c2`. Tests: `tests/test_pace_inference.py` (schema rejection, tamper, version mismatch, HTTP 422/503/200). Full suite: 210 passed.

## Strict decision-time protocol (Milestone 1, gate B)

Command: `uv run python -m f1_racelab.ml.pace.strict` -> `data/processed/race_pace/strict_protocol.json`. Code `ml/pace/strict.py`, tests `tests/test_pace_strict.py` (synthetic, including a check that lap L+1's tyre is not visible). Real data, 65 scored races, 59,414 scored rows.

Differences from the conditional benchmark: rows are chosen from decision-time state only (no neutralisation in the last 3 laps, no yellow on lap L), never from the outcome of lap L+1; tyre inputs are rebuilt "as if the car stays out" from lap L; targets include out-laps, in-laps and neutralisations; training uses the same population with L1 loss.

| MAE (s) | LightGBM | naive persistence | persistence + post-pit rule | anchor |
|---|---|---|---|---|
| all rows | 0.886 | 1.289 | 0.944 | 1.359 |
| green-clean outcome only | 0.539 | - | 0.535 | 0.601 |

**Finding.** Against naive persistence LightGBM wins by 0.40 s [-0.46, -0.33], but that comparison is unfair: persistence predicts 0 after an in-lap, which every pit-wall tool knows to be an out-lap. Against the fair rule (persistence, except after an in-lap predict the training median out-lap delta) the difference is -0.059 s [-0.133, +0.017], not significant, and on green-clean laps the two are tied (+0.005 [-0.041, +0.063]). Out-lap error falls from 13.5 to 4.1 s with the rule + model but the rule alone gets 5.0 s. Median absolute error is marginally better for persistence (0.264 vs 0.280 s). Conclusion: the lap-time model adds little beyond persistence at decision time; the gain it shows is in pit-related laps. Reports should quote the fair baseline, not naive persistence.

## Outlier audit (Milestone 1, gate D)

`audit.outlier_audit`: 593 of 74,077 green rows (0.8%) have |delta| > 8 s. Independent evidence (rainfall flag or INTERMEDIATE/WET compound on at least 5% of a race's rows; no lap-time information) explains 231 of them in 9 races (Dutch 2026, British 2024, Monaco 2023, Dutch 2023, ...). 362 are unexplained: Belgian 2025 (83), Barcelona 2026 (56), Singapore 2026 (53), Canadian 2026 (49). They may be unflagged rain, red-flag restarts or timing artefacts; this is not established. Nothing was removed. Sensitivity excluding the 9 wet-evidence races: LightGBM 0.529 vs persistence 0.559 s, -0.030 [-0.068, +0.017], 59 races; conclusion unchanged.

## Opt-in ML pace in Strategy Lab (Milestone 1, gate G)

`POST /api/v1/strategy/{slug}/ml-pace` (`strategy/ml_overlay.py`, UI `MlPaceOverlay.tsx`, off by default). It rolls the saved next-lap model forward on its own predictions across one stint and returns it next to the deterministic simulator's curve for the same compound, tyre age and fuel. The simulator code and race-time rankings are not touched. Weather and traffic inputs are explicit assumed defaults returned with the result. Evidence label `ml_prediction_rollout`.

Real-model check (Monza 2025, laps 8-32): the ML curve is flatter than the simulator's. After 24 laps the simulator is -1.4 s (MEDIUM) / -1.6 s (HARD) relative to the first lap (fuel burn outweighs tyre wear) while the ML rollout is about -0.04 s / -0.22 s; mean shape gap 0.72 s (MEDIUM), 0.80 s (HARD). The rollout drifts toward persistence, so it understates the fuel-burn trend. It is an exploratory comparison, not a better strategy model, and the UI says so. Tests: `tests/test_ml_overlay.py` (labelling, baseline untouched, 200/404/422/503) and a Playwright spec (18/18 pass).
