# Start here: F1LAB status

F1LAB is being built as one race intelligence workstation. The current working
slice is historical pre-qualifying evaluation. The React app is still the Vite
starter and does not yet demonstrate Race Control.

## Run the verified local checks

```bash
uv sync --dev
.venv/bin/pytest -q
.venv/bin/ruff check src tests
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
