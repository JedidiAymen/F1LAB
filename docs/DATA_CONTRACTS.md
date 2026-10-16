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
| `available_at` | Qualifying start UTC; prediction cutoff label | Pre-Q cutoff |
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
