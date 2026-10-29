import numpy as np
import pandas as pd

from f1_racelab.data import quality


def weekend(year=2025, rnd=1, n=20):
    rows = []
    for k in range(n):
        pace = k * 0.1
        row = {"year": year, "round": rnd, "event": "Test GP", "driver": f"D{k:02d}",
               "team": f"T{k // 2}", "final_position": k + 1,
               "q1_seconds": 80 + pace, "q2_seconds": 79.5 + pace, "q3_seconds": 79 + pace}
        for fp in quality.SESSIONS:
            row[f"{fp}_best_seconds"] = 81 + pace
            row[f"{fp}_gap_pct"] = pace / 81 * 100
        rows.append(row)
    return pd.DataFrame(rows)


def checks(df):
    return {(f.severity, f.check) for f in quality.audit(df)}


def test_clean_weekend_has_no_findings():
    assert quality.audit(weekend()) == []


def test_duplicate_and_non_permutation_classification_are_errors():
    df = weekend()
    df.loc[1, "driver"] = df.loc[0, "driver"]
    df.loc[5, "final_position"] = 3
    found = checks(df)
    assert ("error", "duplicate_driver_weekend") in found
    assert ("error", "classification_not_permutation") in found


def test_gap_contract_and_unit_errors():
    df = weekend()
    df["fp1_gap_pct"] += 0.5            # reference no longer zero
    df.loc[2, "fp2_best_seconds"] = 8100.0  # milliseconds-vs-seconds slip
    found = checks(df)
    assert ("error", "gap_reference_not_zero") in found
    assert ("error", "lap_time_unit") in found


def test_outlier_and_implausible_gap_are_warnings_not_errors():
    df = weekend()
    df.loc[3, "fp3_gap_pct"] = 20.0
    df.loc[4, "fp1_gap_pct"] = 9.0
    found = checks(df)
    assert ("warning", "implausible_gap") in found
    assert ("warning", "practice_outlier") in found
    assert not any(severity == "error" for severity, _ in found)


def test_wet_qualifying_pattern_and_thin_field_are_flagged():
    df = weekend(n=14)
    df.loc[0, "q3_seconds"] = 90.0
    found = checks(df)
    assert ("warning", "field_size") in found
    assert ("warning", "later_phase_slower_than_q1") in found


def test_summary_and_coverage_matrix():
    df = pd.concat([weekend(rnd=1), weekend(rnd=2)], ignore_index=True)
    df.loc[0, "team"] = np.nan
    findings = quality.audit(df)
    summary = quality.summarise(df, findings)
    assert summary["weekends"] == 2 and summary["errors"] == 0 and summary["warnings"] == 1
    cov = quality.coverage_matrix(df)
    assert len(cov) == 2 and cov.loc[0, "team"] == 0.95 and cov.loc[0, "drivers"] == 20
