# Replay geometry, focused trails and browser observations

Starting source SHA: `1a5b7b4fa64ae3ceab0ab7cb6957c2331a5ce7b6`, branch
`feat/foundation`, 2026-10-16. This milestone advances P2; physical circuit
survey accuracy, pit-lane geometry and production performance budgets remain
unproven.

## Display geometry

Previously every pack used VER lap 3 without checking whether the trace closed
or contained large sample gaps. `session.geometry.build_circuit_geometry`
now evaluates completed measured laps across the available drivers, rejects
unusable candidates and deterministically selects one driving line. It retains
the source XY coordinates and every selected measured point. It adds the first
point at the end only when a short closing segment passes the configured
coverage checks; the extra segment is explicitly inferred.

`CircuitGeometry` version 1 carries its layout/source identity, source lap and
sample hashes, coordinate system/unit, bounds, normalized points, cumulative
polyline distance, tangent directions, inferred closure and candidate
diagnostics. The containing replay pack stays schema 2 and canonical
`RaceState` stays schema 3. Physical lap length and width, surveyed edges, pit
lane, corners and sectors remain null/empty. The marker called `start_line` in
the geometry schema is the estimated first retained point of the timed source
lap; the UI calls it the trace origin, not an official timing line.

The geometry is an approximation of the track using one measured driving
line. It is not a measured track centerline or boundary survey. Closing a trace
more tightly does not establish better positional accuracy over the circuit.
Car coordinates are projected with the same affine display transform; they are
not snapped onto the line or forced around it at uniform speed.

For points `p_i=(x_i,y_i)` in unknown provider units:

- Polyline arc length is `s_i = s_(i-1) + hypot(x_i-x_(i-1), y_i-y_(i-1))`.
- Tangent direction is `atan2(y_(i+1)-y_i, x_(i+1)-x_i)` in radians.
- Normalized XY is `(XY - bounding_box_center) / max(span_x, span_y)`;
  it preserves aspect ratio and does not convert into metres.
- Closure ratio is `distance(last_measured, first_measured) / observed_arc`.

Candidates require at least 100 retained measured points, maximum sample gap
2 seconds, start/end coverage gaps no larger than 1.5 seconds, closure ratio
at most 2%, and largest segment at most 4% of observed arc. Known pit-in laps
and explicit pit-out laps are excluded. Missing pit data remains a limitation.
Selection orders by closure ratio, sample gap, boundary gaps, driver number
and lap number; raw row order does not change the result.

The cached-data audit selected:

| Session | Driver/lap | Measured points + closure | Old VER L3 closure gap | New closure gap | New closure ratio |
|---|---|---:|---:|---:|---:|
| Monza 2025 | #30 L7 | 168 + 1 | 406.51 units | 8.06 units | 0.0140% |
| Monaco 2023 | #16 L54 | 191 + 1 | 131.24 units | 2 units | 0.00612% |
| Brazil 2024 | #31 L52 | 166 + 1 | 349.74 units | 1 unit | 0.00237% |

Accepted/candidate lap counts are 911/976, 1322/1516 and 1017/1137. Maximum
selected source sample gaps are 1.160 / 1.161 / 0.840 seconds. Full geometry
and rejection diagnostics are in ignored
`data/processed/replay_packs/geometry_audit.json`; pack manifests contain the
selected geometry and its deterministic SHA-based identity.

## Focused source trail and displacement direction

The existing local state request optionally accepts `focus_driver`. The same
response includes `location_context` for that driver at the exact canonical
`session_time_seconds`; selecting a driver changes the view projection, not
the replay clock. The ordinary state response remains usable without a focus.

The context contains the previous 12 seconds of retained locations, split at
source gaps or implausible coordinate jumps. It never retains a sample after
the requested time. When available, the canonical interpolated current point
can be appended with estimated quality; its connector is dashed. Recent
displacement gives an estimated direction in provider XY, not measured chassis
orientation. Missing, stationary or disconnected current positions have no
direction arrow. The screen flips Y, so the rendered angle negates provider
`atan2` degrees.

Trail segments split across gaps over 1.5 seconds or movement over 2,500
unknown provider units/second. These are existing replay display heuristics,
not a claim about physical speed. Measured historical vertices are at or before
the canonical time; the current estimated endpoint can reuse the following
source bracket already used by offline ReplaySource interpolation. This is
historical replay display, not provider publication-as-of evidence.

The browser does not accumulate trail points while playing. A seek reconstructs
the trail from source history, so reversing and revisiting the same time is
deterministic. Stale selected-driver context is hidden while a new focused
request is loading. Existing source-location interpolation/staleness rules
still determine which cars are shown.

`TrackMap.tsx` separates static circuit nodes from current car/trail nodes. Its
projection/path is memoized per geometry object and the static SVG subtree is
memoized, avoiding path construction on each 5 Hz state update. Existing
180 ms car-transform playback transitions remain; paused exact seeks, reverse
seeks and reduced motion are immediate.

## Browser measurement protocol

`cd apps/web && npm run benchmark:replay` is opt-in and separate from normal
browser tests. It starts the local API/Vite servers on ports 8012/5182, uses
headless Chromium at 1440×1000 and 1× playback, samples four visible seconds per
real session and performs race-start/forward/back/end seeks. It records raw
RAF intervals, canonical panel-clock agreement, Long Tasks API entries, local
state-request latency/decoded bytes, seek-to-DOM latency and Chromium JS heap
snapshots without forced GC.

