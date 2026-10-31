# Implementation atlas — qualifying checkpoint

This atlas describes the current call chain and what each important source
symbol does. One local 2D replay exists; later live/strategy modules do not.

## End-to-end call chain

1. `f1_racelab.data.qualifying_dataset` enumerates 2022 conventional weekends;
   `features.qualifying.build_weekend_dataset` loads FP1, FP2, FP3 and Q through
   `data.fastf1_source`, computes per-driver practice features and post-Q labels,
   and writes one Parquet per event.
2. `f1_racelab.data.openf1_qualifying` reads 2023–2025 OpenF1 meetings and
   sessions, fetches five small result/identity resources per event, maps them
   to the same row schema, and writes JSON source cache and per-event Parquet.
3. `f1_racelab.data.mixed_qualifying` adds provider metadata to cached 2022
   frames, concatenates OpenF1 frames, validates driver-weekend uniqueness and
   writes a local dataset plus SHA-256 manifest.
4. `models.qualifying_backtest` prepares legal practice features, groups by
   event, fits Ridge and LightGBM on 2022–2023, selects on 2024, and evaluates
   2025. `models.qualifying_ablation` adds lagged form and repeats the same
   split with two extra models.

## Provider and feature modules

| File and symbol | Input → algorithm → output | Example and proof | Caveat |
|---|---|---|---|
| `data/fastf1_source.py:load_session` | `(year, round/name, FP1/FP2/FP3/Q)` → FastF1 cached load, telemetry/weather/messages disabled for this tabular path → `Session` with laps/results | 2022 R20/R22 built from cached timing; per-event Parquet in `data/processed/qualifying_weekends/` | F1 archive returned 401 for uncached 2023; this loader is not a reliable new-season source now |
| `features/qualifying.py:representative_laps` | FastF1 lap frame → remove missing time, deleted laps, pit in/out; retain laps ≤ 1.03 × each driver's best clean lap → lap frame | A 90.000-second best retains ≤92.700-second laps; see Sprint 1 notebook | 3% is a heuristic, not a fuel/push-lap classifier; it can include traffic or nonrepresentative laps |
| `features/qualifying.py:build_practice_features` | One practice `Session` + prefix → best/top-three/soft/theoretical lap, counts, tyre life, speed trap; normalize gap against event best → one row per driver | If driver best is 91.0s and session best 90.0s, gap is 1.111…% | Optional fields may be null; lap validity follows FastF1 and the filter above |
| `features/qualifying.py:build_qualifying_targets` | Q results → Q1/Q2/Q3 seconds, final classification, Q1 percent gap → target frame | Q1 91.0s vs 90.0s best gives 1.111…% | Targets are unavailable before qualifying and never legal current inputs |
| `features/qualifying.py:build_weekend_dataset` | FP1/2/3/Q sessions → outer practice merge, inner qualifying merge, FP3 team mapping → driver-weekend frame | One conventional GP usually has ~20 rows; `_validate` requires ≥8 FP3 and Q1 observations | Race grid after penalties is separate; FastF1 source may be unavailable |
| `data/qualifying_dataset.py:scheduled_conventional_events` | FastF1 season schedule → filter `EventFormat == conventional`, positive round, chronological sort → round/name list | 2022 schedule returned 19 selected conventional events | Sprint weekends are intentionally excluded because FP3 may not exist |
| `data/qualifying_dataset.py:build_dataset` | Season list → resume/validate per-event Parquet → combined Parquet and ingestion CSV | First run found 17 cached 2022 and one cached 2025; resumed two 2022 events | Failed events remain visible in report; interrupted run may leave per-event files without rewriting combined file |
| `data/enrich_team_metadata.py:enrich` | Existing event Parquet → cached FP3 `Driver`/`Team` lookup → updated event Parquet | 2022 R20/R22 team labels filled from FP3 | Reopens FastF1 sessions and may warn if schedule endpoint is unavailable |

## OpenF1 adapter

