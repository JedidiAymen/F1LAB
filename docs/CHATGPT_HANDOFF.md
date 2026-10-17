# F1LAB handoff for the next ChatGPT session

**Status at 2026-10-17 UTC:** qualifying research benchmark complete; a
historical Prediction Lab is now integrated; three real historical race packs
build, reconcile and play through one local API/UI:
Monza 2025, Monaco 2023 and Brazil 2024. Stored packs/events are schema 2;
current `RaceState` output is schema 3 with source-time weather, conservative
global track signals and as-of tyre stint history. Fifteen actual Chromium
browser scenarios pass (including one that selects a new driver/lap pair from
the UI), and desktop/mobile screenshots were inspected. P1/P2
remain partial. Versioned approximate driving-line geometry, a selected-driver
12-second trail/direction and fingerprinted local browser observations now
exist; physical circuit geometry remains incomplete. Three-race six-channel
telemetry comparisons (Monza/Monaco/Brazil) now expose speed, throttle, brake
source value, RPM, gear and DRS plus persistent time delta through the local
API/UI. A full per-session, per-driver, per-lap lap library is built offline
from cached source; arbitrary driver/lap pairs can be selected and applied
through the UI without changing the replay clock. P3/P4 remain partial; a
three-phase historical qualifying lab is integrated, while exact feature
publication timestamps, calibration and cross-year sector comparisons remain
incomplete. The overall product goal is far from complete.
Telemetry source starts at `89351502ccb6389c25886d18022430f2ce6319f8`, with comparison
foundation commit `2ac01012c780552f26bd9504f88c9cac87541000` and docs checkpoint
`10b53fd4905a6a22ad94ac249dc9632ce016845e` pushed and remote-verified. The
current UI integration starts from that checkpoint; commit
`43e12407a7f13e02b0eb6d6a3fc0206442ca5816` is pushed to
`origin/feat/foundation` and remote-verified. Git uses the repository's Aymen
Jedidi identity and no assistant coauthor trailers. Two unrelated untracked
`ml/features/` helpers remain untouched.

The latest Prediction Lab implementation is commit
`8a2c06c898e93f0083058a7abb3bcbd5b3f9b606`, pushed and remote-verified on
`origin/feat/foundation`; the owner's identity is the author.

The lap library and selection UI implementation is commit
`32db149737d56d5e32147fdde5080820cf9eb499`, pushed and remote-verified on
`origin/feat/foundation`.

## What exists and what does not

- **Done before this run:** Monza 2025 practice/qualifying exploration; Sprint 2
  FastF1 feature builder, chronological backtest code and synthetic tests.
  The saved single-Monza result (MAE 2.70 positions, Spearman 0.823) is a
  one-event comparison, not a generalization score.
- **Implemented in this run:** project-scoped pytest collection, a public
  OpenF1 historical adapter with raw response cache and request pacing,
  common-source qualifying feature set, provider-labelled dataset merge,
  event-paired bootstrap and coverage outputs, and normalization tests.
- **Done in this run:** OpenF1 ingestion for 2023–2025, merged 2022–2025
  dataset, real 2024 model selection and 2025 held-out evaluation, five-model
  form ablation, one-event provider overlap audit, one manual historical-form
  trace, and executed notebook chart. See `EXPERIMENT_REGISTER.md`.
- **Replay reference gate verified:** Python Pydantic events/state, pure
  ordered reducer, `RaceSource`, indexed/checkpointed `ReplaySource` and
  audited session catalog. Schema 2 packs/events remain readable; emitted
  `RaceState` is schema 3. The
  three current packs contain 5,654 events, including 350 weather observations
  and 14 global track signals, plus 799,422 retained source XY points and 148
  normalized source stint events.
  Available final positions and lap totals reconcile; 15,162 event-boundary/
  regular cutoffs and 600 shuffled jumps pass. `REPLAY_GOLDEN_SESSIONS.md` and
  `REPLAY_CONTEXT.md` contain per-race hashes, source audit and limits.
