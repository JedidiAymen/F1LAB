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
| P1: replay pack | Three-reference offline gate verified; broader contracts partial | Monza/Monaco/Brazil match available final results; 14,112 boundary/arbitrary-time checks and 600 shuffled seeks; full geometry and track-status contracts remain |
| P2: 2D Race Control | Partial, real browser interaction proof | Session picker, 0.25×–16× clock, seek/jumps and shared map/timing/control pass four Chromium tests; smooth rendering, weather, stint bars and global status remain |
| P3–P4: telemetry and Prediction Lab | Not started | Distance-aligned laps and reproducible as-of prediction in UI |
| P5–P6: strategy and counterfactual | Not started | Tested units, seeded worlds, real-event sanity checks |
| P7–P8: live, radio and 3D | Not started | Provider-aware live fan-out and same-clock 3D |

## Current dependency order

1. Add scoped track-status/weather contracts, preserving unknown transitions
   and source timestamps; integrate them into the same replay state.
2. Complete P2 smooth timestamped rendering and tyre/stint views, then
   distance-aligned telemetry. The three audited sessions now build and
   play; see `REPLAY_GOLDEN_SESSIONS.md` for proof and limits.
3. Audit provider agreement across more events and timestamp lineage before
   treating the mixed-source ranking as a production claim.

The React app now has a three-race offline workstation. The full product
inventory remains required; this is an early integrated slice.
