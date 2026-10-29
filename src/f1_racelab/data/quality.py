"""Row- and event-level data-quality audit for qualifying datasets.

Each check returns findings with a severity:

* ``error``   – violates a modelling contract (duplicate key, non-permutation
  classification, negative gap). Ingestion output should not be trusted.
* ``warning`` – plausible provider artefact (a practice lap far off the field,
  missing team label, thin field). Kept in the data but surfaced.

The audit never edits data; it describes it, so an ingestion run can be
accepted or rejected with evidence. Units: ``*_gap_pct`` is percent of the
event-best lap, ``*_seconds`` is seconds.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATASET = ROOT / "data/processed/qualifying_mixed_2022_2023_2024_2025.parquet"
DEFAULT_OUT = ROOT / "data/processed/data_quality"

KEY = ["year", "round"]
SESSIONS = ("fp1", "fp2", "fp3")
FIELD_SIZE = (18, 22)
# A representative lap more than this far off the event-best is implausible for
# a flying practice lap (red flag, damaged car, or wrong unit).
MAX_PLAUSIBLE_GAP_PCT = 15.0
OUTLIER_ROBUST_Z = 6.0


@dataclass(frozen=True)
class Finding:
    severity: str
    check: str
    year: int | None
    round: int | None
    event: str | None
    driver: str | None
    detail: str


def _find(severity: str, check: str, row, detail: str, driver: str | None = None) -> Finding:
    return Finding(severity, check, int(row["year"]), int(row["round"]),
                   str(row["event"]), driver, detail)


def _robust_z(values: pd.Series) -> pd.Series:
    median = values.median()
    mad = (values - median).abs().median()
    scale = 1.4826 * mad if mad > 0 else np.nan
    return (values - median) / scale


def audit(df: pd.DataFrame) -> list[Finding]:
    findings: list[Finding] = []
    for column in ("year", "round", "event", "driver", "final_position"):
        if column not in df.columns:
            raise ValueError(f"Audit requires column {column!r}")

    duplicated = df[df.duplicated(KEY + ["driver"], keep=False)]
    for _, row in duplicated.drop_duplicates(KEY + ["driver"]).iterrows():
        findings.append(_find("error", "duplicate_driver_weekend", row,
                              "driver appears more than once in the weekend", row["driver"]))

    for (year, rnd), event in df.groupby(KEY, sort=True):
        head = event.iloc[0]
        n = len(event)
        if not FIELD_SIZE[0] <= n <= FIELD_SIZE[1]:
            findings.append(_find("warning", "field_size", head,
                                  f"{n} drivers outside {FIELD_SIZE[0]}-{FIELD_SIZE[1]}"))
        if event["event"].nunique() > 1:
            findings.append(_find("error", "event_name_inconsistent", head,
                                  f"names: {sorted(event['event'].unique())}"))

        positions = pd.to_numeric(event["final_position"], errors="coerce").dropna().astype(int)
        if sorted(positions) != list(range(1, len(positions) + 1)):
            findings.append(_find("error", "classification_not_permutation", head,
                                  f"positions {sorted(positions)[:25]} are not 1..{len(positions)}"))

        if "team" in event and event["team"].isna().any():
            missing = int(event["team"].isna().sum())
            findings.append(_find("warning", "missing_team", head, f"{missing} rows without team"))
        elif "team" in event and (event.groupby("team").size() > 2).any():
            findings.append(_find("warning", "team_has_more_than_two_drivers", head,
                                  "reserve driver or team-label error"))

        for fp in SESSIONS:
            gap = pd.to_numeric(event.get(f"{fp}_gap_pct"), errors="coerce")
            seconds = pd.to_numeric(event.get(f"{fp}_best_seconds"), errors="coerce")
            if gap.notna().any():
                if (gap.dropna() < -1e-9).any():
                    findings.append(_find("error", "negative_gap", head, f"{fp} has gap below zero"))
                best = gap.min()
                if abs(best) > 1e-6:
                    findings.append(_find("error", "gap_reference_not_zero", head,
                                          f"{fp} best gap is {best:.4f}, expected 0"))
                for index in gap[gap > MAX_PLAUSIBLE_GAP_PCT].index:
                    findings.append(_find("warning", "implausible_gap", event.loc[index],
                                          f"{fp} gap {gap[index]:.2f}% > {MAX_PLAUSIBLE_GAP_PCT}%",
                                          event.loc[index, "driver"]))
                z = _robust_z(gap.dropna())
                for index in z[z > OUTLIER_ROBUST_Z].index:
                    if gap[index] <= MAX_PLAUSIBLE_GAP_PCT:
                        findings.append(_find("warning", "practice_outlier", event.loc[index],
                                              f"{fp} gap {gap[index]:.2f}% robust z={z[index]:.1f}",
                                              event.loc[index, "driver"]))
            if ((seconds.dropna() < 40) | (seconds.dropna() > 200)).any():
                findings.append(_find("error", "lap_time_unit", head,
                                      f"{fp} best lap outside 40-200 s (unit error?)"))

        q = [pd.to_numeric(event.get(f"q{i}_seconds"), errors="coerce") for i in (1, 2, 3)]
        both = pd.DataFrame({"q1": q[0], "q2": q[1], "q3": q[2]})
        # Within a driver, a later phase should not be slower than Q1 by much
        # unless the track evolved against them; flag only large inversions.
        for later in ("q2", "q3"):
            slow = both[(both[later] - both["q1"]) / both["q1"] > 0.02].index
            for index in slow:
                findings.append(_find("warning", "later_phase_slower_than_q1", event.loc[index],
                                      f"{later} >2% slower than Q1",
                                      event.loc[index, "driver"]))
        poles = event.index[event["final_position"] == 1]
        q1 = both["q1"].dropna()
        if len(poles) == 1 and poles[0] in q1.index:
            pole_q1_rank = int(q1.rank(method="first")[poles[0]])
            if pole_q1_rank > 8:
                findings.append(_find("warning", "pole_sitter_slow_in_q1", head,
                                      f"pole-sitter was only {pole_q1_rank}th in Q1"))
    return findings


def coverage_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Per-weekend fraction of drivers with each key field (0-1)."""
    fields = [f"{fp}_gap_pct" for fp in SESSIONS] + ["q1_seconds", "q2_seconds", "q3_seconds", "team"]
    present = [f for f in fields if f in df.columns]
    table = df.groupby(KEY + ["event"], sort=True).apply(
        lambda part: pd.Series({f: part[f].notna().mean() for f in present} | {"drivers": len(part)}),
        include_groups=False,
    )
    return table.reset_index()


