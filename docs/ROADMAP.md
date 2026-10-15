# F1LAB implementation roadmap

Status is tied to evidence, not to code existing in the tree. The locked scope
is in `SOL61_MASTER_EXECUTION.md`; this page tracks execution.

| Gate | State on 2026-10-15 | Proof needed next |
|---|---|---|
| M1: reconcile repository and tools | In progress | Finish checkpoint review and lint |
| M2: multi-season qualifying data | Complete for 2022–2025 conventional weekends | 71 weekends, 1,418 source rows, provider manifest and overlap audit |
| M3: simple baselines | Complete as a research benchmark | Ridge selected on 2024; 2025 paired interval crosses zero |
| M4: historical-form ablation | Complete as a research ablation | Five models, same eligible rows and common features; form did not win 2024 |
| M5: production ML audit | Not started | Timestamped feature registry, calibrated probabilities only after point model |
| P0: domain contracts and repo hardening | Not started | Typed event/state contracts and tests |
| P1–P2: replay pack and 2D Race Control | Not started | One real session seeks deterministically with synchronized panels |
| P3–P4: telemetry and Prediction Lab | Not started | Distance-aligned laps and reproducible as-of prediction in UI |
| P5–P6: strategy and counterfactual | Not started | Tested units, seeded worlds, real-event sanity checks |
| P7–P8: live, radio and 3D | Not started | Provider-aware live fan-out and same-clock 3D |

## Current dependency order

1. Finish checkpoint review, tests, evidence records and a safe branch push.
2. Implement canonical `SessionEvent`/`RaceState` contracts and a real replay
   fixture, then wire a shared clock into the app.
3. Audit provider agreement across more events and timestamp lineage before
   treating the mixed-source ranking as a production claim.

The React app is currently the Vite starter. The full product inventory remains
required; this table does not narrow it.
