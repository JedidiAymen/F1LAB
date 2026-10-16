# F1LAB

F1LAB is an in-progress Formula 1 race intelligence workstation. The current
verified slices are a historical pre-qualifying benchmark and a one-race
offline Monza replay with a local 2D Race Control UI. Live timing, strategy,
telemetry and broader race coverage remain future work.

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
.venv/bin/python -m f1_racelab.session.validate_replay
```

The pack is ignored by Git. Start the backend and frontend in separate
terminals:

```bash
.venv/bin/uvicorn f1_racelab.api:app --host 127.0.0.1 --port 8000
cd apps/web
npm ci
npm run dev -- --host 127.0.0.1
```

The UI provides one shared playback clock, timing, a provider-derived 2D map
and race-control messages. See [the replay evidence](docs/REPLAY_2025_MONZA.md)
and [the UI milestone](docs/RACE_CONTROL_UI.md) for coverage, clock semantics,
tests and limitations. [The additional-session audit](docs/REPLAY_CANDIDATES.md)
records why Monaco/Brazil cannot yet be treated as validated replay packs.
