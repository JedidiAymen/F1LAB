# F1LAB — Reference Repositories & Reuse Strategy

> **Status:** Living engineering document  
> **Goal:** Track the Formula 1 projects we study, what we can reuse, what we should rebuild, and how each reference influences F1LAB.

## 1. Vision

F1LAB will be an integrated Formula 1 engineering, replay, visualization, simulation, strategy, and machine-learning platform — not a generic statistics dashboard.

Target capabilities:

- historical race and qualifying replay
- live race visualization
- interactive 2D circuit visualization and later 3D
- timing tower and race-state monitoring
- synchronized driver telemetry
- driver-vs-driver and race-vs-race comparison
- tyre, stint, weather, pit-stop, and race-control analysis
- team radio where data is available
- qualifying/grid prediction
- race-result probabilities
- strategy simulation and ML-assisted recommendations
- Monte Carlo race simulation
- what-if scenarios
- actual-vs-simulated race comparison

The central design goal is to make replay, live data, simulation, analytics, and ML share one normalized representation of a Formula 1 session.

## 2. Reuse Philosophy

We want to build quickly **and understand what we build**.

```text
DISCOVER
   ↓
RUN
   ↓
UNDERSTAND
   ↓
CHECK LICENSE
   ↓
IDENTIFY USEFUL SUBSYSTEM
   ↓
TEST ITS BEHAVIOR
   ↓
REUSE / PORT / REBUILD
   ↓
COMPARE
   ↓
IMPROVE FOR F1LAB
```

For each candidate subsystem we answer:

1. What problem does it solve?
2. What data does it consume?
3. How does it represent that data?
4. What assumptions does it make?
5. What are its limitations?
6. What license governs reuse?
7. Does it fit our canonical data model?
8. Is reuse actually better than rebuilding?
9. How do we test equivalence?
10. How can F1LAB improve it?

## 3. Reference Matrix

| Project | Main inspiration | F1LAB area |
|---|---|---|
| F1 Terminal / open-f1 | Dense engineering-terminal UX, replay/live concepts | Race Control, replay, live |
| F1-Telemetry | React visualization and 3D race concepts | Visualization, 3D |
| F1 Race Replay | Replay mechanics and animated race state | Replay engine |
| F1 Vision | Telemetry cockpit and synchronized analytics | Telemetry UX |
| F1 Strategy Engine | Strategy/simulation architecture | Strategy engine |
| F1 Simulator | ML lap-time and strategy baseline | ML + strategy |
| FastF1 | Historical timing, laps and telemetry | Data ingestion |
| OpenF1 | Position, car, race-control and recent/live data | Data ingestion + live |
| Jolpica F1 | Historical metadata/results | Historical data |

These are investigation roles, not hard dependencies.

## 4. F1 Terminal / open-f1

Repository: https://github.com/i-ares/open-f1

### Why study it

It is close to the experience we want: a dense Formula 1 information terminal rather than a normal SaaS dashboard.

Investigate:

- timing tower
- circuit visualization
- telemetry
- sectors
- tyres and pit stops
- weather
- race control
- radio/transcript presentation
- historical replay
- live updates
- movable/resizable panels

### Key idea: one race state

```text
Historical Replay ─┐
                   ├── RaceState ──> UI
Live Feed ─────────┘
```

All visible panels should observe the same session clock.

### Source-level targets

- replay format
- session clock
- event synchronization
- WebSocket/live architecture
- circuit rendering
- position interpolation
- widget state/layout
- radio and race-control integration

### Preliminary decision

Use primarily as an information-architecture and race-terminal reference. Do not copy the whole frontend.

## 5. F1-Telemetry

Repository: https://github.com/MatthewDelong/F1-Telemetry

### Why study it

Useful for React-based race visualization, telemetry, driver comparison, circuit representation, animation, and 3D concepts.

The important question is not “how do we copy its 3D viewer?” but:

> How does normalized race data become a synchronized visual scene?

Target abstraction:

```text
             CircuitGeometry
                    │
           ┌────────┴────────┐
           ▼                 ▼
      2D Renderer       3D Renderer
           │                 │
           └────────┬────────┘
                    ▼
                RaceState
```

