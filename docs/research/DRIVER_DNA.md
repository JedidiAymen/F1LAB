# Driver DNA: can lap telemetry separate drivers?

Status: evaluated on real data; no deployed model; results are read-only in the UI (`GET /api/v1/driver-dna/summary`, workspace "Driver DNA").

## Data
OpenF1 `car_data` (about 3.7 Hz), `laps`, `drivers`; cached locally, git-ignored, non-commercial licence (see `DATA_CONTRACTS.md`). Only three races have full-race telemetry locally: Monaco 2023, Brazil 2024, Monza 2025 (60 driver files, 2.29 M samples). `ml/driver_dna/dataset.py` keeps race laps that are not pit-out or in-laps, are within 1.07x the driver's median lap time (a label-free quality filter) and have no sample gap above 1 s, and resamples speed, throttle, brake, gear, rpm and DRS-open to 256 points of integrated lap distance. Result: **1,749 laps**; 11 drivers race in all three events (ALO, GAS, HAM, LEC, NOR, OCO, PIA, RUS, SAI, TSU, VER). Command: `uv run python -m f1_racelab.ml.driver_dna.dataset`.

## Protocol (fixed before scoring; `ml/driver_dna/protocol.py`)
* **Task A, cross-circuit identity.** Leave one circuit out, 11 shared drivers, chance 9.1%. Laps are z-scored per circuit and grid point using that circuit's laps only, no labels.
* **Task B, teammate discrimination.** Inside a race, which of two teammates drove a lap. Train on laps up to the 60th percentile of lap number, skip 3 laps, test on the rest; 19 pairs qualified; bootstrap over pairs. The majority baseline is 50.9%.

## Models
Handcrafted 17 descriptors (`handcrafted.py`) with logistic regression and LightGBM; dilated residual TCN (about 75 k parameters); SimCLR-style contrastive encoder pre-trained without labels, then a logistic head (`nets.py`). Neural runs use seeds 42, 7, 123 on an RTX 3050; the whole neural evaluation took 296 s with deterministic cuDNN kernels (an earlier non-deterministic run differed by under 1 point, same conclusions). Commands: `uv sync --extra dl`, `uv run python -m f1_racelab.ml.driver_dna.baselines`, `uv run python -m f1_racelab.ml.driver_dna.evaluate_nets`.

## Results (real data)
| Model | Task A accuracy | Task B accuracy [95% CI over pairs] |
|---|---|---|
| chance / majority | 9.1% | 50.9% |
| handcrafted + logistic | 38.4% | 88.8% [81.8, 95.0] |
| handcrafted + LightGBM | 30.2% | 83.6% [76.4, 90.5] |
| TCN (3 seeds) | 39.8% (35.8-43.4) | 89.7% [84.8, 94.0] |
| contrastive + logistic | 23.1% | 80.4% [73.8, 86.7] |

Task B controls: lap number and lap time alone 53.5% [48.9, 59.3]; shape features without absolute speed/rpm level 88.3% [81.7, 93.7]; shuffled teammate labels 48.2%.

## Interpretation and limits
* Telemetry shape separates teammates far above chance and above what pace or stint position explains, so a driver-related signal exists in these laps.
* **The neural models do not clearly beat simple handcrafted features plus logistic regression**: the TCN's intervals overlap the baseline's in both tasks, and the contrastive encoder is worse. The extra complexity is not justified by this data.
* Teammates also differ by car set-up, tyre state and traffic; the controls remove pace and stint position only. This is separability of sampled laps, not proof of innate driving style.
* Task A cannot separate driver from car for drivers who kept the same team. By-driver accuracy is in `baselines.json` and `nets.json`; Monza is hardest (TCN 15.9%).
* Three races and 11 shared drivers is small; no claim should be made about the wider grid. More sessions can be added by fetching `car_data` (about 120 MB per race).

## EXP-DNA-NORM-01 — normalization availability audit (2026-10-31)

Source checkpoint `7238387d206125413d1403b739909cc3e787bade`, with modified
worktree. The original Task A scores use **transductive** normalization: each
circuit's mean/std includes the full unlabeled held-out circuit cohort. The
neural protocol also uses full-circuit moments before teammate splitting.
No held-out labels are used in those moments, but this is still different from
training-only preprocessing. It can be legitimate offline domain adaptation;
it is not evidence of performance on a new circuit without access to its cohort.
Original artifacts/results remain unchanged and are now explicitly labeled.

