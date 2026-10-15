# Strategy model contract (planned)

No race strategy simulator or probability calibration is implemented. This is
the contract that the first implementation must satisfy.

The simulator will consume an as-of `RaceState`, measured stint/tyre/pit data,
and a versioned parameter set. Lap time will be decomposed in **seconds** into
baseline pace, fuel effect, tyre age/compound, traffic, weather, safety-car or
VSC effects and stochastic residual. Pit loss will include entry, stationary
and exit components. Every parameter needs units, provenance, fitting window
and a sanity bound. Race outcomes after the branch time are unavailable to the
initial state.

Candidate strategies will run in seeded common exogenous worlds where
appropriate. Strategy-dependent traffic will remain branch-specific. Reports
must include objective, assumptions, spread, seed, model version, sensitivity
and a comparison with simple baselines. A sampled win rate is conditional on
the simulator and will not be called a calibrated probability until tested on
held-out historical races.

First acceptance evidence: unit tests for time and tyre-age accounting,
pit/SC/VSC ordering and determinism, followed by real-event sanity checks and
calibration plots. See `SOL61_MASTER_EXECUTION.md` for full P5–P6 scope.
