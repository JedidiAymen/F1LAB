"""Conservative OpenF1 weather and track-wide signal normalization.

Sector/driver flags and pit-exit green lights cannot establish a global
running condition. An ending message remains a pending transition, not green.
"""

from f1_racelab.session.contracts import TrackStatusPayload, WeatherPayload


def track_status_payload(row: dict) -> TrackStatusPayload | None:
    """Map only explicit, scoped source signals; preserve unknown restarts."""
    category = row.get("category")
    message = str(row.get("message") or "").strip()
    normalized = message.upper()
    if row.get("driver_number") is not None or row.get("sector") is not None:
        return None
    if category == "Flag" and row.get("scope") == "Track":
        if "PIT EXIT" in normalized:
            return None
        flags = {"GREEN": "green", "YELLOW": "yellow", "DOUBLE YELLOW": "yellow",
                 "RED": "red", "CHEQUERED": "chequered"}
        status = flags.get(str(row.get("flag") or ""))
        if status:
            return TrackStatusPayload.model_validate(
                {"status": status, "message": message, "basis": "track_flag"})
    if category == "SafetyCar" and row.get("scope") in (None, "Track"):
        status = {
            "VIRTUAL SAFETY CAR DEPLOYED": "vsc",
            "VIRTUAL SAFETY CAR ENDING": "vsc_ending",
            "SAFETY CAR DEPLOYED": "safety_car",
            "SAFETY CAR IN THIS LAP": "safety_car_ending",
        }.get(normalized)
        if status:
            return TrackStatusPayload.model_validate(
                {"status": status, "message": message, "basis": "safety_car_message"})
    if category == "SessionStatus" and row.get("scope") in (None, "Track"):
        status = {"SESSION STARTED": "running_unknown", "SESSION ABORTED": "suspended"}.get(normalized)
        if status:
            return TrackStatusPayload.model_validate(
                {"status": status, "message": message, "basis": "session_status"})
    return None


def weather_payload(row: dict) -> WeatherPayload:
    """Rename documented source units without interpolation or conversion."""
    rainfall = row.get("rainfall")
    if isinstance(rainfall, (bool, int)) and rainfall in (0, 1):
        rainfall = bool(rainfall)
    return WeatherPayload.model_validate({
        "air_temperature_c": row.get("air_temperature"),
        "track_temperature_c": row.get("track_temperature"),
        "humidity_percent": row.get("humidity"),
        "pressure_mbar": row.get("pressure"),
        "wind_direction_degrees": row.get("wind_direction"),
        "wind_speed_mps": row.get("wind_speed"),
        "rainfall": rainfall,
    })
