# Three historical replay references — 2026-10-16

Milestone **P1-GOLDEN-3 / P2 session selection**, starting at pushed
`7940f2c` on `feat/foundation`. Three local OpenF1 race packs now build
through the same adapter, replay source, API and UI. P1/P2 remain partial:
global track status, weather display, continuous car motion, full geometry,
retirement chronology and telemetry are not yet complete.

Implementation commit: `af2f64677d48d7f9573451de1419fbe3e0b98e08`,
pushed and verified on `origin/feat/foundation`. This follow-up metadata
entry records the verified implementation SHA after publication.

## Real artifacts and reconciliation

| Reference | Monza 2025 | Monaco 2023 | Brazil 2024 |
|---|---:|---:|---:|
| Session key / round | 9912 / 16 | 9094 / 6 | 9636 / 21 |
| Driver identities | 20 | 20 | 20 |
| Sparse events | 1,506 | 2,101 | 1,683 |
| Retained source XY points | 198,300 | 280,028 | 321,094 |
| Checkpoints | 24 | 33 | 27 |
| Duration (s from scheduled origin) | 5,014.715 | 7,030.073 | 8,935.817 |
| Compressed bytes | 1,776,916 | 2,528,574 | 2,427,873 |
| Classified positions matched | 18/18 | 19/19 | 15/15 |
| Available final lap totals matched | 20/20 | 20/20 | 19/19 |
| Result lap totals unavailable | 0 | 0 | 1 (HUL, DSQ) |
| Indexed seek checks | 3,868 | 5,798 | 4,446 |
| Shuffled seeks matching prior state | 200 | 200 | 200 |
| Local p50 / p95 seek time (ms) | 1.078 / 2.309 | 1.233 / 2.816 | 1.057 / 2.438 |

Pack SHA-256 in this run:

- Monza: `d128938a64a99c97b7c8d4faaeaf9e9fb7d0f1c197fe267f57370053f03e0d3b`
- Monaco: `1e93ffaf292094b05d9edc113999e2e58dcedd2d702031addc10e4976b5045f8`
- Brazil: `8b9637da68afd0c499c0bda1691fcc4e57726626135b0c9b25d626c826f00385`

Packs, raw data, build logs, manifests and QA reports remain ignored under
`data/`. Hashes change when rebuilding because ingest and gzip timestamps
change. Each manifest also records hashes of the exact provider responses.
The per-pack QA and combined `golden_sessions.qa.json` are under
`data/processed/replay_packs/`.

