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
  checkpoint is `111fb60777fa55327ddca36d0b95c04d06990e6f`, committed as
  Aymen Jedidi, pushed normally to `origin/feat/foundation`, and verified with
  `git ls-remote` at the same SHA. This documentation follow-up records the
  exact publication state; no coauthor trailer was added.
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
  policy, not a provider guarantee. Offline replay only; live feed, complete
  measured rendering, telemetry, strategy and the remaining roadmap gates
  are incomplete.

## 2026-10-16 UTC — schema 3 source-time stints and playback map transforms

- **Starting source SHA:** `2feed4059141107b43c31bf87f9937c565e2bdef` on
  `feat/foundation`, previously synchronized with `origin/feat/foundation`.
  Two unrelated untracked user helpers under `ml/features/` were preserved.
  Implementation commit `4a0434aea67ff99a2f949abc08babdcbf0b50578` was
  committed as Aymen Jedidi, pushed normally to `origin/feat/foundation`, and
  verified with `git ls-remote` at the same SHA. This documentation-only
  checkpoint records the exact publication state. No assistant coauthor
  trailer was added.
- **Changed source paths and functions:**
  `src/f1_racelab/session/contracts.py` adds immutable `TyreStintState`,
  `DriverState.tyre_stints`, and `RaceState` output schema 3;
  `session/reducer.py:reduce_event` appends and closes stint history at source
  event time and grows only the open stint on later lap events;
  `session/validate_replay.py:validate` reports state version and stint
  coverage; `apps/web/src/lib/session-context.ts` defines the API shape;
  new `apps/web/src/components/StintPanel.tsx` draws same-clock history;
  `apps/web/src/App.tsx:TrackMap` gates 180 ms transforms on active playback,
  positive forward delta and at most 4 s; `App.css` supplies compound colors,
  lanes, transform timing and the existing reduced-motion rule. Tests changed
  in `test_session_reducer.py`, `test_replay_api.py`, `test_replay_context.py`
  and `apps/web/e2e/replay.spec.ts`.
- **Milestone documentation paths:** `ROADMAP.md`, this `AGENT_WORKLOG.md`,
  `IMPLEMENTATION_ATLAS.md`, `TEST_EVIDENCE.md`, `EXPERIMENT_REGISTER.md`,
  `DECISIONS.md`, `GLOSSARY_FOR_LEARNING.md`, `CHATGPT_HANDOFF.md`,
  `DATA_CONTRACTS.md`, `REPLAY_CONTEXT.md`, `REPLAY_GOLDEN_SESSIONS.md`,
  `RACE_CONTROL_UI.md`, and the new detailed `REPLAY_STINTS_AND_MOTION.md`.
- **Version contract:** stored pack and `SessionEvent` schema stay version 2;
  the reducer emits `RaceState` schema 3. Existing timed stint events were
  already in all three packs, so no provider fetch, pack rebuild, timestamp
  shift or event-count change was required. Version 1 pack reading remains.
- **Inputs, fields and algorithm:** source is the OpenF1 historical
  `stints`/`laps` data already retained in sessions 9912, 9094 and 9636.
  Each state segment records source event ID, session-clock seconds, aware UTC
  observation time, compound, one-based lap start/end, start age in laps,
  quality and closing event ID. On a later `StintPayload`, previous end is
  `max(previous.lap_start, latest_completed_lap)` (using its start when the
  driver has no completed lap); the reducer records the close event and
  appends the new source segment. A later `LapPayload` updates the current
  open segment's inclusive end and end quality. It deliberately does not copy
  the provider's eventual `lap_end` to the earlier start event, which would
  leak a future boundary. Stint number/lap start may not decrease; equal starts
  are preserved because Monaco HUL/car 27 has MEDIUM and HARD source rows both
  starting at lap 1. No missing lap is inferred into a gap.
- **UI formula and motion choice:** the StintPanel uses one lane per source
  row. For `N=scheduled_laps`, left is `100*(lap_start-1)/N` percent and
  inclusive width is `100*max(1,lap_end-lap_start+1)/N` percent. Null end draws
  at least the start lap and remains labelled in progress. The display reports
  source quality and explicitly labels shared lap boundaries. Map positions
  remain in the same canonical state polled at 5 Hz. Only when `playing` is
  true and state time advances by `0 < delta <= 4` does CSS interpolate SVG
  `transform` for 180 ms ease-out. At 16× the nominal 200 ms state interval is
  3.2 seconds. First appearance, pause/seeks (including small forward exact
  seeks), reverse movement, larger gaps and reduced motion show no transition.
  This is visual only and makes no 60 Hz/FPS or continuous measurement claim.