Investigate:

- circuit geometry
- coordinate normalization
- driver-position model
- interpolation
- animation loop
- camera behavior
- React/state integration
- performance

## 6. F1 Race Replay

Repositories:

- https://github.com/Austen33/f1-race-replay
- https://github.com/keithfeb14/f1-race-replay

Replay is a core F1LAB system.

Investigate:

- animated positions
- timing synchronization
- tyre compounds
- safety-car state
- retirements
- lap/race clock
- play/pause
- seek and rewind
- playback speed
- selected-driver telemetry

Target:

```text
Replay Clock
     │
     ▼
 RaceState(t)
     │
 ┌───┼──────────┬─────────────┐
 ▼   ▼          ▼             ▼
Map Timing  Telemetry      Strategy
```

The widgets must never maintain independent clocks.

Expected controls eventually include play, pause, seek, rewind, and multiple playback speeds such as 1x, 2x, 4x, 8x and 16x.

## 7. F1 Vision

Repository: https://github.com/ArsalanKaleem/F1-Vision

Use mainly as a telemetry UX reference.

Investigate:

- speed, RPM and gear
- DRS
- throttle and brake
- track position
- synchronized telemetry charts
- shared crosshair
- zoom/pan
- rolling live buffers
- dense engineering layouts

Selecting or hovering a telemetry point should synchronize circuit position, speed, throttle, brake, gear, RPM, DRS, delta, and relevant timing information.

## 8. F1 Strategy Engine

Repository: https://github.com/LoreMonti/f1-strategy-engine

Strategy is not simply an ML classification task. A useful strategy system needs simulation and uncertainty.

Investigate:

- vehicle/pace model
- tyre model
- weather model
- lap and race simulation
- multi-car interaction
- Monte Carlo
- optimization
- live re-optimization

Target architecture:

```text
                 Race State
                     │
       ┌─────────────┼─────────────┐
       ▼             ▼             ▼
     Tyres        Weather       Traffic
       │             │             │
       └─────────────┼─────────────┘
                     ▼
                 Pace Model
                     │
                     ▼
               Race Simulator
                     │
       ┌─────────────┼─────────────┐
       ▼             ▼             ▼
 Strategy A      Strategy B      Strategy C
       │             │             │
       └─────────────┼─────────────┘
                     ▼
                 Monte Carlo
                     │
                     ▼
            Outcome Distribution
                     │
                     ▼
          Strategy Recommendation
```

## 9. F1 Simulator

Repository: https://github.com/andriaberi/F1-Simulator

Useful as a smaller ML/strategy baseline:

```text
FastF1
  ↓
Lap Dataset
  ↓
Feature Engineering
  ↓
Lap-Time Model
  ↓
Strategy Simulation
```

Our eventual model should investigate tyre compound/age/degradation, driver pace, fuel effect, traffic, dirty air, weather, track temperature/evolution, pit loss, SC/VSC, undercut/overcut, compound availability, and scenario uncertainty.

Strategy output should eventually be probabilistic and explainable rather than only “pit on lap 24”.

## 10. FastF1

Repository: https://github.com/theOehrly/Fast-F1

Planned role: primary Python interface for historical F1 analysis.

Potential data:

- event schedules
- sessions/results
- laps
- telemetry
- weather
- timing
- race-control information where available

Provider objects must not leak throughout F1LAB:

```text
FastF1
   ↓
FastF1Adapter
   ↓
Canonical F1LAB Models
```

## 11. OpenF1

Repository/service:

- https://github.com/br-g/openf1
- https://openf1.org/

Potential role:

- meetings/sessions
- drivers
- positions
- intervals
- car data
- stints
- pits
- weather
- race control
- team radio where available
- recent/live session data

Architecture:

```text
OpenF1
   ↓
OpenF1Adapter
   ↓
Canonical F1LAB Models
```

The frontend should not directly depend on OpenF1 schemas.

## 12. Jolpica F1

Repository: https://github.com/jolpica/jolpica-f1

Potential role: historical seasons, circuits, constructors, drivers, results and standings.

