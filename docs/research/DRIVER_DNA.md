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
