# Qualifying data contract (current implementation)

One row represents one driver at one qualifying weekend. Its key is
`(year, round, driver)`. `event` is a human name; it is not a stable cross-era
circuit identifier. `round` counts completed race meetings, including Sprint
meetings, even when Sprint weekends are omitted from this experiment.

| Field | Unit / meaning | Information time |
|---|---|---|
| `fp1/2/3_best_seconds` | Best valid practice lap in seconds | End of practice session |
| `fp1/2/3_gap_pct` | `100 × (driver best / event best − 1)` | End of practice session |
| `fp1/2/3_rank` | Rank of practice best lap within session | End of practice session |
| `q1_seconds`, `q2_seconds`, `q3_seconds` | Best lap in each qualifying phase, nullable | After respective phase |
| `q1_gap_pct` | `100 × (driver Q1 / event best Q1 − 1)` | Target, after Q1 |
| `final_position` | Qualifying classification | Label, after qualifying |
| `team` | Constructor name at this event | Known before qualifying |
| `available_at` | Scheduled qualifying start UTC; prediction cutoff label | Pre-Q cutoff metadata; not a provider publication time |
| `provider`, `provider_version`, `source_*` | Lineage and quality metadata | Audit only |

`final_position` is qualifying classification, **not** the penalty-adjusted race
starting grid. `q1_gap_pct` is a pace target, not final Q3 pace. Its use in
training is legal only as a past-event label. Current-event Q1/Q2/Q3 and final
position never enter `FEATURES` or `COMMON_FEATURES`.

### Provider mapping and quality

- FastF1 2022: the existing `qualifying_weekends/*.parquet` extracts practice
  laps after filtering missing times, deleted laps, and pit in/out laps. The
  within-3%-of-driver-best threshold selects representative laps; the best lap
  itself is unchanged by that threshold. FP3 supplies team identity. The
  `source_sha256` is the cached **processed Parquet** hash, not a raw upstream
  response hash.
- OpenF1 2023–2025: `meetings` and `sessions` establish completed conventional
  weekends. `session_result` supplies each practice best and Q duration array;
  `drivers` supplies abbreviation/team. Each response is cached as JSON. The
  weekend `source_sha256` hashes its five response hashes. No tyre/sector/lap
  samples are inferred from session results. The OpenF1 Q session `date_start`
  is used as the pre-Q cutoff; the archive does not expose each feature's
  original publication timestamp here.

The two best-lap definitions may differ on deleted or revised laps. A 2025
Monza overlap audit matched all 20 drivers, with zero classification
mismatches and zero differences among paired FP1/FP2/FP3/Q1 best times (18/20/
20/20 pairs). This checks one weekend only; a broader cross-provider audit is
required before treating the mixed-year comparison as a purely sporting
effect. Missing values stay missing until the training-only imputer runs.

The common-feature experiment records source-session lineage (FP1, FP2, FP3)
and rejects inputs outside its explicit allowlist. Individual practice field
observation timestamps are not retained, so this is an offline pre-Q
reconstruction based on session lineage, not a proven replay of the exact data
availability instant. `GET /api/v1/predictions/qualifying` exposes the
checksum-verified local experiment summary; the `/event` route returns predicted
model ranks and the retrospective actual rank without returning Q1 target
values. Missing or altered artifacts return 503. See `PREDICTION_LAB.md` for
the response contract and evidence.

