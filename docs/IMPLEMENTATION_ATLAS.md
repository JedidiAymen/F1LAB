# Implementation atlas — qualifying checkpoint

This atlas describes the current call chain and what each important source
symbol does. It does not claim the later replay or strategy modules exist.

## End-to-end call chain

1. `f1_racelab.data.qualifying_dataset` enumerates 2022 conventional weekends;
   `features.qualifying.build_weekend_dataset` loads FP1, FP2, FP3 and Q through
   `data.fastf1_source`, computes per-driver practice features and post-Q labels,
   and writes one Parquet per event.
2. `f1_racelab.data.openf1_qualifying` reads 2023–2025 OpenF1 meetings and
   sessions, fetches five small result/identity resources per event, maps them
   to the same row schema, and writes JSON source cache and per-event Parquet.
3. `f1_racelab.data.mixed_qualifying` adds provider metadata to cached 2022
   frames, concatenates OpenF1 frames, validates driver-weekend uniqueness and
   writes a local dataset plus SHA-256 manifest.
4. `models.qualifying_backtest` prepares legal practice features, groups by
   event, fits Ridge and LightGBM on 2022–2023, selects on 2024, and evaluates
   2025. `models.qualifying_ablation` adds lagged form and repeats the same
   split with two extra models.

## Provider and feature modules

| File and symbol | Input → algorithm → output | Example and proof | Caveat |
|---|---|---|---|
| `data/fastf1_source.py:load_session` | `(year, round/name, FP1/FP2/FP3/Q)` → FastF1 cached load, telemetry/weather/messages disabled for this tabular path → `Session` with laps/results | 2022 R20/R22 built from cached timing; per-event Parquet in `data/processed/qualifying_weekends/` | F1 archive returned 401 for uncached 2023; this loader is not a reliable new-season source now |
| `features/qualifying.py:representative_laps` | FastF1 lap frame → remove missing time, deleted laps, pit in/out; retain laps ≤ 1.03 × each driver's best clean lap → lap frame | A 90.000-second best retains ≤92.700-second laps; see Sprint 1 notebook | 3% is a heuristic, not a fuel/push-lap classifier; it can include traffic or nonrepresentative laps |
| `features/qualifying.py:build_practice_features` | One practice `Session` + prefix → best/top-three/soft/theoretical lap, counts, tyre life, speed trap; normalize gap against event best → one row per driver | If driver best is 91.0s and session best 90.0s, gap is 1.111…% | Optional fields may be null; lap validity follows FastF1 and the filter above |
| `features/qualifying.py:build_qualifying_targets` | Q results → Q1/Q2/Q3 seconds, final classification, Q1 percent gap → target frame | Q1 91.0s vs 90.0s best gives 1.111…% | Targets are unavailable before qualifying and never legal current inputs |
| `features/qualifying.py:build_weekend_dataset` | FP1/2/3/Q sessions → outer practice merge, inner qualifying merge, FP3 team mapping → driver-weekend frame | One conventional GP usually has ~20 rows; `_validate` requires ≥8 FP3 and Q1 observations | Race grid after penalties is separate; FastF1 source may be unavailable |
| `data/qualifying_dataset.py:scheduled_conventional_events` | FastF1 season schedule → filter `EventFormat == conventional`, positive round, chronological sort → round/name list | 2022 schedule returned 19 selected conventional events | Sprint weekends are intentionally excluded because FP3 may not exist |
| `data/qualifying_dataset.py:build_dataset` | Season list → resume/validate per-event Parquet → combined Parquet and ingestion CSV | First run found 17 cached 2022 and one cached 2025; resumed two 2022 events | Failed events remain visible in report; interrupted run may leave per-event files without rewriting combined file |
| `data/enrich_team_metadata.py:enrich` | Existing event Parquet → cached FP3 `Driver`/`Team` lookup → updated event Parquet | 2022 R20/R22 team labels filled from FP3 | Reopens FastF1 sessions and may warn if schedule endpoint is unavailable |

## OpenF1 adapter

| Symbol | Input → algorithm → output | Example and proof | Caveat |
|---|---|---|---|
| `OpenF1Client.get` | Endpoint + sorted query params → SHA-256 keyed JSON cache; uncached HTTP with ≥2.1s spacing and bounded 429/5xx retries → list of records plus response hash | `session_result?session_key=7768` returned 2023 Bahrain Q phase times; local raw cache is ignored by Git | Public historical tier documents 30 requests/minute; a cached response may later be revised upstream |
| `conventional_weekends` | Year `meetings` and `sessions` → sort completed race meetings, number rounds, retain FP1/2/3 + Q with no Sprint session → event descriptors | Unit test keeps rounds 1 and 3 when round 2 is Sprint | Cancelled meetings are excluded from numbering; verify against season schedule when interpreting round IDs |
| `_practice_rows` | Practice `session_result` records → seconds/rank/gap relative to fastest reported lap → driver-number frame | Bahrain 2023 FP3 VER = 92.345s; ALO = 92.340s, so ALO has zero gap | Result best laps are not raw lap series; tyre/sector/representative fields stay null |
| `normalize_weekend` | Four session result lists + Q driver metadata → Q1/Q2/Q3 split, final classification, practice merge, normalized gaps, provider/time labels → driver-weekend frame | Bahrain 2023 Q VER Q1 = 91.295s, classification P1; SAI had fastest Q1 at 90.993s | Q result and metadata are used after the event to construct historical labels/identity; models only use legal pre-Q columns |
| `build_dataset` | Years → resumable per-event fetch, validation, report and combined Parquet | 52 2023–2025 weekends and 1,038 rows with zero errors; `qualifying_openf1_weekends/*.parquet` | API failures are logged; a partial combined file would not prove complete coverage |
| `mixed_qualifying.combine` | 2022 FastF1 per-event files + OpenF1 combined file → source/time/hashes, duplicate check, provider coverage manifest | 71 weekends and 1,418 rows in `qualifying_mixed_2022_2023_2024_2025.parquet` | Mixed providers require the common feature set and broader overlap audit |

