# ADR-0001: Sparse events and indexed replay sidecars

**Date:** 2026-10-15<br>
**Status:** Accepted for the first offline replay pack

## Context

The one-state temporal contract requires deterministic seek and aligned timing
and car positions. The real OpenF1 Monza race has 1,506 useful sparse changes
and 198,300 retained approximate location points after 2 Hz sampling. Passing
every car point through the current audit-retaining reducer would multiply
state and event-log work without adding official timing information.

## Decision

Store position changes, lap completions, pit stops, stints and race-control
messages as ordered `SessionEvent`s. Store provider location and interval
samples in per-driver sorted sidecars. `ReplaySource.state_at(t)` reduces from
the nearest 64-event checkpoint, then binary-searches sidecars and returns all
fields in **one** `RaceState(t)`. Interpolated coordinates have `estimated`
quality; no timing or classification is interpolated.

## Consequences

Seeking is fast and repeatable for one 1.8 MB local pack. The sidecar lookup
and event reducer must be validated together, so 131 real seek points are
compared against full reduction. The pack format is Python-defined version 1;
future API/TypeScript consumers require generated schemas and integration
tests. More historical sessions are needed before claiming generality. Source
location precision and a traced lap cannot substitute for surveyed geometry.
