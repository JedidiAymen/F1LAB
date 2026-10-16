# 2025 Italian GP offline replay pack: evidence and contract

This is F1LAB's first real race replay pack. It is an **offline, local** pack
for OpenF1 session 9912, meeting 1268, 2025 Italian Grand Prix race. Its
clock origin is the provider's scheduled session start,
`2025-09-07T13:00:00Z`. The first lap starts about 214.805 seconds later; this
is why the pack's first minutes can show grid positions before completed laps.

## Rebuild and validate

```bash
uv sync --dev
.venv/bin/python -m f1_racelab.session.openf1_replay
.venv/bin/python -m f1_racelab.session.validate_replay
```

Both scripts use `OpenF1Client`'s SHA-keyed local response cache and pace
uncached requests by at least 2.1 seconds. The pack and its manifest/QA report
are ignored local artifacts in `data/processed/replay_packs/`. Raw provider
JSON is ignored under `data/raw/openf1/`. The pack itself is not in Git.

## Source and transformation

| OpenF1 endpoint | Raw rows | Replay use |
|---|---:|---|
| `drivers` | 20 | Stable driver number and event-specific name/team/color |
| `position` | 421 | 20 latest pre-clock positions seed state at t=0; 401 later changes |
| `laps` | 976 | 974 dated, positive-duration lap completions; 2 unusable rows counted |
| `pit` | 19 | Recorded pit lane and stationary duration, not inferred pit entry/exit state |
| `stints` | 39 | Compound and starting tyre age at matched approximate lap start |
| `race_control` | 73 | 53 post-clock messages; sector messages do not set a global flag |
| `intervals` | 20,226 | Latest numeric gap or `+N LAP` text, sampled at most once per second per driver |
| `session_result` | 20 | End-state QA only; final result is not exposed as an earlier timeline event |
| `location` | 30,700 × 20 | 198,300 retained actual points, at most 2 Hz per driver; zero/pre-clock points filtered |

Discrete updates become 1,506 versioned `SessionEvent`s sorted by UTC time,
kind priority and source row order. Each has a provider-derived ID, monotonically
increasing sequence, source timestamp, observation timestamp, ingest timestamp,
session seconds, optional lap, quality and typed payload. `lap` completion time
is **estimated** as approximate `date_start + lap_duration`; the source start
timestamp and estimated completion are both preserved. Stint boundaries use a
matched approximate lap start and are also marked estimated. Position, pit and
race-control records use their original provider timestamps. A pre-clock
position seed keeps its actual older timestamp, so a viewer can see its age.

High-rate location and interval samples stay in indexed sidecars. `ReplaySource`
uses an event checkpoint every 64 events, then reduces only the remaining
events for a seek. At a requested clock time it overlays the latest interval
and a location sample on the **same** `RaceState` returned to consumers.
Exact source points are `measured`; between two points at most 1.5 seconds
apart, linear interpolation is `estimated`. A large coordinate jump (>2,500
provider coordinate units per second) or a missing bracket hides the car
location. This threshold is a source-specific visual QA guard, **not** a
physical speed estimate. Gap samples older than 10 seconds are hidden.

The geometry is a 166-point trace from VER's third race lap. OpenF1 calls its
coordinates approximate, with arbitrary origin and no lateral precision;
the trace is therefore `estimated` circuit geometry, not a surveyed map or
track width. The source coordinate unit is unknown. No official F1 graphics
or broadcast assets are used.

## Verification on real data

After the most recent build, the compressed pack was about 1.8 MB. Its
SHA-256 is recorded in `monza_2025_race.json.manifest.json` and the QA report;
the hash changes when the pack is regenerated because ingest timestamps are
included. Source response SHA-256 values are stable and listed in the local
manifest. The build compared final state against `session_result`:

- 18/18 classified finishing positions matched.
- 20/20 lap totals matched, interpreting the DNS driver's absent lap as zero.
- Two drivers have no classified position: ALO DNF (24 laps) and HUL DNS (0).
- 24 checkpoints were constructed, including the initial state.

The validator compared checkpoint-based seek against full event reduction at
131 times, including event boundaries, with no differences in event log,
flag, position, lap, compound or pit count. It also confirmed an exact measured
location sample survived. On this machine the indexed seek median was 1.123 ms
and p95 2.329 ms for those 131 cases; this is a local CPU observation, not a
browser frame-rate claim. The pack duration is 5,014.715 seconds.

## Limits and next proof

This pack covers **one** race. There is no measured speed/throttle/brake
telemetry, weather, radio, source-aware retirement-time event, surveyed track
width, full circuit provenance or frontend player yet. Location samples may
repeat a stopped car's coordinates; a future renderer must distinguish frozen
provider points from active motion. Pit stop records do not prove when a car
entered or exited pit lane. A lap's completion time is derived from an
approximate start timestamp. No model probability, strategy or live service is
claimed from this pack.

Provider documentation: [OpenF1 API](https://openf1.org/docs/). The inspected
OpenF1 repository revision was
`87540e3f495bbd9bedb37b10456dd848c8f193d6`, with
[CC BY-NC-SA 4.0 repository license](https://github.com/br-g/openf1/blob/87540e3f495bbd9bedb37b10456dd848c8f193d6/LICENSE).
F1LAB independently implemented the adapter; raw and replay data stay local.
Commercial data rights require separate review.
