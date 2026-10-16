"""Fetch cached OpenF1 car data and build a reproducible lap comparison."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt

from f1_racelab.data.openf1_qualifying import RAW_ROOT, OpenF1Client
from f1_racelab.session.catalog import SESSIONS
from f1_racelab.telemetry.artifacts import COMPARISONS, ComparisonSpec
from f1_racelab.telemetry.contracts import LapComparison
from f1_racelab.telemetry.distance_alignment import build_lap_telemetry, compare_laps


def _source_lap(rows: list[dict], driver_number: int, lap_number: int) -> dict:
    matches = [row for row in rows
               if int(row.get("driver_number", -1)) == driver_number
               and int(row.get("lap_number", -1)) == lap_number]
    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one lap row for driver {driver_number} lap {lap_number}; got {len(matches)}"
        )
    return matches[0]


def plot_comparison(comparison: LapComparison, path: Path) -> None:
    """Render speed and cumulative time delta against shared distance."""
    x = [sample.distance_m for sample in comparison.samples]
    speed_a = [sample.speed_a_kmh for sample in comparison.samples]
    speed_b = [sample.speed_b_kmh for sample in comparison.samples]
    delta = [sample.delta_time_b_minus_a_seconds for sample in comparison.samples]
    figure, (speed_axis, delta_axis) = plt.subplots(
        2, 1, figsize=(13, 8), sharex=True, constrained_layout=True,
    )
    figure.set_facecolor("#10161a")
    for axis in (speed_axis, delta_axis):
        axis.set_facecolor("#182126")
        axis.tick_params(colors="#aeb9bf")
        axis.xaxis.label.set_color("#d4dde1")
        axis.yaxis.label.set_color("#d4dde1")
        for spine in axis.spines.values():
            spine.set_color("#52616a")
        axis.grid(color="#52616a", alpha=0.28)
    speed_axis.plot(x, speed_a, label=f"#{comparison.lap_a.driver_number} L{comparison.lap_a.lap_number}",
                    color="#e85b4f", linewidth=1.1)
    speed_axis.plot(x, speed_b, label=f"#{comparison.lap_b.driver_number} L{comparison.lap_b.lap_number}",
                    color="#55a6d9", linewidth=1.1)
    speed_axis.set_ylabel("Speed (km/h)")
    speed_axis.legend(loc="upper right", facecolor="#182126", edgecolor="#52616a",
                      labelcolor="#e7edef")
    delta_axis.plot(x, delta, color="#d8b65c", linewidth=1.1)
    delta_axis.axhline(0, color="#8b949a", linewidth=0.8)
    delta_axis.set_ylabel("B − A time (s)")
    delta_axis.set_xlabel("Estimated distance from lap start (m)")
    figure.suptitle(
        f"OpenF1 historical lap comparison · estimated speed-integrated distance · "
        f"{comparison.sample_spacing_m:g} m grid", color="#e7edef",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=150, facecolor="#10161a")
    plt.close(figure)


def build_comparison(
    *,
    session_slug: str,
    driver_a: int,
    lap_a_number: int,
    driver_b: int,
    lap_b_number: int,
    spacing_m: float = 5.0,
    cache_root: Path = RAW_ROOT,
    offline: bool = False,
) -> LapComparison:
    if session_slug not in SESSIONS:
        raise ValueError(f"Unsupported replay session: {session_slug}")
    spec = SESSIONS[session_slug]
    with OpenF1Client(cache_root, offline=offline) as client:
        lap_rows = client.get("laps", session_key=spec.session_key)
        source_a = _source_lap(lap_rows, driver_a, lap_a_number)
        source_b = _source_lap(lap_rows, driver_b, lap_b_number)
        # Pit-in checks use an already cached optional endpoint only. Monaco's
        # historical pit resource is unavailable; do not invent a clean-lap label.
        pit_hashes: dict[str, str] = {}
        with OpenF1Client(cache_root, offline=True) as optional_client:
            try:
                pit_rows = optional_client.get("pit", session_key=spec.session_key)
            except FileNotFoundError:
                pit_rows = None
            if pit_rows is not None:
                if any(row.get("session_key") != spec.session_key
                       or row.get("meeting_key") != spec.meeting_key for row in pit_rows):
                    raise ValueError("Pit rows belong to a different session or meeting")
                for driver_number, lap_number in ((driver_a, lap_a_number), (driver_b, lap_b_number)):
                    if any(row.get("driver_number") == driver_number
                           and row.get("lap_number") == lap_number for row in pit_rows):
                        raise ValueError(f"Pit-in lap excluded: driver {driver_number} lap {lap_number}")
                pit_hashes = dict(optional_client.hashes)
        telemetry_a = client.get("car_data", session_key=spec.session_key, driver_number=driver_a)
        telemetry_b = client.get("car_data", session_key=spec.session_key, driver_number=driver_b)
        lap_a = build_lap_telemetry(
            telemetry_a, source_a, session_key=spec.session_key,
            meeting_key=spec.meeting_key, driver_number=driver_a,
        )
        lap_b = build_lap_telemetry(
            telemetry_b, source_b, session_key=spec.session_key,
            meeting_key=spec.meeting_key, driver_number=driver_b,
        )
        source_hashes = {
            f"laps?session_key={spec.session_key}": client.hashes[f"laps?session_key={spec.session_key}"],
            f"car_data?driver_number={driver_a}&session_key={spec.session_key}":
                client.hashes[f"car_data?driver_number={driver_a}&session_key={spec.session_key}"],
            f"car_data?driver_number={driver_b}&session_key={spec.session_key}":
                client.hashes[f"car_data?driver_number={driver_b}&session_key={spec.session_key}"],
        }
    source_hashes.update(pit_hashes)
    return compare_laps(lap_a, lap_b, source_hashes=source_hashes, spacing_m=spacing_m)


def save_comparison(comparison: LapComparison, output: Path) -> dict:
    """Write validated JSON, source-quality QA and a speed/delta chart."""
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(comparison.model_dump(mode="json"), indent=2) + "\n")
    temporary.replace(output)
    chart_path = output.with_suffix(".png")
    plot_comparison(comparison, chart_path)
    pit_resource = f"pit?session_key={comparison.session_key}"
    report = {
        "output": str(output), "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "chart": str(chart_path), "session_key": comparison.session_key,
        "lap_a": comparison.lap_a.model_dump(mode="json", exclude={"points"}),
        "lap_b": comparison.lap_b.model_dump(mode="json", exclude={"points"}),
        "common_distance_end_m": comparison.common_distance_end_m,
        "grid_spacing_m": comparison.sample_spacing_m, "grid_points": len(comparison.samples),
        "pit_entry_audit": ("cached provider pit rows checked" if pit_resource in comparison.source_hashes
                            else "pit source unavailable locally; pit-in status unverified"),
        "channel_nonnull_grid_points": {
            field: sum(getattr(point, field) is not None for point in comparison.samples)
            for field in type(comparison.samples[0]).model_fields
            if field not in {"quality", "distance_m"}},
        "source_hashes": comparison.source_hashes,
        "limits": ["Lap start and speed-integrated distance are estimated",
                   "Equal distance does not certify equal physical track point",
                   "Tyre, fuel, weather and traffic differences are uncontrolled",
                   "Brake values and DRS codes retain raw provider semantics"],
    }
    output.with_suffix(".qa.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--session", choices=sorted(SESSIONS), default="monza-2025")
    group.add_argument("--all", action="store_true", help="Build all catalogued reference comparisons")
    parser.add_argument("--driver-a", type=int)
    parser.add_argument("--lap-a", type=int)
    parser.add_argument("--driver-b", type=int)
    parser.add_argument("--lap-b", type=int)
    parser.add_argument("--spacing-m", type=float, default=5.0)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--offline", action="store_true", help="Require cached source responses")
    args = parser.parse_args()
    custom = (args.driver_a, args.lap_a, args.driver_b, args.lap_b)
    if any(value is not None for value in custom) and not all(value is not None for value in custom):
        parser.error("Custom comparisons require --driver-a, --lap-a, --driver-b and --lap-b")
    if args.all and (args.out or any(value is not None for value in custom)):
        parser.error("--all cannot be combined with --out or custom driver/lap arguments")
    specs = list(COMPARISONS.values()) if args.all else [
        ComparisonSpec(args.session, *custom) if all(value is not None for value in custom)
        else COMPARISONS[args.session]]
    reports = []
    for spec in specs:
        comparison = build_comparison(
            session_slug=spec.session_slug, driver_a=spec.driver_a, lap_a_number=spec.lap_a,
            driver_b=spec.driver_b, lap_b_number=spec.lap_b, spacing_m=args.spacing_m,
            offline=args.offline,
        )
        reports.append(save_comparison(comparison, args.out or spec.path))
    print(json.dumps({"comparisons": reports}, indent=2))


if __name__ == "__main__":
    main()
