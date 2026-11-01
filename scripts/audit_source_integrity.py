"""Archive and screen an existing OpenF1 laps response without changing it."""
import argparse
import json
from pathlib import Path

from f1_racelab.data.source_integrity import archive, audit_laps


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("session_key", type=int)
    parser.add_argument("store", type=Path)
    parser.add_argument("--retrieved-at-utc", default=None, help="Known timezone-aware retrieval timestamp; omit if unknown")
    args = parser.parse_args()
    payload = args.source.read_bytes()
    report = audit_laps(payload, args.session_key)
    record = archive(args.store, payload, provider="OpenF1", endpoint="laps",
                     parameters={"session_key": args.session_key}, retrieved_at_utc=args.retrieved_at_utc,
                     report=report, source_location=str(args.source))
    print(json.dumps({"record": record["record"], "snapshot": record["snapshot"], "audit": report}, indent=2))


if __name__ == "__main__":
    main()