| Symbol | Input → algorithm → output | Example and proof | Caveat |
|---|---|---|---|
| `OpenF1Client.get` | Endpoint + sorted query params → SHA-256 keyed JSON cache; uncached HTTP with ≥2.1s spacing and bounded 429/5xx retries → list of records plus response hash | `session_result?session_key=7768` returned 2023 Bahrain Q phase times; local raw cache is ignored by Git | Public historical tier documents 30 requests/minute; a cached response may later be revised upstream |
| `conventional_weekends` | Year `meetings` and `sessions` → sort completed race meetings, number rounds, retain FP1/2/3 + Q with no Sprint session → event descriptors | Unit test keeps rounds 1 and 3 when round 2 is Sprint | Cancelled meetings are excluded from numbering; verify against season schedule when interpreting round IDs |
| `_practice_rows` | Practice `session_result` records → seconds/rank/gap relative to fastest reported lap → driver-number frame | Bahrain 2023 FP3 VER = 92.345s; ALO = 92.340s, so ALO has zero gap | Result best laps are not raw lap series; tyre/sector/representative fields stay null |
| `normalize_weekend` | Four session result lists + Q driver metadata → Q1/Q2/Q3 split, final classification, practice merge, normalized gaps, provider/time labels → driver-weekend frame | Bahrain 2023 Q VER Q1 = 91.295s, classification P1; SAI had fastest Q1 at 90.993s | Q result and metadata are used after the event to construct historical labels/identity; models only use legal pre-Q columns |
| `build_dataset` | Years → resumable per-event fetch, validation, report and combined Parquet | 52 2023–2025 weekends and 1,038 rows with zero errors; `qualifying_openf1_weekends/*.parquet` | API failures are logged; a partial combined file would not prove complete coverage |
| `mixed_qualifying.combine` | 2022 FastF1 per-event files + OpenF1 combined file → source/time/hashes, duplicate check, provider coverage manifest | 71 weekends and 1,418 rows in `qualifying_mixed_2022_2023_2024_2025.parquet` | Mixed providers require the common feature set and broader overlap audit |

## Model and evaluation modules

| Symbol | Input → algorithm → output | Example and proof | Caveat |
|---|---|---|---|
| `qualifying_backtest.prepare_dataset` | Raw driver-weekend rows → derive within-event practice-only gaps; coerce numeric; keep rows with FP3, Q1 target and classification → eligible frame | 2022/2023 training, 2024 validation, 2025 test; `sample_coverage.csv` records drop counts | Excluded drivers change the evaluated field; ranks are within eligible drivers |
| `FEATURES` / `COMMON_FEATURES` | Static legal feature registries → model columns | Common list: FP1/2/3 gap/rank and two gap improvements | Rich features are unsuitable for mixed providers because OpenF1 lacks lap-level values |
| `model_pipelines` | Feature list → train-only median imputer, scaler, one-hot encoder, Ridge(α=20) or LightGBM(150 trees, 12 leaves, seed 42) | Offline synthetic tests fit both | Hyperparameters were fixed before viewing 2025; this is a benchmark, not tuned optimum |
| `scored_positions` | Driver rows + lower-is-faster predicted Q1 score → deterministic within-event rank by score/driver | FP3 90s beats 91s; tie broken stably by driver | Prediction ranks are proxies for final classification |
| `evaluate` | Ranked driver table → per-event position MAE, Spearman, pole hit, top-three overlap | MAE = mean absolute position difference within event | Event means weight every GP equally regardless of eligible driver count |
| `paired_event_bootstrap` | Per-event candidate and FP3 errors → resample paired event differences with seed 42 → mean delta and 95% percentile interval | Three events all −1.0 MAE yield [−1, −1] in unit test | Descriptive uncertainty across sampled events; not future-race calibration |
| `run_backtest` | Dataset, feature set and chronological years → fit on 2022–2023, select lowest 2024 event MAE, evaluate 2025 → tables, coverage and manifest | `test_season_split_and_models_execute` asserts group counts and split | A minimum weekend guard prevents small smoke sets; it does not guarantee representative coverage |
| `historical_qualifying.add_historical_features` | Complete chronology including past labels → sort year/round; driver `shift(1)` before rolling 3/5; one team mean per event before team shift → 12 form columns | If a driver's R1 Q1 gap is 0.5%, their R2 last-3 contains 0.5%; changing R2 labels leaves R2 inputs unchanged in test | Current-year earlier events are legal; team renames reset team history; driver abbreviation is the join key |
| `qualifying_ablation.run_ablation` | Raw rows → same baseline plus form features and two form models; choose among five by 2024 only → validation/test tables, form coverage, bootstrap | Synthetic tests verify first event has no form and current label cannot change current features | Historical form is learned from previous classification, while Q1 is still only a proxy for final Q order |

## Notebooks, scripts and tests

- Notebook 01 explores one Monza 2025 FP3-to-Q comparison; its saved single
  event MAE/Spearman is **not** a held-out generalization estimate.
- Notebook 02 reads baseline CSV/Parquet outputs and visualizes event errors.
- Notebook 03 cells 0–5 describe the ablation and show 2024 selection/2025
  held-out tables; cells 6–7 plot both splits; cells 8–9 inspect historical
  feature availability; cells 10–11 pivot test event errors; cell 12 lists
  interpretation questions. The notebook consumes CLI artifacts; model logic
  is not embedded in its cells.
