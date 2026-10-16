# Agent worklog

## 2026-10-15 UTC — M1/M2, qualifying source recovery and evaluation setup

- **Before:** branch `feat/foundation`, HEAD
  `bb840d44a2cf6c2f325f6ef2a575ff074f0d1b05`. Existing local changes
  included `pyproject.toml`, `uv.lock`, Sprint 3 source/tests/notebook, scripts
  and new mandate documents. All were preserved.
- **Objective:** make the existing qualifying experiment executable against
  real 2022–2025 seasons, then use legal common features for the baseline and
  historical-form ablation. This implements the first dependent slice of the
  locked product, not the entire workstation.
- **Inspected:** `AGENTS.md` and `SOL61_MASTER_EXECUTION.md` completely;
  original feature builder, ingestion, model/test code, notebook 03, package
  configuration, cached Parquets and prior ingestion log.
- **Finding:** 360-row combined dataset lacked 2023 and 2024. The earlier log
  showed FastF1 500 calls/hour failures. On resumption, two remaining cached
  2022 weekends completed, but uncached 2023 F1 timing failed; one direct URL
  returned HTTP 401. The interrupted command did not rewrite the combined
  artifact. OpenF1 public history returned the needed 2023 result schema.
- **Files changed/created this checkpoint:** `.gitignore` (notebook checkpoint
  exclusion), `pyproject.toml` (pytest testpaths, preserving user-added Jupyter
  dependencies), `data/fastf1_source.py` (disable unused weather fetch),
  `features/qualifying.py` (deleted-lap flag handling and FP3 team labels),
  `data/openf1_qualifying.py` (cached, paced provider adapter),
  `data/mixed_qualifying.py` (provider-labelled merge),
  `models/qualifying_backtest.py` (common feature set, paired event bootstrap,
  sample coverage), `models/qualifying_ablation.py` (same feature set and
  uncertainty), `features/historical_qualifying.py` (bind rolling window),
  `tests/test_openf1_qualifying.py` and existing test files (normalization,
  schedule, common-feature and bootstrap checks), plus the documentation listed
  below. Untracked Sprint 3 files remain uncommitted until real results pass.
- **Algorithm:** normalize practice gap as
  `100 × (driver best seconds / event best seconds − 1)`; Q1 uses the same
  equation over Q1 times. Fit on 2022–2023, select by 2024 event-mean MAE,
  evaluate 2025 only after selection. `add_historical_features` shifts each
  driver/team qualifying result before a 3/5-event rolling mean. The bootstrap
  resamples paired candidate-minus-FP3 event MAE, not individual drivers.
- **Data flow/source:** FastF1 3.8.3 cached 2022 event Parquets plus OpenF1 v1
  meeting/session/result/driver JSON for 2023–2025; exact field and hash
  semantics are in `DATA_CONTRACTS.md`. OpenF1 API documentation:
  https://openf1.org/docs/ . No third-party code was copied; provider JSON
  is local ignored data. Public historical free tier is paced at 2.1s/request.
- **Tests/commands:** initial `uv run pytest -q` failed from collecting
  `references/`; setting `testpaths = ["tests"]` yielded 10 passes. After new
  adapter and bootstrap tests, `.venv/bin/pytest -q` yielded 14 passes. Full
  OpenF1 ingestion completed with 52 weekends and 1,038 rows; mixed data had
  71 weekends and 1,418 rows. Baseline and form ablation ran on 35/18/18
  eligible train/validation/test events. Ridge won 2024 validation; 2025
  Ridge MAE 3.2433 vs FP3 3.3141, paired interval [-0.2934, +0.1587]. Form
  did not win validation. Shared 2025 Monza provider times matched on all
  available pairs, and a three-event VER driver/team form trace was checked.
  Notebook 03 executed with zero cell errors. Final scoped test run passed
  16/16 and Ruff passed. Detailed evidence:
  `TEST_EVIDENCE.md` and `EXPERIMENT_REGISTER.md`.
