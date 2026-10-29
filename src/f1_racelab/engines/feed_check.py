"""Feed-contract check for the race-pace frame (completeness, mappings, plausibility), in the spirit of checking a
client feed against a canonical data format. Findings carry a severity; any ``error`` fails the check.

Command: ``uv run python -m f1_racelab.engines.feed_check`` (exit 1 on errors).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
FRAME = ROOT / "data/processed/race_pace/pace_frame.parquet"
REQUIRED = ["race_id", "year", "driver_number", "lap", "anchor_seconds", "next_lap_seconds", "delta_seconds",
            "compound_next", "tyre_age_next", "eligible_green_next", "regime_next"]
COMPOUNDS = {"SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET", "UNKNOWN"}
REGIMES = {"green", "sc_vsc", "yellow", "red"}
MAX_NULL_SHARE = {"anchor_seconds": 0.0, "next_lap_seconds": 0.0, "compound_next": 0.0, "tyre_age_next": 0.05}


def check(df: pd.DataFrame) -> list[dict]:
    findings: list[dict] = []

    def add(severity: str, rule: str, detail: str) -> None:
        findings.append({"severity": severity, "rule": rule, "detail": detail})

    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        add("error", "required_columns", f"missing {missing}")
        return findings
    for col, limit in MAX_NULL_SHARE.items():
        share = float(df[col].isna().mean())
        if share > limit:
            add("error", "completeness", f"{col} null share {share:.3f} > {limit}")
    unknown = set(df.compound_next.dropna().unique()) - COMPOUNDS
    if unknown:
        add("error", "compound_mapping", f"unmapped compounds {sorted(unknown)}")
    bad_regime = set(df.regime_next.dropna().unique()) - REGIMES
    if bad_regime:
        add("error", "regime_mapping", f"unknown regimes {sorted(bad_regime)}")
    dup = int(df.duplicated(["race_id", "driver_number", "lap"]).sum())
    if dup:
        add("error", "unique_key", f"{dup} duplicate (race, driver, lap) rows")
    implausible = ~df.next_lap_seconds.between(30, 400)
    if (implausible & df.eligible_green_next.astype(bool)).any():
        add("error", "plausibility", "green-eligible next_lap_seconds outside 30-400 s")
    elif implausible.any():  # red-flag stoppages produce multi-minute laps; they are never green-eligible
        add("warning", "plausibility_non_green", f"{int(implausible.sum())} non-green rows outside 30-400 s")
    gap = (df.anchor_seconds + df.delta_seconds - df.next_lap_seconds).abs().max()
    if gap > 1e-6:
        add("error", "target_consistency", f"anchor + delta != next lap (max gap {gap:.3g} s)")
    share_unknown = float((df.compound_next == "UNKNOWN").mean())
    if share_unknown > 0.02:
        add("warning", "compound_unknown", f"{share_unknown:.1%} of rows have UNKNOWN compound")
    per_race = df.groupby("race_id").size()
    short = per_race[per_race < 200]
    if len(short):
        add("warning", "short_races", f"{len(short)} races with fewer than 200 rows")
    return findings


def main() -> None:
    df = pd.read_parquet(FRAME)
    findings = check(df)
    print(json.dumps({"rows": len(df), "findings": findings}, indent=1))
    sys.exit(1 if any(f["severity"] == "error" for f in findings) else 0)


if __name__ == "__main__":
    main()
