# Test and experiment evidence ledger

Evidence classes: **real data** means responses/cache from a historical
provider; **synthetic fixture** means test rows constructed by the test suite.
Exit codes and limits are retained even when a later fix passes.

| UTC date | Command / observation | Exit | Class | Result |
|---|---|---:|---|---|
| 2026-10-15 | `uv --version`; `.venv/bin/python --version`; `node --version` | 0 | environment | uv 0.12.17, Python 3.12.13, Node 22.23.2 |
| 2026-10-15 | `uv sync --dev` | 2 in sandbox, 0 elevated | environment | Cache directory outside workspace needed tool elevation; 167 packages resolved, 164 checked |
| 2026-10-15 | `uv run pytest -q` before testpaths | 2 | synthetic tests | Collected unrelated `references/` tests and failed on their dependencies |
| 2026-10-15 | `uv run pytest -q` after `[tool.pytest.ini_options]` | 0 | synthetic tests | 10 passed initially; later additions increased count |
| 2026-10-15 | `.venv/bin/pytest -q` after OpenF1 adapter/bootstrap | 0 | synthetic tests | 14 passed; no model performance claim |
| 2026-10-15 | `.venv/bin/ruff check src tests` before cleanup | 1 | static | Initial source/style diagnostics, including broad exception catches and a loop closure warning; cleanup in progress |
| 2026-10-15 | Read `data/processed/qualifying_2022_2023_2024_2025.parquet` | 0 | real cached data | 360 rows: 17 2022 weekends + 2025 Monza; 359/360 team labels |
| 2026-10-15 | `uv run python -m f1_racelab.data.qualifying_dataset --years 2022 2023 2024 2025` | 130, interrupted | real provider/cache | Built 2022 R20 and R22. Uncached 2023 session requests failed; stopped to avoid repeated failed requests. Combined file was not rewritten |
| 2026-10-15 | `curl -IL --max-time 15` F1 2023 Bahrain `SessionInfo.json` | 0 (HTTP 401) | real provider | F1 archive access denied for this uncached timing URL |
| 2026-10-15 | OpenF1 2023 Bahrain `sessions`, `session_result`, `drivers` | 0 (HTTP 200) | real provider | Public archive returned Q phase times, classification, FP3 best and team identity |
| 2026-10-15 | `.venv/bin/python -m f1_racelab.data.enrich_team_metadata --years 2022` | 0 with cached-response warnings | real cache | 19/19 2022 event Parquets enriched; combined `qualifying_2022.parquet` written. DNS was unavailable in sandbox; cached schedule/timing were used |
| 2026-10-15 | `.venv/bin/python -m f1_racelab.data.openf1_qualifying --years 2023 2024 2025` | 0 | real provider | 52 conventional weekends, 1,038 driver rows, zero errors across 2023–2025 |
| 2026-10-15 | `.venv/bin/python -m f1_racelab.data.mixed_qualifying` | 0 | real provider/cache | 71 weekends, 1,418 rows; SHA-256 in `qualifying_mixed_manifest.json` |
| 2026-10-15 | `.venv/bin/python -m f1_racelab.models.qualifying_backtest --dataset data/processed/qualifying_mixed_2022_2023_2024_2025.parquet --feature-set common` | 0 | real historical experiment | 2024 Ridge selected; 2025 Ridge MAE 3.2433 vs FP3 3.3141; paired 95% interval crosses zero |
| 2026-10-15 | `.venv/bin/python -m f1_racelab.models.qualifying_ablation --dataset data/processed/qualifying_mixed_2022_2023_2024_2025.parquet --feature-set common` | 0 | real historical experiment | Five candidates; form Ridge did not win 2024 selection |
| 2026-10-15 | `.venv/bin/python -m f1_racelab.data.audit_provider_overlap --year 2025 --round 16` | 0 | real provider overlap | 20 Monza drivers matched; all paired best times equal; zero classification mismatches |
| 2026-10-15 | `.venv/bin/python scripts/audit_historical_form.py data/processed/qualifying_mixed_2022_2023_2024_2025.parquet` | 0 | real feature audit | Independently traced 2025 Monza VER driver/team three-event features to earlier rounds |
| 2026-10-15 | `.venv/bin/jupytext --sync notebooks/03_qualifying_form_ablation.ipynb` and notebook execution via nbclient | 0 | real artifact rendering | Seven code cells, zero errors; saved ignored executed notebook and 59 KB plot |
| 2026-10-15 | `.venv/bin/pytest -q` after all qualifying changes | 0 | synthetic tests | 16 passed; an initial new test failed only because compared Series retained different row index names, then the assertion was corrected |
| 2026-10-15 | `.venv/bin/ruff check src tests scripts` | 0 | static | All checks passed |
| 2026-10-15 | `npm run build` in `apps/web` | 0 | frontend build | Vite starter builds; no Race Control UI is claimed |
| 2026-10-15 | `.venv/bin/python -m f1_racelab.session.openf1_sample` | 0 | real provider/cache | 53 post-start Monza 2025 race-control messages normalized from OpenF1 session 9912; final event at 4,896 s; source SHA in `DATA_CONTRACTS.md` |
| 2026-10-15 | `.venv/bin/pytest -q tests/test_session_reducer.py` | 0 | synthetic tests | 3 passed: idempotence, ordering, session guard, deterministic seek and payload validation |
| 2026-10-15 | `.venv/bin/pytest -q`; `.venv/bin/ruff check src tests scripts`; `git diff --check` | 0 | synthetic/static | 19 tests passed, Ruff clean, whitespace clean after session foundation |
| 2026-10-15 | `.venv/bin/python -m f1_racelab.session.openf1_replay` first attempt | 1 | real provider/cache | All 20 location responses cached; builder then failed on a `lap`→`laps` source-table mapping error before writing pack |
| 2026-10-15 | `.venv/bin/python -m f1_racelab.session.openf1_replay` after mapping fix | 0 | real provider/cache | 20 drivers, 1,506 events, 198,300 location points, 24 checkpoints; final 18/18 classified positions and 20/20 lap totals matched |
| 2026-10-15 | `.venv/bin/python -m f1_racelab.session.validate_replay` | 0 | real pack QA | 131 indexed seeks matched full reduction; exact source coordinate preserved; p50 1.123 ms, p95 2.329 ms locally |
| 2026-10-15 | `.venv/bin/pytest -q`; `.venv/bin/ruff check src tests scripts`; `uv sync --dev` | 0 | synthetic/static/environment | 24 tests passed, Ruff clean; uv resolved 167 packages and checked 164 |
| 2026-10-15 | `.venv/bin/mypy src/f1_racelab/session --follow-imports=silent --ignore-missing-imports` | 1 then 0 | static | Initial nine type errors in new replay adapter; explicit payload kind/union and nullable numeric guards fixed them; eight session source files now pass |
| 2026-10-16 | `.venv/bin/pytest -q tests/test_replay_api.py` | 0 | synthetic fixture | Initial two API tests passed; full suite later includes third frozen-coordinate test |
| 2026-10-16 | `curl -sS -w ... http://127.0.0.1:8000/api/v1/replay/monza-2025/manifest` | 0, HTTP 200 | real historical pack | 35,246-byte JSON manifest from local ignored Monza pack |
| 2026-10-16 | `curl -sS 'http://127.0.0.1:8000/api/v1/replay/monza-2025/state?seconds=1200'` | 0, HTTP 200 | real historical pack | 20 driver states; 20 had locations at t=1,200 s; max completed lap 11 |
| 2026-10-16 | `.venv/bin/pytest -q`; `.venv/bin/ruff check src tests scripts` | 0 | synthetic/static | 27 passed (one Starlette/httpx deprecation warning); Ruff clean |
| 2026-10-16 | `.venv/bin/mypy src/f1_racelab/session src/f1_racelab/api.py --follow-imports=silent --ignore-missing-imports` | 1 then 0 | static | Initial new stationary-index `starts` annotation missing; explicit `list[float]` fixed it |
| 2026-10-16 | `npm run lint`; `npm run build` in `apps/web` | 1 then 0; 0 | static/build | Initial lint flagged effect state update and generated shadcn variant exports; effect corrected and narrow UI component lint exception added. Final lint and TypeScript/Vite build passed; JS 300.65 KB (98.86 KB gzip) |
| 2026-10-16 | `.venv/bin/python -m f1_racelab.session.validate_replay` | 0 | real historical pack | 131/131 state seeks match; measured sample preserved; p50/p95 0.975/2.066 ms; pack SHA `c993cc67937cb4dcc82d7bd604214c7059e31d72c5d76830f365c90ca1074fa8` |
| 2026-10-16 | Browser visual/interaction inspection | skipped | unavailable surface | Both Chrome and in-app browser reported unavailable through computer-use tool; no visual or FPS claim |
| 2026-10-16 | Manual OpenF1 coverage fetch for sessions 9094/9636 | 1 then 0 | real provider/cache | Initial 2023 Monaco `pit` HTTP 404 stopped the naive loop; explicit 404 handling found remaining table counts, rain and control coverage |
| 2026-10-16 | `.venv/bin/python -m f1_racelab.session.audit_candidates` | 0 | real provider/cache | Ignored `data/processed/replay_candidate_audit.json`: Monaco 8/9 available tables, Brazil 9/9; source hashes retained; details in `REPLAY_CANDIDATES.md` |
| 2026-10-16 | `.venv/bin/pytest -q tests/test_replay_candidate_audit.py`; `.venv/bin/pytest -q` | 0 | synthetic tests | 1 audit test and 28 full-suite tests passed; one existing Starlette/httpx deprecation warning |
| 2026-10-16 | `.venv/bin/ruff check src tests scripts`; `.venv/bin/mypy src/f1_racelab/session/audit_candidates.py --follow-imports=silent --ignore-missing-imports` | 0 | static | Ruff and audit module mypy clean |
| 2026-10-16 | `.venv/bin/mypy src/f1_racelab/session src/f1_racelab/api.py --follow-imports=silent --ignore-missing-imports`; `git diff --check` | 0 | static | Ten session/API source files type-check; working-tree whitespace check clean |
| 2026-10-16 | `.venv/bin/python -m f1_racelab.session.openf1_replay --session monaco-2023` | 0 | real provider/cache | 20 drivers, 2,101 events, 280,028 XY points; 19/19 classified positions and 20/20 lap totals matched; pit resource unavailable |
| 2026-10-16 | `.venv/bin/python -m f1_racelab.session.openf1_replay --session brazil-2024` | 1 then 0 | real provider/cache | Initial null stint start raised TypeError; null guard and explicit missing DSQ lap-total QA fixed it. 20 drivers, 1,683 events, 321,094 XY points; 15/15 positions and 19/19 available lap totals matched |
| 2026-10-16 | Final cached `build_replay_pack(spec=spec)` loop for all catalog specs | 0 | real cache | All three rebuilt with current metadata; full executed loop in worklog; manifests/hashes in `REPLAY_GOLDEN_SESSIONS.md`, ignored `golden_build.log` |
| 2026-10-16 | `.venv/bin/python -m f1_racelab.session.validate_replay --all` | 0 | real local packs | 3,868/5,798/4,446 cutoffs plus 200 shuffled revisits per race matched; 59 source-driver first coordinates preserved, ALB Brazil location absent; combined ignored `golden_sessions.qa.json` |
| 2026-10-16 | `.venv/bin/pytest -q`; `.venv/bin/mypy src/f1_racelab/session src/f1_racelab/api.py --follow-imports=silent --ignore-missing-imports` | 0 | synthetic/static | 30 Python tests passed with one existing Starlette/httpx warning; 11 source files type-check |
| 2026-10-16 | `npm run test:unit` | 1 then 0 | synthetic clock | Initial exact floating-point equality failed at 34.123000000000005; 1e−9 tolerance corrected assertion. Both clock tests now pass, including stopped-end seek behavior |
| 2026-10-16 | `npm run test:e2e` | 1 then 0 | real local-pack browser | First run 2 passed/2 failed on unnamed slider input; label forwarded to actual input. Final run 4 passed in 10.9 s; inspected desktop Monza/Brazil and mobile Monaco screenshots in ignored browser-test output |
| 2026-10-16 | `npm ci`; `npx playwright install chromium` | 0 | bootstrap | 552 packages installed from tracked lockfile; Playwright 1.64.1 and Chromium 156 fallback build on Arch Linux |
| 2026-10-16 | `npm audit --json`; `npm audit --omit=dev` | 1; 0 | dependency audit | Seven high advisories in development shadcn CLI chain; suggested fix requires major downgrade. Production-only audit reports zero; no force fix |
| 2026-10-16 | `npm run lint`; `npm run build` | 0 | frontend static/build | Three-session UI passes ESLint and TypeScript/Vite build; final size recorded in milestone notes |
| 2026-10-16 | `git push origin feat/foundation`; `git ls-remote origin refs/heads/feat/foundation` | 0 | publication | Implementation checkpoint `af2f64677d48d7f9573451de1419fbe3e0b98e08` pushed and remote SHA verified; user Git identity, no coauthor trailer |

