"""Synthetic context fixtures exercise scope, transitions and as-of cutoffs."""

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from f1_racelab.session.contracts import SessionEvent, SessionId, WeatherPayload
from f1_racelab.session.openf1_context import track_status_payload, weather_payload
from f1_racelab.session.openf1_replay import _timed_events
from f1_racelab.session.replay_source import ReplaySource
from f1_racelab.session.validate_context import _cached_rows

ORIGIN = datetime(2024, 11, 3, 15, 30, tzinfo=UTC)
SESSION = SessionId(season=2024, round=21, kind="race", provider_key="openf1:9636")


@pytest.mark.parametrize(("row", "expected"), [
    ({"category": "Flag", "scope": "Track", "flag": "GREEN",
      "message": "GREEN LIGHT - PIT EXIT OPEN"}, None),
    ({"category": "Flag", "scope": "Sector", "sector": 3, "flag": "YELLOW",
      "message": "YELLOW IN TRACK SECTOR 3"}, None),
    ({"category": "Flag", "scope": "Track", "driver_number": 1,
      "flag": "GREEN", "message": "GREEN FLAG"}, None),
    ({"category": "Flag", "scope": "Track", "flag": "RED", "message": "RED FLAG"}, "red"),
    ({"category": "Flag", "scope": "Track", "flag": "GREEN",
      "message": "GREEN FLAG"}, "green"),
    ({"category": "SafetyCar", "message": "VIRTUAL SAFETY CAR DEPLOYED"}, "vsc"),
    ({"category": "SafetyCar", "message": "VIRTUAL SAFETY CAR ENDING"}, "vsc_ending"),
    ({"category": "SafetyCar", "message": "SAFETY CAR IN THIS LAP"}, "safety_car_ending"),
    ({"category": "SessionStatus", "message": "SESSION STARTED"}, "running_unknown"),
    ({"category": "SessionStatus", "message": "SESSION ABORTED"}, "suspended"),
])
def test_track_signal_scope_and_pending_endings(row: dict, expected: str | None) -> None:
    payload = track_status_payload(row)
    assert (payload.status if payload else None) == expected


@pytest.mark.parametrize("row", [
    {"humidity": 101}, {"wind_speed": -1}, {"wind_direction": 360},
    {"air_temperature": float("nan")}, {"rainfall": 2}, {},
])
def test_invalid_weather_is_rejected_without_coercing_it_into_measurement(row: dict) -> None:
    with pytest.raises(ValidationError):
        weather_payload(row)


def test_weather_units_and_false_rain_are_preserved() -> None:
    value = weather_payload({"air_temperature": 20.5, "track_temperature": 24.1,
                             "pressure": 925.4, "humidity": 89, "wind_speed": .4,
                             "wind_direction": 160, "rainfall": 0})
    assert value == WeatherPayload(air_temperature_c=20.5, track_temperature_c=24.1,
                                   pressure_mbar=925.4, humidity_percent=89,
                                   wind_speed_mps=.4, wind_direction_degrees=160,
                                   rainfall=False)


