# Driver DNA future forecast failure analysis

Status: **exploratory, previously inspected events; no new model or untouched test**. This is a stacked follow-up to [PR #4](https://github.com/JedidiAymen/F1LAB/pull/4), based on `968013b937ed352ffb8ae2b5c3c66efd8582de14`. The [registered slice protocol](DRIVER_DNA_FAILURE_PROTOCOL.md) fixes thresholds before this decomposition but after the original full-cohort results had been examined. Input `study.json` SHA-256 `09949690cae00168d33a6db969fd612b93783fe3523251abb35ccaaf52ee8265`; saved predictions SHA-256 `c0bd6e95964aaa3368ba72697e9671c5c51ec247688998ffc39f76c9f2ec8bc0`. The [aggregate report](evidence/dna_future_failures_20261101/report.json) SHA-256 is `1e45d763bb33f6fbd33788556594d83c4c5ed0fc07e011c83aad9c6a5c9e2848`; a separate repeat produced identical bytes.

## What the saved forecasts show

The original primary result is unchanged: on all 1,597 completed-lap test prefixes, persistence MAE is 5.2198 s, standard TCN seed 7 is 8.1130 s, no-head-context seed 42 is 6.7989 s, and masked seed 42 is 8.0249 s. The no-head-context model still adds a residual to the last-lap anchor. No model is promoted.

The first grouping below uses **future completed-lap outcome** to describe errors after the fact. It is not available at forecast time, is not a model input, and cannot be used to construct a deployable regime switch. It does not identify pit, safety-car or tyre causes.

| Absolute observed lap change from last lap | Laps | Persistence MAE | TCN seed 7 MAE | TCN minus persistence, conditional 95% interval |
| --- | ---: | ---: | ---: | ---: |
| ≤1 s | 1,097 | 0.279 s | 4.577 s | +4.298 s [3.884, 4.783] |
| >1–5 s | 211 | 2.029 s | 7.611 s | +5.581 s [4.258, 7.073] |
| >5 s | 289 | 26.304 s | 21.903 s | −4.401 s [−6.980, −2.476] |

Thus 68.7% of the sampled test laps have an observed change at most one second, where persistence is difficult to beat. The >5-second group contributes roughly 7,602 of 8,336 total absolute-error seconds to persistence. Seed 7 has lower error in that **outcome-selected** subgroup but is substantially worse on the more common small-change groups and worse overall; the subgroup contrast does not establish an actionable or generalizable advantage. It cannot explain which physical events caused the changes.

For an as-of grouping based on the gap between the last completed lap and the median of up to three completed prior laps, the ≤1 s slice contains 1,231 laps: persistence MAE 2.369 s versus TCN seed 7 5.641 s. The >5 s prior-gap slice contains 217 laps: persistence 17.375 s versus TCN seed 7 17.285 s, paired difference −0.090 s with conditional interval [−3.696, 2.441]. These are retrospective observation-time assumptions; provider publication latency is not verified. Thresholds are conventions, and results do not establish an operational gating policy.

The code resamples session/driver clusters 2,000 times with seed 42, retaining correlated laps within a cluster. Intervals are conditional on these two already-inspected events and do not quantify performance on new circuits, seasons or populations. Australia and Japan are confounded with the 2026 season boundary. Training correction correlations are in-sample and do not imply causal feature effects. Full event, model, correction and slice values are in the aggregate report.

## Implementation and reproduction

`scripts/analyze_dna_future_errors.py` verifies the study and prediction hashes, checks event identities/keys/finiteness, computes the fixed slices and writes a new report without overwriting existing evidence. `GET /api/v1/driver-dna/future-failures` verifies the bundled report against the original study; the Driver DNA future-performance view offers slice/model selectors, a linked MAE chart, a table with paired intervals, and explicit as-of/outcome warnings. The source experiment and trained weights are unchanged. This is not multi-horizon retraining, expanded data, Corner Intelligence or Driver DNA 3.0 completion.

```bash
PYTHONPATH=src .venv/bin/python scripts/analyze_dna_future_errors.py \
  --input data/processed/driver_dna_future/verified \
  --out data/processed/driver_dna_future/error_analysis_new/report.json
```

The local input artifacts require the original PR #4 reproduction and applicable [OpenF1 terms](https://github.com/br-g/openf1/blob/main/LICENSE); only aggregate metrics are bundled. Subsequent work should obtain genuinely fresh sessions, audit their source coverage, register prospective input and split contracts, compare multi-horizon models and uncertainty against persistence, and retain disruptions and negative findings.

The analysis code revision used for the recorded calculation is `49cc5de069b5706ff091c772a5741786c0011fd6`. Rendered aggregate-only screenshots: [desktop](../images/dna-failure-desktop.png) and [mobile](../images/dna-failure-mobile.png). These use saved OpenF1-derived aggregates, with the license and upstream data caveats above.
