"""Refresh a suspect lap response in a separate cache and preserve old bytes."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from f1_racelab.data.openf1_qualifying import RAW_ROOT, OpenF1Client
from f1_racelab.ml.driver_dna.future_data import (
    OUT,
    RESPONSE_CAP,
    cache_path,
    write_json,
)


def audit(cache: Path, out: Path, session: int) -> Path:
    fresh_root = out / f"fresh_session_{session}"
    with OpenF1Client(fresh_root, max_response_bytes=RESPONSE_CAP) as client:
        rows = client.get("laps", session_key=session)
    _, fresh = cache_path(fresh_root, "laps", {"session_key": session})
    _, original = cache_path(cache, "laps", {"session_key": session})
    overlay = out / "audited_cache"
    for folder in cache.iterdir():
        if folder.is_dir():
            target = overlay / folder.name
            target.mkdir(parents=True, exist_ok=True)
            for source in folder.iterdir():
                destination = target / source.name
                if not destination.exists():
                    destination.symlink_to(source.resolve())
    _, destination = cache_path(overlay, "laps", {"session_key": session})
    if destination.is_symlink():
        destination.unlink()
    elif destination.exists():
        raise ValueError("Overlay target is not a generated symlink; preserve it")
    destination.symlink_to(fresh.resolve())
    write_json(out / f"session_{session}_audit.json", {
        "session_key": session, "fresh_rows": len(rows), "original_path": str(original),
        "original_sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
        "fresh_path": str(fresh), "fresh_sha256": hashlib.sha256(fresh.read_bytes()).hexdigest(),
        "overlay": str(overlay), "original_preserved": True})
    return overlay


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", type=int, default=11234)
    parser.add_argument("--cache", type=Path, default=RAW_ROOT)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    print(audit(args.cache, args.out, args.session))
