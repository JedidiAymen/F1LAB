"""Fetch the OpenF1 race-session resources needed for race-pace modelling.

Per Race session (Sprint excluded): laps, stints, pit, weather, race_control,
intervals. Responses are cached through ``OpenF1Client`` (exact JSON, 2.1 s
pacing, retries, corrupt-cache quarantine). Source: https://openf1.org (data
terms in docs/DATA_CONTRACTS.md; raw responses stay local and git-ignored).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx

from f1_racelab.data.openf1_qualifying import RAW_ROOT, OpenF1Client

RESOURCES = ("laps", "stints", "pit", "weather", "race_control", "intervals")
MANIFEST = Path(__file__).resolve().parents[4] / "data/processed/race_pace/fetch_manifest.json"


def race_sessions(client: OpenF1Client, years: list[int]) -> list[dict]:
    out = []
    for year in years:
        meetings = {m["meeting_key"]: m for m in client.get("meetings", year=year)}
        for session in client.get("sessions", year=year):
            if session.get("session_name") == "Race" and not session.get("is_cancelled"):
                meeting = meetings.get(session["meeting_key"], {})
                out.append({"year": year, "session_key": session["session_key"],
                            "meeting_key": session["meeting_key"],
                            "meeting_name": meeting.get("meeting_name"),
                            "circuit": session.get("circuit_short_name"),
                            "date_start": session["date_start"], "date_end": session.get("date_end")})
    return sorted(out, key=lambda s: s["date_start"])


def fetch(years: list[int], cache_root: Path = RAW_ROOT, offline: bool = False) -> list[dict]:
    report = []
    with OpenF1Client(cache_root, offline=offline) as client:
        for item in race_sessions(client, years):
            status, detail = "OK", ""
            hashes: dict[str, str] = {}
            missing: list[str] = []
            for resource in RESOURCES:
                try:
                    client.get(resource, session_key=item["session_key"])
                    hashes[resource] = client.hashes[f"{resource}?session_key={item['session_key']}"]
                except httpx.HTTPStatusError as exc:
                    # OpenF1 answers 404 for an empty result set; only laps are mandatory.
                    if exc.response.status_code == 404 and resource != "laps":
                        missing.append(resource)
                        continue
                    status, detail = "INCOMPLETE", f"{resource}: {exc.response.status_code}"
                    break
                except (httpx.HTTPError, OSError, ValueError) as exc:
                    status, detail = "INCOMPLETE", f"{resource}: {type(exc).__name__}: {str(exc)[:120]}"
                    break
            item = {**item, "missing_resources": missing}
            report.append({**item, "status": status, "detail": detail, "sha256": hashes})
            print(f"[{status}] {item['year']} {item['meeting_name']} {detail}", flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", type=int, nargs="+", default=[2023, 2024, 2025, 2026])
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    report = fetch(args.years, offline=args.offline)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(report, indent=2))
    print(f"{sum(r['status'] == 'OK' for r in report)}/{len(report)} complete -> {MANIFEST}")


if __name__ == "__main__":
    main()
