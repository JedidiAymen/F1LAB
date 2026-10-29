"""Run every registered transformation on the engine it declares and write a manifest (engine, rows, seconds, SHA-256).

Command: ``uv run python -m f1_racelab.engines.pipeline [--input PARQUET | --sample] [--engine-override ENGINE]``.
The feed check runs first; an error-level finding stops the run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import pandas as pd

from f1_racelab.engines import feed_check, run, transforms

OUT = Path(__file__).resolve().parents[3] / "data/processed/engines"


def execute(df: pd.DataFrame, *, override: str | None = None, out_dir: Path = OUT, check_feed: bool = True) -> dict:
    if check_feed:
        findings = feed_check.check(df)
        if any(f["severity"] == "error" for f in findings):
            raise ValueError(f"feed check failed: {[f for f in findings if f['severity'] == 'error']}")
    out_dir.mkdir(parents=True, exist_ok=True)
    steps = []
    for name, declared in transforms.REGISTRY.items():
        engine = override or declared
        started = time.perf_counter()
        result = transforms.run(name, df, engine)
        seconds = time.perf_counter() - started
        path = out_dir / f"{name}.parquet"
        result.to_parquet(path, index=False)
        steps.append({"step": name, "declared_engine": declared, "engine_used": engine, "rows_out": len(result),
                      "seconds": round(seconds, 4), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    manifest = {"input_rows": len(df), "steps": steps}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input")
    parser.add_argument("--sample", action="store_true")
    parser.add_argument("--engine-override", choices=transforms.ENGINES)
    args = parser.parse_args()
    df = run.sample_frame() if args.sample else pd.read_parquet(args.input or run.DEFAULT_INPUT)
    print(json.dumps(execute(df, override=args.engine_override, check_feed=not args.sample), indent=1))


if __name__ == "__main__":
    main()
