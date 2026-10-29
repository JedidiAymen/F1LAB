"""Combine cached FastF1 2022 and OpenF1 2023–2025 qualifying rows.

The common-feature experiment uses only best practice laps/ranks/gaps shared
by both providers. Source labels and cutoff timestamps remain on every row.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import fastf1
import pandas as pd

from f1_racelab.data import fastf1_source as _fastf1_cache  # noqa: F401
from f1_racelab.data.qualifying_dataset import OUTPUT_ROOT, _validate


def combine(output_root: Path = OUTPUT_ROOT,
            openf1_years: tuple[int, ...] = (2023, 2024, 2025)) -> pd.DataFrame:
    """Merge cached FastF1 2022 with OpenF1 ``openf1_years`` (default unchanged)."""
    output_root = Path(output_root)
    suffix = "_".join(map(str, sorted(set(openf1_years))))
    fastf1_files = sorted((output_root / "qualifying_weekends").glob("2022_*.parquet"))
    if not fastf1_files:
        raise FileNotFoundError("No cached FastF1 2022 weekends")
    # This metadata was cached during 2022 ingestion. Freeze it here so the
    # local merge neither depends on a live schedule server nor emits network
    # errors when the F1 archive is unavailable.
    fastf1.Cache.offline_mode(True)
    try:
        schedule = fastf1.get_event_schedule(2022, include_testing=False)
    finally:
        fastf1.Cache.offline_mode(False)
    schedule = schedule.set_index("RoundNumber")
    frames: list[pd.DataFrame] = []
    for path in fastf1_files:
        frame = pd.read_parquet(path)
        _validate(frame, str(path))
        round_no = int(frame["round"].iloc[0])
        if not frame["round"].eq(round_no).all():
            raise ValueError(f"Mixed rounds in {path}")
        event = schedule.loc[round_no]
        if event["EventFormat"] != "conventional":
            raise ValueError(f"Cached 2022 R{round_no} is not conventional")
        cutoff = pd.Timestamp(event["Session4DateUtc"]).tz_localize("UTC").isoformat()
        frame["session"] = "Qualifying"
        frame["provider"] = "FastF1"
        frame["provider_version"] = fastf1.__version__
        frame["available_at"] = cutoff
        frame["source_quality"] = "fastf1_clean_lap_best"
        frame["source_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        frame["source_meeting_key"] = pd.Series(pd.NA, index=frame.index, dtype="Int64")
        frame["source_session_key"] = pd.Series(pd.NA, index=frame.index, dtype="Int64")
        if "team" not in frame:
            frame["team"] = pd.NA
        frames.append(frame)
    openf1_file = output_root / f"qualifying_openf1_{suffix}.parquet"
    if not openf1_file.exists():
        raise FileNotFoundError(f"Run OpenF1 ingestion first: {openf1_file}")
    openf1 = pd.read_parquet(openf1_file)
    if not set(openf1.year.unique()).issubset(set(openf1_years)):
        raise ValueError("Unexpected years in OpenF1 dataset")
    if openf1.provider.ne("OpenF1").any():
        raise ValueError("Unexpected provider in OpenF1 dataset")
    combined = pd.concat([*frames, openf1], ignore_index=True)
    if combined.duplicated(["year", "round", "driver"]).any():
        raise ValueError("Duplicate driver-weekend after provider merge")
    combined = combined.sort_values(["year", "round", "final_position"], kind="stable")
    output_file = output_root / f"qualifying_mixed_2022_{suffix}.parquet"
    combined.to_parquet(output_file, index=False)
    coverage = combined.groupby(["year", "provider"], as_index=False).agg(
        weekends=("round", "nunique"), rows=("driver", "count"),
        fp3_available=("fp3_best_seconds", "count"), q1_available=("q1_seconds", "count"),
        team_available=("team", "count"),
    )
    manifest = {"generated_at_utc": datetime.now(UTC).isoformat(),
                "dataset": str(output_file),
                "dataset_sha256": hashlib.sha256(output_file.read_bytes()).hexdigest(),
                "source": "FastF1 2022 processed event files + OpenF1 v1 2023–2025",
                "coverage": coverage.to_dict(orient="records")}
    (output_root / ("qualifying_mixed_manifest.json" if suffix == "2023_2024_2025"
                    else f"qualifying_mixed_manifest_{suffix}.json")).write_text(json.dumps(manifest, indent=2))
    print(coverage.to_string(index=False), flush=True)
    return combined


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--openf1-years", type=int, nargs="+", default=[2023, 2024, 2025])
    args = parser.parse_args()
    combine(args.out, tuple(args.openf1_years))


if __name__ == "__main__":
    main()
