"""Run real-data QA on an offline replay pack and save a reproducible report."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
import time
from pathlib import Path

from f1_racelab.session.catalog import PACK_ROOT, SESSIONS
from f1_racelab.session.contracts import DriverState, RaceState
from f1_racelab.session.openf1_replay import OUTPUT
from f1_racelab.session.reducer import reduce_event
from f1_racelab.session.replay_source import ReplaySource

SIDECAR_FIELDS = {
    "track_x", "track_y", "location_quality", "location_observed_at",
    "gap_to_leader_seconds", "gap_to_leader_text", "interval_ahead_seconds",
    "interval_ahead_text", "interval_observed_at",
}


def _compare_discrete(indexed: RaceState, direct: RaceState, seconds: float) -> None:
    if indexed.model_dump(exclude={"session_time_seconds", "drivers"}) != direct.model_dump(
        exclude={"session_time_seconds", "drivers"}
    ):
        raise AssertionError(f"Checkpoint event state disagrees at {seconds:.3f}s")
    for driver_id in indexed.drivers.keys() | direct.drivers.keys():
        left = indexed.drivers.get(driver_id, DriverState(driver_id=driver_id))
        right = direct.drivers.get(driver_id, DriverState(driver_id=driver_id))
        if left.model_dump(exclude=SIDECAR_FIELDS) != right.model_dump(exclude=SIDECAR_FIELDS):
            raise AssertionError(f"Driver state differs at {seconds:.3f}s: {driver_id}")


def validate(path: Path = OUTPUT) -> dict:
    path = Path(path)
    source = ReplaySource.from_file(path)
    duration = source.duration_seconds
    boundaries = {time for event in source.events for time in
                  (max(0, event.session_time_seconds - .001), event.session_time_seconds,
                   min(duration, event.session_time_seconds + .001))}
    times = sorted({0.0, duration, *(duration * i / 100 for i in range(101)), *boundaries})
    random_times = random.Random(42).sample(times, min(200, len(times)))
    expected_hashes = {}
    direct = RaceState(session=source.session, capabilities=tuple(source.pack.get("capabilities", ())))
    event_index = 0
    elapsed_ms = []
    for seconds in times:
        start = time.perf_counter()
        indexed = source.state_at(seconds)
        elapsed_ms.append((time.perf_counter() - start) * 1000)
        while event_index < len(source.events) and source.event_times[event_index] <= seconds:
            direct = reduce_event(direct, source.events[event_index])
            event_index += 1
        _compare_discrete(indexed, direct, seconds)
        if seconds in random_times:
            expected_hashes[seconds] = hashlib.sha256(indexed.model_dump_json().encode()).hexdigest()
    for seconds in random_times:
        actual = hashlib.sha256(source.state_at(seconds).model_dump_json().encode()).hexdigest()
        if actual != expected_hashes[seconds]:
            raise AssertionError(f"Arbitrary-order seek changed state at {seconds:.3f}s")
    measured_drivers = []
    missing_locations = []
    for driver in source.pack["drivers"]:
        driver_id = driver["driver_id"]
        rows = source.locations.get(driver_id, [])
        if not rows:
            missing_locations.append(driver_id)
            continue
        measured = rows[0]
        state = source.state_at(measured[0]).drivers[driver_id]
        if (state.track_x, state.track_y, str(state.location_quality)) != (
            float(measured[1]), float(measured[2]), "measured"
        ):
            raise AssertionError(f"Measured car location changed during seek: {driver_id}")
        measured_drivers.append(driver_id)
    final_state = source.state_at(duration)
    stint_count = sum(len(driver.tyre_stints) for driver in final_state.drivers.values())
    drivers_with_stints = sorted(
        driver_id for driver_id, driver in final_state.drivers.items() if driver.tyre_stints
    )
    report = {
        "pack_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "session": source.session.model_dump(mode="json"),
        "duration_seconds": duration,
        "drivers": len(source.pack["drivers"]),
        "discrete_events": len(source.events),
        "race_state_schema_version": final_state.schema_version,
        "tyre_stint_segments_at_pack_end": stint_count,
        "drivers_with_stint_segments": drivers_with_stints,
        "location_samples": sum(map(len, source.locations.values())),
        "checkpoint_count": len(source.checkpoint_indices),
        "seek_cases_matching_full_reducer": len(times),
        "event_boundary_cases": len(boundaries),
        "arbitrary_order_seek_cases_matching": len(random_times),
        "measured_sample_preserved": True,
        "drivers_with_measured_sample_verified": measured_drivers,
        "drivers_without_location_samples": missing_locations,
        "indexed_seek_p50_ms": round(statistics.median(elapsed_ms), 3),
        "indexed_seek_p95_ms": round(sorted(elapsed_ms)[int(.95 * (len(elapsed_ms) - 1))], 3),
        "limits": ["This pack only", "Approximate provider coordinates", "No full telemetry",
                   "No inferred green at ending/restart signals"],
    }
    destination = path.with_suffix(".qa.json")
    destination.write_text(json.dumps(report, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--pack", type=Path)
    group.add_argument("--all", action="store_true", help="Validate every audited local reference pack")
    args = parser.parse_args()
    if args.all:
        reports = [validate(spec.pack_path) for spec in SESSIONS.values()]
        report = {"packs": reports, "all_passed": True}
        PACK_ROOT.joinpath("golden_sessions.qa.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
    else:
        print(json.dumps(validate(args.pack or OUTPUT), indent=2))


if __name__ == "__main__":
    main()
