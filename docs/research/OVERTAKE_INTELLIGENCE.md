# Overtake Intelligence: next-lap on-track pass probability

Status: evaluated on real data; read-only API `GET /api/v1/overtake/summary`; UI workspace "Overtakes" (model table, paired gains, reliability, per-season); not a live system.

## Data and label
Built from the race-pace frame (OpenF1 laps, intervals, stints; 85 races 2023-2026). Unit: follower F directly behind leader A by gap-to-leader at the end of lap L with interval at most 3 s. Label: F is ahead of A at the end of lap L+1. Pairs are **dropped** (not labelled 0) if either car had an in-lap or out-lap at L or L+1, or if a safety car/VSC/yellow affected L+1 or the last 3 laps. Result: **29,608 pairs, 1,595 passes (5.4%)**. Command: `uv run python -m f1_racelab.ml.overtake.dataset`.

Sanity checks on the label: pass rate falls smoothly with interval (about 50% at 0.3 s or less, 20% at 0.3-0.6 s, 5% at 0.6-1.0 s, 0.1% above 2 s) and 92% of detected swaps are still in place two laps later, so the label mostly reflects real passes rather than timing noise. Residual risk: order comes from gap-to-leader snapshots, not a dedicated overtake log.

## Features (all known at the end of lap L)
Interval, interval trend, pace advantage (leader's last lap minus follower's), tyre-age and compound differences, both tyre ages, DRS window (interval at most 1 s), laps remaining, circuit pass rate from strictly earlier races only, interval age.

## Protocol and models
Expanding-window walk-forward grouped by race (20 races minimum, step 3), identical in spirit to race pace; 22,637 pairs scored in 22 folds. Models: constant rate, logistic on gap only, logistic on all features, LightGBM raw, LightGBM with isotonic calibration fitted on the last 20% of the training races (never on test races). Fixed hyper-parameters. Command: `uv run python -m f1_racelab.ml.overtake.benchmark`.

## Results (real data, scored folds)
| Model | Brier | Log-loss | AUC | Avg. precision | ECE |
|---|---|---|---|---|---|
| constant rate | 0.0494 | 0.2050 | 0.479 | 0.049 | 0.0073 |
| logistic, gap only | 0.0407 | 0.1493 | 0.877 | 0.325 | 0.0056 |
| logistic, all features | 0.0335 | 0.1219 | 0.927 | 0.527 | 0.0036 |
| LightGBM raw | **0.0329** | **0.1170** | **0.936** | **0.563** | 0.0086 |
| LightGBM + isotonic | 0.0335 | 0.1241 | 0.929 | 0.534 | 0.0063 |

Paired race-clustered Brier difference against the gap-only logistic: logistic all -0.0073 [-0.0098, -0.0049]; LightGBM raw -0.0079 [-0.0105, -0.0056]; calibrated -0.0072 [-0.0098, -0.0050]. Most of the skill is the gap itself (the gap-only model already reaches AUC 0.88); the other features add a significant but smaller gain. Isotonic calibration did **not** improve Brier or log-loss over the raw model; it only lowered ECE slightly versus raw (0.0063 vs 0.0086), while plain logistic is best calibrated (0.0036). By year the calibrated model's Brier is 0.043 (2023, 521 pairs), 0.034, 0.029 and 0.041 (2026), with mean predictions close to observed rates.

## Limits
* Not a prediction of who will win a duel under strategy changes: pit stops and neutralisations are excluded by design.
* One-lap horizon; no multi-lap or lap-by-lap sequence model.
* Possible dependence between consecutive laps of the same pair is handled only by race-level bootstrap.
* Needs an as-of live feed before any decision use.
