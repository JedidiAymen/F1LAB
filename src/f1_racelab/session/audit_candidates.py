"""Audit public OpenF1 resources before adding a historical replay session.

An optional endpoint can be unavailable for an older session. Only HTTP 404
is classified as absent; other provider errors still fail the audit.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import httpx

from f1_racelab.data.openf1_qualifying import OpenF1Client

OUTPUT = Path(__file__).resolve().parents[3] / "data/processed/replay_candidate_audit.json"
TABLES = ("drivers", "position", "laps", "pit", "stints", "intervals",
          "race_control", "weather", "session_result")


@dataclass(frozen=True)
class Candidate:
    year: int
    country: str


def summarize(candidate: Candidate, session: dict, tables: dict[str, list[dict] | None],
              hashes: dict[str, str]) -> dict:
    """Return counts and provenance without treating missing tables as zero rows."""
    control = tables["race_control"] or []
    weather = tables["weather"] or []
    stints = tables["stints"] or []
    key = int(session["session_key"])
    important = [
        {"date": row.get("date"), "category": row.get("category"),
         "flag": row.get("flag"), "message": row.get("message")}
        for row in control
        if row.get("category") == "SafetyCar"
        or (row.get("category") == "Flag" and row.get("flag") == "RED")
    ]
    return {
        "year": candidate.year, "country": candidate.country,
        "session_key": key, "meeting_key": int(session["meeting_key"]),
        "clock_origin_utc": session["date_start"],
        "source": "OpenF1 v1",
        "resource_rows": {name: None if rows is None else len(rows)
                          for name, rows in tables.items()},
        "driver_coverage": {
            name: None if tables[name] is None else len({
                int(row["driver_number"]) for row in tables[name] or []})
            for name in ("drivers", "position", "laps")
        },
        "flag_counts": {f"{category or 'None'}|{flag or 'None'}": count
                       for (category, flag), count in Counter(
                           (row.get("category"), row.get("flag")) for row in control).items()},
        "rainfall_records": {str(value): count for value, count in Counter(
            row.get("rainfall") for row in weather).items()},
        "stint_compounds": dict(Counter(row.get("compound") for row in stints)),
        "critical_control": important,
        "source_sha256": {name: hashes[f"{name}?session_key={key}"]
                          for name, rows in tables.items() if rows is not None},
    }


def audit_candidate(client: OpenF1Client, candidate: Candidate) -> dict:
    """Fetch a named race and all expected replay resources with cache/pacing."""
    sessions = client.get("sessions", year=candidate.year, country_name=candidate.country)
    races = [row for row in sessions if row.get("session_name") == "Race"]
    if len(races) != 1:
        raise ValueError(f"Expected one race for {candidate}, got {len(races)}")
    session = races[0]
    key = int(session["session_key"])
    tables: dict[str, list[dict] | None] = {}
    for name in TABLES:
        try:
            rows = client.get(name, session_key=key)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
            tables[name] = None
            continue
        if any(row.get("session_key") != key for row in rows):
            raise ValueError(f"{name}: foreign session row")
        tables[name] = rows
    return summarize(candidate, session, tables, client.hashes)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    with OpenF1Client() as client:
        audits = [audit_candidate(client, item)
                  for item in (Candidate(2023, "Monaco"), Candidate(2024, "Brazil"))]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(audits, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "sessions": [
        {"year": row["year"], "country": row["country"],
         "session_key": row["session_key"], "resource_rows": row["resource_rows"],
         "rainfall_records": row["rainfall_records"],
         "critical_messages": len(row["critical_control"])}
        for row in audits]}, indent=2))


if __name__ == "__main__":
    main()
