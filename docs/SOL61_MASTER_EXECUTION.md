# F1LAB — MASTER EXECUTION MANDATE FOR SOL 6.1 CLI

**Status:** AUTHORITATIVE HANDOFF BRIEF FOR THE IMPLEMENTING AGENT<br>
**Prepared:** 2026-10-15<br>
**Project:** F1LAB / F1 RaceLab — Formula 1 engineering, ML, replay, analytics and strategy workstation<br>
**Repository:** https://github.com/JedidiAymen/F1LAB<br>
**User working directory (Arch Linux):** `~/Documents/projects/F1LAB`<br>
**Working branch at last inspection:** `feat/foundation`<br>
**Audience:** Sol 6.1 CLI operating as principal F1 data/ML scientist, simulation researcher, staff software engineer, frontend visualization engineer, quality lead, and technical documentation author.

> **MANDATE:** Take ownership of the implementation workflow end-to-end. Inspect the actual code and working tree first, build and validate coherent vertical slices, run experiments on real data wherever access permits, commit/push safe verified checkpoints, and DOCUMENT YOUR WORK SO PRECISELY that a second assistant (ChatGPT) can later reconstruct what you did and teach the user every technical concept in detail. Do not merely write a plan. Implement it. Do not equate a passing import, a pretty screenshot, or synthetic tests with scientific validation.

---

## 0. Your immediate first action, operating contract and authority

Read this entire file before acting, then inspect the repository, existing docs, git status/log, installed tools and actual dependencies. Do not overwrite existing uncommitted work or assume that files described in this brief have already been installed. Use the actual repository as the source of truth for current code; this document is the source of truth for product intent and constraints. Make a short action plan, then **proceed autonomously** through the feasible stages without asking the user to perform routine terminal work. Ask only for truly external prerequisites such as an unavailable account credential, paid API authorization, destructive operation approval, or a decision that changes a locked product constraint.

**Permissions and safeguards:**
- Work in the existing repo, preserve its history, do not reinitialize it, do not delete user's files or rewrite unrelated features. No `git reset --hard`, force push, broad `rm -rf`, or history rewriting. Never commit `.env`, API tokens, account identifiers, secrets, downloaded copyrighted audio, gigantic caches, or generated environments.
- You may run normal installs, migrations for disposable local dev databases, tests, local experiments, Git commits and regular pushes to the feature branch after checking status and verifying tests. Do NOT merge to main, modify production credentials, pay for APIs, or deploy a paid production service without explicit authorization.
- Favor locally reproducible, CPU-first solutions. Parallelize safe independent inspections/tests, but do not saturate the user's Arch Linux machine or fire high-volume provider requests. Throttle upstream calls, add caching, make downloads resumable and respect terms of service.
- If a prerequisite or provider is unavailable, record exact cause and implement the best honest fallback/fixture; never invent measurements, results, confidence or capabilities.
- “All the work” means write code, tests, notebooks, docs, and integrated demonstrations, not just instructions. Retain proof of execution, not claims.
- Perform one coherent milestone at a time and maintain an up-to-date checklist. Continue to the next milestone automatically once quality gates pass. Do not get trapped endlessly polishing a notebook or UI at the expense of functionality.

**Initial commands to run and record:**
```bash
cd ~/Documents/projects/F1LAB
pwd && git remote -v && git branch --show-current
git status --short && git log -8 --oneline
find . -maxdepth 3 -type f -not -path './.venv/*' -not -path './references/*' | sort | head -200
uv --version && uv sync --dev
uv run pytest -q
```
Check Node/pnpm package-manager choices actually in the repo before invoking frontend commands. Record versions, exit codes, failure logs, and fixes. If source docs, cached data, the Sprint 3 ZIP, or local-only changes already exist, reconcile rather than overwrite.

---

## 1. What we are building — the LOCKED product vision

**F1LAB is a serious integrated Formula 1 race-intelligence and engineering workstation, not a generic statistics dashboard, one-off notebook, Streamlit demo, or simple “AI predicts winner” toy.**

The north-star experience: choose a Grand Prix/session, reconstruct it faithfully; watch all cars move on an accurate circuit in synchronized 2D (later 3D), inspect timing/tyres/flags/weather/radio and full telemetry, compare drivers and laps, examine what ML predicted and why, ask a race-strategy engine what a driver should do, and fork the past into a counterfactual future with uncertainty-aware outcome comparisons. The **same canonical session/race state** must drive replay, live, simulation, analysis and UI. It is one product and one coherent temporal model.

### Locked capability inventory (full scope, not a promise every item is in the first release)