## Model and evaluation modules

| Symbol | Input → algorithm → output | Example and proof | Caveat |
|---|---|---|---|
| `qualifying_backtest.prepare_dataset` | Raw driver-weekend rows → derive within-event practice-only gaps; coerce numeric; keep rows with FP3, Q1 target and classification → eligible frame | 2022/2023 training, 2024 validation, 2025 test; `sample_coverage.csv` records drop counts | Excluded drivers change the evaluated field; ranks are within eligible drivers |
| `FEATURES` / `COMMON_FEATURES` | Static legal feature registries → model columns | Common list: FP1/2/3 gap/rank and two gap improvements | Rich features are unsuitable for mixed providers because OpenF1 lacks lap-level values |
| `model_pipelines` | Feature list → train-only median imputer, scaler, one-hot encoder, Ridge(α=20) or LightGBM(150 trees, 12 leaves, seed 42) | Offline synthetic tests fit both | Hyperparameters were fixed before viewing 2025; this is a benchmark, not tuned optimum |
| `scored_positions` | Driver rows + lower-is-faster predicted Q1 score → deterministic within-event rank by score/driver | FP3 90s beats 91s; tie broken stably by driver | Prediction ranks are proxies for final classification |
| `evaluate` | Ranked driver table → per-event position MAE, Spearman, pole hit, top-three overlap | MAE = mean absolute position difference within event | Event means weight every GP equally regardless of eligible driver count |
| `paired_event_bootstrap` | Per-event candidate and FP3 errors → resample paired event differences with seed 42 → mean delta and 95% percentile interval | Three events all −1.0 MAE yield [−1, −1] in unit test | Descriptive uncertainty across sampled events; not future-race calibration |
| `run_backtest` | Dataset, feature set and chronological years → fit on 2022–2023, select lowest 2024 event MAE, evaluate 2025 → tables, coverage and manifest | `test_season_split_and_models_execute` asserts group counts and split | A minimum weekend guard prevents small smoke sets; it does not guarantee representative coverage |
| `historical_qualifying.add_historical_features` | Complete chronology including past labels → sort year/round; driver `shift(1)` before rolling 3/5; one team mean per event before team shift → 12 form columns | If a driver's R1 Q1 gap is 0.5%, their R2 last-3 contains 0.5%; changing R2 labels leaves R2 inputs unchanged in test | Current-year earlier events are legal; team renames reset team history; driver abbreviation is the join key |
| `qualifying_ablation.run_ablation` | Raw rows → same baseline plus form features and two form models; choose among five by 2024 only → validation/test tables, form coverage, bootstrap | Synthetic tests verify first event has no form and current label cannot change current features | Historical form is learned from previous classification, while Q1 is still only a proxy for final Q order |

## Notebooks, scripts and tests

- Notebook 01 explores one Monza 2025 FP3-to-Q comparison; its saved single
  event MAE/Spearman is **not** a held-out generalization estimate.
- Notebook 02 reads baseline CSV/Parquet outputs and visualizes event errors.
- Notebook 03 cells 0–5 describe the ablation and show 2024 selection/2025
  held-out tables; cells 6–7 plot both splits; cells 8–9 inspect historical
  feature availability; cells 10–11 pivot test event errors; cell 12 lists
  interpretation questions. The notebook consumes CLI artifacts; model logic
  is not embedded in its cells.
- `scripts/make_nvim_pairs.sh` uses Jupytext percent format to pair three
  notebooks with text sources. It does not modify Neovim configuration.
- `tests/test_qualifying_backtest.py` checks legal features, within-event
  normalization/ranking, grouped years, duplicate rejection and paired
  bootstrap. `tests/test_historical_qualifying.py` checks lagging and five-model
  execution. `tests/test_openf1_qualifying.py` checks schedule numbering and
  result normalization. These synthetic fixtures test code invariants only;
  real performance comes from the separate historical run.

## Session foundation (partial P0)

| Symbol | Input → algorithm → output | Proof and limit |
|---|---|---|
| `session.contracts.SessionId` | Season, round, kind and provider key → immutable validated identifier | 2025 Monza race uses OpenF1 key 9912; cross-provider ID mapping remains future work |
| `session.contracts.SessionEvent` | Typed payload, source, three UTC timestamps, session seconds, sequence, quality → immutable versioned event | Synthetic validation rejects wrong payload and naive observation time |
| `session.contracts.RaceState` | Session ID and reduced events → one clock, driver dictionary, global flag, race-control messages and event IDs | No UI or live provider is connected yet |
| `session.reducer.reduce_event` | Current state + next ordered event → copied next state; duplicate ID returns same state | Tests cover order, time and session rejection; late packets need a source reorder buffer |
| `session.reducer.seek_state` | Events + cutoff seconds → sort and reduce from start → deterministic state | Test compares forward reduction with arbitrary seek; checkpoints are future work |
| `session.openf1_sample.build_sample` | Cached OpenF1 2025 Monza race-control records → 53 post-start message events and local ignored JSON | Real source SHA in `DATA_CONTRACTS.md`; message timeline only, no positions/laps |

`RaceSource`, `CircuitGeometry`, replay packs and the shared frontend clock are
specified in `SOL61_MASTER_EXECUTION.md` but not implemented. No full
replay/live/simulation result is claimed from these contracts.
