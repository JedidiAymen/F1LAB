# F1LAB

F1LAB is an in-progress Formula 1 race-intelligence workstation: historical
race replay on one shared clock, walk-forward qualifying and race-pace
forecasting with honest baselines and uncertainty, a deterministic strategy
simulator and what-if branches, behind a FastAPI backend and a React/Vite
front end. Live timing and the deep-learning and computer-vision modules are
not built yet.

## Status at a glance

Real data is OpenF1 (2023-2026) and FastF1 (2022); raw data stays local and
git-ignored (OpenF1 terms are non-commercial, see
[the data contract](docs/DATA_CONTRACTS.md)).

| Area | State | Measured result (real data) |
| --- | --- | --- |
| Qualifying forecast | Walk-forward ensemble with rank probabilities (`/api/v1/predictions/qualifying/walkforward`) | 2024-25 pooled: 0.27 positions better than latest practice (interval excludes zero). **2026: no transfer** (+0.05, interval includes zero). |
| Race-pace forecast | Next-lap LightGBM, out-of-fold UI (`/api/v1/pace/*`), versioned prediction endpoint (`POST /api/v1/pace/predict`) | 65 scored races, 57,679 green laps. 0.575 s MAE vs 0.593 s for last-lap persistence: **difference -0.018 s, race-clustered 95% CI [-0.057, +0.029], not significant**; persistence is better in 2025. Raw 80% interval covers 75%; a chronological conformal correction reaches 80%. Safety-car laps are out of distribution. |
| Replay and Race Control | Three historical races, shared clock, 2D map, race control | Deterministic seek; see [replay docs](docs/RACE_CONTROL_UI.md) |
| Strategy and What-If | Deterministic simulator, seeded Monte Carlo | Assumption-driven, calibrated on Monza 2025 only |
| Driver DNA, RaceVision, Overtake, Neural Qualifying, Radio | Not started | None. No claims are made. |

Model cards, hashes and the research notes are in
[docs/research](docs/research/RACE_PACE_INTELLIGENCE.md); CI runs ruff, pytest
and the web lint, unit tests and build (`.github/workflows/ci.yml`).

Start with [the project status](docs/START_HERE.md), [the execution roadmap](docs/ROADMAP.md)
and [the latest handoff](docs/CHATGPT_HANDOFF.md). The full product scope is in
[the master execution document](docs/SOL61_MASTER_EXECUTION.md).

## Local setup and checks

```bash
uv sync --dev
.venv/bin/pytest -q
.venv/bin/ruff check src tests scripts
```

## Reproduce the qualifying benchmark

The dataset and metric artifacts are stored locally under ignored `data/`.
OpenF1 historical requests are cached and paced. The 2022 part uses existing
FastF1 event files; see [the data contract](docs/DATA_CONTRACTS.md) for
provider lineage and rights caveats.

```bash
.venv/bin/python -m f1_racelab.data.openf1_qualifying --years 2023 2024 2025
.venv/bin/python -m f1_racelab.data.mixed_qualifying
.venv/bin/python -m f1_racelab.models.qualifying_backtest --dataset data/processed/qualifying_mixed_2022_2023_2024_2025.parquet --feature-set common
.venv/bin/python -m f1_racelab.models.qualifying_ablation --dataset data/processed/qualifying_mixed_2022_2023_2024_2025.parquet --feature-set common
```

The experiment covers 71 conventional weekends across 2022–2025. Ridge was
selected on 2024 and scored 3.2433 position MAE on held-out 2025 events,
versus 3.3141 for FP3 ranking. Its paired event uncertainty interval crosses
zero, so the benchmark does not establish a reliable gain. Read
[the evaluation report](docs/ML_EVALUATION.md) and
[experiment register](docs/EXPERIMENT_REGISTER.md) before interpreting results.

## Session timeline foundation

The Python package now has versioned event/state contracts and deterministic
seek logic. A limited real-data sample of 2025 Monza race-control messages can
be built from the local OpenF1 cache:

```bash
.venv/bin/python -m f1_racelab.session.openf1_sample
```

It writes an ignored JSON artifact under `data/processed/replay_samples/`.
The older sample contains messages only; the richer pack below drives the
first interactive Race Control view.

A richer **local offline replay pack** is now available for the 2025 Italian
GP race. It contains 20 drivers, 1,506 discrete events and 198,300 retained
approximate location points. Build and validate it with:

```bash
.venv/bin/python -m f1_racelab.session.openf1_replay
.venv/bin/python -m f1_racelab.session.openf1_replay --session monaco-2023
.venv/bin/python -m f1_racelab.session.openf1_replay --session brazil-2024
.venv/bin/python -m f1_racelab.session.validate_replay --all
```

The pack is ignored by Git. Start the backend and frontend in separate
terminals:

```bash
.venv/bin/uvicorn f1_racelab.api:app --host 127.0.0.1 --port 8000
cd apps/web
npm ci
npm run dev -- --host 127.0.0.1
```

Select Monza 2025, Monaco 2023 or Brazil 2024. The UI provides one shared
playback clock, timing, a provider-derived 2D map and race-control messages.
Monaco's missing pit resource is shown explicitly. Run real-pack browser
checks from `apps/web` with:

```bash
npx playwright install chromium
npm run test:unit
npm run test:e2e
```

See [the three-session evidence](docs/REPLAY_GOLDEN_SESSIONS.md) for exact
source/clock semantics, checks, screenshots and remaining limitations.
