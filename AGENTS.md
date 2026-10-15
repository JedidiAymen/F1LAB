# F1LAB — Repository Agent Instructions

**Read `docs/SOL61_MASTER_EXECUTION.md` in full at the start of your first session.** It is the implementation mandate and product scope. This file is the shorter persistent operating rule for all later CLI sessions.

## Purpose
Build an integrated F1 race-intelligence workstation: historical replay + future live feed + common canonical RaceState + synchronized telemetry/2D/3D + qualifying/race ML + uncertainty-aware strategy and what-if branches. Produce working, tested, reproducible software, not only architecture prose.

## Current repo defaults (inspect, don't assume)
- Remote: `https://github.com/JedidiAymen/F1LAB`; working branch: `feat/foundation`.
- Python package: `src/f1_racelab` (not `f1lab`); `uv`, Python >=3.12, FastF1/pandas/Polars/PyArrow, scikit-learn/LightGBM/XGBoost, pytest.
- React/Vite/TypeScript/Tailwind frontend `apps/web`, FastAPI/backend scaffolding, PostgreSQL + SQLAlchemy/Alembic, MinIO/Parquet.
- Existing Sprint 1/2 qualifying notebooks, feature extraction, event-grouped temporally held-out benchmarking. Sprint 3 may be an external ZIP and **not** committed.

## Mandatory workflow
1. Check `git status`, current HEAD, source/docs/config and tests before edits. Don't erase unrelated changes.
2. Implement the smallest valuable integrated milestone, starting from existing multi-season qualifying backtest and historical-form features; then canonical session engine/replay.
3. In every significant source module, encode contracts, correctness and unit tests. Use real data where accessible; mark synthetic results clearly.
4. Use historical-as-of feature availability for ML, event-grouped chronological validation and honest baselines. Distinguish qualifying classification from starting grid; Q1 pace from final Q order.
5. Enforce one `RaceSource` → `SessionEvent` → `RaceState` temporal contract for Replay, Live and Simulation. UI panels don't maintain separate clocks.
6. Keep notebook experimentation reproducible with Jupytext/Neovim if possible. Put shared business logic in `src`, not cell fragments.
7. Document every implementation step as described below **in the same commit as the code**, not as an afterthought.
8. Execute and record tests/builds/benchmarks; classify evidence real/synthetic/skipped/blocked. Preserve exact commands, versions, counts and artifacts.
9. Commit verified incremental checkpoints to feature branch and push normally when safe. No forced pushes, prod secret changes, expensive paid service actions or main-branch merges.
10. Proceed autonomously to the next dependent phase; if blocked, explain what is blocked, why, and advance other safe work.

## Required documents and handoff
Update or create: `docs/ROADMAP.md`, `docs/AGENT_WORKLOG.md`, `docs/IMPLEMENTATION_ATLAS.md`, `docs/TEST_EVIDENCE.md`, `docs/EXPERIMENT_REGISTER.md`, `docs/DECISIONS.md`, `docs/GLOSSARY_FOR_LEARNING.md`, and most importantly `docs/CHATGPT_HANDOFF.md`.

**Per milestone entry:** source SHA; modified paths and major functions; inputs, outputs, algorithm/formula and units; why choices made; source URL/license; exact commands/tests; real vs synthetic evidence; metrics, graphs and artifact paths; bugs and fixes; unresolved caveats; commit SHA/push state; reproduction and next tasks.

**CHATGPT_HANDOFF.md:** stand-alone digest for the owner's future tutoring session. Must list exact done/partial/not done scope, metrics and coverage, architecture, file map, tested demo, reproduction commands, all notable decisions and failures, and links to deeper notes. Never claim things are complete without proof.

## Quality bar
- Professional pit-wall UX, real data and source-quality indicators; no fake telemetry or official broadcast asset cloning.
- Deterministic seek/state and realistic measured/estimated position flags; sync 2D/3D/telemetry/race control on one clock.
- ML baseline ablation, walk-forward/as-of leakage prevention, calibrated uncertainties when claiming probabilities.
- Strategy uses independent tested simulator, unit-consistent tyre/fuel/pit/traffic/SC logic; seeded MC, honesty about assumptions.
- Respect upstream licenses and live/data rate limits; no silently downloaded/rerelayed protected audio.

Read `docs/SOL61_MASTER_EXECUTION.md` for all phases, acceptance gates and the full project story.
