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

## R-005 — source-time weather and scoped status in canonical replay

- Starting source SHA `418806099b7670d96cfe13c13c6484d5f8644a50`; three real
  cached OpenF1 races. Schema 2 adds 350 exact-time weather observations and
  14 conservative global track signals; durations remain unchanged. Weather
  maximum retained gaps are 60.042/60.093/60.225 seconds. No interpolation,
  rain intensity, or green state is inferred from ending messages.
- Independent raw-cache lineage and as-of audit: 700 weather before/exact
  checks, 14 golden boundaries, zero invalid weather. The replay differential
  validator checks 15,162 boundary/regular cutoffs and 600 shuffled revisits.
- Six real-pack Chromium tests cover synced panels, Monaco's rain/dry/rain
  seeks and Brazil's VSC ending, red, session restart and Safety Car ending.
  Fifty Python tests and three JS unit tests pass. Exact commands, hashes,
  units, signal sequence, screenshots and interpretation limits are in
  `REPLAY_CONTEXT.md` and `TEST_EVIDENCE.md`.
- This is replay-context evidence for three events, not weather calibration,
  wet-track estimation, live behavior or a general race-condition model.

## R-006 — as-of tyre stint history and map motion

- Starting source SHA `2feed4059141107b43c31bf87f9937c565e2bdef`; real source
  data is the already-audited OpenF1 stint/lap timeline in the three local
  packs. Event envelopes and pack files remain schema 2; current emitted
  `RaceState` is schema 3. Implementation commit
  `4a0434aea67ff99a2f949abc08babdcbf0b50578` is pushed and remote-verified.
- `TyreStintState` records source event ID, source time, compound, lap start,
  as-of lap end, quality, observed time, tyre age at start and closing event.
  A lap event advances only the currently open segment. A later stint-start
  event closes the previous segment at the latest completed lap (not below its
  start), then appends the new event. Provider `lap_end` is not read into an
  earlier replay state, preventing future leakage.
- Pack coverage: 39 Monza, 57 Monaco and 52 Brazil stint events are retained
  (148 total). Brazil has 54 raw rows; one has no `lap_start` and one has no
  matching lap-start row, so both are counted and omitted. Monaco car 27 has
  two source starts on lap 1; both appear, including the mapped overlap. No
  missing lap range is fabricated.
- The selected-driver panel uses one lane per stint and positions lap `L` at
  `100×(L−1)/scheduled_laps`; its width is
  `100×max(1,lap_end−lap_start+1)/scheduled_laps`. Compounds and source quality
  are shown. Map motion is only visual CSS `transform` interpolation for
  forward canonical-state deltas through 4 s (180 ms ease-out); exact seeks,
  reverse movement, initial samples and larger gaps disable transitions.
  Reduced-motion preference disables CSS transitions. Server state remains
  sampled at 5 Hz and unchanged; no FPS or physically continuous position
  claim follows.
- Synthetic evidence: 51 Python tests pass (one existing Starlette/httpx
  deprecation), including duplicate lap-start, as-of end and API state schema.
  Ruff, 13-file session/API mypy and three JS unit tests pass. Real-pack
  Playwright suite passes 8/8 with inspected Monza/Monaco desktop screenshots.
  Independent replay QA checks 15,162 boundary/regular cutoffs and 600
  shuffled revisits; context QA reruns 700 weather cutoff checks and 14
  reviewed status boundaries with zero invalid rows.
- The first new browser assertion failed after seeking to pack end because no
  source car locations remained and React correctly rendered zero cars. The
  test now exact-seeks to the source `SESSION STARTED` event, where measured
  locations are present, and verifies the transition is disabled. Exact
  commands, screenshots, QA artifacts and caveats are in
  `REPLAY_STINTS_AND_MOTION.md`.

## R-007 — distance-aligned historical lap telemetry foundation

- Starting source SHA `89351502ccb6389c25886d18022430f2ce6319f8`; source is
  cached OpenF1 v1 historical session 9912 (Monza 2025), with response hashes
  and provider/license links in `DISTANCE_ALIGNED_TELEMETRY.md`.
- Implementation commit `2ac01012c780552f26bd9504f88c9cac87541000` is pushed
  to `origin/feat/foundation` and remote-verified at the same SHA.
- Compared VER #1 lap 50 (81.297 s) with NOR #4 lap 50 (81.123 s). Inputs are
  29,611 car-data rows per driver and the session lap table. In-window counts
  are 318 and 309; bounded point counts 320 and 311 include two interpolated
  boundaries each. Maximum bounded sample interval is 0.799 s.
- Algorithm: integrate speed with the trapezoidal rule after converting km/h
  to m/s; reject gaps over 1 s; align both independently estimated distance
  axes to a common 5 m grid; interpolate continuous fields linearly and
  discrete source states by previous value; delta is elapsed B minus elapsed A.
- Result: integrated distances 5,746.062 m and 5,751.324 m; common endpoint
  5,746.062 m; 1,150 grid points; B−A delta range −0.374 to +0.212 s and
  endpoint −0.234 s. These are descriptive outputs from two laps, not a
  general performance result.
- Synthetic tests: 5 telemetry tests; complete repo suite 56 passed (one
  existing deprecation warning); Ruff passed; mypy passed 17 files. Chart was
  visually inspected. Full artifact hashes and exact commands are recorded in
  `TEST_EVIDENCE.md` and `DISTANCE_ALIGNED_TELEMETRY.md`.
- Failure/fix: observations of 104 in full source streams disproved an assumed
  0–100 validation bound; no clipping is performed. Chart contrast was fixed.
  No frontend, canonical cursor or prediction model has been added.
