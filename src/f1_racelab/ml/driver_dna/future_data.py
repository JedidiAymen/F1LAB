"""As-of 20-second telemetry prefixes for a separate remaining-lap study.

No whole-lap alignment or outcome-based pace filter. Existing Driver DNA
artifacts are untouched. New source responses stay in the ignored shared cache.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from f1_racelab.data.openf1_qualifying import RAW_ROOT, OpenF1Client
from f1_racelab.ml.common.contracts import fingerprint_frame, now_utc
from f1_racelab.ml.driver_dna.dataset import CHANNELS, SCALES, _utc

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "data/processed/driver_dna_future"
WINDOW_S = 20.0
GRID = 64
CONTEXT = ("last_lap_seconds", "recent_three_seconds", "lap_number")
SESSIONS = {
    9094: ("Monaco", 2023, "train"), 9636: ("Brazil", 2024, "train"),
    9912: ("Monza", 2025, "train"), 9839: ("Abu Dhabi", 2025, "validation"),
    11234: ("Australia", 2026, "test"), 11253: ("Japan", 2026, "test"),
}
RESPONSE_CAP = 24 * 1024**2
DOWNLOAD_BUDGET = 600 * 1024**2
FREE_FLOOR = 1024**3


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False))
    temporary.replace(path)


def cache_path(cache: Path, endpoint: str, params: dict) -> tuple[str, Path]:
    resource = endpoint + "?" + "&".join(f"{key}={value}" for key, value in sorted(params.items()))
    return resource, cache / endpoint / f"{hashlib.sha256(resource.encode()).hexdigest()[:20]}.json"


def fetch(cache: Path = RAW_ROOT, out: Path = OUT) -> dict:
    """Paced/resumable existing cache plus hard new-payload and decoded limits."""
    manifest: dict = {"schema_version": 1, "created_at_utc": now_utc(), "status": "partial",
                      "source": "https://api.openf1.org/v1", "license": "CC BY-NC-SA 4.0; non-commercial research",
                      "license_url": "https://github.com/br-g/openf1/blob/main/LICENSE",
                      "sessions": SESSIONS, "response_cap_bytes": RESPONSE_CAP,
                      "new_payload_budget_bytes": DOWNLOAD_BUDGET, "new_bytes": 0, "resources": {}}
    with OpenF1Client(cache, max_response_bytes=RESPONSE_CAP) as client:
        def get(endpoint: str, **params) -> list[dict]:
            resource, path = cache_path(cache, endpoint, params)
            existed = path.is_file()
            if not existed:
                if shutil.disk_usage(cache).free < FREE_FLOOR + RESPONSE_CAP:
                    raise RuntimeError("Free disk floor would be violated; no request made")
                remaining = DOWNLOAD_BUDGET - manifest["new_bytes"]
                if remaining <= 0:
                    raise RuntimeError("New download budget exhausted")
                client.max_response_bytes = min(RESPONSE_CAP, remaining)
            else:
                client.max_response_bytes = RESPONSE_CAP
            rows = client.get(endpoint, **params)
            size = path.stat().st_size
            manifest["new_bytes"] += 0 if existed else size
            manifest["resources"][resource] = {"sha256": client.hashes[resource], "bytes": size,
                                                "cache_path": str(path), "reused": existed, "rows": len(rows)}
            write_json(out / "source_manifest.json", manifest)
            return rows

        for key in SESSIONS:
            get("sessions", session_key=key)
            drivers = get("drivers", session_key=key)
            get("laps", session_key=key)
            numbers = sorted({int(row["driver_number"]) for row in drivers})
            if not 2 <= len(numbers) <= 24:
                raise ValueError("Unexpected driver cohort; inspect metadata before fetching telemetry")
            for number in numbers:
                get("car_data", session_key=key, driver_number=number)
                print(f"Cached {key}/{number}; new payload {manifest['new_bytes'] / 1024**2:.1f} MiB", flush=True)
    manifest["status"] = "complete"
    write_json(out / "source_manifest.json", manifest)
    return manifest


def prefix(samples: pd.DataFrame, start: pd.Timestamp) -> tuple[np.ndarray | None, str]:
    """All sampled information comes from [start,start+20s], including endpoints."""
    times_ns = samples.date.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    start_ns = pd.Timestamp(start).value
    selected = (times_ns >= start_ns) & (times_ns <= start_ns + int(WINDOW_S * 1e9))
    rows = samples[selected]
    if len(rows) < 40:
        return None, "prefix_sample_count"
    t = (times_ns[selected] - start_ns) / 1e9
    if t[0] > 0.6 or WINDOW_S - t[-1] > 0.6 or (np.diff(t) > 1).any() or (np.diff(t) <= 0).any():
        return None, "prefix_coverage_or_gap"
    values = rows[["speed", "throttle", "brake", "n_gear", "rpm"]].to_numpy(float)
    if not np.isfinite(values).all():
        return None, "prefix_nonfinite"
    grid = np.linspace(0, WINDOW_S, GRID)
    past = np.clip(np.searchsorted(t, grid, side="right") - 1, 0, len(t) - 1)
    # Discrete channels hold known values; continuous signals interpolate within
    # the observed prefix and carry the first/last reading across <=0.6s edges.
    x = np.stack([values[past, channel] if channel in (2, 3)
                  else np.interp(grid, t, values[:, channel]) for channel in range(5)])
    return x.astype(np.float32), "kept"


def prior_context(laps: pd.DataFrame, row) -> tuple[float, float] | None:
    """Reject a prior lap unless it actually completed by this decision time."""
    cutoff = row.start + pd.Timedelta(seconds=WINDOW_S)
    prior = laps[(laps.lap_number < row.lap_number) & (laps.end <= cutoff)
                 & np.isfinite(laps.lap_duration) & (laps.lap_duration > 0)].sort_values("end")
    if prior.empty:
        return None
    return float(prior.lap_duration.iloc[-1]), float(prior.lap_duration.tail(3).median())


def build(cache: Path = RAW_ROOT, out: Path = OUT) -> dict:
    """Write a new versioned dataset; never overwrite the original full-lap tensors."""
    if (out / "prefixes.npz").exists():
        raise ValueError("Dataset exists; use a new output directory rather than overwrite evidence")
    tensors, metadata, quality = [], [], {}
    with OpenF1Client(cache, offline=True, max_response_bytes=RESPONSE_CAP) as client:
        for key, (circuit, year, split) in SESSIONS.items():
            laps = pd.DataFrame(client.get("laps", session_key=key))
            drivers = pd.DataFrame(client.get("drivers", session_key=key)).drop_duplicates("driver_number")
            names = drivers.set_index("driver_number").name_acronym.to_dict()
            counts: Counter = Counter()
            counts["source_laps"] = len(laps)
            if laps.duplicated(["driver_number", "lap_number"]).any():
                raise ValueError("Duplicate driver/lap source keys")
            laps["start"] = _utc(laps.date_start)
            laps["lap_duration"] = pd.to_numeric(laps.lap_duration, errors="coerce")
            laps["end"] = laps.start + pd.to_timedelta(laps.lap_duration, unit="s")
            for number, driver_laps in laps.groupby("driver_number"):
                samples = pd.DataFrame(client.get("car_data", session_key=key, driver_number=int(number)))
                samples["date"] = _utc(samples.date)
                samples = samples.sort_values("date")
                for row in driver_laps.sort_values("lap_number").itertuples():
                    if pd.isna(row.start):
                        counts["unknown_lap_start"] += 1
                        continue
                    x, reason = prefix(samples, row.start)
                    if x is None:
                        counts[reason] += 1
                        continue
                    context = prior_context(driver_laps, row)
                    if context is None:
                        counts["no_completed_prior_lap"] += 1
                        continue
                    if not np.isfinite(row.lap_duration) or row.lap_duration <= WINDOW_S:
                        counts["unavailable_or_invalid_target"] += 1
                        continue
                    tensors.append(x)
                    counts["kept"] += 1
                    metadata.append({"session_key": key, "circuit": circuit, "year": year, "split": split,
                                     "driver_number": int(number), "driver": names.get(number, str(number)),
                                     "lap_number": int(row.lap_number), "last_lap_seconds": context[0],
                                     "recent_three_seconds": context[1], "lap_seconds": float(row.lap_duration),
                                     "remaining_seconds": float(row.lap_duration - WINDOW_S),
                                     "cutoff_utc": (row.start + pd.Timedelta(seconds=WINDOW_S)).isoformat()})
            quality[str(key)] = dict(counts)
    x, meta = np.stack(tensors), pd.DataFrame(metadata)
    if set(meta.session_key) != set(SESSIONS):
        write_json(out / "failed_coverage.json", {"quality": quality, "expected_sessions": list(SESSIONS),
                                                  "usable_sessions": sorted(meta.session_key.unique().tolist())})
        raise ValueError("Every registered session needs usable data; inspect failed_coverage.json")
    out.mkdir(parents=True, exist_ok=True)
    with (out / "prefixes.tmp").open("wb") as handle:
        np.savez_compressed(handle, x=x, scales=SCALES[:5])
    (out / "prefixes.tmp").replace(out / "prefixes.npz")
    meta.to_parquet(out / "prefixes_meta.parquet", index=False)
    summary = {"schema_version": 1, "created_at_utc": now_utc(), "evidence": "real OpenF1 telemetry",
               "window_seconds": WINDOW_S, "channels": CHANNELS[:5], "grid": GRID,
               "context_features": CONTEXT, "rows": len(meta), "quality": quality,
               "split_rows": meta.groupby("split").size().to_dict(), "metadata_fingerprint": fingerprint_frame(meta),
               "tensor_sha256": hashlib.sha256(x.tobytes()).hexdigest(), "source_hashes": client.hashes,
               "files": {name: hashlib.sha256((out / name).read_bytes()).hexdigest()
                         for name in ("prefixes.npz", "prefixes_meta.parquet")}}
    write_json(out / "dataset_card.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--cache", type=Path, default=RAW_ROOT)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    result = fetch(args.cache, args.out) if args.fetch else build(args.cache, args.out)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
