"""Audit normalized replay context against hashed, local provider responses."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from itertools import pairwise
from pathlib import Path

from f1_racelab.data.openf1_qualifying import RAW_ROOT
from f1_racelab.session.catalog import DEFAULT_SESSION, PACK_ROOT, SESSIONS
from f1_racelab.session.contracts import TrackStatusPayload, WeatherPayload
from f1_racelab.session.replay_source import ReplaySource

# Independently reviewed source-message boundaries for the three reference races.
# These do not call the adapter's mapper; a changed source timeline needs review.
GOLDEN_SIGNALS: dict[str, list[tuple[float, str]]] = {
    "openf1:9912": [(214.805, "running_unknown"), (4619.0, "chequered")],
    "openf1:9094": [(183.926, "running_unknown"), (6718.0, "chequered")],
    "openf1:9636": [
        (1197.515, "running_unknown"), (3501.0, "vsc"), (3590.0, "vsc_ending"),
        (3773.0, "safety_car"), (4041.752, "suspended"), (4042.0, "red"),
        (5520.39, "running_unknown"), (6194.0, "safety_car"),
        (6484.0, "safety_car_ending"), (8812.0, "chequered"),
    ],
}
STEADY_FLAGS = {"green", "yellow", "red", "safety_car", "vsc", "chequered"}


def _cached_rows(source: ReplaySource, endpoint: str, cache_root: Path = RAW_ROOT) -> tuple[list, str]:
    key = int(str(source.session.provider_key).rsplit(":", 1)[1])
    resource = f"{endpoint}?session_key={key}"
    expected = source.pack["provenance"]["source_sha256_by_resource"][resource]
    cache_key = hashlib.sha256(resource.encode()).hexdigest()[:20]
    path = cache_root / endpoint / f"{cache_key}.json"
    payload = path.read_bytes()
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise ValueError(f"Cached {endpoint} source hash differs from replay provenance")
    return json.loads(payload), actual


def validate_context(path: Path, *, cache_root: Path = RAW_ROOT) -> dict:
    """Verify as-of weather and reviewed track signals without network access."""
    source = ReplaySource.from_file(path)
    if not {"weather", "track_status_signals"} <= set(source.pack.get("capabilities", [])):
        raise ValueError("Rebuild the pack with weather and track-status signal capabilities")
    raw_weather, weather_hash = _cached_rows(source, "weather", cache_root)
    raw_control, control_hash = _cached_rows(source, "race_control", cache_root)
    weather_events = [event for event in source.events if isinstance(event.payload, WeatherPayload)]
    weather_times = []
    for event in weather_events:
        raw = raw_weather[int(event.event_id.rsplit(":", 1)[1])]
        observed = datetime.fromisoformat(raw["date"])
        seconds = (observed - source.clock_origin).total_seconds()
        expected = {
            "air_temperature_c": raw.get("air_temperature"),
            "track_temperature_c": raw.get("track_temperature"),
            "humidity_percent": raw.get("humidity"), "pressure_mbar": raw.get("pressure"),
            "wind_direction_degrees": raw.get("wind_direction"),
            "wind_speed_mps": raw.get("wind_speed"),
            "rainfall": None if raw.get("rainfall") is None else bool(raw["rainfall"]),
        }
        if event.payload.model_dump() != expected or event.observed_at != observed or (
            event.source_timestamp != observed or event.session_time_seconds != seconds
        ):
            raise AssertionError(f"Weather payload/source timestamp differs: {event.event_id}")
        weather = source.state_at(seconds).weather
        if weather is None or weather.event_id != event.event_id or weather.values.model_dump() != expected:
            raise AssertionError(f"Weather missing at source cutoff: {seconds}")
        before = source.state_at(max(0, seconds - .001)).weather
        if before and before.session_time_seconds > max(0, seconds - .001):
            raise AssertionError(f"Future weather leaked before its observation: {seconds}")
        weather_times.append(seconds)
    raw_in_window = sum(0 <= (datetime.fromisoformat(row["date"]) - source.clock_origin).total_seconds()
                        <= source.duration_seconds for row in raw_weather)
    invalid = source.pack["coverage"]["events"].get("weather_invalid_rows", 0)
    if len(weather_events) + invalid != raw_in_window:
        raise AssertionError("Weather source/event coverage is not reconciled")

    track_events = [event for event in source.events if isinstance(event.payload, TrackStatusPayload)]
    actual_signals = [(event.session_time_seconds, event.payload.status)
                      for event in track_events if isinstance(event.payload, TrackStatusPayload)]
    expected_signals = GOLDEN_SIGNALS[str(source.session.provider_key)]
    if actual_signals != expected_signals:
        raise AssertionError(f"Track signals differ from reviewed reference: {actual_signals}")
    for index, (seconds, status) in enumerate(expected_signals):
        event = track_events[index]
        raw = raw_control[int(event.event_id.rsplit(":", 1)[1])]
        signal = source.state_at(seconds).track_status
        if signal is None or signal.signal.status != status or signal.signal.message != raw["message"]:
            raise AssertionError(f"Track signal/source mismatch at {seconds}")
        before_signal = source.state_at(seconds - .001).track_status
        expected_before = expected_signals[index - 1][1] if index else None
        if (before_signal.signal.status if before_signal else None) != expected_before:
            raise AssertionError(f"Track signal leaked before boundary {seconds}")
        expected_flag = status if status in STEADY_FLAGS else None
        if source.state_at(seconds).flag != expected_flag:
            raise AssertionError(f"Pending/unknown status was converted to a steady flag at {seconds}")
        if raw.get("driver_number") is not None or raw.get("sector") is not None:
            raise AssertionError(f"Driver/sector signal became global at {seconds}")
    final_weather = source.state_at(source.duration_seconds).weather
    report = {
        "pack_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "session": source.session.model_dump(mode="json"),
        "weather_source_rows": len(raw_weather),
        "weather_events_verified_against_source": len(weather_events),
        "weather_cutoff_checks": len(weather_events) * 2,
        "weather_invalid_rows": invalid,
        "weather_max_sample_gap_seconds": round(max(
            [0.0, *(b - a for a, b in pairwise(weather_times))]), 3),
        "last_weather_age_at_pack_end_seconds": round(
            source.duration_seconds - final_weather.session_time_seconds, 3) if final_weather else None,
        "reviewed_track_signal_boundaries_verified": len(expected_signals),
        "source_sha256": {"weather": weather_hash, "race_control": control_hash},
        "limits": ["Rainfall is presence, not intensity or track grip",
                   "Ending signals do not prove green running",
                   "Last signal can remain pending until another source signal"],
    }
    path.with_suffix(".context.qa.json").write_text(json.dumps(report, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--all", action="store_true")
    group.add_argument("--pack", type=Path)
    args = parser.parse_args()
    if args.all:
        report = {"packs": [validate_context(spec.pack_path) for spec in SESSIONS.values()],
                  "all_passed": True}
        PACK_ROOT.joinpath("golden_context.qa.json").write_text(json.dumps(report, indent=2))
    else:
        report = validate_context(args.pack or DEFAULT_SESSION.pack_path)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