1. **Race Control / Session Player:** historical race/qualifying/practice/sprint sessions where source coverage permits; replay, pause, seek, rewind, event jumps, speed changes (e.g. 0.25x–16x); position/timing tower, gaps, intervals, lap state, sectors, last/best lap, flags, race-control events, weather, tyre compound/life, stints, pit stops, retirements; stable same-session clock.
2. **Live race intelligence:** a server-side single upstream ingest per session and WebSocket fan-out to viewers; reconnect/deduplicate, snapshot + deltas, lag/backpressure/quality monitoring; replay and live share renderers and domain contracts. Live availability may be restricted by provider subscription: no unsupported claims of real-time access.
3. **2D animated circuit:** accurate circuit geometry, car dots/driver abbreviations/colors, heading/position and selected trail, laps, pit lane where possible, smoothing/interpolation driven by timestamps, sensible handling of dropped/batched position samples. Do not depict cars moving at fake uniform speed.
4. **3D circuit + cars:** optional synchronized Three.js/React Three Fiber viewer built on the **same** CircuitGeometry and RaceState; spline/ribbon track geometry, camera top/follow/free modes, car heading/velocity, clean scene performance; use licensed original/procedural models rather than appropriating F1/trademarked car assets. 2D correctness precedes 3D.
5. **Full telemetry and comparisons:** speed, throttle, brake, RPM, gear, DRS, position/distance, delta time, speed trace, sector/mini-sector data, shared cursor, synchronized map marker and selected-lap chart crosshair; compare two+ drivers/laps and across events/years. **Distance-align** lap telemetry so the same physical track point is compared, not blindly same timestamp.
6. **Tyre/strategy/event analysis:** stints, degradation, pit time, undercut/overcut, clean air vs traffic, rival response, SC/VSC and weather effects; historic vs recommended decisions.
7. **Radio + context:** show **available** radio clips on timeline with relevant concurrent gaps, flags, tyres and incidents; optional transcript/intent classification only with legal access and appropriate quality. Never promise full radio coverage or silently redistribute protected media.
8. **Prediction Lab:** qualifying pace/ranking and predicted grid (separate penalty adjustment step), pre-/in-race finishing-position probabilities, win/podium/points/DNF probabilities with evaluation, calibration, driver-vs-team pace and explanations. Prediction snapshots as weekend information improves.
9. **Strategy Lab:** physics-informed/empirical race simulator with lap/stint, fuel, tyres, pit entry/stop/exit, traffic/overtake, rivals, race flags/weather; optimize compound/pit lap/stint sequence; Monte Carlo race futures; configurable goals (race time, expected points, podium/win probabilities, risk). Re-optimize at decision points, with scenario and model version provenance.
10. **What-if / counterfactual:** fork an actual replay at a chosen event/lap, modify pit lap/compound/SC/weather/opponent policy, simulate alternate futures, display actual-vs-predicted state/outcomes. Simulated state is unmistakably labeled, never mixed into historical truth.
11. **Comparison Studio / History / Research:** season → GP → session navigation; same driver between seasons, race-vs-race/same circuit across years, ghost laps, reproducible notebook/export, model runs/metrics, actual vs simulated timing.
12. **Professional desktop-first F1 UX:** dense pit-wall engineering workstation, not giant SaaS cards. Dark/carbon-like base, restrained race-red action accent, readable tabular numerals, semantic tyre/flag/team colors, precise state labels, fast keyboard controls, responsive degradation. Strong visual hierarchy, circuit as anchor, docked/resizable panels where justified, no broken transparent selectors, no hardcoded fake demo numbers without a visible DEMO badge.

**NON-GOAL:** Do not introduce Kubernetes, Kafka, Feast, distributed training, Kafka/Flink/Redis/MLflow solely for fashion. Do not replace existing React/Vite or FastAPI/Python stack without a measured, documented reason. Do not use copyrighted official F1 broadcast graphics as UI assets.

---

## 2. The story so far — decisions and discoveries to preserve

This work began as an investigation of how to build a coherent F1 ML/software platform while *understanding* technologies instead of blindly cloning GitHub. The user prefers small, precise conceptual explanations and examples as they learn, but now explicitly delegates implementation to you. They will later ask ChatGPT to explain **every line of reasoning at the architectural/technical level, every file/function/data field, tests, outputs, charts, surprises and limitations**. Therefore, document rationale and evidence in depth. Do not expose private chain-of-thought; produce professional engineering explanations, proofs and decision records.

### Existing foundation (verify locally rather than blindly assuming)
- Repo `JedidiAymen/F1LAB`, active development branch `feat/foundation`, Arch Linux directory `~/Documents/projects/F1LAB`.
- Python >=3.12, managed with `uv`; `src/f1_racelab` is the current actual Python package name (do **not** accidentally invent `f1lab` import paths). Dependencies include FastF1, pandas, Polars, NumPy, SciPy, PyArrow, scikit-learn, XGBoost, LightGBM, SQLAlchemy, Alembic, Pydantic, FastAPI, psycopg, rich, tests, Jupyter/ipykernel/matplotlib.
- Frontend: `apps/web` React 19/Vite 8/TypeScript/Tailwind 4 with shadcn/Base UI primitives; inspect exact present package versions rather than claiming the current UI is finished.
- Existing scaffolds include `apps/api`, `services/ingest`, `services/session-engine`, `packages/circuit`, `packages/schemas`, `packages/telemetry`, `ml/features`, `ml/training`, `ml/evaluation`, `tests`, `infra`, `docs`.
- Planned development infrastructure: PostgreSQL 17, MinIO/S3-compatible object storage, Docker Compose; SQLAlchemy/Alembic owns DB schema; no Drizzle duplicate ownership. Historical snapshots/data cached under `data/`, not committed.
- Existing docs `docs/REFERENCE_REPOS.md`, `docs/ML_QUALIFYING_SPRINT2.md`; do not erase them. The repo docs are part of the project's history.

### Source-level findings from earlier investigation
**i-ares/open-f1 (F1 Terminal):** high-rate compact replay can use binary column-oriented/ArrayBuffer chunks and lower-rate JSON events; indexed timestamps + binary search for seek, prefetch/LRU, session-wide `requestAnimationFrame` clock; car position interpolation (including velocity-guided handling of batched GPS), stable Canvas/Path2D circuit layer with dynamic car marks, React state updates at sensible rate. Live SignalR/backend source ingest with WebSocket fan-out. REFERENCE/ADAPT, not wholesale UI copy.

**MatthewDelong/F1-Telemetry:** track builder smooths X/Y position traces, Catmull–Rom spline / ~1500 samples, computes normals/ribbon/triangles for track width, sectors/kerbs and optional scenery; 3D rendering via Three.js / React Three Fiber, GLTF models, camera modes. Historical code may have heuristic curvature “speed heatmap”; do NOT present heuristic as measured actual speed. Avoid using a tween-queue as the authoritative simulation clock. REFERENCE/ADAPT. Check separate code vs visual asset licensing.