- **Partial Race Control UI:** local catalog and per-session state API;
  session picker, anchored central clock, 0.25×–16×, exact seek/control and
  race-start jumps, timing tower, driver focus, approximate 2D map, full
  prior control feed, missing-source indicators, weather freshness and rainfall
  change navigation, conservative track-status summary, source-time tyre
  history, playback-only map transforms, mobile transport and the Monza
  telemetry comparison. Time-dependent panels share one returned state; the
  telemetry plot reads a separate local artifact while its crosshair follows
  that state's session time. React polls at 5 Hz rather than rerendering the
  whole tree on every animation frame.
- **Source quality:** Monaco `pit` is HTTP 404, so capability is absent and
  UI displays unavailable. Brazil STR's null stint start is counted/skipped;
  HUL's null DSQ lap total is excluded from that QA comparison. Global
  SC/VSC/red-flag messages remain preserved. Context audit matches all 350
  retained weather observations to cached raw records, performs 700
  before/exact-time checks, and verifies 14 reviewed global signal boundaries.
  Rainfall reports are presence only; no wet-surface or intensity estimate is
  shown. Unknown restarts and ending notices do not imply green.
- **Partial:** Three-race six-channel telemetry with a shared-clock cursor.
  Per-session lap library (content-addressed gzip, manifest validated against
  source hashes) supports arbitrary driver/lap selection from the UI without
  contacting any provider. Monza has 2 available drivers (VER/NOR) with 22/23
  cached laps; Monaco and Brazil each have 2 available drivers (VER/SAI or
  VER/OCO) with ~45–61 laps each. Other drivers lack cached car_data; their
  unavailable status is labelled. Distance is speed-integrated and estimated.
- **Not done:** after-FP1/after-FP2 forecasts, per-feature observation-time
  lineage and probability calibration; surveyed/full geometry and measured
  rendering performance; retirement-time handling; cross-year/sector
  telemetry comparisons; wider driver car_data caching; strategy, what-if,
  live/radio, 3D, CI and storage/schema-export hardening. The full product
  goal remains active.

## Why the provider changed