- `scripts/make_nvim_pairs.sh` uses Jupytext percent format to pair three
  notebooks with text sources. It does not modify Neovim configuration.
- `tests/test_qualifying_backtest.py` checks legal features, within-event
  normalization/ranking, grouped years, duplicate rejection and paired
  bootstrap. `tests/test_historical_qualifying.py` checks lagging and five-model
  execution. `tests/test_openf1_qualifying.py` checks schedule numbering and
  result normalization. These synthetic fixtures test code invariants only;
  real performance comes from the separate historical run.

## Session foundation (partial P0)

| Symbol | Input → algorithm → output | Proof and limit |
|---|---|---|
| `session.contracts.SessionId` | Season, round, kind and provider key → immutable validated identifier | 2025 Monza race uses OpenF1 key 9912; cross-provider ID mapping remains future work |
| `session.contracts.SessionEvent` | Typed payload, source, three UTC timestamps, session seconds, sequence, quality → immutable versioned event | Synthetic validation rejects wrong payload and naive observation time |
| `session.contracts.RaceState` | Session ID and reduced events → one clock, driver dictionary, global flag, race-control messages and event IDs | Local UI now consumes this state; live provider remains future work |
| `session.reducer.reduce_event` | Current state + next ordered event → copied next state; duplicate ID returns same state | Tests cover order, time and session rejection; late packets need a source reorder buffer |
| `session.reducer.seek_state` | Events + cutoff seconds → sort and reduce from start → deterministic state | Test compares forward reduction with arbitrary seek; checkpoints are future work |
| `session.openf1_sample.build_sample` | Cached OpenF1 2025 Monza race-control records → 53 post-start message events and local ignored JSON | Real source SHA in `DATA_CONTRACTS.md`; message timeline only, no positions/laps |
| `session.openf1_replay._timed_events` | OpenF1 position/lap/pit/stint/control rows → source-labelled, UTC-sorted events with unique sequence | 1,506 real Monza events; 974 dated positive-duration laps, 2 unusable counted; lap completion is estimated start + duration |
| `session.openf1_replay._location_samples` | One driver's raw location rows → actual nonzero points at most 2 Hz, with filter counts | 9,915 points retained per driver, 198,300 overall; no interpolated point is stored in the pack |
| `session.openf1_replay._interval_samples` | Gap/interval rows → per-driver time-indexed numeric values and `+N LAP` text | 20,226 raw interval rows; latest values older than 10 seconds are hidden at seek |
| `session.openf1_replay._geometry` | VER race lap 3 source points → approximate 166-point circuit trace | OpenF1 coordinates have arbitrary origin and unknown units; not surveyed geometry |
| `session.openf1_replay.build_replay_pack` | Cached OpenF1 resources → compressed ignored JSON pack, source hashes, coverage and final-result QA | 20 drivers, 18/18 classified position and 20/20 lap-total match; no post-race result injected into earlier events |
| `session.replay_source.ReplaySource` | Replay pack → 64-event checkpoints + binary-searched sidecars → one `RaceState(t)` | 131 real seek times agreed with full reduction; measured coordinates preserved, interpolated positions marked estimated |
| `session.validate_replay.validate` | Local pack → event/checkpoint/driver comparison and latency report | Median 1.123 ms, p95 2.329 ms on this machine; no browser FPS claim |

`RaceSource` now exists as a mode-independent Python protocol, and one
approximate geometry trace and one offline replay pack exist. The full
`CircuitGeometry` contract, more golden sessions and live/simulation adapters
remain. See `REPLAY_2025_MONZA.md` for field-level semantics.

### Schema 2 replay context

| Symbol | Input → algorithm → output | Proof and limit |
|---|---|---|
| `session.openf1_context.weather_payload` | OpenF1 row → finite/range/unit validation → canonical weather values | Real cache validation matches all 350 retained observations; no interpolation or rain intensity inference |
| `session.openf1_context.track_status_payload` | OpenF1 race-control message and scope → accept only eligible track-wide cases → conservative `TrackStatusPayload` | Reviewed golden boundaries: 2 Monza, 2 Monaco, 10 Brazil; ending signals do not assert green |
| `session.reducer.reduce_event` | Schema 1/2 event + immutable state → copy current observation/status at event time → current schema 3 `RaceState` | 20 context reducer/contract tests; schema 1 packs stay readable |
| `session.validate_context.validate` | Local schema 2 pack + exact raw cache bytes → independent source-lineage, cutoff and golden-message audit → QA JSON | 700 weather before/exact cutoff checks and 14 signal boundary checks; only three cached races |
| `web.lib.session_context.weatherAt` | Canonical session time + observation → age seconds and `0 <= age <= 120` freshness → shown/stale state | Three unit cases include zero-valued temperatures, exact 120-second limit, future and stale observations |
| `WeatherPanel` | Canonical state + all historical rainfall state changes → source-labelled readings and exact seek buttons | Six browser tests use actual local packs; rain means provider-reported presence only |