**TUMFTM/race-simulation:** academic lap-discretized multi-car simulator; basic and advanced models, driver/car/fuel/tyre terms, SC/VSC and a ghost safety-car timing model, traffic/overtake thresholds rather than full aerodynamics, pit entry/standstill/exit, random lap/pit events, MC and RL strategy agent. Base lap: reference pace + driver + car + fuel-mass sensitivity + tyre model + variation/DRS, then race effects. Important to preserve `T_free` vs `T_realized`, distinguishing traffic loss. In `helper_funcs/src/calc_tire_degradation.py`, inspect/reconfirm a suspected cubic multi-lap coefficient inconsistency before porting; old TF/Python stack should not be installed wholesale. License LGPL-3.0; porting actual code requires legal compliance. Use conceptual lessons and independent tested implementation.

**j5t3313/f1-strategy-simulator:** Bayesian tyre degradation + Streamlit proof-of-concept; investigation identified stubbed `load_real_f1_data` and `build_bayesian_tire_model` in an app path, therefore **not** a validated end-to-end training pipeline. Useful for uncertainty concept only.

**eddmann/f1-picks-2025-predictor:** rich historical/practice feature modules (FP1–FP3 rank/gap, sectors, tyre life, Q1–Q3 history, practice→quali conversion, driver/team ELO, form), `shift(1)` temporal safeguards; LightGBM LambdaRank grouped by event. Prior review suggested complex ML can lose to simple FP3 baseline; VERIFY metric definitions and report independently rather than copying a reported score.

**Adhithiyaram13/F1-Predictor:** rolling form/EWM, team/driver separation and probabilistic re-ranking ideas; use as benchmark/reference.

**gcckd01/F1-QUALI-PREDICTOR:** tiny tutorial with FP3 gap + crude `Is_Top_Team` binary feature and GradientBoostingRegressor; use as lower baseline, NOT scientific gold standard.

**siddoboi/f1-telemetry-dashboard (PIT WALL):** telemetry normalized to a uniform distance grid, synced lap comparisons, anomaly/rule-based physics inspection. Prefer reproducible distance alignment first, anomaly ML later.

Other investigated roles: LoreMonti/F1-strategy-engine (strategy/MC), ArsalanKaleem/F1-Vision (UX), 4f4d/f1radio (radio context), nina-coder/f1-predictions (driver/car split and probabilistic baseline), manasscodes/f1-race-intelligence (XGBoost/SHAP), F1 Race Replay repos, Jolpica, OpenF1, FastF1. All references are **not** automatically installable dependencies.

### Actual ML work already present or previously handed off
1. Historical Monza 2025 FP3 exploration loaded and cleaned laps; critical finding: **non-deleted, non-pit laps are not necessarily representative push laps**. `pick_quicklaps()` default ≈107% is too broad for certain purposes. A per-driver within-3%-of-best V1 heuristic was implemented in `src/f1_racelab/features/qualifying.py`; this is a heuristic, not ground-truth push-lap classification.
2. Monza 2025 Notebook 01, `notebooks/01_qualifying_weekend.ipynb`, feature builder and `fastf1_source.py` are committed. In a saved run: ~20 driver rows, ~43 columns, simple FP3 vs actual final qualifying baseline MAE **2.70 positions** and Spearman **0.823** for that *single* weekend; these are not model-generalization results. Baseline FP3 order included NOR/LEC/PIA/VER, but actual qualifying pole VER — important example of practice vs qualifying mismatch.
3. Sprint 2 is committed in remote `feat/foundation` as of inspection 2026-10-15 (tree SHA `bb840d44a2cf6c2f325f6ef2a575ff074f0d1b05` at inspection): `src/f1_racelab/data/qualifying_dataset.py`, `src/f1_racelab/models/qualifying_backtest.py`, `notebooks/02_qualifying_backtest.ipynb`, `tests/test_qualifying_backtest.py`, docs. It enumerates **conventional** 2022–2025 weekends (Sprint FP3 availability differs), caches event Parquet, creates ingestion report; Ridge and LightGBM predict *Q1 relative pace proxy*, rank within each GP against final qualifying position; select by 2024 validation, evaluate 2025 held-out; FP3 baseline is comparator; guard tiny smoke dataset. This workflow was offline-tested synthetically, NOT claimed to have produced genuine multi-season performance numbers.
4. A separately supplied Sprint 3 archive may exist locally: `F1LAB_SPRINT3_NEOVIM_HISTORICAL_FORM.zip`. **It was NOT in the checked remote branch** at the 2026-10-15 snapshot. Do not assume installed. Inspect if available, extract to a temp directory, exclude `__pycache__`/`.pyc` junk, review and adapt safely rather than blindly overlaying. Intended files include `historical_qualifying.py`, `qualifying_ablation.py`, `enrich_team_metadata.py`, Notebook 03, Neovim/Jupytext instructions, offline tests. If unavailable, independently implement equivalent tested components. Do not claim Sprint 3 has passed real-data backtesting without outputs.

**Educational ML story**: We established why predicting continuous normalized qualifying pace + sorting/phase simulation is often more useful than independent multiclass P1–P20 predictions; Q1 pace is a useful first target but **not** the same as final qualifying pace/classification; Q1/Q2/Q3 progression and changing track conditions matter. Models get information available at a precise pre-qualifying cutoff (practice, past qualifying, forecast as-of that time), never same-session Q1/Q2/Q3 features. Event/time-grouped train/validation/test, shifted historical features, simple baselines, calibration, missingness and 2026 regulation-era shift are nonnegotiable.

---

## 3. First priority: close the real ML experiment loop (IMMEDIATE WORK)

Even though full product scope is large, start with an executable scientific vertical slice, because Sprint 2 is already present. Move efficiently: implement, test, run, analyze, document, then proceed to the core session/replay architecture in parallel only when a validated ML checkpoint exists.

