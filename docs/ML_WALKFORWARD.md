# Walk-forward qualifying forecaster with calibrated rank probabilities

Source: `src/f1_racelab/models/qualifying_walkforward.py`, served by
`models/walkforward_lab.py`, shown in the Prediction Lab (`ForecastPanel.tsx`).

## Question
Before qualifying, predict each driver's Q1 gap (percent of the event-best Q1
lap), turn it into a within-event order and into probabilities for **pole**,
**top three** and an **80% rank interval**. Evidence label is the final
qualifying classification among eligible drivers (same proxy as
`ML_EVALUATION.md`; starting grids and penalties are out of scope).

## Contract (leakage control)
* Events are in chronological `(year, round)` order. Event *i* is scored by
  models fitted on events `< i` only. First 12 events are warm-up and never
  scored. Evaluation covers 2024 and 2025 (36 events, 706 driver forecasts).
* No hyper-parameter is tuned on evaluated seasons; all are constants in the
  module. `ensemble` was declared the candidate **before** results were seen, so
  there is no selection step. `latest_practice` (latest of FP3>FP2>FP1 gap) is
  the baseline.
* Features (30) are same-weekend practice summaries, FP1/2/3 gap/rank, and labels
  from strictly earlier weekends (`features/historical_qualifying.py` lags, plus
  `track_history_q1_gap` = this driver's Q1 gap at the same circuit name in an
  earlier season). Team features use only same-weekend practice gaps
  (`team_best_latest_gap`, `teammate_delta_latest`).
  `test_event_predictions_ignore_the_evaluated_event_labels` poisons the
  evaluated event's labels and asserts identical predictions.

## Models
Ridge (+team one-hot), LightGBM regressor, LightGBM **LambdaRank** (relevance =
clip(n − rank, 0, 20), linear gain) and `ensemble` = mean of per-event z-scores
of the three, mapped back to the ridge gap scale.

## Uncertainty
`sigma_i = k × ratio × (0.5 + gap_i)`; `ratio` is the std of earlier
out-of-sample `(actual − predicted) / (0.5 + predicted)`; `k` is chosen from
{0.4…1.2} to minimise earlier events' top-3 Brier score (causal). Then 4,000
seeded Gaussian draws per event give P(pole), P(top-3), expected rank and P10/P90
rank. Drivers are treated as independent (teammate correlation ignored).

## Results (real data, OpenF1 2023–2025 + FastF1 2022; 71 weekends)
Position MAE (lower better; 18 events per season):

| model | 2024 | 2025 |
|---|---|---|
| latest_practice | 3.038 | 3.314 |
| ridge | 2.945 | 3.148 |
| lightgbm | 2.945 | 3.208 |
| lambdarank | 2.721 | 2.971 |
| **ensemble** | 2.728 | 3.077 |

Paired event bootstrap (10,000 draws, seed 42) of ensemble − latest_practice MAE:
2024 −0.311 [−0.829, +0.098]; 2025 −0.237 [−0.440, −0.045];
**pooled 2024–2025 −0.274 [−0.544, −0.042]** (36 events). Ridge and LightGBM alone
cross zero pooled; LambdaRank pooled −0.330 [−0.599, −0.106].

Probabilities (ensemble, 36 events): Brier(pole) 0.0374 vs 0.0484 for uniform
1/n; Brier(top-3) 0.0807 vs 0.1295 for uniform 3/n.
P10–P90 rank interval coverage **89.5%** against 80% nominal: intervals are
conservative (mean width 9.7 ranks), i.e. not perfectly calibrated.

## Honest caveats
* Pole-hit rate does **not** improve: ensemble 0.611 (2024) / 0.167 (2025) vs
  baseline 0.444 / 0.222. With 18 events per season this metric is very noisy;
  the gain is in the whole ordering and in probabilities, not in picking pole.
* The label is final classification, which includes Q2/Q3 evolution and wet
  sessions (see `data_quality` warnings); gains are relative, not absolute.
* LambdaRank is slightly better than the ensemble on MAE; the ensemble was kept
  because it was fixed beforehand and gives the gap-scale needed for sigma.
* Scheduled practice end is not provider publication time (as in
  `QUALIFYING_PHASES.md`). Offline historical only; no live forecast.

## Reproduce
```
uv run python -m f1_racelab.models.qualifying_walkforward   # ~16 s
uv run pytest tests/test_qualifying_walkforward.py tests/test_walkforward_lab.py
```
Artifacts (git-ignored under `data/processed/qualifying_walkforward/`):
`predictions.parquet` SHA-256 `4f2b5521de72576e67a58526d1889d5dae4e034f394213f3946680d1dc9133a2`,
dataset SHA-256 `eef5a7277d2f62fdf263e94cadbc7a5f5c38cd6acdbea9dc00549d5caef37fd8`.
Python 3.12.13, lightgbm 4.7.0, scikit-learn 1.9.1, pandas 2.3.3.
API: `GET /api/v1/predictions/qualifying/walkforward[/event?year=&round=]`
(SHA-256 verified, 503 with reproduction command when missing).
