"""Distance-normalised lap telemetry tensors for Driver DNA.

Source: cached OpenF1 ``car_data`` (about 3.7 Hz), ``laps`` and ``drivers`` for the sessions whose full-race
telemetry is available locally (Monaco 2023, Brazil 2024, Monza 2025). Raw data stays git-ignored.

Per kept lap the channels speed, throttle, brake, gear, rpm and DRS-open are resampled onto ``GRID`` points of
normalised integrated distance (trapezoidal integral of speed, as in ``telemetry.distance_alignment``). Only
race laps that are not pit-out/in laps, are within ``SLOW_RATIO`` x the driver's median lap time (a data-quality
filter that does not use the driver label) and have a sample gap of at most ``MAX_GAP_S`` are kept.

Command: ``uv run python -m f1_racelab.ml.driver_dna.dataset``.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from f1_racelab.data.openf1_qualifying import RAW_ROOT, OpenF1Client

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "data/processed/driver_dna"
SESSIONS = {9094: ("Monaco", 2023), 9636: ("Brazil", 2024), 9912: ("Monza", 2025)}
CHANNELS = ("speed", "throttle", "brake", "gear", "rpm", "drs_open")
SCALES = np.array([350.0, 100.0, 100.0, 8.0, 13000.0, 1.0], dtype=np.float32)
GRID = 256
SLOW_RATIO = 1.07
MAX_GAP_S = 1.0
MIN_SAMPLES = 120


def _utc(values) -> pd.Series:
    return pd.to_datetime(values, utc=True, format="ISO8601").dt.tz_convert(None)


def resample_lap(samples: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> np.ndarray | None:
    """Return a [6, GRID] array for one lap, or None if the telemetry does not support it."""
    lap = samples[(samples.date >= start) & (samples.date <= end)]
    if len(lap) < MIN_SAMPLES:
        return None
    t = (lap.date - lap.date.iloc[0]).dt.total_seconds().to_numpy()
    if (np.diff(t) > MAX_GAP_S).any() or (np.diff(t) <= 0).any():
        return None
    speed = lap.speed.to_numpy(float)
    distance = np.concatenate([[0.0], np.cumsum((speed[1:] + speed[:-1]) / 2 / 3.6 * np.diff(t))])
    if distance[-1] < 500:
        return None
    grid = np.linspace(0, distance[-1], GRID)
    columns = [lap.speed, lap.throttle, lap.brake, lap.n_gear, lap.rpm, (lap.drs >= 10).astype(float)]
    out = np.stack([np.interp(grid, distance, c.to_numpy(float)) for c in columns]).astype(np.float32)
    return out


def build(cache_root: Path = RAW_ROOT, sessions: dict = SESSIONS) -> tuple[np.ndarray, pd.DataFrame]:
    tensors, meta = [], []
    index = _index(cache_root / "car_data")
    with OpenF1Client(cache_root, offline=True) as client:
        for session_key, (circuit, year) in sessions.items():
            laps = pd.DataFrame(client.get("laps", session_key=session_key))
            drivers = pd.DataFrame(client.get("drivers", session_key=session_key)).drop_duplicates("driver_number")
            team = drivers.set_index("driver_number").team_name.to_dict()
            acronym = drivers.set_index("driver_number").name_acronym.to_dict()
            laps = laps.dropna(subset=["date_start", "lap_duration"]).copy()
            laps["start"] = _utc(laps.date_start)
            laps["end"] = laps.start + pd.to_timedelta(laps.lap_duration, unit="s")
            for number, driver_laps in laps.groupby("driver_number"):
                path = index.get((session_key, int(number)))
                if path is None:
                    continue
                samples = pd.DataFrame(json.loads(path.read_text()))
                samples["date"] = _utc(samples.date)
                samples = samples.sort_values("date")
                driver_laps = driver_laps.sort_values("lap_number")
                pit_out = driver_laps.is_pit_out_lap.fillna(False).astype(bool)
                in_lap = pit_out.shift(-1, fill_value=False)
                median = driver_laps.lap_duration.median()
                keep = (~pit_out) & (~in_lap) & (driver_laps.lap_duration <= SLOW_RATIO * median)
                for row in driver_laps[keep].itertuples():
                    lap = resample_lap(samples, row.start, row.end)
                    if lap is None:
                        continue
                    tensors.append(lap)
                    meta.append({"session_key": session_key, "circuit": circuit, "year": year,
                                 "driver_number": int(number), "driver": acronym.get(number, str(number)),
                                 "team": team.get(number, "?"), "lap_number": int(row.lap_number),
                                 "lap_seconds": float(row.lap_duration)})
    return np.stack(tensors), pd.DataFrame(meta)


def _index(folder: Path) -> dict[tuple[int, int], Path]:
    """Map (session_key, driver_number) to the cached car_data file by reading each file's first record."""
    out = {}
    for path in folder.glob("*.json"):
        head = path.read_bytes()[:400].decode("utf8", "ignore")
        session, driver = re.search(r'"session_key":\s*(\d+)', head), re.search(r'"driver_number":\s*(\d+)', head)
        if session and driver:
            out[(int(session.group(1)), int(driver.group(1)))] = path
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    x, meta = build()
    np.savez_compressed(OUT / "laps.npz", x=x, scales=SCALES)
    meta.to_parquet(OUT / "laps_meta.parquet", index=False)
    summary = {"laps": len(meta), "grid": GRID, "channels": CHANNELS,
               "per_session": meta.groupby("circuit").size().to_dict(),
               "drivers_per_session": meta.groupby("circuit").driver.nunique().to_dict(),
               "shared_drivers_all_sessions": sorted(set.intersection(*[set(g.driver) for _, g in meta.groupby("circuit")]))}
    (OUT / "dataset_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