### M1 — audit environment, reconcile work
- Inspect `git status`, recent commits, actual `pyproject.toml`, notebook execution outputs, Sprint 2 source/tests/docs, and any uncommitted/Sprint 3 local files.
- Run `uv sync --dev`, pytest, Ruff/typecheck where configured; fix broken imports, stale dataset locations and incompatible dependencies. Check FastF1 cache path and package script entrypoints.
- Check whether the full 2022–2025 dataset has actually been ingested (`data/processed/...`), and whether validation/test CSVs exist. Do NOT infer existence from GitHub because data is intentionally ignored.
- Make portable requirements/README commands; remove tracked `.ipynb_checkpoints` and notebook huge outputs *only with clean, explicit git changes*. Add appropriate `.gitignore` entries for checkpoints, notebook executables and cache; preserve notebook source.

### M2 — multi-weekend ingestion with evidence
- Run `uv run python -m f1_racelab.data.qualifying_dataset --years 2022 2023 2024 2025`; monitor provider policies, provider failures, rate limiting; cache and resume. First smoke-test one/two events with proper marker; never evaluate scientific performance on smoke size.
- Validate session format and **schedule chronology**, identify actual complete sessions, missing FP1/2/3, cancelled sessions, grid penalties, results source quality, changed driver IDs, disappearing entries, deleted/inaccurate laps and pit/in/out laps.
- Produce per-year coverage counts and drop reasons; ensure 2025 test set is complete enough. Record exact counts (events/drivers/laps/features and errors) and source versions, not approximate or invented values.
- Distinguish `qualifying_position`, `starting_grid_position`, `Q1_gap_pct`, `Q2_gap_pct`, `Q3_gap_pct`. Qualifying vs starting grid differ due to penalties/DSQ/etc.
- Preserve raw and processed lineage. Do not commit entire raw FastF1 cache or potentially restricted datasets. Use versioned processing/config manifest and a local reproducible rerun path.

### M3 — baseline backtest, reproducible artifacts
- Run official Sprint 2 backtest with 2022–23 training, 2024 validation and 2025 held-out test. Report event-weighted MAE, Spearman, pole-hit, top-3 overlap, coverage; include bootstrap confidence intervals over **events** where feasible. **No target columns in features.**
- Verify actual stored test results, not synthetic data. For issues, fix systematically and regenerate affected cached weekends; never hide failed events by silently dropping them without coverage report.
- Evaluate FP3 and stronger simple baselines (recent qualifying score, team median, simple weighted FP3 + history) before complex model claims.
- Error analysis by event, circuit type and driver; plots and tables in Notebook 02. Use a true final holdout, avoid repeated hyperparameter changes based on 2025.

### M4 — Sprint 3 feature ablation + Neovim notebook workflow
- Implement or safely integrate the separately delivered Sprint 3 source if it exists: past 3/5 driver Q1 performance (normalized), teammate-relative performance, team-relative performance, rolling Q3/front-row/pole rates, historical FP3→Q conversion, recency/EWM when justified.
- `shift(1)`/as-of joins are **per driver/team and chronological**, correctly reset across teams when intended; do not leak the same session's qualifying target to any current feature. A current event may have FP1/FP2/FP3, but **not any current Q**.
- Check teammate mapping by event and constructors, substitutions/sprint format, and that missing features are represented honestly (not filled with arbitrary zero). Audit one high-risk feature manually by printing its upstream contributing rows.
- Ablation: practice-only Ridge/LightGBM vs historical-form Ridge/LightGBM plus FP3 baseline. Same event splits, same evaluation, controls for sample selection. Record deltas + uncertainty and retain only groups with repeatable benefit.
- Jupyter files for visualization and `# %%` **Jupytext** pairs for Neovim editing; Molten optional, not mandatory and do not overwrite user's Neovim config. Use kernel registration and reproducible launches. Kaggle optional for hosted heavy experiments; local is preferred for this tabular workload. Keep all reusable logic in `src/f1_racelab`, not notebook-only magic. Generate/edit notebooks programmatically only when it improves reproducibility; run notebooks with tests or nbclient and clear/freeze outputs responsibly.

### M5 — production-ish ML baseline / probability and model audit
- Compare simple regression, Ridge, LightGBM/XGBoost; evaluate optional group-aware LambdaRank only against genuine gains, with proper group labels/relevance ordering (higher-is-better relevance conversion).
- Create a **well-defined prediction timestamp** for pre-weekend, after FP1, after FP2 and immediately pre-Q; each snapshot has legal features as of that time. Track feature `available_at`, provenance, coverage and imputation.
- Introduce residual/quantile/ensemble uncertainty only after point predictions; calibrate resulting P(pole), P(top3) or Q3 where ground truth exists, evaluate probability scores (Brier/log loss/reliability), no fake percentages.
- Develop walk-forward evaluation for 2026, explicitly respecting regulation changes; do not use unseen future rounds in historic features. Underlying distribution shift requires caution.
- Version datasets, models, seeds and hyperparameters; output experiment manifest, metrics, confusion/rank charts, feature-importance with limitations (permutation/SHAP if warranted), and exact reproduction commands.

**M1–M5 acceptance gate**: fully rerunnable ingestion, legal feature schema, held-out result CSVs, tests, notebook charts and detailed `ML_EVALUATION.md`. Once met, proceed with the unified race architecture rather than endlessly adding features.

---

## 4. The CORE architectural lock — RaceSource → ordered events → one RaceState

The central contract is **one canonical time-dependent state** for replay, live, and simulation, NOT three unrelated UI data formats.

```text
FastF1 / OpenF1 / Jolpica / weather / archived packs
            │ provider adapters + source provenance
            ▼
       Raw snapshots + normalized domain objects
            ▼
 Ordered SessionEvents + immutable/versioned checkpoints
            ▼
        RaceSource interface (mode-independent)
        ├── ReplaySource
        ├── LiveSource
        └── SimulationSource
            ▼
       Session clock / time-indexed reducer
            ▼
         RaceState(t) + quality/capabilities
            │
  ┌─────────┼───────────┬──────────┬──────────────┐
  ▼         ▼           ▼          ▼              ▼
 2D map   3D map      timing     telemetry     strategy/ML
```