## Local Race Control UI (partial P2)

| Symbol | Input → algorithm → output | Proof and limit |
|---|---|---|
| `api.create_app` | Path or `F1LAB_REPLAY_PACK` → cached `ReplaySource`, HTTP manifest and `state?seconds=` | Synthetic TestClient fixture, real Monza HTTP 200; 503 missing pack and 422 invalid time |
| `ReplaySource._location_at` | Indexed provider points → measured exact or short estimated bracket, with 15 s identical-coordinate cutoff | Synthetic frozen-point test; cutoff is heuristic, not a retirement claim |
| `App` | One playback seconds value and speed (1/2/4×) → 5 Hz canonical state requests, shared timing/map/control rendering | TypeScript build and ESLint; browser interaction/visual review still needed |
| `TrackMap` | Provider XY trace and current state coordinates → uniformly projected SVG circuit/car marks | Coordinates approximate and unitless; does not produce surveyed geometry or telemetry |
| `TrackMap` visual interpolation | Successive canonical states → 180 ms CSS transform only on forward deltas up to 4 seconds; seeks/backward/large jumps disable it | Eight Chromium tests cover playback, exact seek and reduced motion; no 60 Hz/FPS claim |
| `StintPanel` | Selected driver's schema 3 `tyre_stints` at the same session time → one lane per source event, compound, lap range, quality and overlap note | 39/57/52 retained stint events in Monza/Monaco/Brazil; Monaco HUL duplicate lap-1 starts remain separate; see `REPLAY_STINTS_AND_MOTION.md` |

### Schema 3 stint state and display interpolation

| Symbol | Input → algorithm → output | Proof and limit |
|---|---|---|
| `contracts.TyreStintState` | Existing timed `StintPayload` plus lap events → validated source event/time, compound, lap range, quality and close event → immutable per-driver history | `RaceState` emits version 3; event envelopes and packs remain version 2; no event data was added to packs |
| `reducer.reduce_event` stint branch | New source stint → close the prior stint at the latest completed lap (at least its start lap), mark its close event, append the new start; lap event grows the open end | Does not read provider `lap_end` from a start row; same-lap starts are retained; synthetic test covers cutoff and overlap |
| `StintPanel` timeline geometry | `scheduled_laps`, `lap_start`, `lap_end` → `left=100×(lap_start−1)/scheduled_laps`; `width=100×max(1,lap_end−lap_start+1)/scheduled_laps` | Gaps and overlaps stay visible; null end renders at start lap, labelled in progress |

All transport times are seconds since scheduled 2025 Monza race origin. SVG
projection is dimensionless. Driver lap durations/gaps remain seconds from
the backend contract. `RACE_CONTROL_UI.md` has precise reproduction, source,
test evidence and caveats.

## Additional session audit

| Symbol | Input → algorithm → output | Proof and limit |
|---|---|---|
| `audit_candidates.Candidate` | Year and country → immutable session lookup request | Monaco 2023 and Brazil 2024 are explicit defaults |
| `audit_candidates.audit_candidate` | One OpenF1 Race session and nine source tables → checked table rows; only 404 becomes unavailable | Real audit found Monaco `pit` 404; all other HTTP failures propagate |
| `audit_candidates.summarize` | Source rows and hashes → counts, driver coverage, rain/compound categories, critical control timestamps | Synthetic fixture distinguishes null from zero; counts are raw source records, not events |

The ignored `data/processed/replay_candidate_audit.json` preserves response
hashes for reproduction. `REPLAY_CANDIDATES.md` records numbers and the
builder changes required before claiming a second replay.

## Three-session implementation (supersedes one-race limits above)

The current replay builder/source/API/UI call chain and every major changed
symbol are documented in `REPLAY_GOLDEN_SESSIONS.md`. The new
`session/catalog.py:ReplaySpec` supplies one explicit race specification;
`_timed_events`, `_location_samples`, `_interval_samples` and
`_geometry` all accept its scheduled UTC origin. Event IDs carry the
selected provider key. `build_replay_pack` checks actual session metadata
and preserves optional pit capability gaps; `_verify_pack_against_results`
requires matching driver coverage and compares only available result totals.

