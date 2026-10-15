# F1LAB architecture: actual and target

## Implemented qualifying path

```mermaid
flowchart LR
  A[FastF1 cached 2022 laps/results] --> B[per-weekend Parquet]
  C[OpenF1 2023–2025 session results] --> D[raw JSON cache]
  D --> E[per-weekend Parquet]
  B --> F[mixed provider dataset + manifest]
  E --> F
  F --> G[legal common practice features]
  G --> H[FP3 / Ridge / LightGBM]
  F --> I[shifted historical form]
  I --> J[form Ridge / LightGBM]
  H --> K[2024 selection + 2025 held-out metrics]
  J --> K
```

Each event is a prediction group. Training is 2022–2023, validation 2024,
test 2025. The row schema and timestamp policy are in `DATA_CONTRACTS.md`.
The existing React/Vite app is still the starter screen; it is not integrated
with predictions or replay yet. Python API and session-engine directories are
scaffolds.

## Locked temporal architecture to implement

```mermaid
flowchart LR
  P[Provider adapters] --> N[Canonical SessionEvents]
  N --> S[RaceSource: replay / live / simulation]
  S --> R[Deterministic RaceState reducer]
  C[One session clock] --> R
  R --> M[2D and later 3D circuit]
  R --> T[Timing and telemetry]
  R --> L[Prediction and strategy]
```

`RaceState` must be the single source of visible session truth. A future
animation frame may update drawing, but it cannot create a separate race clock.
Measured, interpolated and simulated values must remain distinguishable. No
`SessionEvent`/`RaceState` implementation is claimed here yet.

## Storage and module ownership

- `src/f1_racelab/data`: provider adapters and local Parquet/JSON lineage.
- `src/f1_racelab/features`: practice and strictly past qualifying features.
- `src/f1_racelab/models`: event grouped evaluation and model ablations.
- `apps/web`: React/Vite interface, currently starter UI.
- `apps/api`, `services/session-engine`, `packages/*`: future typed API, reducer
  and shared contracts; current contents are mostly empty scaffolding.
- `data/raw`, `data/cache`, `data/processed`: ignored local data artifacts.
- PostgreSQL/MinIO in Compose are intended stores, but no replay state or ML
  serving contract currently depends on them.
