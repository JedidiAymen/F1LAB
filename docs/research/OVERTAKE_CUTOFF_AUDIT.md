# Overtake cutoff and label audit — protocol

This audit uses the saved Race Pace feature frame and previously published Overtake pairs and predictions from foundation `5cdac66677e6abb513f84e3ede5f74dd74d00bb6`. It does not re-train, change or overwrite them. Join each saved pair to the source follower and proposed leader by race, driver and lap; count missing/nonconsecutive next records and records where the leader's lap cutoff is later than the follower's cutoff. Use race IDs present in saved walk-forward predictions to identify previously scored races. Hash the three input files. Timing cutoffs indicate observation times only; provider publication delays and exact physical positions remain uncertain.

Separately, inspect the label design. An order change inferred from gap snapshots is not a verified on-track pass. The published cohort excludes pairs using later pit and neutralization outcomes, so its metrics are conditional on a retrospectively selected population. Do not present them as unconditional live probabilities. Record actual results without assuming their effect on the original model metrics. Any new dataset build must enforce leader feature cutoff ≤ follower cutoff and consecutive next source records, fail on missing timing inputs, and preserve the old artifacts and exact original revision for reproducibility.

## Observed results and impact

The saved dataset has 29,608 pairs. Five contain a proposed leader cutoff later than the follower cutoff; three are in races included in the saved walk-forward predictions. The observed offsets range from 0.065 to 58.893 seconds. All five saved labels are zero, but that does not establish that they have no effect on fitted models or metrics. No saved pair had a nonconsecutive next source record. A strict rebuild has 29,603 pairs, removes exactly those five, adds none, and preserves the labels of shared pairs. Recomputing earlier-race circuit priors after removal changes that feature for 2,364 retained pairs, all in scored races. A subsequent corrected retrospective backtest is reported below; these previously inspected, outcome-selected races are not a fresh confirmatory test.

The source frame SHA-256 is `993cfaeb810883509bd9348e98a3b8a700813f4f509eeddcec22bd2c2e190ece`, the saved pair dataset is `8c25cdbef56555d4594a81e665eef8b5490a68d5dc7220b057f87d6be4be419c`, and saved predictions are `0b15d93c81c4067c16ef4361e3b319259372ac5724b1a7bedc0c5595e54e267c`. The [aggregate audit](evidence/overtake_cutoff_20261101/report.json) SHA-256 is `fc3576989f0253e19292bf2c29fc26d6239231cffda5a0a82ba87019cb3b9a59`; a repeat after the equal-start correction produced the same hash. `scripts/audit_overtake_cutoffs.py` performs the joins, strict rebuild and hash recording; it writes a new file only. Its initial calculation revision was `4a57750dcb8d1f7b41af7d05d01ed262ede2fb3a`; the audit result was independently repeated using the equal-start fix.

`dataset.build` now rejects duplicate race/driver/lap keys and absent or invalid cutoffs, requires the leader cutoff to be no later than the follower cutoff, and requires both next source records to be exactly lap L+1. Earlier-race circuit rates now exclude all races with the same start timestamp, preventing tie-order leakage. These measures do not make the retrospectively filtered population unconditional, verify the label as a real pass, fix provider publication-time uncertainty or establish precise track position. Missing or late data are excluded rather than replaced with a speculative other leader.

`GET /api/v1/overtake/cutoff-audit` provides the checksum-verified aggregate and affected-pair details. The Overtake workspace labels its saved scores provisional and explains the later-outcome exclusions; The separate historical explorer shows saved out-of-fold predictions and decision cutoffs for the corrected cohort when local artifacts are available; it does not execute a live model. Dataset and benchmark CLI outputs refuse to overwrite existing pair, prediction or summary artifacts; specify new output directories. The old benchmark remains reproducible by checking out its original foundation revision and retaining its original inputs. OpenF1 source terms and upstream timing-rights caveats apply; no raw timing data is newly redistributed.

```bash
PYTHONPATH=src .venv/bin/python scripts/audit_overtake_cutoffs.py \
  --pace data/processed/race_pace/pace_frame.parquet \
  --pairs data/processed/overtake/pairs.parquet \
  --predictions data/processed/overtake/predictions.parquet \
  --out data/processed/overtake/cutoff_audit_new/report.json
PYTHONPATH=src .venv/bin/python -m f1_racelab.ml.overtake.dataset \
  --pace data/processed/race_pace/pace_frame.parquet --out data/processed/overtake/new_dataset
PYTHONPATH=src .venv/bin/python -m f1_racelab.ml.overtake.benchmark \
  --pairs data/processed/overtake/new_dataset/pairs.parquet --out data/processed/overtake/new_benchmark
```

The commands above reproduce the dataset and backtest in new directories. Next, register a genuinely prospective target and selection policy, distinguish verified passes from pit/retirement/penalty effects, establish source publication timing, retrain chronologically on a versioned dataset, and evaluate calibration and uncertainty without reusing inspected events as untouched tests.

