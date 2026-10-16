# Phase-aware qualifying Prediction Lab

**Milestone date:** 2026-10-16. **Starting source SHA:**
`d60c36f77295075bd50a1950ccabefc7eb5022b9` on `feat/foundation`.
**Status:** implemented as an offline historical research slice; it is not an
operational forecast or production model.

## Scope and temporal contract

The Prediction Lab now compares three separately trained snapshots:

| Snapshot | Recorded cutoff | Legal pace inputs | Measured baseline |
|---|---|---|---|
| After FP1 | Scheduled FP1 end | `fp1_gap_pct`, `fp1_rank` | FP1 best lap |
| After FP2 | Scheduled FP2 end | FP1 and FP2 gap/rank | FP2 best lap |
| Before qualifying | Scheduled FP3 end | FP1/FP2/FP3 gap/rank and FP1→FP3 / FP2→FP3 gap improvement | FP3 best lap |

The event schedule comes from the cached OpenF1 `/sessions` response. For each
phase, the code requires the latest included practice's scheduled end to be no
later than the next scheduled session start. The archived `session_result`
features are assigned to that practice phase, but OpenF1 publication times for
individual result rows were not retained. A scheduled end is therefore a
research cutoff label; it does **not** prove that every final practice result
was already visible to an external forecaster at that instant.

This run uses OpenF1 for every split. FastF1 2022 remains in the earlier mixed
dataset, but its cached schedule could not be read offline in this environment.
The phase experiment consequently uses 2023 for training, 2024 for validation
and model selection, and 2025 as untouched holdout. That keeps provider
semantics consistent across this experiment, at the cost of reducing the
training window from 35 to 16 weekends.

The target is Q1 relative pace (`q1_gap_pct`); predictions are sorted within a
weekend and evaluated against final qualifying classification. It is not the
race starting grid. For each phase, Ridge and LightGBM are compared with that
phase's measured practice baseline. The selected model minimizes 2024 event
mean position MAE. 2025 results do not select the model. A 10,000-draw seeded
event bootstrap (`seed=42`) estimates candidate-minus-baseline rank-MAE
differences; units are positions and these intervals are descriptive, not
calibrated probabilities.

All predicted and actual ranks, leader-hit and top-three metrics are computed
within the phase's eligible driver cohort. The API/UI also shows official
qualifying position separately: eligible rank 1 can be official P2 or lower
when faster drivers have no measured phase baseline. Cohorts differ across
phases, so these results alone do not measure the benefit of waiting for a
later practice; that needs a shared-cohort comparison.

## Implementation map

- `src/f1_racelab/models/qualifying_phases.py`
  - `cached_openf1_sessions`: reads local cached schedule JSON only.
  - `phase_event_schedule`: maps source meeting keys to practice end times,
    validates the next-session boundary, and hashes canonical schedule rows.
  - `run_phase_experiment`: builds three phase-specific eligible cohorts,
    trains/selects/evaluates models, and records per-event cutoffs.
  - `write_experiment`: writes predictions, summaries, event metrics,
    bootstrap intervals, and checksum manifest under ignored local data.
- `src/f1_racelab/models/qualifying_backtest.py`
  - `run_backtest` now accepts a baseline name and measured baseline column;
    defaults preserve the original FP3 experiment.
- `src/f1_racelab/models/qualifying_phase_lab.py`
  - Validates phase allowlists, target/split contracts, per-driver model
    coverage, rank permutations, manifest counts, rank-derived metrics and
    SHA-256 checksums before projecting event ranks.
- `src/f1_racelab/api.py`
  - Adds `/api/v1/predictions/qualifying/phases` and
    `/api/v1/predictions/qualifying/phases/event`.
- `apps/web/src/components/PredictionLab.tsx`
  - Adds FP1, FP2 and pre-qualifying selection, phase-specific metrics and
    rankings, source cutoff display and timing caveat.
- `tests/test_qualifying_phases.py` and `apps/web/e2e/replay.spec.ts`
  - Check schedule boundaries, phase feature legality, chronological split,
    missing-artifact integrity, route projections and browser phase switching.

The serving API omits `q1_gap_pct` and the raw `final_position` field name and
projects official classification as `qualifying_position` alongside eligible
actual and predicted ranks. The UI labels actual classification as historical scoring. Artifacts are local and
checksum-verified; the API makes no provider requests.

## Real cached experiment

Input is `data/processed/qualifying_mixed_2022_2023_2024_2025.parquet`, filtered
to the OpenF1 2023–2025 rows (1,038 source rows), with dataset SHA-256
`eef5a7277d2f62fdf263e94cadbc7a5f5c38cd6acdbea9dc00549d5caef37fd8`.
Canonical session schedule SHA-256 is
`af8ce323bb62591d925fded4fdaf696276921a305bb26fbc970573579d82734d`.
The prediction Parquet SHA-256 is
`db7232189404da2f74970d20d1f69d65b082c128252e4b908308651857a79fe1`.

Eligible driver counts differ by phase because rows without that phase's
measured practice baseline are excluded rather than imputed:

