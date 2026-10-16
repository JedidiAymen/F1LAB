# Replay tyre stints and map motion — 2026-10-16

**Starting source SHA:** `2feed4059141107b43c31bf87f9937c565e2bdef`

**Branch:** `feat/foundation`

**Implementation commit:** recorded in the follow-up publication checkpoint
**Source data:** existing local OpenF1 packs for sessions 9912, 9094 and 9636. No new provider request or pack event was required.

This milestone exposes tyre stint history at the canonical replay cutoff and
adds a small visual transform between nearby map samples during playback. It
does not add another timeline, infer missing tyre ranges, or create additional
position observations. P1 and P2 remain partial.

## Contract and algorithm

`src/f1_racelab/session/contracts.py:TyreStintState` is an immutable state
record with one-based stint number and lap start, optional as-of lap end,
compound, optional starting tyre age in laps, source event ID, closing event
ID, event time in seconds from the scheduled session origin, quality and
UTC-aware observation time. `DriverState.tyre_stints` holds these records in
source order. It is included in emitted `RaceState` schema version 3. The
stored replay packs and their `SessionEvent` envelopes remain schema version
2; schema 1 packs also remain readable. Pack files and source event counts did
not change.

The reducer is as-of and deterministic:

1. On a `StintPayload`, close only the prior open segment. Its lap end is the
   greater of its start lap and the driver's latest completed lap (or start lap
   if no lap is known). The close record keeps the prior state quality and the
   new stint event ID as `closed_by_event_id`.
2. Append the new stint with its source event ID, session time, quality,
   observation time, compound, lap start and tyre age at start.
3. On later `LapPayload` events, advance only the latest unclosed stint's lap
   end and record that lap event's quality. Older stints and future start
   events are not visible before their own source time.
4. Stint number and lap start may not move backward. Equal lap starts are
   allowed because the Monaco source has two distinct car-27 records starting
   on lap 1. Both records are kept; the UI calls out the mapped overlap.

The OpenF1 stint table can contain an eventual `lap_end`, but this implementation
does not copy that value into the earlier start event. Doing so would expose a
future boundary before it occurred in replay time. Lap ranges therefore come
from lap events observed by the selected cutoff and can preserve source gaps or
overlaps. Stint start `quality` is shown to the user; it is not a tyre-fit
timestamp or a tyre performance measurement.

## UI behavior

`apps/web/src/components/StintPanel.tsx` receives the selected driver's stints
from the same `RaceState` used by timing, weather, control and map panels. The
panel shows one horizontal lane per source stint, compound color, inclusive lap
range, start quality, current tyre age when available and the scheduled lap
axis. For `N = scheduled_laps`, the bar uses:

```text
left_percent  = 100 × (lap_start - 1) / N
width_percent = 100 × max(1, lap_end - lap_start + 1) / N
```

An open segment is drawn for at least its start lap and labelled in progress.
Each stint gets its own lane so a duplicated or overlapping source range is
not hidden by an overlaid bar. When mapped ranges share a lap, the panel says
both source records are retained. Missing laps are not filled.

`TrackMap` keeps the API and canonical clock at 5 Hz. CSS transitions only the
SVG car-group `transform` for a forward state update while `playing` is true
and the replay-time delta is positive and at most 4 seconds. The 4-second
ceiling covers a 3.2-second state gap at the supported 16× playback rate with
some scheduling room. The CSS transition lasts 180 ms with `ease-out`. Initial
appearance, paused exact seeks (including small forward seeks), reverse seeks
and larger gaps set inline `transition: none`. The existing reduced-motion
rule sets transition duration to zero. This changes presentation only; it does
not move the session clock, update `RaceState`, or claim continuous measured
positions or a 60 Hz rendering rate.

## Real source coverage

| Race | Raw OpenF1 stint rows | Normalized stint events | Stints visible at pack end |
|---|---:|---:|---:|
| Monza 2025, session 9912 | 39 | 39 | 39 |
| Monaco 2023, session 9094 | 57 | 57 | 57 |
| Brazil 2024, session 9636 | 54 | 52 | 52 |
| **Total** | **150** | **148** | **148** |

Brazil's 2 excluded rows are accounted for in the existing pack manifest: one
has no `lap_start`; one has no matching lap-start event. This is missing-data
coverage, not a zero stint or a synthetic estimate. Monaco's HUL/car-27 source
has lap-1 MEDIUM and lap-1 HARD starts; its selected-driver panel shows both
and the overlap note. Monaco also shows INTERMEDIATE and WET changes at their
source times. The packs' previously audited duration, position and XY coverage
are unchanged.

