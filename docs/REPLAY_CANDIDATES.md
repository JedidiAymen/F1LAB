# Additional replay session coverage audit — 2026-10-16

**Follow-up:** both candidates now build through the shared replay adapter
and run in the UI. The audit below records the earlier source findings;
`REPLAY_GOLDEN_SESSIONS.md` records the later pack/browser evidence.

**Starting source SHA:** `2d270fc` on `feat/foundation`. This is a real
provider coverage audit, not two additional replay packs. The source is
[OpenF1 historical API](https://openf1.org/docs/), queried through the
existing cached, paced `OpenF1Client`. The independently written audit
code is `src/f1_racelab/session/audit_candidates.py`; raw responses and the
generated JSON artifact stay ignored under `data/`.

## Reproduce

```bash
.venv/bin/python -m f1_racelab.session.audit_candidates
.venv/bin/pytest -q tests/test_replay_candidate_audit.py
```

The first command writes `data/processed/replay_candidate_audit.json`.
`Candidate(year,country)` resolves exactly one Race session. The auditor
fetches nine expected tables for its session key, checks every returned row
belongs to it, and records counts, driver coverage, rain records, compounds,
critical control messages and SHA-256 hashes of provider responses. Only
HTTP 404 becomes a `null` resource count; HTTP/rate/parse errors fail the
audit. `null` means unavailable, distinct from a real empty response.
Numbers below are **source row counts**, not usable replay-event counts.

| Source session | 2023 Monaco race | 2024 Brazil race |
|---|---:|---:|
| OpenF1 session / meeting key | 9094 / 1210 | 9636 / 1249 |
| Scheduled UTC origin | 2023-05-28 13:00 | 2024-11-03 15:30 |
| Driver rows / distinct driver IDs | 20 / 20 | 20 / 20 |
| Position rows / drivers | 300 / 20 | 360 / 20 |
| Lap rows / drivers | 1,516 / 20 | 1,137 / 19 |
| Pit rows | **HTTP 404 / unavailable** | 35 |
| Stint / interval rows | 57 / 30,074 | 54 / 21,060 |
| Control / weather rows | 244 / 176 | 111 / 201 |
| Rainfall=1 weather records | 26 | 117 |
| Session-result rows | 20 | 20 |

Monaco's stints include 20 INTERMEDIATE and 3 WET rows among dry compounds.
Its control table has sector/driver flags but no source `SafetyCar` category
or RED flag. Brazil's stints include 49 INTERMEDIATE and 5 WET rows. Brazil
has source messages for VSC deployment/ending (16:28:21/16:29:50 UTC), safety
car deployment (16:32:53), red flag (16:37:22), safety car deployment
(17:13:14) and safety car in this lap (17:18:04). Their categorical meanings
still require scoped parsing before creating a global `RaceState.flag`.
Rainfall is provider boolean observation count, not precipitation amount.

Control/weather response hashes: Monaco
`df28785249dae893a6489bf0a620a5550e2623335117fbba8527f45e5da03f9d` /
`43a544af35fe02685e4724269f8cb95e14f9f77c01e354ac87feec419d884d97`;
Brazil
`ab6bf12fd26662ba855c6e892218ef3ffad43a639f4f2c0165c413587e21185a` /
`a05f9c12460bca0c87aa7dd64124eeed729321bd439cbc7f3251fa88ff9084fe`.
The artifact carries hashes for every available table.

## Implementation consequence

The current Monza pack builder hardcodes session key 9912, meeting key 1268,
origin, output name and a required `pit` response. It must be parameterized
and allow an explicitly unavailable optional pit resource before Monaco can
build. Brazil is the first source case for global safety-car/VSC/red-flag
logic, but a source `SafetyCar` message cannot be naively applied to all
sector flags. Both future packs need their own end-state result QA,
event-boundary seeks, quality coverage and browser review. No second pack
or replay reliability claim is made here.

**Evidence:** synthetic audit test passed; full suite 28 passed with one
Starlette/httpx deprecation warning; Ruff and audit-scoped mypy passed.
The initial manual coverage fetch failed with HTTP 404 on Monaco `pit`;
the reproducible auditor now records that as unavailable. The audit CLI ran
successfully and printed both summaries. No provider code or raw records are
committed. The inspected OpenF1 repository license/source-rights notes are
in `DECISIONS.md`.
