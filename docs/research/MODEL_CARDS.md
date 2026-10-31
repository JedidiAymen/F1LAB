# Model and dataset cards (summary)

The machine-readable card for the served race-pace model is `data/processed/models/race_pace/race_pace_lightgbm.card.json` (git-ignored; regenerate with `uv run python -m f1_racelab.ml.pace.benchmark --refit-only`). Cards below summarise the other modules. All data: OpenF1 (CC BY-NC-SA 4.0 project terms, non-commercial) and FastF1 (2022); raw data is local and not redistributed.

| Module | Intended use | Data | Split | Headline (real data) | Not for |
|---|---|---|---|---|---|
| Race pace LightGBM | Historical next-lap research, Strategy Lab comparison | 85 races 2023-2026, 83,523 rows | expanding window by race | MAE 0.575 s; vs persistence -0.018 s [-0.057, +0.029] (not significant) | live decisions; safety-car laps |
| Qualifying ensemble | Walk-forward grid forecasts | 2022-2026 weekends | expanding window by event | 2024-25 gain 0.27 positions; 2026 no gain | 2026 regime without refit |
| Driver DNA (TCN, contrastive, baselines) | Separability study | 1,749 laps, 3 races, 11 shared drivers | leave-one-circuit-out; blocked teammate split | teammates 0.80-0.90 vs 0.51; cross-circuit 23-40% vs 9% | claiming innate style; deployment |
| Overtake LightGBM | Next-lap pass probability research | 29,608 pairs, 85 races | expanding window by race | Brier 0.0329 vs 0.0407 gap-only | strategy changes; neutralised laps |
| Neural qualifying variants | Exploratory comparison | same 48 events | same walk-forward | no variant beats ensemble | serving |
| RaceVision, Radio | Not built | none | none | none | all uses |

Each module's research note lists exact commands, versions, limitations and artifact locations in `docs/research/`.

**2026-10-31 normalization correction:** the Driver DNA headline above describes
the original transductive protocol. Same-data train-only normalization gives
Task A 19.79% logistic / 12.33% LightGBM (original 38.43% / 30.21%); Task B
88.80% / 83.92%. No new inductive neural model or expanded dataset exists.
`driver_dna/normalization_study.json` records source/dependency/input hashes and
per-split results; API checks its SHA sidecar. See `DRIVER_DNA.md`.
