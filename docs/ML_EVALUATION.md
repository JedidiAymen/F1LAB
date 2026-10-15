# Qualifying evaluation contract and current evidence

## Question and split

Predict each driver's **Q1 gap percent** immediately before qualifying, sort
predicted pace within a Grand Prix, and compare the sorted positions with the
actual **final qualifying classification**. This is a proxy benchmark: Q2/Q3
track evolution and elimination can reorder the field. Race starting-grid
penalties are outside the label.

- Fit Ridge and LightGBM on 2022–2023; FP3 best-lap ranking is the comparator.
- Select the lowest event-mean position MAE using 2024 only.
- Report every model on 2025 held-out events. Earlier 2025 results may inform
  lagged features at later 2025 weekends; the state is walk-forward as-of.
- Same eligible drivers for all models: valid FP3 best, Q1 gap and final
  classification. Entire events stay in one split.
- For mixed providers, `COMMON_FEATURES` contains only FP1/2/3 gap/rank and
  FP1→FP3, FP2→FP3 gap changes. Median imputation, standardization and category
  encoding fit on training rows only.

## Metrics and uncertainty

For each event, rank predictions and classifications among eligible drivers.
`position_mae = mean_i |predicted_rank_i − actual_rank_i|`. Spearman correlation
measures ordering; pole hit is one if the predicted fastest eligible driver is
the actual class leader; top-three overlap is intersection size divided by 3.
Overall metrics are unweighted means over events. A seeded paired bootstrap
resamples whole event differences relative to FP3 10,000 times and reports the
2.5th and 97.5th percentiles. A negative MAE delta favors the candidate.

## Data state

At the start of this run the local combined Parquet held 360 rows: 17 cached
conventional 2022 weekends and one 2025 Monza weekend. The previous ingestion
log reported FastF1's 500 calls/hour limit. The resumed FastF1 run completed
cached 2022 R20 and R22, then uncached 2023 timing failed; the upstream F1
timing endpoint returned HTTP 401. A separate mixed dataset now contains 71
conventional weekends and 1,418 source rows: 19/380 FastF1 2022, 16/320
OpenF1 2023, 18/358 OpenF1 2024, and 18/360 OpenF1 2025. Its SHA-256 is
`eef5a7277d2f62fdf263e94cadbc7a5f5c38cd6acdbea9dc00549d5caef37fd8`.
No provider ingestion errors remained in this run. The original combined file
was preserved.

Eligibility leaves 35 training events/684 rows, 18 validation events/342 rows,
and 18 test events/354 rows. On 2024, Ridge had position MAE 2.8362 versus
2.8975 for FP3 and 3.0247 for LightGBM. Ridge was therefore selected before
inspecting the held-out results. On 2025, Ridge had MAE 3.2433, Spearman
0.7095, pole hit rate 0.2778 and top-three overlap 0.6667; FP3 had MAE
3.3141, Spearman 0.6848, pole hit rate 0.2222 and top-three overlap 0.6296.
The Ridge-minus-FP3 paired event MAE difference was -0.0708 positions with a
95% bootstrap interval [-0.2934, +0.1587]. The interval crosses zero, so this
run does not establish a reliable improvement over FP3.

The five-model ablation selected the same Ridge model on 2024. Adding lagged
driver/team form to Ridge increased 2024 MAE to 2.8989. Its 2025 MAE was
3.2314, but that held-out observation cannot be used to change selection.
One shared event audit, 2025 Monza, matched 20 drivers and all available best
practice/Q1 times exactly between providers; this does not prove agreement
across seasons. OpenF1 has no per-lap/tyre/sector inputs in this adapter, and
the 2022/2023 provider boundary remains a confounder.

## Artifacts and reproduction

`data/raw/openf1/` and `data/processed/` are ignored local artifacts. Their
event files and report permit reproduction and resume:

```bash
.venv/bin/python -m f1_racelab.data.openf1_qualifying --years 2023 2024 2025
.venv/bin/python -m f1_racelab.data.mixed_qualifying
.venv/bin/python -m f1_racelab.models.qualifying_backtest --dataset data/processed/qualifying_mixed_2022_2023_2024_2025.parquet --feature-set common
.venv/bin/python -m f1_racelab.models.qualifying_ablation --dataset data/processed/qualifying_mixed_2022_2023_2024_2025.parquet --feature-set common
```

The source code was implemented without copying third-party code. The OpenF1
contract and free historical access are documented at
[OpenF1](https://openf1.org/docs/). See `DATA_CONTRACTS.md` for fields and
`EXPERIMENT_REGISTER.md` for the completed runs.
