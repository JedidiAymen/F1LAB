# Replay weather and track context — schema 2

**Milestone date:** 2026-10-16 UTC

**Starting source SHA:** `418806099b7670d96cfe13c13c6484d5f8644a50`

**Branch:** `feat/foundation`
**Implementation and remote SHAs:** recorded in the post-push entry in
`CHATGPT_HANDOFF.md` and `AGENT_WORKLOG.md`.

This milestone carries historical OpenF1 weather observations and a limited
set of explicitly scoped race-control messages through the same source event,
canonical `RaceState`, local API and React session clock as timing and map
state. It does not complete P1/P2 or the broader F1LAB goal.

## Contract and meaning

`src/f1_racelab/session/contracts.py` makes schema 2 the current emitted event
and state format. `ReplaySource` still reads version 1 and version 2 packs;
version 1 events remain replayable and reduce to a version 2 current state.
Version 1 event envelopes cannot claim a schema 2 weather or track-status
payload. Immutable observation metadata carries event/source IDs, UTC-aware
`observed_at`, session seconds and measured quality.

Weather fields retain source units and missing values:

| Canonical field | Unit / interpretation |
|---|---|
| `air_temperature_c`, `track_temperature_c` | °C |
| `humidity_percent` | percent |
| `pressure_mbar` | millibar |
| `wind_direction_degrees` | degrees, 0–359 |
| `wind_speed_mps` | metres/second |
| `rainfall` | boolean presence reported by provider; `false` is distinct from null |

All-null observations are rejected. Other ranges are validated. A weather event
is placed at its provider timestamp with no interpolation. It is added only
within the existing session clock window; pre-clock rows are counted and
skipped, invalid values are counted and skipped, and weather does not extend
the pack duration. Optional weather/control resources treat HTTP 404 as
unavailable; other request failures propagate.

`WeatherObservation.max_age_seconds` defaults to 120. The frontend computes
`age = canonical_state.session_time_seconds - observation.session_time_seconds`
and displays values only for `0 <= age <= max_age_seconds`. It uses the replay
clock, not browser wall time, so pause, exact seek and playback rate preserve
deterministic freshness. Rainfall wording reports provider presence only: it
does not estimate wet track, grip, rainfall amount or intensity. The manifest
contains the first non-null rainfall observation and each subsequent boolean
change as navigation points. These are historical seek targets; all reading
values still come from the current canonical state.

Track-status mapping is deliberately narrow and is implemented independently
of presentation labels:

- Track-scoped `Flag` messages with no driver number or sector may map explicit
  GREEN, YELLOW, DOUBLE YELLOW, RED or CHEQUERED messages.
- Any scoped driver/sector message, pit-exit flag, or unsupported phrase is
  not promoted to a global status.
- Exact global SafetyCar phrases map VSC deployed/ending and Safety Car
  deployed/in-this-lap. SessionStatus SESSION STARTED maps to
  `running_unknown`; SESSION ABORTED maps to `suspended`.
- Ending/deployment-lap notices never imply green. `running_unknown` records
  that a session-started source message arrived without claiming track
  conditions. The latest accepted signal remains visible until a later signal.
- Original race-control messages remain in the source feed regardless of
  whether a message meets this narrower global-state contract.

## Implementation map

- `session.openf1_context.weather_payload` preserves and validates provider
  weather fields; `track_status_payload` implements the scoped phrase rules.
- `session.openf1_replay._timed_events` adds source-labelled schema 2 weather
  and accepted context events, with deterministic sequence ordering and
  provider timestamp lineage.
- `session.reducer.reduce_event` updates weather/status with immutable copies.
  A steady explicit flag also creates a canonical status observation; ending
  and unknown transitions clear the old steady `flag` rather than carrying a
  stale green/yellow/red `flag` forward.
- `session.replay_source.ReplaySource` retains context through indexed seeks
  and schema 1 compatibility.
- `session.validate_context.validate_context` independently checks exact raw
  cache bytes against pack provenance, weather values/timestamps at before
  and exact cutoffs, and a separately reviewed status golden list. Generated
  JSON is ignored under `data/processed/replay_packs/`.
- `/api/v1/replay/{slug}/manifest` exposes `weather_changes`; state returns
  weather and status as part of the single `RaceState`.
- `apps/web/src/lib/session-context.ts` evaluates freshness and shared time
  labels; `WeatherPanel.tsx`, `App.tsx` and `App.css` render the context and
  exact-source-time controls. Six browser checks verify common panel time.

## Real source audit

