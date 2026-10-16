# Three-session telemetry coverage and channel semantics

**Status: P3 partial, verified source milestone; source commit and remote push are recorded in the handoff after publication.** This increment expands the existing Monza comparison to the three supported historical replay sessions. It does not complete arbitrary lap or driver selection, sector mapping, cross-layout alignment, ghost laps, or calibrated braking analysis.

## Data and selected laps

All comparisons use cached OpenF1 v1 `laps` and per-driver `car_data` responses for a single shared session. The builder makes no upstream request in `--offline` mode. It uses an explicit `ComparisonSpec` from `src/f1_racelab/telemetry/artifacts.py`; a stable catalogue selection is reproducible but does not certify equal running conditions.

| Session | Driver A lap | Driver B lap | A / B duration (s) | Source rows in lap A / B | Max sample gap A / B (s) | Common integrated distance (m) | 5 m grid rows | Delta B−A at last grid row (s) | Pit source |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| Monza 2025 | #1 L50 | #4 L50 | 81.297 / 81.123 | 318 / 309 | 0.799 / 0.799 | 5,746.062 | 1,150 | −0.234 | Cached provider pit rows checked |
| Monaco 2023 | #1 L40 | #31 L40 | 77.161 / 77.025 | 291 / 294 | 0.640 / 0.520 | 3,279.036 | 656 | −0.184 | Unavailable locally; pit-in status unverified |
| Brazil 2024 | #1 L52 | #31 L52 | 82.380 / 82.569 | 307 / 312 | 0.560 / 0.560 | 4,241.193 | 849 | Cached provider pit rows checked |

Both lap records have `is_pit_out_lap=false`; that source flag is not a general clean-lap classifier. Monza and Brazil also had cached pit records checked. Monaco's pit source is unavailable, so pit-in status cannot be established. Tyres, fuel, traffic, yellow flags and changing weather are not controlled by this comparison. Laps remain examples selected for a stable regression fixture; the reported delta is descriptive and is not a driver-performance claim.

The response source SHA-256 values are embedded in each artifact and were checked against the raw cache. Each artifact has 3 source resources for Monaco and 4 for Monza/Brazil (the extra resource is cached pit coverage). The full hashes are preserved in the JSON; `catalog_build.log` records the reproducible offline build.

| Session | Artifact SHA-256 | JSON size | Chart path | Chart SHA-256 |
|---|---|---:|---|---|
| Monza | `9bc3aa5ea7750541deff8d10a4f84f8f228e0c5e372f85692e1923821d8dfea6` | 847,715 B | `data/processed/telemetry_comparisons/monza-2025_driver_1_lap_50_vs_4_lap_50.png` | `7e7a7f5d6b19a2244a1b63d2cc993fc3227e2742a924202861fa2b7faeb50582` |
| Monaco | `5ac531b5e3ada9e3c90a3e0e86e27c169283163ab5328904d2b71d47f558b0d5` | 547,035 B | `data/processed/telemetry_comparisons/monaco-2023_driver_1_lap_40_vs_31_lap_40.png` | `52b60afd29db68c5d2d8803772f9885e7122ba9b512743f3a4594a5c7ac673b4` |
| Brazil | `774191e671021aac0519452d771f9395d68e5ae1a6f4b929ec03b8f0a2c33998` | 669,987 B | `data/processed/telemetry_comparisons/brazil-2024_driver_1_lap_52_vs_31_lap_52.png` | `1926d1cbccab6f529b0f7c553cd9fe89fac16a49abe87f6b5b5fefee545e9216` |

The charts were opened and visually reviewed. They show the speed traces and cumulative B−A time over the estimated shared distance. The compared speed lines are similar in some sections and differ in others; neither chart resolves the cause. DRS is constant within each selected lap (codes 0 in Monza/Monaco and 1 in Brazil), so a flat trace there is faithful source data, not missing coverage. The build QA JSON reports non-null counts separately for every channel and lap.

## Algorithm and units

`src/f1_racelab/telemetry/distance_alignment.py:build_lap_telemetry` checks session, meeting, driver identity, timezone, non-pit-out status, timestamp order and gaps no greater than 1 second. It brackets each approximate OpenF1 lap start/end and interpolates the boundary only when source samples bracket it within the limit. For successive speeds in km/h, it integrates estimated metres with the trapezoid:

`distance += ((speed_previous + speed_current) / 2 / 3.6) * elapsed_seconds`

