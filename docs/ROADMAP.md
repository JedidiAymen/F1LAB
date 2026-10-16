# F1LAB implementation roadmap

Status is tied to evidence, not to code existing in the tree. The locked scope
is in `SOL61_MASTER_EXECUTION.md`; this page tracks execution.

| Gate | State on 2026-10-16 | Proof needed next |
|---|---|---|
| M1: reconcile repository and tools | Complete for this branch checkpoint | Scoped pytest, Ruff, session mypy and uv bootstrap pass; unrelated user files preserved |
| M2: multi-season qualifying data | Complete for 2022–2025 conventional weekends | 71 weekends, 1,418 source rows, provider manifest and overlap audit |
| M3: simple baselines | Complete as a research benchmark | Ridge selected on 2024; 2025 paired interval crosses zero |
| M4: historical-form ablation | Complete as a research ablation | Five models, same eligible rows and common features; form did not win 2024 |
| M5: production ML audit | Not started | Timestamped feature registry, calibrated probabilities only after point model |
| P0: domain contracts and repo hardening | Partial | Python event/state contract and reducer tests exist; CI, schema export and ownership remain |
| P1–P2: replay pack and 2D Race Control | P1/P2 partial | One real Monza pack plus local API and shared-clock 2D/timing/control UI; browser visual review and wider session coverage remain |
| P3–P4: telemetry and Prediction Lab | Not started | Distance-aligned laps and reproducible as-of prediction in UI |
| P5–P6: strategy and counterfactual | Not started | Tested units, seeded worlds, real-event sanity checks |
| P7–P8: live, radio and 3D | Not started | Provider-aware live fan-out and same-clock 3D |

## Current dependency order

1. Inspect the local Race Control UI in an available browser, exercise seek,
   playback, driver selection and responsive widths, and fix any visual issues.
2. Add two more historical sessions only after auditing actual provider
   coverage, including safety-car/VSC and mixed-weather cases.
3. Audit provider agreement across more events and timestamp lineage before
   treating the mixed-source ranking as a production claim.

The React app now has a one-race offline workstation; `RACE_CONTROL_UI.md`
records its evidence and limits. The full product inventory remains required.
