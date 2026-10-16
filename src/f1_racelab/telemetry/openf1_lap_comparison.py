"""Fetch cached OpenF1 car data and build a reproducible lap comparison."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt

from f1_racelab.data.openf1_qualifying import RAW_ROOT, OpenF1Client
from f1_racelab.session.catalog import SESSIONS
from f1_racelab.telemetry.distance_alignment import build_lap_telemetry, compare_laps

ROOT = Path(__file__).resolve().parents[3]
OUTPUT_ROOT = ROOT / "data/processed/telemetry_comparisons"


def _source_lap(rows: list[dict], driver_number: int, lap_number: int) -> dict:
    matches = [row for row in rows
               if int(row.get("driver_number", -1)) == driver_number
               and int(row.get("lap_number", -1)) == lap_number]
    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one lap row for driver {driver_number} lap {lap_number}; got {len(matches)}"
        )
    return matches[0]


def plot_comparison(comparison, path: Path) -> None:
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
):
    if session_slug not in SESSIONS:
        raise ValueError(f"Unsupported replay session: {session_slug}")
    spec = SESSIONS[session_slug]
    with OpenF1Client(cache_root) as client:
        lap_rows = client.get("laps", session_key=spec.session_key)
        source_a = _source_lap(lap_rows, driver_a, lap_a_number)
        source_b = _source_lap(lap_rows, driver_b, lap_b_number)
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
    return compare_laps(lap_a, lap_b, source_hashes=source_hashes, spacing_m=spacing_m)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", choices=sorted(SESSIONS), default="monza-2025")
    parser.add_argument("--driver-a", type=int, default=1)
    parser.add_argument("--lap-a", type=int, default=50)
    parser.add_argument("--driver-b", type=int, default=4)
    parser.add_argument("--lap-b", type=int, default=50)
    parser.add_argument("--spacing-m", type=float, default=5.0)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    comparison = build_comparison(
        session_slug=args.session, driver_a=args.driver_a, lap_a_number=args.lap_a,
        driver_b=args.driver_b, lap_b_number=args.lap_b, spacing_m=args.spacing_m,
    )
    output = args.out or OUTPUT_ROOT / (
        f"{args.session}_driver_{args.driver_a}_lap_{args.lap_a}_"
        f"vs_{args.driver_b}_lap_{args.lap_b}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(comparison.model_dump(mode="json"), indent=2) + "\n")
    temporary.replace(output)
    chart_path = output.with_suffix(".png")
    plot_comparison(comparison, chart_path)
    print(json.dumps({
        "output": str(output),
        "chart": str(chart_path),
        "session_key": comparison.session_key,
        "lap_a": [comparison.lap_a.driver_number, comparison.lap_a.lap_number],
        "lap_b": [comparison.lap_b.driver_number, comparison.lap_b.lap_number],
        "integrated_distance_m": [
            round(comparison.lap_a.integrated_distance_m, 2),
            round(comparison.lap_b.integrated_distance_m, 2),
        ],
        "common_distance_end_m": round(comparison.common_distance_end_m, 2),
        "grid_spacing_m": comparison.sample_spacing_m,
        "grid_points": len(comparison.samples),
        "source_hashes": comparison.source_hashes,
    }, indent=2))


if __name__ == "__main__":
    main()