The initial local `qualifying_2022_2023_2024_2025.parquet` had only 360 rows:
17 conventional 2022 weekends plus 2025 Monza. The prior ingestion log hit
FastF1's 500 calls/hour limit. This run completed two more cached 2022
weekends, but uncached 2023 F1 timing failed; a direct 2023 Bahrain timing URL
returned HTTP 401. OpenF1 documents public historical data from 2023 onward
and returned Q phase times, FP3 results and driver/team identity. We preserve
the original dataset and build a separate source-labelled one. See
`DATA_CONTRACTS.md`, `DECISIONS.md` and [OpenF1 docs](https://openf1.org/docs/).

## Architecture and source map

`src/f1_racelab/data/fastf1_source.py` configures the local cache;
`features/qualifying.py` computes practice rows and post-Q labels;
`data/qualifying_dataset.py` stores FastF1 event Parquets;
`data/openf1_qualifying.py` stores OpenF1 JSON and normalizes 2023–2025;
`data/mixed_qualifying.py` combines providers;
`features/historical_qualifying.py` creates strictly lagged driver/team form;
`models/qualifying_backtest.py` and `models/qualifying_ablation.py` fit and
evaluate five candidate rankings. `IMPLEMENTATION_ATLAS.md` describes inputs,
outputs, formulas, tests and caveats per function. `ARCHITECTURE.md` diagrams
the actual data flow and partial unified replay architecture. The new
`session/contracts.py`, `session/reducer.py`, `session/source.py`,
`session/openf1_replay.py`, `session/replay_source.py` and
`session/validate_replay.py` provide the first canonical, real-data replay
path. `session/catalog.py` defines the three supported specifications.
`session/openf1_context.py` validates provider weather and cautiously maps
global status phrases; `session/validate_context.py` independently checks raw
cache lineage and source-time boundaries. The schema and limits are documented
in `REPLAY_CONTEXT.md`. The new `telemetry/contracts.py`,
`telemetry/distance_alignment.py` and
`telemetry/openf1_lap_comparison.py` define and reproduce the first
distance-aligned lap comparison. `api.py` serves the validated local artifact;
`web/components/TelemetryPanel.tsx` draws its speed/delta graph and derives its
crosshair from the shared replay time. Detailed source hashes, API behavior and
limitations are in `DISTANCE_ALIGNED_TELEMETRY.md`.
Compressed packs/manifests/QA stay ignored under `data/processed/replay_packs/`.
`src/f1_racelab/api.py` caches sources by session slug;
`apps/web/src/App.tsx` and `App.css` render the UI with
`src/lib/playback-clock.ts` as the browser clock.
`tests/test_replay_api.py` tests cross-session isolation synthetically;
`apps/web/e2e/replay.spec.ts` tests real local packs in Chromium.

## Reproduction and evidence

```bash
uv sync --dev
.venv/bin/pytest -q
.venv/bin/python -m f1_racelab.data.openf1_qualifying --years 2023 2024 2025
.venv/bin/python -m f1_racelab.data.mixed_qualifying
.venv/bin/python -m f1_racelab.models.qualifying_backtest --dataset data/processed/qualifying_mixed_2022_2023_2024_2025.parquet --feature-set common
.venv/bin/python -m f1_racelab.models.qualifying_ablation --dataset data/processed/qualifying_mixed_2022_2023_2024_2025.parquet --feature-set common
.venv/bin/python -m f1_racelab.session.openf1_sample
.venv/bin/python -m f1_racelab.session.openf1_replay
.venv/bin/python -m f1_racelab.session.openf1_replay --session monaco-2023
.venv/bin/python -m f1_racelab.session.openf1_replay --session brazil-2024
.venv/bin/python -m f1_racelab.session.validate_replay --all
.venv/bin/python -m f1_racelab.session.validate_context --all
.venv/bin/python -m f1_racelab.telemetry.openf1_lap_comparison
.venv/bin/python -m f1_racelab.session.audit_candidates
.venv/bin/uvicorn f1_racelab.api:app --host 127.0.0.1 --port 8000
cd apps/web && npm ci && npm run dev -- --host 127.0.0.1
```

Start the API and frontend commands in separate terminals. Choose a session,
jump to race start, play/pause/seek and select a driver. In Monaco, select the
rain report at 4,363.946 s, seek to the dry report at 5,923.949 s, then seek
back; weather follows the canonical replay clock. In Brazil, inspect VSC ending
at 3,590 s, red at 4,042 s, session restart at 5,520.39 s (shown
RUNNING / UNKNOWN), and “SAFETY CAR IN THIS LAP” at 6,484 s. Monaco shows
unavailable pit records. Restart the API after rebuilding packs.

From `apps/web`, `npx playwright install chromium`,
`npm run test:unit` and `npm run test:e2e` run the clock and actual browser
checks. The browser suite launches/cleans up its own local servers on
8011/5181, requires all three packs and performs no provider downloads.
It passed **8/8**; screenshots under ignored
`data/processed/browser_tests/results/` were visually inspected at
desktop 1440×1000 and mobile 390×844. No measured 60 Hz/FPS claim is made.

The latest full Python test run passed **51/51** with one existing deprecation
warning; three JS unit tests passed, Ruff passed, mypy passed for 13 session/API
source files, and web ESLint/TypeScript/Vite build passed. The eight-case
Chromium suite passes; the latest source-timed stint and playback screenshots
were inspected. `npm ci` uses a
tracked lockfile.
Exact commands are
in `TEST_EVIDENCE.md`. Fixture tests are separate from the real provider data
and model experiment. Generated
datasets and metrics are under ignored `data/processed/`; inspect
`qualifying_mixed_manifest.json`, ingestion CSV, `qualifying_backtest/` and
`qualifying_ablation/`. The mixed file has 71 conventional weekends and 1,418
source rows, with 35/18/18 eligible train/validation/test events and
684/342/354 evaluated rows. Its SHA-256 is
`eef5a7277d2f62fdf263e94cadbc7a5f5c38cd6acdbea9dc00549d5caef37fd8`.
Ridge won on 2024 MAE (2.8362 vs FP3 2.8975). Its held-out 2025 MAE was
3.2433 vs FP3 3.3141, with paired event delta -0.0708 and 95% bootstrap
interval [-0.2934, +0.1587]. The interval crosses zero, so no reliable
improvement is claimed.

Monza/Monaco/Brazil match 18/18, 19/19 and 15/15 classified positions and
20/20, 20/20 and 19/19 available lap totals; Brazil has one unavailable DSQ
lap-total label. The validator compares all discrete/audit fields through
15,162 event-boundary/regular cutoffs plus 600 seed-42 shuffled revisits.
It preserves a measured first coordinate for 59 source-driver series;
Brazil ALB has no retained location series. Latest per-race p50/p95 seek ms:
Monza 1.301/2.814, Monaco 1.376/3.229, Brazil 1.236/2.734.
Full artifact hashes and limits are in `REPLAY_GOLDEN_SESSIONS.md`;
the combined local report is `replay_packs/golden_sessions.qa.json`.
Packs change hashes on rebuild because ingest/gzip timestamps change.

## Latest milestone — source-time stints and map motion

Implementation commit `4a0434aea67ff99a2f949abc08babdcbf0b50578` is pushed
and remote-verified.

`TyreStintState` carries source event/time, compound, one-based lap range,
quality, start tyre age and closing event. A lap event advances only its open
stint; a later start closes it at the latest completed lap. The reducer does
not copy provider `lap_end` into an earlier start, preventing future leakage.
Monza/Monaco/Brazil retain 39/57/52 normalized stints (148 total); Brazil's
two unusable source start rows remain counted in coverage. Monaco HUL/car 27
has two distinct lap-1 starts, both retained and visibly labelled as an
overlap.

The UI lists stints for the focused driver at the shared canonical state time.
Map SVG transforms use a 180 ms CSS transition only during playback when a
forward state sample is at most four seconds ahead. Paused exact seeks,
including small forward seeks, reverse seeks and reduced motion are immediate.
This is visual interpolation; the API remains 5 Hz and coordinates remain
approximate.

Modified source: `contracts.py`, `reducer.py`, `validate_replay.py`,
`App.tsx`, `App.css`, `session-context.ts`, new `StintPanel.tsx`, their
reducer/API/context tests and `apps/web/e2e/replay.spec.ts`. Implementation
details, exact command output, OpenF1 source/license links, screenshot paths,
initial browser-test failure, limitations and reproduction are in
`REPLAY_STINTS_AND_MOTION.md`.

Latest verification: 51 Python tests; Ruff; 13-file session/API mypy; 3 JS
unit tests; web ESLint and TypeScript/Vite build; 8/8 Chromium tests. The replay
validator checks 15,162 cutoffs and 600 shuffled revisits; the context auditor
checks 700 weather cutoffs and 14 track boundaries. The end state reports
39/57/52 stint segments. No model-performance, 60 Hz, tyre-grip or live-data
claim is made.

## Latest milestone — shared-clock telemetry comparison (partial P3)

The comparison foundation starts at source SHA
`89351502ccb6389c25886d18022430f2ce6319f8`; commit
`2ac01012c780552f26bd9504f88c9cac87541000` is pushed. The UI/API integration
starts from docs checkpoint `10b53fd4905a6a22ad94ac249dc9632ce016845e`;
implementation commit `43e12407a7f13e02b0eb6d6a3fc0206442ca5816` is pushed and
remote-verified. Every commit uses the Aymen Jedidi repository identity and
has no assistant coauthor trailer.

OpenF1 session 9912 VER #1 L50 and NOR #4 L50 contain 318 and 309 in-lap
samples, bounded to 320 and 311 points. Trapezoidal speed integration yields
estimated distances 5,746.062 m and 5,751.324 m. A 5 m common grid has 1,150
points; B−A delta ranges −0.374 to +0.212 s and ends at −0.234 s. This is a
two-lap descriptive result, not a performance claim. Source timestamps and
distance are approximate; source query hashes and the full raw artifact remain
available locally.

The API serves a projected 200,119-byte chart payload from the 847,619-byte
hash-validated ignored artifact and makes no provider requests. The web panel
shows both speeds and B−A time. Its cursor derives from the same canonical
`RaceState.session_time_seconds` used by map and timing; exact seeking, playback
and out-of-lap hiding pass a real Chromium test. Python tests pass 57/57 with
one existing deprecation warning; Ruff and 18-file mypy pass; five JS unit
tests and nine Chromium tests pass; frontend lint and build pass. The chart was
visually inspected at the reference lap start. Reproduction commands, source
links, formulas, failure/fix history and artifact hashes are in
`DISTANCE_ALIGNED_TELEMETRY.md` and `TEST_EVIDENCE.md`.

## Latest milestone — historical qualifying Prediction Lab (partial P4)

Starting source SHA is `bd67b199a189fed6adc604a5130638b9c34b18c6` on the
cleanly synchronized `feat/foundation` branch, apart from the two preserved
untracked user helpers. This milestone adds a source-session feature registry
and cutoff audit, a SHA-verified local artifact API, an integrated historical
Prediction Lab page, API/UI tests, and the full documentation set. Implementation
and required docs are committed together in `9f928361c9c7fdf59a2e685dc2994137cf942e35`.
It is pushed to `origin/feat/foundation`; `git ls-remote` returned the exact
same SHA. A follow-up documentation commit records the verification. The
repository owner is the commit author; there is no assistant coauthor trailer.

The page is historical, not live. It reads the existing 71-event mixed-source
dataset benchmark artifacts. Inputs are eight FP1/FP2/FP3 pace features; Ridge
is selected with 2024 validation and 2025 remains the held-out set. The API
returns each model's predicted rank and actual rank for retrospective
evaluation, while omitting Q1 target values and raw classification fields.
The actual score is labeled retrospective in the UI.

The audit records 1,418 scheduled qualifying-start rows and the allowed source
sessions/units. Individual practice feature timestamps and provider
publication times are absent, so this cannot establish their exact
availability instant. The UI states this directly. Dataset hash:
`eef5a7277d2f62fdf263e94cadbc7a5f5c38cd6acdbea9dc00549d5caef37fd8`;
regenerated predictions hash:
`88195b26ef5f3f5ab86d7b8a906233e7b0c6ef1af05401fc9f74d3afe91d011b`.
2025 Ridge MAE is 3.2433 versus FP3 at 3.3141; paired delta is −0.0708 with
95% interval [−0.2934,+0.1587], which crosses zero. There is no reliable
superiority or probability claim. Exact reproduction and tests are in
`PREDICTION_LAB.md` and `TEST_EVIDENCE.md`.

## Latest milestone — phase-aware qualifying snapshots (partial M5/P4)

Starting source SHA: `d60c36f77295075bd50a1950ccabefc7eb5022b9`.
Implementation and required documentation are committed together in
`8a2c06c898e93f0083058a7abb3bcbd5b3f9b606`, pushed normally to
`origin/feat/foundation`; `git ls-remote` returned the exact same SHA.
The owner is the author and there is no assistant coauthor trailer. This
adds three retrospective forecast moments to the Prediction Lab: after FP1,
after FP2 and before qualifying. The API validates phase feature allowlists
and checksums and returns predicted ranks, actual ranks for scoring, and the
event's scheduled practice-end cutoff. It makes no provider request.

The experiment filters the 1,418-row mixed-source dataset to its 1,038 OpenF1
rows from 2023–2025. Dataset SHA-256 is
`eef5a7277d2f62fdf263e94cadbc7a5f5c38cd6acdbea9dc00549d5caef37fd8`;
canonical cached schedule SHA-256 is
`af8ce323bb62591d925fded4fdaf696276921a305bb26fbc970573579d82734d`.
FastF1's 2022 schedule was unavailable offline, so the phase study keeps one
provider across all splits: 2023 train, 2024 validation/model selection and
2025 holdout. This leaves 16 training weekends.

| Phase | Eligible train / validation / test rows | 2025 selected/baseline MAE | Ridge − baseline and 95% event interval |
|---|---:|---:|---:|
| After FP1 | 275 / 325 / 319 (16 / 18 / 18 events) | Ridge 3.6736; FP1 3.7245 | −0.0508 [−0.1676,+0.0628] |
| After FP2 | 310 / 333 / 351 (16 / 18 / 18 events) | Ridge 3.4827; FP2 3.6802 | −0.1975 [−0.4056,+0.0218] |
| Before qualifying | 311 / 342 / 354 (16 / 18 / 18 events) | FP3 3.3141; Ridge 3.3100 | −0.0041 [−0.2617,+0.2626] |

Ridge is selected on 2024 for FP1 and FP2; FP3 baseline wins pre-Q validation.
Every reported 2025 Ridge comparison interval crosses zero. Missing measured
practice baselines are excluded within their phase; no lap pace is imputed.
An audit removed an unintended shared-preprocessing FP3 requirement from the
earlier phases; the experiment and metrics above were regenerated using only
the selected phase baseline for cohort eligibility.
The cutoff is scheduled practice end, **not** the exact provider publication
time. This remains offline historical work, not a live prediction claim.

Verification: 65 Python tests passed in 3.99 s (one existing Starlette/httpx warning),
Ruff and scoped mypy passed, 5 frontend unit tests passed, TypeScript/Vite
build and ESLint passed, and 10 Chromium tests passed in 23.8 s. The screenshot
is `data/processed/browser_tests/results/replay-Prediction-Lab-labe-7122e-tes-validation-from-holdout-chromium/prediction-lab-holdout.png`.
Exact commands, complete metric tables and generated artifact hashes are in
`QUALIFYING_PHASES.md` and `TEST_EVIDENCE.md`.

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

## Known failure and risk matrix

| Issue | Evidence | Effect / next handling |
|---|---|---|
| FastF1 uncached archive access | F1 timing URL HTTP 401 | Use OpenF1 historical data, keep source labels and raw hashes |
| Mixed provider best-lap definitions | FastF1 lap filter vs OpenF1 `session_result`; 2025 Monza matched exactly on available pairs | Extend overlap audit beyond one event; use common eight fields |
| Q1 pace proxy vs final Q classification | Pipeline target/label definitions | Report Q1 pace separately from final order; the phase model is retrospective and not a full Q1/Q2/Q3 simulator |
| Practice result timing | OpenF1 scheduled date_end is available, but per-result publication timestamps are absent | Call the cutoff scheduled practice end; do not claim exact as-of/live availability |
| Limited uncertainty evidence | 18 held-out events; paired interval crosses zero | Avoid superiority or deployment claims |
| Team names and driver acronyms as identifiers | Current row schema | Audit transfers, substitutions and renamed constructors before production |
| Approximate replay geometry | OpenF1 positions have arbitrary origin and unknown unit; trace is VER lap 3 | Show coordinate/quality labels; do not call the trace surveyed or precise |
| Repeated stopped-car locations | Provider may repeat constant points after a DNF/DNS | 15-second identical-coordinate streak now hides the map point; heuristic may hide a legitimate stationary car; no retirement time inferred |
| Optional historical pit resource | Monaco 2023 `pit` HTTP 404 | Builder/state/UI now expose missing capability; pit duration/count truth remains unavailable |
| Global track status | 14 accepted signals across three sessions; endings/restarts remain non-green meanings | Other message phrases are unmapped; status can remain at the latest source signal |
| Weather interpretation | 350 OpenF1 historical readings; rainfall is presence only and 120 s UI freshness | Do not infer wet grip, intensity or conditions between observations; weather calibration remains future work |
| Partial motion and geometry | Backend state is sampled at 5 Hz; a short transform runs only during playback; outlines are one measured lap trace | Browser checks pass; surveyed geometry and measured rendering/performance coverage remain |
| Estimated telemetry axis | Integrated distance from sampled speed and approximate lap start; one Monza pair in the UI | Cursor follows canonical replay time; axis is not GPS/surveyed distance, and broader event/channel coverage remains |
| Browser dependency audit | Production audit clean; full audit has seven high advisories in shadcn development CLI chain | CLI is dev-only; suggested fix is major downgrade and was not applied |
| Null Brazil records | STR stint has no start, HUL DSQ lap total null, ALB location empty | Preserve gaps and coverage; do not inject final labels or synthetic coordinates |

## Next three actions

1. Continue P2 with fuller circuit geometry and measured rendering performance.
2. Expand shared-clock telemetry beyond the Monza reference pair and broaden
   qualifying provider overlap checks.
3. Preserve feature publication timestamps and validate phase snapshots with
   a 2026 walk-forward before calibrated prediction research; then build the
   independent strategy simulator, what-if, live and 3D phases in locked order.

For tutoring, read `QUALIFYING_PHASES.md`, `PREDICTION_LAB.md`,
`AGENT_WORKLOG.md`, `IMPLEMENTATION_ATLAS.md`, `ML_EVALUATION.md`,
`TEST_EVIDENCE.md`, `DATA_CONTRACTS.md`, `DECISIONS.md` and
`GLOSSARY_FOR_LEARNING.md` after this page. The locked scope remains
`SOL61_MASTER_EXECUTION.md`; a passing ML benchmark will not finish it.


## Latest P2 worktree — geometry, focused trail and observations

Starting source/last published checkpoint: `1a5b7b4fa64ae3ceab0ab7cb6957c2331a5ce7b6` on
`feat/foundation`. The implementation is committed as `132e3aaff34f4c805485e54bbef24f39025aab03`, pushed normally to `origin/feat/foundation` and remote-verified.
P1/P2 remain partial; strategy, what-if, live/radio and 3D remain not started.

Done in source: typed approximate `CircuitGeometry` selection from one complete
measured driving line with source/lap hashes, normalization, diagnostics and
explicit missing physical dimensions; three real cached packs rebuilt; extracted
memoized SVG map; selected 12-second source trail and estimated displacement
heading in the canonical state response via optional `focus_driver`. Key files:
`session/geometry.py`, `session/location_history.py`, `session/openf1_replay.py`,
`api.py`, `components/TrackMap.tsx`, `lib/circuit-geometry.ts` and
`apps/web/benchmarks/`. Full file/algorithm map is in `IMPLEMENTATION_ATLAS.md`.

Real trace audit `data/processed/replay_packs/geometry_audit.json` selects
Monza driver 30 lap 7 (168 source points), Monaco driver 16 lap 54 (191), and
Brazil driver 31 lap 52 (166). Coordinates/arc lengths are unknown provider
units. The source-lap origin is estimated; pit lane, physical dimensions,
surveyed geometry and official timing line are not implemented. The trail
ends at the existing canonical position and splits dropouts/jumps; its arrow
shows recent displacement, not measured chassis orientation.

Current checks: 13 new geometry tests plus 5 existing focused tests and 8
frontend unit tests pass; frontend build/lint pass. All 11 browser scenarios
pass in 33 seconds. Offline CLI rebuild, replay/context validators and 360 real
trail probes pass. Final full Python/static verification passed (92 Python tests). Baseline browser
report `data/processed/browser_benchmarks/replay-performance-2026-10-16T16-32-00-868Z.json`
records no page exceptions or sampled panel clock disagreements over four
seconds/session. RAF p95 33.3/16.8/33.3 ms and request p95 9.02/6.75/16.04 ms
are Monza/Monaco/Brazil local development observations. Baseline predates final
map/trail source; no painted FPS or causal improvement claim follows.

Reproduction: existing local API/web launch instructions still apply. Choose
one of three supported races, select a driver, play/pause and seek; the map
shows a quality-marked trailing path and movement arrow when connected current
movement exists. Opt into observations with `cd apps/web && npm run benchmark:replay`.
See `REPLAY_GEOMETRY_AND_PERFORMANCE.md` for commands, provenance, evidence and
remaining gaps. Next: expand telemetry coverage and evaluate
licensed physical circuit geometry sources before declaring the P2 gate done.

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

Temporal detail: measured trail vertices are at or before requested time `t`.
The canonical estimated endpoint may use a later source sample as the existing
historical interpolation bracket; this is retrospective reconstruction, not
proof that data had been published live by `t`. Without `focus_driver`, the API
returns strict canonical `RaceState` schema 3. Focused `location_context` is a
view extension of that same state response; it does not change the canonical
state schema or create another position/clock authority.

Final integrated checks (all exit 0): `uv run pytest -q` — 92 passed in
6.87 s, one upstream Starlette/httpx deprecation warning;
`uv run ruff check src/f1_racelab tests` — clean;
`uv run mypy src/f1_racelab/session src/f1_racelab/api.py src/f1_racelab/data/openf1_qualifying.py --ignore-missing-imports`
— 16 source files, no issues. In `apps/web`, `npm run test:unit` — 8 passed;
`npm run build` and `npm run lint` passed. Build JS is 434.63 KB
(142.33 KB gzip), CSS 78.65 KB (15.55 KB gzip). Milestone source commit `132e3aaff34f4c805485e54bbef24f39025aab03` was pushed normally to
`origin/feat/foundation`; `git ls-remote` returned the identical SHA.


### P2 publication proof

Implementation commit `132e3aaff34f4c805485e54bbef24f39025aab03` includes source, tests and all eight
required milestone documents. `git push origin feat/foundation` succeeded;
`git ls-remote origin refs/heads/feat/foundation` returned the same SHA.
Author: Aymen Jedidi; no assistant coauthor. Generated evidence remains local
and ignored; the two unrelated user feature helpers remain untouched.
Next: extend shared-clock telemetry beyond the Monza reference pair.


## Published P3 checkpoint — three-session six-channel telemetry

Starting published source `acff2d86ba79ef9dc23c20ac3070d54a989bab8e`, branch `feat/foundation`.
Implementation and correction are committed and remote-verified on `feat/foundation`.
The previous checkpoint's 92 Python / 8 frontend unit / 11 browser results are
baseline evidence, not proof for this milestone.

Current source introduces explicit Monza #1 L50/#4 L50, Monaco #1 L40/#31 L40
and Brazil #1 L52/#31 L52 selections; stronger comparison artifact math/grid
contracts; six source-labelled channel definitions; null-aware/step-wise values
and cursor coverage handling. Offline catalog build, full API channel projection,
six-channel UI and final new artifacts now pass integrated checks. Key paths are
`telemetry/artifacts.py`, `contracts.py`, `openf1_lap_comparison.py`, `api.py`,
`lib/telemetry-comparison.ts` and `components/TelemetryPanel.tsx`.

Speed-integrated distance remains estimated in metres. Continuous channels are
speed/throttle/RPM; brake source values, gear and DRS codes remain discrete.
Null source data stay unknown. Canonical reference-A lap time determines the
shared cursor and it disappears beyond shared grid coverage rather than
freezing at a shorter lap's tail. Delta is elapsed B−A seconds. No independent
telemetry clock or surveyed geometry is introduced. Missing Monaco pit source
means no pit-in-clean proof; tyres, fuel, traffic and weather are not controlled.

Next: publish the verified source/docs checkpoint. Broader arbitrary lap/driver selection,
sector/corner bands, cross-layout comparisons and ghost laps remain incomplete.
Full milestone detail is maintained by root in `DISTANCE_ALIGNED_TELEMETRY.md`.

Additional current contract evidence: 16 focused distance-alignment tests pass
and scoped Ruff passes, including eight serialized-contract mutation cases,
two fractional gear/DRS rejection cases and one missing-channel case. The
builder rejects fractional discrete codes instead of silently truncating them
with `int()`. The previous real Monza artifact validates against the stricter
contract. API projection exposes all aligned channels and lap-quality metadata
while omitting the large raw `lap.points` arrays; all three-session builds
and integrated checks pass.

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
