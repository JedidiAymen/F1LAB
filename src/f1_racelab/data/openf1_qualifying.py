"""Build a source-labelled qualifying dataset from public OpenF1 history.

OpenF1 session results give best practice laps and Q1/Q2/Q3 classifications,
but not the richer FastF1 representative-lap features. This adapter keeps
those fields missing rather than fabricating equivalent measurements.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pandas as pd

from f1_racelab.data.qualifying_dataset import OUTPUT_ROOT, _validate

ROOT = Path(__file__).resolve().parents[3]
RAW_ROOT = ROOT / "data/raw/openf1"
BASE_URL = "https://api.openf1.org/v1"
MIN_REQUEST_INTERVAL_SECONDS = 2.1  # below the public 30 requests/minute ceiling
RETRIABLE_STATUS = {429, 500, 502, 503, 504}
PRACTICE_NAMES = ("Practice 1", "Practice 2", "Practice 3")


class OpenF1Client:
    """Cache exact JSON responses and pace uncached public requests."""

    def __init__(self, cache_root: Path = RAW_ROOT, *, interval: float = MIN_REQUEST_INTERVAL_SECONDS):
        self.cache_root = Path(cache_root)
        self.interval = interval
        self._last_request = 0.0
        self._http = httpx.Client(timeout=30.0, headers={"User-Agent": "F1LAB/0.1 research"})
        self.hashes: dict[str, str] = {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self._http.close()

    def get(self, endpoint: str, **params: int | str) -> list[dict]:
        query = "&".join(f"{key}={value}" for key, value in sorted(params.items()))
        resource = f"{endpoint}?{query}"
        key = hashlib.sha256(resource.encode()).hexdigest()[:20]
        destination = self.cache_root / endpoint / f"{key}.json"
        if destination.exists():
            payload = destination.read_bytes()
        else:
            for attempt in range(4):
                delay = self.interval - (time.monotonic() - self._last_request)
                if delay > 0:
                    time.sleep(delay)
                self._last_request = time.monotonic()
                response = self._http.get(f"{BASE_URL}/{endpoint}", params=params)
                if response.status_code in RETRIABLE_STATUS and attempt < 3:
                    retry_after = response.headers.get("Retry-After")
                    time.sleep(max(float(retry_after) if retry_after else 0.0, 2 ** attempt))
                    continue
                response.raise_for_status()
                payload = response.content
                break
            self.cache_root.joinpath(endpoint).mkdir(parents=True, exist_ok=True)
            temporary = destination.with_suffix(".tmp")
            temporary.write_bytes(payload)
            temporary.replace(destination)
        rows = json.loads(payload)
        if not isinstance(rows, list):
            raise TypeError(f"OpenF1 {resource} returned a non-list payload")
        self.hashes[resource] = hashlib.sha256(payload).hexdigest()
        return rows


def conventional_weekends(meetings: list[dict], sessions: list[dict]) -> list[dict]:
    """Number completed race meetings chronologically; keep full FP1/2/3 format."""
    by_meeting: dict[int, dict[str, dict]] = {}
    for session in sessions:
        if session.get("is_cancelled"):
            continue
        by_meeting.setdefault(int(session["meeting_key"]), {})[session["session_name"]] = session
    completed = [m for m in meetings if not m.get("is_cancelled")
                 and "Race" in by_meeting.get(int(m["meeting_key"]), {})]
    completed.sort(key=lambda m: m["date_start"])
    out = []
    for round_no, meeting in enumerate(completed, start=1):
        current = by_meeting[int(meeting["meeting_key"])]
        if all(name in current for name in (*PRACTICE_NAMES, "Qualifying")) and not any(
            name.startswith("Sprint") for name in current
        ):
            out.append({"year": int(meeting["year"]), "round": round_no,
                        "event": meeting["meeting_name"], "meeting_key": int(meeting["meeting_key"]),
                        "sessions": current})
    return out


def _practice_rows(results: list[dict], prefix: str) -> pd.DataFrame:
    rows = []
    for result in results:
        seconds = pd.to_numeric(result.get("duration"), errors="coerce")
        if pd.notna(seconds) and seconds > 0:
            rows.append({"driver_number": int(result["driver_number"]),
                         f"{prefix}_best_seconds": float(seconds),
                         f"{prefix}_rank": result.get("position")})
    frame = pd.DataFrame(rows, columns=["driver_number", f"{prefix}_best_seconds", f"{prefix}_rank"])
    if not frame.empty:
        reference = frame[f"{prefix}_best_seconds"].min()
        frame[f"{prefix}_gap_pct"] = (frame[f"{prefix}_best_seconds"] / reference - 1) * 100
    else:
        frame[f"{prefix}_gap_pct"] = pd.Series(dtype=float)
    return frame


def normalize_weekend(item: dict, drivers: list[dict], results: dict[str, list[dict]]) -> pd.DataFrame:
    """Map OpenF1 session results to the shared driver-weekend schema."""
    names = {int(d["driver_number"]): d for d in drivers}
    q = []
    for result in results["Qualifying"]:
        number = int(result["driver_number"])
        identity = names.get(number)
        if identity is None:
            continue
        phases = result.get("duration")
        if not isinstance(phases, list):
            phases = []
        phase_seconds = [pd.to_numeric(phases[i], errors="coerce") if i < len(phases) else float("nan")
                         for i in range(3)]
        q.append({"driver_number": number, "driver": identity["name_acronym"],
                  "team": identity.get("team_name"), "final_position": result.get("position"),
                  "q1_seconds": phase_seconds[0], "q2_seconds": phase_seconds[1],
                  "q3_seconds": phase_seconds[2]})
    frame = pd.DataFrame(q)
    if frame.empty:
        raise ValueError("No qualifying result rows with driver identities")
    for index, name in enumerate(PRACTICE_NAMES, start=1):
        frame = frame.merge(_practice_rows(results[name], f"fp{index}"),
                            on="driver_number", how="left", validate="one_to_one")
    reference = frame["q1_seconds"].min()
    frame["q1_gap_pct"] = (frame["q1_seconds"] / reference - 1) * 100
    frame["fp1_to_fp3_improvement_pct"] = frame["fp1_gap_pct"] - frame["fp3_gap_pct"]
    frame["fp2_to_fp3_improvement_pct"] = frame["fp2_gap_pct"] - frame["fp3_gap_pct"]
    frame["year"] = item["year"]
    frame["round"] = item["round"]
    frame["event"] = item["event"]
    frame["session"] = "Qualifying"
    frame["provider"] = "OpenF1"
    frame["provider_version"] = "v1"
    frame["available_at"] = item["sessions"]["Qualifying"]["date_start"]
    frame["source_meeting_key"] = item["meeting_key"]
    frame["source_session_key"] = item["sessions"]["Qualifying"]["session_key"]
    frame["source_quality"] = "session_result_best_lap"
    if frame.duplicated("driver").any():
        raise ValueError("Duplicate driver acronym in qualifying result")
    _validate(frame, f"OpenF1 {item['year']} R{item['round']}")
    return frame.sort_values("final_position", kind="stable").reset_index(drop=True)


def build_dataset(years: list[int], *, output_root: Path = OUTPUT_ROOT,
                  cache_root: Path = RAW_ROOT) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Resume per-weekend ingestion and write coverage even when a source fails."""
    output_root = Path(output_root)
    weekend_root = output_root / "qualifying_openf1_weekends"
    weekend_root.mkdir(parents=True, exist_ok=True)
    frames: list[pd.DataFrame] = []
    report: list[dict] = []
    with OpenF1Client(cache_root) as client:
        for year in sorted(set(years)):
            try:
                weekends = conventional_weekends(client.get("meetings", year=year),
                                                 client.get("sessions", year=year))
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                report.append({"year": year, "round": None, "event": "schedule",
                               "status": "ERROR", "rows": 0, "detail": f"{type(exc).__name__}: {exc}"})
                continue
            print(f"{year}: {len(weekends)} conventional weekends", flush=True)
            for item in weekends:
                destination = weekend_root / f"{year}_{item['round']:02d}_{item['meeting_key']}.parquet"
                status = "CACHED"
                try:
                    if destination.exists():
                        frame = pd.read_parquet(destination)
                    else:
                        session_keys = {name: item["sessions"][name]["session_key"]
                                        for name in (*PRACTICE_NAMES, "Qualifying")}
                        results = {name: client.get("session_result", session_key=key)
                                   for name, key in session_keys.items()}
                        drivers = client.get("drivers", session_key=session_keys["Qualifying"])
                        frame = normalize_weekend(item, drivers, results)
                        resources = [f"session_result?session_key={key}" for key in session_keys.values()]
                        resources.append(f"drivers?session_key={session_keys['Qualifying']}")
                        frame["source_sha256"] = hashlib.sha256(
                            "".join(client.hashes[key] for key in resources).encode()).hexdigest()
                        frame.to_parquet(destination, index=False)
                        status = "BUILT"
                    _validate(frame, str(destination))
                    frames.append(frame)
                    report.append({"year": year, "round": item["round"], "event": item["event"],
                                   "status": status, "rows": len(frame), "detail": ""})
                    print(f"[{status}] {year} R{item['round']:02d} {item['event']}: {len(frame)}", flush=True)
                except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                    report.append({"year": year, "round": item["round"], "event": item["event"],
                                   "status": "ERROR", "rows": 0,
                                   "detail": f"{type(exc).__name__}: {exc}"[:300]})
                    print(f"[ERROR] {year} R{item['round']:02d}: {exc}", flush=True)
    report_frame = pd.DataFrame(report)
    suffix = "_".join(map(str, sorted(set(years))))
    report_frame.to_csv(output_root / f"qualifying_openf1_ingestion_{suffix}.csv", index=False)
    if not frames:
        raise RuntimeError("No OpenF1 weekends built; inspect the ingestion report")
    combined = pd.concat(frames, ignore_index=True)
    combined.to_parquet(output_root / f"qualifying_openf1_{suffix}.parquet", index=False)
    print(json.dumps({"weekends": len(frames), "rows": len(combined),
                      "errors": int(report_frame.status.eq("ERROR").sum()),
                      "generated_at_utc": datetime.now(UTC).isoformat()}, indent=2), flush=True)
    return combined, report_frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", type=int, nargs="+", default=[2023, 2024, 2025])
    args = parser.parse_args()
    build_dataset(args.years)


if __name__ == "__main__":
    main()
