# F1LAB handoff for the next ChatGPT session

**Status at 2026-10-16 UTC:** qualifying research benchmark complete; one
real 2025 Monza offline pack now builds, seeks and serves through a local API.
The first shared-clock 2D Race Control screen is implemented. Branch
`feat/foundation`; pushed checkpoints `b6835e7`, `4c5bd37` and
`abe031c`, and UI checkpoint `2d270fc`. Check `git log -1`, `git status`
and `git ls-remote origin refs/heads/feat/foundation` for the exact later
candidate-audit checkpoint SHA/push state.

## What exists and what does not

- **Done before this run:** Monza 2025 practice/qualifying exploration; Sprint 2
  FastF1 feature builder, chronological backtest code and synthetic tests.
  The saved single-Monza result (MAE 2.70 positions, Spearman 0.823) is a
  one-event comparison, not a generalization score.
- **Implemented in this run:** project-scoped pytest collection, a public
  OpenF1 historical adapter with raw response cache and request pacing,
  common-source qualifying feature set, provider-labelled dataset merge,
  event-paired bootstrap and coverage outputs, and normalization tests.
- **Done in this run:** OpenF1 ingestion for 2023–2025, merged 2022–2025
  dataset, real 2024 model selection and 2025 held-out evaluation, five-model
  form ablation, one-event provider overlap audit, one manual historical-form
  trace, and executed notebook chart. See `EXPERIMENT_REGISTER.md`.
- **Now implemented in part:** Python Pydantic `SessionEvent`/`RaceState`, pure
  ordered reducer, `RaceSource` protocol and indexed `ReplaySource`. A real
  OpenF1 2025 Monza pack has 20 drivers, 1,506 discrete events, 198,300
  retained approximate location points, laps, position changes, pit records,
  stints, intervals and race-control messages. It includes a 166-point
  approximate one-lap circuit trace. Read `REPLAY_2025_MONZA.md` for exact
  source/time/quality contract and QA. The older 53-message smoke sample remains.
- **First UI/API implemented:** local FastAPI manifest and `RaceState(t)`
  endpoints, a React/Vite pit-wall screen with one playback clock (seek,
  play/pause, 1/2/4×), timing tower, selected-driver detail, provider-derived
  approximate 2D map and race-control message timeline. Missing locations
  are hidden, including unchanged coordinates after 15 seconds. Backend
  states are requested at most 5 Hz. See `RACE_CONTROL_UI.md` for source
  paths, API, data semantics and exact evidence.
- **Two further sessions audited, not built:** OpenF1 2023 Monaco race 9094
  has wet/intermediate coverage but its `pit` resource returned HTTP 404.
  OpenF1 2024 Brazil race 9636 has rain, VSC, safety-car and red-flag records.
  `session/audit_candidates.py` preserves a real source coverage/hash report
  in ignored `data/processed/replay_candidate_audit.json`. See
  `REPLAY_CANDIDATES.md` for counts, times, SHA-256 and implementation limits.
- **Not done:** calibrated probabilities, prediction serving, full historical
  replay across three representative sessions, browser visual/interaction
  proof, 3D visualization, telemetry comparison, strategy, what-if, live
  and radio. The 2D screen is one-race and partial P2.

## Why the provider changed

