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

## Q-003 — historical Prediction Lab artifact and cutoff audit

- Status: implemented on 2026-10-16 from the existing local Q-002 dataset; no
  new provider request. This exposes historical artifacts in the web app and
  does not create a live/2026 forecast.
- Source Parquet SHA-256:
  `eef5a7277d2f62fdf263e94cadbc7a5f5c38cd6acdbea9dc00549d5caef37fd8`.
  Regenerated predictions Parquet SHA-256:
  `88195b26ef5f3f5ab86d7b8a906233e7b0c6ef1af05401fc9f74d3afe91d011b`.
- Feature cutoff: immediately before qualifying, using only the eight
  `COMMON_FEATURES` sourced from FP1/FP2/FP3. The row-level `available_at`
  label means scheduled qualifying start; it does not prove each provider
  field's publication time or individual feature observation time.
- The manifest contains the feature/session/unit registry, cutoff metadata,
  forbidden target list, selected model, split counts, and dataset/prediction
  hashes. API validates the split/target contract and prediction hash before
  returning only predicted ranks and retrospective actual ranks.
- Model selection and metrics exactly reproduce Q-002: Ridge selected on
  2024 with MAE 2.8362; 2025 Ridge MAE 3.2433 vs FP3 3.3141. Paired delta
  −0.0708 positions, seeded 10,000-event bootstrap interval
  [−0.2934, +0.1587], crossing zero. No reliable gain or calibrated
  probability claim.
- Artifacts remain ignored under `data/processed/qualifying_backtest/`.
  Reproduction, API routes, local UI and known limits are in
  `PREDICTION_LAB.md`.

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

## R-008 — canonical-time telemetry comparison display

- Starting source SHA `10b53fd4905a6a22ad94ac249dc9632ce016845e`; this builds on
  R-007's pushed comparison artifact and source hashes. Implementation SHA
  `43e12407a7f13e02b0eb6d6a3fc0206442ca5816` is pushed to
  `origin/feat/foundation` and remote-verified at the same SHA.
- `GET /api/v1/replay/{slug}/telemetry/lap-comparison` reads only the expected
  ignored JSON artifact, validates its session/meeting, returns unavailable
  when absent and never calls OpenF1. The current full artifact is 847,619
  bytes; the plotted-field response is 200,119 bytes and retains source hashes.
- `TelemetryPanel` graphs speed A/B and B−A time versus estimated integrated
  distance. The cursor maps the canonical RaceState time through the reference
  lap's UTC start to `elapsed_a_seconds`, then interpolates distance/delta/
  speed. The jump action invokes the existing clock's seek. No second clock or
  surveyed-position claim is introduced.
- Evidence: two synthetic cursor unit tests, API fixture and unavailable-path
  tests, five JS unit tests, and nine Chromium tests using all three real replay
  packs. The browser case checks reference-start alignment, movement after a
  normal transport seek, hiding outside the reference lap and shared panel
  session time. Desktop chart screenshot was visually inspected; file path and
  exact commands are in `TEST_EVIDENCE.md`.
- Initial e2e failed because a generic `role=status` selector matched both the
  Monaco pit-coverage notice and the new static telemetry hint. The hint no
  longer uses that live status role; the existing pit assertion and complete
  suite pass. The first chart screenshot also showed the x-axis title
  overlapping distance ticks; SVG plotting area was given separate title space.
- This is a real-data view of one fixed Monza lap pair. More generated events,
  driver/lap selection, braking/gear/DRS charts, prediction outputs and
  uncertainty calibration remain unimplemented.

## R-009 — practice-phase qualifying snapshots

- **Question:** how does an event-grouped Q1-pace proxy compare with the best
  measured lap after FP1, after FP2 and before qualifying?
- **Source:** cached OpenF1 2023–2025, 1,038 driver-weekend rows across 52
  events, plus cached session start/end metadata. Dataset SHA-256
  `eef5a7277d2f62fdf263e94cadbc7a5f5c38cd6acdbea9dc00549d5caef37fd8`;
  canonical schedule SHA-256
  `af8ce323bb62591d925fded4fdaf696276921a305bb26fbc970573579d82734d`.
- **Protocol:** train on 2023, select each phase's practice baseline/Ridge/
  LightGBM by 2024 event-mean position MAE, evaluate once on 2025. Inputs are
  restricted to sessions completed by that phase. Rows without the measured
  baseline are removed. Shared preprocessing now uses that phase baseline
  rather than requiring FP3 availability; the experiment was regenerated after
  correcting this unintended future-session cohort restriction. Eligible
  train/validation/test rows are FP1 275/325/319, FP2 310/333/351 and pre-Q
  311/342/354 (16/18/18 events each). Cutoff values are scheduled practice ends; exact
  provider publication times are unknown. FastF1 2022 is excluded because its
  schedule was not available offline and this study keeps one provider across
  all three splits.
