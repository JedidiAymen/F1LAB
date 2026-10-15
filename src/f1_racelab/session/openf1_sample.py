"""Build a limited real Monza 2025 race-control timeline from OpenF1 history.

This is a contract/reducer smoke sample, not a complete replay pack. It has no
car positions, lap timing, weather or strategy and must not be shown as such.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from f1_racelab.data.openf1_qualifying import OpenF1Client
from f1_racelab.session.contracts import (
    Quality,
    RaceControlPayload,
    SessionEvent,
    SessionId,
)
from f1_racelab.session.reducer import seek_state

SESSION_KEY = 9912
SESSION_START = datetime(2025, 9, 7, 13, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / "data/processed/replay_samples/openf1_2025_monza_race_control.json"


def build_sample(output: Path = OUTPUT) -> dict:
    """Normalize real provider messages after scheduled race start; preserve provenance."""
    with OpenF1Client() as client:
        raw = client.get("race_control", session_key=SESSION_KEY)
        source_sha256 = client.hashes[f"race_control?session_key={SESSION_KEY}"]
    session = SessionId(season=2025, round=16, kind="race", provider_key=f"openf1:{SESSION_KEY}")
    ingested_at = datetime.now(UTC)
    eligible = []
    for original_index, row in enumerate(raw):
        if row.get("session_key") != SESSION_KEY:
            raise ValueError("Race-control row has a different session key")
        source_time = datetime.fromisoformat(row["date"])
        if source_time.tzinfo is None:
            raise ValueError("OpenF1 race-control timestamp is timezone-naive")
        if source_time >= SESSION_START:
            eligible.append((source_time, original_index, row))
    eligible.sort(key=lambda item: (item[0], item[1]))
    events = []
    for sequence, (source_time, original_index, row) in enumerate(eligible):
        payload = RaceControlPayload(
            category=row.get("category") or "Unknown",
            message=row.get("message") or "",
            flag=row.get("flag"),
            scope=row.get("scope"),
        )
        events.append(SessionEvent(
            session=session,
            event_id=f"openf1:{SESSION_KEY}:race_control:{original_index}",
            type="race_control", source="OpenF1 v1",
            source_timestamp=source_time, observed_at=source_time,
            ingested_at=ingested_at,
            session_time_seconds=(source_time - SESSION_START).total_seconds(),
            sequence=sequence, applicable_lap=row.get("lap_number"),
            quality=Quality.MEASURED, payload=payload,
        ))
    if not events:
        raise ValueError("No race-control messages at or after scheduled start")
    final_state = seek_state(session, events, events[-1].session_time_seconds)
    sample = {
        "schema_version": 1,
        "description": "2025 Italian GP race-control messages only; incomplete race replay",
        "source_url": f"https://api.openf1.org/v1/race_control?session_key={SESSION_KEY}",
        "source_sha256": source_sha256,
        "session_start_utc": SESSION_START.isoformat(),
        "generated_at_utc": ingested_at.isoformat(),
        "event_count": len(events),
        "last_event_time_seconds": final_state.session_time_seconds,
        "capabilities": ["race_control_messages"],
        "events": [event.model_dump(mode="json") for event in events],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(sample, indent=2))
    sample["artifact_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    return sample


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = build_sample(args.out)
    print(json.dumps({key: value for key, value in result.items() if key != "events"}, indent=2))


if __name__ == "__main__":
    main()
