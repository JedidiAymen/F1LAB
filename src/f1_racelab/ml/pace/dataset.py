"""Race-pace forecasting dataset: one row per (driver, lap L) forecasting lap L+1.

Decision time ``cutoff`` is the instant lap L ends (= start of lap L+1). Every
feature is an observation at or before ``cutoff`` (laps <= L, weather/intervals
as-of cutoff, race-control messages <= cutoff), except two explicitly labelled
*scenario inputs* known to the team when planning the next lap: the tyre
compound and tyre age at lap L+1 (taken from the stint table).

Target: ``delta_seconds = lap_duration(L+1) - anchor_seconds`` where the anchor
is the median of the driver's last three clean laps <= L. Models predict the
delta and the forecast is ``anchor + delta`` (circuit lap-time scale cancels).

Eligibility: a row is a **green-flag clean** forecast when lap L+1 is not lap 1,
not an in-lap/out-lap, has a duration, and its regime is ``green``. Rows whose
lap L+1 is yellow / SC-VSC / red are kept with their regime so interrupted laps
are reported separately and never mixed into green-flag training.

Units: seconds, km/h not used, temperatures in Celsius, intervals in seconds.
Fuel mass is not observed; ``laps_remaining`` / ``lap`` are proxies only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from f1_racelab.ml.common.contracts import FeatureSpec

HISTORY_LAPS = 5
ANCHOR_LAPS = 3
MIN_ANCHOR_LAPS = 2
COMPOUNDS = ("SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET", "UNKNOWN")
NEUTRAL_START = {"SAFETY CAR DEPLOYED", "VIRTUAL SAFETY CAR DEPLOYED"}
NEUTRAL_END = {"SAFETY CAR IN THIS LAP", "VIRTUAL SAFETY CAR ENDING"}

FEATURES: list[FeatureSpec] = [
    FeatureSpec(name="lap", unit="lap number", available_at="cutoff (lap L)"),
    FeatureSpec(name="laps_remaining", unit="laps", available_at="pre-race (scheduled distance)"),
    FeatureSpec(name="tyre_age_next", unit="laps", available_at="scenario input for lap L+1"),
    FeatureSpec(name="stint_number_next", unit="count", available_at="scenario input for lap L+1"),
    FeatureSpec(name="compound_next", unit="category", available_at="scenario input for lap L+1"),
    FeatureSpec(name="laps_in_stint", unit="laps", available_at="cutoff"),
    FeatureSpec(name="last1", unit="s vs anchor", available_at="cutoff"),
    FeatureSpec(name="last2", unit="s vs anchor", available_at="cutoff"),
    FeatureSpec(name="last3", unit="s vs anchor", available_at="cutoff"),
    FeatureSpec(name="slope5", unit="s/lap over last clean laps", available_at="cutoff"),
    FeatureSpec(name="stint_best_delta", unit="s vs anchor", available_at="cutoff"),
    FeatureSpec(name="n_clean_history", unit="laps", available_at="cutoff"),
    FeatureSpec(name="track_temp", unit="degC", available_at="latest observation <= cutoff"),
    FeatureSpec(name="air_temp", unit="degC", available_at="latest observation <= cutoff"),
    FeatureSpec(name="humidity", unit="percent", available_at="latest observation <= cutoff"),
    FeatureSpec(name="wind_speed", unit="m/s", available_at="latest observation <= cutoff"),
    FeatureSpec(name="rainfall", unit="0/1 flag", available_at="latest observation <= cutoff"),
    FeatureSpec(name="weather_age_s", unit="s", available_at="cutoff"),
    FeatureSpec(name="interval_ahead", unit="s", available_at="latest observation <= cutoff"),
    FeatureSpec(name="gap_to_leader", unit="s", available_at="latest observation <= cutoff"),
    FeatureSpec(name="intervals_age_s", unit="s", available_at="cutoff"),
    FeatureSpec(name="neutral_in_last3", unit="count of laps", available_at="cutoff"),
    FeatureSpec(name="yellow_in_last1", unit="0/1", available_at="cutoff"),
    FeatureSpec(name="laps_since_neutral", unit="laps (cap 50)", available_at="cutoff"),
]
NUMERIC = [f.name for f in FEATURES if f.name != "compound_next"]
CATEGORICAL = ["compound_next"]
IDENTITY = ["driver_number", "circuit"]
# Columns that describe the forecast target or lap L+1 and must never be features.
FORBIDDEN_AS_FEATURES = ["next_lap_seconds", "delta_seconds", "regime_next", "eligible_green_next",
                         "next_is_out_lap", "next_is_in_lap"]


def _utc(values: pd.Series) -> pd.Series:
    """Parse ISO timestamps to timezone-naive UTC (uniform arithmetic, numpy-safe)."""
    return pd.to_datetime(values, utc=True, format="ISO8601").dt.tz_convert(None)


def _neutral_intervals(control: pd.DataFrame) -> tuple[list[tuple], list[tuple], list[pd.Timestamp]]:
    """(neutral SC/VSC intervals, red intervals, yellow instants) from race control."""
    neutral, red, yellow = [], [], []
    start = None
    red_start = None
    for row in control.sort_values("date").itertuples():
        msg = str(row.message).upper()
        if msg in NEUTRAL_START and start is None:
            start = row.date
        elif msg in NEUTRAL_END and start is not None:
            neutral.append((start, row.date))
            start = None
        flag = str(getattr(row, "flag", "") or "").upper()
        if flag == "RED" and red_start is None:
            red_start = row.date
        elif red_start is not None and (msg.startswith("GREEN LIGHT") or msg == "SESSION STARTED"):
            red.append((red_start, row.date))
            red_start = None
        if flag in ("YELLOW", "DOUBLE YELLOW"):
            yellow.append(row.date)
    if start is not None:
        neutral.append((start, control["date"].max()))
    if red_start is not None:
        red.append((red_start, control["date"].max()))
    return neutral, red, yellow


def _lap_regimes(laps: pd.DataFrame, control: pd.DataFrame, buffer: pd.Timedelta) -> pd.Series:
    neutral, red, yellow = _neutral_intervals(control) if len(control) else ([], [], [])
    yellow_arr = np.array(yellow, dtype="datetime64[ns]") if yellow else np.array([], dtype="datetime64[ns]")
    start = laps["start"].to_numpy("datetime64[ns]")
    end = laps["end"].to_numpy("datetime64[ns]")
    regime = np.full(len(laps), "green", dtype=object)

    def overlap(a, b, buf):
        a, b = np.datetime64(a), np.datetime64(b + buf)
        return (start <= b) & (end >= a)

    if len(yellow_arr):
        inside = ((yellow_arr[None, :] >= start[:, None]) & (yellow_arr[None, :] <= end[:, None])).any(axis=1)
        regime[inside] = "yellow"
    for a, b in neutral:
        regime[overlap(a, b, buffer)] = "sc_vsc"
    for a, b in red:
        regime[overlap(a, b, buffer)] = "red"
    return pd.Series(regime, index=laps.index)


def _tyre_table(stints: pd.DataFrame, laps: pd.DataFrame) -> pd.DataFrame:
    """compound / tyre age / stint number for every (driver, lap) from the stint table."""
    rows = []
    stints = stints.dropna(subset=["lap_start"])
    for stint in stints.itertuples():
        last = stint.lap_end if (pd.notna(stint.lap_end) and stint.lap_end > 0) else laps["lap_number"].max()
        for lap in range(int(stint.lap_start), int(last) + 1):
            rows.append((int(stint.driver_number), lap, str(stint.compound).upper() if pd.notna(stint.compound)
                         else "UNKNOWN", int(stint.stint_number),
                         float(stint.tyre_age_at_start or 0) + (lap - int(stint.lap_start)),
                         lap - int(stint.lap_start) + 1))
    table = pd.DataFrame(rows, columns=["driver_number", "lap_number", "compound", "stint_number",
                                        "tyre_age", "laps_in_stint"])
    return table.drop_duplicates(["driver_number", "lap_number"], keep="last")


def build_race_frame(resources: dict[str, list[dict]], *, race_id: str, year: int, circuit: str) -> pd.DataFrame:
    """Build the forecasting table for one race session from raw OpenF1 resources."""
    laps = pd.DataFrame(resources["laps"])
    if laps.empty:
        return pd.DataFrame()
    laps["start"] = _utc(laps["date_start"])
    laps["lap_duration"] = pd.to_numeric(laps["lap_duration"], errors="coerce")
    laps = laps.dropna(subset=["start"]).sort_values(["driver_number", "lap_number"]).reset_index(drop=True)
    nxt_start = laps.groupby("driver_number")["start"].shift(-1)
    own_end = laps["start"] + pd.to_timedelta(laps["lap_duration"], unit="s")
    laps["end"] = nxt_start.fillna(own_end)
    laps = laps.dropna(subset=["end"]).reset_index(drop=True)
    scheduled = int(laps["lap_number"].max())
    median_lap = float(laps["lap_duration"].dropna().median())

    control = pd.DataFrame(resources.get("race_control") or [])
    if len(control):
        control["date"] = _utc(control["date"])
    laps["regime"] = _lap_regimes(laps, control, pd.Timedelta(seconds=median_lap)) if len(control) \
        else "green"
    out_lap = laps["is_pit_out_lap"].fillna(False).astype(bool)
    laps["is_out"] = out_lap
    laps["is_in"] = laps.groupby("driver_number")["is_out"].shift(-1).eq(True)
    laps["clean"] = (laps["lap_duration"].notna() & ~laps["is_out"] & ~laps["is_in"]
                     & (laps["lap_number"] > 1) & (laps["regime"] == "green"))

    stints = pd.DataFrame(resources.get("stints") or [])
    tyres = _tyre_table(stints, laps) if len(stints) else pd.DataFrame(
        columns=["driver_number", "lap_number", "compound", "stint_number", "tyre_age", "laps_in_stint"])

    weather = pd.DataFrame(resources.get("weather") or [])
    if len(weather):
        weather["date"] = _utc(weather["date"])
        weather = weather.sort_values("date")
    intervals = pd.DataFrame(resources.get("intervals") or [])
    if len(intervals):
        intervals["date"] = _utc(intervals["date"])
        for col in ("interval", "gap_to_leader"):
            intervals[col] = pd.to_numeric(intervals[col], errors="coerce")
        intervals = intervals.sort_values("date")

    records = []
    for driver, group in laps.groupby("driver_number", sort=False):
        group = group.reset_index(drop=True)
        durations = group["lap_duration"].to_numpy(float)
        clean = group["clean"].to_numpy(bool)
        regimes = group["regime"].to_numpy(object)
        lap_numbers = group["lap_number"].to_numpy(int)
        for i in range(len(group) - 1):
            history = [j for j in range(max(0, i - HISTORY_LAPS + 1), i + 1) if clean[j]]
            if len(history) < MIN_ANCHOR_LAPS:
                continue
            anchor_idx = history[-ANCHOR_LAPS:]
            anchor = float(np.median(durations[anchor_idx]))
            nxt = i + 1
            if lap_numbers[nxt] != lap_numbers[i] + 1:
                continue
            slope = float(np.polyfit(np.arange(len(history)), durations[history], 1)[0]) \
                if len(history) >= 3 else np.nan
            deltas = [durations[j] - anchor if j >= 0 and clean[j] else np.nan for j in (i, i - 1, i - 2)] \
                if i >= 2 else [durations[i] - anchor if clean[i] else np.nan, np.nan, np.nan]
            neutral_idx = np.flatnonzero(np.isin(regimes[: i + 1], ["sc_vsc", "red"]))
            records.append({
                "race_id": race_id, "year": year, "circuit": circuit, "driver_number": int(driver),
                "lap": int(lap_numbers[i]), "laps_remaining": scheduled - int(lap_numbers[i]),
                "cutoff": group.loc[i, "end"], "anchor_seconds": anchor,
                "next_lap_seconds": durations[nxt], "delta_seconds": durations[nxt] - anchor,
                "regime_next": regimes[nxt], "next_is_out_lap": bool(group.loc[nxt, "is_out"]),
                "next_is_in_lap": bool(group.loc[nxt, "is_in"]),
                "eligible_green_next": bool(clean[nxt]),
                "last1": deltas[0], "last2": deltas[1], "last3": deltas[2], "slope5": slope,
                "n_clean_history": len(history),
                "neutral_in_last3": int(np.isin(regimes[max(0, i - 2): i + 1], ["sc_vsc", "red"]).sum()),
                "yellow_in_last1": int(regimes[i] == "yellow"),
                "laps_since_neutral": float(min(50, i - neutral_idx[-1])) if len(neutral_idx) else 50.0,
            })
    frame = pd.DataFrame(records)
    if frame.empty:
        return frame
    frame = frame.merge(tyres.rename(columns={"lap_number": "_n"}).assign(lap=lambda d: d["_n"] - 1)
                        .rename(columns={"compound": "compound_next", "stint_number": "stint_number_next",
                                         "tyre_age": "tyre_age_next", "laps_in_stint": "laps_in_stint_next"})
                        .drop(columns="_n"), on=["driver_number", "lap"], how="left")
    frame["compound_next"] = frame["compound_next"].fillna("UNKNOWN")
    frame["laps_in_stint"] = (frame["laps_in_stint_next"] - 1).clip(lower=0)
    # Stint-best clean delta so far (needs per-row stint membership of laps <= L).
    best = {}
    clean_lookup = laps.loc[laps["clean"], ["driver_number", "lap_number", "lap_duration"]].merge(
        tyres[["driver_number", "lap_number", "stint_number"]], on=["driver_number", "lap_number"], how="left")
    for (driver, stint), group in clean_lookup.groupby(["driver_number", "stint_number"]):
        best[(driver, stint)] = (group["lap_number"].to_numpy(), group["lap_duration"].to_numpy())

    def stint_best(row) -> float:
        entry = best.get((row.driver_number, row.stint_number_next))
        if entry is None:
            return np.nan
        mask = entry[0] <= row.lap
        return float(entry[1][mask].min() - row.anchor_seconds) if mask.any() else np.nan

    frame["stint_best_delta"] = [stint_best(r) for r in frame.itertuples()]

    if len(weather):
        weather_cols = ["date", "track_temperature", "air_temperature", "humidity", "wind_speed", "rainfall"]
        merged = pd.merge_asof(frame.sort_values("cutoff"), weather[weather_cols], left_on="cutoff",
                               right_on="date", direction="backward")
        merged["weather_age_s"] = (merged["cutoff"] - merged["date"]).dt.total_seconds()
        frame = merged.rename(columns={"track_temperature": "track_temp", "air_temperature": "air_temp"}) \
            .drop(columns="date")
    else:
        for col in ("track_temp", "air_temp", "humidity", "wind_speed", "rainfall", "weather_age_s"):
            frame[col] = np.nan
    if len(intervals):
        merged = pd.merge_asof(frame.sort_values("cutoff"),
                               intervals[["date", "driver_number", "interval", "gap_to_leader"]],
                               left_on="cutoff", right_on="date", by="driver_number", direction="backward")
        merged["intervals_age_s"] = (merged["cutoff"] - merged["date"]).dt.total_seconds()
        frame = merged.rename(columns={"interval": "interval_ahead"}).drop(columns="date")
    else:
        for col in ("interval_ahead", "gap_to_leader", "intervals_age_s"):
            frame[col] = np.nan
    return frame.sort_values(["driver_number", "lap"]).reset_index(drop=True)


def build_dataset(years: list[int], *, offline: bool = True) -> tuple[pd.DataFrame, list[dict]]:
    """Assemble all cached race sessions; returns (frame, per-race coverage report)."""
    from f1_racelab.data.openf1_qualifying import RAW_ROOT, OpenF1Client
    from f1_racelab.ml.pace.fetch import RESOURCES, race_sessions

    frames, report = [], []
    with OpenF1Client(RAW_ROOT, offline=offline) as client:
        for item in race_sessions(client, years):
            resources, missing = {}, []
            for name in RESOURCES:
                try:
                    resources[name] = client.get(name, session_key=item["session_key"])
                except (FileNotFoundError, OSError, ValueError):
                    resources[name] = []
                    missing.append(name)
            entry = {"race_id": str(item["session_key"]), "year": item["year"],
                     "event": item["meeting_name"], "circuit": item["circuit"],
                     "date_start": item["date_start"], "missing": missing, "rows": 0}
            if "laps" in missing or not resources["laps"]:
                entry["status"] = "SKIPPED_NO_LAPS"
                report.append(entry)
                continue
            frame = build_race_frame(resources, race_id=str(item["session_key"]), year=item["year"],
                                     circuit=item["circuit"] or "unknown")
            frame["event"] = item["meeting_name"]
            frame["race_start"] = _utc(pd.Series([item["date_start"]])).iloc[0]
            entry.update(rows=len(frame), status="OK" if len(frame) else "EMPTY")
            if len(frame):
                entry["green_rows"] = int(frame["eligible_green_next"].sum())
                frames.append(frame)
            report.append(entry)
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()), report
