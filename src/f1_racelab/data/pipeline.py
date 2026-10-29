"""One-command qualifying ingestion: OpenF1 sync -> provider merge -> quality gate.

Writes ``pipeline_manifest_<years>.json`` recording arguments, per-step outcome,
dataset SHA-256, library versions and the audit summary, so any run can be
reproduced and compared. ``--offline`` uses only the cached raw responses.
The quality gate fails the run (exit 1) on error-severity findings.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path

import pandas as pd

from f1_racelab.data import mixed_qualifying, openf1_qualifying, quality
from f1_racelab.data.qualifying_dataset import OUTPUT_ROOT


def _versions() -> dict[str, str]:
    names = ("pandas", "pyarrow", "httpx", "fastf1")
    return {"python": platform.python_version(),
            **{name: metadata.version(name) for name in names}}


def run(years: list[int], *, output_root: Path = OUTPUT_ROOT, offline: bool = False,
        merge: bool = True, fail_on_errors: bool = True) -> dict:
    years = sorted(set(years))
    suffix = "_".join(map(str, years))
    started = datetime.now(UTC)
    steps: list[dict] = []

    combined_openf1, report = openf1_qualifying.build_dataset(
        years, output_root=output_root, offline=offline)
    errors = report[report.status == "ERROR"]
    steps.append({
        "step": "openf1_sync", "weekends": int(combined_openf1[["year", "round"]].drop_duplicates().shape[0]),
        "rows": len(combined_openf1), "status_counts": report.status.value_counts().to_dict(),
        "errors": errors[["year", "round", "event", "detail"]].to_dict("records"),
    })
    dataset_frame = combined_openf1
    dataset_path = output_root / f"qualifying_openf1_{suffix}.parquet"

    if merge:
        dataset_frame = mixed_qualifying.combine(output_root, tuple(years))
        dataset_path = output_root / f"qualifying_mixed_2022_{suffix}.parquet"
        steps.append({"step": "provider_merge", "rows": len(dataset_frame),
                      "providers": sorted(dataset_frame.provider.unique())})

    findings = quality.audit(dataset_frame)
    summary = quality.summarise(dataset_frame, findings)
    audit_dir = output_root / "data_quality" / suffix
    audit_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([f.__dict__ for f in findings]).to_csv(audit_dir / "findings.csv", index=False)
    quality.coverage_matrix(dataset_frame).to_csv(audit_dir / "coverage.csv", index=False)
    steps.append({"step": "quality_gate", **{k: summary[k] for k in ("errors", "warnings", "weekends")}})

    manifest = {
        "started_at_utc": started.isoformat(), "finished_at_utc": datetime.now(UTC).isoformat(),
        "years": years, "offline": offline, "merge": merge, "steps": steps,
        "dataset": str(dataset_path),
        "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "quality": summary, "versions": _versions(),
        "passed": summary["errors"] == 0,
    }
    (output_root / f"pipeline_manifest_{suffix}.json").write_text(json.dumps(manifest, indent=2))
    if fail_on_errors and not manifest["passed"]:
        raise SystemExit(f"Quality gate failed: {summary['errors']} error finding(s); see {audit_dir}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", type=int, nargs="+", default=[2023, 2024, 2025])
    parser.add_argument("--out", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--offline", action="store_true", help="use cached raw responses only")
    parser.add_argument("--no-merge", action="store_true", help="skip FastF1 2022 provider merge")
    args = parser.parse_args()
    manifest = run(args.years, output_root=args.out, offline=args.offline, merge=not args.no_merge)
    print(json.dumps({k: manifest[k] for k in ("years", "dataset_sha256", "passed")}, indent=2))


if __name__ == "__main__":
    main()
