"""Build source-labelled offline replay packs for audited historical races.

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

import httpx
from pydantic import ValidationError

from f1_racelab.data.openf1_qualifying import OpenF1Client
from f1_racelab.session.catalog import DEFAULT_SESSION, SESSIONS, ReplaySpec
from f1_racelab.session.contracts import (
    LapPayload,
    PitStopPayload,
    PositionPayload,
    Quality,
    RaceControlPayload,
    SessionEvent,
    SessionId,
    StintPayload,
    TrackStatusPayload,
    WeatherPayload,
)
from f1_racelab.session.openf1_context import track_status_payload, weather_payload

SESSION_KEY = DEFAULT_SESSION.session_key
CLOCK_ORIGIN = DEFAULT_SESSION.clock_origin
OUTPUT = DEFAULT_SESSION.pack_path
SOURCE = "OpenF1 v1"
type CandidateKind = Literal["position", "position_seed", "lap", "pit_stop", "stint",
                             "race_control", "track_status", "weather"]
type EventKind = Literal["position", "lap", "pit_stop", "stint", "race_control",
                         "track_status", "weather"]
type EventPayload = (PositionPayload | LapPayload | PitStopPayload | StintPayload
                    | RaceControlPayload | TrackStatusPayload | WeatherPayload)


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"Timezone-naive provider timestamp: {value}")
    return parsed.astimezone(UTC)


def _seconds(when: datetime, clock_origin: datetime = CLOCK_ORIGIN) -> float:
    return (when - clock_origin).total_seconds()


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


def _rows(client: OpenF1Client, endpoint: str, spec: ReplaySpec = DEFAULT_SESSION) -> list[dict]:
    rows = client.get(endpoint, session_key=spec.session_key)
    if any(row.get("session_key") != spec.session_key or row.get("meeting_key") != spec.meeting_key
           for row in rows):
        raise ValueError(f"{endpoint}: response contains a foreign session or meeting")
    return rows


def _timed_events(raw: dict[str, list[dict]], session: SessionId, ingested_at: datetime,
                  clock_origin: datetime = CLOCK_ORIGIN,
                  location_end_seconds: float | None = None,
                  ) -> tuple[list[SessionEvent], dict[str, int]]:
    """Use source timestamps where present; label derived lap/stint time estimated."""
    candidates: list[tuple[datetime, int, CandidateKind, int, EventPayload, int | None, Quality]] = []
    counts: dict[str, int] = defaultdict(int)
    lap_starts: dict[tuple[int, int], datetime] = {}
    payload: EventPayload
    if not session.provider_key:
        raise ValueError("OpenF1 event normalization requires a provider session key")
    for row in raw["laps"]:
        if row.get("date_start"):
            lap_starts[(int(row["driver_number"]), int(row["lap_number"]))] = _time(row["date_start"])
    for index, row in enumerate(raw["position"]):
        when = _time(row["date"])
        if when < clock_origin:
            continue
        payload = PositionPayload(driver_id=str(row["driver_number"]), position=int(row["position"]))
        candidates.append((when, 2, "position", index, payload, None, Quality.MEASURED))
    # OpenF1 position rows before the clock origin carry the only initial grid
    # positions for some drivers. Keep their original observation timestamps
    # and seed the state at t=0; a viewer can see their age.
    previous: dict[int, tuple[int, dict]] = {}
    for index, row in enumerate(raw["position"]):
        when = _time(row["date"])
        if when < clock_origin:
            number = int(row["driver_number"])
            if number not in previous or when > _time(previous[number][1]["date"]):
                previous[number] = (index, row)
    for index, row in previous.values():
        payload = PositionPayload(driver_id=str(row["driver_number"]), position=int(row["position"]))
        candidates.append((clock_origin, 0, "position_seed", index, payload, None, Quality.MEASURED))
    for index, row in enumerate(raw["laps"]):
        start = lap_starts.get((int(row["driver_number"]), int(row["lap_number"])))
        duration = _positive(row.get("lap_duration"))
        if start is None or duration is None:
            counts["laps_without_dated_duration"] += 1
            continue
        when = start + timedelta(seconds=duration)
        if when < clock_origin:
            continue
        payload = LapPayload(driver_id=str(row["driver_number"]),
                             lap_number=int(row["lap_number"]), lap_duration_seconds=duration)
        candidates.append((when, 4, "lap", index, payload, int(row["lap_number"]), Quality.ESTIMATED))
    for index, row in enumerate(raw["pit"]):
        when = _time(row["date"])
        if when < clock_origin:
            continue
        payload = PitStopPayload(driver_id=str(row["driver_number"]),
                                 lap_number=int(row["lap_number"]),
                                 lane_duration_seconds=_positive(row.get("lane_duration")),
                                 stop_duration_seconds=_positive(row.get("stop_duration")))
        candidates.append((when, 3, "pit_stop", index, payload,
                           int(row["lap_number"]), Quality.MEASURED))
    for index, row in enumerate(raw["stints"]):
        if row.get("lap_start") is None:
            counts["stints_without_lap_start"] += 1
            continue
        number, lap_start = int(row["driver_number"]), int(row["lap_start"])
        stint_when = lap_starts.get((number, lap_start))
        if stint_when is None:
            counts["stints_without_matching_lap_start"] += 1
            continue
        if stint_when < clock_origin:
            continue
        payload = StintPayload(driver_id=str(number), stint_number=int(row["stint_number"]),
                               lap_start=lap_start, compound=row.get("compound") or "UNKNOWN",
                               tyre_age_at_start=row.get("tyre_age_at_start"))
        candidates.append((stint_when, 1, "stint", index, payload, lap_start, Quality.ESTIMATED))
    for index, row in enumerate(raw["race_control"]):
        when = _time(row["date"])
        if when < clock_origin:
            continue
        payload = RaceControlPayload(category=row.get("category") or "Unknown",
                                     message=row.get("message") or "",
                                     flag=row.get("flag"), scope=row.get("scope"),
                                     sector=row.get("sector"),
                                     driver_id=str(row["driver_number"])
                                     if row.get("driver_number") is not None else None)
        candidates.append((when, 5, "race_control", index, payload,
                           row.get("lap_number"), Quality.MEASURED))
        signal = track_status_payload(row)
        if signal is not None:
            candidates.append((when, 6, "track_status", index, signal,
                               row.get("lap_number"), Quality.MEASURED))

    context_end = None if location_end_seconds is None else max(
        [location_end_seconds, *(_seconds(item[0], clock_origin) for item in candidates)])
    for index, row in enumerate(raw.get("weather", [])):
        when = _time(row["date"])
        seconds = _seconds(when, clock_origin)
        if seconds < 0:
            counts["weather_before_clock"] += 1
            continue
        if context_end is not None and seconds > context_end:
            counts["weather_after_replay_window"] += 1
            continue
        try:
            reading = weather_payload(row)
        except ValidationError:
            counts["weather_invalid_rows"] += 1
            continue
        candidates.append((when, 7, "weather", index, reading, None, Quality.MEASURED))

    candidates.sort(key=lambda item: (item[0], item[1], item[3]))
    events = []
    for sequence, (when, _, kind, index, payload, lap, quality) in enumerate(candidates):
        source_table = {"position_seed": "position", "lap": "laps",
                        "pit_stop": "pit", "stint": "stints", "track_status": "race_control"}
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
            session=session, event_id=f"{session.provider_key}:{kind}:{index}",
            type=event_type, source=SOURCE,
            source_timestamp=source_time,
            observed_at=when if kind == "lap" else source_time,
            ingested_at=ingested_at, session_time_seconds=_seconds(when, clock_origin),
            sequence=sequence, applicable_lap=lap, quality=quality, payload=payload,
        ))
        counts[kind] += 1
    return events, dict(counts)


def _location_samples(rows: list[dict], *, sample_hz: int = 2,
                      clock_origin: datetime = CLOCK_ORIGIN
                      ) -> tuple[list[list[float]], dict[str, int]]:
    """Retain actual source points at most twice per second; never synthesize coordinates."""
    selected: dict[int, tuple[float, int, int]] = {}
    removed_zero = 0
    removed_early = 0
    for row in rows:
        when = _time(row["date"])
        seconds = _seconds(when, clock_origin)
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


def _interval_samples(rows: list[dict], clock_origin: datetime = CLOCK_ORIGIN) -> dict[str, list[list]]:
    selected: dict[str, dict[int, list]] = defaultdict(dict)
    for row in rows:
        when = _time(row["date"])
        seconds = _seconds(when, clock_origin)
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


def _geometry(samples: list[list[float]], laps: list[dict],
              clock_origin: datetime = CLOCK_ORIGIN) -> dict:
    """Use one actual VER lap trace as approximate geometry, in provider units."""
    candidate = next((row for row in laps if row.get("driver_number") == 1
                      and row.get("lap_number") == 3 and row.get("date_start")
                      and _positive(row.get("lap_duration"))), None)
    if candidate is None:
        raise ValueError("VER lap 3 is unavailable for approximate circuit trace")
    start = _seconds(_time(candidate["date_start"]), clock_origin)
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
    result_ids = [str(row["driver_number"]) for row in results]
    if len(result_ids) != len(set(result_ids)) or set(result_ids) != set(state.drivers):
        raise ValueError("Replay/result driver coverage differs")
    classified = 0
    nonclassified = 0
    lap_counts_matching = 0
    unavailable_lap_counts = 0
    mismatches = []
    for result in results:
        driver_id = str(result["driver_number"])
        driver = state.drivers[driver_id]
        expected_laps = result.get("number_of_laps")
        if expected_laps is None:
            unavailable_lap_counts += 1
        elif (driver.lap or 0) != int(expected_laps):
            mismatches.append(f"{driver_id} laps {driver.lap} != {expected_laps}")
        else:
            lap_counts_matching += 1
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
            "lap_counts_matching": lap_counts_matching,
            "unavailable_result_lap_counts": unavailable_lap_counts,
            "checkpoint_count": len(source.checkpoint_indices)}


def build_replay_pack(output: Path | None = None, *, spec: ReplaySpec = DEFAULT_SESSION) -> dict:
    """Fetch once with OpenF1Client cache; write a compact, verified local pack."""
    output = Path(output or spec.pack_path)
    unavailable: dict[str, str] = {}
    with OpenF1Client() as client:
        metadata = client.get("sessions", session_key=spec.session_key)
        if len(metadata) != 1 or metadata[0].get("meeting_key") != spec.meeting_key or (
            _time(metadata[0]["date_start"]) != spec.clock_origin
            or metadata[0].get("year") != spec.season
            or metadata[0].get("session_name") != "Race"
        ):
            raise ValueError("Catalog and provider session metadata disagree")
        raw = {name: _rows(client, name, spec) for name in
               ("drivers", "position", "laps", "stints", "race_control",
                "intervals", "session_result")}
        for optional in ("pit", "weather"):
            try:
                raw[optional] = _rows(client, optional, spec)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 404:
                    raise
                raw[optional] = []
                unavailable[optional] = "HTTP 404: provider resource unavailable"
        drivers = sorted(raw["drivers"], key=lambda row: int(row["driver_number"]))
        numbers = [int(row["driver_number"]) for row in drivers]
        if len(numbers) < 2 or len(numbers) != len(set(numbers)):
            raise ValueError("Expected distinct driver identities")
        locations = {}
        location_coverage = {}
        for driver in drivers:
            number = int(driver["driver_number"])
            rows = client.get("location", session_key=spec.session_key, driver_number=number)
            if any(row.get("session_key") != spec.session_key or row.get("driver_number") != number
                   or row.get("meeting_key") != spec.meeting_key for row in rows):
                raise ValueError(f"Location response contains a foreign driver/session: {number}")
            locations[str(number)], location_coverage[str(number)] = _location_samples(
                rows, clock_origin=spec.clock_origin)
            print(f"location {number}: {location_coverage[str(number)]['sampled']} samples", flush=True)
        source_hashes = dict(client.hashes)
    session = SessionId(season=spec.season, round=spec.round, kind="race",
                        provider_key=f"openf1:{spec.session_key}")
    location_end = max([0.0, *(rows[-1][0] for rows in locations.values() if rows)])
    events, event_coverage = _timed_events(raw, session, datetime.now(UTC),
                                          spec.clock_origin, location_end)
    geometry = _geometry(locations["1"], raw["laps"], spec.clock_origin)
    pack = {
        "schema_version": 2,
        "session": session.model_dump(mode="json"),
        "slug": spec.slug,
        "session_name": f"{spec.title} — Race",
        "circuit_name": spec.circuit,
        "scheduled_laps": spec.scheduled_laps,
        "clock_origin_utc": spec.clock_origin.isoformat(),
        "provider": SOURCE,
        "capabilities": ["positions", "laps", "stints", "race_control_messages",
                         "approximate_location", "intervals"]
                        + ([] if "pit" in unavailable else ["pit_stops"])
                        + (["weather"] if event_coverage.get("weather") else [])
                        + (["track_status_signals"] if event_coverage.get("track_status") else []),
        "drivers": [{"driver_id": str(row["driver_number"]),
                     "number": int(row["driver_number"]),
                     "acronym": row.get("name_acronym"), "name": row.get("full_name"),
                     "team": row.get("team_name"), "team_color": row.get("team_colour")}
                    for row in drivers],
        "events": [event.model_dump(mode="json") for event in events],
        "locations": locations,
        "intervals": _interval_samples(raw["intervals"], spec.clock_origin),
        "geometry": geometry,
        "provenance": {"api": "https://api.openf1.org/v1",
                       "source_sha256_by_resource": source_hashes,
                       "source_license_note": "See docs/DATA_CONTRACTS.md; raw data is local only"},
        "coverage": {"raw_rows": {key: None if key in unavailable else len(rows)
                                for key, rows in raw.items()},
                     "unavailable_resources": unavailable,
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
    parser.add_argument("--session", choices=SESSIONS, default=DEFAULT_SESSION.slug)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    manifest = build_replay_pack(args.out, spec=SESSIONS[args.session])
    print(json.dumps({key: manifest[key] for key in
                      ("path", "sha256", "bytes", "event_count", "driver_count",
                       "sample_count", "qa")}, indent=2))


if __name__ == "__main__":
    main()