Generated data and metric tables are ignored by Git. The public OpenF1 source
contract and documented 30 requests/minute free limit are at
[OpenF1](https://openf1.org/docs/). `OpenF1Client` spaces uncached requests by
at least 2.1 seconds. No production paid API or live feed was used.

## 2026-10-16 — schema 2 weather and track context

| Exact command/check | Result | Evidence class and artifact |
|---|---|---|
| `.venv/bin/pytest -q` | 50 passed; 1 existing Starlette/httpx deprecation warning | Synthetic contracts, replay/API behavior and raw-cache tamper fixture |
| `.venv/bin/ruff check src tests scripts` | Passed | Static source checks |
| `.venv/bin/mypy src/f1_racelab/session src/f1_racelab/api.py --follow-imports=silent --ignore-missing-imports` | 13 files passed | Static type checking |
| `cd apps/web && npm run test:unit` | 3 passed | Synthetic clock and weather freshness boundaries |
| `cd apps/web && npm run lint` | Passed | Frontend static checks |
| `cd apps/web && npm run build` | Passed | TypeScript/Vite production bundle |
| `cd apps/web && npm run test:e2e` | 6 passed against three real local packs | Chromium interactions, Monaco rain changes, Brazil signal meanings, synced panel timestamps; screenshots are ignored under `data/processed/browser_tests/results/` |
| `.venv/bin/python -m f1_racelab.session.validate_context --all` | 700 weather cutoff comparisons, 14 reviewed track-signal boundaries, all source rows reconciled, zero invalid weather rows | Real raw OpenF1 cache; reports `data/processed/replay_packs/golden_context.qa.json` and per-pack `*.context.qa.json` |
| `.venv/bin/python -m f1_racelab.session.validate_replay --all` | 15,162 event-boundary/regular cutoffs and 600 shuffled revisits agree with independent forward reduction | Real local schema 2 packs; `data/processed/replay_packs/golden_sessions.qa.json` |
| `git diff --check` | Passed before commit | Static whitespace check |
| `git push origin feat/foundation`; `git ls-remote origin refs/heads/feat/foundation` | Exit 0; remote SHA `111fb60777fa55327ddca36d0b95c04d06990e6f` | Published implementation checkpoint on the feature branch, authored with repository identity |

The new context pack SHA-256/bytes/event totals are Monza
`cdb6a7a6f79d18c24c51001aef9c7829bfbf4db1d9da7fd9b4fab2559c1ae1dd` /
1,781,361 / 1,592; Monaco
`3b2cb79107ed8d5c72e14a87f0c3705d1cb29c9a7a2b735f52c07686b0294f2a` /
2,534,796 / 2,220; Brazil
`ca3df608046d96d9d87d9ae383037a11192800802f7d5c88603a7ca6bbb5cdec` /
2,436,435 / 1,842. Pack hashes may change on rebuild because gzip metadata
contains build-time data. Raw weather response SHA-256 values are documented
in `REPLAY_CONTEXT.md` and the generated manifests.

The first six-case browser run had five passes and one readiness timeout; its
captured page showed that all 20 timing rows eventually rendered. An isolated
rerun then exposed that a repeated `SESSION STARTED` message made `.first()`
seek to the wrong event. The test now waits up to 15 seconds for the real
20-driver render and selects the exact event by session seconds. The targeted
Brazil case and final six-case suite pass. No behavior test uses mocked race
observations; the weather freshness unit tests use synthetic times by design.
Toolchain: Python 3.12.13 / FastAPI 0.142.2; Node 22.23.2 / npm 10.9.8;
Playwright 1.64.1 / Chromium 156; Vite 8.3.2.

## 2026-10-16 — source-time stint state and playback map transitions

| Exact command/check | Result | Evidence class and artifact |
|---|---|---|
| `.venv/bin/pytest -q` | 51 passed; one existing Starlette/httpx deprecation warning | Synthetic reducer/API/context contracts |
| `.venv/bin/ruff check src tests scripts` | Passed | Static source checks |
| `.venv/bin/mypy src/f1_racelab/session src/f1_racelab/api.py --follow-imports=silent --ignore-missing-imports` | 13 source files passed | Static type checking |
| `cd apps/web && npm run test:unit` | 3 passed | Synthetic clock/weather tests |
| `cd apps/web && npm run lint` | Passed | ESLint |
| `cd apps/web && npm run build` | Passed; JavaScript 413.23 KB (136.45 KB gzip), CSS 67.09 KB (13.12 KB gzip) | TypeScript/Vite production build |
| `cd apps/web && npm run test:e2e` | 8 passed in 19.5 s | Chromium, actual local Monza/Monaco/Brazil packs; stints, map playback, backward/small-forward seek and reduced motion |
| `.venv/bin/python -m f1_racelab.session.validate_replay --all` | All packs passed; 15,162 event-boundary/regular cutoffs and 600 shuffled revisits | Real local packs; ignored `golden_sessions.qa.json`; emitted `RaceState` schema 3 with 39/57/52 stint segments |
| `.venv/bin/python -m f1_racelab.session.validate_context --all` | All packs passed; 700 weather cutoff checks, 14 reviewed signal boundaries, zero invalid weather rows | Real raw cache; ignored per-pack context reports and `golden_context.qa.json` |
| `git diff --check` | Passed before publication | Patch/whitespace check |
| `git push origin feat/foundation`; `git ls-remote origin refs/heads/feat/foundation` | Exit 0; remote SHA `4a0434aea67ff99a2f949abc08babdcbf0b50578` | Implementation checkpoint published under repository identity with no coauthor |

The first map-motion browser attempt sought Monza's pack end and expected a car
element after all location observations had become unavailable. The page
correctly rendered zero cars there, so the test now seeks to the source
`SESSION STARTED` record with measured positions. Review also found that a
short forward exact seek should be immediate even if its time delta resembles
a playback sample; motion now requires `playing=true`, and the browser suite
checks a paused forward seek. The reducer similarly accepts Monaco car 27's
two same-lap stint starts rather than discarding one. Full source lineage,
contracts, screenshot paths and limitations are in
`REPLAY_STINTS_AND_MOTION.md`.

## 2026-10-16 — distance-aligned telemetry foundation

| Exact command/check | Result | Evidence class and artifact |
|---|---|---|
| `.venv/bin/pytest -q tests/test_distance_alignment.py` | 5 passed | Synthetic exact integration, boundary, gap, identity and comparison contracts |
| `.venv/bin/python -m f1_racelab.telemetry.openf1_lap_comparison` | Exit 0; 1,150 grid points at 5 m; distances 5,746.062 m and 5,751.324 m | Real cached OpenF1 session 9912, driver 1/4 lap 50; JSON/PNG ignored under `data/processed/telemetry_comparisons/` |
| `.venv/bin/pytest -q` | 56 passed; one existing Starlette/httpx deprecation warning | Synthetic suite including telemetry contracts |
| `.venv/bin/ruff check src tests scripts` | Passed | Repository static checks |
| `.venv/bin/mypy src/f1_racelab/telemetry src/f1_racelab/session src/f1_racelab/api.py --follow-imports=silent --ignore-missing-imports` | 17 files passed | Static type checking |
| Visual inspection of comparison PNG | Readable speed and B−A panels with estimated-distance labeling | Real derived artifact; not an interactive UI or precision geometry claim |
| `git push origin feat/foundation`; `git ls-remote origin refs/heads/feat/foundation` | Exit 0; implementation SHA `2ac01012c780552f26bd9504f88c9cac87541000` matches remote | Published source and documentation checkpoint; repository identity, no coauthor trailer |

Full input hashes, formulas, output hashes and caveats are in
`DISTANCE_ALIGNED_TELEMETRY.md`. This milestone does not include web tests
because no frontend/API consumer was changed.

## 2026-10-16 — historical qualifying Prediction Lab

| Exact command/check | Result | Evidence class and artifact |
|---|---|---|
| `.venv/bin/python -m f1_racelab.models.qualifying_backtest --dataset data/processed/qualifying_mixed_2022_2023_2024_2025.parquet --feature-set common` | Exit 0; Ridge selected on 2024; 2025 metrics reproduced | Real cached dataset, 71 events / 1,418 source rows; predictions SHA-256 `88195b26ef5f3f5ab86d7b8a906233e7b0c6ef1af05401fc9f74d3afe91d011b` |
| `.venv/bin/pytest -q tests/test_prediction_lab.py tests/test_qualifying_backtest.py tests/test_replay_api.py` | 16 passed, one existing Starlette/httpx deprecation warning | Synthetic cutoff, missing/tampered artifact, response projection and replay API contracts |
| `.venv/bin/pytest -q` | 61 passed, one existing Starlette/httpx deprecation warning | Full Python suite |
| `.venv/bin/ruff check src tests scripts` | Passed | Repository source/test/script static checks |
| `.venv/bin/mypy src/f1_racelab/session src/f1_racelab/telemetry src/f1_racelab/api.py src/f1_racelab/models/qualifying_backtest.py src/f1_racelab/models/prediction_lab.py --follow-imports=silent --ignore-missing-imports` | 20 source files passed | Static type check with the repo's missing-third-party-stub policy |
| `cd apps/web && npm run test:unit` | 5 passed | Existing clock/context/telemetry unit suite |
| `cd apps/web && npm run lint` | Passed | ESLint |
| `cd apps/web && npm run build` | Passed; JS 431.12 KB (141.19 KB gzip), CSS 78.22 KB (15.43 KB gzip) | TypeScript/Vite production build |
| `cd apps/web && npm run test:e2e` | 10 Chromium tests passed in 21.8 s | Three real replay packs plus Prediction Lab split switch, artifact rendering and return navigation |
| `git push origin feat/foundation`; `git ls-remote origin refs/heads/feat/foundation` | Exit 0; implementation SHA `9f928361c9c7fdf59a2e685dc2994137cf942e35` matches remote | Published from `feat/foundation` with repository owner identity and no coauthor trailer |
| Real-artifact API via FastAPI `TestClient` | Manifest HTTP 200 / 6,337 bytes; 36 events, eight features, 1,418 cutoff rows; Abu Dhabi 2025 test event HTTP 200 / 20 drivers | Local regenerated artifact; no provider request |
| Screenshot inspection | Desktop page shows the selected model, holdout metrics, retrospective actual rank, interval crossing zero and timestamp caveat | `data/processed/browser_tests/results/replay-Prediction-Lab-labe-7122e-tes-validation-from-holdout-chromium/prediction-lab-holdout.png` |
| `.venv/bin/ruff check` (whole repository) | 17 pre-existing findings | Three findings are in the two preserved untracked `ml/features/` user files; the rest are notebook/interactive-cell lint findings. No unrelated files were edited; scoped `src tests scripts` check passes |
| Direct mypy without repository flags | Failed on missing pandas/scipy/scikit-learn stubs and an inferred dictionary key type | No dependency changes were made; supported scoped command above passes after explicit response typing |
| Initial `npm run lint` for this page | Failed on synchronous state reset in the event-fetch effect | Loading state is now derived from selected event/result; final ESLint passes |

The exact feature cutoff is based on scheduled qualifying session start and
FP1/FP2/FP3 lineage. Individual feature observation/publication times remain
unrecorded. The run is historical and retrospective, not a live forecast; see
`PREDICTION_LAB.md` for the model metrics, hashes, API, reproduction and limits.

## 2026-10-16 — shared-clock telemetry panel and local API artifact route

| Exact command/check | Result | Evidence class and artifact |
|---|---|---|
| `.venv/bin/pytest -q` | 57 passed; one existing Starlette/httpx deprecation warning | Synthetic reducer/API/telemetry contracts |
| `.venv/bin/ruff check src tests scripts` | Passed | Repository static checks |
| `.venv/bin/mypy src/f1_racelab/telemetry src/f1_racelab/session src/f1_racelab/api.py --follow-imports=silent --ignore-missing-imports` | 18 files passed | Static type checking |
| `cd apps/web && npm run test:unit` | 5 passed | Clock, weather and synthetic UTC-to-distance cursor tests |
| `cd apps/web && npm run lint` | Passed | ESLint |
| `cd apps/web && npm run build` | Passed; JS 420.49 KB (138.37 KB gzip), CSS 69.12 KB (13.60 KB gzip) | TypeScript/Vite production build |
| `cd apps/web && npm run test:e2e` | 9 passed in 19.0 s | Chromium against three real packs; cursor matches canonical time, advances on normal seek and hides out of reference-lap range |
| `GET /api/v1/replay/monza-2025/telemetry/lap-comparison` via FastAPI `TestClient` | HTTP 200; 200,119 bytes; 5 projected sample fields plus session and source hashes | Real local comparison artifact; full JSON is 847,619 bytes and remains ignored |
| Screenshot inspection | Cursor at estimated 0 m on lap start; speed and delta axes readable, no tick/title overlap | `data/processed/browser_tests/results/replay-telemetry-crosshair-176f6--clock-on-its-reference-lap-chromium/telemetry-cursor.png` |
| `git push origin feat/foundation`; `git ls-remote origin refs/heads/feat/foundation` | Exit 0; implementation SHA `43e12407a7f13e02b0eb6d6a3fc0206442ca5816` matches remote | Published API/UI and documentation milestone under repository identity, no coauthor trailer |

First browser run had 8/9 passing because the existing generic status-role
selector matched both the Monaco coverage notice and a static telemetry hint.
The hint no longer uses that role; the full 9-case run passes. Axis-title
overlap was fixed after screenshot review. This integration makes no new
provider request. Details and exact query hashes are in
`DISTANCE_ALIGNED_TELEMETRY.md`.

## 2026-10-16 — phase-aware qualifying snapshots

| Exact command/check | Result | Evidence class and artifact |
|---|---|---|
| `.venv/bin/python -m f1_racelab.models.qualifying_phases --dataset data/processed/qualifying_mixed_2022_2023_2024_2025.parquet` | Exit 0; 1,038 OpenF1 source rows; 52 scheduled weekends per phase | Real cached OpenF1 dataset and schedule cache; no provider request |
| Source dataset and canonical schedule SHA-256 | `eef5a7277d2f62fdf263e94cadbc7a5f5c38cd6acdbea9dc00549d5caef37fd8`; `af8ce323bb62591d925fded4fdaf696276921a305bb26fbc970573579d82734d` | Real local artifacts; phase manifest `data/processed/qualifying_phases/experiment.json` |
| `.venv/bin/pytest -q` | 65 passed in 3.99 s; one existing Starlette/httpx deprecation warning | Synthetic phase cutoff, schedule overlap, feature lineage, chronology, projection and tampered-artifact contracts; all existing Python tests |
| `.venv/bin/ruff check src/f1_racelab tests` | Passed | Static lint |
| `.venv/bin/mypy src/f1_racelab/models/qualifying_backtest.py src/f1_racelab/models/qualifying_phases.py src/f1_racelab/models/qualifying_phase_lab.py src/f1_racelab/api.py --follow-imports=silent --ignore-missing-imports` | Four source files passed | Static type check |
| `cd apps/web && npm run test:unit` | 5 passed | Frontend clock, weather and telemetry tests |
| `cd apps/web && npm run build && npm run lint` | TypeScript/Vite build and ESLint passed | Frontend production verification |
| `cd apps/web && npm run test:e2e` | 10 Chromium tests passed in 23.8 s | Three real replay packs plus Prediction Lab phase/split/event interactions |
| `cd apps/web && npm run test:e2e -- --grep 'Prediction Lab'` | Final enhanced scenario passed, 1 test in 8.8 s | Austria FP1 PIA eligible rank 1 / official qualifying P3, separate table columns, and 2024 validation interval label |
| FastAPI `TestClient`, `/api/v1/predictions/qualifying/phases` | HTTP 200; three phases; 36 validation/test event choices per phase | Real checksum-verified ignored phase artifacts |
| FastAPI `TestClient`, after-FP1 Abu Dhabi 2025 event | HTTP 200; 11 measured driver rankings; scheduled cutoff `2025-12-05T10:30:00+00:00` | Real cached phase rows; field size is phase-specific, not padded |
| Prediction Lab screenshot inspection | Phase, scheduled cutoff, retrospective rankings and publication-time caveat are visible | `data/processed/browser_tests/results/replay-Prediction-Lab-labe-7122e-tes-validation-from-holdout-chromium/prediction-lab-holdout.png` |

Verified environment: Python 3.12.13, pandas 2.3.3, NumPy 2.5.3,
scikit-learn 1.9.1, LightGBM 4.7.0, pytest 9.1.1, Node v22.23.2, npm
10.9.8. The final browser screenshot was inspected after official
classification and eligible-cohort columns were separated.

Artifact SHA-256 values: predictions Parquet
`db7232189404da2f74970d20d1f69d65b082c128252e4b908308651857a79fe1`, summary
CSV `32a742539764fbfc8f5716956c3a06f8c3b07456fbe7cec5a315b7421602eac6`, event
metrics CSV `d93edba4d7be17f99a6d867bd98484b1ecf22fddf4a37c9598a9cacb3dcb6fc4`,
and bootstrap CSV
`e20dfe797190df48b4b408776d4866a60adb4a4a311e4b026eaf73f7017b6286`.

The first real-data run failed because some drivers lacked FP1 measured best
times, causing non-finite FP1 baseline predictions. Those rows are now
excluded from that phase, with separate cohort sizes in the manifest; no pace
is imputed for the measured comparator. Full interpretation and metric tables
are in `QUALIFYING_PHASES.md`.

A subsequent audit removed an unintended FP3-best-time requirement in shared
`prepare_dataset`: eligibility now uses each phase's own measured baseline.
The real experiment was regenerated after that fix. Eligible train/validation/
test rows are FP1 275/325/319, FP2 310/333/351 and pre-Q 311/342/354,
with 16/18/18 events in every phase. The full suite passed with 65 tests in
3.99 s. Implementation commit `8a2c06c898e93f0083058a7abb3bcbd5b3f9b606`
was pushed normally; `git ls-remote origin refs/heads/feat/foundation` returned
that exact SHA.

Phase rankings are relative to the eligible phase cohort: `predicted_rank`
and `actual_rank` are consecutive ranks within the retained drivers. The API
projects raw final classification into a separate `qualifying_position` for
retrospective scoring and omits raw `q1_gap_pct`/`final_position` field names.
The UI labels leader-hit and top-three-overlap metrics as eligible-cohort
metrics. Because phase cohorts differ, their MAEs alone do not establish
improvement as more weekend information arrives; that comparison requires a
shared-cohort analysis. Official classification and eligible rank can differ
when a classified driver lacks the measured practice baseline.

The phase artifact loader now checks per-driver coverage for every model,
rank permutations, manifest cohort counts, event metrics recomputed from
rank predictions, summary reconciliation, and bootstrap point estimates,
event counts and interval-bound validity. Synthetic regressions reject
a removed model row despite a refreshed checksum, an inconsistent summary
despite a refreshed checksum, a future-session feature registry, a source/Q
schedule mismatch and a cohort made too small after target filtering. These
checks validate artifact consistency; they do not prove provider publication
times or prediction calibration.


## 2026-10-16 — geometry, selected trail and browser observation worktree

Starting source SHA `1a5b7b4fa64ae3ceab0ab7cb6957c2331a5ce7b6`.
Final full Python/static verification passed; publication was pending at this earlier checkpoint; the publication proof below records completion. Offline
build, replay/context validators and 11 browser scenarios have passed.

| Check / command | Current evidence | Class / limit |
|---|---|---|
| Focused geometry tests | 13 new plus 5 existing focused tests passed | Synthetic invariants, selection/rejection and existing replay coverage |
| `cd apps/web && npm run test:unit` | 8 passed | Synthetic clock/projection/heading contracts |
| `cd apps/web && npm run build`; `npm run lint` | Passed | Static/build; final combined rerun also passed |
| `.venv/bin/python -m f1_racelab.session.openf1_replay --all --offline` | Three packs rebuilt successfully | Real cached source; no upstream request |
| `cd apps/web && npm run benchmark:replay` | Baseline report completed; no page errors; zero sampled panel mismatch frames in all three sessions | Real cached packs / short local Chromium observation; predates final map/trail source |

Baseline report: `data/processed/browser_benchmarks/replay-performance-2026-10-16T16-32-00-868Z.json`.
Monza/Monaco/Brazil RAF callback interval p95: 33.3/16.8/33.3 ms; request
latency p95 including seeks: 9.02/6.75/16.04 ms. Twelve individual seek
observations range 50.0–163.8 ms input-to-synchronized-DOM. Four-second playback
windows and one run per session do not establish stable release performance.
RAF is scheduling, request timings include proxy/API/browser delivery, decoded
bytes are JSON size and heap is JS heap without forced GC. Final idle fingerprints and observations are recorded below; changed
source/packs prevent causal claims.

Final idle browser artifact:
`data/processed/browser_benchmarks/replay-performance-2026-10-16T16-46-32-467Z.json`,
SHA-256 `2c16efc9ec43e43ed6dcd1b461afa7c1bee527ee09928cd2db89eac218764477`.
Monza/Monaco/Brazil callbacks/s: 59.08/59.54/60.00; interval p95:
16.7/16.8/16.7 ms; local state-request p95: 11.49/8.89/7.05 ms.
All eight panel clocks agreed, no long-task entries; twelve seek observations
range 47.30–171.34 ms. An intermediate 16:45 report overlapped validator
workload; the 16:46 run was idle. These are bounded local development
observations; differing source/features/packs preclude causal speedup claims.

Offline checks: `.venv/bin/python -m f1_racelab.session.openf1_replay --all --offline`;
`.venv/bin/python -m f1_racelab.session.validate_replay --all`;
`.venv/bin/python -m f1_racelab.session.validate_context --all`. Monza/Monaco/
Brazil replay checks pass 4,120/6,149/4,893 cases plus 200 shuffled seeks each;
seek p50/p95 ms are 1.356/3.360, 1.444/3.617 and 1.319/2.962.
Context validation and 360 real source-trail QA probes pass. Browser
`npm run test:e2e`: 11 scenarios passed in 33 seconds.

Final integrated checks (all exit 0): `uv run pytest -q` — 92 passed in
6.87 s, one upstream Starlette/httpx deprecation warning;
`uv run ruff check src/f1_racelab tests` — clean;
`uv run mypy src/f1_racelab/session src/f1_racelab/api.py src/f1_racelab/data/openf1_qualifying.py --ignore-missing-imports`
— 16 source files, no issues. In `apps/web`, `npm run test:unit` — 8 passed;
`npm run build` and `npm run lint` passed. Build JS is 434.63 KB
(142.33 KB gzip), CSS 78.65 KB (15.55 KB gzip). Milestone source commit `132e3aaff34f4c805485e54bbef24f39025aab03` was pushed normally to
`origin/feat/foundation`; `git ls-remote` returned the identical SHA.


### P2 publication proof

Implementation commit `132e3aaff34f4c805485e54bbef24f39025aab03` includes source, tests and all eight
required milestone documents. `git push origin feat/foundation` succeeded;
`git ls-remote origin refs/heads/feat/foundation` returned the same SHA.
Author: Aymen Jedidi; no assistant coauthor. Generated evidence remains local
and ignored; the two unrelated user feature helpers remain untouched.
Next: extend shared-clock telemetry beyond the Monza reference pair.


## 2026-10-16 — multi-session, six-channel telemetry (verified and published)

Starting source `acff2d86ba79ef9dc23c20ac3070d54a989bab8e`. The prior published checkpoint had
92 Python / 8 frontend unit / 11 browser tests; those counts do not certify
this worktree. Final full checks and generated artifact metrics pass as recorded below.
New contract regressions target wrong session/meeting, identical source lap,
missing/incorrect grid coverage, elapsed-time bounds/order and delta identity.
Frontend checks cover continuous versus discrete values, missing values,
channel paths, canonical cursor and the shorter shared-grid tail. Real offline
builds and per-session source hashes/chart artifacts are recorded below. No claim of pit-in-clean Monaco laps is made without pit coverage.

Additional current contract evidence: 16 focused distance-alignment tests pass
and scoped Ruff passes, including eight serialized-contract mutation cases,
two fractional gear/DRS rejection cases and one missing-channel case. The
builder rejects fractional discrete codes instead of silently truncating them
with `int()`. The previous real Monza artifact validates against the stricter
contract. API projection exposes all aligned channels and lap-quality metadata
while omitting the large raw `lap.points` arrays; all three-session builds
and integrated checks pass.

Verified reproduction: `uv run python -m f1_racelab.telemetry.openf1_lap_comparison --all --offline`
completed from cached data; log `data/processed/telemetry_comparisons/catalog_build.log`.
JSON, `.qa.json` and PNG files share basenames under that directory:
`monza-2025_driver_1_lap_50_vs_4_lap_50`,
`monaco-2023_driver_1_lap_40_vs_31_lap_40`,
`brazil-2024_driver_1_lap_52_vs_31_lap_52`.

| Session | JSON bytes | 5 m grid points | Common end m | End-grid B−A s | Maximum source gaps A/B s | Pit source |
|---|---:|---:|---:|---:|---|---|
| Monza | 847,715 | 1,150 | 5,746.06 | −0.234 | 0.799 / 0.799 | Cached, checked |
| Monaco | 547,035 | 656 | 3,279.04 | −0.184 | 0.640 / 0.520 | Unavailable; pit-in unverified |
| Brazil | 669,987 | 849 | 4,241.19 | +0.252 | 0.560 / 0.560 | Cached, checked |

All six channels are nonnull at every aligned grid point for both laps in
these artifacts; null handling remains tested for incomplete future inputs.
Source hashes were checked directly against 4/3/4 raw cached resources
(Monza/Monaco/Brazil). Artifact SHA-256 values:

- Monza: `9bc3aa5ea7750541deff8d10a4f84f8f228e0c5e372f85692e1923821d8dfea6`.
- Monaco: `5ac531b5e3ada9e3c90a3e0e86e27c169283163ab5328904d2b71d47f558b0d5`.
- Brazil: `774191e671021aac0519452d771f9395d68e5ae1a6f4b929ec03b8f0a2c33998`.

Final checks: `uv run pytest -q` — 104 passed in 4.26 s, one upstream
Starlette/httpx warning; `uv run ruff check src/f1_racelab tests` passed.
`uv run mypy src/f1_racelab/telemetry src/f1_racelab/session src/f1_racelab/api.py --ignore-missing-imports`
passed, 20 source files. In `apps/web`, `npm run test:unit` — 13 passed (after review correction);
`npm run build` and `npm run lint` passed. Build JS 452.63 KB (148.05 KB gzip),
CSS 79.61 KB (15.71 KB gzip). `npm run test:e2e` — 14 passed in 39.2 s,
including exact six-channel cursor assertions for all three races and mobile;
Monaco/Brazil PNG plots and mobile panel screenshot were visually inspected. Source milestone `5bce32930dfaa802c6ec1c7a54e1a0f7ffce0cf9` was pushed;
corrective review publication is pending.


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

## 2026-10-29 — walk-forward ML, quality audit, client hardening, layout

Classification: **real** data for metrics, **synthetic** fixtures for unit tests.
* `uv run pytest -q` — 184 passed (167 before; +17: 5 walk-forward, 6 quality, 3 client, 3 lab/API).
* `uv run python -m f1_racelab.models.qualifying_walkforward` — real, 36 evaluated events, numbers in `ML_WALKFORWARD.md`.
* `uv run python -m f1_racelab.data.quality` — real, 1,418 rows / 71 weekends: 0 errors, 37 warnings.
* `cd apps/web && npx tsc -b` clean; `npm run test:unit` 16 passed; `npm run build` ok;
  `npx playwright test` **15 passed** (44 s). Two scenarios (`mobile keeps…`, `monaco-2023 six…`)
  also failed on the untouched baseline (topbar overflow) and now pass.
* `npm run lint`: 3 errors + 1 warning in `StrategyLab`, `WhatIfLab`, `use-live-session`;
  identical with this work stashed (pre-existing, not fixed here).

## 2026-10-29 (2) — pipeline, timeline, 2026 extension

* `uv run pytest -q` — 191 passed (+7: pipeline 2, timeline 3, walk-forward 2).
* `uv run python -m f1_racelab.data.pipeline --offline` (scratch dir) — real; dataset SHA identical to the committed-era dataset.
* `uv run python -m f1_racelab.data.pipeline --years 2023 2024 2025 2026` — real live sync; manifest `data/processed/pipeline_manifest_2023_2024_2025_2026.json`.
* Walk-forward re-run on 48 events — real; 2026 result is negative, see `ML_WALKFORWARD.md`.
* `npx tsc -b`, `npm run lint` (clean, was 3 errors), `npm run test:unit` 16 pass,
  `npx playwright test` **16 passed** (new: race-history chart seeks the shared clock).
