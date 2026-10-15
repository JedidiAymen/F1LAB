"""Enrich previously cached qualifying weekend Parquet with FP3 team labels.

Reuses FastF1 session cache. Does not require rebuilding raw features.
This is optional: driver form works even when some team labels are missing.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from f1_racelab.data.fastf1_source import load_session

ROOT = Path(__file__).resolve().parents[3] / "data" / "processed"


def enrich(file: Path) -> tuple[int, int]:
    frame = pd.read_parquet(file)
    if "team" not in frame.columns:
        frame["team"] = pd.NA
    missing = frame["team"].isna() | frame["team"].astype("string").str.strip().eq("")
    if not missing.any():
        return len(frame), 0
    year = int(frame["year"].iloc[0]); rd = int(frame["round"].iloc[0])
    fp3 = load_session(year, rd, "FP3")
    lookup = (fp3.laps[["Driver", "Team"]].dropna().drop_duplicates("Driver")
              .set_index("Driver")["Team"])
    frame.loc[missing, "team"] = frame.loc[missing, "driver"].map(lookup).to_numpy()
    frame.to_parquet(file, index=False)
    return len(frame), int(frame["team"].notna().sum())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--years", type=int, nargs="+", default=[2022, 2023, 2024, 2025])
    ap.add_argument("--root", type=Path, default=ROOT)
    a = ap.parse_args()
    yearset = set(a.years)
    paths = sorted(p for p in (a.root / "qualifying_weekends").glob("*.parquet") if int(p.name[:4]) in yearset)
    if not paths:
        ap.error("No cached weekends yet; run f1_racelab.data.qualifying_dataset first")
    good = 0
    failures = []
    for p in paths:
        try:
            rows, labels = enrich(p)
            good += 1
            print(f"[TEAM] {p.name}: {labels}/{rows} team labels", flush=True)
        except Exception as e:  # noqa: BLE001 - report each provider/cache failure
            failures.append(p.name)
            print(f"[WARN] {p.name}: {type(e).__name__}: {e}", flush=True)
    print(f"Enriched {good}/{len(paths)} weekend files", flush=True)
    if failures:
        raise RuntimeError(f"Team enrichment incomplete for {len(failures)} weekends: {failures}")
    # Reassemble only from the cached files for selected years. Other years
    # are intentionally untouched, no accidental deletion of raw cache.
    combined = [pd.read_parquet(p) for p in paths]
    if combined:
        output = a.root / ("qualifying_" + "_".join(map(str, sorted(yearset))) + ".parquet")
        pd.concat(combined, ignore_index=True).sort_values(["year", "round", "final_position"]).to_parquet(output, index=False)
        print(f"Wrote {output} ({len(combined)} weekends)")

if __name__ == "__main__":
    main()