Define a precise, typed interface (Python Pydantic + generated/validated TypeScript schemas, or JSON Schema), including:
- `SessionId`, `DriverId`, canonical mapping to provider IDs, stable event/clock IDs, track/circuit layout/era IDs.
- `SessionEvent`: type, event ID, source, observed_at/source timestamp, session-relative time, applicable lap, payload, ingest timestamp, sequence/order, data quality, interpolation/estimated marker.
- `RaceState`: session metadata, session time, lap/progress, flags, drivers, live gaps/race times/positions, stints, tyre ages, pit status, weather, race control, radio refs, model predictions, source confidence and event log; UI consumes these only via contracts.
- `CircuitGeometry`: normalized centerline/polyline/spline, transforms, lap distance, coordinate system, optional width, corners, sectors, pit lane, start line, geometry artifact version.
- `ReplayPack`: version/schema/source hashes, event timeline (JSON/small events + compact binary high-frequency frames/Parquet), snapshots/checkpoints, canonical geometry, capability and provenance manifest.
- `SimulationBranch`: parent session/timestamp, fork action sequence, random seed/world ID, model versions, objective, generated events and outcomes; original events never modified.

**Clock invariants:** one authoritative session time for all panels; pause means pause all; seek deterministically reproduces state; playback speeds change time advancement not data semantics; live data timestamps may be late/out of order; position interpolation smooths between measured samples but must never fabricate official lap times; no stale per-widget clocks.

**Event correctness:** deterministic `reduce(state,event) → next_state` for replay/simulation, test ordering around pit stops, SC/VSC, retirements, lead changes, lap crossing; idempotent events and checkpointed seek; track source/time/quality. A frontend requestAnimationFrame is a **renderer ticker**, not the authoritative race-time source. React high-frequency car positions should update in Canvas/WebGL mutable draw state rather than forcing whole-tree re-render 60–144 times/sec.

**Interpolation constraints:** do not label approximate OpenF1 GPS as centimeter-accurate; use sample timestamps, interpolation and gap confidence; handle batched/coarse updates, missing frames, pit lane path, start/finish wrap, short backwards jumps without teleporting; use measured position when available, estimated position visually differentiated.

**Storage contracts:** PostgreSQL for relational metadata and run ledgers, MinIO/S3 for raw/replay/model/large datasets, Parquet/Arrow for analytics; SQLAlchemy/Alembic on Python backend. Keep provider adapters isolated. Avoid duplicate schemas or duplicate ORM. Build versioned migrations and artifact checksum/source lineage.

---

## 5. End-to-end platform build roadmap (continue after ML checkpoint)

Each phase has implementation output, proof and a gate. You can implement in a better dependency order if you record the reason in an ADR; you must preserve the capabilities and architectural constraints.

### P0 — repository hardening and documented contracts
- Standardize actual monorepo ownership (do not make duplicate packages merely to satisfy an imagined diagram). Implement lint/type/unit test scripts, CI, safe env templates and Docker Compose developer bootstrap; preserve existing React/Vite, FastAPI and Python `uv` settings.
- Create `docs/ARCHITECTURE.md`, `docs/DATA_CONTRACTS.md`, `docs/ML_EVALUATION.md`, `docs/STRATEGY_MODEL.md`, `docs/VISUAL_PIPELINE.md`, reference-license matrix, `docs/ROADMAP.md` and `docs/adr/`. Schemas and temporal contract before wide ingestion.
- Choose three golden historical fixtures **by checking actual coverage**: clean dry event, SC/VSC-heavy event, mixed-weather event. Preserve limited sample fixtures lawfully; store local fixture manifest and expected events, not huge tracked data.
- Gate: one documented session can be reconstructed from source with stable IDs/timestamps, schema tests pass, one clean `uv` bootstrap command and frontend build/test.

### P1 — data sources and replay pack
- FastF1 adapter for historical timing, laps, sector, telemetry and weather, OpenF1 adapter for eligible recent/live GPS/telemetry/race-control/radio, Jolpica for historical results/metadata as needed. Verify current API pricing/rate limits and licenses; add capability detection and retries.
- Raw snapshots, normalized event ETL, circuit geometry extraction, provenance and QA coverage report. Build per-session replay pack with timestamps, checkpoints, prefetch/index. Avoid reloading all raw upstream data on every user play.
- Gate: reproduce three reference sessions offline; replay seek yields same state when approached from forward playback or arbitrary jump; reconciled lap/order/events.

### P2 — Race Control 2D usable vertical slice
- Functional session picker/history browser and one integrated workspace: 2D circuit + smooth moving cars + timing tower + replay seek + speed control + event timeline + tyre/stint bar + weather/race control where available. Need genuine real session evidence, not static fake animations.
- Modern visually credible dark pit-wall UI. Responsive panel layout, accurate time synchronization, good accessibility/keyboard navigation, data missing states, source-quality indicators; shadcn components restyled with consistent palette, no transparent drop-down bugs or dead controls.
- Gate: user selects supported historical GP and uses play/pause/seek while multiple widgets and displayed car positions remain coherent, with reproducible automated UI test and manual demo instructions.

### P3 — full telemetry and distance-aligned Comparison Studio
- Speed/throttle/brake/gear/RPM/DRS charts aligned to selected driver and player clock. Lap-vs-lap by distance, uniform distance-grid normalization (e.g., 5m where appropriate), interpolation/derivative unit checks, delta-time integration with explicit quality bounds, sector/corner bands, shared crosshair and circuit cursor, ghost laps and teammate comparisons.
- Comparisons across years/track layouts should require compatible layouts or explicit distance normalization; do not pretend incomparable layouts are direct equivalents.
- Gate: overlay two measured clean laps and inspect actual sectors, breaking/throttle points, cumulative delta, synced car marker; numerical tests for monotonic distance/track length and chart/timestamp sync.

