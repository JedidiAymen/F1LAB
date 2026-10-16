"""Run real-data QA on an offline replay pack and save a reproducible report."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from pathlib import Path

from f1_racelab.session.openf1_replay import OUTPUT
from f1_racelab.session.reducer import seek_state
from f1_racelab.session.replay_source import ReplaySource


def validate(path: Path = OUTPUT) -> dict:
    path = Path(path)
    source = ReplaySource.from_file(path)
    duration = source.duration_seconds
    times = sorted({0.0, duration, *(duration * i / 100 for i in range(101)),
                    *(event.session_time_seconds for event in source.events[::50])})
    elapsed_ms = []
    for seconds in times:
        start = time.perf_counter()
        indexed = source.state_at(seconds)
        elapsed_ms.append((time.perf_counter() - start) * 1000)
        direct = seek_state(source.session, source.events, seconds)
        if indexed.event_log != direct.event_log or indexed.flag != direct.flag:
            raise AssertionError(f"Checkpoint seek disagrees with full reducer at {seconds:.3f}s")
        for driver_id in indexed.drivers:
            left = indexed.drivers[driver_id]
            right = direct.drivers.get(driver_id)
            if right and (left.position, left.lap, left.tyre_compound, left.pit_count) != (
                right.position, right.lap, right.tyre_compound, right.pit_count
            ):
                raise AssertionError(f"Driver state differs at {seconds:.3f}s: {driver_id}")
    driver_id = source.pack["drivers"][0]["driver_id"]
    measured = source.locations[driver_id][100]
    state = source.state_at(measured[0]).drivers[driver_id]
    if (state.track_x, state.track_y, str(state.location_quality)) != (
        float(measured[1]), float(measured[2]), "measured"
    ):
        raise AssertionError("Measured car location changed during seek")
    report = {
        "pack_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "session": source.session.model_dump(mode="json"),
        "duration_seconds": duration,
        "drivers": len(source.pack["drivers"]),
        "discrete_events": len(source.events),
        "location_samples": sum(map(len, source.locations.values())),
        "checkpoint_count": len(source.checkpoint_indices),
        "seek_cases_matching_full_reducer": len(times),
        "measured_sample_preserved": True,
        "indexed_seek_p50_ms": round(statistics.median(elapsed_ms), 3),
        "indexed_seek_p95_ms": round(sorted(elapsed_ms)[int(.95 * (len(elapsed_ms) - 1))], 3),
        "limits": ["One race", "Approximate provider coordinates", "No full telemetry",
                   "No sector-correct global flag inference"],
    }
    destination = path.with_suffix(".qa.json")
    destination.write_text(json.dumps(report, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(validate(args.pack), indent=2))


if __name__ == "__main__":
    main()