It complements telemetry-oriented sources.

## 13. Storage Architecture

### PostgreSQL

Use for relational/application data:

- events and sessions
- drivers/constructors/circuits
- results metadata
- ingestion metadata
- model runs
- simulation runs
- later user-created scenarios

### Parquet / Arrow

Use for large analytical datasets:

- telemetry
- position samples
- processed laps
- feature-engineering datasets
- ML datasets

### MinIO

Use for object storage:

- raw provider snapshots
- Parquet datasets
- replay packs
- circuit geometry
- generated artifacts
- model artifacts

```text
Providers
   │
   ├────> Raw snapshots ─────────────> MinIO
   │
   ▼
Adapters
   │
   ▼
Canonical Data
   │
   ├────> Relational metadata ───────> PostgreSQL
   │
   └────> Analytical tables ─────────> Parquet / MinIO
```

## 14. SQLAlchemy vs Drizzle

Current backend ownership:

```text
React / Vite
     │
 REST / WebSocket
     ▼
   FastAPI
     │
     ▼
 SQLAlchemy
     │
     ▼
 PostgreSQL
```

F1LAB's heavy data/ML stack is Python-oriented: FastF1, Pandas, Polars, NumPy, SciPy, scikit-learn, and likely XGBoost/LightGBM later.

### Current decision

Use:

- PostgreSQL
- SQLAlchemy
- Alembic

Do **not** introduce Drizzle yet.

Two ORM ownership layers against the same application database add complexity without a demonstrated requirement. Revisit only if a future TypeScript backend/service genuinely needs database ownership.

## 15. Canonical Data Model

Before serious visualization or ML, define provider-independent models based on real data.

Initial candidates:

- Season
- Meeting
- Circuit
- Session
- Driver
- Constructor
- Result
- Lap
- TelemetryFrame
- PositionFrame
- Stint
- PitStop
- WeatherFrame
- RaceControlEvent
- RadioEvent
- SessionClock / ReplayTime

The exact schema should be designed after comparing FastF1 and OpenF1 for the same real Grand Prix/session.

## 16. Visualization Architecture

```text
FastF1 ─────┐
OpenF1 ─────┤
Jolpica ────┤
            ▼
         Adapters
            ▼
     Canonical Models
            ▼
       Session Engine
            ▼
         RaceState
            │
     ┌──────┼───────────┐
     ▼      ▼           ▼
 Circuit  Timing     Telemetry
     │
  ┌──┴──┐
  ▼     ▼
 2D     3D
```

The same visualization system should eventually display historical, live, simulated, strategy what-if, and ML-generated scenarios.

## 17. UI Philosophy

F1LAB should not look like a generic admin dashboard.

Avoid the typical “sidebar + random cards + large empty spaces” design.

The primary interface should feel like:

- an F1 pit wall
- a race-engineering workstation
- a telemetry terminal
- a race-control system
- a motorsport analysis laboratory

Principles:

- dark-first
- dense but readable
- circuit as a major visual anchor
- meaningful driver/team colors
- compact controls
- synchronized panels
- minimal decorative cards
- animation used to communicate race state
- resizable/reconfigurable panels where useful

shadcn/Base UI gives us primitives; it does not define the visual identity.

## 18. Race Control Workspace

Concept:

```text
┌──────────────────────────────────────────────────────────────────────┐
│ F1LAB   MONACO 2025 / RACE    LAP 47/78       ◀ ▶  1x 4x 8x 16x │
├───────────────┬────────────────────────────────┬─────────────────────┤
│ TIMING TOWER  │                                │ DRIVER              │
│ 01 NOR        │                                │ NORRIS              │
│ 02 LEC +1.2   │            CIRCUIT             │ 287 km/h            │
│ 03 PIA +3.7   │        ●       ●               │ GEAR 7 / DRS OPEN   │
│               │            ●                   │                     │
├───────────────┴────────────────────────────────┴─────────────────────┤
│ LAP 47  ━━━━━━━━━━━━━━━━━●━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
├────────────────────────────────┬─────────────────────────────────────┤
│ STRATEGY                       │ TELEMETRY                           │
│ NOR MMMMMMMM | HHHHHHHHH       │ SPEED ─────╲___╱────────           │
│ LEC MMMMM | HHHHHHHHHHH        │ THR   ───────╲__╱────              │
├────────────────────────────────┼─────────────────────────────────────┤
│ RACE CONTROL                   │ RADIO                               │
│ YELLOW - TURN 8                │ NOR ▶ ...                           │
│ SAFETY CAR DEPLOYED            │ LEC ▶ ...                           │
└────────────────────────────────┴─────────────────────────────────────┘
```

