# F1LAB handoff for the next ChatGPT session

**Status at 2026-10-15 UTC:** qualifying source recovery, baseline and form
ablation completed as a research benchmark. Branch `feat/foundation`; starting
HEAD `bb840d44a2cf6c2f325f6ef2a575ff074f0d1b05`. Check `git log -1` and
`git status` for the latest checkpoint and push state.

## What exists and what does not

- **Done before this run:** Monza 2025 practice/qualifying exploration; Sprint 2
  FastF1 feature builder, chronological backtest code and synthetic tests.
  The saved single-Monza result (MAE 2.70 positions, Spearman 0.823) is a
  one-event comparison, not a generalization score.
- **Implemented in this run:** project-scoped pytest collection, a public
  OpenF1 historical adapter with raw response cache and request pacing,
  common-source qualifying feature set, provider-labelled dataset merge,
  event-paired bootstrap and coverage outputs, and normalization tests.
- **Done in this run:** OpenF1 ingestion for 2023–2025, merged 2022–2025
  dataset, real 2024 model selection and 2025 held-out evaluation, five-model
  form ablation, one-event provider overlap audit, one manual historical-form
  trace, and executed notebook chart. See `EXPERIMENT_REGISTER.md`.
- **Not done:** calibrated probabilities, prediction serving, canonical
  `RaceState`/`SessionEvent` reducer, historical replay, 2D
  or 3D visualization, telemetry comparison, strategy, what-if, live and radio.
  The React frontend still renders the Vite starter screen.

## Why the provider changed

The initial local `qualifying_2022_2023_2024_2025.parquet` had only 360 rows:
17 conventional 2022 weekends plus 2025 Monza. The prior ingestion log hit
FastF1's 500 calls/hour limit. This run completed two more cached 2022
weekends, but uncached 2023 F1 timing failed; a direct 2023 Bahrain timing URL
returned HTTP 401. OpenF1 documents public historical data from 2023 onward
and returned Q phase times, FP3 results and driver/team identity. We preserve
the original dataset and build a separate source-labelled one. See
`DATA_CONTRACTS.md`, `DECISIONS.md` and [OpenF1 docs](https://openf1.org/docs/).

## Architecture and source map

`src/f1_racelab/data/fastf1_source.py` configures the local cache;
`features/qualifying.py` computes practice rows and post-Q labels;
`data/qualifying_dataset.py` stores FastF1 event Parquets;
`data/openf1_qualifying.py` stores OpenF1 JSON and normalizes 2023–2025;
`data/mixed_qualifying.py` combines providers;
`features/historical_qualifying.py` creates strictly lagged driver/team form;
`models/qualifying_backtest.py` and `models/qualifying_ablation.py` fit and
evaluate five candidate rankings. `IMPLEMENTATION_ATLAS.md` describes inputs,
outputs, formulas, tests and caveats per function. `ARCHITECTURE.md` diagrams
the actual data flow and the still-unimplemented unified replay architecture.

## Reproduction and evidence

```bash
uv sync --dev
.venv/bin/pytest -q
.venv/bin/python -m f1_racelab.data.openf1_qualifying --years 2023 2024 2025
.venv/bin/python -m f1_racelab.data.mixed_qualifying
.venv/bin/python -m f1_racelab.models.qualifying_backtest --dataset data/processed/qualifying_mixed_2022_2023_2024_2025.parquet --feature-set common
.venv/bin/python -m f1_racelab.models.qualifying_ablation --dataset data/processed/qualifying_mixed_2022_2023_2024_2025.parquet --feature-set common
```

The latest test count and lint status are in `TEST_EVIDENCE.md`; fixture tests
are separate from the real provider data and model experiment. Generated
datasets and metrics are under ignored `data/processed/`; inspect
`qualifying_mixed_manifest.json`, ingestion CSV, `qualifying_backtest/` and
`qualifying_ablation/`. The mixed file has 71 conventional weekends and 1,418
source rows, with 35/18/18 eligible train/validation/test events and
684/342/354 evaluated rows. Its SHA-256 is
`eef5a7277d2f62fdf263e94cadbc7a5f5c38cd6acdbea9dc00549d5caef37fd8`.
Ridge won on 2024 MAE (2.8362 vs FP3 2.8975). Its held-out 2025 MAE was
3.2433 vs FP3 3.3141, with paired event delta -0.0708 and 95% bootstrap
interval [-0.2934, +0.1587]. The interval crosses zero, so no reliable
improvement is claimed. The UI remains the Vite starter; no replay demo exists.

## Known failure and risk matrix

| Issue | Evidence | Effect / next handling |
|---|---|---|
| FastF1 uncached archive access | F1 timing URL HTTP 401 | Use OpenF1 historical data, keep source labels and raw hashes |
| Mixed provider best-lap definitions | FastF1 lap filter vs OpenF1 `session_result`; 2025 Monza matched exactly on available pairs | Extend overlap audit beyond one event; use common eight fields |
| Q1 pace proxy vs final Q classification | Pipeline target/label definitions | Report separately; phase-aware model remains future work |
| Limited uncertainty evidence | 18 held-out events; paired interval crosses zero | Avoid superiority or deployment claims |
| Team names and driver acronyms as identifiers | Current row schema | Audit transfers, substitutions and renamed constructors before production |

## Next five actions

1. Run final scoped tests and lint, review staged files for secrets and data,
   then commit and push the documented research checkpoint.
2. Implement typed `SessionEvent`/`RaceState` and a real historical sample as
   the first step toward synchronized 2D replay.
3. Expand cross-provider overlap and as-of timestamp audits before promoting
   a qualifying model toward production use.

For tutoring, read `AGENT_WORKLOG.md`, `IMPLEMENTATION_ATLAS.md`,
`ML_EVALUATION.md`, `TEST_EVIDENCE.md`, `DATA_CONTRACTS.md`, `DECISIONS.md` and
`GLOSSARY_FOR_LEARNING.md` after this page. The locked scope remains
`SOL61_MASTER_EXECUTION.md`; a passing ML benchmark will not finish it.
