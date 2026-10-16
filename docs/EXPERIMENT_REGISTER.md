# Experiment register

## Q-001 — original FastF1 Sprint 2 dataset

- Dataset: `data/processed/qualifying_2022_2023_2024_2025.parquet`, ignored.
- Initial observation on 2026-10-15: 360 driver rows, 17 conventional 2022
  weekends and 2025 Monza. This is **not** a valid chronological backtest.
- Previous ingestion report: `data/processed/qualifying_ingestion_2022_2023_2024_2025.csv`;
  FastF1 500 calls/hour errors and 2023/2024 schedule failures. Current uncached
  F1 timing endpoint returned 401. The two remaining cached 2022 weekends were
  built during this run; original combined file was intentionally preserved.
- Published performance: none.

## Q-002 — mixed-provider common-feature benchmark

- Status: completed research benchmark on 2026-10-15.
- FastF1 3.8.3 supplies 2022. OpenF1 v1 `session_result` and `drivers` supply
  2023–2025. Full source and field mapping: `DATA_CONTRACTS.md`.
- Legal practice fields: eight `COMMON_FEATURES` in `qualifying_backtest.py`.
- Target: Q1 percent gap; evaluation label: final qualifying position.
- Fit 2022–2023; choose by 2024 event-mean MAE; hold out 2025. FP3, Ridge,
  LightGBM, form Ridge and form LightGBM; fixed model settings and seed 42.
- Coverage: 71 conventional weekends, 1,418 source rows; 35/18/18 eligible
  train/validation/test events with 684/342/354 evaluated rows. Mixed dataset
  SHA-256: `eef5a7277d2f62fdf263e94cadbc7a5f5c38cd6acdbea9dc00549d5caef37fd8`.
- 2024 validation position MAE: FP3 2.8975; Ridge 2.8362; LightGBM 3.0247;
  form Ridge 2.8989; form LightGBM 3.0411. Selection: Ridge.
- 2025 held-out position MAE: FP3 3.3141; Ridge 3.2433; LightGBM 3.5897;
  form Ridge 3.2314; form LightGBM 3.4115. Form Ridge's held-out lead was
  observed after selection and does not change the chosen model.
- Ridge-minus-FP3 2025 paired event MAE: -0.0708, 95% bootstrap interval
  [-0.2934, +0.1587], 10,000 seeded resamples. No reliable gain established.
- Artifacts: `data/processed/qualifying_backtest/`,
  `data/processed/qualifying_ablation/`, including executed notebook and plot.
- 2025 Monza overlap: 20 matched drivers, zero classification mismatches and
  zero best-time differences on all available paired FP1/FP2/FP3/Q1 values.
  One weekend cannot establish cross-season equivalence. The provider boundary
  and Q1 pace versus final classification remain the main interpretation risks.

## R-001 — 2025 Italian GP replay-pack QA

- Real source: OpenF1 v1 session 9912, meeting 1268. URL schema and historical
  access: [OpenF1 API](https://openf1.org/docs/). Code is independently
  implemented; raw and compressed packs remain local ignored artifacts.
- Local artifact: `data/processed/replay_packs/monza_2025_race.json.gz` with
  manifest and QA JSON alongside it. Exact artifact/source hashes are in the
  manifest; regeneration changes the pack hash because ingest times change.
- Coverage: 20 drivers, 1,506 sparse events, 198,300 retained source location
  points, 24 event checkpoints. One 2025 race only.
- Checks: 18/18 classified end positions and 20/20 completed-lap totals agree
  with the provider's post-session result; 131 indexed seek times match full
  reduction on discrete state fields. Median indexed seek 1.123 ms, p95
  2.329 ms on this machine. These are implementation QA, not sporting model
  metrics or browser performance.
- Limits: approximate coordinates, unknown coordinate unit, one-lap derived
  circuit trace, estimated lap completion times, no full telemetry or live
  service. A later one-race UI is described in `RACE_CONTROL_UI.md`.

## R-002 — local Race Control API and UI

- Starting SHA `abe031c`; one real Monza pack, with 20 driver states and
  53 post-clock control messages. API manifest returned HTTP 200/35,246 bytes;
  at t=1,200 s all 20 drivers had available provider-derived locations and
  maximum completed lap was 11.
- Synthetic contract tests cover missing/invalid seeks, estimated position
  and a 15-second frozen-coordinate guard. The real replay validator again
  matched 131/131 seeks, p50/p95 0.975/2.066 ms. These are backend checks.
- Web TypeScript/Vite build and ESLint passed. Browser UI inspection was
  unavailable; no visual FPS, real-user playback or interaction metric is
  claimed. See `RACE_CONTROL_UI.md` for commands, files and limits.

## R-003 — additional session source coverage

- Starting SHA `2d270fc`; real OpenF1 v1 sessions 9094 (2023 Monaco) and
  9636 (2024 Brazil). The output is an ignored source audit JSON, not a
  replay pack or UI test. Source table counts, response hashes and exact
  reproduction are in `REPLAY_CANDIDATES.md`.
- Monaco: 20 position/lap drivers, 26 of 176 weather records with rainfall,
  20 INTERMEDIATE plus 3 WET stint rows; pit endpoint HTTP 404. Brazil: 20
  position drivers, 19 lap drivers, 117 of 201 rain records and six critical
  VSC/SC/red control messages. This establishes useful source cases, not
  validated pack behavior.
- Synthetic auditor test and full suite (28 passed) plus Ruff and scoped
  mypy passed. Generalization and pack QA remain next.

## R-004 — three local reference packs and real browser replay

- Starting SHA `7940f2c`. Same adapter/source/API/UI now supports Monza
  2025, Monaco 2023 and Brazil 2024. Real sparse-event/location counts:
  1,506/198,300; 2,101/280,028; 1,683/321,094.
- Final classified positions match 18/18, 19/19 and 15/15; available lap
  totals match 20/20, 20/20 and 19/19. Brazil's HUL DSQ lap total is null,
  counted unavailable. Monaco pit source is unavailable, not zero stops.
- All-boundary and evenly spaced seeks match a separate forward reducer:
  3,868 / 5,798 / 4,446 cases, plus 200 shuffled seeks per pack. Latest
  p50/p95 indexed seek ms: Monza 1.078/2.309, Monaco 1.233/2.816, Brazil
  1.057/2.438. No general FPS claim follows from those backend numbers.
- Four real-pack Chromium UI tests pass; screenshots inspected. Two
  synthetic clock tests and 30 Python contract tests pass. Full artifact
  hashes, exact commands, code map and caveats:
  `REPLAY_GOLDEN_SESSIONS.md`.
