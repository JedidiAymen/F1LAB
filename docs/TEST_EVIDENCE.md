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