- **Result:** FP1 selects Ridge (2024 MAE 3.3744 vs FP1 3.5924); 2025 Ridge
  MAE 3.6736 vs FP1 3.7245, paired delta −0.0508 [−0.1676,+0.0628]. FP2
  selects Ridge (3.0788 vs 3.4291); 2025 Ridge 3.4827 vs FP2 3.6802,
  delta −0.1975 [−0.4056,+0.0218]. Pre-Q selects FP3 baseline (2.8975); 2025
  FP3 3.3141 vs Ridge 3.3100, delta −0.0041 [−0.2617,+0.2626]. All reported
  2025 Ridge intervals cross zero.
- **Evidence:** real cached historical evaluation plus synthetic schedule,
  cutoff, feature allowlist, chronological split, API and tampered-file tests;
  full Python/TypeScript/lint/type/browser evidence is in `TEST_EVIDENCE.md`.
- **Interpretation:** the early Ridge point estimates do not establish a
  reliable improvement; no probability calibration or deployment claim is
  made. The late Ridge point result does not change the FP3 validation winner.
  Q1 pace is a proxy and final qualifying classification is the label.
- **Artifacts and reproduction:** ignored output under
  `data/processed/qualifying_phases/`; exact commands and every artifact hash
  are in `QUALIFYING_PHASES.md`.

- **Publication:** implementation and required docs are in
  `8a2c06c898e93f0083058a7abb3bcbd5b3f9b606`, pushed normally to
  `origin/feat/foundation`; remote SHA matched exactly.

Phase rankings are relative to the eligible phase cohort: `predicted_rank`
and `actual_rank` are consecutive ranks within the retained drivers. The API
projects raw final classification into a separate `qualifying_position` for
retrospective scoring and omits raw `q1_gap_pct`/`final_position` field names.
The UI labels leader-hit and top-three-overlap metrics as eligible-cohort
metrics. Because phase cohorts differ, their MAEs alone do not establish
improvement as more weekend information arrives; that comparison requires a
shared-cohort analysis. Official classification and eligible rank can differ
when a classified driver lacks the measured practice baseline.

The phase artifact loader now checks per-driver coverage for every model,
rank permutations, manifest cohort counts, event metrics recomputed from
rank predictions, summary reconciliation, and bootstrap point estimates,
event counts and interval-bound validity. Synthetic regressions reject
a removed model row despite a refreshed checksum, an inconsistent summary
despite a refreshed checksum, a future-session feature registry, a source/Q
schedule mismatch and a cohort made too small after target filtering. These
checks validate artifact consistency; they do not prove provider publication
times or prediction calibration.

Final checks: 65 Python tests passed in 3.99 s (one existing warning); Ruff,
scoped four-file mypy, frontend build/lint and all 10 Chromium scenarios
passed (23.8 s for Chromium).


## R-010 — circuit trace selection and bounded browser observations (verified and published)

Question: can measured-source display geometry and selected-driver context be
made deterministic and auditable while observing synchronization and local
browser costs? Starting source `1a5b7b4fa64ae3ceab0ab7cb6957c2331a5ce7b6`.

Real cached OpenF1 races: Monza 2025, Monaco 2023 and Brazil 2024. The geometry
selector accepts 911/976, 1322/1516 and 1017/1137 candidate laps respectively;
selected source point counts are 168/191/166, with no inferred physical units.
The geometry audit records all rejected reasons, selected lap/sample hashes
and normalization/closure diagnostics. This tests trace completeness and
reproducibility; no independent surveyed reference was evaluated.

Opt-in browser protocol: one headless visible Chromium document, 1440×1000,
1× playback, four seconds per session plus race-start, forward/back ten-second
and session-end seeks. Baseline artifact:
`data/processed/browser_benchmarks/replay-performance-2026-10-16T16-32-00-868Z.json`.
No page exceptions or sampled clock mismatches; RAF p95 33.3/16.8/33.3 ms,
request p95 9.02/6.75/16.04 ms (Monza/Monaco/Brazil). The baseline predates
extracted map/trail source; final idle run is recorded below. No causal before/after speedup,
painted-FPS or leak inference follows from this protocol. Reproduce with
`cd apps/web && npm run benchmark:replay`; see the benchmark README and
`REPLAY_GEOMETRY_AND_PERFORMANCE.md`. Final full Python/static checks passed; commit/push remain pending.

