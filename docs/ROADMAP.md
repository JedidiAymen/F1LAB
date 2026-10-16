# F1LAB implementation roadmap

Status is tied to evidence, not to code existing in the tree. The locked scope
is in `SOL61_MASTER_EXECUTION.md`; this page tracks execution.

| Gate | State on 2026-10-16 | Proof needed next |
|---|---|---|
| M1: reconcile repository and tools | Complete for this branch checkpoint | Scoped pytest, Ruff, session mypy and uv bootstrap pass; unrelated user files preserved |
| M2: multi-season qualifying data | Complete for 2022–2025 conventional weekends | 71 weekends, 1,418 source rows, provider manifest and overlap audit |
| M3: simple baselines | Complete as a research benchmark | Ridge selected on 2024; 2025 paired interval crosses zero |
| M4: historical-form ablation | Complete as a research ablation | Five models, same eligible rows and common features; form did not win 2024 |
| M5: production ML audit | Partial | FP1/FP2/pre-qualifying phase snapshots, practice-only allowlists and scheduled cutoff audit exist; provider publication times, calibration, driver identity audit and walk-forward 2026 remain |
| P0: domain contracts and repo hardening | Partial | Python event/state contract and reducer tests exist; CI, schema export and ownership remain |
| P1: replay pack | Three-reference offline gate verified; broader contracts partial | Monza/Monaco/Brazil match available final results; 15,162 boundary/arbitrary-time checks and 600 shuffled seeks; context adds 700 as-of checks; 148 source-timed stint histories are reconstructed without changing pack events; full geometry remains |
| P2: 2D Race Control | Partial, real browser interaction proof | Session picker, 0.25×–16× clock, synchronized map/timing/control/weather/status/stints/telemetry cursor, playback transforms and exact source-time jumps; 10 Chromium scenarios pass; fuller geometry and rendering performance coverage remain |
| P3–P4: telemetry and Prediction Lab | Partial, historical phase-aware UI integrated | Monza telemetry follows canonical `RaceState`; local qualifying lab serves checksum-verified FP1/FP2/pre-Q snapshots, same-provider 2023 training/2024 validation/2025 holdout and phase feature registries; wider telemetry, publication timestamps and calibration remain |
| P5–P6: strategy and counterfactual | Not started | Tested units, seeded worlds, real-event sanity checks |
| P7–P8: live, radio and 3D | Not started | Provider-aware live fan-out and same-clock 3D |

## Current dependency order

1. Continue P2 with fuller circuit geometry and rendering performance coverage
   while preserving the integrated source-time weather, stint history and
   conservative track-signal state.
2. Expand the shared-clock telemetry comparison beyond the Monza reference
   pair, then continue cross-provider overlap checks for qualifying.
3. Find or retain timestamped practice-result availability before making any
   operational prediction claim. The new phase study uses scheduled practice
   ends and explicitly does not establish provider publication time; details
   and metrics are in `QUALIFYING_PHASES.md`.

The React app now has a three-race offline workstation. The full product
inventory remains required; this is an early integrated slice.
