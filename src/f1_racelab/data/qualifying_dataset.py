"""Build reproducible, resumable pre-qualifying multi-weekend datasets.

Sprint weekends deliberately excluded from V1: FP3 may not exist.
Use original F1LAB src/f1_racelab/features/qualifying.py for each weekend.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import fastf1
import pandas as pd

from f1_racelab.features.qualifying import build_weekend_dataset

PROJECT_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_ROOT = PROJECT_ROOT / "data" / "processed"


def _safe_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _validate(frame: pd.DataFrame, label: str) -> None:
    required = {"year", "event", "driver", "final_position", "q1_gap_pct", "fp3_best_seconds"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{label}: missing columns: {sorted(missing)}")
    if frame.duplicated(["year", "event", "driver"]).any():
        raise ValueError(f"{label}: duplicate driver-event rows")
    if frame["q1_gap_pct"].notna().sum() < 8:
        raise ValueError(f"{label}: fewer than eight drivers with valid Q1 pace")
    if frame["fp3_best_seconds"].notna().sum() < 8:
        raise ValueError(f"{label}: fewer than eight drivers with valid FP3 pace")


def scheduled_conventional_events(year: int) -> list[dict]:
    schedule = fastf1.get_event_schedule(year, include_testing=False)
    if not {"EventFormat", "RoundNumber", "EventName"}.issubset(schedule.columns):
        raise ValueError(f"Unsupported FastF1 schedule columns for {year}")
    events = schedule.loc[
        (schedule["EventFormat"].astype(str).str.lower() == "conventional")
        & (pd.to_numeric(schedule["RoundNumber"], errors="coerce") > 0)
    ]
    events = events.sort_values("RoundNumber")
    return [
        {"year": int(year), "round": int(row["RoundNumber"]), "event": str(row["EventName"])}
        for _, row in events.iterrows()
    ]


def build_dataset(
    years: list[int], *, refresh: bool = False,
    max_events_per_year: int | None = None,
    output_root: Path = OUTPUT_ROOT,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build per-event cache + combined Parquet. Errors are reported, not silently hidden."""
    output_root = Path(output_root)
    weekend_root = output_root / "qualifying_weekends"
    weekend_root.mkdir(parents=True, exist_ok=True)
    years = sorted(set(years))
    frames: list[pd.DataFrame] = []
    report: list[dict] = []

    for year in years:
        try:
            events = scheduled_conventional_events(year)
        except Exception as exc:
            report.append({"year": year, "round": None, "event": "schedule", "status": "ERROR", "rows": 0, "detail": str(exc)[:300]})
            print(f"[ERROR] {year} schedule: {exc}", flush=True)
            continue
        if max_events_per_year is not None:
            events = events[:max_events_per_year]
        print(f"{year}: {len(events)} conventional weekends selected", flush=True)

        for item in events:
            number, name = item["round"], item["event"]
            destination = weekend_root / f"{year}_{number:02d}_{_safe_name(name)}.parquet"
            status = "CACHED"
            try:
                if destination.exists() and not refresh:
                    frame = pd.read_parquet(destination)
                else:
                    frame = build_weekend_dataset(year, number)
                    # The original function writes its event input into the table.
                    # Always use a consistent, human-readable event name for ML grouping.
                    frame["year"] = year
                    frame["round"] = number
                    frame["event"] = name
                    _validate(frame, f"{year} round {number}")
                    frame.to_parquet(destination, index=False)
                    status = "BUILT"
                # Validate cached frames too; don't silently trust old cache.
                _validate(frame, f"{year} round {number}")
                frames.append(frame)
                report.append({"year": year, "round": number, "event": name, "status": status, "rows": len(frame), "detail": ""})
                print(f"[{status}] {year} R{number:02d} {name}: {len(frame)} driver rows", flush=True)
            except Exception as exc:
                report.append({"year": year, "round": number, "event": name, "status": "ERROR", "rows": 0, "detail": f"{type(exc).__name__}: {exc}"[:300]})
                print(f"[ERROR] {year} R{number:02d} {name}: {type(exc).__name__}: {exc}", flush=True)

    log = pd.DataFrame(report)
    suffix = "_".join(map(str, years))
    log.to_csv(output_root / f"qualifying_ingestion_{suffix}.csv", index=False)
    if not frames:
        raise RuntimeError("No qualifying weekends built. Check the ingestion CSV for errors.")
    data = pd.concat(frames, ignore_index=True)
    if data.duplicated(["year", "round", "driver"]).any():
        raise ValueError("Combined dataset contains duplicate (year, round, driver) keys")
    data = data.sort_values(["year", "round", "final_position"], kind="stable").reset_index(drop=True)
    data.to_parquet(output_root / f"qualifying_{suffix}.parquet", index=False)
    print(json.dumps({
        "dataset": str(output_root / f"qualifying_{suffix}.parquet"),
        "weekends": int(data[["year", "round"]].drop_duplicates().shape[0]),
        "rows": len(data),
        "ingestion_errors": int((log["status"] == "ERROR").sum()),
        "status_file": str(output_root / f"qualifying_ingestion_{suffix}.csv"),
    }, indent=2), flush=True)
    return data, log


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", type=int, nargs="+", default=[2022, 2023, 2024, 2025])
    parser.add_argument("--refresh", action="store_true", help="Rebuild per-weekend files")
    parser.add_argument("--max-events-per-year", type=int, default=None, help="Quick smoke check; not a valid benchmark")
    args = parser.parse_args()
    build_dataset(args.years, refresh=args.refresh, max_events_per_year=args.max_events_per_year)


if __name__ == "__main__":
    main()