### P4 — prediction integration
- Wire validated qualitative/quantitative baseline results into Prediction Lab. Provide experiment selector/model versions, as-of time, feature availability, data coverage, prediction vs actual; Q1 and final classification explicitly separate. Eventually qualifying phase model, grid-penalty adjustment, race-result distribution.
- If a model is weak, show the honest FP3 baseline instead of marketing an inaccurate "AI". Preserve holdout. Simulation/probability charts only if calibrated/validated.
- Gate: one pre-qualifying prediction reproducible from source as-of snapshot, historical backtest link, explanation for why the model predicted it, errors visible.

### P5 — physics-informed race simulator and strategy v1
- Define deterministic car state/lap transition: pace baseline + driver/car + estimated fuel + tyre compound/age/warm-up + weather/track effects + driver variance; then SC/VSC timing, traffic/overtaking/duels, pit entry/standstill/exit and fuel/tyre ageing. **Track `free_pace` versus `realized_pace`** and lap-by-lap state chronology.
- Start with tested two-car 8–10 lap undercut example, then full-grid and 3 representative golden races. Pit in/out timing and SC pit relative loss depend on circuit and flag state; handle minimum stint constraints, available tyre sets, compound rules and special events with explicit approximations.
- Strategy action space: stay, pit Soft/Medium/Hard (and inter/wet where appropriate), multiple stops, compare deterministic and probabilistic projections; objective expected points/race time/podium/win/risk. Model traffic as empirically/heuristically, not pretend CFD dirty air.
- Monte Carlo uncertainty sampled at appropriate levels: per-lap noise, per-pit tails, per-stint tyre coefficients, race-world flags/weather/opponent pace; share common random worlds across candidate strategies where valid. Seeded reproducibility. Run N only within resource budgets; vectorize/parallelize after profiling.
- CALIBRATE and backtest against historical races; show distributions, uncertainty bands, simulation assumptions and limitations. RL research only when conventional optimizer/simulator is trustworthy.
- Gate: deterministic tests, stable seeded MC, strategy A vs B comparison, documented model parameters/units, at least one real-event sanity check, no false claims of validated race-winning strategies.

### P6 — what-if branching
- Fork replay at selected state, scenario builder: pit one lap earlier, change compound, inject/remove SC/weather perturbation, choose rival policy. Rerun strategies under common random worlds, compare observed timeline with simulated distributions, preserve provenance/branch seed/version.
- Gate: fork a real historical pit decision, results reproducible; UI clearly identifies measured vs simulated segments and scenario assumptions.

### P7 — live architecture and coverage-aware radio
- Only after replay stable. Implement backend single-ingest, reconnect/resume, dedup, bounded WebSocket fan-out, snapshot/delta state, source-lag metrics and fallback to last good snapshot. Honor OpenF1/provider live licensing/subscription requirements; if unavailable, run true playback-through-live-adapter test using cached feed with visible SIMULATED LIVE badge.
- Radio timeline with availability flags, legal link/clip handling, contextualized RaceState; do not store/rehost unlicensed content. Optional transcript classification as research with explicit confidence.
- Gate: two viewers observe one upstream ingest with consistent race clock, reconnect works, missing radio does not break UI.

### P8 — 3D circuit and advanced research
- Implement shared geometry pipeline with track normalization/heading spline and separate 3D renderer (Three.js/React Three Fiber), proper moving car models where asset license permits, orbit/top/follow cameras, LOD/performance. Same RaceState and clock, no 3D-specific fork of session logic.
- Optional: probabilistic opponent behavior/SC/rain, telemetry anomaly detection (physics rules before Isolation Forest), model vs reality timeline, strategy regret map, race DNA, championship mode, notebook exports; only with traceable tests and incremental gates.

**Recommended practical order:** finish the existing ML benchmark and historical-form ablation quickly; in parallel, design and implement the canonical data/clock foundation; deliver a real, impressive 2D historical replay UI; then telemetry comparison, strategy integration, live and 3D. The original blueprints sometimes prioritized replay before ML, but **the repository now contains ML code**; preserve this investment while enforcing the unified architecture. Both tracks must converge on RaceState/SessionEvent rather than becoming two apps.

---

## 6. Exact professional engineering standards

### Research/reuse
For every cited third-party repo, record **exact URL + commit/tag, license, files/functions examined, tested behavior, relevance, limitations, code reused vs idea independently implemented, attribution if required**. Do not claim upstream code was adopted without a diff/trace. Observe LGPL/MIT/asset-specific obligations. Check current versions and APIs instead of repeating old unsupported assumptions.

### Data science
- Every data row needs `(season, round/event ID, session, driver ID, provider version, available_at)` or a documented equivalent. No mixing different sessions/season-era definitions silently.
- For qualifying, legal pre-Q features: current FP1–FP3 where available + prior-session qualifying/race history + as-of environmental forecasts. Illegal: current Q1/Q2/Q3/final classification, future full-season averages, later realized weather, starting grid after penalties, post-race race results.
- All rolling features: chronological order, shift before rolling and per-driver/team/exposure semantics. No random row split across same GP; all drivers of same GP stay in same partition. Fit imputers/scalers only on train.
- Distinguish lap legal validity, timing accuracy, representative push lap, Soft-only pace, fuel unknown, wind/tow/track evolution, missing tyre info. Report filtering/removal counts and threshold sensitivity. Don't pretend 3% of best lap is ground truth.
- `Q1_relative_pace` is not the same as final Q classification; compare alternate target formulations. Validate final ranking separately, avoid comparing normalized time measured under changed track conditions as if identical.
- Store datasets as Parquet with schema+code+source provenance; don't train on fake/synthetic fixtures for published performance. Validated charts have clearly named training/validation/test windows and sample sizes.
- For confidence probabilities, use calibrated uncertainty. Monte Carlo probabilities conditional on model assumptions are not generic "AI confidence"; report calibration and sensitivity.
- For 2026 regulatory reset, evaluate separately via walk-forward, not indiscriminately merge eras; verify up-to-date driver/team mapping and schedule formats.

