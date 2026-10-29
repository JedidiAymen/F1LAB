# F1LAB implementation roadmap

Status is tied to evidence, not to code existing in the tree. The locked scope
is in `SOL61_MASTER_EXECUTION.md`; this page tracks execution.

| Gate | State on 2026-10-16 | Proof needed next |
|---|---|---|
| M1: reconcile repository and tools | Complete for this branch checkpoint | Scoped pytest, Ruff, session mypy and uv bootstrap pass; unrelated user files preserved |
| M2: multi-season qualifying data | Complete for 2022–2025 conventional weekends | 71 weekends, 1,418 source rows, provider manifest and overlap audit |
| M3: simple baselines | Complete as a research benchmark | Ridge selected on 2024; 2025 paired interval crosses zero |
| M4: historical-form ablation | Complete as a research ablation | Five models, same eligible rows and common features; form did not win 2024 |
| M5: production ML audit | Partial | FP1/FP2/pre-qualifying phase snapshots, practice-only allowlists and scheduled cutoff audit exist; provider publication times, calibration, driver identity audit and walk-forward 2026 remain |
| P0: domain contracts and repo hardening | Partial | Python event/state contract and reducer tests exist; CI, schema export and ownership remain |
| P1: replay pack | Three-reference offline gate verified; broader contracts partial | Monza/Monaco/Brazil match available final results; 15,162 boundary/arbitrary-time checks and 600 shuffled seeks; context adds 700 as-of checks; 148 source-timed stint histories are reconstructed without changing pack events; full geometry remains |
| P2: 2D Race Control | Partial, real browser interaction proof | Session picker, 0.25×–16× clock, synchronized map/timing/control/weather/status/stints/telemetry cursor, playback transforms and exact source-time jumps; 11 Chromium scenarios pass; versioned driving-line geometry, 12-second selected trail/direction and bounded browser measurements exist; physical geometry and broader rendering evidence remain |
| P3–P4: telemetry and Prediction Lab | Partial, historical phase-aware UI integrated | Three-race six-channel telemetry follows canonical `RaceState`, offline catalog and stronger artifact contracts pass; local qualifying lab serves checksum-verified FP1/FP2/pre-Q snapshots, same-provider 2023 training/2024 validation/2025 holdout and phase feature registries; wider telemetry, publication timestamps and calibration remain |
| P5: strategy simulator and lab | Complete (commit 5c87a8a) | 24 tests pass; deterministic simulator, optimizer, MC, calibration, React 3-tab UI, 4 API endpoints; estimation='simulated' everywhere |
| P6: what-if counterfactual branching | Complete (commit f76d8b6) | 13 tests pass; fork-lap historical/simulated timeline pairs; delta; React WhatIfLab with SVG charts |
| P7: simulated-live WebSocket fan-out | Complete (commit f3098cb) | 7 async tests pass; LiveSession/LiveRegistry, subscriber queue, reconnect delivery, SIMULATED LIVE badge, React hook with backoff; 167 total Python tests |
| P8: Three.js/R3F 3D circuit viewer | Complete (commit fbd4b68) | TypeScript build clean; spline track ribbon, CarDot lerp animation, Top/Orbit cameras, lazy Canvas mount; same CircuitGeometry as 2D |
| M6: walk-forward ML with probabilities | Complete as a research benchmark (2026-10-29) | Pooled 2024–2025 MAE −0.274 [−0.544, −0.042] vs latest practice; Brier beats uniform; intervals conservative; pole-hit not improved. See `ML_WALKFORWARD.md`, plan in `ENHANCEMENT_PLAN.md` |

## Current dependency order

1. Continue P2 with fuller circuit geometry and rendering performance coverage
   while preserving the integrated source-time weather, stint history and
   conservative track-signal state.
2. Expand shared-clock telemetry beyond explicit reference pairs to audited
   driver/lap selection, compatible layouts and sector/corner comparisons;
   continue cross-provider overlap checks for qualifying.
3. Find or retain timestamped practice-result availability before making any
   operational prediction claim. The new phase study uses scheduled practice
   ends and explicitly does not establish provider publication time; details
   and metrics are in `QUALIFYING_PHASES.md`.

The React app now has a three-race offline workstation. The full product
inventory remains required; this is an early integrated slice.


