# Visual pipeline contract (partial implementation)

A synchronized local Race Control screen now renders one real Monza pack from
the Python `SessionEvent`/`RaceState` foundation.
`REPLAY_2025_MONZA.md` details its 166-point approximate trace, indexed
2 Hz retained source locations and interpolation quality rules.

One session clock will select a canonical `RaceState(t)` for timing, race
control, telemetry, 2D and 3D views. Playback speed changes clock advancement;
pause and seek affect every panel together. The renderer may interpolate car
motion between provider measurements, but interpolated positions must be
labelled estimated and cannot create official lap times, flags or gaps. When a
provider does not supply a capability, the UI must show that absence.

The circuit geometry artifact will carry layout ID, coordinate system,
centerline, lap distance, pit lane, corners, sectors, start line, source and
version. Position samples must be projected onto matching geometry with error
bounds and handling for the start/finish wrap, pit path and missing samples.
The first 2D demo uses a real offline replay pack and labels its source XY
trace approximate. Its browser state updates at most 5 Hz; interaction and
visual review remain unverified. A 3D view will consume the same geometry
and state after 2D correctness is established. See
`SOL61_MASTER_EXECUTION.md` for P1–P3 and P8 acceptance gates.