All three cache entries are the documented OpenF1 historical API, retrieved
through the existing paced client and stored outside Git. Provider units are
documented at [OpenF1 API documentation](https://openf1.org/docs/). Repository
license provenance and limits remain in D-001 and `DATA_CONTRACTS.md`; no
OpenF1 repository implementation code was copied.

| Session | Raw weather rows | Before clock | Retained in pack | After existing window | Invalid | Raw weather SHA-256 |
|---|---:|---:|---:|---:|---:|---|
| Monza 2025, session 9912 | 144 | 54 | 84 | 6 | 0 | `e32d4cbe40e2997b039a3e637b5ee8e76e2b788d079d7898311efdae032fa7f5` |
| Monaco 2023, session 9094 | 176 | 59 | 117 | 0 | 0 | `43a544af35fe02685e4724269f8cb95e14f9f77c01e354ac87feec419d884d97` |
| Brazil 2024, session 9636 | 201 | 52 | 149 | 0 | 0 | `a05f9c12460bca0c87aa7dd64124eeed729321bd439cbc7f3251fa88ff9084fe` |

Raw race-control response SHA-256 values are Monza
`b138137eadc17c3d10d1b1bfe7f5fe8beddf033753b0a5adad79904a5693fa25`, Monaco
`df28785249dae893a6489bf0a620a5550e2623335117fbba8527f45e5da03f9d`, and
Brazil `ab6bf12fd26662ba855c6e892218ef3ffad43a639f4f2c0165c413587e21185a3`.
Raw response hashes are verified from the local cache against each pack's
provenance record before field comparisons.

| Pack | Schema 2 events (base + weather + global signal) | Pack SHA-256 | Bytes | Duration unchanged |
|---|---:|---|---:|---:|
| Monza 2025 | 1,592 (1,506 + 84 + 2) | `cdb6a7a6f79d18c24c51001aef9c7829bfbf4db1d9da7fd9b4fab2559c1ae1dd` | 1,781,361 | 5,014.715 s |
| Monaco 2023 | 2,220 (2,101 + 117 + 2) | `3b2cb79107ed8d5c72e14a87f0c3705d1cb29c9a7a2b735f52c07686b0294f2a` | 2,534,796 | 7,030.073 s |
| Brazil 2024 | 1,842 (1,683 + 149 + 10) | `ca3df608046d96d9d87d9ae383037a11192800802f7d5c88603a7ca6bbb5cdec` | 2,436,435 | 8,935.817 s |

Across the packs, there are 5,654 normalized events, 350 weather observations,
14 accepted global track signals and the previously audited 799,422 XY points.
Maximum gaps between retained weather observations are 60.042, 60.093 and
60.225 seconds. At pack end the newest reading ages are 30.938, 25.987 and
29.506 seconds respectively. These values describe these three source
sessions, not a general provider cadence guarantee.

The independent golden signal list is:

- Monza: 214.805 s `running_unknown`; 4,619 s `chequered`.
- Monaco: 183.926 s `running_unknown`; 6,718 s `chequered`.
- Brazil: 1,197.515 s `running_unknown`; 3,501 s `vsc`; 3,590 s
  `vsc_ending`; 3,773 s `safety_car`; 4,041.752 s `suspended`; 4,042 s
  `red`; 5,520.39 s `running_unknown`; 6,194 s `safety_car`; 6,484 s
  `safety_car_ending`; 8,812 s `chequered`.

Validation checked each of the 350 weather rows one millisecond before and at
its source time (700 comparisons). It checked before/at every one of the 14
golden status boundaries, confirmed matching source messages and context scope,
and verified unknown states do not leave an inferred steady flag. No invalid
weather records were silently coerced. The combined report is
`data/processed/replay_packs/golden_context.qa.json`; the pack reports end in
`.context.qa.json`.

## Browser proof and reproduction

The real-pack browser cases cover common timestamps across timing, map, focus,
race control, weather and session summary; session switching and optional
Monaco pit unavailability; Monaco rainfall at 4,363.946 s and the dry report
at 5,923.949 s; Brazil VSC ending at 3,590 s, red at 4,042 s, unknown restart
at 5,520.39 s, and Safety Car ending at 6,484 s. At the restart, the UI says
RUNNING / UNKNOWN rather than green.

Rebuild cached packs and run the checks:

```bash
.venv/bin/python -m f1_racelab.session.openf1_replay --session monza-2025
.venv/bin/python -m f1_racelab.session.openf1_replay --session monaco-2023
.venv/bin/python -m f1_racelab.session.openf1_replay --session brazil-2024
.venv/bin/python -m f1_racelab.session.validate_context --all
.venv/bin/python -m f1_racelab.session.validate_replay --all
.venv/bin/pytest -q
.venv/bin/ruff check src tests scripts
.venv/bin/mypy src/f1_racelab/session src/f1_racelab/api.py --follow-imports=silent --ignore-missing-imports
cd apps/web
npm run test:unit
npm run lint
npm run build
npm run test:e2e
```

Browser tests use packs built from the local raw cache; they do not download
provider data. The test run is six Playwright/Chromium cases. Screenshots,
traces, packs, QA and reports are ignored build artifacts. Current pack hashes
can change when rebuilt because gzip metadata includes build-time data.
The recorded toolchain is Python 3.12.13 / FastAPI 0.142.2, Node 22.23.2 /
npm 10.9.8, Playwright 1.64.1 / Chromium 156, and Vite 8.3.2.

## Limits and next work

This covers three audited historical races. `running_unknown` is intentionally
not a claim that the circuit was green. Weather rainfall is presence only, and
the 120-second display age is a product rule. Session status can remain at the
last accepted signal. Other global message phrases may not map; source scope is
required. Nothing here calibrates tyre grip, strategy effects, model
probabilities, retirement time or live-feed behavior. Remaining work includes
smooth map motion, stint views, distance-aligned telemetry, richer measured
geometry, production ML, strategy/counterfactual, live mode, radio, 3D,
storage/schema export and CI. Consult `ROADMAP.md` for the dependency order.
