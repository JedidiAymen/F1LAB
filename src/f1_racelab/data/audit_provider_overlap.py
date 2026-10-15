"""Compare a weekend independently available in FastF1 and OpenF1 caches."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from scipy.stats import spearmanr

from f1_racelab.data.qualifying_dataset import OUTPUT_ROOT

TIME_FIELDS = ("fp1_best_seconds", "fp2_best_seconds", "fp3_best_seconds", "q1_seconds")


def audit(year: int, round_no: int, *, root: Path = OUTPUT_ROOT) -> tuple[pd.DataFrame, dict]:
    candidates = []
    for folder in ("qualifying_weekends", "qualifying_openf1_weekends"):
        paths = sorted((root / folder).glob(f"{year}_{round_no:02d}_*.parquet"))
        if len(paths) != 1:
            raise FileNotFoundError(f"Expected one {folder} event for {year} R{round_no}, got {len(paths)}")
        candidates.append(paths[0])
    fastf1, openf1 = (pd.read_parquet(path) for path in candidates)
    if fastf1.duplicated("driver").any() or openf1.duplicated("driver").any():
        raise ValueError("Duplicate driver in provider event")
    joined = fastf1[["driver", *TIME_FIELDS, "final_position"]].merge(
        openf1[["driver", *TIME_FIELDS, "final_position"]], on="driver",
        how="outer", suffixes=("_fastf1", "_openf1"), indicator=True,
        validate="one_to_one",
    )
    summary: dict = {"year": year, "round": round_no, "fastf1_rows": len(fastf1),
                     "openf1_rows": len(openf1),
                     "matched_drivers": int(joined._merge.eq("both").sum()),
                     "unmatched_drivers": joined.loc[joined._merge.ne("both"), "driver"].tolist()}
    for field in TIME_FIELDS:
        left, right = f"{field}_fastf1", f"{field}_openf1"
        paired = joined[[left, right]].dropna()
        difference = (paired[left] - paired[right]).abs()
        summary[field] = {"pairs": len(paired), "mae_seconds": float(difference.mean()),
                          "max_abs_seconds": float(difference.max()),
                          "spearman": float(spearmanr(paired[left], paired[right]).statistic)
                          if len(paired) > 2 else None}
    paired_positions = joined[["final_position_fastf1", "final_position_openf1"]].dropna()
    summary["classification_mismatches"] = int(
        paired_positions["final_position_fastf1"].ne(paired_positions["final_position_openf1"]).sum()
    )
    return joined, summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--round", type=int, default=16)
    parser.add_argument("--root", type=Path, default=OUTPUT_ROOT)
    args = parser.parse_args()
    joined, summary = audit(args.year, args.round, root=args.root)
    destination = args.root / f"provider_overlap_{args.year}_{args.round:02d}"
    destination.mkdir(parents=True, exist_ok=True)
    joined.to_csv(destination / "drivers.csv", index=False)
    (destination / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