### Simulation
- Units explicit everywhere (seconds, m, km/h, fuel kg, ages in racing/equivalent laps, distances). State transitions tested for off-by-one in age/burn. Pit on finish line, lap wrap and FCY fractional laps explicit.
- Observed timing is authoritative; simulated time is modeled; interpolated position is estimated. No spurious negative fuel, impossible overtake teleportation or illegal pit/tyre sequence without marked assumptions.
- Reproducible RNG with scenario ID; common random numbers for shared independent uncertainties when comparing strategy branches, but trajectory-dependent traffic/attacks remain branch-dependent.

### Backend / frontend
- Typed REST and WS contracts, schema validation, unit/integration tests, health checks, graceful null/unknown values, browser disconnect handling, timestamp timezone/clock basis, efficient redraw, reproducible golden replay and Playwright if configured.
- No premature library overload; profile before optimizing binary/compression format, WebGPU or workers. Always test seeks, pauses, variable speeds and cross-panel clock synchronization.
- UI ships with real data and source-quality context; add tooltips, loading/empty/error states and meaningful labels. Avoid giant dashboard cards, random palettes or non-functional controls.

### Testing and evidence
- Check formatting/lint, pytest, mypy if practical, build/lint/TS checks, integrated API and UI tests, seeded simulations, data validators, model backtest metrics, performance FPS/seek latency/memory for replay where possible.
- Save exact command, timestamp, exit code, environment fingerprint and short output plus artifact path. Distinguish `PASS (real data)`, `PASS (synthetic fixture)`, `SKIPPED`, `BLOCKED`, `FAILED`; never conflate them.
- Avoid checkpoint notebook outputs that bloat git; notebook source in git, generated tables/models/data ignored and indexed via manifest. Document artifact hashes and reproduction commands.

---

## 7. Mandatory documentation system — ChatGPT must later be able to teach every detail

This section is a **hard requirement** and more important than superficial polished documentation. As you work, continuously create/update the following; use the included `AGENTS.md` as your durable agent contract.

```
docs/
├── START_HERE.md                  # project status + how to run + where to learn
├── ROADMAP.md                     # exact phase checklist, priority, progress, blockers
├── ARCHITECTURE.md                # diagrams, modules, contracts, data/time flow
├── DATA_CONTRACTS.md              # provider→canonical mapping, units, timestamps, quality
├── VISUAL_PIPELINE.md             # track geometry, dot interpolation, 2D/3D, chart sync
├── ML_EVALUATION.md               # data splits, feature audit, baselines, real metrics
├── STRATEGY_MODEL.md              # lap equations, tyre/pit/SC, MC and evaluation
├── REFERENCE_REPOS.md             # keep existing; source-level citations/licensing
├── NVIM_NOTEBOOK_WORKFLOW.md      # tools, actual commands, notebook pairing/repro
├── GLOSSARY_FOR_LEARNING.md       # FastF1, dataframe, ETL, delta, MAE, RaceState, etc.
├── DECISIONS.md                   # short evidence-based design decision log
├── AGENT_WORKLOG.md               # chronological work, experiments and proof
├── CHATGPT_HANDOFF.md             # top-priority digest for future ChatGPT tutor
├── IMPLEMENTATION_ATLAS.md        # EACH important file/module/function explained
├── EXPERIMENT_REGISTER.md         # dataset/model config, results, artifacts, limits
├── TEST_EVIDENCE.md               # exact commands, PASS/FAIL, screenshots/artifacts
└── adr/ADR-0001-....md            # reasons behind significant changes
```

### Minimum standards for EACH implemented milestone
Write an entry in `docs/AGENT_WORKLOG.md` with:
1. UTC/local date, phase/milestone ID, starting git SHA, current branch/status.
2. What the user wanted, what you set out to accomplish, precise scope.
3. Existing code you found and why you changed it; **list all modified/created/deleted paths**, plus key functions/classes.
4. Technical explanation in teachable language: inputs, outputs, underlying formula/algorithm, execution/data flow, units and before/after example. For ML, include feature definitions, temporal availability and model metrics. For replay, clock/event transformations and visualization timing. For simulation, math/assumptions and objective.
5. Research/source URLs, exact reference commits/licenses and what was used or rejected.
6. Commands run and verifiable outcomes, datasets involved, record IDs/counts, seeds, dependency versions, tests/plots/screenshots locations; explicitly identify synthetic vs real results.
7. Bugs discovered, root cause, fix and regression test, limitations/coverage/proxy approximations.
8. Design choices/trade-offs (why this tech instead of alternative), dependencies introduced, performance/cost implications.
9. Git commit SHA/link, whether pushed, and a minimal reproduction procedure.
10. What remains unfinished, blockers and next logically dependent work.

`docs/IMPLEMENTATION_ATLAS.md` must cover all major files, APIs, notebook cells and internal contracts with **purpose → call chain → input shape → algorithm → output shape → example → test → caveat**. Do not merely paste code. Explain sophisticated steps (e.g. per-driver `shift(1)` and event-scoped normalization) as if preparing a deep technical tutorial for the project's owner.

`docs/CHATGPT_HANDOFF.md` MUST BE SELF-SUFFICIENT. A future assistant will read this first after your execution, without seeing your terminal history. Include a precise executive status, completed vs incomplete features, git HEAD and branch, source tree map, what was run successfully, real ML metrics with data coverage, available demo instructions, failure/blocker matrix, ordered next work, all major technical design choices, and links/relative paths to verbose docs and artifacts. No speculation. Update it at the end of each milestone and at the end of every session.

Also write **a human-readable learning chronology** in `docs/GLOSSARY_FOR_LEARNING.md`: all technologies and important equations (FastF1 cache, pandas vs Polars, Parquet vs SQL vs MinIO, `LapTime` Timedelta, event normalization, distance alignment, linear regression/Ridge/LightGBM, overfitting, feature leakage, MAE/Spearman, Monte Carlo, correlated worlds, tyre degradation, undercut) in precise language with F1LAB examples. Aim for accuracy, not filler. The next assistant's job will be to explain your work step by step to the user; give them enough evidence to do so without reverse-engineering everything again.