`compare_laps` uses the shorter of the two integrated distances and a 5 m grid. It does not extrapolate beyond either lap. At each grid distance, delta is `elapsed_B_seconds - elapsed_A_seconds`; positive means B took longer to reach that estimated point. The final common endpoint may fall between grid points, so the last emitted sample is the largest multiple of 5 m within it.

Six channel definitions live in `apps/web/src/lib/telemetry-comparison.ts`:

- Speed in km/h, throttle in the provider's reported percent field, and RPM use linear interpolation when both bounding values are present.
- Brake remains the provider's raw source value; gear and DRS remain integer source values/codes. These discrete values hold the preceding sample between grid points. The labels do not claim brake pressure or assign a universal DRS open/closed meaning.
- A missing source value remains null. It is not replaced with zero, does not interpolate across a gap, and breaks the corresponding plotted path. Throttle is not clamped at 100.

Pydantic contracts in `contracts.py` validate serialized source laps and comparisons before the API exposes them: zero distance/time origin, point counts and maximum gap, correct session identity, distinct laps, full uniform grid, increasing elapsed values inside each lap, shared endpoint and delta arithmetic. `gear` and `drs` source values must be integral; fractional values are rejected instead of truncated.

Lap start timestamps are provider estimates. The UI's telemetry cursor translates the canonical replay time by reference lap A's UTC start relative to the replay origin, then interpolates only across the actual grid sample range. It disappears outside that range, including any tail of lap A that extends beyond the shorter shared distance. Changing the channel never creates a separate clock. `TelemetryPanel.tsx` memoizes channel paths by artifact and channel, keeps delta visible, and shows both drivers' channel values at the canonical cursor.

## API and reproduction

`GET /api/v1/replay/{slug}/manifest` reports the configured pair's actual ID and label and whether its local artifact exists. `GET /api/v1/replay/{slug}/telemetry/lap-comparison` validates that the file belongs to the requested session and catalog pair, then returns lap quality and every aligned channel while omitting the much larger raw per-lap point arrays. The read-only API does not download data.

From the repository root, with the cached OpenF1 response files:

```bash
uv run python -m f1_racelab.telemetry.openf1_lap_comparison --all --offline
uv run pytest -q tests/test_distance_alignment.py tests/test_replay_api.py
uv run pytest -q
uv run ruff check src/f1_racelab tests
uv run mypy src/f1_racelab/telemetry src/f1_racelab/session src/f1_racelab/api.py --ignore-missing-imports
cd apps/web
npm run test:unit
npm run build
npm run lint
npm run test:e2e
```

The offline CLI log and each JSON, QA report and PNG are under ignored `data/processed/telemetry_comparisons/`. `tests/test_distance_alignment.py` contains synthetic arithmetic, identity, boundary, gap, grid, channel and malformed-contract cases. `tests/test_replay_api.py` includes per-session synthetic API responses and wrong-catalog-pair rejection. Browser checks use the three real artifacts and verify each catalog label, selected channel path, source-valued discrete readouts, canonical-clock synchronization and stable values after reverse/forward seeks; one case also inspects mobile overflow.

Source documentation: [OpenF1 API docs](https://openf1.org/docs/). Upstream source and its terms are recorded in [the pinned OpenF1 license](https://github.com/br-g/openf1/blob/87540e3f495bbd9bedb37b10456dd848c8f193d6/LICENSE). This work does not copy provider implementation code. Raw responses and derived artifacts remain local in ignored data directories.

## Known limits and next work

This is distance integration from rounded sampled speed, not provider distance, GPS lap trace, surveyed circuit length or guaranteed matching physical track points. Approximate lap start alignment, asynchronous sampling and unknown race conditions limit delta interpretation. Monaco pit coverage is absent. DRS is constant in each fixed reference lap, even though the channel path and cursor are implemented. The reference pairs are explicit fixtures: the UI cannot yet select arbitrary drivers/laps. Sectors/corners, shared map-to-telemetry location, across-year/layout normalization, ghost laps and uncertainty ranges remain unimplemented. P3 therefore remains partial.

Visual review artifacts include the generated PNGs above and the Playwright
screenshots under `data/processed/browser_tests/results/`, particularly the
three `*-telemetry-channels.png` captures and `monaco-telemetry-mobile.png`.
These and the source/build QA reports are ignored local artifacts and are
regenerated by the documented commands.


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