def test_context_replays_as_of_time_and_restart_clears_red_without_claiming_green() -> None:
    def date(seconds: float) -> str:
        return (ORIGIN + timedelta(seconds=seconds)).isoformat()

    control = [
        {"date": date(10), "category": "SafetyCar", "message": "VIRTUAL SAFETY CAR DEPLOYED"},
        {"date": date(20), "category": "SafetyCar", "message": "VIRTUAL SAFETY CAR ENDING"},
        {"date": date(30), "category": "Flag", "scope": "Track", "flag": "RED",
         "message": "RED FLAG"},
        {"date": date(40), "category": "SessionStatus", "message": "SESSION STARTED"},
        {"date": date(41), "category": "Flag", "scope": "Track", "flag": "GREEN",
         "message": "GREEN LIGHT - PIT EXIT OPEN"},
        {"date": date(200), "category": "Flag", "scope": "Track", "flag": "CHEQUERED",
         "message": "CHEQUERED FLAG"},
    ]
    weather = [{"date": date(t), "rainfall": rain}
               for t, rain in [(-5, 1), (5, 0), (15, 1), (201, 0)]]
    weather.append({"date": date(16), "humidity": 101})
    raw = {key: [] for key in ("position", "laps", "pit", "stints")}
    raw.update(race_control=control, weather=weather)
    events, counts = _timed_events(raw, SESSION, ORIGIN, ORIGIN, 200)
    assert counts["weather"] == 2
    assert counts["weather_before_clock"] == 1
    assert counts["weather_after_replay_window"] == 1
    assert counts["weather_invalid_rows"] == 1
    assert counts["track_status"] == 5  # pit-exit green is retained only as a message
    source = ReplaySource({
        "schema_version": 2, "session": SESSION.model_dump(mode="json"),
        "clock_origin_utc": ORIGIN.isoformat(), "drivers": [], "locations": {}, "intervals": {},
        "events": [event.model_dump(mode="json") for event in events],
        "capabilities": ["weather", "track_status_signals"],
    })
    assert source.state_at(4.999).weather is None
    assert source.state_at(14.999).weather.values.rainfall is False
    assert source.state_at(15).weather.values.rainfall is True
    assert source.state_at(19.999).flag == "vsc"
    pending = source.state_at(20)
    assert pending.track_status.signal.status == "vsc_ending"
    assert pending.flag is None
    assert source.state_at(39.999).flag == "red"
    assert source.state_at(40).track_status.signal.status == "running_unknown"
    assert source.state_at(41).flag is None
    last = source.state_at(200)
    assert last.track_status.signal.status == "chequered"
    assert last.weather.observed_at == ORIGIN + timedelta(seconds=15)
    assert last.session_time_seconds - last.weather.session_time_seconds > last.weather.max_age_seconds
    assert source.state_at(20) == pending  # backward seek cannot retain a later context reading


def test_old_pack_is_readable_and_context_requires_new_schema() -> None:
    timestamp = ORIGIN.isoformat()
    legacy = {
        "schema_version": 1, "session": SESSION.model_dump(mode="json"),
        "event_id": "legacy", "source": "synthetic", "source_timestamp": timestamp,
        "observed_at": timestamp, "ingested_at": timestamp, "session_time_seconds": 0,
        "sequence": 0, "quality": "measured", "type": "flag", "payload": {"flag": "red"},
    }
    pack = {
        "schema_version": 1, "session": SESSION.model_dump(mode="json"),
        "clock_origin_utc": timestamp, "drivers": [], "locations": {}, "intervals": {},
        "events": [legacy],
    }
    state = ReplaySource(pack).state_at(0)
    assert state.schema_version == 3 and state.flag == "red" and state.weather is None
    with pytest.raises(ValidationError, match="require schema_version 2"):
        SessionEvent.model_validate(legacy | {"type": "weather", "payload": {"rainfall": True}})
    with pytest.raises(ValueError, match="newer event"):
        ReplaySource(pack | {"events": [legacy | {"schema_version": 2}]})


def test_context_audit_rejects_changed_source_cache(tmp_path: Path) -> None:
    resource = "weather?session_key=9636"
    payload = b'[{"rainfall":1}]'
    expected_hash = hashlib.sha256(payload).hexdigest()
    source = ReplaySource({
        "schema_version": 1, "session": SESSION.model_dump(mode="json"),
        "clock_origin_utc": ORIGIN.isoformat(), "drivers": [], "locations": {},
        "intervals": {}, "events": [],
        "provenance": {"source_sha256_by_resource": {resource: expected_hash}},
    })
    path = tmp_path / "weather" / f"{hashlib.sha256(resource.encode()).hexdigest()[:20]}.json"
    path.parent.mkdir()
    path.write_bytes(payload)
    assert _cached_rows(source, "weather", tmp_path) == ([{"rainfall": 1}], expected_hash)
    path.write_bytes(b'[{"rainfall":0}]')
    with pytest.raises(ValueError, match="source hash differs"):
        _cached_rows(source, "weather", tmp_path)