Rendered audit UI screenshots from the locally available research artifacts: [desktop](../images/overtake-audit-desktop.png) and [mobile](../images/overtake-audit-mobile.png). The figures display aggregate evidence and the selected saved timing pair; they are not screenshots of live race inference.

## Corrected retrospective experiment, 2026-11-01

The registered re-run at training source revision `b9b2db0b9120d164ca5fab281d09b595059fda5a` used the same previously inspected races, not an untouched test. The strict dataset contains 29,603 pairs in 85 races and 1,595 timing-order swaps; 22 walk-forward folds scored 22,634 pairs across 65 races. The hashes and versions are in the [manifest](evidence/overtake_corrected_20261101/manifest.json), with the full [summary](evidence/overtake_corrected_20261101/summary.json). Training used Python 3.12.13, LightGBM 4.7.0, scikit-learn 1.9.1, four OpenMP threads and one OpenBLAS thread. It took 8.59 seconds and 291,360 KB peak RSS on this machine. This is not a controlled hardware benchmark.

| Model | Brier | Log loss |
| --- | ---: | ---: |
| Training rate | 0.049449 | 0.205061 |
| Gap-only logistic | 0.040755 | 0.149358 |
| All-feature logistic | 0.033463 | 0.121924 |
| Raw LightGBM | 0.032841 | 0.117176 |
| Calibrated LightGBM | 0.033553 | 0.123577 |

Raw LightGBM's paired Brier difference against gap-only logistic is −0.007914, race-cluster bootstrap 95% interval [−0.010563, −0.005582] (65 races, 5,000 draws, seed 42). This is a comparison **within this retrospectively selected, already inspected cohort**, not evidence of prospective improvement. The original cohort and metrics differ and should not be compared as a controlled before/after experiment. Model scores do not validate physical on-track passes or provider publication times.

The strict pairs SHA-256 is `d159df2087178bce480ba42b51b254b35b3e5e7f795ab1d8b0fefc6e678849fa`; predictions SHA-256 is `0498947116dbde48c7844c6aed615f42184b5aee12389f4972479685733106d4`. Dataset, predictions and 22 fitted fold artifacts remain locally in `data/processed/overtake/cutoff_strict_20261101_dataset/` and `data/processed/overtake/cutoff_strict_20261101_run/`. Independently reloading these trusted local artifacts and reproducing all 113,170 model/pair predictions yielded maximum absolute difference 0.0. Hashes detect inconsistency, not authenticity; never deserialize an untrusted joblib file. The API reads parquet predictions, not joblib models.

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=4 PYTHONPATH=src .venv/bin/python -m f1_racelab.ml.overtake.dataset --pace data/processed/race_pace/pace_frame.parquet --out data/processed/overtake/new_dataset
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=4 PYTHONPATH=src .venv/bin/python -m f1_racelab.ml.overtake.benchmark --pairs data/processed/overtake/new_dataset/pairs.parquet --out data/processed/overtake/new_benchmark
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=4 PYTHONPATH=src .venv/bin/python scripts/verify_overtake_folds.py --pairs data/processed/overtake/new_dataset/pairs.parquet --run data/processed/overtake/new_benchmark
```

The local explorer validates dataset, source, prediction and summary hashes, joins cutoffs and displays saved model probabilities and later observed timing outcomes. It is not online inference. Source provider latency, unpublished positions and the selected population remain unresolved. Its default artifact locations are intentionally local; a clean checkout shows an unavailable message until the reproducible research inputs exist.

Rendered saved-forecast explorer: [desktop](../images/overtake-history-desktop.png) and [mobile](../images/overtake-history-mobile.png). Captured from the local research artifacts, not a live feed.


## Further source-feature audit — 2026-11-01

The cutoff repair does **not** make all model inputs decision-time safe. In `pace.dataset.build_race_frame`, `laps_remaining` uses the maximum lap number found after the race, which can reveal an eventual shortened distance rather than a pre-race scheduled distance. Overtake uses that field directly, and also uses `tyre_age_next` and `compound_next`, derived from the following lap's stint. The outcome-selected no-pit cohort does not establish that these values were available to an unconditional forecast at the cutoff. The saved original and corrected experiments must remain retrospective and provisional; the 22 fitted models and reported scores are not evidence for as-of deployment. The size of any score change after removing these features is not yet measured. No old artifacts or scores were overwritten.

The broader pace frame's `laps_in_stint` and `stint_best_delta` also derive from the next-lap stint; its clean-lap and regime calculations use subsequent pit-out status and a full-race median lap time. The existing Race Pace “strict” result therefore has unresolved decision-time provenance as well. A new prospective cohort and causally reconstructed features are required before making strict as-of or live-inference claims. Provider publication timing remains another unresolved limitation.
