# Agent worklog

## 2026-10-15 UTC — M1/M2, qualifying source recovery and evaluation setup

- **Before:** branch `feat/foundation`, HEAD
  `bb840d44a2cf6c2f325f6ef2a575ff074f0d1b05`. Existing local changes
  included `pyproject.toml`, `uv.lock`, Sprint 3 source/tests/notebook, scripts
  and new mandate documents. All were preserved.
- **Objective:** make the existing qualifying experiment executable against
  real 2022–2025 seasons, then use legal common features for the baseline and
  historical-form ablation. This implements the first dependent slice of the
  locked product, not the entire workstation.
- **Inspected:** `AGENTS.md` and `SOL61_MASTER_EXECUTION.md` completely;
  original feature builder, ingestion, model/test code, notebook 03, package
  configuration, cached Parquets and prior ingestion log.
- **Finding:** 360-row combined dataset lacked 2023 and 2024. The earlier log
  showed FastF1 500 calls/hour failures. On resumption, two remaining cached
  2022 weekends completed, but uncached 2023 F1 timing failed; one direct URL
  returned HTTP 401. The interrupted command did not rewrite the combined
  artifact. OpenF1 public history returned the needed 2023 result schema.
- **Files changed/created this checkpoint:** `.gitignore` (notebook checkpoint
  exclusion), `pyproject.toml` (pytest testpaths, preserving user-added Jupyter
  dependencies), `data/fastf1_source.py` (disable unused weather fetch),
  `features/qualifying.py` (deleted-lap flag handling and FP3 team labels),
  `data/openf1_qualifying.py` (cached, paced provider adapter),
  `data/mixed_qualifying.py` (provider-labelled merge),
  `models/qualifying_backtest.py` (common feature set, paired event bootstrap,
  sample coverage), `models/qualifying_ablation.py` (same feature set and
  uncertainty), `features/historical_qualifying.py` (bind rolling window),
  `tests/test_openf1_qualifying.py` and existing test files (normalization,
  schedule, common-feature and bootstrap checks), plus the documentation listed
  below. Untracked Sprint 3 files remain uncommitted until real results pass.
- **Algorithm:** normalize practice gap as
  `100 × (driver best seconds / event best seconds − 1)`; Q1 uses the same
  equation over Q1 times. Fit on 2022–2023, select by 2024 event-mean MAE,
  evaluate 2025 only after selection. `add_historical_features` shifts each
  driver/team qualifying result before a 3/5-event rolling mean. The bootstrap
  resamples paired candidate-minus-FP3 event MAE, not individual drivers.
- **Data flow/source:** FastF1 3.8.3 cached 2022 event Parquets plus OpenF1 v1
  meeting/session/result/driver JSON for 2023–2025; exact field and hash
  semantics are in `DATA_CONTRACTS.md`. OpenF1 API documentation:
  https://openf1.org/docs/ . No third-party code was copied; provider JSON
  is local ignored data. Public historical free tier is paced at 2.1s/request.
- **Tests/commands:** initial `uv run pytest -q` failed from collecting
  `references/`; setting `testpaths = ["tests"]` yielded 10 passes. After new
  adapter and bootstrap tests, `.venv/bin/pytest -q` yielded 14 passes. Full
  OpenF1 ingestion completed with 52 weekends and 1,038 rows; mixed data had
  71 weekends and 1,418 rows. Baseline and form ablation ran on 35/18/18
  eligible train/validation/test events. Ridge won 2024 validation; 2025
  Ridge MAE 3.2433 vs FP3 3.3141, paired interval [-0.2934, +0.1587]. Form
  did not win validation. Shared 2025 Monza provider times matched on all
  available pairs, and a three-event VER driver/team form trace was checked.
  Notebook 03 executed with zero cell errors. Final scoped test run passed
  16/16 and Ruff passed. Detailed evidence:
  `TEST_EVIDENCE.md` and `EXPERIMENT_REGISTER.md`.
- **Caveats:** OpenF1 session results provide best lap, not tyre/sector/lap
  series; common-source comparison is necessary. This is Q1 pace predicting
  final Q classification, not grid prediction. 2025 was not used to choose
  model settings. Cross-provider overlap was audited for one event only. No probability
  calibration, replay or strategy engine exists yet.
- **After:** commit SHA and push state pending verification; current worktree
  contains preserved user changes plus this checkpoint work.
- **Next:** run final checks; commit/push a safe checkpoint; start canonical
  session contracts and a real replay fixture.
