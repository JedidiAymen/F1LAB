# Race Control UI — first local 2D replay, 2026-10-16

**Later checkpoints:** `REPLAY_GOLDEN_SESSIONS.md` supersedes the one-race
status below, and `REPLAY_CONTEXT.md` documents schema 2 weather and scoped
track status. The current emitted state is schema 3 and includes source-time
stints; stored packs/events are schema 2. Three packs, session selection and
eight real Chromium interaction tests now work; desktop/mobile screenshots
were inspected. Weather, global status and stints follow the same canonical
session clock. P2 remains partial.

**Status:** one real 2025 Monza offline demo implemented; broader P2 gate is
partial. Starting source commit: `abe031c` on `feat/foundation`. Find this
milestone's commit and remote state with `git log -1 --oneline` and
`git ls-remote origin refs/heads/feat/foundation`.

## Run

```bash
uv sync --dev
.venv/bin/python -m f1_racelab.session.openf1_replay
.venv/bin/uvicorn f1_racelab.api:app --host 127.0.0.1 --port 8000
cd apps/web
npm ci
npm run dev -- --host 127.0.0.1
```

Open the Vite URL printed by the last command. The backend pack path defaults
to `data/processed/replay_packs/monza_2025_race.json.gz`; set
`F1LAB_REPLAY_PACK` to choose a different local file. The frontend dev proxy
sends `/api` to port 8000. The API returns HTTP 503 with a build instruction
when the pack is absent or invalid, and HTTP 422 for an out-of-range seek.

## Contracts and implementation

| Path / function | Input → computation → output |
|---|---|
| `src/f1_racelab/api.py:create_app` | Local gzip pack → cached `ReplaySource` → manifest and `RaceState(t)` JSON |
| `session/replay_source.py:state_at` | Seconds since scheduled race clock origin → checkpoint replay plus indexed location/interval sidecars → canonical state |
| `apps/web/src/App.tsx:App` | One browser playback time in seconds → at most five state requests per second; timing, driver focus, map and race-control list use the same returned state |
| `apps/web/src/App.tsx:TrackMap` | Provider-derived XY trace and current state → SVG circuit and visible car points; playback-only 180 ms CSS transforms bridge forward samples at most 4 seconds apart |
| `apps/web/src/components/StintPanel.tsx:StintPanel` | Selected driver + current schema 3 state → source-labelled compound and inclusive lap-range lanes, including overlap notes |
| `apps/web/src/App.css` | Dense responsive pit-wall layout, focus states and reduced-motion support |

The manifest includes 20 driver identities, approximate geometry, 53
post-clock control messages, 5,014.715-second duration and source metadata.
The state endpoint leaves reducer audit IDs/hashes out of transport but keeps
the race fields, observation times and quality markers. The top-level UI
clock drives all requests. Map and timing both read the same `RaceState`;
the message list only reveals messages up to that state's time. The SVG
projects provider XY using a uniform scale and labels unknown coordinate
units. The browser does not create telemetry, add future results, or infer a
global flag from sector messages. If a location bracket is missing, it hides
the car. Provider coordinates unchanged for 15 seconds are now hidden to
avoid showing a stopped car as active indefinitely; that is a visual
staleness rule, not a retirement classification.

## Evidence and caveats

- **Synthetic:** `tests/test_replay_api.py` checks missing pack, manifest,
  mid-bracket estimated state, invalid seek and frozen points. Full
  `.venv/bin/pytest -q`: 27 passed, one upstream Starlette/httpx
  deprecation warning.
- **Real historical:** `curl` returned HTTP 200 and 35,246 bytes for the
  Monza manifest. `state?seconds=1200` returned 20 drivers, 20 located cars
  and maximum completed lap 11. The replay validator matched 131/131
  discrete-state seeks after the stationary guard; p50/p95 seek time was
  0.975/2.066 ms in this run. Pack hash
  `c993cc67937cb4dcc82d7bd604214c7059e31d72c5d76830f365c90ca1074fa8`.
- **Static/build:** Ruff passed; session and API mypy passed after annotating
  the stationary index; web ESLint and TypeScript/Vite build passed. The
  generated shadcn component folder has a narrow Fast Refresh lint exception
  because it exports variant constants by design.
- **Skipped:** browser visual/interaction inspection; the enabled computer
  browser surfaces reported unavailable. No visual FPS or accessible
  interaction claim is made from the build alone.

The 2D map is an approximate OpenF1 coordinate trace, not surveyed geometry.
Repeated coordinate detection may hide a legitimately stationary car after
15 seconds; the current pack has no authoritative retirement timestamp.
Position is latest provider observation; gap expires after 10 seconds.
The full live feed, 3D, telemetry, strategy, simulation and additional
historical sessions remain future work. The raw pack is ignored by Git.
Provider source and rights: [OpenF1 API](https://openf1.org/docs/) and the
local source/licensing notes in `REPLAY_2025_MONZA.md`.

## Current follow-up — schema 3 stint state and display interpolation

The earlier metrics above document the first Monza UI checkpoint. Current
full-suite results, three-pack state and context validation, source stint
counts, exact state/transition behavior and desktop screenshots are in
`REPLAY_STINTS_AND_MOTION.md`, `REPLAY_GOLDEN_SESSIONS.md` and
`TEST_EVIDENCE.md`. The map transitions are cosmetic only. They are active
only while the canonical clock is playing; paused seeks (including small
forward seeks), reverse seeks, first appearance, large state gaps and reduced
motion do not animate. The server and shared panel clock remain sampled at
5 Hz. Surveyed geometry and quantified rendering performance are still open.
