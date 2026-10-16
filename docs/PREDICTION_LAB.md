# Historical qualifying Prediction Lab (partial P4)

**Checkpoint date:** 2026-10-16. **Starting source SHA:**
`bd67b199a189fed6adc604a5130638b9c34b18c6`. **Status:** local historical
Prediction Lab integrated; P4 and M5 remain partial.

## Question and temporal contract

The model predicts each driver's Q1 pace gap percentage from practice-only
fields, then ranks those predictions within each event. Evaluation compares
the predicted order with final qualifying classification. Race starting grid
penalties are not the label. Q1 pace and final classification are not legal
same-event inputs.

The reproduced experiment uses 2022–2023 for training, chooses among FP3,
Ridge and LightGBM by 2024 mean event position MAE, and reports the chosen
model and comparators on held-out 2025 events. Ridge won validation; the 2025
results are not used to change selection. The eight `COMMON_FEATURES` are:

| Feature | Session lineage | Unit |
|---|---|---|
| `fp1_gap_pct`, `fp2_gap_pct`, `fp3_gap_pct` | FP1, FP2, FP3 respectively | Percent gap to that event/session best |
| `fp1_rank`, `fp2_rank`, `fp3_rank` | FP1, FP2, FP3 respectively | Rank in that practice session |
| `fp1_to_fp3_improvement_pct` | FP1 and FP3 | FP1 gap percentage minus FP3 gap percentage |
| `fp2_to_fp3_improvement_pct` | FP2 and FP3 | FP2 gap percentage minus FP3 gap percentage |

`available_at` is the **scheduled qualifying session start** carried by each
source row. It is not the provider's publication time and does not store a
separate observation time for each practice feature. The audit validates the
practice-only feature allowlist, session lineage, qualifying session marker,
and parseable UTC cutoff metadata. The claim is an offline pre-qualifying
reconstruction based on session ordering; it does not establish precisely when
every provider field became available. There are no after-FP1/after-FP2
snapshots yet.

## API and UI

The API reads local ignored artifacts only; it makes no provider request.
`GET /api/v1/predictions/qualifying` returns split summaries, paired bootstrap
intervals, event choices, the eight-feature registry, dataset/prediction
hashes and the timing caveat. `GET
/api/v1/predictions/qualifying/event?year=2025&round=24&split=test` returns one
event's three predicted ranks and retrospective actual ranks. It does not
return `q1_gap_pct`, Q1/Q2/Q3 seconds or the raw `final_position` field. The
actual rank is present so this historical lab can display and inspect errors.

The service loads `data/processed/qualifying_backtest/experiment.json`, the
three prediction summaries, event metrics, bootstrap reports and
`predictions.parquet`. It verifies the experiment split/target contract, the
allowlist result and SHA-256 checksums for every report file it serves
(prediction Parquet, summaries, event metrics and bootstrap reports). Missing
or modified artifacts return HTTP 503 with the reproduction command. A fresh
clone needs to reproduce the ignored dataset and backtest before the page has
data.

The React page is reachable from Race Control's `Prediction Lab` button. It
defaults to the 2025 held-out split, allows 2024 validation selection, shows
event and aggregate rank metrics, and marks the actual classification as
retrospective. The 2025 Ridge-minus-FP3 interval is displayed with a clear
statement that it crosses zero. No probability or confidence percentage is
claimed. The UI screenshot was reviewed at:

`data/processed/browser_tests/results/replay-Prediction-Lab-labe-7122e-tes-validation-from-holdout-chromium/prediction-lab-holdout.png`

## Reproduced evidence

Local source data is the previously cached mixed-provider Parquet: 71
conventional weekends, 1,418 source rows (19 FastF1 2022; 52 OpenF1
2023–2025). Dataset SHA-256:
`eef5a7277d2f62fdf263e94cadbc7a5f5c38cd6acdbea9dc00549d5caef37fd8`.
The served prediction Parquet SHA-256 is
`88195b26ef5f3f5ab86d7b8a906233e7b0c6ef1af05401fc9f74d3afe91d011b`.