`api.create_app` lists local session availability and caches sources by slug;
`RaceState.capabilities` reaches consumers even without a manifest fetch.
`validate_replay._compare_discrete` compares all driver fields except
explicit location/interval overlays against a separate forward reduction,
at all boundaries and in shuffled order. The current proof is 14,112
cutoffs plus 600 shuffled revisits across the three packs.

`apps/web/src/lib/playback-clock.ts:PlaybackClock` implements anchored
monotonic time. `ReplayWorkspace` in `App.tsx` owns one instance, samples
it at 200 ms, cancels state requests on seek/session change and displays
the same returned state in every data panel. The root `App` fetches the
catalog and remounts the workspace by selected slug. Two Node clock tests
and four Playwright tests in `apps/web/e2e/replay.spec.ts` cover invariants
and real-pack browser integration. Screenshot and raw artifact locations,
units, example timeline jumps, initial failures/fixes and exact reproduction
commands are in the three-reference document.

## Distance-aligned telemetry (partial P3)

| Symbol | Input → algorithm → output | Proof and limit |
|---|---|---|
| `telemetry.contracts.LapTelemetryPoint` | One car-data sample → immutable typed values and source channel names → point on approximate elapsed/distance axes | Unit tests check validation and raw-value preservation; distance is integrated, not measured geometry |
| `telemetry.distance_alignment.build_lap_telemetry` | One lap row + one driver's timestamped car data → identity/pit-out checks, ≤1 s boundary/gap contract, trapezoidal speed integration → `LapTelemetry` | Real Monza 2025 VER/NOR lap-50 streams and synthetic exact-integration/boundary/gap tests; provider lap start remains approximate |
| `telemetry.distance_alignment.compare_laps` | Two laps from one session + raw response hashes → common range, regular 5 m grid, continuous linear and discrete previous-state interpolation → `LapComparison` | 1,150 real comparison points; `elapsed_B - elapsed_A` is labelled in seconds; only two drivers and one race |
| `telemetry.openf1_lap_comparison.main` | CLI options + rate-limited `OpenF1Client` cache → provenance JSON and speed/delta PNG | Reproduced from cached OpenF1 responses; generated files remain ignored under `data/processed/telemetry_comparisons/` |
| `api.create_app` telemetry route | Session slug + expected local artifact path → Pydantic validation, session-key check and plotted-field projection → comparison JSON | Returns 503 when the local artifact is absent/invalid; it never calls the provider |
| `web.lib.telemetry-comparison.comparisonCursorAtSessionTime` | One canonical session time + reference lap UTC start → elapsed time on lap A → interpolated estimated distance/delta/speed cursor | Synthetic UTC-offset unit tests and real Chromium seek/playback checks; cursor is hidden outside the reference lap |
| `TelemetryPanel` | The returned comparison + current canonical `RaceState.session_time_seconds` → speed/delta SVG and crosshair → readouts on the shared replay clock | Nine Chromium tests pass; the fixed Monza pair has no selector and only other sessions with generated artifacts can display data |

The full hashed JSON artifact retains all source channels. The API projects the
fields needed by this chart, reducing the current response from 847,619 to
200,119 bytes. The chart labels the axis as estimated and displays the exact
session-time basis for its cursor.

## Historical qualifying Prediction Lab (partial P4)

| Symbol | Input → algorithm → output | Proof and limit |
|---|---|---|
| `qualifying_backtest.audit_prequalifying_cutoff` | Common/full legal feature list + source rows → target-field allowlist check, FP1/FP2/FP3 lineage registry and scheduled-cutoff audit → manifest data | 1,418 qualifying cutoff rows; feature-level observed-at timestamps are absent, so it documents rather than overclaims the cutoff |
| `qualifying_backtest.main` | Cached mixed Parquet → event-grouped training/selection/test → CSV, Parquet and SHA-256 experiment manifest | Ridge remains selected using 2024 only; 2025 remains held out; source hash `eef5a727…37fd8` |
| `models.prediction_lab.load_prediction_lab` | Local experiment JSON, summary CSVs and predictions Parquet → schema/split/allowlist/checksum checks → in-memory report | Test fixtures verify successful projection, absent artifact, and changed prediction/summary bytes; API performs no provider requests |
| `models.prediction_lab.prediction_event` | Year/round/split → pivot the three model rank outputs by driver → retrospective rank table and event metrics | API output omits Q1 pace target and raw `final_position`; it exposes actual rank only for evaluation |
| `api.create_app` Prediction Lab routes | Local ignored `data/processed/qualifying_backtest/` → `/api/v1/predictions/qualifying` manifest or `/event` selection → JSON | Real local manifest returns 36 validation/test event choices and eight features; absent or altered artifacts return 503 |
| `web/components/PredictionLab` | Manifest + selected historical split/event → validation/holdout metrics, baseline/model ranks, actual order and limitations | Ten Chromium scenarios pass across the app; screenshot is in `data/processed/browser_tests/results/`; this is not live prediction serving |