Final idle browser artifact:
`data/processed/browser_benchmarks/replay-performance-2026-10-16T16-46-32-467Z.json`,
SHA-256 `2c16efc9ec43e43ed6dcd1b461afa7c1bee527ee09928cd2db89eac218764477`.
Monza/Monaco/Brazil callbacks/s: 59.08/59.54/60.00; interval p95:
16.7/16.8/16.7 ms; local state-request p95: 11.49/8.89/7.05 ms.
All eight panel clocks agreed, no long-task entries; twelve seek observations
range 47.30–171.34 ms. An intermediate 16:45 report overlapped validator
workload; the 16:46 run was idle. These are bounded local development
observations; differing source/features/packs preclude causal speedup claims.

Offline checks: `.venv/bin/python -m f1_racelab.session.openf1_replay --all --offline`;
`.venv/bin/python -m f1_racelab.session.validate_replay --all`;
`.venv/bin/python -m f1_racelab.session.validate_context --all`. Monza/Monaco/
Brazil replay checks pass 4,120/6,149/4,893 cases plus 200 shuffled seeks each;
seek p50/p95 ms are 1.356/3.360, 1.444/3.617 and 1.319/2.962.
Context validation and 360 real source-trail QA probes pass. Browser
`npm run test:e2e`: 11 scenarios passed in 33 seconds.

Final integrated checks (all exit 0): `uv run pytest -q` — 92 passed in
6.87 s, one upstream Starlette/httpx deprecation warning;
`uv run ruff check src/f1_racelab tests` — clean;
`uv run mypy src/f1_racelab/session src/f1_racelab/api.py src/f1_racelab/data/openf1_qualifying.py --ignore-missing-imports`
— 16 source files, no issues. In `apps/web`, `npm run test:unit` — 8 passed;
`npm run build` and `npm run lint` passed. Build JS is 434.63 KB
(142.33 KB gzip), CSS 78.65 KB (15.55 KB gzip). Milestone source commit `132e3aaff34f4c805485e54bbef24f39025aab03` was pushed normally to
`origin/feat/foundation`; `git ls-remote` returned the identical SHA.


## R-011 — three-session six-channel distance comparison (verified and published)

Starting source `acff2d86ba79ef9dc23c20ac3070d54a989bab8e`. This is an engineering/data-quality
extension, not a predictive model experiment. Catalog pairs are Monza 2025
#1 L50 vs #4 L50, Monaco 2023 #1 L40 vs #31 L40 and Brazil 2024 #1 L52 vs
#31 L52. Source lap durations, integrated metres, 5 m grid counts, maximum gaps,
source hashes and chart paths are recorded in the regenerated QA artifacts.

The comparison integrates speed and aligns at a shared distance from approximate
lap starts. Six channels retain provider/null semantics, and delta remains
elapsed B−A. Distances are estimated and source conditions are not controlled;
Monaco lacks pit data. No clean-lap, equal-condition or general performance
claim follows. Offline reproduction and contracts/API/UI checks pass;
normal push to `origin/feat/foundation` was verified at the correction SHA below.

Verified reproduction: `uv run python -m f1_racelab.telemetry.openf1_lap_comparison --all --offline`
completed from cached data; log `data/processed/telemetry_comparisons/catalog_build.log`.
JSON, `.qa.json` and PNG files share basenames under that directory:
`monza-2025_driver_1_lap_50_vs_4_lap_50`,
`monaco-2023_driver_1_lap_40_vs_31_lap_40`,
`brazil-2024_driver_1_lap_52_vs_31_lap_52`.

| Session | JSON bytes | 5 m grid points | Common end m | End-grid B−A s | Maximum source gaps A/B s | Pit source |
|---|---:|---:|---:|---:|---|---|
| Monza | 847,715 | 1,150 | 5,746.06 | −0.234 | 0.799 / 0.799 | Cached, checked |
| Monaco | 547,035 | 656 | 3,279.04 | −0.184 | 0.640 / 0.520 | Unavailable; pit-in unverified |
| Brazil | 669,987 | 849 | 4,241.19 | +0.252 | 0.560 / 0.560 | Cached, checked |

All six channels are nonnull at every aligned grid point for both laps in
these artifacts; null handling remains tested for incomplete future inputs.
Source hashes were checked directly against 4/3/4 raw cached resources
(Monza/Monaco/Brazil). Artifact SHA-256 values:

