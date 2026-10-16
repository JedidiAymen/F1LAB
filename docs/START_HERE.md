# Start here: F1LAB status

F1LAB is being built as one race intelligence workstation. The current working
slice includes historical pre-qualifying evaluation and three offline race
replays: Monza 2025, Monaco 2023 and Brazil 2024. The local Race Control
screen has a session picker and passes real-pack browser interaction checks.

## Run the verified local checks

```bash
uv sync --dev
.venv/bin/pytest -q
.venv/bin/ruff check src tests scripts
cd apps/web && npm run lint && npm run build
```

Historical data lives under ignored `data/`; it is not in Git. The completed
research benchmark covers 71 conventional weekends; Ridge was chosen on 2024
and evaluated on 2025, but its paired uncertainty interval versus FP3 crosses
zero. Read `ML_EVALUATION.md` and `EXPERIMENT_REGISTER.md` for exact coverage,
metrics, commands and limitations. OpenF1 downloads use an on-disk JSON cache
and a request interval below its public limit.

## Read in this order

1. `CHATGPT_HANDOFF.md`: exact done/partial/missing scope and current evidence.
2. `ROADMAP.md`: acceptance gates and next dependent work.
3. `ARCHITECTURE.md` and `DATA_CONTRACTS.md`: paths, fields and time semantics.
4. `ML_EVALUATION.md`, `EXPERIMENT_REGISTER.md`, `TEST_EVIDENCE.md`: science.
5. `IMPLEMENTATION_ATLAS.md`, `AGENT_WORKLOG.md`, `DECISIONS.md`, and
   `GLOSSARY_FOR_LEARNING.md`: implementation tutorial and chronology.

The full locked product scope remains `SOL61_MASTER_EXECUTION.md`.
The partial session foundation is described in `ARCHITECTURE.md`; its limited
real race-control sample is reproducible with
`.venv/bin/python -m f1_racelab.session.openf1_sample`.
For the richer offline Monza race pack, run
`.venv/bin/python -m f1_racelab.session.openf1_replay` followed by
`.venv/bin/python -m f1_racelab.session.validate_replay` and read
`REPLAY_2025_MONZA.md`. The packs are local and ignored. Build all three
and run the browser checks using `REPLAY_GOLDEN_SESSIONS.md`; it also
provides the current demo narrative, exact metrics, screenshots and limits.