The feature target is Q1 gap percentage; rank metrics compare predictions with
final qualifying classification. The selected event’s target columns are not
included in the API response. `PREDICTION_LAB.md` records the exact split,
metrics, hashes, reproduction and timestamp caveats.

### Phase-aware extension (partial M5)

| Symbol | Input → algorithm → output | Proof and limit |
|---|---|---|
| `qualifying_phases.cached_openf1_sessions` | Ignored cached `/sessions` JSON → local session rows | Does not make provider requests |
| `qualifying_phases.phase_event_schedule` | OpenF1 meeting keys + Practice 1/2/3 schedule → scheduled practice-end cutoffs, next-session boundary checks and canonical SHA-256 | 52 weekends in each phase; exact result publication time is not present |
| `qualifying_phases.run_phase_experiment` | OpenF1 2023–2025 driver rows + phase feature allowlist → per-phase eligible participants, train 2023, select on 2024, hold out 2025 → predictions, event metrics and paired bootstrap | 16/18/18 events; phase cohorts exclude rows missing the measured practice baseline |
| `qualifying_phase_lab.load_phase_prediction_lab` | Local manifest and phase artifacts → split/feature-lineage/checksum validation, per-driver complete models, rank permutations, cohort counts and metric reconciliation | Tests reject future-session features, dropped model rows and inconsistent summaries even with refreshed hashes, plus tampered Parquet |
| `qualifying_phase_lab.phase_prediction_event` | Phase/year/round/split → predicted and actual eligible ranks, separate official qualifying position and scheduled cutoff | API omits target and raw final-position field names; official classification is projected as `qualifying_position` |
| `api.create_app` phase routes | Local ignored `qualifying_phases/` → `/api/v1/predictions/qualifying/phases` manifest and `/event` selection | Real cached manifest returns three phases, 36 validation/test event choices per phase; API has no provider calls |
| `web/components/PredictionLab` phase selector | Phase/split/event → phase-specific feature registry, metric cards and rankings | Ten Chromium cases pass; 2025 intervals cross zero and no probability claims appear |

Each phase selects among a measured same-session practice baseline, Ridge and
LightGBM using 2024 event mean position MAE. The input scope is 2 / 4 / 8
features after FP1 / FP2 / before qualifying. Since FastF1 2022 schedules were
not available offline, this extension uses OpenF1 across all three splits and
has only 16 training weekends. The API labels practice-end cutoffs as
scheduled; it does not claim exact provider availability. See
`QUALIFYING_PHASES.md` for feature units, metrics, hashes and reproduction.


## Driving-line geometry, selected location context and browser observations

`src/f1_racelab/session/geometry.py`: `build_circuit_geometry` receives driver
location arrays `[session_seconds,x,y]`, timed lap records, clock origin,
session/layout IDs and optional pit stops. It rejects incomplete/discontinuous
laps, chooses a deterministic low-closure-error lap and returns a frozen typed
`CircuitGeometry`: source/normalized XY, bounds, normalization transform,
provider-unit cumulative arc length, radians, provenance hashes and diagnostic
counts. Normalization is `(xy−bounds_midpoint)/max(bounds_spans)`; arc length
is the sum of Euclidean segment lengths. The closing segment is explicitly
inferred. Tests cover chronology, finite values, rejection, row-order stability,
closure and geometry invariants. A driving line is a display trace; physical
track edges, pit lane, sectors, corners and official start line remain absent.

`src/f1_racelab/session/location_history.py`: `build_location_context` slices
the existing validated source time index by binary search for a trailing
12-second window. It appends/replaces only the already-computed canonical
current position, splits dropouts/jumps into separate segments, then estimates
current movement direction from the last connected moving pair. `LocationContext`
validates bounds, increasing timestamps and heading consistency. API state with
optional `focus_driver` returns this alongside the same timestamp and drivers;
no extra renderer clock or alternate position interpolation is introduced.
Missing/stationary/disconnected current movement yields no direction.

`apps/web/src/lib/circuit-geometry.ts`: `projectCircuit` validates provider XY
and derives aspect-preserving centered SVG coordinates with Y inverted;
`projectTrail` draws separate segments with estimated endpoints dashed;
`headingScreenDegrees` negates radians when converting to screen degrees.
`components/TrackMap.tsx` memoizes projection/static `CircuitTrace`, renders
canonical car locations and selected context, and suppresses transition
animation on seeks/pause. Geometry identity and source quality remain visible.
Tests cover projection, invalid inputs and heading conversion; all 11 browser scenarios, including deterministic trail/heading, seek and
driver selection assertions, pass.