---

## 8. Required completion report format (end of every substantial CLI run)

Write **both** `docs/CHATGPT_HANDOFF.md` and a concise terminal summary in this form:

```
F1LAB IMPLEMENTATION CHECKPOINT — <date/time>
Repo branch / git HEAD / clean? / pushed?
PHASES: [done, in progress, blocked, not started]
FILES: <key additions and changed modules>
RUNS: <actual commands and PASS/FAIL>
REAL-DATA EVIDENCE: <sources, number of weekends, rows, charts, valid metrics>
SYNTHETIC-ONLY EVIDENCE: <what it does NOT prove>
ARCHITECTURE: <changes/ADRs>
UI DEMO: <exact command and steps, or not available>
BLOCKERS / CAVEATS: <truthful>
NEXT ACTIONS: <prioritized 1–5>
FOR CHATGPT REVIEW: read docs/CHATGPT_HANDOFF.md,
  docs/AGENT_WORKLOG.md, docs/IMPLEMENTATION_ATLAS.md,
  docs/ML_EVALUATION.md and docs/TEST_EVIDENCE.md
```

Do not say “finished entire product” because a few tests passed. Mark scope honestly. When leaving a major phase, include a **demo narrative** (what the user clicks, what the data represents, expected output and known missing cases).

---

## 9. Backlog priorities, success criteria and nonnegotiable final quality

### Near-term priority (first autonomous execution cycle)
- [ ] Inspect and preserve branch/worktree and existing Sprint 1–2 code/notebooks.
- [ ] Verify real 2022–2025 dataset ingestion; run or repair it and log coverage/errors.
- [ ] Execute FP3/Ridge/LightGBM baseline on genuinely held-out 2025.
- [ ] Integrate/rebuild Sprint 3 historical features and Neovim/Jupytext workflow, with tests.
- [ ] Complete honest practice-vs-form ablation results and documented improvement/failure.
- [ ] Create complete mandatory docs/handoff and commit/push verified changes.
- [ ] Start canonical `RaceState`/`SessionEvent` contracts + one realistic historical sample once ML checkpoint is sound.

### Mid-term proof (first compelling working application)
- [ ] A real historical session loads and replays deterministically offline, including synchronized 2D car animation, timeline/seek and timing tower.
- [ ] Two-driver telemetry can be distance-aligned with shared crosshair/circuit point.
- [ ] An evaluated pre-Q model displays predictions, baselines, errors and provenance.
- [ ] A basic strategy simulator compares stay-out vs pit on an actual race state with documented uncertainty.

### Long-term integrated lock
- [ ] Replay/live/simulation share event contracts and RaceState.
- [ ] Analysis, strategy, prediction and comparison are integrated workspaces.
- [ ] 3D uses same circuit geometry and session clock.
- [ ] Radio is contextual/coverage-aware, counterfactual scenarios reproducible.
- [ ] CI/tests/migrations/source provenance/model evaluation, comprehensive learnable documentation.

### Final principles
**Build fast, but not blindly. Reuse ideas, not dependencies without proof. Explain all important transformations. Test what you claim. Keep a rigorous scientific evaluation. Protect the user's project. Make F1LAB feel like a professional motorsport engineering workstation.**

If something is ambiguous, choose the least disruptive, measurable and extensible approach, document the assumption and proceed. The user does not want a succession of confirmation questions or an impressive plan with no functional implementation. They want the implementation and a forensic documentation trail that ChatGPT can later use to teach them **exactly what you built and why**.

---

## 10. Source map (starting reading list, not unconditional trust)

**Existing F1LAB:**
- https://github.com/JedidiAymen/F1LAB/tree/feat/foundation
- `docs/REFERENCE_REPOS.md`
- `docs/ML_QUALIFYING_SPRINT2.md`
- `src/f1_racelab/data/qualifying_dataset.py`
- `src/f1_racelab/features/qualifying.py`
- `src/f1_racelab/models/qualifying_backtest.py`
- `notebooks/01_qualifying_weekend.ipynb`, `02_qualifying_backtest.ipynb`
- `tests/test_qualifying_backtest.py`

**Historical/replay/live references:**
- https://github.com/i-ares/open-f1
- https://github.com/MatthewDelong/F1-Telemetry
- https://github.com/Austen33/f1-race-replay
- https://github.com/keithfeb14/f1-race-replay
- https://github.com/theOehrly/Fast-F1
- https://github.com/br-g/openf1
- https://openf1.org/docs/
- https://github.com/jolpica/jolpica-f1
- https://github.com/siddoboi/f1-telemetry-dashboard
- https://github.com/ArsalanKaleem/F1-Vision
- https://github.com/4f4d/f1radio

**Race simulation/strategy:**
- https://github.com/TUMFTM/race-simulation
- https://github.com/LoreMonti/F1-strategy-engine
- https://github.com/andriaberi/F1-Simulator
- https://github.com/j5t3313/f1-strategy-simulator
- https://github.com/loisekk/f1-strategy-engine

**Prediction/features:**
- https://github.com/eddmann/f1-picks-2025-predictor
- https://github.com/Adhithiyaram13/F1-Predictor
- https://github.com/gcckd01/F1-QUALI-PREDICTOR
- https://github.com/nina-coder/f1-predictions
- https://github.com/manasscodes/f1-race-intelligence

**Historical technical blueprint (if available in user-provided files):** `F1_RaceLab_Full_Technical_Investigation_v2.docx` and `F1_RaceLab_Deep_Investigation_and_Product_Blueprint.docx`; these are design context, not current repository truth. This master brief captures their key scope independently so those attachments are not essential to begin.

**BEGIN NOW.** Do not stop after writing another roadmap. Implement M1–M5, validate with real-data evidence, produce the full teaching handoff, then proceed to the canonical replay/session foundation as permitted by actual progress, resources and constraints.
