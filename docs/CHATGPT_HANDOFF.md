# F1LAB handoff for the next ChatGPT session

**Status at 2026-10-16 UTC:** qualifying research benchmark complete; three
real historical race packs build, reconcile and play through one local API/UI:
Monza 2025, Monaco 2023 and Brazil 2024. Four actual Chromium browser tests
pass, and desktop/mobile screenshots were inspected. P1/P2 remain partial.
Branch `feat/foundation`; pushed prior checkpoints include `2d270fc`
(first UI) and `7940f2c` (candidate audit), the starting SHA of the current
three-session milestone. Check `git log -1`, `git status` and
`git ls-remote origin refs/heads/feat/foundation` for its final SHA/push state.
Git uses the repository's Aymen Jedidi identity and no assistant coauthor
trailers. Two unrelated untracked `ml/features/` helpers remain untouched.

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
- **Replay reference gate verified:** Python Pydantic events/state, pure
  ordered reducer, `RaceSource`, indexed/checkpointed `ReplaySource` and
  audited session catalog. The three packs have 20 drivers each and total
  5,290 events / 799,422 retained source XY points. Available final positions
  and lap totals reconcile; all-boundary seeks and shuffled jumps pass.
  `REPLAY_GOLDEN_SESSIONS.md` contains per-race counts/hashes/proof.
- **Partial Race Control UI:** local catalog and per-session state API;
  session picker, anchored central clock, 0.25×–16×, exact seek/control and
  race-start jumps, timing tower, driver focus, approximate 2D map, full
  prior control feed, missing-source indicators and mobile transport.
  Every data panel uses one returned state; React polls at 5 Hz rather
  than rerendering the whole tree on every animation frame.
- **Source quality:** Monaco `pit` is HTTP 404, so capability is absent and
  UI displays unavailable. Brazil STR's null stint start is counted/skipped;
  HUL's null DSQ lap total is excluded from that QA comparison. Global
  SC/VSC/red-flag messages are preserved; a full track-status mapping and
  weather state/display remain unfinished.
- **Not done:** production ML timestamp/probability audit and prediction
  serving; continuous smooth car rendering, surveyed/full geometry, complete
  tyre/stint/weather panels and retirement-time handling; telemetry and
  distance comparisons; strategy, what-if, live/radio, 3D, CI and storage/
  schema-export hardening. The full product goal remains active.

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
path. `session/catalog.py` defines the three supported specifications.
Compressed packs/manifests/QA stay ignored under `data/processed/replay_packs/`.
`src/f1_racelab/api.py` caches sources by session slug;
`apps/web/src/App.tsx` and `App.css` render the UI with
`src/lib/playback-clock.ts` as the browser clock.
`tests/test_replay_api.py` tests cross-session isolation synthetically;
`apps/web/e2e/replay.spec.ts` tests real local packs in Chromium.

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
.venv/bin/python -m f1_racelab.session.openf1_replay --session monaco-2023
.venv/bin/python -m f1_racelab.session.openf1_replay --session brazil-2024
.venv/bin/python -m f1_racelab.session.validate_replay --all
.venv/bin/python -m f1_racelab.session.audit_candidates
.venv/bin/uvicorn f1_racelab.api:app --host 127.0.0.1 --port 8000
cd apps/web && npm ci && npm run dev -- --host 127.0.0.1
```

Start the API and frontend commands in separate terminals. Choose a session,
jump to race start, play/pause/seek and select a driver. In Brazil, a control
jump to “SAFETY CAR IN THIS LAP” shows t=6,484 s in all data panels. Monaco
shows unavailable pit records. Restart the API after rebuilding cached packs.

From `apps/web`, `npx playwright install chromium`,
`npm run test:unit` and `npm run test:e2e` run the clock and actual browser
checks. The browser suite launches/cleans up its own local servers on
8011/5181, requires all three packs and performs no provider downloads.
It passed **4/4**; screenshots under ignored
`data/processed/browser_tests/results/` were visually inspected at
desktop 1440×1000 and mobile 390×844. No measured 60 Hz/FPS claim is made.

The latest full Python test run passed **30/30**, two JS clock tests passed,
Ruff passed, mypy passed for 11 session/API source files, and web
ESLint/TypeScript/Vite build passed. `npm ci` now uses a tracked lockfile.
Exact commands are
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
improvement is claimed.

Monza/Monaco/Brazil match 18/18, 19/19 and 15/15 classified positions and
20/20, 20/20 and 19/19 available lap totals; Brazil has one unavailable DSQ
lap-total label. The validator compares all discrete/audit fields through
14,112 event-boundary/regular cutoffs plus 600 seed-42 shuffled revisits.
It preserves a measured first coordinate for 59 source-driver series;
Brazil ALB has no retained location series. Latest per-race p50/p95 seek ms:
Monza 1.078/2.309, Monaco 1.233/2.816, Brazil 1.057/2.438.
Full artifact hashes and limits are in `REPLAY_GOLDEN_SESSIONS.md`;
the combined local report is `replay_packs/golden_sessions.qa.json`.
Packs change hashes on rebuild because ingest/gzip timestamps change.

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
| Optional historical pit resource | Monaco 2023 `pit` HTTP 404 | Builder/state/UI now expose missing capability; pit duration/count truth remains unavailable |
| Global track status | SC/VSC/red messages are source-specific and ending signals are not green-running proof | Status remains unconfirmed until scoped status contract and transitions are validated |
| Partial smoothness and geometry | Backend state is sampled at 5 Hz; outlines are one measured lap trace | Browser interactions pass, but continuous rendering/full geometry/FPS work remains |
| Browser dependency audit | Production audit clean; full audit has seven high advisories in shadcn development CLI chain | CLI is dev-only; suggested fix is major downgrade and was not applied |
| Null Brazil records | STR stint has no start, HUL DSQ lap total null, ALB location empty | Preserve gaps and coverage; do not inject final labels or synthetic coordinates |

## Next five actions

1. Confirm current three-session checkpoint SHA and remote push state.
2. Implement scoped track-status/weather contracts and source-time transitions;
   preserve unknown cases rather than deriving green from an ending notice.
3. Add timestamped smooth map rendering, tyre/stint views and fuller P2
   keyboard/performance coverage; then distance-align real lap telemetry.
4. Expand cross-provider overlap and as-of timestamp audits before promoting
   a qualifying model toward production use.
5. Continue Prediction Lab, independent strategy simulator, what-if, live
   and 3D in the locked dependency order. Keep all modes on canonical state.

For tutoring, read `AGENT_WORKLOG.md`, `IMPLEMENTATION_ATLAS.md`,
`ML_EVALUATION.md`, `TEST_EVIDENCE.md`, `DATA_CONTRACTS.md`, `DECISIONS.md` and
`GLOSSARY_FOR_LEARNING.md` after this page. The locked scope remains
`SOL61_MASTER_EXECUTION.md`; a passing ML benchmark will not finish it.