## Current P2 geometry and observation checkpoint (verified and published)

The worktree now contains a versioned, quality-checked driving-line geometry
contract, a selected-driver 12-second trail and estimated movement direction
returned with canonical replay state, and an opt-in browser observation harness.
Three packs were rebuilt from cached OpenF1 source. Offline CLI rebuild, replay/context validators, 360 real trail probes and
11 browser scenarios now pass. Final full Python/static/build checks also pass.
P1/P2 remain partial: physical circuit dimensions, pit-lane geometry, official
timing-line location and broader rendering evidence are still required.

Next: expand telemetry coverage and evaluate a licensed source of physical circuit geometry.
See `REPLAY_GEOMETRY_AND_PERFORMANCE.md` for this checkpoint's evidence.


## P3 multi-session, multi-channel telemetry milestone (verified and published)

Expand the existing distance-aligned comparison to an explicit three-race
catalog, offline reproducible build, and six source-labelled channels with a
persistent cumulative delta. Preserve the canonical replay cursor and hide it
outside the shared sampled interval. Contract validation now checks comparison
mathematics and complete grid coverage; all three real artifacts and integrated
checks pass. This advances P3 without completing arbitrary lap/driver,
cross-year or track-layout comparisons, sector/corner bands or ghost laps.


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


## P3 lap library and driver/lap selection (partial P3 advance)

A per-session offline lap library now indexes each driver's available cached
laps. Content-addressed gzip files hold validated `LapTelemetry` instances;
a manifest published only after all referenced files exist records source hashes,
pit-check status and rejected-lap reasons. The UI exposes a `TelemetrySelection`
control above the chart so the user can pick any available driver/lap pair and
apply it without touching the replay clock. The API's `/telemetry/laps` catalog
route returns the manifest; the existing `/telemetry/lap-comparison` route now
accepts `driver_a/lap_a/driver_b/lap_b` query params for library-backed
comparisons. This advances arbitrary lap selection; cross-year, sector and wider
driver coverage remain incomplete.


## P5–P8 milestone summary (2026-10-17)

All four milestones are implemented and pushed to `origin/feat/foundation`.

### P5 Strategy Simulator — commit 5c87a8a
Deterministic lap simulator with tyre/fuel/pit physics; traffic heuristic;
optimizer (0/1/2-stop enumeration + ranking); Monte Carlo with shared worlds;
OLS calibration from real pack data. All output labelled `estimation='simulated'`.
4 FastAPI endpoints. React 3-tab Strategy Lab. 24 tests; 147 total.

### P6 What-If Branching — commit f76d8b6
Fork replay at lap N; historical prefix from measured pack; separate simulated
suffixes per strategy; cumulative time re-rooted at fork. React WhatIfLab with
SVG bar + gap charts and simulation limits disclosure. 13 tests.

### P7 Live WebSocket Fan-Out — commit f3098cb
`LiveSession` asyncio 0.5s tick; SIMULATED LIVE badge mandatory; subscriber
queue fan-out; last snapshot on reconnect; `LiveRegistry` singleton; exponential
backoff React hook. 7 async tests; 167 total Python tests.

### P8 Three.js 3D Circuit Viewer — commit fbd4b68
CatmullRomCurve3 spline from centerline_xy; TubeGeometry track ribbon;
projectOnSpline nearest-point; CarDot sphere + lerp animation; Top/Orbit
cameras; lazy Canvas mount. Same CircuitGeometry source as 2D map.

### What remains
- Walk-forward 2026 evaluation, calibration, provider publication timestamps (M5)
- Broader physical geometry and rendering performance (P2 gate)
- Camera follow-mode for 3D; E2E browser tests for P5–P8
- Real-time OpenF1 live adapter credentials (P7 gate)
- CI, schema export, storage hardening (P0 gate)

**Update 2026-10-29:** M6 evidence extended to 2026 — ensemble does not beat latest practice
under the new regulations (+0.052 [−0.030, +0.136], 12 events); pooled 48-event gain −0.192
[−0.404, −0.015]. Added: one-command ingestion pipeline with quality gate, race-history
chart, 2026 data (12 weekends). See `ENHANCEMENT_PLAN.md`.