| Phase | 2023 training | 2024 validation | 2025 holdout | Selected on 2024 |
|---|---:|---:|---:|---|
| After FP1 | 275 drivers / 16 events | 325 / 18 | 319 / 18 | Ridge |
| After FP2 | 310 / 16 | 333 / 18 | 351 / 18 | Ridge |
| Before qualifying | 311 / 16 | 342 / 18 | 354 / 18 | FP3 baseline |

The held-out results are:

| Phase | Selected on 2024 | Practice baseline MAE | Ridge MAE | Ridge − baseline and 95% paired event interval |
|---|---|---:|---:|---:|
| After FP1 | Ridge | FP1 3.7245 | 3.6736 | −0.0508 [−0.1676, +0.0628] |
| After FP2 | Ridge | FP2 3.6802 | 3.4827 | −0.1975 [−0.4056, +0.0218] |
| Before qualifying | FP3 baseline | FP3 3.3141 | 3.3100 | −0.0041 [−0.2617, +0.2626] |

All three 2025 Ridge-vs-practice-baseline intervals cross zero. The small
pre-qualifying Ridge point difference is not the selected validation model and
does not establish superiority. Validation selected Ridge after FP1 and FP2;
the corresponding validation mean MAEs were 3.3744 vs FP1 3.5924 and 3.0788
vs FP2 3.4291. Before qualifying, validation selected the FP3 baseline at
2.8975 positions MAE.

Cutoff records cover 52 OpenF1 conventional weekends. In each phase they span
the 2023 opening event through the 2025 Abu Dhabi weekend. Event-specific
coverage in the UI remains visible; for example, the latest 2025 FP1 snapshot
has 11 measured drivers, while later-practice records have wider coverage.

Generated local artifacts (ignored by git):

- `data/processed/qualifying_phases/phase_predictions.parquet`
- `data/processed/qualifying_phases/phase_summary.csv`
- `data/processed/qualifying_phases/phase_event_metrics.csv`
- `data/processed/qualifying_phases/phase_bootstrap.csv`
- `data/processed/qualifying_phases/experiment.json`

The other report hashes are in `experiment.json` and in the worklog. No
provider data or generated predictions were added to the repository.

## Reproduction and verification

The reproduction used existing ignored local source data and schedule cache;
no network request was made:

```bash
.venv/bin/python -m f1_racelab.models.qualifying_phases \
  --dataset data/processed/qualifying_mixed_2022_2023_2024_2025.parquet
.venv/bin/pytest -q
.venv/bin/ruff check src/f1_racelab tests
.venv/bin/mypy src/f1_racelab/models/qualifying_backtest.py \
  src/f1_racelab/models/qualifying_phases.py \
  src/f1_racelab/models/qualifying_phase_lab.py src/f1_racelab/api.py \
  --follow-imports=silent --ignore-missing-imports
cd apps/web
npm run test:unit
npm run build
npm run lint
npm run test:e2e
```

The Python suite reports 65 passed and one existing Starlette/httpx
deprecation warning. Frontend unit tests report 5 passed. Build, lint, Ruff and
scoped mypy pass. Ten Chromium scenarios and screenshot inspection pass;
exact results are in `TEST_EVIDENCE.md`.

Verified environment: Python 3.12.13, pandas 2.3.3, NumPy 2.5.3,
scikit-learn 1.9.1, LightGBM 4.7.0, pytest 9.1.1, Node v22.23.2 and npm
10.9.8. The final targeted browser scenario also verifies eligible leader vs
official qualifying position and the selected validation year in the interval
label.

Source reference: [OpenF1 API documentation](https://openf1.org/docs/) and
[OpenF1 license](https://github.com/br-g/openf1/blob/87540e3f495bbd9bedb37b10456dd848c8f193d6/LICENSE).
This work uses cached public API fields; it copies no provider code and commits
no raw timing records.

## Bugs, caveats and next work

- The first real run exposed FP1 baseline rows with missing measured best
  times. Those rows are now excluded per phase, and phase counts are recorded;
  no missing pace is fabricated. Review also found the shared evaluator still
  required FP3 for early-phase rows; it now requires only that phase's measured
  baseline, Q1 target and classification.
- The FastF1 offline 2022 schedule was unavailable, so phase chronology begins
  with OpenF1 2023. Reintroduce 2022 only when source schedule timestamps and
  provider semantics can be audited.
- Scheduled practice end is not exact data publication time. Preserve that
  label in any future display; do not describe these results as a live or
  exact as-of replay.
- No feature-value timestamps, probability calibration, 2026 walk-forward,
  driver transfer identity resolution, or external inference endpoint exists.
- The model remains a Q1-pace proxy evaluated against final qualifying order.

The next prediction work should secure timestamped/archived feature
availability and expand cross-provider overlap checks. In parallel, the
roadmap's P2 geometry and rendering performance work remains open; strategy,
what-if, live and 3D phases are not started. The milestone implementation and
this documentation are committed and pushed together; final publication SHA
is recorded in the handoff/worklog follow-up.
