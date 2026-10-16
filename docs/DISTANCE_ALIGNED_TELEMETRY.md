# Distance-aligned telemetry foundation

This document records the first reproducible telemetry comparison. It is a
backend/data milestone only: the result is not yet served by the replay API or
shown in the Race Control UI, and it does not claim a precise surveyed track
distance.

## Source and coverage

- Provider: OpenF1 historical API v1, session `9912` (Monza 2025), meeting
  `1268`; public endpoint documentation is at
  [openf1.org/docs](https://openf1.org/docs/) and access notes at
  [openf1.org/auth](https://openf1.org/auth.html).
- License reference: the upstream OpenF1 repository is published under
  [CC BY-NC-SA 4.0](https://github.com/br-g/openf1/blob/87540e3f495bbd9bedb37b10456dd848c8f193d6/LICENSE).
  This implementation does not copy upstream code. Raw responses and derived
  data artifacts remain in ignored local `data/` paths.
- Inputs: `laps?session_key=9912` and `car_data` for drivers 1 and 4. Each
  complete driver response has 29,611 rows. The compared lap rows are VER #1
  lap 50 (81.297 s) and NOR #4 lap 50 (81.123 s), both marked non-pit-out.
- Exact source endpoints: [laps](https://api.openf1.org/v1/laps?session_key=9912),
  [car_data for #1](https://api.openf1.org/v1/car_data?session_key=9912&driver_number=1)
  and [car_data for #4](https://api.openf1.org/v1/car_data?session_key=9912&driver_number=4).
- Source SHA-256: laps
  `89cee73604aaf44129b1a80cb10205f55eb16937dff0ba804ca38326532bbbae`;
  driver 1 car data
  `6ff42419ce5d39a0ca77d8fca0836676328f1456bf187028e94771acf621d36e`;
  driver 4 car data
  `9ed72c1fbbce6a4e462dcf1cb6d93e75813896aa1b5bfc8598df60de82ac1a40`.
- The source stream's median interval is 0.24 s and p99 is 0.519 s. The
  largest retained interval in either lap is 0.799 s. OpenF1 lap start times
  and location timing are approximate; all distances and aligned outputs are
  labelled `estimated`.

## Contracts and algorithm

`src/f1_racelab/telemetry/contracts.py` defines immutable Pydantic contracts
for source lap points, lap-level provenance and shared-distance comparison
points. `distance_alignment.py:build_lap_telemetry` validates session, meeting,
driver, timezone and pit-out status; selects the approximate lap window;
interpolates only its start/end when bracketed by samples no more than one
second apart; and preserves source throttle, brake, gear and DRS values.

For successive source speeds `v_i` and `v_(i+1)` in km/h separated by
`Δt` seconds, distance increases by the trapezoidal integral
`Δd = ((v_i + v_(i+1)) / 2) × Δt / 3.6` metres. A gap above the configured
limit is rejected rather than bridged. Boundary interpolation is linear for
speed, throttle and RPM; brake, gear and DRS are held at the preceding source
state. This is a calculated distance axis from sampled speed, not provider
distance or surveyed geometry.

`compare_laps` requires a common session and meeting, uses the shared distance
range, and creates a regular 5 m grid. Continuous channels and elapsed time
are linearly interpolated by distance; discrete channels use the previous
sample. Delta is `elapsed_B - elapsed_A` seconds, so a negative value means B
reached that estimated distance earlier. The common endpoint is floored to
the last whole grid spacing.

Throttle is stored in the source's reported percent field without clipping;
brake is named `brake_source_value` because it should not be silently
reinterpreted as a normalized percentage. DRS remains an integer source code,
including codes whose meaning is unknown. Session cache observations with
values above 100 remain unmodified; the synthetic unit test also asserts that
104 stays 104 through the builder.

## Real comparison result

| Driver/lap | Source samples in lap | Bounded points | Estimated distance |
|---|---:|---:|---:|
| VER #1, lap 50 | 318 | 320 | 5,746.062 m |
| NOR #4, lap 50 | 309 | 311 | 5,751.324 m |

Each lap has two interpolated boundaries. The shared grid ends at 5,746.062 m
and contains 1,150 points from 0 through 5,745 m. Across that grid, B−A
elapsed-time delta ranges from −0.374 s to +0.212 s and ends at −0.234 s.
These numbers describe this sampled comparison only; lap-start approximation,
speed rounding, source sampling and separate distance integration limit
precision.

The local ignored artifacts are
`data/processed/telemetry_comparisons/monza-2025_driver_1_lap_50_vs_4_lap_50.json`
and the adjacent `.png`. The rebuilt JSON SHA-256 is
`8e4ddc3217641f3543c37aba440574156512f4bd89e5c66a7dd6168b88543277`; the
chart SHA-256 is
`7e7a7f5d6b19a2244a1b63d2cc993fc3227e2742a924202861fa2b7faeb50582`.
The chart was visually inspected. These generated artifacts are intentionally
not committed; cached source hashes and the CLI reproduce them.

## Reproduction and verification

From the repository root, with the already-cached historical responses:

```bash
.venv/bin/python -m f1_racelab.telemetry.openf1_lap_comparison
.venv/bin/pytest -q tests/test_distance_alignment.py
.venv/bin/pytest -q
.venv/bin/ruff check src tests scripts
.venv/bin/mypy src/f1_racelab/telemetry src/f1_racelab/session src/f1_racelab/api.py --follow-imports=silent --ignore-missing-imports
```

The comparison CLI uses the existing rate-limited, hash-recording
`OpenF1Client`; it needed no new network request because all three response
files were cached. Five synthetic telemetry tests pass, including exact
integration, boundary interpolation, excessive-gap rejection, identity/pit-out
checks, discrete values and shared-session/spacing validation. Full suite:
56 passed with one existing Starlette/httpx deprecation warning. Repository
Ruff passes and mypy reports 17 checked Python files without issues. The real
comparison has two driver streams and one session; it is not a population
study or performance claim.

Tool versions for this run: Python 3.12.13, Pydantic 2.13.5, Matplotlib
3.11.2, pytest 9.1.1, Ruff 0.16.10 and mypy 2.4.0.

## Failures, limitations and next work

The source contained channel observations of 104 elsewhere in each full
session. An initial upper-bound assumption rejected them; it was removed and
raw values are retained. An initial plot used low-contrast dark text; chart
labels and axes were restyled and visually checked. Ruff import ordering and
mypy narrow typing diagnostics were corrected before the final checks.

The selected lap windows themselves have throttle/brake values from 0 to 100;
the 104 observations are elsewhere in the source response, while the fixture
checks preservation. There is no GPS/distance alignment, sector segmentation,
pit-lap classification beyond the explicit pit-out flag, uncertainty band,
frontend graph/crosshair, canonical replay-clock binding, prediction model,
strategy inference or live data. The next integration should derive its graph
cursor from the existing canonical replay time rather than introducing a
second independent clock. Broader lap eligibility checks and more events are
also needed.
