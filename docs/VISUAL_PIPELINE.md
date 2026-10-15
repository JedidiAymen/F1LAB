# Visual pipeline contract (planned)

No circuit renderer or synchronized Race Control UI is implemented. The Python
`SessionEvent`/`RaceState` foundation and the real race-control message sample
are the current inputs to a future replay pack.

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
The first 2D demo should use a real offline replay pack. A 3D view will consume
the same geometry and state after 2D correctness is established. See
`SOL61_MASTER_EXECUTION.md` for P1–P3 and P8 acceptance gates.