Source: [OpenF1 API documentation](https://openf1.org/docs/). Public historical
access is rate limited; `OpenF1Client` requests at least 2.1 seconds apart and
caches exact responses. The OpenF1 repository's
[CC BY-NC-SA 4.0 license](https://github.com/br-g/openf1/blob/87540e3f495bbd9bedb37b10456dd848c8f193d6/LICENSE)
has attribution/noncommercial/share-alike terms. Raw responses remain local;
commercial redistribution requires a separate rights review. Real-time
availability is a separate subscription issue.

## Canonical race timeline (partial implementation)

`src/f1_racelab/session/contracts.py` holds schema version 1 for one
`SessionId`, ordered `SessionEvent`s and `RaceState`. Each event includes a
stable source-specific ID, event type, source, source/observed/ingest UTC
timestamps, session-relative seconds, sequence, optional lap, quality
(`measured`, `estimated`, `simulated`) and a typed payload. The reducer rejects
cross-session or nonmonotonic events and never infers official timing from a
race-control message. The real local Monza sample contains 53 OpenF1 messages
after scheduled start, with source response SHA-256
`b138137eadc17c3d10d1b1bfe7f5fe8beddf033753b0a5adad79904a5693fa25`.
Its only advertised capability is `race_control_messages`; it is not a full
race replay. Raw and normalized data stay in ignored `data/`.

The newer 2025 Monza race pack extends that smoke sample. Its sparse event
types now include position changes, estimated lap completions, pit records,
estimated stint boundaries and race-control messages. OpenF1 `location` and
`intervals` are indexed sidecars sampled into the same `RaceState` at seek
time. Driver identifiers are event-specific car numbers, not acronyms; the
pack maps them to name/team/color metadata. `position_quality` and
`location_quality` are separate. A location between two retained measurements
is estimated; lap time and classification are never interpolated. Raw
`session_result` is used only to verify the final state, not injected as an
early replay event. See `REPLAY_2025_MONZA.md` for counts, timestamp choices,
source hashes, limits and reproduction.

## Three-reference replay extension

`session/catalog.py` now specifies Monza 2025 (9912), Monaco 2023 (9094)
and Brazil 2024 (9636). Each spec has an audited scheduled UTC origin and
provider IDs, checked against the actual session endpoint before building.
Every event ID is scoped by provider session key, and all event/location/
interval relative seconds use that selected origin. Driver car numbers
remain session-local IDs; switching sessions changes the enclosing session.

`RaceState.capabilities` is a tuple serialized as a JSON array on every
state. A Monaco pit HTTP 404 produces `coverage.raw_rows.pit=null`,
`coverage.unavailable_resources.pit` with reason and no `pit_stops`
capability. The UI presents pit count as unavailable. A successful zero-row
table remains zero. The builder propagates other HTTP failures.
Null stint starts cannot form events and are counted in coverage; null
post-session DSQ lap totals cannot be used as a zero-lap QA label.

The local API now lists session availability at `GET /api/v1/replays`;
manifest and state paths are `/api/v1/replay/{slug}/manifest` and
`/api/v1/replay/{slug}/state?seconds=...`. Old Monza paths remain valid.
The API does not expose future final classifications through the event
timeline. Schema 2 now carries timestamped weather and conservatively scoped
global track-status observations in the same `RaceState`; exact units, event
mapping, age rules, raw hashes and proof are in `REPLAY_CONTEXT.md`.
`REPLAY_GOLDEN_SESSIONS.md` records replay state and `REPLAY_CONTEXT.md`
records context artifacts and proof.

### Current source-timed stint state

Stored pack files and `SessionEvent` envelopes remain schema 2. The current
emitted `RaceState` is schema 3 and adds `DriverState.tyre_stints`, a tuple of
`TyreStintState` records. Each record includes source event ID, source time in
seconds since the scheduled origin, UTC-aware provider observation time,
compound, one-based lap start/end, start age in laps, quality and the event
that closed the segment. A lap event extends only the current open segment;
the next stint event closes it at the latest completed lap. Eventual provider
`lap_end` values are not copied into earlier state. This retains same-lap
source starts and prevents future boundary leakage. Current pack totals are
39 Monza, 57 Monaco and 52 Brazil normalized stints; the two unnormalizable
Brazil rows are separately counted in coverage. Full algorithm and evidence:
`REPLAY_STINTS_AND_MOTION.md`.

## Historical telemetry comparison (partial P3)

`src/f1_racelab/telemetry/contracts.py` defines an immutable source lap
contract. A point has elapsed seconds, distance in metres integrated from
reported speed, speed in km/h, source throttle value, raw brake value, RPM,
gear and DRS code. Lap metadata includes session/meeting/driver/lap identity,
timezone-aware approximate start, duration, source sample count, bounded point
count, interpolated-boundary count, maximum gap and integrated distance.
Every distance and comparison point is explicitly `estimated`.

The builder requires source identity to match, excludes pit-out laps, uses a
maximum 1-second interpolation/integration gap by default and integrates
`average(speed_i, speed_(i+1)) / 3.6 * elapsed_seconds` metres. It refuses to
bridge larger gaps. Throttle and brake are not clipped; brake remains named
`brake_source_value`, and DRS remains a raw integer code. Continuous channels
are linear-interpolated while brake/gear/DRS use the preceding source state.
`LapComparison` holds two same-session laps on a regular shared-distance grid;
`delta_time_b_minus_a_seconds` is elapsed time for B minus elapsed time for A.

The current real sample is Monza 2025 session 9912, car 1 vs car 4, lap 50,
with raw query hashes and precise limitations in
`DISTANCE_ALIGNED_TELEMETRY.md`. Output JSON/PNG is local and ignored. The
local API validates and serves the generated comparison artifact; the endpoint
does not fetch provider data. `TelemetryPanel` derives its crosshair from the
reference lap's UTC start and the `session_time_seconds` of the same
`RaceState` used by the rest of the page. Its “jump to reference lap” action
seeks the existing playback clock. The distance remains a derived coordinate,
not another clock or a surveyed location. Other session artifacts are shown
only after the corresponding local CLI output exists.