The initial local `qualifying_2022_2023_2024_2025.parquet` had only 360 rows:
17 conventional 2022 weekends plus 2025 Monza. The prior ingestion log hit
FastF1's 500 calls/hour limit. This run completed two more cached 2022
weekends, but uncached 2023 F1 timing failed; a direct 2023 Bahrain timing URL
returned HTTP 401. OpenF1 documents public historical data from 2023 onward
and returned Q phase times, FP3 results and driver/team identity. We preserve
the original dataset and build a separate source-labelled one. See
`DATA_CONTRACTS.md`, `DECISIONS.md` and [OpenF1 docs](https://openf1.org/docs/).

## Architecture and source map

`src/f1_racelab/data/fastf1_source.py` configures the local cache;
`features/qualifying.py` computes practice rows and post-Q labels;
`data/qualifying_dataset.py` stores FastF1 event Parquets;
`data/openf1_qualifying.py` stores OpenF1 JSON and normalizes 2023–2025;
`data/mixed_qualifying.py` combines providers;
`features/historical_qualifying.py` creates strictly lagged driver/team form;
`models/qualifying_backtest.py` and `models/qualifying_ablation.py` fit and
evaluate five candidate rankings. `IMPLEMENTATION_ATLAS.md` describes inputs,
outputs, formulas, tests and caveats per function. `ARCHITECTURE.md` diagrams
the actual data flow and partial unified replay architecture. The new
`session/contracts.py`, `session/reducer.py`, `session/source.py`,
`session/openf1_replay.py`, `session/replay_source.py` and
`session/validate_replay.py` provide the first canonical, real-data replay
path. The compressed pack, manifest and QA report are local ignored artifacts
under `data/processed/replay_packs/`. `src/f1_racelab/api.py` exposes the
pack and state locally; `apps/web/src/App.tsx` and `App.css` render the
single-clock UI. `tests/test_replay_api.py` covers synthetic API contracts.

## Reproduction and evidence

```bash
uv sync --dev
.venv/bin/pytest -q
.venv/bin/python -m f1_racelab.data.openf1_qualifying --years 2023 2024 2025
.venv/bin/python -m f1_racelab.data.mixed_qualifying
.venv/bin/python -m f1_racelab.models.qualifying_backtest --dataset data/processed/qualifying_mixed_2022_2023_2024_2025.parquet --feature-set common
.venv/bin/python -m f1_racelab.models.qualifying_ablation --dataset data/processed/qualifying_mixed_2022_2023_2024_2025.parquet --feature-set common
.venv/bin/python -m f1_racelab.session.openf1_sample
.venv/bin/python -m f1_racelab.session.openf1_replay
.venv/bin/python -m f1_racelab.session.validate_replay
.venv/bin/python -m f1_racelab.session.audit_candidates
.venv/bin/uvicorn f1_racelab.api:app --host 127.0.0.1 --port 8000
cd apps/web && npm ci && npm run dev -- --host 127.0.0.1
```

The latest full test run passed **28/28**, Ruff passed, mypy passed for ten
session/API source files, and web ESLint/TypeScript/Vite build
passed; exact commands are
in `TEST_EVIDENCE.md`. Fixture tests are separate from the real provider data
and model experiment. Generated
datasets and metrics are under ignored `data/processed/`; inspect
`qualifying_mixed_manifest.json`, ingestion CSV, `qualifying_backtest/` and
`qualifying_ablation/`. The mixed file has 71 conventional weekends and 1,418
source rows, with 35/18/18 eligible train/validation/test events and
684/342/354 evaluated rows. Its SHA-256 is
`eef5a7277d2f62fdf263e94cadbc7a5f5c38cd6acdbea9dc00549d5caef37fd8`.
Ridge won on 2024 MAE (2.8362 vs FP3 2.8975). Its held-out 2025 MAE was
3.2433 vs FP3 3.3141, with paired event delta -0.0708 and 95% bootstrap
interval [-0.2934, +0.1587]. The interval crosses zero, so no reliable
improvement is claimed. The UI now has a one-race local replay demo; browser
inspection was unavailable, so no visual/interaction or FPS result is claimed.

The replay builder checked 18/18 classified end positions and 20/20 completed
lap totals against OpenF1 `session_result` without leaking that final table
into earlier replay events. The validator compared 131 arbitrary/event-boundary
seeks with full reduction and found no discrete-state differences; one exact
location sample was preserved. The most recent validator run gave p50/p95
0.975/2.066 ms. The API returned HTTP 200/35,246-byte manifest and 20 driver
states at t=1,200 seconds (20 located, max completed lap 11). These are
one-race backend results, not browser frame-rate or multi-race proof.
Pack/source hashes are in the local manifest;
the pack hash changes across rebuilds because ingest timestamps change.

## Known failure and risk matrix

| Issue | Evidence | Effect / next handling |
|---|---|---|
| FastF1 uncached archive access | F1 timing URL HTTP 401 | Use OpenF1 historical data, keep source labels and raw hashes |
| Mixed provider best-lap definitions | FastF1 lap filter vs OpenF1 `session_result`; 2025 Monza matched exactly on available pairs | Extend overlap audit beyond one event; use common eight fields |
| Q1 pace proxy vs final Q classification | Pipeline target/label definitions | Report separately; phase-aware model remains future work |
| Limited uncertainty evidence | 18 held-out events; paired interval crosses zero | Avoid superiority or deployment claims |
| Team names and driver acronyms as identifiers | Current row schema | Audit transfers, substitutions and renamed constructors before production |
| Approximate replay geometry | OpenF1 positions have arbitrary origin and unknown unit; trace is VER lap 3 | Show coordinate/quality labels; do not call the trace surveyed or precise |
| Repeated stopped-car locations | Provider may repeat constant points after a DNF/DNS | 15-second identical-coordinate streak now hides the map point; heuristic may hide a legitimate stationary car; no retirement time inferred |
| Browser QA | Computer-use Chrome and in-app browser unavailable | Build/static/API tests pass; visual, responsive and interaction QA remain |
| Optional historical pit resource | Monaco 2023 `pit` HTTP 404; other eight audited resources available | Generic builder must expose unavailable pit capability instead of assuming zero pit stops |

## Next five actions

1. Confirm current UI checkpoint SHA and remote push state.
2. Inspect the rendered local UI at desktop/mobile widths and exercise
   seek, playback, speed, driver selection and message jumps in a browser.
3. Generalize the replay builder to audited Monaco/Brazil with explicit
   missing-resource semantics; build and run end-state/seek QA for both.
4. Expand cross-provider overlap and as-of timestamp audits before promoting
   a qualifying model toward production use.

For tutoring, read `AGENT_WORKLOG.md`, `IMPLEMENTATION_ATLAS.md`,
`ML_EVALUATION.md`, `TEST_EVIDENCE.md`, `DATA_CONTRACTS.md`, `DECISIONS.md` and
`GLOSSARY_FOR_LEARNING.md` after this page. The locked scope remains
`SOL61_MASTER_EXECUTION.md`; a passing ML benchmark will not finish it.