`apps/web/benchmarks/playwright.config.ts` and `replay-performance.spec.ts`:
opt-in local API/Vite Chromium harness samples three real packs at 1× for four
seconds each and records raw RAF callbacks, long tasks when supported, eight
panel clocks, requests, decoded body bytes, four seeks/session and JS heap.
Output retains source/manifest fingerprints and environment metadata under
ignored `data/processed/browser_benchmarks/`. These observations measure local
scheduling, delivery and DOM agreement; they do not measure painted FPS,
full-process memory, survey accuracy or causal optimization benefit. See
`REPLAY_GEOMETRY_AND_PERFORMANCE.md` and the benchmark README for commands.

Temporal detail: measured trail vertices are at or before requested time `t`.
The canonical estimated endpoint may use a later source sample as the existing
historical interpolation bracket; this is retrospective reconstruction, not
proof that data had been published live by `t`. Without `focus_driver`, the API
returns strict canonical `RaceState` schema 3. Focused `location_context` is a
view extension of that same state response; it does not change the canonical
state schema or create another position/clock authority.


## Three-session telemetry catalog and channel semantics (worktree)

`telemetry/artifacts.py` defines frozen `ComparisonSpec(session_slug,driver_a,
lap_a,driver_b,lap_b)`, deriving stable `comparison_id`, label and local path.
`COMPARISONS` explicitly selects one pair for each supported replay; no hidden
provider default is used as a scientific clean-lap certificate. The comparison
builder/API consume those selections; offline CLI and all three final artifacts pass verification. Monaco pit-in absence cannot be proved from missing pit data.

`telemetry/contracts.py`: `LapTelemetry.ordered_samples` validates counts,
start/end, monotonic time/distance and reported max gap. `LapComparison` checks
both laps' session/meeting identity, distinct source laps, common end equal to
the shorter integrated lap, full uniform grid count/spacing, increasing elapsed
times within both lap bounds, zero-time origin and exact delta B−A. These checks
prevent internally inconsistent persisted JSON from entering UI scoring.

`lib/telemetry-comparison.ts`: `TELEMETRY_CHANNELS` maps speed/throttle/brake/
RPM/gear/DRS to API field names, display units and continuous/discrete semantics.
`channelValue` preserves missing values as null. `telemetryChannelPath` breaks
at missing values and draws step segments for discrete source channels.
`comparisonCursorAtSessionTime` binary-searches reference-A elapsed time on the
common grid, interpolates continuous values and holds earlier discrete values;
it returns null outside available sampled time, including a short trailing
portion of the reference lap beyond the common grid. Replay session origin
and lap UTC start define time; changing channels does not advance another clock.
The six-channel UI is integrated; final coverage/test evidence is in
`TEST_EVIDENCE.md`.

Additional current contract evidence: 16 focused distance-alignment tests pass
and scoped Ruff passes, including eight serialized-contract mutation cases,
two fractional gear/DRS rejection cases and one missing-channel case. The
builder rejects fractional discrete codes instead of silently truncating them
with `int()`. The previous real Monza artifact validates against the stricter
contract. API projection exposes all aligned channels and lap-quality metadata
while omitting the large raw `lap.points` arrays; all three-session builds
and integrated checks pass.

`openf1_lap_comparison.py --all --offline` now builds catalog artifacts, PNGs
and QA records using only existing cached resources. The API projects every
aligned channel and lap sample/gap/boundary/pit-quality metadata without raw
source-lap point arrays. `TelemetryPanel.tsx` selects six channels while keeping
elapsed B−A visible and memoizing channel paths; missing values break paths,
discrete codes stay step-valued and out-of-coverage cursors are absent. Final
proof: 104 Python, 12 JS unit and 14 browser tests; exact artifact data and
commands are in `TEST_EVIDENCE.md`.


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

## Walk-forward forecaster (2026-10-29)
`qualifying_walkforward.py` → artifacts → `walkforward_lab.py` (SHA check) → `api.py`
`/api/v1/predictions/qualifying/walkforward[/event]` → `ForecastPanel.tsx`.
Data audit: `data/quality.py`. Client hardening: `OpenF1Client._fetch`.

## 2026-10-31 — deployment and reliability call chains

- `infra/api.Dockerfile` → frozen scientific deps + source `/app/src` → non-root
  Uvicorn with repo-relative read-only `/app/data/processed`. `web.Dockerfile`
  → locked Vite build → unprivileged Nginx same-origin API/WS. Compose profiles
  isolate optional services; `scripts/smoke_compose.py` checks SPA/API, real packs,
  optional model inference and simulated-live WebSocket forwarding. CI also
  tests basic startup without private research artifacts.