The validator now compares all non-sidecar driver fields and event/audit
state with an independent forward pass through the canonical reducer. It
checks immediately before, at and after every discrete event timestamp plus
101 evenly spaced times, then revisits 200 times in seed-42 shuffled order.
It verifies the first measured XY point for every driver with location data.
Brazil has no retained location for ALB (#23); STR (#18) has only 784
pre-race/formational points. An empty location series is preserved as missing.
These tests verify code/source reconciliation for these packs, not universal
correctness of upstream data or a sporting model.

## Contracts and code

| Path / symbol | Input → algorithm → output / caveat |
|---|---|
| `session/catalog.py:ReplaySpec/SESSIONS` | Explicit audited IDs, UTC scheduled origin, round, title/circuit/lap count → immutable source specification and local path |
| `openf1_replay.build_replay_pack` | Spec + cached provider tables → validates session metadata, normalizes source-time events and sidecars, checks final results, writes gzip/manifest |
| `_timed_events` | Source rows + session identity/origin → session-specific event IDs and relative seconds; missing stint start is counted and skipped |
| `_verify_pack_against_results` | Pack + final results reserved for QA → exact driver coverage, classified position and available lap-total checks; missing result totals remain unavailable |
| `contracts.RaceState.capabilities` | Pack capability tuple → available on every canonical state, including requests made without reading the manifest first |
| `api.create_app` | Catalog/local pack paths → `GET /api/v1/replays`, slug-specific manifest and `state?seconds=`; bounded source cache keyed by session |
| `validate_replay.validate/_compare_discrete` | Pack → all-boundary forward comparison, seeded arbitrary-order seek and measured-point reports |
| `apps/web/src/lib/playback-clock.ts:PlaybackClock` | Monotonic wall milliseconds and anchored session seconds → play/pause/seek/rate-adjusted time independent of polling cadence |
| `apps/web/src/App.tsx:ReplayWorkspace/App` | Catalog selection → remounts one session workspace, cancels old fetches, resets time, queries one state per 200 ms during playback |
| `components/ui/slider.tsx` | Scrubber accessible label → forwards label to the actual keyboard-operable thumb/input |
| `apps/web/e2e/replay.spec.ts` | Real local packs + local FastAPI/Vite → four Chromium interaction/synchronization/mobile checks and screenshots |

For clock anchors `(t₀,w₀)`, wall time `w` and playback rate `r`,
playing time is `min(duration, t₀ + max(0,w−w₀)/1000 × r)` in seconds.
Pause/rate changes first commit the current time to the anchor; seek sets
an explicit bounded anchor. React samples this clock at 5 Hz, and the browser
pauses playback when the tab becomes hidden. All data panels use one returned
`RaceState`; the requested transport time and current state can differ by
one in-flight request. Control-message jumps use their exact source seconds,
without rounding down to a polling bucket.

The UI offers 0.25×–16× playback, all prior race-control messages, keyboard
scrub/end jumps, source-time race-start jump, driver focus and a session
picker. Numeric gaps and lapped-gap text are both supported. Estimated
location markers have a distinct outline/opacity. Circuit XY units and
geometry remain explicitly approximate. The compass was labelled XY because
the provider transform does not establish true north. Scheduled lap count is
metadata (Brazil 71), while completed laps come from state (winner 69).

## Source cases and fixes

1. Monaco `pit` returns HTTP 404. Only that optional endpoint may be absent;
   the pack records a null raw-row count, unavailable-resource reason, and
   omits `pit_stops` capability. The UI says **Unavailable** rather than
   displaying a source-derived zero. Stints do not invent missing pit times.
2. Brazil STR's first stint has `lap_start=null`; it cannot be placed on
   a temporal timeline and is counted as skipped.
3. Brazil HUL's disqualified result has `number_of_laps=null`; QA now skips
   that unavailable comparison and reports it explicitly. It does not
   reinterpret null as zero.
4. The first UI browser run found an unnamed scrubber input. Forwarding
   `aria-label` from the group to its thumb/input fixed the accessible
   control and enabled the keyboard seek tests.
5. An initial clock assertion compared floating-point seconds with exact
   decimal equality; it now uses a 1e−9 tolerance. A clock regression test
   also covers seeking backward after the replay has stopped at its end.
6. A user-global Git ignore excluded `package-lock.json`; this repository
   now explicitly includes the web lockfile. `npm ci` succeeded. The shadcn
   CLI is a development dependency. Full npm audit reports seven high
   advisories in its CLI dependency chain; the suggested fix is a major
   downgrade, so no force fix was applied. Production-only audit reports
   zero vulnerabilities.

## Reproduction and demo

Run each pack build sequentially; uncached provider calls are paced/cached.

```bash
uv sync --dev
.venv/bin/python -m f1_racelab.session.openf1_replay --session monza-2025
.venv/bin/python -m f1_racelab.session.openf1_replay --session monaco-2023
.venv/bin/python -m f1_racelab.session.openf1_replay --session brazil-2024
.venv/bin/python -m f1_racelab.session.validate_replay --all
.venv/bin/pytest -q
.venv/bin/ruff check src tests scripts
.venv/bin/mypy src/f1_racelab/session src/f1_racelab/api.py --follow-imports=silent --ignore-missing-imports
cd apps/web
npm ci
npx playwright install chromium
npm run test:unit
npm run test:e2e
npm run lint
npm run build
```

The browser test config starts its own local API (8011) and Vite (5181)
and closes them after tests. It requires all three packs and fails with a
build instruction if any is missing. It does not download provider data.
For manual use start `uvicorn` on 8000 and Vite normally, as in
`RACE_CONTROL_UI.md`; restart the API after rebuilding a cached pack.

Demo: select Monaco; note unavailable pit records; jump to race start; play,
pause and change speed; scrub and select a driver. Select Brazil; seek near
1:48:04 or go to pack end, scroll the control feed and click “SAFETY CAR IN
THIS LAP”; the clock becomes 6,484 seconds, and map/timing/focus/control all
share that state timestamp. Global status still reads unconfirmed because
the adapter preserves messages without claiming a complete track-status
mapping.

**Evidence:** 30 Python tests (synthetic contracts), two JS clock tests,
four Chromium tests using real local packs, Ruff, 11-source-file mypy,
web lint and production build pass. Screenshots were visually inspected:
`data/processed/browser_tests/results/*/monza-desktop.png`,
`*/brazil-desktop.png`, `*/monaco-mobile.png`; the HTML report is under
`data/processed/browser_tests/report/`. Chromium 156 / Playwright 1.64.1
ran on this Arch Linux host using Playwright's Ubuntu fallback build.
Playwright is an Apache-2.0 test dependency; no browser binaries are committed.
The final client build is 406.73 KB JavaScript (134.59 KB gzip) and 63.95 KB
CSS (12.37 KB gzip), with local Geist font assets.

Source data/API: [OpenF1 documentation](https://openf1.org/docs/). The
independent adapter and local-only data follow the source/license notes in
`DECISIONS.md` and `REPLAY_2025_MONZA.md`. Circuit outlines derive from
provider points and branding was created locally; no official broadcast
graphics were copied.
Next: scoped global track-status/weather contracts, smoother timestamped
rendering and fuller P2 panel coverage, then distance-aligned telemetry.