This is an information-architecture concept, not a locked visual design.

## 19. Main Workspaces

### Race Control

Historical replay, live session, circuit, timing, telemetry, race control, weather, radio, playback controls.

### Analysis

Driver vs driver, lap comparison, telemetry comparison, tyre/stint analysis, race pace, qualifying analysis, track evolution.

### Strategy Lab

Actual strategy, alternatives, what-if simulation, ML recommendation, Monte Carlo outcomes, pit-window optimization, SC/weather scenarios.

### Prediction Lab

Qualifying prediction, grid prediction, race-result probabilities, confidence/uncertainty, model explanation and historical backtesting.

### History

```text
Season
  ↓
Grand Prix
  ↓
Session
  ↓
Replay / Analyze / Compare
```

## 20. Race Comparison

Race comparison should be first-class.

Potential modes:

- same driver across seasons
- different drivers in one race
- same circuit across years
- teammate comparison
- qualifying vs race
- actual vs simulated
- actual vs recommended strategy
- synchronized laps by distance rather than only timestamp

```text
        MONACO 2024                 MONACO 2025
      ┌────────────┐              ┌────────────┐
      │  CIRCUIT   │      VS      │  CIRCUIT   │
      └────────────┘              └────────────┘
               synchronized comparison
                         ↓
       pace / tyres / weather / strategy
       position / telemetry / race events
```

## 21. ML Roadmap

Do not begin with one giant black-box model.

### Stage A — Baselines

- qualifying lap-time prediction
- grid-position probabilities
- race-result probabilities
- lap-time/pace estimation

### Stage B — Features

Investigate driver form, constructor performance, circuit characteristics, practice/qualifying pace, tyres, weather, track temperature, grid position, historical circuit performance, stint age and traffic.

### Stage C — Probabilities

Prefer calibrated distributions such as:

```text
P1: 18%
P2: 24%
P3: 21%
P4+: 37%
```

rather than pretending one predicted finishing position is certain.

### Stage D — Explanation

Expose important features, confidence, calibration, historical errors and similar historical situations.

## 22. Strategy Roadmap

Potential factors:

- driver/base pace
- tyre compound and age
- degradation
- fuel effect
- pit-stop loss
- traffic and dirty air
- undercut/overcut
- track evolution
- weather
- SC/VSC
- later red flags/reliability uncertainty

For every candidate strategy, run many scenarios and compare outcome distributions rather than only one deterministic result.

## 23. Live Mode Comes Later

Historical replay should be proven first because it is reproducible and debuggable.

Later:

```text
OpenF1 / Live Provider
          ↓
      Live Adapter
          ↓
       RaceState
          ↓
 Same Race Control UI
```

Replay and live mode should mainly differ in how RaceState is produced.

## 24. Avoid Premature Complexity

Do not add technology because it looks sophisticated.

Not required yet:

- Kafka
- Kubernetes
- microservices everywhere
- distributed training
- feature stores
- MLflow without a real experiment-management need
- Redis without a concrete cache/pub-sub need
- Celery without real background-job requirements
- complex 3D before 2D/session-state correctness

Complexity must solve a demonstrated problem.

## 25. Implementation Order

### Phase 0 — Foundation

React, Vite, TypeScript, Tailwind, shadcn/Base UI, Python environment, FastAPI direction, PostgreSQL, MinIO, project structure and docs.

### Phase 1 — Reference Repo Investigation

Run/read the strongest repos, identify exact useful modules, verify licenses, record data sources, limitations, and decide reuse vs port vs rebuild.