RAF callback cadence is browser scheduling evidence, not painted frames or GPU
FPS. Local request latency includes proxy, server and browser delivery. Heap
samples exclude native/GPU/Python memory. One short run on a shared host cannot
establish a statistical regression, universal frame budget or production
capacity. The final run adds geometry/trail features, so before/after changes
cannot be attributed solely to memoization.

Baseline artifact:
`data/processed/browser_benchmarks/replay-performance-2026-10-16T16-32-00-868Z.json`.

| Baseline session | RAF callbacks/s | RAF interval p95 | Local state request p95 | Long-task entries |
|---|---:|---:|---:|---:|
| Monza | 56.51 | 33.3 ms | 9.02 ms | 0 |
| Monaco | 59.97 | 16.8 ms | 6.75 ms | 0 |
| Brazil | 55.16 | 33.3 ms | 16.04 ms | 3 |

All sampled panel clocks agreed; twelve seek observations ranged from
50.03–163.84 ms. Baseline report source/config fingerprints and environment
are stored with the raw observations. Final post-change report and verification
are recorded below after the integrated run.

## Reproduction and source

```bash
uv run python -m f1_racelab.session.openf1_replay --all --offline
.venv/bin/python -m f1_racelab.session.validate_replay --all
.venv/bin/python -m f1_racelab.session.validate_context --all
.venv/bin/pytest -q
.venv/bin/ruff check src/f1_racelab tests
cd apps/web
npm run test:unit
npm run build
npm run lint
npm run test:e2e
npm run benchmark:replay
```

The source build requires existing ignored cached data. `--offline` refuses
uncached resources before HTTP; optional absence is reused only from explicit
same-session HTTP 404 evidence in a prior manifest (legacy manifests additionally
require a matching pack hash). No missing file is treated as proof of absence. Raw API records and generated packs/reports stay
ignored. Data-source details and rights are in `DATA_CONTRACTS.md`,
[OpenF1 documentation](https://openf1.org/docs/) and the
[pinned OpenF1 license](https://github.com/br-g/openf1/blob/87540e3f495bbd9bedb37b10456dd848c8f193d6/LICENSE).

## Final integrated evidence

`uv run pytest -q`: **92 passed** in 6.87 s, one upstream Starlette/httpx
compatibility deprecation warning. Ruff over `src/f1_racelab tests` passed;
`uv run mypy src/f1_racelab/session src/f1_racelab/api.py
src/f1_racelab/data/openf1_qualifying.py --ignore-missing-imports` passed across
16 source files. Frontend unit tests: **8 passed**; build and ESLint passed.
`npm run test:e2e`: **11 passed** in 33.0 s, including exact trail reconstruction
on forward/back seeks and same-clock driver selection. Production JS is
434.63 kB (142.33 kB gzip), CSS 78.65 kB (15.55 kB gzip).

The durable offline CLI rebuilt all three packs. Final replay validation passed
4,120 / 6,149 / 4,893 cases plus 200 arbitrary seeks per session. Local backend
seek p50/p95 milliseconds were 1.356/3.360, 1.444/3.617 and 1.319/2.962.
Context validation and 360 real cached location-context checks passed. Logs:
`geometry_offline_build.log`, `geometry_offline_validation.log`,
`geometry_context_validation.log`, `geometry_location_context.qa.json` under
`data/processed/replay_packs/`.

Final idle browser artifact:
`data/processed/browser_benchmarks/replay-performance-2026-10-16T16-46-32-467Z.json`,
SHA256 `2c16efc9ec43e43ed6dcd1b461afa7c1bee527ee09928cd2db89eac218764477`.

| Final session | RAF callbacks/s | RAF interval p95 | State request p95 | Long tasks | Decoded JSON bytes |
|---|---:|---:|---:|---:|---:|
| Monza | 59.08 | 16.7 ms | 11.49 ms | 0 | 600,414 |
| Monaco | 59.54 | 16.8 ms | 8.89 ms | 0 | 604,229 |
| Brazil | 60.00 | 16.7 ms | 7.05 ms | 0 | 595,738 |

All eight panels agreed with the canonical clock; twelve seeks took
47.30–171.34 ms; no hidden samples or page exceptions. JS heap after sampling
was 30,965,440 / 47,984,100 / 45,121,188 bytes without forced GC. The test took
18.5 s (21.4 s including servers). An earlier successful report at
`replay-performance-2026-10-16T16-45-47-483Z.json` overlapped backend validation;
it is retained as a concurrent-workload observation, separate from this idle
run. Initial harness failures involved explicit-role selector assumptions and
delayed reset-response matching; both were corrected before sampling.

Generated packs/reports remain ignored local artifacts. Their exact source,
manifest, environment and geometry fingerprints are in the report. Final pack
SHA256 values in Monza/Monaco/Brazil order:

- `63b3435d4e201e9d659e5964fa32d436abdb24b05632f4cc4ba173087bf0db54`
- `df1f6b79a03ffc3cead46ddff839f60b3bf785e965e8f024622beba8effdffc0`
- `ada89571c6326a4f8a941c10e6343974e757f372aca786410f43873bca01462c`

P2 remains partial: physical circuit dimensions, pit-lane geometry, wider
telemetry coverage and production performance budgets need further evidence.
Publication SHA and push proof are recorded in the handoff/worklog checkpoint.

Implementation `132e3aaff34f4c805485e54bbef24f39025aab03` was pushed normally to
`origin/feat/foundation`; the remote branch returned the identical SHA.