Eligible coverage is 684 training drivers / 35 events, 342 validation drivers
/ 18 events, and 354 test drivers / 18 events. Event means are unweighted.

| Split | Model | Position MAE | Spearman | Pole hit | Top-three overlap |
|---|---:|---:|---:|---:|---:|
| 2024 validation | FP3 | 2.8975 | 0.7168 | 0.4444 | 0.5556 |
| 2024 validation | Ridge (selected) | 2.8362 | 0.7523 | 0.5556 | 0.5185 |
| 2024 validation | LightGBM | 3.0247 | 0.7362 | 0.4444 | 0.5185 |
| 2025 held-out | FP3 | 3.3141 | 0.6848 | 0.2222 | 0.6296 |
| 2025 held-out | Ridge | 3.2433 | 0.7095 | 0.2778 | 0.6667 |
| 2025 held-out | LightGBM | 3.5897 | 0.6475 | 0.3889 | 0.6296 |

The held-out Ridge-minus-FP3 event MAE delta is −0.0708 positions, with a
seeded 10,000-resample 95% event bootstrap interval [−0.2934, +0.1587]. It
crosses zero; this run does **not** establish a reliable improvement over FP3.
These are retrospective research metrics, not live-race performance.

## Reproduction

Requires the ignored local mixed dataset described in `ML_EVALUATION.md`.

```bash
.venv/bin/python -m f1_racelab.models.qualifying_backtest \
  --dataset data/processed/qualifying_mixed_2022_2023_2024_2025.parquet \
  --feature-set common
.venv/bin/uvicorn f1_racelab.api:app --host 127.0.0.1 --port 8000
cd apps/web
npm run dev -- --host 127.0.0.1
```

The backtest command writes the CSV/Parquet outputs and manifests to the
default ignored `data/processed/qualifying_backtest/` directory. It selects
the model from 2024 and evaluates 2025 once per reproduction; do not tune based
on the 2025 outputs.

## Verification, source and limitations

- **Real historical model evidence:** cached FastF1/OpenF1 mixed dataset and
  regenerated 2022–2025 evaluation artifact. No new provider request was made.
- **Synthetic tests:** cutoff audit, malformed timestamp/illegal feature,
  missing/tampered artifact, event projection and no-target response tests.
- **Build/browser evidence:** full Python suite 61 passed; targeted Ruff and
  mypy checks pass; frontend 5 unit tests and 10 Chromium tests pass; build and
  ESLint pass. The exact final command log is in `TEST_EVIDENCE.md`.
- **Source rights:** source adapters and data mapping are documented in
  `DATA_CONTRACTS.md`; see [OpenF1 documentation](https://openf1.org/docs/),
  [OpenF1 license](https://github.com/br-g/openf1/blob/87540e3f495bbd9bedb37b10456dd848c8f193d6/LICENSE),
  [FastF1 documentation](https://docs.fastf1.dev/), and the
  [FastF1 package license](https://github.com/theOehrly/Fast-F1/blob/main/LICENSE).
  FastF1's MIT package license is not treated as a license for upstream timing
  data. No third-party source code was copied into this milestone; raw provider
  data and Parquet remain ignored local artifacts.
- **Unresolved:** practice feature observation timestamps and provider
  publication times are not preserved; 2022/2023 provider boundary may
  confound comparisons; only one cross-provider weekend has been compared;
  no per-phase forecast, 2026 walk-forward run, probability calibration,
  feature attribution or model registry exists. Q1 pace remains a proxy for
  final qualifying order.
- **Git:** this document is committed with the milestone; the resulting code
  commit and remote state are recorded in `AGENT_WORKLOG.md` and
  `CHATGPT_HANDOFF.md` after publication.