Source and rights reference: [OpenF1 API documentation](https://openf1.org/docs/)
and the OpenF1 repository's pinned
[CC BY-NC-SA 4.0 license](https://github.com/br-g/openf1/blob/87540e3f495bbd9bedb37b10456dd848c8f193d6/LICENSE).
Historical response hashes and exact field lineage remain in the pack
manifests and `REPLAY_GOLDEN_SESSIONS.md`; raw responses/packs remain ignored
under `data/`.

## Changed paths

- `contracts.py`: schema 3 state and validated `TyreStintState`.
- `reducer.py`: source-time stint append, as-of close and lap-end updates.
- `validate_replay.py`: report state version and stint counts at pack end.
- `apps/web/src/lib/session-context.ts`: frontend stint response shape.
- New `apps/web/src/components/StintPanel.tsx`: source-quality, compound and
  lap-range presentation.
- `apps/web/src/App.tsx` and `App.css`: shared-clock panel plus playback-only
  SVG transform transition with seek/reduced-motion handling.
- `tests/test_session_reducer.py`, `tests/test_replay_api.py`,
  `tests/test_replay_context.py`: source, state-version and as-of assertions.
- `apps/web/e2e/replay.spec.ts`: Monaco overlap/history and Monza motion,
  forward exact-seek and reduced-motion checks.

## Verification

Toolchain: Python 3.12.13, FastAPI 0.142.2, Node 22.23.2, npm 10.9.8,
Playwright 1.64.1 with Chromium 156, Vite 8.3.2.

| Exact command | Result | Evidence |
|---|---|---|
| `.venv/bin/pytest -q` | 51 passed; one existing Starlette/httpx deprecation warning | Synthetic contracts/API/reducer tests |
| `.venv/bin/ruff check src tests scripts` | Passed | Static source checks |
| `.venv/bin/mypy src/f1_racelab/session src/f1_racelab/api.py --follow-imports=silent --ignore-missing-imports` | 13 source files passed | Static type check |
| `cd apps/web && npm run test:unit` | 3 passed | Clock and weather freshness unit cases |
| `cd apps/web && npm run lint` | Passed | ESLint |
| `cd apps/web && npm run build` | Passed; JS 413.23 KB (136.45 KB gzip), CSS 67.09 KB (13.12 KB gzip) | TypeScript/Vite production build |
| `cd apps/web && npm run test:e2e` | 8 passed | Actual three-pack Chromium browser flow |
| `.venv/bin/python -m f1_racelab.session.validate_replay --all` | 15,162 event-boundary/regular cutoffs and 600 shuffled seeks matched an independent reducer; all packs passed | Ignored `data/processed/replay_packs/golden_sessions.qa.json` |
| `.venv/bin/python -m f1_racelab.session.validate_context --all` | 700 weather cutoff comparisons, 14 reviewed track boundaries, zero invalid weather rows; all packs passed | Ignored per-pack `*.context.qa.json` and `golden_context.qa.json` |
| `git diff --check` | Passed before publication | Whitespace and patch hygiene |

Browser screenshots were visually inspected at desktop size. The selected
Monaco HUL screenshot shows all four stints and preserves the two lap-1
records. The Monza screenshot shows estimated car locations on the approximate
trace. No model/strategy graph was generated for this UI/state milestone; these
screenshots are interface artifacts, not sporting-result figures. All images
are ignored test artifacts:

- `data/processed/browser_tests/results/replay-Monaco-stint-histor-accfb-ame-lap-source-rows-visible-chromium/monaco-stints-desktop.png`
- `data/processed/browser_tests/results/replay-real-Monza-seeks-ke-610fd-d-control-on-the-same-state-chromium/monza-desktop.png`

An initial browser assertion sought to Monza's pack end and expected a map car
to remain mounted. At that time the provider has no eligible locations, so
the correct state contains zero cars. The assertion now seeks to the exact
`SESSION STARTED` event with available locations, checks transitions are
disabled, makes a small paused forward seek, and checks again. No production
behavior change was needed for that locator issue.

## Limits and next work

The panel shows source stint history, not tyre wear, grip, degradation or a
strategy recommendation. Lap boundaries do not identify exact pit exit or tyre
fit seconds; missing lap starts stay missing; same-lap rows can overlap. Map
transforms visually bridge sampled positions but can lag or stop at unavailable
location brackets. P2 still needs fuller circuit geometry and measured
rendering/performance coverage. Distance-aligned telemetry, predictive and
strategy models, simulation, live mode, radio, 3D, CI and storage hardening are
not implemented. See `ROADMAP.md` and `CHATGPT_HANDOFF.md` for the whole-product
state.
