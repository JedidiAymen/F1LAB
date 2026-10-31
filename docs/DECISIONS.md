# Engineering decisions

## D-001 — historical qualifying provider fallback, 2026-10-15

FastF1 3.8.3 could reuse 2022 cached timing, but an uncached 2023 Bahrain
timing request to `livetiming.formula1.com` returned HTTP 401. OpenF1's public
historical API documents 2023 onward and returned session results for a 2023
qualifying and FP3. We keep the original FastF1 dataset and create a separate
mixed-source dataset. Each row records provider, version, source identifiers,
hash and prediction cutoff. The raw OpenF1 responses are cached under ignored
`data/raw/openf1/`. See `ML_EVALUATION.md` for comparability limits.

Primary sources: [OpenF1 API](https://openf1.org/docs/) and the local FastF1
3.8.3 source in `.venv/lib/python3.12/site-packages/fastf1/req.py`. No
third-party repository code was copied. The inspected OpenF1 repository HEAD
was `87540e3f495bbd9bedb37b10456dd848c8f193d6`; its
[LICENSE](https://github.com/br-g/openf1/blob/87540e3f495bbd9bedb37b10456dd848c8f193d6/LICENSE)
is CC BY-NC-SA 4.0. The exact licensing of upstream F1 timing facts and a
future commercial product needs separate review. F1LAB keeps raw API data out
of Git and attributes the provider in data rows and documentation.

## D-002 — common practice feature set, 2026-10-15

OpenF1 `session_result` reports official best practice times, ranks, and Q1–Q3
times, but not the per-lap tyre, sector, and representative-lap features in the
FastF1 extractor. Models on the mixed dataset therefore use an explicit eight
field intersection: FP1/FP2/FP3 gaps and ranks plus FP1→FP3 and FP2→FP3 gap
changes. This avoids training on source-specific missingness as a proxy for
season. The original richer feature list remains available for a homogeneous
FastF1 experiment when access returns.

## D-003 — event-level uncertainty, 2026-10-15

The unit of evaluation and bootstrap resampling is the Grand Prix, because all
drivers in one event share weather, track evolution and conditions. A paired
bootstrap resamples candidate-minus-FP3 event errors with a fixed seed. Its
interval describes variability among these historical events; it is not a
calibrated probability that a model will win a future race.

## D-004 — one typed timeline and conservative provider mapping, 2026-10-15

The first replay foundation lives in the installable root Python package,
`src/f1_racelab/session`, because the `packages/schemas` and
`services/session-engine` folders currently have no independent build wiring.
Pydantic validates versioned events and state; a pure reducer applies ordered
events. OpenF1 race-control records are preserved as message events, not
translated into global flag state: sector/driver flags and pit-exit messages
cannot safely imply a session-wide flag. The 2025 Monza sample proves that
real messages can be normalized and replayed, but not car movement or timing.

## D-005 — sparse events and indexed measured sidecars, 2026-10-15

The full 2025 Monza pack holds low-frequency position/lap/pit/stint/control
changes as `SessionEvent`s and keeps approximate 2 Hz car coordinates plus
interval samples in indexed sidecars. This avoids pushing about 200,000 car
points through a reducer that retains an audit log, while `RaceSource.state_at`
still exposes one canonical state at any time. A checkpoint is stored every 64
events. Source coordinate points are measured as provider observations;
intermediate movement is estimated and limited to short, plausible brackets.
Lap completion is derived from approximate start + duration and marked
estimated. `session_result` is reserved for end-state QA to avoid showing final
classification at earlier replay times. The ~1.8 MB compressed pack is local
  and ignored, respecting uncertain redistribution rights.

## D-006 — local canonical state API and browser clock, 2026-10-16

The first 2D workstation requests `ReplaySource.state_at(t)` through a
read-only local FastAPI endpoint. The browser holds one playback time and
requests state at most five times per second. Timing, selected-driver details,
map points and visible race-control messages all use that same state response;
the UI does not reimplement the Python reducer or fetch 198,300 location rows.
The pack remains local and ignored. This trades smooth 60 Hz car motion for a
small, auditable, source-faithful first milestone. Provider coordinates that
repeat unchanged for 15 seconds are hidden as stale on the map; no retirement
event is inferred. The 15-second threshold is a visual heuristic and needs
validation on more sessions. Design and test evidence: `RACE_CONTROL_UI.md`.

## D-007 — distinguish missing provider resources, 2026-10-16

An OpenF1 `pit?session_key=9094` request for the 2023 Monaco race returned
HTTP 404 while eight other expected resources were available. The candidate
auditor therefore records only 404 as `null` availability, separate from a
successful zero-row response, and rethrows all other HTTP failures. The
future generic pack builder must carry this distinction into capability and
quality metadata rather than pretending Monaco had zero pit stops. See
`REPLAY_CANDIDATES.md`.

## D-008 — audited catalog and explicit source gaps, 2026-10-16

`ReplaySpec` now binds each supported race's IDs, round, scheduled UTC
origin and display metadata. The builder validates these against the
provider session response, uses the selected origin for all event/sidecar
times, and includes provider key in every event ID. Monaco's optional pit
404 becomes an unavailable capability; other HTTP failures propagate.
Null stint start and missing final DSQ lap total remain explicitly counted
gaps. Every state carries capabilities. The API's three-source cache is
keyed by slug, preventing one session's clock/state from serving another.
Real references and null-handling proofs: `REPLAY_GOLDEN_SESSIONS.md`.

## D-009 — anchored playback and real browser checks, 2026-10-16

The prior UI advanced React state on every animation frame. It now uses a
monotonic clock anchored at play/pause/seek/rate changes and samples that
clock every 200 ms. Seeks retain exact source milliseconds. Switching session
remounts the workspace and cancels old requests. This keeps one clock and
avoids 60 Hz whole-tree rendering. At this checkpoint there was no continuous
map interpolation; D-011 later adds a small playback-only CSS transform
between adjacent canonical samples. Four Playwright Chromium tests run against
real local packs; browser snapshots exposed an unnamed slider input, which was fixed.
The web lockfile is tracked despite a user-global ignore; the shadcn CLI is
a development dependency. Production-only npm audit is clean, with seven
upstream high advisories still reported for the development CLI chain.

## D-010 — source-time context and conservative display rules, 2026-10-16

Weather readings are source observations, so packs store them at their exact
provider timestamps and never interpolate or extend a session's existing time
window. `RaceState` retains the last observation for deterministic seeks; the
UI shows its values only when its age on that same session clock is between
zero and 120 seconds. The threshold is a display policy. `rainfall` means the
provider reported rain presence and does not mean the surface is wet or encode
intensity. Rainfall changes become historical navigation markers, while
current panel values still derive from the selected canonical state.

Global track status requires provider scope and message conditions. Explicit
Track flags require no driver number or sector; pit-exit messages are excluded.
Known SC/VSC endings and restart notices map to ending/unknown statuses and
never to green. This avoids turning a phrase such as “SAFETY CAR IN THIS LAP”
or “SESSION STARTED” into a false current flag. Unsupported and local signals
stay available as raw race-control messages. Proof on three real races and the
source lineage report are in `REPLAY_CONTEXT.md`.

## D-011 — as-of tyre stints and display-only map transitions, 2026-10-16

Existing OpenF1 stint start events and lap events are enough to expose tyre
history without adding future information to a source event. `RaceState` now
emits schema 3, while event and replay-pack schema remain version 2. A start
event appends a source-identified stint; the next source start closes its
predecessor at the latest completed lap, with the close event ID and quality.
Lap events extend only the currently open segment. The provider's eventual
`lap_end` is not copied onto the start event because doing so would reveal a
future stint boundary during an earlier replay seek. Same-lap starts are
accepted and retained: Monaco car 27 has two provider rows starting at lap 1.
The UI makes mapped overlap explicit and does not fill missing laps.

The map still receives canonical positions at 5 Hz. A short 180 ms CSS
transform bridges a forward visual update only when the state delta is at most
4 seconds (including the 3.2 second gap possible at 16× playback). Exact and
backward seeks, larger source gaps and initial appearance set `transition:
none`; the existing reduced-motion CSS rule remains in force. This is a
rendering aid, not another simulation clock or a claim of continuously
measured location. Source counts, tests and screenshots are recorded in
`REPLAY_STINTS_AND_MOTION.md`.

## D-012 — distance-integrated telemetry remains estimated, 2026-10-16

OpenF1 car-data speeds can support a useful comparative axis, but they are
sampled and lap start timestamps are approximate. F1LAB therefore integrates
each lap's reported speed independently with the trapezoidal rule, labels all
resulting distance as estimated, rejects source gaps over one second and
interpolates only boundaries bracketed within that limit. It does not claim
GPS alignment or surveyed metres. Continuous channels use linear interpolation;
brake, gear and DRS remain source-state values. Brake is named as a raw source
value and DRS retains its code because its meaning can be unclear. Provider
values are not clipped based on documentation assumptions. The first artifact
compares Monza 2025 laps 50 for cars 1 and 4 on a 5 m shared estimated-distance
grid; source hashes and limitations are in `DISTANCE_ALIGNED_TELEMETRY.md`.

The comparison is not a separate replay clock. Any UI cursor must derive from
the current canonical replay time, with the estimated distance shown as a
derived coordinate. D-013 records the first implementation; broader event
coverage and prediction work remain incomplete.

## D-013 — telemetry cursor follows canonical replay time, 2026-10-16

The distance comparison is an analytical sidecar, not a second session
timeline. `TelemetryPanel` computes reference-lap elapsed time by subtracting
its approximate UTC lap start from the replay pack's clock origin, then uses
the current `RaceState.session_time_seconds` to interpolate the shared-distance
grid. The cursor disappears outside that lap window. Jumping to the reference
lap calls the existing browser `PlaybackClock.seek()`. This keeps the chart,
map, timing and other data panels on the same selected replay state and makes
no continuous-position claim between 5 Hz API updates.

The API reads the generated, ignored local artifact and validates its
Pydantic contract and session identifiers. It does not make OpenF1 requests.
It projects the fields the graph uses while retaining response hashes; raw
channels remain in the local full artifact. Missing artifact paths are shown
as unavailable, not as an empty measured comparison. The first implementation
supports the default #1 L50 vs #4 L50 artifact naming across the catalog, but
only Monza has a generated artifact. Driver/lap selection and broader event
coverage remain future work. Full browser/API evidence is in
`DISTANCE_ALIGNED_TELEMETRY.md`.

## D-014 — historical predictions are local, checksum-verified and explicit about cutoff limits, 2026-10-16

The first Prediction Lab consumes the completed, event-grouped backtest
artifact instead of fitting or requesting data on page load. It reads only
ignored local output, validates the selected-model/split/target contract, and
checks SHA-256 for the prediction Parquet, split summaries, event metrics and
bootstrap reports. A missing or modified artifact returns unavailable. This keeps the browser view
reproducible and avoids provider traffic.

The model inputs are restricted to the eight shared FP1/FP2/FP3 practice
features; Q1 gap, Q phase times and current final position remain target/label
fields. The UI calls the result historical and displays actual rank only for
retrospective scoring. It reports the existing 2024 selection and 2025 held-out
metrics without claiming model superiority or calibrated probability.

`available_at` is a scheduled qualifying-start label. Since individual
practice-field observation and provider publication timestamps were not
retained, the audit records legal source-session lineage and plainly states
that limitation. It does not claim exact historical publication-time replay,
and after-FP1/after-FP2 snapshots remain future work. Detail and tests are in
`PREDICTION_LAB.md`.

## D-015 — phase snapshots use scheduled practice ends and one provider, 2026-10-16

The historical qualifying page now supports after-FP1, after-FP2 and
pre-qualifying snapshots. Each phase has an explicit source-session feature
allowlist and a measured same-phase practice-lap baseline. The cutoff timestamp
is the cached OpenF1 scheduled practice end, checked to occur before the next
scheduled session.

The archive does not retain when each final practice result became available
through the API. The UI therefore labels these as scheduled cutoffs and keeps
the provider-publication-time limitation visible. They are offline research
snapshots, not exact as-of or live forecasts.

FastF1 2022 schedule lookup was unavailable offline. The experiment uses
OpenF1 2023 as training, 2024 for selection and 2025 as holdout to avoid
provider changes between splits, accepting a smaller 16-weekend training set.
Missing measured phase baselines remove that driver from that phase rather than
imputing a lap. Ridge is selected after FP1/FP2, and FP3 baseline before Q;
all 2025 Ridge-versus-baseline event intervals cross zero. No superiority or
probability claim is made. Implementation and metric evidence are in
`QUALIFYING_PHASES.md`.

Phase ranks and leader/top-three metrics use the eligible subset. Official
qualifying position is projected separately as `qualifying_position` so an
eligible-cohort leader is not presented as the official polesitter. Since
phase cohorts differ, comparing phase MAEs does not by itself establish the
value of later practice; that requires a shared-cohort experiment.


## 2026-10-16 — audit one measured driving line and retain provider units

Select a complete, continuous timed lap deterministically rather than hardcode
VER lap 3. Retain source points, record rejection/closure diagnostics, hash
source lap/sample payloads, and preserve unknown provider units. Normalize by
bounds only for shared display geometry; label the origin as an estimated
source-lap point. Missing physical length/width, pit lane, sectors and corners
remain explicit. A visually closed trace does not prove surveyed accuracy.

Selected-driver trail and displacement heading belong in the canonical state
response at the requested time. Binary-search the existing source index and
reuse its current car location so chart/map time cannot diverge. Render the
static SVG trace through memoized projection; preserve measured/estimated
quality and disconnect missing samples. Profile before changing render engines.

Keep performance observations opt-in and fingerprinted. Record RAF scheduling,
DOM clock agreement, delivery/seek timing and JS heap without claiming painted
FPS, whole-process memory or causal improvement between differing sources/packs.

Temporal detail: measured trail vertices are at or before requested time `t`.
The canonical estimated endpoint may use a later source sample as the existing
historical interpolation bracket; this is retrospective reconstruction, not
proof that data had been published live by `t`. Without `focus_driver`, the API
returns strict canonical `RaceState` schema 3. Focused `location_context` is a
view extension of that same state response; it does not change the canonical
state schema or create another position/clock authority.


## 2026-10-16 — explicit lap catalog and source-valued telemetry channels

Use an explicit per-session catalog for supported historical comparisons and
retain source hashes; choosing laps does not certify identical conditions or
absence of pit-in when source coverage is unavailable. Require internally
consistent full shared-distance artifacts before API projection.

Expose speed, throttle, brake source value, RPM, gear and DRS code while retaining
nulls and provider units. Hold discrete channel values rather than inventing
fractional gears or DRS codes. Keep cumulative elapsed B−A beside the selected
channel. Canonical replay time determines the cursor; outside the shorter
shared-grid coverage the cursor is unavailable, avoiding a frozen tail that
could imply current data. Memoize distance paths before adding rendering tools.


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

## 2026-10-29 — Walk-forward evaluation replaces fixed splits for the headline model

Decision: retrain per event on strictly earlier events; fix hyper-parameters; declare
the candidate before evaluation. Rationale: fixed 2024 selection with 18 events was
noisy and the earlier Ridge/LightGBM did not separate from FP3. Consequence: more
compute (~16 s) and a documented conservative interval (89.5% vs 80%). The older
phase-aware lab is kept unchanged.

## 2026-10-29 — Do not tune on 2026; report negative transfer
The 2026 result is an out-of-regime test. Changing features/weights after seeing it would
turn it into training data. Decision: publish as-is, pre-declare a regime-aware variant,
and score it only on rounds that complete after it is fixed.

## 2026-10-29 — Report the fair baseline; do not claim a race-pace win
Naive last-lap persistence is a straw man at decision time (it ignores that the lap after an in-lap is an out-lap). The headline comparison is against persistence plus that rule, and pooled differences whose race-clustered interval includes zero are reported as no significant gain. mypy is advisory in CI until its 72 pre-existing errors are triaged.

## 2026-10-29 — Report Driver DNA as separability, not style; torch stays optional
Neural models did not clearly beat handcrafted features, so no deployed model or live endpoint was built. torch is an optional `dl` extra so CI and the core install stay light.

## 2026-10-29 — mypy is blocking in CI
All 102 errors cleared: 74 were missing type information for third-party libraries (configured as `ignore_missing_imports` for those modules only, in `pyproject.toml`), 28 were fixed in code. The earlier advisory setting is removed. Not yet run on GitHub Actions.

## 2026-10-31 — deploy locally, retain scientific contracts, expose negative evidence

Use production Docker/Compose first; API+web are default, storage/MLflow/Prometheus/
HTTP inference replica optional. Retain GitHub Actions; add real container smoke
coverage there. No parallel mandatory Jenkins/Kubernetes/cloud workflow.
Keep repo-relative `/app/src` layout until artifact paths are explicitly refactored;
move ingestion cache creation out of import-time serving. Digest-pin runtime bases,
read-only artifact mounts, localhost bindings, bounded resources and graceful stops.

Keep local model/card/SHA authoritative; MLflow is an optional REST sink so a
tracking outage cannot destroy successful training. Differentiate artifact import
from actual training, preserve dirty-source markers and original snapshots, retain
inherited evaluation provenance. Correct fingerprint documentation without changing
existing fingerprints. Existing hashes/manifests are adequate dataset versioning here.

Show actual paired uncertainty/negative model findings and descriptive PSI; never
call inspected events untouched holdouts or drift causal. Distinguish citation-ID
existence from support; expose actual low-performing LLM traces for review. Keep
agent SQL local/read-only with engine limits, not falsely advertised as a hostile
multitenant sandbox. Defer new CV training because RACECAR lacks annotations,
A2RL access/storage/GPU gate is unmet; do not silently download protected footage.
