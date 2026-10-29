"""Position / gap time series sampled from the canonical RaceState.

Every sample is ``ReplaySource.state_at(t)``, so the chart is the same state the
timing tower shows at that instant (one clock, no parallel computation).
Samples are at multiples of ``step_seconds`` from session time 0 plus the final
instant. Gaps are seconds behind the leader as reported by the source; ``None``
means the source gave no value (leader, retired, not yet reported).
"""
from __future__ import annotations

from f1_racelab.session.replay_source import ReplaySource

MIN_STEP, MAX_STEP = 5.0, 300.0


def build_timeline(replay: ReplaySource, step_seconds: float = 30.0) -> dict:
    if not MIN_STEP <= step_seconds <= MAX_STEP:
        raise ValueError(f"step_seconds must be within {MIN_STEP}-{MAX_STEP}")
    duration = float(replay.duration_seconds)
    times: list[float] = []
    t = 0.0
    while t < duration:
        times.append(round(t, 3))
        t += step_seconds
    times.append(round(duration, 3))
    driver_ids = [driver["driver_id"] for driver in replay.pack["drivers"]]
    series = {driver: {"positions": [], "gaps": [], "laps": []} for driver in driver_ids}
    for moment in times:
        drivers = replay.state_at(moment).drivers
        for driver in driver_ids:
            state = drivers.get(driver)
            series[driver]["positions"].append(state.position if state else None)
            series[driver]["gaps"].append(state.gap_to_leader_seconds if state else None)
            series[driver]["laps"].append(state.lap if state else None)
    return {"step_seconds": step_seconds, "duration_seconds": duration, "times": times,
            "drivers": [{"driver_id": driver, **series[driver]} for driver in driver_ids]}