- **Real source coverage:** manifests report 39/57/54 raw stint rows for
  Monza/Monaco/Brazil. Retained normalized event totals are 39/57/52 (148).
  Brazil has one source row without `lap_start` and one without a matching lap
  start; the builder already records these two exclusions. At pack end the
  independent validator reports 39/57/52 histories; it does not imply all 20
  Brazil drivers have stints. OpenF1 docs are at
  [openf1.org/docs](https://openf1.org/docs/); the repository's pinned
  [CC BY-NC-SA 4.0 license](https://github.com/br-g/openf1/blob/87540e3f495bbd9bedb37b10456dd848c8f193d6/LICENSE)
  remains applicable. No raw provider data or pack is committed.
- **Verification and evidence class:** Python 3.12.13 / FastAPI 0.142.2,
  Node 22.23.2 / npm 10.9.8, Playwright 1.64.1 / Chromium 156, Vite 8.3.2.
  `.venv/bin/pytest -q`: 51 passed with one existing Starlette/httpx warning.
  Ruff passed; session/API mypy passed 13 files. `npm run test:unit`: 3
  synthetic tests passed. `npm run lint`, `npm run build`, and the real-pack
  `npm run test:e2e` suite passed; E2E total is 8 Chromium cases. Production
  build is JS 413.23 KB (136.45 KB gzip), CSS 67.09 KB (13.12 KB gzip).
  `.venv/bin/python -m f1_racelab.session.validate_replay --all` passed 15,162
  event-boundary/regular cutoffs plus 600 shuffled revisits; pack-end state
  versions are 3 and stint counts 39/57/52. The context auditor passed 700
  weather cutoff comparisons and 14 reviewed track boundaries with zero
  invalid weather rows. These are real local-pack/source reconciliation and
  synthetic contract checks, not a tyre model or racing-performance result.
- **Failure and fix:** an initial reducer draft rejected strictly increasing
  stint lap starts. The real Monaco car-27 source contradicted that assumption;
  validation now requires nondecreasing starts and preserves both same-lap
  records, covered by a new cutoff/overlap reducer test. The first motion
  browser assertion sought to pack end where no source locations are available;
  the correct map has zero cars there. The test was redirected to the exact
  source `SESSION STARTED` row. A further review found small forward exact
  seeks would otherwise resemble playback deltas, so the animation now also
  requires `playing=true` and the browser test verifies a paused forward seek.
- **Artifacts:** `data/processed/replay_packs/golden_sessions.qa.json`,
  `golden_context.qa.json`, and per-pack QA reports are ignored. Inspected
  browser images are
  `data/processed/browser_tests/results/replay-Monaco-stint-histor-accfb-ame-lap-source-rows-visible-chromium/monaco-stints-desktop.png`
  and
  `data/processed/browser_tests/results/replay-real-Monza-seeks-ke-610fd-d-control-on-the-same-state-chromium/monza-desktop.png`.
- **Unresolved scope:** this is a source stint history, not exact pit-exit or
  tyre-fit timing, wear/grip estimation, degradation prediction or strategy.
  Lap ranges can overlap or have gaps. Positions stay approximate; missing
  provider samples remain hidden. Full geometry, calibrated map performance,
  telemetry, production prediction, strategy/simulation, live, radio, 3D, CI
  and storage/schema-export work remain. Reproduce the service/build and checks
  with the commands in `REPLAY_STINTS_AND_MOTION.md`; next, continue P2 geometry
  and performance evidence, then distance-align telemetry. See all required
  handoff/atlas/decision notes linked from `CHATGPT_HANDOFF.md`.

## 2026-10-16 UTC — distance-aligned telemetry foundation (partial P3)

- **Starting source SHA:** `89351502ccb6389c25886d18022430f2ce6319f8` on
  `feat/foundation`, synchronized with `origin/feat/foundation`. Implementation
  commit `2ac01012c780552f26bd9504f88c9cac87541000` was pushed normally and
  verified at the same remote SHA. The two unrelated untracked user helpers
  under `ml/features/` remain untouched. Commit author is Aymen Jedidi; no
  assistant coauthor trailer was added.
- **Changed source paths and symbols:** new
  `src/f1_racelab/telemetry/contracts.py` defines immutable
  `LapTelemetryPoint`, `LapTelemetry`, `DistanceComparisonPoint` and
  `LapComparison`; `distance_alignment.py:build_lap_telemetry` validates a
  source lap and integrates bounded speed samples; `compare_laps` interpolates
  two laps onto a uniform common-distance grid; `openf1_lap_comparison.py`
  reproduces a cached-source comparison as JSON and PNG. New synthetic tests
  are in `tests/test_distance_alignment.py`.
- **Inputs and source lineage:** OpenF1 v1 historical Monza 2025 session 9912,
  meeting 1268; `laps` response SHA-256
  `89cee73604aaf44129b1a80cb10205f55eb16937dff0ba804ca38326532bbbae`;
  car data for VER #1
  `6ff42419ce5d39a0ca77d8fca0836676328f1456bf187028e94771acf621d36e` and
  NOR #4
  `9ed72c1fbbce6a4e462dcf1cb6d93e75813896aa1b5bfc8598df60de82ac1a40`.
  Official API docs and access notes are linked in
  `DISTANCE_ALIGNED_TELEMETRY.md`; OpenF1 upstream terms are CC BY-NC-SA 4.0.
  Raw cache and derived JSON/PNG stay ignored under `data/`.
- **Contract, units and formulas:** lap rows must match session/meeting/driver,
  be timezone-aware and not be pit-out. Sample gaps above 1.0 s reject the lap.
  For speeds in km/h, integrate `((v_i+v_(i+1))/2)/3.6 * delta_seconds` to
  metres. Lap boundaries are linearly interpolated only when bracketed inside
  the gap limit. Continuous channels are linear; brake/gear/DRS hold the prior
  source state. Throttle is not clipped; brake remains a raw source value; DRS
  remains an integer provider code. Distance and comparison quality are
  explicitly estimated. Comparison uses a 5 m grid and delta
  `elapsed_B - elapsed_A` in seconds.
- **Real result:** VER #1 L50 (81.297 s), 318 source samples / 320 bounded
  points / 5,746.062 m; NOR #4 L50 (81.123 s), 309 / 311 / 5,751.324 m.
  Both have two interpolated boundaries; largest bounded interval is 0.799 s.
  The common grid ends at 5,746.062 m with 1,150 points. B−A ranges from
  −0.374 to +0.212 s and finishes at −0.234 s. These two real laps do not
  establish a general performance conclusion. JSON SHA-256
  `8e4ddc3217641f3543c37aba440574156512f4bd89e5c66a7dd6168b88543277`; PNG
  `7e7a7f5d6b19a2244a1b63d2cc993fc3227e2742a924202861fa2b7faeb50582`.
- **Verification:** Python 3.12.13, Pydantic 2.13.5, Matplotlib 3.11.2,
  pytest 9.1.1, Ruff 0.16.10 and mypy 2.4.0. The telemetry tests pass 5/5;
  full `.venv/bin/pytest -q` passes 56 with one existing Starlette/httpx
  deprecation warning; `.venv/bin/ruff check src tests scripts` passes;
  mypy over telemetry/session/API passes 17 files. Real cached-source CLI exits
  0 and the generated plot was visually inspected. Exact reproduction and
  tool versions are in `DISTANCE_ALIGNED_TELEMETRY.md` and
  `TEST_EVIDENCE.md`.
- **Failures and fixes:** existing source values of 104 contradicted an
  assumed 0–100 cap, so clipping/bounds were removed and raw values retained;
  synthetic tests assert 104 fidelity. Corrected Ruff import ordering and
  mypy typing. Restyled dark chart labels for readable contrast. No further
  network request was made after cached responses were available.
- **Modified documentation paths:** `ROADMAP.md`, this worklog,
  `IMPLEMENTATION_ATLAS.md`, `TEST_EVIDENCE.md`, `EXPERIMENT_REGISTER.md`,
  `DECISIONS.md`, `GLOSSARY_FOR_LEARNING.md`, `CHATGPT_HANDOFF.md`,
  `DATA_CONTRACTS.md`, and detailed `DISTANCE_ALIGNED_TELEMETRY.md`.
- **Partial/not done:** the comparison is not an API endpoint or frontend
  panel, and has no cursor bound to canonical `RaceState` time. It has no
  sector model, GPS alignment, surveyed geometry, uncertainty band, prediction,
  strategy or live feed. Next: derive a telemetry cursor from the existing
  replay time and display it within that shared clock; then widen event
  coverage. P3/P4 remain partial. Remote verification used
  `git ls-remote origin refs/heads/feat/foundation` and returned the exact
  implementation SHA above.

## 2026-10-16 UTC — shared-clock telemetry comparison panel (partial P3)

- **Starting source SHA:** `10b53fd4905a6a22ad94ac249dc9632ce016845e` on
  `feat/foundation`, synchronized with `origin/feat/foundation`. Implementation
  commit `43e12407a7f13e02b0eb6d6a3fc0206442ca5816` was pushed normally and
  verified with `git ls-remote` at the same SHA. The two unrelated untracked
  user helpers under `ml/features/` remain untouched. Commit author is Aymen
  Jedidi; no assistant coauthor trailer was added.
- **Changed source paths and symbols:** `src/f1_racelab/telemetry/artifacts.py`
  shares the ignored artifact root; `api.py:create_app` advertises local
  comparisons and `/api/v1/replay/{slug}/telemetry/lap-comparison` validates
  and projects an existing artifact without provider requests;
  `apps/web/src/lib/telemetry-comparison.ts` maps canonical replay seconds to
  the reference-lap grid; new `components/TelemetryPanel.tsx` renders speed,
  delta and the canonical-time cursor; `App.tsx` fetches the available local
  artifact and passes `RaceState.session_time_seconds`; CSS provides responsive
  chart/readout layout. Tests changed in `test_replay_api.py`, new unit tests
  in `telemetry-comparison.test.ts`, and a Chromium scenario in
  `apps/web/e2e/replay.spec.ts`.
- **Inputs and formulas:** unchanged real cached source is OpenF1 v1 historical
  Monza 2025 session 9912, VER #1 L50 against NOR #4 L50. Its raw query hashes,
  license and detailed units are in `DISTANCE_ALIGNED_TELEMETRY.md`. For UI
  session time `t`, reference elapsed is
  `t - ((lap_a.start_utc - clock_origin_utc) / 1000)`; if inside the approximate
  lap duration, the UI linearly interpolates `distance_m`, B−A time and both
  speeds by `elapsed_a_seconds`. Outside that lap window, it hides the cursor.
  Jumping to the reference calls the existing `PlaybackClock.seek()`; no new
  clock is maintained.
- **API behavior and payload:** manifest lists the expected local #1 L50 vs #4
  L50 artifact per catalog session, with availability from `data/processed/`.
  The route validates Pydantic data and requires the artifact session and
  meeting keys to match the selected slug. Missing/invalid artifacts return
  unavailable; API never calls OpenF1. It returns plotted fields plus source
  hashes: current response is 200,119 bytes vs 847,619 bytes for the full local
  comparison JSON. Full source channels remain in the ignored artifact.
- **UI/result:** the panel plots #1/#4 speed and B−A cumulative seconds versus
  estimated integrated metres. In the real sample, distances remain 5,746.062
  m and 5,751.324 m; grid has 1,150 points. The cursor follows the exact
  canonical state timestamp shown in every other panel. `Jump to reference lap`
  seeks to session time 4,294.383 s; forward 10 s moves the cursor down the
  distance curve, and seeking to pack end hides it. Screenshot, visually
  inspected at the reference lap start:
  `data/processed/browser_tests/results/replay-telemetry-crosshair-176f6--clock-on-its-reference-lap-chromium/telemetry-cursor.png`.
- **Verification:** `.venv/bin/pytest -q`: 57 passed, one existing
  Starlette/httpx deprecation warning. Ruff passed; mypy passed 18 files. In
  `apps/web`, `npm run test:unit` passed 5, `npm run lint` passed,
  `npm run build` passed (JS 420.49 KB / 138.37 KB gzip; CSS 69.12 KB /
  13.60 KB gzip), and `npm run test:e2e` passed 9 Chromium cases in 19.0 s.
  The full test and artifact evidence is in `TEST_EVIDENCE.md`.
- **Failure and fixes:** first E2E run passed 8/9 because the pre-existing
  `getByRole('status')` pit-unavailable assertion also matched the new static
  telemetry hint. The hint no longer uses the live `status` role; 9/9 then
  passed. Visual inspection found the distance-axis title overlapped its tick
  labels, so the SVG plot gives the title its own space. The y scales are
  derived from the returned sample values to avoid clipping other comparisons.
- **Modified documentation paths:** `ROADMAP.md`, this worklog,
  `IMPLEMENTATION_ATLAS.md`, `TEST_EVIDENCE.md`, `EXPERIMENT_REGISTER.md`,
  `DECISIONS.md`, `GLOSSARY_FOR_LEARNING.md`, `CHATGPT_HANDOFF.md`,
  `DATA_CONTRACTS.md`, `ARCHITECTURE.md`, `RACE_CONTROL_UI.md`, and
  `DISTANCE_ALIGNED_TELEMETRY.md`.
- **Partial/not done:** only one fixed driver/lap pair is generated and served;
  no channel selectors, brake/gear/DRS plots, GPS distance, sector alignment,
  calibrated uncertainty, prediction, strategy or live telemetry exist. Other
  sessions display a build-artifact hint. Next widen real comparison coverage,
  then add historical-as-of prediction outputs. P3/P4 remain partial. Remote
  branch `feat/foundation` returned exact implementation SHA
  `43e12407a7f13e02b0eb6d6a3fc0206442ca5816`.

## 2026-10-16 UTC — historical qualifying Prediction Lab (partial P4)

- **Starting source SHA:** `bd67b199a189fed6adc604a5130638b9c34b18c6` on
  `feat/foundation`, synchronized with `origin/feat/foundation`. The two
  pre-existing user-owned untracked files under `ml/features/` were not
  modified or staged.
- **Modified implementation paths:** `src/f1_racelab/models/qualifying_backtest.py`
  adds `audit_prequalifying_cutoff` and writes cutoff/target/split metadata plus
  source and report-artifact SHA-256 values into `experiment.json`; new
  `src/f1_racelab/models/prediction_lab.py` validates local artifacts and
  projects per-weekend ranks; `src/f1_racelab/api.py:create_app` adds local
  manifest and event routes; `apps/web/src/App.tsx` adds navigation;
  `apps/web/src/components/PredictionLab.tsx` and its CSS implement the page;
  `apps/web/e2e/replay.spec.ts` adds a historic holdout/validation workflow;
  new `tests/test_prediction_lab.py` covers audit and API contracts.
- **Inputs, formulas and outputs:** reuse the local mixed-source qualifying
  Parquet with 71 conventional weekends/1,418 rows; no new provider request.
  The eight model inputs are FP1/2/3 percent gaps/ranks and the FP1→FP3 and
  FP2→FP3 gap changes. Prediction target is Q1 gap percent. Predicted pace is
  ranked inside an event; evaluation target is actual final qualifying rank.
  `position_mae` is mean absolute difference in rank places; event metrics are
  equally weighted. The audit checks an explicit practice-only allowlist,
  source-session/unit metadata, qualifying session marker and parseable UTC
  scheduled cutoff. It clearly records that this is not a per-feature
  observation/publication timestamp.
- **Why:** the current benchmark can responsibly support a historical
  retrospective lab from existing model outputs, but not a live or earlier
  session forecast. The local API checks the 2024-selection/2025-holdout and
  target contract, checks all served report artifact SHA-256 values, returns only rank output
  and actual rank, and performs no provider calls. UI explicitly says actual
  classification is retrospective and labels timestamp limits.
- **Real experiment evidence:** source dataset SHA-256
  `eef5a7277d2f62fdf263e94cadbc7a5f5c38cd6acdbea9dc00549d5caef37fd8`;
  regenerated prediction artifact SHA-256
  `88195b26ef5f3f5ab86d7b8a906233e7b0c6ef1af05401fc9f74d3afe91d011b`.
  Training coverage 684 rows/35 events; validation 342/18; test 354/18.
  Ridge remains the 2024 selection (MAE 2.8362 vs FP3 2.8975). On 2025,
  Ridge MAE 3.2433, Spearman .7095, pole-hit .2778, top-three overlap .6667;
  FP3 MAE 3.3141, Spearman .6848, pole-hit .2222, top-three .6296. Paired
  Ridge−FP3 MAE delta −.0708, 95% seeded 10,000-event bootstrap interval
  [−.2934,+.1587]. The interval crosses zero; no reliable superiority or
  probability claim is made. Full metrics and caveat are in `PREDICTION_LAB.md`.
- **Source URL/license:** no data fetched in this milestone. Existing source
  adapters/data lineage are documented in `DATA_CONTRACTS.md`; links include
  OpenF1 API docs and its pinned CC BY-NC-SA 4.0 license, plus FastF1 docs and
  package MIT license. Software package license is not treated as a license
  for upstream timing data. No third-party code was copied; raw data and model
  artifacts remain Git-ignored.
- **Commands/evidence:** backtest reproduction command recorded in
  `PREDICTION_LAB.md`; exit 0. `.venv/bin/pytest -q`: 61 passed, one existing
  Starlette/httpx deprecation. `.venv/bin/ruff check src tests scripts` passed.
  Scoped mypy command passed 20 source files. Web: 5 unit tests, ESLint and
  TypeScript/Vite build passed (JS 431.12 KB/141.19 gzip; CSS
  78.22 KB/15.43 gzip); 10 Chromium cases passed in 21.8 s. API real artifact
  manifest returned HTTP 200/6,337 bytes and 36 events; Abu Dhabi 2025 event
  returned 20 drivers. Screenshot reviewed at the path in `PREDICTION_LAB.md`.
- **Bug/failure notes:** first ESLint run objected to synchronous result/loading
  state resets in an effect; the page now derives loading from the selected
  event and current result, then final ESLint passes. Whole-repo `ruff check`
  finds 17 pre-existing notebook/interactive-cell findings, including three
  style findings in the two preserved user-owned untracked helper files; no
  unrelated cleanup was made. Direct mypy without repo flags found missing
  third-party stubs and one inferred key type; the supported scoped command
  with `--follow-imports=silent --ignore-missing-imports` and explicit typing
  passes.
- **Unresolved:** no individual feature observation or provider publication
  timestamps; no after-FP1/after-FP2 forecast snapshots, 2026 walk-forward,
  probability calibration, model attribution or production model registry;
  source-provider boundary and Q1 pace versus final classification still limit
  interpretation. This is one historical UI backed by the existing dataset.
- **Documentation changed in the same milestone:** `PREDICTION_LAB.md`,
  `ROADMAP.md`, `AGENT_WORKLOG.md`, `IMPLEMENTATION_ATLAS.md`,
  `TEST_EVIDENCE.md`, `EXPERIMENT_REGISTER.md`, `DECISIONS.md`,
  `GLOSSARY_FOR_LEARNING.md`, `CHATGPT_HANDOFF.md`, `ML_EVALUATION.md`,
  `DATA_CONTRACTS.md`, `ARCHITECTURE.md`, and `RACE_CONTROL_UI.md`.
- **Commit/push:** source and required milestone notes are in implementation
  commit `9f928361c9c7fdf59a2e685dc2994137cf942e35`, pushed normally to
  `origin/feat/foundation`. `git ls-remote` returned this exact SHA. A separate
  docs follow-up records this proof; no force push or coauthor trailer.

## 2026-10-16 UTC — phase-aware qualifying Prediction Lab (partial M5/P4)

- **Starting source SHA:** `d60c36f77295075bd50a1950ccabefc7eb5022b9` on
  `feat/foundation`; only the two pre-existing user helper files were
  untracked. They remain untouched.
- **Scope:** add separate after-FP1, after-FP2 and pre-qualifying historical
  snapshots; evaluate on event groups with 2023 training, 2024 model selection
  and 2025 holdout; show the phase and scheduled cutoff in the local Prediction
  Lab. No live prediction path was added.
- **Source/algorithm:** cached mixed Parquet filtered to OpenF1 2023–2025
  (1,038 rows; dataset SHA-256
  `eef5a7277d2f62fdf263e94cadbc7a5f5c38cd6acdbea9dc00549d5caef37fd8`) plus
  cached OpenF1 `/sessions` schedule (canonical schedule SHA-256
  `af8ce323bb62591d925fded4fdaf696276921a305bb26fbc970573579d82734d`).
  Scheduled practice end labels each phase cutoff and is checked against the
  next session start. Per-value result publication times are absent, so this
  is not an exact historical as-of replay. FastF1 2022 schedule was
  unavailable offline; one provider across all splits was preferred over
  mixing provider semantics.
- **Features/baselines:** after FP1 uses FP1 gap/rank and FP1 best lap; after
  FP2 uses FP1+FP2 gap/rank and FP2 best; pre-Q uses the existing eight common
  FP1/2/3 gap/rank/improvement features and FP3 best. Rows without that
  phase's measured baseline are excluded instead of imputing pace. Each phase
  independently selects among its practice baseline, Ridge and LightGBM from
  2024 mean event position MAE. Q1 gap is the prediction target; final
  qualifying classification is the evaluation label.
- **Coverage:** FP1 has 275/325/319 driver rows over 16/18/18 events for
  train/validation/test. FP2 has 310/333/351 over 16/18/18. Pre-Q has
  311/342/354 over 16/18/18. All 52 OpenF1 conventional event schedules have
  cutoff metadata in each phase.
- **Held-out results:** FP1-selected Ridge 3.6736 vs FP1 3.7245 MAE; paired
  delta −0.0508, 95% event bootstrap [−0.1676,+0.0628]. FP2-selected Ridge
  3.4827 vs FP2 3.6802; delta −0.1975, interval [−0.4056,+0.0218]. Pre-Q
  selected the FP3 baseline on validation: FP3 3.3141 vs Ridge 3.3100; Ridge
  delta −0.0041, interval [−0.2617,+0.2626]. All 2025 Ridge intervals cross
  zero; no reliable improvement or probability claim is made.
- **Modified source:** `qualifying_backtest.py` generalized its measured
  practice baseline; new `qualifying_phases.py` builds schedules, features,
  event-grouped runs and checksummed outputs; new `qualifying_phase_lab.py`
  validates allowlists, split/model coverage and checksums; `api.py` adds two
  local routes; `PredictionLab.tsx` switches forecast phase and renders
  phase-specific rankings/cutoffs. `test_qualifying_phases.py` covers schedule,
  feature legality, split and API contracts; browser scenario switches FP1
  and pre-Q.
- **Artifacts:** ignored local files in
  `data/processed/qualifying_phases/`. Prediction Parquet SHA-256
  `db7232189404da2f74970d20d1f69d65b082c128252e4b908308651857a79fe1`;
  summary CSV `32a742539764fbfc8f5716956c3a06f8c3b07456fbe7cec5a315b7421602eac6`;
  event metrics CSV `d93edba4d7be17f99a6d867bd98484b1ecf22fddf4a37c9598a9cacb3dcb6fc4`;
  bootstrap CSV `e20dfe797190df48b4b408776d4866a60adb4a4a311e4b026eaf73f7017b6286`.
- **Verification:** real cached-data experiment command:
  `.venv/bin/python -m f1_racelab.models.qualifying_phases --dataset data/processed/qualifying_mixed_2022_2023_2024_2025.parquet`.
  `.venv/bin/pytest -q`: 65 passed in 3.99 s, one existing Starlette/httpx deprecation
  warning. `.venv/bin/ruff check src/f1_racelab tests`: pass. Scoped mypy on
  four model/API modules: pass. `npm run test:unit`: 5 passed; `npm run build`
  and `npm run lint`: pass; `npm run test:e2e`: 10 Chromium cases passed in 23.8 s,
  including the phase switch. The first data run found missing FP1 measured
  baselines; excluding absent baseline rows fixed non-finite baseline ranks.
  A later audit found that shared `prepare_dataset` still required FP3 best
  times for every phase. It now filters on the selected phase baseline,
  removing that unintended future-session cohort requirement. Artifacts and
  phase metrics above were regenerated after this correction.
- **Documentation:** milestone detail is in `QUALIFYING_PHASES.md`; roadmap,
  atlas, experiment register, decisions, glossary, test evidence and
  `CHATGPT_HANDOFF.md` are updated in this checkpoint.
- **Source/rights:** cached public OpenF1 API fields; see
  https://openf1.org/docs/ and the pinned OpenF1 license link in
  `QUALIFYING_PHASES.md`. No raw provider data or generated predictions are
  committed.
- **Unresolved:** exact result publication time, 2022 FastF1 schedule lineage,
  provider overlap breadth, calibration, 2026 walk-forward and driver/team
  identity continuity. This remains retrospective research.
- **Final browser review:** the enhanced Prediction Lab scenario passed
  separately (1 test, 8.8 s) after the full 10-test suite. It verifies that
  Austria FP1 PIA is eligible rank 1 but official qualifying P3, and that the
  validation uncertainty label displays 2024. Two delegated reviews helped
  identify the classification ambiguity and incomplete artifact-coverage
  checks; both are corrected and tested in this checkpoint.
- **Commit/push:** source and required documentation committed together as
  `8a2c06c898e93f0083058a7abb3bcbd5b3f9b606`, pushed normally to
  `origin/feat/foundation`. `git ls-remote origin refs/heads/feat/foundation`
  returned that exact SHA. Author/committer are Aymen Jedidi; no assistant
  coauthor trailer is used. A docs follow-up records this publication proof.

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


## 2026-10-16 UTC — validated driving-line geometry and focused map context (P2 partial)

- **Starting source SHA:** `1a5b7b4fa64ae3ceab0ab7cb6957c2331a5ce7b6` on `feat/foundation`.
  Two pre-existing untracked `ml/features/` helpers are preserved. Final verification passed; publication was pending at this earlier checkpoint; the publication proof below records completion.
- **Scope and paths:** `session/geometry.py`, `session/openf1_replay.py` and
  provider cache support select and persist typed display geometry;
  `session/location_history.py` and `api.py` attach optional selected-driver
  location context to canonical state. `TrackMap.tsx`, `circuit-geometry.ts`,
  `App.tsx` and `App.css` separate the static track trace from car/trail marks.
  `apps/web/benchmarks/`, `package.json`, geometry/trail/API/browser tests and
  the required docs record correctness and bounded browser observations.
- **Algorithm:** reject pit laps, missing timed laps, insufficient samples,
  bad sample/boundary gaps, open traces and coordinate jumps. Select one
  measured driving line deterministically by closure ratio, gaps, driver and
  lap; preserve its points and explicitly append a short closing segment.
  Hash source samples/lap and geometry identity, derive bounds, normalized XY,
  polyline arc length and segment directions. Coordinates/length retain unknown
  provider units; time is session seconds and direction is radians.
- **Map context:** use indexed source samples in `[max(0,t−12),t]` and the
  existing canonical current position. Disconnect long gaps/jumps; mark an
  interpolated current endpoint estimated. `atan2(dy,dx)` gives recent
  displacement direction, not chassis yaw. The frontend flips Y for SVG,
  negates heading angle, memoizes the static path and keeps all panel time
  tied to the returned `RaceState` timestamp.
- **Real evidence:** geometry audit
  `data/processed/replay_packs/geometry_audit.json`: Monza driver 30 lap 7,
  168 source points; Monaco driver 16 lap 54, 191; Brazil driver 31 lap 52,
  166. Accepted/candidate laps: 911/976, 1322/1516, 1017/1137 respectively.
  Rebuilds used cached OpenF1 data with network requests blocked; source
  sample and lap hashes are stored in each geometry provenance record.
- **Checks so far:** 13 new geometry tests plus 5 existing focused tests pass;
  8 frontend unit tests, build and lint pass. The explicit offline CLI rebuild, replay/context validators, 360 real
  trail probes and all 11 browser scenarios now pass; final full Python/static
  verification passed with 92 tests. The independent baseline
  browser observation completed; it predates the extracted map/trail changes.
- **Benchmark:** `cd apps/web && npm run benchmark:replay` opts into 4 seconds
  per session at 1×, 1440×1000 headless Chromium. Baseline artifact is
  `data/processed/browser_benchmarks/replay-performance-2026-10-16T16-32-00-868Z.json`.
  All three sessions had zero sampled panel clock disagreements and no page
  exceptions. RAF p95 was 33.3/16.8/33.3 ms (Monza/Monaco/Brazil); this is
  callback scheduling, not painted FPS. Final idle-worktree observations are recorded below.
- **Choice/limits:** retain SVG for this bounded workload and memoize the
  static trace before considering Canvas/WebGL. No new runtime dependency,
  upstream asset reuse or physical-unit conversion. Geometry is approximate,
  with null physical length/width/pit lane and an estimated source-lap origin.
  No official start-line or surveyed accuracy claim; no causal cross-run
  performance claim. Public source: https://openf1.org/docs/; existing provider
  license/provenance policy applies; generated packs stay ignored.
- **Next:** publish the verified checkpoint, then expand measured telemetry
  and source geometry coverage. Root will add
  milestone commit SHA and remote publication proof after normal push.

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


## 2026-10-16 UTC — multi-session telemetry and six-channel inspection (P3 partial)

- **Starting source SHA:** `acff2d86ba79ef9dc23c20ac3070d54a989bab8e` on `feat/foundation`.
  The prior checkpoint verified 92 Python tests, 8 frontend unit tests and 11
  browser scenarios. Those are prior evidence; new final checks are recorded below.
  Preserve the two unrelated untracked user helpers. No publication yet.
- **Scope:** grow the Monza-only comparison into an explicit per-race catalog,
  locally reproducible offline builder, six-channel API/UI and stricter math
  contracts. Current selected pairs: Monza #1 L50/#4 L50; Monaco #1 L40/#31
  L40; Brazil #1 L52/#31 L52. Real rebuilt artifact metrics are recorded below.
- **Current source changes:** `telemetry/artifacts.py` introduces immutable
  `ComparisonSpec`, `COMPARISONS` and stable artifact identities/paths;
  `contracts.py` validates sessions, distinct laps, full regular common grid,
  increasing within-lap elapsed times and B−A delta. API channel projection and
  offline CLI now support the explicit catalog. `lib/telemetry-comparison.ts` now defines six
  channels, null-aware/discrete cursor values and disconnected channel paths;
  `TelemetryPanel.tsx` integration and new browser cases pass.
- **Algorithms/units:** speed trapezoids integrate metres using km/h÷3.6;
  resample both laps on a 5 m common grid ending before the shorter integrated
  lap distance. Delta is elapsed B minus elapsed A in seconds. Speed/throttle/
  RPM are continuous channels; brake source values, gear and DRS codes hold
  earlier values between samples. Missing source values remain null and break
  plotted paths. The replay cursor uses reference-lap UTC start relative to
  canonical session origin; it becomes unavailable outside sampled elapsed
  coverage rather than freezing at its tail.
- **Caveats:** estimated speed-integrated distance is not surveyed track
  distance. These selected laps do not establish equal fuel, tyres, weather or
  unobstructed running. Monaco has no cached pit resource, so no pit-in-clean
  proof is available. Brake/DRS codes retain source semantics and throttle may
  exceed nominal 100; do not reinterpret them as measured pressure or a
  universal DRS-open boolean. No independent telemetry clock is introduced.
- **Evidence/publication:** dataset rows, source/artifact hashes, commands/tests and
  charts are recorded below; commit/push proof remains pending.
  Source: https://openf1.org/docs/; no upstream implementation copied and raw
  source/derived artifacts remain ignored under the existing rights policy.
- **Next:** publish the verified source/docs checkpoint normally, then expand
  arbitrary lap/driver selection and compatible-layout/sector comparisons.

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


## 2026-10-17 UTC — per-session lap library and driver/lap selection UI (P3 partial advance)

- **Starting source SHA:** `9a13f6eef679c417fc3bc6a8beddd320504dbc06` on
  `feat/foundation`, synchronized with `origin/feat/foundation`. The two
  pre-existing user helper files under `ml/features/` were left untouched.
- **Scope:** build an offline, content-addressed lap library for all three
  sessions; add a driver/lap selection control to the Telemetry panel; wire
  the new API catalog route and extend the existing comparison route to accept
  arbitrary selections from the library.
- **Modified source paths and symbols:**
  `src/f1_racelab/telemetry/lap_library.py` defines `LapEntry`,
  `DriverEntry`, `LapSelection`, `LapLibrary`, `build_library`,
  `load_library`, `load_lap` and `compare_library_laps`; the builder indexes
  cached car_data timestamps, validates each lap's bounded window and writes
  a deterministic gzip with a content-addressed filename; the manifest is
  published atomically only after all referenced files exist.
  `src/f1_racelab/telemetry/contracts.py` relaxes `source_hashes` minimum
  from 3 to 2 to allow same-driver comparisons that share one car_data source.
  `src/f1_racelab/api.py:create_app` adds `telemetry_library_roots` override,
  `GET /api/v1/replay/{slug}/telemetry/laps` and extends the existing
  `lap-comparison` route to validate and serve library-backed arbitrary pairs.
  `apps/web/src/lib/telemetry-selection.ts` defines TypeScript types and
  `initialTelemetrySelection`, `telemetrySelectionError`, `changeTelemetryDriver`
  and `telemetrySelectionQuery`.
  `apps/web/src/components/TelemetrySelection.tsx` renders driver/lap dropdowns
  and "Compare laps" with a validation note.
  `apps/web/src/App.tsx` fetches the library on session change, initializes a
  `telemetryRequest` state and calls `applyTelemetrySelection`; the
  `TelemetryPanel` receives the selector as a `controls` slot.
  `apps/web/src/components/TelemetryPanel.tsx` accepts `controls?: ReactNode`
  and exposes `data-reference-driver/lap` and `data-comparison-driver/lap`
  attributes.
  `apps/web/src/App.css` adds layout rules for the selection group.
  `tests/test_telemetry_library.py` covers build, roundtrip, pit filtering,
  same-driver comparison, reverse delta and manifest security mutations.
  `tests/test_telemetry_library_api.py` covers catalog/selection HTTP routes.
  `apps/web/tests/telemetry-selection.test.ts` covers eligibility, driver
  change and query serialization.
  `apps/web/e2e/replay.spec.ts` adds the selection scenario and fixes the
  Monaco pit test's `role="status"` conflict.
- **Algorithm/units:** the builder sorts car_data by timestamp and selects a
  window `[lap_start - gap, lap_end + gap]` (gap = 1.0 s default), delegating
  to `build_lap_telemetry`; rejected laps record the reason string. Pit-in
  check uses cached `pit` data when available, marking status
  `checked_not_pit_in` or `unverified`. `compare_library_laps` includes pit
  source hash only when it was used for both laps' sessions. Manifest filename
  encodes `driver-{N}-lap-{M}-{sha256}.json.gz`; content hash guards against
  replay and substitution.
- **Real evidence:** Monza 2025: 2 available drivers (1/4) with 22/23 accepted
  laps; 18 total rejected across pit/pit-out/gap reasons; default selection
  driver 1 L50 vs driver 4 L50 (the existing reference comparison). Monaco
  2023: 2 available drivers (1/31) with 61/61 accepted laps. Brazil 2024: 2
  available drivers (1/31) with 45/46 accepted laps. Other drivers in all
  sessions report `car_data source is not cached`. Libraries were built offline
  from existing cached provider data; no new network request was made.
- **Accessibility fix:** `TelemetrySelection`'s informational paragraph
  (driver count) no longer carries `role="status"`; only the validation error
  case does. This resolved a `getByRole('status')` count conflict with the
  Monaco pit unavailable note in the existing Chromium test.
- **Verification:**
  `.venv/bin/pytest -q` — 123 passed in 4.35 s, one existing Starlette/httpx
  deprecation warning.
  `.venv/bin/ruff check src/f1_racelab tests` — clean (corrected import order
  in `test_telemetry_library_api.py`).
  `mypy src/f1_racelab/telemetry src/f1_racelab/session src/f1_racelab/api.py
  --ignore-missing-imports` — 21 source files, no issues.
  `npm run test:unit` — 16 passed; `npm run lint` and `npm run build` passed
  (JS 458.09 KB / 149.53 KB gzip, CSS 80.28 KB / 15.81 KB gzip).
  `npm run test:e2e` — 15 Chromium scenarios passed in 36 s, including the
  new selection scenario and all prior 14.
- **Failure and fix:** initial E2E test selected the wrong dropdown (driver
  instead of lap) causing a 30-second timeout. Corrected to use `combos.nth(1)`
  (the side-A lap dropdown). A prior Ruff failure corrected import block order
  in the API test file.
- **Limits:** only VER and NOR/SAI/OCO have cached car_data in these three
  sessions; other drivers are labelled unavailable. Lap distance remains
  speed-integrated and estimated. No cross-year or sector comparisons exist.
  The `LapComparison.source_hashes` minimum of 2 allows same-driver
  single-source comparisons; the prior minimum-3 requirement was not a
  stated contract invariant and matched an implicit three-source assumption
  that does not apply to same-driver pairs.
- **Commit/push:** implementation commit
  `32db149737d56d5e32147fdde5080820cf9eb499` pushed normally to
  `origin/feat/foundation`; `git ls-remote` returned the identical SHA.
  Author: Aymen Jedidi; no assistant coauthor trailer. The two unrelated
  user helpers under `ml/features/` remain untracked.

## 2026-10-17 UTC — P5 Race Strategy Simulator and Strategy Lab

- **Before:** branch `feat/foundation`, HEAD `a514042` (docs: record lap library
  and selection UI publication). Four Python files in `src/f1_racelab/strategy/`
  existed but were unverified and unintegrated.
- **Objective:** verify the strategy simulator, add the API layer, build the
  React Strategy Lab panel, write tests, and update all required docs.

### What was built

**`src/f1_racelab/strategy/`** — all files created in the prior (summarized)
session:
- `models.py`: `TyreCompoundModel` (degradation_delta, net_pace_offset),
  `FuelModel` (fuel_remaining, lap_time_delta), `PitModel` (total_pit_loss_s),
  `RaceSpec`, `DriverModel`; calibrated dicts `CIRCUIT_COMPOUNDS`,
  `CIRCUIT_FUEL`, `CIRCUIT_PIT`, `RACE_SPECS` for monza-2025 / monaco-2023 /
  brazil-2024.
- `simulator.py`: `simulate_race()` — lap-by-lap deterministic simulator;
  `PitStop`, `Strategy`, `LapState` (frozen), `CarSimulationState` (mutable);
  traffic heuristic (TRAFFIC_WINDOW_S=2.0s, TRAFFIC_PENALTY_S=0.3s); utilities
  `race_time`, `gap_history`, `undercut_window`.
- `optimizer.py`: `evaluate_strategy`, `compare_strategies`,
  `enumerate_strategies` (0/1/2-stop combinatorial search), `best_strategies`;
  `StrategyEvaluation` frozen Pydantic model; `SIMULATION_LIMITS` tuple.
- `monte_carlo.py`: `MCWorld` (seeded Gaussian noise, lap + pit sigma),
  `MCWorld.apply()`, `MCResult`, `mc_compare()` (shared random worlds technique).
- `calibration.py`: `calibrate_base_lap_time` (40-60 pct percentile of clean
  laps from pack), `calibrate_pit_model`, `calibrate_tyre_degradation` (OLS
  linear after removing fuel trend), `sanity_check_monza`.

**`tests/test_strategy_simulator.py`** — 24 tests across five groups:
1. Model unit tests: warm-up only on lap 1, fuel delta monotonically decreasing,
   pit model total loss summation.
2. Simulator contracts: lap count matches scheduled_laps, cumulative time
   non-decreasing, pit lap flag and extra time, compound changes after pit,
   stint_lap resets to 1 after pit, deterministic re-run, all laps labelled
   `estimation='simulated'`.
3. Gap and undercut utilities.
4. Optimizer: evaluate, compare sorted ascending, enumerate no duplicates,
   best_strategies top_n limit, simulation_limits included in output.
5. Monte Carlo: count, seed stability, win fraction sums to ~1.0, limits
   present.
6. Real-data sanity check (skipped if pack absent): calibration within 1s of
   model, medium/hard slope < 0.05 s/lap, R² > 0.

**`src/f1_racelab/api.py`** — four new strategy endpoints:
- `GET /api/v1/strategy/{slug}/info` — compounds, spec, simulation_limits.
- `POST /api/v1/strategy/{slug}/compare` — deterministic rank of explicit
  strategies.
- `GET /api/v1/strategy/{slug}/best` — enumerate + rank with max_stops, top_n,
  pit_step, compounds query params.
- `POST /api/v1/strategy/{slug}/montecarlo` — shared-world MC comparison with
  n_worlds and seed.

**`apps/web/src/components/StrategyLab.tsx`** + **`StrategyLab.css`**:
- Three tabs: Best Strategies (compound + stop config → ranked table), Custom
  Compare (two side-by-side strategy editors with add/remove pit stops), Monte
  Carlo (same editors, world count selector, MC results table with win %, P5/P95).
- `CompoundBadge` — circular badge with official-ish compound colors.
- `fmtRaceTime`, `fmtDelta` formatting helpers.
- Simulation limits disclosure panel.

**`apps/web/src/App.tsx`**:
- Added `workspace` state value `'strategy'`.
- Added Strategy Lab nav button (FlagTriangleRight icon) alongside Prediction Lab.
- Full-page Strategy Lab view when workspace === 'strategy'.

### Verification

```
uv run pytest tests/ -q  →  147 passed (123 existing + 24 strategy) in 4.7 s
npm run build            →  tsc + vite clean, 469.70 KB JS / 152.24 KB gzip
```

- **Fix during development:** `test_tyre_fresh_offset_increases_monotonically`
  initially failed because the warm-up offset (0.3s at lap 1) is larger than the
  linear degradation at lap 2 (0.0105s). The test was corrected to check
  monotonicity only for ages ≥ 2 (post-warm-up); this is the correct semantics.

### Monza calibration values (from prior session, real VER data)

| Parameter | Value | Source |
|---|---|---|
| Base lap time | 82.8 s | 40-60 pct percentile, VER clean laps |
| Medium linear deg | 0.005 s/lap | essentially flat at Monza |
| Hard offset vs Medium | +0.30 s | measured from stint medians |
| Pit entry/stationary/exit | 14.5/2.5/8.5 = 25.5 s total | lane/stop data |
| Fuel 100 kg / 53 laps | 1.887 kg/lap, 0.030 s/kg | FIA standard estimate |

### Limits

- Strategy Lab does not exist in UI if the session slug is not in `RACE_SPECS`.
  Currently only monza-2025, monaco-2023, brazil-2024 are in the model.
- No E2E test for Strategy Lab (Playwright); the feature requires the FastAPI
  server to serve `/api/v1/strategy/{slug}/best` which is not mocked in tests.
- Calibration sanity check requires a local race pack; marked
  `test_real_data_calibration_monza` to skip naturally when pack absent.
- All simulation limits are explicitly included in every API response and in the
  UI disclosure panel. Simulated results are never mixed with historical data.

## 2026-10-17 UTC — P6 What-If, P8 3D Circuit, P7 Live WebSocket

### P6 — What-If Counterfactual Branch (commit f76d8b6)

**`src/f1_racelab/strategy/whatif.py`**:
- `BranchLap`: per-lap record, estimation='historical'|'simulated', is_fork_lap
- `BranchResult`: full paired timeline, delta, simulation_limits
- `branch()`: shared historical prefix (measured from pack) + separate
  simulated suffixes; cumulative time re-rooted at fork boundary
- `_load_measured_laps/_stints/_compound_at_lap`: pack readers

**API**: `POST /api/v1/strategy/{slug}/whatif`
- Body: driver_number, fork_lap, actual_strategy, counterfactual_strategy
- Returns full timeline pair, delta, counterfactual_is_faster

**UI** (`WhatIfLab.tsx` + `.css`):
- Fork-lap / driver number controls
- Side-by-side strategy editors with add/remove pit stops
- Summary card (actual vs what-if total + delta)
- SVG lap-time bar chart (blue=actual, orange=CF, dash=fork)
- SVG cumulative gap chart (green=CF faster, red=CF slower)
- Simulation limits disclosure; "What-If" nav button in App.tsx

**Tests** (13, all pass): compound_at_lap logic, historical segment length,
identical pre-fork laps, estimation labels, fork-lap marker, cumulative
monotonicity, delta consistency, invalid fork raises, direction on real Monza.

**Fix**: test_earlier_pit_is_faster_than_actual_at_monza used fork_lap=20
which was wrong (at Monza, Hard baseline is 0.30s slower; early pit without
degradation benefit doesn't win from lap 21). Corrected to fork_lap=30
where the CF already pitted at L25 in the simulation past, giving more fresh
Hard laps and matching the manually verified −25s result.

### P8 — Three.js/React Three Fiber 3D Circuit Viewer (commit fbd4b68)

**`Circuit3D.tsx`** + **`Circuit3D.css`**:
- Lazy Canvas mount (placeholder → "Open 3D view" avoids R3F init cost)
- normalizePts(): provider XY → [-5, 5] Three.js world
- buildSpline(): CatmullRomCurve3 (closed, alpha=0.5)
- TrackRibbon: TubeGeometry (r=0.18) on spline
- projectOnSpline(): 200-sample grid nearest-point search
- CarDot: sphere mesh + lerp animation + team color + emissive glow
- Two cameras: Top (fixed overhead) / Orbit (OrbitControls)
- Placed below 2D TrackMap in App.tsx workspace-grid
- No official car models; generic spheres per AGENTS.md license guidance

**Dependencies**: three@0.186.1, @react-three/fiber@9.8.2, @react-three/drei@10.7.9

### P7 — Simulated-Live WebSocket Fan-Out (commit f3098cb)

**`src/f1_racelab/live/ingest.py`**:
- `LiveSession`: asyncio 0.5s tick, SIMULATED_LIVE badge, subscriber queues
  (maxsize=4, drops slow clients)
- `LiveSubscription`: async context manager / iterator per subscriber
- `LiveRegistry`: singleton per slug; get_or_create() idempotent
- Reconnect: last snapshot delivered immediately to new subscriber

**API**:
- `WS /ws/live/{slug}?speed=1.0&start=0.0`: WebSocket fan-out
- `GET /api/v1/live/{slug}/status`: running/subscriber_count/mode

**React hook** (`use-live-session.ts`):
- useLiveSession(): WebSocket connect, exponential backoff (1→30s),
  badge state, subscriber count polling

**Tests** (7, all pass): snapshot shape, subscriber count, reconnect delivery,
state keys, stop semantics, registry singleton, HTTP status route.

### Totals at this checkpoint
- Python tests: 167 passing
- TypeScript build: clean (Three.js bundle 1.4 MB expected)
- Commits: f76d8b6 (P6), fbd4b68 (P8), f3098cb (P7) all pushed to feat/foundation

## 2026-10-29 — Walk-forward ML, ingestion hardening, layout repair

Base SHA `bd00ddf` (feat/foundation). Plan: `docs/ENHANCEMENT_PLAN.md`.

**Paths**: `models/qualifying_walkforward.py` (`build_frame`, `add_weekend_context_features`,
`walk_forward`, `ResidualScale`, `monte_carlo_ranks`, `probability_audit`),
`models/walkforward_lab.py`, `data/quality.py` (`audit`, `coverage_matrix`),
`data/openf1_qualifying.py` (`OpenF1Client._fetch/_read_cached`), `api.py`
(2 endpoints), `apps/web/src/components/ForecastPanel.{tsx,css}`,
`PredictionLab.tsx`, `App.css`.

**Algorithm/units**: see `ML_WALKFORWARD.md` (gap in percent of event-best lap;
ranks 1-based; seeded 4,000-draw Monte Carlo).

**Why**: LambdaRank optimises the ordering directly; the ensemble gives a gap scale
for sigma; sigma/multiplier use only earlier events. Quality audit reports instead
of editing data. Client retries are bounded (5 attempts, capped jittered backoff).

**Bugs found and fixed**: replay grid placed 4 children in 3 columns (dead right
column); mobile top bar overflowed (2 e2e tests failed on the baseline); stale
`Ensemble` test year in my own test.

**Caveats**: ensemble 2025 pole-hit 0.167 is below baseline 0.222 (noisy, 18 events);
rank-interval coverage 89.5% vs 80% nominal; 3 React lint errors predate this work.

## 2026-10-29 (2) — plan items executed: pipeline, 2026 data, race history, lint

* `data/pipeline.py`: one command, OpenF1 sync → provider merge → quality gate →
  `pipeline_manifest_<years>.json` (args, step results, dataset SHA, versions).
  Offline run reproduced the existing 2023–2025 dataset byte-for-byte
  (SHA `eef5a727…37fd8`). `mixed_qualifying.combine` generalised to any OpenF1 years.
* Live sync of 2026 (polite 2.1 s pacing): +12 weekends, 259 rows, gate passed
  (0 errors, 39 warnings across 83 weekends). 404 results are `NOT_PUBLISHED`, not `ERROR`.
* `session/timeline.py` + `GET /api/v1/replay/{slug}/timeline` + `PositionChart.tsx`:
  position / gap history from canonical `state_at`, click-to-seek on the shared clock.
* ML: teammate-correlated Monte Carlo; 2026 evaluated → **no transfer** (see `ML_WALKFORWARD.md`).
* Lint: the 3 pre-existing errors fixed (`key={slug}` remount for Strategy/What-If labs,
  derived closed status and snapshot ref in `use-live-session`).
* Not done: race-finishing model, sprint weekends, per-feature `observed_at`, router/shell
  refactor, regime-aware model (pre-declared only).

## 2026-10-29 (3) — ML/DL/CV mandate: infrastructure and Race Pace Intelligence

Done: `ml/common` (cards, fingerprints, guards, registry, metrics), `ml/pace` (fetch, dataset,
benchmark, service), 3 API routes, research doc `docs/research/RACE_PACE_INTELLIGENCE.md`.
Real result: LightGBM MAE 0.575 s vs 0.682 s anchor over 65 held-out races (−0.107 [−0.138, −0.076]);
persistence 0.593 s is a strong baseline; weather features did not help.
Not done: React workspace, Strategy Lab hook, multi-lap forecast, Driver DNA (PyTorch not installed),
RaceVision, Overtake Intelligence, Neural Qualifying extension, Radio Intelligence, MLflow.
Audit: 8 earlier commits carry `Co-Authored-By` trailers (pre-existing; history not rewritten).

## 2026-10-29 (4) — Race Pace workspace
`RacePaceLab.tsx/.css`, `onOpenPace` navigation, driver list in `/api/v1/pace/races`, e2e test.
Verified: `npx tsc -b`, `npm run lint` clean, `npm run build`, Playwright 17/17. Chart axis uses an IQR range so
undetected neutralised laps do not flatten it. Still open: Strategy Lab hook, multi-lap forecast, other five modules.

## 2026-10-29 (5) — Race Pace quality gates (A-D, F, H) and CI
Source SHA before: c051276. Added `ml/pace/{audit,strict,inference,bundle}.py`, `POST /api/v1/pace/predict`, `.github/workflows/ci.yml`, README status table; `benchmark.py --refit-only`. Inputs: `data/processed/race_pace/{predictions,pace_frame}.parquet`. Outputs: `audit.json`, `strict_protocol.json`. Method and numbers: `docs/research/RACE_PACE_INTELLIGENCE.md`.
**Bug found:** the served artifact was pickled with `LgbmBundle` in `__main__`, so it could not be loaded outside the benchmark process; fixed by moving the class to `bundle.py` and refitting (new SHA-256 `98b611f3…adf8c2`). **Findings:** gain over persistence not significant (-0.018 s [-0.057, +0.029]); strict protocol vs fair baseline -0.059 [-0.133, +0.017]. Caveats: gate G (Strategy Lab opt-in) not done; 2026 is not an untouched holdout for the race model.

## 2026-10-29 (6) — Milestone 1 completion and Driver DNA
Added `strategy/ml_overlay.py` + `MlPaceOverlay.tsx` (gate G); `ml/driver_dna/{dataset,protocol,handcrafted,baselines,nets,evaluate_nets,service}.py`, `DriverDnaLab.tsx`, `/api/v1/driver-dna/summary`, `docs/research/DRIVER_DNA.md`. Artifacts under `data/processed/driver_dna/` (git-ignored). Bug fixed on the way: car_data cache files are compact JSON, so a spaced-key matcher found no files. Caveats: three races only; neural models not clearly better.

## 2026-10-29 (7) — RaceVision (blocked) and Overtake Intelligence
RaceVision: no licensed camera dataset available, nothing implemented, documented as BLOCKED in `docs/research/RACEVISION.md`. Overtake: `ml/overtake/{dataset,benchmark}.py`, `GET /api/v1/overtake/summary`, `tests/test_overtake.py`, `docs/research/OVERTAKE_INTELLIGENCE.md`. Real data: 29,608 pairs, 1,595 passes, 22,637 scored. LightGBM raw Brier 0.0329 vs gap-only logistic 0.0407, paired -0.0079 [-0.0105, -0.0056]; isotonic calibration did not help. Bug found in own test data (in-lap flag placed on the wrong row), fixed. Not done: UI.

## 2026-10-29 (8) — Neural Qualifying extension (exploratory)
`models/neural_qualifying.py`, `tests/test_neural_qualifying.py`, `docs/research/NEURAL_QUALIFYING.md`. 48 real events; no variant significantly better than the existing ensemble (all paired intervals include zero); regime shrinkage removes the 2026 loss but gives no gain. Labelled exploratory because the 2026 outcome was known.

## 2026-10-29 (9) — Engines layer (DuckDB, Spark, Delta)
Added `engines/{transforms,run}.py`, portable SQL, `mape`/`bias` metrics, `tests/test_engines.py`, `docs/research/ENGINES.md`; optional extra `engines`. Real data: all engines identical on 83,523 rows; pandas fastest at this size. Databricks untested.

## 2026-10-29 (10) — pipeline runner, feed check, Overtake UI
`engines/{pipeline,feed_check}.py`, `tests/test_feed_and_pipeline.py`, `OvertakeLab.tsx` + e2e. Feed check found 53 red-flag rows >400 s (non-green); rule narrowed to green-eligible rows. 20/20 Playwright.

## 2026-10-29 (11) — mypy cleared
`uv run mypy src/f1_racelab`: Success, 85 files. Annotations added in strategy, session, ml/pace, ml/overtake, ml/driver_dna and api; `fastf1_source.load_session` now accepts `event: str | int` (it is called with a round number). 244 tests pass, ruff clean.

## 2026-10-29 (12) — forecast review
`engines/forecast_review.py` + SQL + test. Finding: 2026 LightGBM bias -0.293 s (persistence -0.031 s); MAPE under 1% everywhere.

## 2026-10-31 — integrated deployment, research provenance and reliability

Starting/fetched SHA `129e4b106a7ad06afec124be44095c6f091e66e2`, branch
`feat/foundation`, Aymen Jedidi Git identity. Two untracked user helpers preserved.
Read master mandate/instructions, CI and research/handoff docs; audited hardware,
actual saved model and datasets. Baseline 271 Python / 20 Chromium; Ruff/mypy
and web checks pass. Optional engines/DL restored after a frozen default sync.

Changes: `infra/*`, Compose, `.dockerignore`, CI, operational API/middleware,
FastF1 lazy cache initialization; `ml/common/{tracking,reliability}.py` and
registry hook; research/agent saved-data endpoints; `ResearchObservatory`,
`AgentInvestigation`, lazy Three.js loader; SQL parser/deadline/fetch limits;
Ollama bounds/latency/citation-ID metrics. All primary functions, units, hashes,
commands, failure history and source/license references are documented in
`MLOPS_AND_DEPLOYMENT.md` and `research/FORECAST_DEBUG_AGENT.md`.

Real evidence: all three replay packs served in Compose; model integrity verified;
MLflow artifact import plus real 74,077-row green-lap refit (same model SHA);
65-race reliability recomputation preserves no-significant-gain conclusion.
Synthetic-only evidence: SQL/API tests and planted-fault warehouses. Actual local
Ollama inference on eight synthetic scenarios: 2/8 correct, 17.4275 s mean,
24 calls, zero nonexistent citation IDs. The prior local 24-case artifact was
found and documented (33.3%, protocol differs). Reference 200/200 is not LLM skill.

Bugs/failures: read-only container startup exposed cache creation on import
(fixed and tested); overlapping builds exhausted disk and broke one browser
run (reclaimed only session-created disposable cache/images and reran); lazy
Recharts triggered Vite optimizer navigation reset (prebundle config fixed);
existing reliability SVG duplicate keys fixed. No source data/volumes deleted.
No model-quality improvement, GPU execution, fresh holdout or CV training claimed.
Screenshots are generated by the research browser scenario and visually reviewed.
Final counts, commit/push and next work are in `CHATGPT_HANDOFF.md`.