- **Caveats:** OpenF1 session results provide best lap, not tyre/sector/lap
  series; common-source comparison is necessary. This is Q1 pace predicting
  final Q classification, not grid prediction. 2025 was not used to choose
  model settings. Cross-provider overlap was audited for one event only. No probability
  calibration, replay or strategy engine exists yet.
- **After:** commit SHA and push state pending verification; current worktree
  contains preserved user changes plus this checkpoint work.
- **Next:** run final checks; commit/push a safe checkpoint; start canonical
  session contracts and a real replay fixture.

## 2026-10-15 UTC — P0 canonical session foundation

- **Prior checkpoint:** `b6835e7`, pushed to `origin/feat/foundation` using the
  repository's existing Aymen Jedidi Git identity, with no assistant coauthor.
- **Changed:** `src/f1_racelab/session/contracts.py` defines immutable
  versioned Pydantic session IDs, event payloads, events and race state;
  `reducer.py` applies strict event order and deterministic seek;
  `openf1_sample.py` maps real OpenF1 race-control messages into the contract;
  `tests/test_session_reducer.py` covers the reducer and validation. Related
  architecture, data, decision, atlas, evidence, roadmap and handoff documents
  were updated in this same checkpoint.
- **Algorithm/units:** event session time is seconds from the scheduled UTC
  session start. Source, observed and ingest timestamps must be timezone-aware.
  Events use a strictly increasing sequence and unique ID; duplicate IDs are
  idempotent. `seek_state` sorts by `(session_time_seconds, sequence)` and
  reduces through the requested cutoff. Provider race-control messages remain
  messages; local sector flags do not imply a global race flag.
