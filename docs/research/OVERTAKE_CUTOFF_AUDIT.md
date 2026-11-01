# Overtake cutoff and label audit — protocol

This audit uses the saved Race Pace feature frame and previously published Overtake pairs and predictions from foundation `5cdac66677e6abb513f84e3ede5f74dd74d00bb6`. It does not re-train, change or overwrite them. Join each saved pair to the source follower and proposed leader by race, driver and lap; count missing/nonconsecutive next records and records where the leader's lap cutoff is later than the follower's cutoff. Use race IDs present in saved walk-forward predictions to identify previously scored races. Hash the three input files. Timing cutoffs indicate observation times only; provider publication delays and exact physical positions remain uncertain.

Separately, inspect the label design. An order change inferred from gap snapshots is not a verified on-track pass. The published cohort excludes pairs using later pit and neutralization outcomes, so its metrics are conditional on a retrospectively selected population. Do not present them as unconditional live probabilities. Record actual results without assuming their effect on the original model metrics. Any new dataset build must enforce leader feature cutoff ≤ follower cutoff and consecutive next source records, fail on missing timing inputs, and preserve the old artifacts and exact original revision for reproducibility.

## Observed results and impact

The saved dataset has 29,608 pairs. Five contain a proposed leader cutoff later than the follower cutoff; three are in races included in the saved walk-forward predictions. The observed offsets range from 0.065 to 58.893 seconds. All five saved labels are zero, but that does not establish that they have no effect on fitted models or metrics. No saved pair had a nonconsecutive next source record. A strict rebuild has 29,603 pairs, removes exactly those five, adds none, and preserves the labels of shared pairs. Recomputing earlier-race circuit priors after removal changes that feature for 2,364 retained pairs, all in scored races. **No corrected model has been trained and no corrected score or improvement has been established.**

The source frame SHA-256 is `993cfaeb810883509bd9348e98a3b8a700813f4f509eeddcec22bd2c2e190ece`, the saved pair dataset is `8c25cdbef56555d4594a81e665eef8b5490a68d5dc7220b057f87d6be4be419c`, and saved predictions are `0b15d93c81c4067c16ef4361e3b319259372ac5724b1a7bedc0c5595e54e267c`. The [aggregate audit](evidence/overtake_cutoff_20261101/report.json) SHA-256 is `fc3576989f0253e19292bf2c29fc26d6239231cffda5a0a82ba87019cb3b9a59`; a repeat after the equal-start correction produced the same hash. `scripts/audit_overtake_cutoffs.py` performs the joins, strict rebuild and hash recording; it writes a new file only. Its initial calculation revision was `4a57750dcb8d1f7b41af7d05d01ed262ede2fb3a`; the audit result was independently repeated using the equal-start fix.

`dataset.build` now rejects duplicate race/driver/lap keys and absent or invalid cutoffs, requires the leader cutoff to be no later than the follower cutoff, and requires both next source records to be exactly lap L+1. Earlier-race circuit rates now exclude all races with the same start timestamp, preventing tie-order leakage. These measures do not make the retrospectively filtered population unconditional, verify the label as a real pass, fix provider publication-time uncertainty or establish precise track position. Missing or late data are excluded rather than replaced with a speculative other leader.

`GET /api/v1/overtake/cutoff-audit` provides the checksum-verified aggregate and affected-pair details. The Overtake workspace labels its saved scores provisional and explains the later-outcome exclusions; it does not provide interactive historical-cutoff inference. Dataset and benchmark CLI outputs refuse to overwrite existing pair, prediction or summary artifacts; specify new output directories. The old benchmark remains reproducible by checking out its original foundation revision and retaining its original inputs. OpenF1 source terms and upstream timing-rights caveats apply; no raw timing data is newly redistributed.

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

The commands for rebuilding/rebenchmarking are instructions, not claims that corrected metrics were measured. Next, register a genuinely prospective target and selection policy, distinguish verified passes from pit/retirement/penalty effects, establish source publication timing, retrain chronologically on a versioned dataset, and evaluate calibration and uncertainty without reusing inspected events as untouched tests.

Rendered audit UI screenshots from the locally available research artifacts: [desktop](../images/overtake-audit-desktop.png) and [mobile](../images/overtake-audit-mobile.png). The figures display aggregate evidence and the selected saved timing pair; they are not screenshots of live race inference.
