"""Build a source-labelled offline replay pack for the 2025 Italian GP.

Discrete timing messages become SessionEvents. Approximate OpenF1 car
coordinates and gap samples remain indexed sidecars; ReplaySource overlays
them on one RaceState at seek time with measured/estimated quality labels.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from f1_racelab.data.openf1_qualifying import OpenF1Client
from f1_racelab.session.contracts import (
    LapPayload,
    PitStopPayload,
    PositionPayload,
    Quality,
    RaceControlPayload,
    SessionEvent,
    SessionId,
    StintPayload,
)

SESSION_KEY = 9912
MEETING_KEY = 1268
CLOCK_ORIGIN = datetime(2025, 9, 7, 13, 0, tzinfo=UTC)
OUTPUT = Path(__file__).resolve().parents[3] / "data/processed/replay_packs/monza_2025_race.json.gz"
SOURCE = "OpenF1 v1"
type CandidateKind = Literal["position", "position_seed", "lap", "pit_stop", "stint", "race_control"]
type EventKind = Literal["position", "lap", "pit_stop", "stint", "race_control"]
type EventPayload = PositionPayload | LapPayload | PitStopPayload | StintPayload | RaceControlPayload


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"Timezone-naive provider timestamp: {value}")
    return parsed.astimezone(UTC)


def _seconds(when: datetime) -> float:
    return (when - CLOCK_ORIGIN).total_seconds()


def _positive(value: float | str | None) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and result > 0 else None


def _nonnegative(value: float | str | None) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and result >= 0 else None


def _rows(client: OpenF1Client, endpoint: str) -> list[dict]:
    rows = client.get(endpoint, session_key=SESSION_KEY)
    if any(row.get("session_key") != SESSION_KEY or row.get("meeting_key") != MEETING_KEY
           for row in rows):
        raise ValueError(f"{endpoint}: response contains a foreign session or meeting")
    return rows


def _timed_events(raw: dict[str, list[dict]], session: SessionId, ingested_at: datetime
                  ) -> tuple[list[SessionEvent], dict[str, int]]:
    """Use source timestamps where present; label derived lap/stint time estimated."""
    candidates: list[tuple[datetime, int, CandidateKind, int, EventPayload, int | None, Quality]] = []
    counts: dict[str, int] = defaultdict(int)
    lap_starts: dict[tuple[int, int], datetime] = {}
    payload: EventPayload
    for row in raw["laps"]:
        if row.get("date_start"):
            lap_starts[(int(row["driver_number"]), int(row["lap_number"]))] = _time(row["date_start"])
    for index, row in enumerate(raw["position"]):
        when = _time(row["date"])
        if when < CLOCK_ORIGIN:
            continue
        payload = PositionPayload(driver_id=str(row["driver_number"]), position=int(row["position"]))
        candidates.append((when, 2, "position", index, payload, None, Quality.MEASURED))
    # OpenF1 position rows before the clock origin carry the only initial grid
    # positions for some drivers. Keep their original observation timestamps
    # and seed the state at t=0; a viewer can see their age.
    previous: dict[int, tuple[int, dict]] = {}
    for index, row in enumerate(raw["position"]):
        when = _time(row["date"])
        if when < CLOCK_ORIGIN:
            number = int(row["driver_number"])
            if number not in previous or when > _time(previous[number][1]["date"]):
                previous[number] = (index, row)
    for index, row in previous.values():
        payload = PositionPayload(driver_id=str(row["driver_number"]), position=int(row["position"]))
        candidates.append((CLOCK_ORIGIN, 0, "position_seed", index, payload, None, Quality.MEASURED))
    for index, row in enumerate(raw["laps"]):
        start = lap_starts.get((int(row["driver_number"]), int(row["lap_number"])))
        duration = _positive(row.get("lap_duration"))
        if start is None or duration is None:
            counts["laps_without_dated_duration"] += 1
            continue
        when = start + timedelta(seconds=duration)
        if when < CLOCK_ORIGIN:
            continue
        payload = LapPayload(driver_id=str(row["driver_number"]),
                             lap_number=int(row["lap_number"]), lap_duration_seconds=duration)
        candidates.append((when, 4, "lap", index, payload, int(row["lap_number"]), Quality.ESTIMATED))
    for index, row in enumerate(raw["pit"]):
        when = _time(row["date"])
        if when < CLOCK_ORIGIN:
            continue
        payload = PitStopPayload(driver_id=str(row["driver_number"]),
                                 lap_number=int(row["lap_number"]),
                                 lane_duration_seconds=_positive(row.get("lane_duration")),
                                 stop_duration_seconds=_positive(row.get("stop_duration")))
        candidates.append((when, 3, "pit_stop", index, payload,
                           int(row["lap_number"]), Quality.MEASURED))
    for index, row in enumerate(raw["stints"]):
        number, lap_start = int(row["driver_number"]), int(row["lap_start"])
        stint_when = lap_starts.get((number, lap_start))
        if stint_when is None:
            counts["stints_without_matching_lap_start"] += 1
            continue
        if stint_when < CLOCK_ORIGIN:
            continue
        payload = StintPayload(driver_id=str(number), stint_number=int(row["stint_number"]),
                               lap_start=lap_start, compound=row.get("compound") or "UNKNOWN",
                               tyre_age_at_start=row.get("tyre_age_at_start"))
        candidates.append((stint_when, 1, "stint", index, payload, lap_start, Quality.ESTIMATED))
    for index, row in enumerate(raw["race_control"]):
        when = _time(row["date"])
        if when < CLOCK_ORIGIN:
            continue
        payload = RaceControlPayload(category=row.get("category") or "Unknown",
                                     message=row.get("message") or "",
                                     flag=row.get("flag"), scope=row.get("scope"))
        candidates.append((when, 5, "race_control", index, payload,
                           row.get("lap_number"), Quality.MEASURED))

    candidates.sort(key=lambda item: (item[0], item[1], item[3]))
    events = []
    for sequence, (when, _, kind, index, payload, lap, quality) in enumerate(candidates):
        source_table = {"position_seed": "position", "lap": "laps",
                        "pit_stop": "pit", "stint": "stints"}
        source_row = raw[source_table.get(kind, kind)][index]
        timestamp_field = "date_start" if kind in {"lap", "stint"} else "date"
        if kind == "stint":
            source_time = when  # stint has no timestamp; matched lap start is approximate
        elif kind == "lap":
            source_time = _time(source_row[timestamp_field])
        else:
            source_time = _time(source_row[timestamp_field])
        event_type: EventKind = "position" if kind == "position_seed" else kind
        events.append(SessionEvent(
            session=session, event_id=f"openf1:{SESSION_KEY}:{kind}:{index}",
            type=event_type, source=SOURCE,
            source_timestamp=source_time,
            observed_at=when if kind == "lap" else source_time,
            ingested_at=ingested_at, session_time_seconds=_seconds(when),
            sequence=sequence, applicable_lap=lap, quality=quality, payload=payload,
        ))
        counts[kind] += 1
    return events, dict(counts)


def _location_samples(rows: list[dict], *, sample_hz: int = 2) -> tuple[list[list[float]], dict[str, int]]:
    """Retain actual source points at most twice per second; never synthesize coordinates."""
    selected: dict[int, tuple[float, int, int]] = {}
    removed_zero = 0
    removed_early = 0
    for row in rows:
        when = _time(row["date"])
        seconds = _seconds(when)
        if seconds < 0:
            removed_early += 1
            continue
        x, y = row.get("x"), row.get("y")
        if x is None or y is None or (x == 0 and y == 0):
            removed_zero += 1
            continue
        bucket = int(seconds * sample_hz)
        point = (round(seconds, 3), int(x), int(y))
        if bucket not in selected or abs(point[0] - (bucket + .5) / sample_hz) < abs(
            selected[bucket][0] - (bucket + .5) / sample_hz
        ):
            selected[bucket] = point
    samples = [list(selected[bucket]) for bucket in sorted(selected)]
    return samples, {"raw": len(rows), "sampled": len(samples),
                     "removed_pre_clock": removed_early, "removed_zero": removed_zero}


def _interval_samples(rows: list[dict]) -> dict[str, list[list]]:
    selected: dict[str, dict[int, list]] = defaultdict(dict)
    for row in rows:
        when = _time(row["date"])
        seconds = _seconds(when)
        if seconds < 0:
            continue
        driver_id = str(row["driver_number"])
        gap = row.get("gap_to_leader")
        interval = row.get("interval")
        selected[driver_id][int(seconds)] = [round(seconds, 3), _nonnegative(gap),
                                             _nonnegative(interval),
                                             gap if isinstance(gap, str) else None,
                                             interval if isinstance(interval, str) else None]
    return {driver: [buckets[bucket] for bucket in sorted(buckets)]
            for driver, buckets in selected.items()}


def _geometry(samples: list[list[float]], laps: list[dict]) -> dict:
    """Use one actual VER lap trace as approximate geometry, in provider units."""
    candidate = next((row for row in laps if row.get("driver_number") == 1
                      and row.get("lap_number") == 3 and row.get("date_start")
                      and _positive(row.get("lap_duration"))), None)
    if candidate is None:
        raise ValueError("VER lap 3 is unavailable for approximate circuit trace")
    start = _seconds(_time(candidate["date_start"]))
    end = start + float(candidate["lap_duration"])
    trace = [[x, y] for t, x, y in samples if start <= t <= end]
    if len(trace) < 100:
        raise ValueError(f"Circuit trace has only {len(trace)} points")
    return {"source": "OpenF1 location, VER lap 3",
            "quality": "estimated", "coordinate_system": "openf1_approx_cartesian_unknown_unit",
            "lap_start_seconds": round(start, 3), "lap_end_seconds": round(end, 3),
            "centerline_xy": trace}


def _verify_pack_against_results(pack: dict, results: list[dict]) -> dict[str, int]:
    """Compare end state with provider results without leaking final labels into replay."""
    from f1_racelab.session.replay_source import ReplaySource

    source = ReplaySource(pack)
    state = source.state_at(source.duration_seconds)
    classified = 0
    nonclassified = 0
    mismatches = []
    for result in results:
        driver_id = str(result["driver_number"])
        driver = state.drivers[driver_id]
        expected_laps = int(result.get("number_of_laps") or 0)
        if (driver.lap or 0) != expected_laps:
            mismatches.append(f"{driver_id} laps {driver.lap} != {expected_laps}")
        expected_position = result.get("position")
        if expected_position is None:
            nonclassified += 1
        else:
            classified += 1
            if driver.position != int(expected_position):
                mismatches.append(f"{driver_id} position {driver.position} != {expected_position}")
    if mismatches:
        raise ValueError("Replay/result mismatch: " + "; ".join(mismatches))
    return {"classified_positions_matching": classified,
            "nonclassified_excluded_from_position_check": nonclassified,
            "lap_counts_matching": len(results),
            "checkpoint_count": len(source.checkpoint_indices)}


def build_replay_pack(output: Path = OUTPUT) -> dict:
    """Fetch once with OpenF1Client cache; write a compact, verified local pack."""
    output = Path(output)
    with OpenF1Client() as client:
        raw = {name: _rows(client, name) for name in
               ("drivers", "position", "laps", "pit", "stints", "race_control",
                "intervals", "session_result")}
        drivers = sorted(raw["drivers"], key=lambda row: int(row["driver_number"]))
        locations = {}
        location_coverage = {}
        for driver in drivers:
            number = int(driver["driver_number"])
            rows = client.get("location", session_key=SESSION_KEY, driver_number=number)
            if any(row.get("session_key") != SESSION_KEY or row.get("driver_number") != number
                   or row.get("meeting_key") != MEETING_KEY for row in rows):
                raise ValueError(f"Location response contains a foreign driver/session: {number}")
            locations[str(number)], location_coverage[str(number)] = _location_samples(rows)
            print(f"location {number}: {location_coverage[str(number)]['sampled']} samples", flush=True)
        source_hashes = dict(client.hashes)
    session = SessionId(season=2025, round=16, kind="race", provider_key=f"openf1:{SESSION_KEY}")
    events, event_coverage = _timed_events(raw, session, datetime.now(UTC))
    if len(drivers) != 20 or len(locations) != 20:
        raise ValueError("Expected 20 drivers with location responses")
    geometry = _geometry(locations["1"], raw["laps"])
    pack = {
        "schema_version": 1,
        "session": session.model_dump(mode="json"),
        "session_name": "2025 Italian Grand Prix — Race",
        "clock_origin_utc": CLOCK_ORIGIN.isoformat(),
        "provider": SOURCE,
        "capabilities": ["positions", "laps", "pit_stops", "stints", "race_control_messages",
                         "approximate_location", "intervals"],
        "drivers": [{"driver_id": str(row["driver_number"]),
                     "number": int(row["driver_number"]),
                     "acronym": row.get("name_acronym"), "name": row.get("full_name"),
                     "team": row.get("team_name"), "team_color": row.get("team_colour")}
                    for row in drivers],
        "events": [event.model_dump(mode="json") for event in events],
        "locations": locations,
        "intervals": _interval_samples(raw["intervals"]),
        "geometry": geometry,
        "provenance": {"api": "https://api.openf1.org/v1",
                       "source_sha256_by_resource": source_hashes,
                       "source_license_note": "See docs/DATA_CONTRACTS.md; raw data is local only"},
        "coverage": {"raw_rows": {key: len(rows) for key, rows in raw.items()},
                     "events": event_coverage, "location": location_coverage},
    }
    qa = _verify_pack_against_results(pack, raw["session_result"])
    output.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(output, "wt", encoding="utf-8", compresslevel=6) as handle:
        json.dump(pack, handle, separators=(",", ":"))
    manifest = {"path": str(output), "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                "bytes": output.stat().st_size, "event_count": len(events),
                "driver_count": len(drivers), "sample_count": sum(map(len, locations.values())),
                "coverage": pack["coverage"], "capabilities": pack["capabilities"],
                "qa": qa,
                "source_sha256_by_resource": source_hashes}
    output.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()
    manifest = build_replay_pack(args.out)
    print(json.dumps({key: manifest[key] for key in
                      ("path", "sha256", "bytes", "event_count", "driver_count",
                       "sample_count", "qa")}, indent=2))


if __name__ == "__main__":
    main()
