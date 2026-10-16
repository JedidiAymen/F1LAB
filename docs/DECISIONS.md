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