Implemented `protocol.fit_train_normalization` / `apply_train_normalization`:
input `[N, features...]` tensors and explicit unique training indices; fit mean
and std in float64 over training rows only, add `1e-6` to scale, make fitted
arrays read-only; output dimensionless float32 z-scores. Reject empty/invalid
indices, nonfinite train/transform data and incompatible shapes. A held-out
poisoning regression proves that changing test values cannot change fitted
statistics or training transforms. These tensor helpers are available for a
future inductive neural study; **no new neural model was trained** here.

`normalization_study.py` reuses the existing inspected dataset/split indices and
original model factories. It compares the original per-circuit handcrafted
standardization with raw handcrafted descriptors: logistic's StandardScaler and
classifier fit only on each training fold, and LightGBM only fits training data.
No held-out circuit mean/std is used in the latter condition. Same 1,749 laps,
three races, 11 shared drivers; Task A scores 1,046 shared-driver laps, Task B
19 teammate pairs. Training-only normalization does not make the retrospective
quality filter or closed shared-driver vocabulary a fully online protocol.

| Model | Task A original transductive | Task A train-only normalization | Task B original | Task B train-only [95% pair-bootstrap CI] |
| --- | ---: | ---: | ---: | ---: |
| Handcrafted logistic | 38.43% | **19.79%** | 88.80% | 88.80% [81.82,95.04] |
| Handcrafted LightGBM | 30.21% | **12.33%** | 83.59% | 83.92% [76.52,90.76] |

Train-only Task A by held-out circuit (Brazil / Monaco / Monza): logistic
18.87% / 23.81% / 13.76%; LightGBM 9.07% / 16.67% / 10.09%. Uniform chance
is 9.09%, not a class-imbalance-adjusted majority baseline. With three circuits,
do not claim a significant improvement or broad generalization. The large
cross-circuit drop shows how much the earlier result depends on unlabeled
target-circuit normalization. This is a negative availability finding, not a
reason to replace a stronger simple model with a neural model.

Task B logistic's equality is expected: an affine same-circuit preprocessing
step is cancelled by its training-only StandardScaler (up to roundoff). Tree
results differ slightly; the paired uncertainty does not establish a gain.
The original TCN/contrastive scores cannot be compared directly to these new
train-only scores; there is **no** inductive neural benchmark yet.
Handcrafted `accel_p95`/`decel_p05` are adjacent normalized-distance-grid speed
changes, not physically measured longitudinal acceleration in m/s².

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 \
  .venv/bin/python -m f1_racelab.ml.driver_dna.normalization_study
.venv/bin/pytest -q tests/test_driver_dna_normalization.py -W ignore
# API: existing GET /api/v1/driver-dna/summary
# UI: Driver DNA → training-only normalization comparison
```

Output `data/processed/driver_dna/normalization_study.json` plus SHA sidecar;
source SHA/dirty flag, dependencies, complete per-circuit/per-pair scores and
input hashes are recorded. Inputs unchanged:
`laps.npz` SHA `d58b779dd532c5ae9aa5e435a4d774ee49e33703aa52c8f5355308c56cfd774f`;
`laps_meta.parquet` SHA `df74abadef5adeb3a9c920a902aeb171240631227d909df3c8e26048de8c5b12`.
Output SHA `ba8e21be1b2ccef3f381409d3db0a6de700d090b450e39cb0915e8221b4670b4`.
Data source/license is unchanged: cached [OpenF1](https://openf1.org/docs/),
with the project's non-commercial/source-rights caveats in `DATA_CONTRACTS.md`.
No new provider requests, footage or source data redistribution.

API serves the additional study when present and verifies its sidecar; missing
optional study retains old results with explicit transductive warnings; altered
study fails closed. UI shows both protocols and warns against cross-protocol
neural comparisons. Synthetic tests cover held-out poisoning, zero variance,
shape/finite/index validation, optional report and checksum tamper. Real-data
browser test selects Driver DNA and verifies the 19.8% result and warnings.
This milestone fixes the normalization distinction; expansion beyond three
races, inductive neural training, masked/self-supervised encoders, future-segment
prediction, corner modeling and embedding retrieval remain not done.