- `api.create_app` → isolated `HttpTelemetry` registry and lifespan; middleware
  receives ASGI HTTP scopes, derives safe correlation IDs and registered route
  templates, records status/count/monotonic seconds and failure logs. Tests
  validate unmatched path cardinality, per-app registry isolation and shutdown.
- `registry.save_artifact` → `tracking.record_artifact` → verified byte hashes +
  atomic local run manifest → optional MLflow REST experiment/run/metrics/artifacts.
  `artifact_import` does not refit; `training` follows registry save. Failures
  remain explicit; original model contract and library checks remain unchanged.
- `reliability.build` consumes saved prediction/frame Parquets → one-to-one
  paired comparisons by race/driver/lap → 5,000 race-bootstrap draws (seed 42),
  signed bias and MAE in seconds, reference-decile PSI/missingness → hash-linked
  report. `load` verifies report sidecar; API projects it with model/run cards.
  Rebuild after source changes; no live drift detector or fresh holdout claim.
- `ResearchObservatory` lazily reads report; Recharts season-bias plot, season
  selector/failure review, card/feature provenance. `AgentInvestigation` reads
  saved diagnoses and tool observations only. Fixed-path `forecast_debug.service`
  returns source hashes and omits model `thought` fields; bundled synthetic-fault
  evaluation is a clean-checkout fallback. React renders tool output as text.
- `Circuit3DLoader` uses a type-only props import and dynamic module import on
  user action; actual Three.js scene still consumes existing geometry/state.
  `initiallyVisible` avoids requiring a second click after module load. Browser
  test proves no scene chunk request before opening, then tests Orbit interaction.
- `ForecastTools.run_sql` guards size, parses SELECT, locks one connection and
  starts an interrupt timer; fetches 51 rows, limits 32 unique columns/string
  cell length, reports sampled row-count exactness. Timer cancellation+join
  prevents a late interrupt hitting the next query. External access, extension
  autoload/install and spill are disabled; memory 128 MB/thread 1. Cooperative
  cancellation is not an OS sandbox. Evaluation closes each connection.

See `MLOPS_AND_DEPLOYMENT.md` for examples, formulas, exact paths, reproduced
metrics, sources/licenses, tests and limitations. `fingerprint_frame` remains
row-order-sensitive; its docstring/test now describes the existing contract.

## 2026-10-31 — Driver DNA training-only normalization

`protocol.fit_train_normalization(x, train_indices)` accepts finite N-dimensional
feature tensors, unique in-range explicit training rows; stores read-only float64
mean/std+1e-6. `apply_train_normalization` validates feature shape/finite inputs,
returns dimensionless float32 z-scores without fitting. Synthetic held-out poison
cannot affect training statistics or outputs. Existing per-circuit function is
retained and explicitly documented as transductive.

`normalization_study.run` loads existing tensors/meta → raw 17 handcrafted
features and original per-circuit variant → existing circuit/blocked teammate
folds and fixed logistic/LightGBM factories → real paired-protocol result JSON
and SHA. It records source/dependencies/input hashes; no new data or neural fit.
`driver_dna.service.summary` adds an optional checksum-verified study and always
labels original scores transductive; UI shows protocols side by side. `tests/
test_driver_dna_normalization.py` covers poisoning/contracts/optional data/tamper;
research browser scenario checks real 19.8% logistic and no-inductive-neural warning.
All metrics/units/caveats/reproduction are in `research/DRIVER_DNA.md`.

## Issue #2 paired agent study

- `agents/forecast_debug/paired.py`: isolated per-arm subprocess runner, fixed
  Ollama settings, source/model/table hashes, atomic resumable cases, one-writer
  lock, matched pair validation and known-family clustered accuracy bootstrap.
- `agents/forecast_debug/service.py:load_paired`: verifies publication checksums
  and protocol identity, recomputes scores, binds semantic annotations to result
  hashes; returns tool observations without internal model thoughts.
- `api.py`: GET-only `/api/v1/research/agent-paired`; invalid evidence gives 503.
- `apps/web/src/components/PairedAgentStudy.tsx`: same-incident two-arm selection,
  failure filter, scores, cited observations, support reasons and data provenance.
  Loaded inside the existing lazy Research & reliability workspace.
- Tests: `test_agent_paired.py`, `test_agent_paired_service.py`, research Playwright
  interactions. Compose includes the small synthetic-warehouse output bundle.
- Inputs/outputs, algorithm, seconds/proportions, review findings and exact
  reproduction: `research/AGENT_PAIRED_EVALUATION.md`. No external data download.