def summarise(df: pd.DataFrame, findings: list[Finding]) -> dict:
    frame = pd.DataFrame([asdict(f) for f in findings],
                         columns=list(Finding.__dataclass_fields__))
    by_check = (frame.groupby(["severity", "check"]).size().rename("count").reset_index()
                .sort_values(["severity", "count"], ascending=[True, False])
                if len(frame) else pd.DataFrame(columns=["severity", "check", "count"]))
    weekends = df[KEY].drop_duplicates().shape[0]
    return {
        "rows": len(df), "weekends": int(weekends),
        "years": sorted(int(y) for y in df["year"].unique()),
        "errors": int((frame.severity == "error").sum()) if len(frame) else 0,
        "warnings": int((frame.severity == "warning").sum()) if len(frame) else 0,
        "weekends_with_error": int(frame.loc[frame.severity == "error", KEY].drop_duplicates().shape[0]) if len(frame) else 0,
        "by_check": by_check.to_dict("records"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--strict", action="store_true", help="exit 1 when any error finding exists")
    args = parser.parse_args()
    df = pd.read_parquet(args.dataset)
    findings = audit(df)
    summary = summarise(df, findings)
    args.out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([asdict(f) for f in findings]).to_csv(args.out / "findings.csv", index=False)
    coverage_matrix(df).to_csv(args.out / "coverage.csv", index=False)
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    if args.strict and summary["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