### Phase 2 — Real Data Investigation

Pick one Grand Prix/session and compare FastF1, OpenF1 and Jolpica where relevant: IDs, timestamps, laps, telemetry, positions, stints, pits, weather and race-control events.

### Phase 3 — Canonical Contracts

Design provider-independent models from the evidence.

### Phase 4 — Ingestion

Implement FastF1Adapter, OpenF1Adapter and JolpicaAdapter while preserving raw source data.

### Phase 5 — First Historical Replay

```text
Historical Session
       ↓
Circuit Geometry
       ↓
One Driver
       ↓
Full Field
       ↓
Race Clock
       ↓
Timing Tower
       ↓
Playback Controls
```

### Phase 6 — Telemetry

Speed, RPM, gear, throttle, brake, DRS, synchronized charts and driver selection.

### Phase 7 — Analysis

Lap/driver comparison, tyres/stints, race pace, qualifying and race comparison.

### Phase 8 — Prediction

Evaluated qualifying, grid and race-result baselines.

### Phase 9 — Strategy Simulation

Pace model, tyre model, pit loss, traffic, weather, SC scenarios, strategy search and Monte Carlo.

### Phase 10 — Live

Feed live/recent data into the same RaceState architecture.

### Phase 11 — Advanced Visualization

3D circuit/replay, richer geometry, strategy overlays and simulated/predicted trajectories.

## 26. Reference Investigation Template

For every new reference:

```text
Repository:
URL:
License:
Primary language:
Framework:
Activity:
F1LAB subsystem:
Data sources:

Useful files/modules:
- ...

Architecture findings:
- ...

What we can learn:
- ...

What may be reused:
- ...

What should be rebuilt:
- ...

Known limitations:
- ...

Integration point:
- ...

Decision:
REUSE / PORT / REBUILD / REFERENCE ONLY

Reason:
...
```

## 27. Immediate Investigation Queue

1. **F1 Terminal / open-f1** — replay format, race clock, map, interpolation, live architecture, widgets, race control, radio.
2. **F1 Race Replay** — interpolation, playback/seek, state reconstruction and driver state.
3. **F1-Telemetry** — circuit geometry, 3D scene, animation and React integration.
4. **F1 Vision** — telemetry synchronization, chart interaction and cockpit layout.
5. **F1 Strategy Engine** — simulation abstractions, tyre/pace model, Monte Carlo and optimization.
6. **F1 Simulator** — dataset construction, features, lap-time model, strategy baseline and evaluation.

Findings should be added back into this document with exact files/modules and licensing decisions.

## 28. Core F1LAB Abstraction

```text
                    GRAND PRIX
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
        LIVE           REPLAY       SIMULATED
          │              │              │
          └──────────────┼──────────────┘
                         ▼
                     RaceState
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
      VISUALIZE       ANALYZE        PREDICT
                         │
                         ▼
                      OPTIMIZE
```

That shared representation is what should make F1LAB a coherent platform rather than a collection of unrelated F1 tools.

## 29. Current Decisions

| Question | Decision |
|---|---|
| Frontend | React + Vite + TypeScript |
| UI primitives | Tailwind + shadcn/Base UI |
| Backend | FastAPI / Python |
| Database | PostgreSQL |
| ORM | SQLAlchemy |
| Migrations | Alembic |
| Drizzle | Not for now |
| Analytical format | Parquet / Arrow |
| Object storage | MinIO |
| Historical telemetry | FastF1 |
| Live/recent source | Investigate OpenF1 |
| Historical metadata | Investigate Jolpica |
| First visualization | 2D circuit/replay |
| 3D | Later |
| ML | Evaluated interpretable baselines first |
| Strategy | Simulation + probabilistic modeling |
| UI direction | F1 engineering workstation |

These are engineering decisions, not permanent dogma. Change them when evidence supports a better design.

## 30. Next Step

Do **source-level investigation first**, then compare FastF1 and OpenF1 on the same real session.

That evidence will determine:

1. the canonical data model,
2. the replay engine,
3. the visualization architecture,
4. the storage contracts,
5. and which existing implementations are genuinely worth reusing.