- Monza: `9bc3aa5ea7750541deff8d10a4f84f8f228e0c5e372f85692e1923821d8dfea6`.
- Monaco: `5ac531b5e3ada9e3c90a3e0e86e27c169283163ab5328904d2b71d47f558b0d5`.
- Brazil: `774191e671021aac0519452d771f9395d68e5ae1a6f4b929ec03b8f0a2c33998`.

Final checks: `uv run pytest -q` — 104 passed in 4.26 s, one upstream
Starlette/httpx warning; `uv run ruff check src/f1_racelab tests` passed.
`uv run mypy src/f1_racelab/telemetry src/f1_racelab/session src/f1_racelab/api.py --ignore-missing-imports`
passed, 20 source files. In `apps/web`, `npm run test:unit` — 13 passed (after review correction);
`npm run build` and `npm run lint` passed. Build JS 452.63 KB (148.05 KB gzip),
CSS 79.61 KB (15.71 KB gzip). `npm run test:e2e` — 14 passed in 39.2 s,
including exact six-channel cursor assertions for all three races and mobile;
Monaco/Brazil PNG plots and mobile panel screenshot were visually inspected. Source milestone `5bce32930dfaa802c6ec1c7a54e1a0f7ffce0cf9` was pushed;
corrective review publication is pending.


### 2026-10-16 — telemetry UI review correction

Published P3 source: `5bce32930dfaa802c6ec1c7a54e1a0f7ffce0cf9`. A subsequent
UI/source review found a discrete trace ended at the previous known point
instead of extending its held value to the first missing observation. The path
now draws that final horizontal step to the missing grid point, then breaks;
it does not bridge the unknown interval. A gear regression checks this behavior.
The review also found delta-axis tick text could crowd the zero label. Nearby
text within 14 SVG pixels is suppressed while its grid line remains visible.
These are display corrections; source comparison artifacts and hashes are
unchanged.

Current corrective checks: `cd apps/web && npm run test:unit` — 13 passed;
`npm run build` and `npm run lint` passed. Latest JS is 452.63 KB (148.05 KB
gzip), CSS unchanged at 79.61 KB (15.71 KB gzip). Full
`cd apps/web && npm run test:e2e` passed 14/14 in 36.5 s with both UI fixes.
After cleanup, `npx playwright test --grep='six telemetry channels'` passed
3/3 in 14.4 s. The full suite covers the fixes before cleanup; the targeted
three-race run verifies the subsequent cleanup. Corrective source commit/push
remains pending. Prior 14-scenario/39.2-second evidence applies to the original
published P3 source.

### P3 publication proof

Implementation commit `5bce32930dfaa802c6ec1c7a54e1a0f7ffce0cf9` expanded the catalog and channel UI. Review
correction commit `9a13f6eef679c417fc3bc6a8beddd320504dbc06` fixed held-value traces at missing discrete samples
and crowded mobile delta labels. Both are on `origin/feat/foundation`;
`git ls-remote origin refs/heads/feat/foundation` returned `9a13f6eef679c417fc3bc6a8beddd320504dbc06`. Git
used Aymen Jedidi's repository identity, with no assistant coauthor. The two
unrelated user helpers under `ml/features/` remain untracked and untouched.

## EXP-WF-01 — walk-forward ensemble with rank probabilities (2026-10-29)

Candidate `ensemble` pre-declared; baseline `latest_practice`; 12 warm-up events,
evaluated 2024–2025 (36 events); dataset SHA `eef5a727…37fd8`; predictions SHA
`4f2b5521…133a2`; seed 42; 4,000 draws. Pooled MAE delta −0.274 [−0.544, −0.042];
Brier pole 0.0374 vs 0.0484; top-3 0.0807 vs 0.1295; interval coverage 89.5% (80% nominal).
Pole-hit not improved in 2025. Details: `ML_WALKFORWARD.md`.

## EXP-WF-02 — 2026 regime-change evaluation (2026-10-29)
Same frozen pipeline as EXP-WF-01, 12 completed 2026 events. Ensemble vs latest practice
+0.052 [−0.030, +0.136] (neutral); Ridge/LambdaRank worse. Pooled 48 events −0.192 [−0.404, −0.015].
Dataset SHA `74455574…2d3e4`. Negative transfer result retained deliberately.

## EXP-PACE-01 — next-lap pace, expanding-window by race (2026-10-29)
Dataset fingerprint in `data/processed/race_pace/summary.json`; seed 42; LightGBM MAE 0.575 vs anchor 0.682;
interval coverage 75.2% (80% nominal). See `docs/research/RACE_PACE_INTELLIGENCE.md`.