- **Real source:** [OpenF1 race-control API](https://openf1.org/docs/), session
  key 9912, 2025 Italian GP. Source response SHA-256
  `b138137eadc17c3d10d1b1bfe7f5fe8beddf033753b0a5adad79904a5693fa25`.
  The local ignored sample has 53 messages after scheduled start; final event
  at 4,896 seconds. No position, lap, weather or strategy data was inferred.
- **Evidence:** `.venv/bin/python -m f1_racelab.session.openf1_sample` exited
  0; `.venv/bin/pytest -q` passed 19/19, Ruff and `git diff --check` passed.
  The three new reducer tests are synthetic; the sample build uses real cached
  provider data. No frontend demo is claimed.
- **Risks and next:** this is a message-only sample, not a replay pack; there
  is no reorder buffer for late live packets, checkpoint index or frontend
  binding. Next add measured position/lap/pit events, then a versioned pack and
  shared frontend clock. Check `git log -1` for the final checkpoint SHA.

## 2026-10-15 UTC — P1 first full offline race pack

- **Starting state:** `feat/foundation` at pushed `4c5bd37`; only two unrelated
  untracked helper files in `ml/features/` were present and left untouched.
  The previous checkpoint normalized 53 race-control messages but had no car
  position or lap replay. This milestone implements the next dependent data
  path for one actual race; no frontend claim is made.
- **Files:** `session/contracts.py` adds typed lap, pit-stop and stint payloads
  plus separate timing/position/location quality fields;
  `session/reducer.py` applies them and rejects event-ID reuse with changed
  contents; `session/source.py` defines the mode-independent `RaceSource`
  protocol; `session/openf1_replay.py` caches/normalizes OpenF1 data into a
  compact ignored pack; `session/replay_source.py` supplies indexed seek and
  sidecar sampling; `session/validate_replay.py` runs real-data QA.
  `tests/test_session_reducer.py` and `tests/test_openf1_replay.py` cover
  synthetic invariants. README and `docs/REPLAY_2025_MONZA.md`, `ROADMAP.md`,
  `ARCHITECTURE.md`, `DATA_CONTRACTS.md`, `VISUAL_PIPELINE.md`, `DECISIONS.md`,
  `IMPLEMENTATION_ATLAS.md`, `GLOSSARY_FOR_LEARNING.md`, `EXPERIMENT_REGISTER.md`,
  `TEST_EVIDENCE.md`, this worklog, the handoff and ADR-0001 document the
  same milestone.
- **Real source and algorithm:** [OpenF1 API](https://openf1.org/docs/) session
  9912, meeting 1268. UTC clock origin is scheduled 2025-09-07 13:00. Twenty
  driver rows, 421 position rows, 976 laps, 19 pit, 39 stints, 73 control and
  20,226 interval rows were fetched, plus 20 driver-specific location responses
  of 30,700 rows each. The client used its 2.1-second minimum request interval
  and cached raw JSON. Sparse events sort by time, type priority and source
  index; 974 lap completions are at `approximate date_start + lap_duration`
  seconds and marked estimated; 2 unusable lap rows are counted. Twenty
  latest pre-clock position rows seed t=0 while preserving their older source
  observation. Location retains **actual** nonzero points at most 2 Hz, never
  synthetic points in the stored sidecar. Replay samples them through a binary
  search; only short in-between movement is estimated. Intervals older than
  10 seconds are hidden. A 166-point trace from VER lap 3 is approximate
  geometry in unknown provider coordinate units.
- **Evidence:** 1,506 events, 198,300 retained location samples, 24
  checkpoints, 20 drivers and ~1.8 MB compressed local pack. The builder's
  end-state comparison matched 18/18 classified positions and 20/20 lap totals
  against post-session results. The validator matched 131 indexed seeks to full
  reducer output and one exact measured location; local p50/p95 seek times
  were 1.123/2.329 ms. `uv sync --dev` resolved 167 and checked 164 packages;
  `.venv/bin/pytest -q` passed 24 synthetic tests; Ruff passed. Artifacts and
  source SHA values are in ignored `data/processed/replay_packs/`. After
  explicit event type aliases and nullable numeric guards, session-scoped
  mypy passed eight source files. Reproduce
  via the two commands in `REPLAY_2025_MONZA.md`.
- **Bug and fix:** the first builder run cached all 20 locations but failed
  when a singular `lap` event was incorrectly used as the plural `laps` raw
  table key. The mapping was corrected; the cached rerun succeeded. A synthetic
  normalization test protects the source-time transformation. A later check
  found `source_timestamp` for lap start must differ from the estimated
  completion `observed_at`; the builder now records both correctly.
- **Rationale/rights:** ADR-0001 explains sidecars and checkpoints. The
  adapter is independent code informed by OpenF1's documented schema. The
  inspected OpenF1 repository revision was
  `87540e3f495bbd9bedb37b10456dd848c8f193d6`, licensed CC BY-NC-SA 4.0;
  upstream race data rights need separate review. Raw/pack data stay ignored.
  No new dependency was added.
- **Limits/next:** one race; coordinates approximate, source units unknown;
  stale stationary points may repeat after retirement; pit records do not
  locate pit entry/exit; no full telemetry or browser demo. Next serve the
  pack locally and build a shared-clock 2D UI, then audit two more sessions.
  Check `git log -1` and remote for this checkpoint's final SHA/push state.

## 2026-10-16 UTC — P2 first local Race Control screen

- **Source SHA and scope:** started from pushed `abe031c` on
  `feat/foundation`; the same two unrelated untracked `ml/features/`
  helper scripts were left untouched. Implemented a local API and one-race
  2D/timing/control replay UI. This is partial P2, not a full product gate.
- **Paths/functions:** `src/f1_racelab/api.py:create_app` serves manifest
  and canonical `RaceState(t)`; `session/replay_source.py:_location_at`
  hides frozen coordinates after 15 s; `apps/web/src/App.tsx:App/TrackMap`
  owns one playback clock and maps backend state to timing, focus, control
  list and provider XY; `App.css`, Vite proxy, title/favicon and ESLint
  support the screen. `tests/test_replay_api.py` checks API and staleness.
  This worklog, `RACE_CONTROL_UI.md`, atlas, decisions, roadmap, register,
  glossary, test ledger, replay notes and handoff document the same step.
- **Data and formula:** OpenF1 historical 2025 Monza session 9912, 20
  drivers, 53 post-clock messages, 166 approximate geometry points. One
  browser time in seconds requests backend state at most 5 Hz. Track XY is
  uniformly projected to SVG pixels; unknown provider units stay labelled.
  A repeated XY streak lasting at least 15 s hides the location. This is a
  visual rule only; timing/position truth remains in `RaceState`.
- **Evidence:** synthetic suite 27 passed, one upstream deprecation warning;
  Ruff, nine-file session/API mypy, web ESLint and TypeScript/Vite build
  passed. Real pack API manifest HTTP 200/35,246 bytes; t=1,200 s returned
  20 states, 20 locations, max completed lap 11. Replay validator matched
  131 seeks; p50/p95 0.975/2.066 ms. Exact commands/artifact SHA and
  failure/fix details are in `TEST_EVIDENCE.md` and `RACE_CONTROL_UI.md`.
- **Limits/next:** computer-use browsers were unavailable, so visual and
  interactive browser QA remain. The UI currently displays backend state
  at 5 Hz, not 60 Hz car motion. One race only; no full telemetry, live,
  strategy or 3D. Next inspect and refine the actual rendered screen, then
  add two audited sessions. Source/rights remain OpenF1 public historical
  data and the repository/license details in `REPLAY_2025_MONZA.md`.
  Find the final checkpoint SHA and push state with `git log -1` and
  `git ls-remote origin refs/heads/feat/foundation`.

## 2026-10-16 UTC — source audit for two replay candidates

- **Starting SHA:** pushed `2d270fc` on `feat/foundation`; two preexisting
  untracked helper scripts remain untouched. This is a source-coverage
  checkpoint, not a second/third built replay pack.
- **Code:** `session/audit_candidates.py:Candidate/audit_candidate/summarize`
  resolves each race, fetches nine tables through the existing OpenF1 client,
  validates session keys, records rows/driver coverage/rain/compounds/critical
  messages/SHA-256, and marks HTTP 404 unavailable rather than zero.
  `tests/test_replay_candidate_audit.py` checks that contract synthetically.
  The ignored output is `data/processed/replay_candidate_audit.json`.
- **Real findings:** 2023 Monaco session 9094 has 20 drivers in position and
  lap tables, 26/176 rainfall records and INTERMEDIATE/WET stints; its
  `pit` endpoint returned HTTP 404. 2024 Brazil session 9636 has 20
  position drivers, 19 lap drivers, 117/201 rainfall records and VSC/SC/red
  control messages. Full counts, times, hashes and source/licensing links
  are in `REPLAY_CANDIDATES.md`.
- **Evidence/bug:** first naive fetch stopped on Monaco `pit` 404; the
  auditor now catches only that status and keeps `null` distinct from a
  successful empty response. CLI rerun succeeded; one synthetic audit test,
  full 28-test suite, Ruff and audit mypy passed. Exact commands are in
  `TEST_EVIDENCE.md`.
- **Next:** parameterize the Monza builder, carry optional pit coverage into
  capabilities, then build/validate both packs before changing global flag
  state or claiming wider replay reliability. Find this checkpoint's final
  commit/push via `git log -1` and `git ls-remote origin
  refs/heads/feat/foundation`.

## 2026-10-16 UTC — P1-GOLDEN-3 / P2 multi-session browser replay

- **Starting state:** pushed `7940f2c`, branch `feat/foundation`; two
  unrelated untracked helpers in `ml/features/` remain untouched.
  The prior checkpoint only audited candidate sources; the builder and UI
  still selected Monza exclusively.
- **Implementation paths:** `src/f1_racelab/session/catalog.py`,
  `openf1_replay.py`, `contracts.py`, `replay_source.py`,
  `validate_replay.py`, `src/f1_racelab/api.py`;
  `tests/test_openf1_replay.py`, `tests/test_replay_api.py`;
  `apps/web/src/App.tsx`, `App.css`, `index.css`,
  `components/ui/slider.tsx`, `lib/playback-clock.ts`,
  `apps/web/tests/playback-clock.test.ts`, `e2e/replay.spec.ts`,
  `playwright.config.ts`, `package.json`, `package-lock.json`,
  `vite.config.ts`, `index.html`, root `.gitignore` and `README.md`.
  Documentation: this worklog, handoff, atlas, roadmap, test ledger, experiment
  register, decisions, glossary, architecture, data contracts, visual pipeline,
  start page, replay candidates, first UI notes and new
  `REPLAY_GOLDEN_SESSIONS.md`.
- **Behavior:** explicit audited catalog specs carry source IDs/clock and
  display metadata. The builder checks provider metadata, uses per-session
  event IDs/origins, preserves optional missing pit capability and null
  stint/result counts. The API caches three sources by slug and every
  canonical state includes capabilities. The UI cancels old requests and
  resets its central clock when switching session; rates 0.25×–16×,
  exact control jumps, race-start jump and numeric gaps work. React reads
  a monotonic anchored clock every 200 ms. All data panels share one returned
  state. Formula, units, inputs/outputs and functions are described in
  `REPLAY_GOLDEN_SESSIONS.md` and the atlas.
- **Real evidence:** three packs contain 5,290 sparse events and 799,422 XY
  points overall. Available final classification/lap checks all pass;
  Brazil DSQ lap total remains unknown. The validator checks every event
  boundary ±1 ms and 101 regular times: 14,112 cutoffs match a separate
  forward pass, plus 600 seeded shuffled revisits. Latest per-race p95 seek
  times 2.309/2.816/2.438 ms are local backend results. Four actual Chromium
  tests operate all three local packs and pass; screenshots inspected.
  Exact metrics, hashes, sources and artifact paths are in the new milestone
  document.
- **Synthetic/static evidence:** 30 Python tests, two JS clock tests, Ruff,
  11-file session/API mypy and web lint/build pass. Node 22.23.2, npm 10.9.8,
  Python 3.12.13, FastAPI 0.142.2, Playwright 1.64.1/Chromium 156.
  `npm ci` works with the now-tracked lockfile. Production-only npm audit
  is clean; seven high advisories remain in the development shadcn CLI
  chain. No force downgrade was applied.
- **Failures/fixes:** Brazil's null `lap_start` initially raised TypeError;
  it is now counted/skipped. HUL DSQ null lap total is no longer treated
  as zero in QA. Browser tests found the scrubber's actual input unnamed;
  forwarding the label fixed keyboard access. A synthetic clock assertion
  now uses decimal tolerance. Numeric gaps had been hidden because only
  lapped text was rendered; numeric seconds now display too. Global Git
  ignore excluded npm lockfiles, so the repository adds an explicit include.
- **Sources/rights:** independent adapter against documented
  [OpenF1 API](https://openf1.org/docs/), source response hashes in local
  manifests; exact prior repository/license audit in D-001. Playwright is
  an Apache-2.0 test dependency. No provider data, browser binaries or
  broadcast assets were committed.
- **Scope and next:** P1 three-reference gate is verified; full P1/P2 remain
  partial (approximate geometry, 5 Hz state rendering, no global status or
  weather in state, missing source-time retirement handling). Next add
  scoped track-status/weather, smoother rendering/stint panels, then
  distance-aligned telemetry. Implementation checkpoint
  `af2f64677d48d7f9573451de1419fbe3e0b98e08` was pushed to
  `origin/feat/foundation`; remote SHA verified with `git ls-remote`.
  A follow-up docs-only commit records this publication. No coauthor
  trailers are added.

The final cached rebuild executed:

```bash
.venv/bin/python - <<'PY'
import contextlib,json
from pathlib import Path
from f1_racelab.session.catalog import SESSIONS
from f1_racelab.session.openf1_replay import build_replay_pack
log=Path('data/processed/replay_packs/golden_build.log')
with log.open('w') as handle:
 for slug,spec in SESSIONS.items():
  with contextlib.redirect_stdout(handle):
   manifest=build_replay_pack(spec=spec)
  print(slug, json.dumps({k:manifest[k] for k in ('sha256','bytes','event_count','driver_count','sample_count','qa')}),flush=True)
PY
```

## 2026-10-16 UTC — schema 2 weather observations and scoped track signals

- **Starting source SHA:** `418806099b7670d96cfe13c13c6484d5f8644a50` on
  `feat/foundation`, synchronized with `origin/feat/foundation`; the two
  unrelated untracked `ml/features/` helpers were preserved. The implementation
  and complete note set are committed and pushed together; exact implementation
  and publication SHAs are recorded in the follow-up handoff entry after push.
- **Changed paths and contracts:** `session/contracts.py` adds schema 2
  `WeatherObservation`, `TrackStatusObservation`, strict weather units/ranges,
  observation metadata, 120-second maximum display age, and scoped status
  enums. `session/openf1_context.py` normalizes weather and conservative
  session-wide messages. `session/reducer.py` applies both at their provider
  event time; `ReplaySource` reads schema 1 and 2 packs and exposes schema 2
  state. `openf1_replay.py` adds weather and eligible global signals without
  changing the position/lap replay window. `validate_context.py` independently
  verifies the raw-source lineage and golden signal boundaries.
- **UI and API paths:** `api.py` exposes rainfall-change navigation points in
  the manifest. `apps/web/src/lib/session-context.ts` derives weather freshness
  from the canonical session clock. `WeatherPanel.tsx`, `App.tsx` and `App.css`
  display units, observation age, rainfall reports and last track signal.
  Every panel remains tied to one state timestamp. Race-control buttons expose
  their exact source seconds for stable access and browser checks.
- **Real inputs and algorithm:** OpenF1 historical weather values remain at
  exact provider timestamps: air/track °C, humidity %, pressure mbar, wind
  direction degrees, wind speed m/s, and rain presence boolean. They are not
  interpolated. In UI, age is `state.session_time_seconds - observed_at`; data
  is fresh only when `0 <= age <= 120 s`. Rainfall labels state only whether
  the provider reported rain. Global flag rows require Track scope and no
  driver/sector; pit-exit flags are discarded. Exact SC/VSC deployed/ending,
  session-started/aborted messages are mapped, but ending/restart signals do
  not imply green. Other rows remain ordinary race-control messages.
- **Real evidence:** packs contain 5,654 events (Monza 1,592; Monaco 2,220;
  Brazil 1,842), including 350 weather and 14 track-status events, and retain
  799,422 source XY points. Raw weather coverage is 144/176/201 rows; retained
  rows are 84/117/149 after 54/59/52 pre-clock records and six post-window
  Monza records are handled without extending replay duration. All 350 records
  match raw cache bytes, source timestamps and values. The independent audit
  performs 700 before/exact-as-of comparisons and checks 14 reviewed global
  status boundaries. Max retained weather gaps are 60.042/60.093/60.225 seconds.
  Pack durations remain 5,014.715/7,030.073/8,935.817 seconds. Details, source
  hashes, command lines, limitations and generated report paths are in
  `REPLAY_CONTEXT.md`.
- **Synthetic and browser evidence:** 50 Python tests pass (one existing
  Starlette/httpx deprecation warning); Ruff and session/API mypy pass (13
  files); three JS unit tests, web lint and Vite build pass. Six Playwright
  Chromium checks pass with all three real local packs, including Monaco rain
  transitions and Brazil VSC ending/red/restart/SC ending semantics. Screenshots
  in ignored browser output were inspected. A first full browser attempt exposed
  two test issues: cold page initialization exceeded the default five-second
  assertion despite a complete page snapshot, and `.first()` selected a later
  repeated SESSION STARTED message. A 15-second bounded data readiness check
  and exact event-time selector fixed these; the Brazil case then passed alone
  and the complete suite passed. No 60 Hz/FPS or official track-condition claim
  is made.
- **Sources and caveats:** documented [OpenF1 API](https://openf1.org/docs/),
  including native weather units; source/license audit and non-commercial
  upstream CC BY-NC-SA 4.0 terms remain in D-001. No raw pack is committed.
  `running_unknown` intentionally makes no green assertion; `suspended` follows
  SESSION ABORTED, not a guessed red flag. Reported rain does not imply a wet
  surface, rainfall amount, or intensity. The 120-second age is a UI freshness
  policy, not a provider guarantee. Offline replay only; live feed, smooth
  rendering, stint bars, telemetry, strategy and the remaining roadmap gates
  are incomplete.
