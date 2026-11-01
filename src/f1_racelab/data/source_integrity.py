"""Immutable source evidence and conservative OpenF1 lap-coverage screening.

Completeness cannot be inferred from a valid JSON response or roster coverage.
This module never alters the provider cache or treats a heuristic as proof of
complete ingestion. A reference classification is optional and independently
recorded; a mismatch is evidence for review, not proof of provider error.
"""
from __future__ import annotations

import hashlib
import json
import os
import string
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _timestamp_known(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return datetime.fromisoformat(value).utcoffset() is not None
    except ValueError:
        return False


def audit_laps(payload: bytes, session_key: int, *, reference_completed: dict[int, int] | None = None,
               session_window_utc: tuple[str, str] | None = None) -> dict:
    """Screen source rows without inferring a guaranteed expected row count."""
    if reference_completed is not None and any(
        not isinstance(driver, int) or isinstance(driver, bool) or driver <= 0
        or not isinstance(count, int) or isinstance(count, bool) or count < 0
        for driver, count in reference_completed.items()
    ):
        raise ValueError("Reference driver IDs and completed laps must be nonnegative integers")
    rows = json.loads(payload)
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("Source response must be a JSON array of objects")
    frame = pd.DataFrame(rows)
    required = {"session_key", "driver_number", "lap_number", "date_start", "lap_duration"}
    missing = sorted(required - set(frame.columns))
    report: dict[str, Any] = {"schema_version": 1, "session_key": session_key, "rows": len(rows),
                              "content_sha256": sha256(payload), "missing_columns": missing,
                              "completeness": "unknown", "findings": []}
    if missing or frame.empty:
        report.update(status="broken", findings=["Missing required columns or no rows"])
        return report
    key_numeric = {col: pd.to_numeric(frame[col], errors="coerce") for col in ("session_key", "driver_number", "lap_number")}
    invalid_keys = sum(int((~np.isfinite(series) | (series % 1 != 0) | (series <= 0)).sum())
                       for series in key_numeric.values())
    wrong_session = int((key_numeric["session_key"] != session_key).sum())
    duplicates = int(pd.DataFrame({"driver": key_numeric["driver_number"], "lap": key_numeric["lap_number"]}).duplicated().sum())
    times = pd.to_datetime(frame.date_start, utc=True, errors="coerce", format="mixed")
    supplied_time = frame.date_start.notna()
    invalid_times = int((supplied_time & (times.isna() | ~frame.date_start.map(_timestamp_known))).sum())
    outside_window = None
    if session_window_utc is not None:
        start, end = (pd.Timestamp(value) for value in session_window_utc)
        if start.tzinfo is None or end.tzinfo is None or end <= start:
            raise ValueError("Session window must contain ordered timezone-aware timestamps")
        outside_window = int((times.notna() & ((times < start) | (times > end))).sum())
    durations = pd.to_numeric(frame.lap_duration, errors="coerce")
    invalid_durations = int((frame.lap_duration.notna() & (~np.isfinite(durations) | (durations <= 0))).sum())
    drivers: list[dict[str, Any]] = []
    for driver, group in frame.assign(_driver=key_numeric["driver_number"], _lap=key_numeric["lap_number"]).groupby("_driver"):
        if not np.isfinite(driver) or driver <= 0 or driver % 1 != 0:
            continue
        laps = sorted({int(value) for value in group._lap.dropna() if np.isfinite(value) and value > 0 and value % 1 == 0})
        if not laps:
            continue
        internal_missing = laps[-1] - laps[0] + 1 - len(laps)
        reference = (reference_completed or {}).get(int(driver))
        observed_reference = len({lap for lap in laps if reference is not None and lap <= reference})
        drivers.append({"driver_number": int(driver), "rows": len(group), "first_lap": laps[0], "last_lap": laps[-1],
                        "internal_missing_keys": internal_missing, "reference_completed_laps": reference,
                        "observed_keys_within_reference": observed_reference if reference is not None else None})
    late = [row["driver_number"] for row in drivers if row["first_lap"] > 3]
    sparse = [row["driver_number"] for row in drivers if row["last_lap"] > row["first_lap"]
              and row["internal_missing_keys"] / (row["last_lap"] - row["first_lap"] + 1) > 0.2]
    report.update({"drivers": drivers, "driver_count": len(drivers), "late_start_drivers": late,
                   "sparse_key_drivers": sparse, "duplicate_keys": duplicates, "invalid_keys": invalid_keys,
                   "wrong_session_rows": wrong_session, "invalid_timestamps": invalid_times,
                   "outside_declared_session_window": outside_window,
                   "timestamp_missing": int((~supplied_time).sum()),
                   "timestamp_min_utc": times.min().isoformat() if times.notna().any() else None,
                   "timestamp_max_utc": times.max().isoformat() if times.notna().any() else None,
                   "duration_finite": int(np.isfinite(durations).sum()), "duration_missing": int(frame.lap_duration.isna().sum()),
                   "duration_invalid": invalid_durations,
                   "reference_kind": "cross-endpoint completed-lap totals" if reference_completed is not None else None})
    if reference_completed is not None:
        observed = {row["driver_number"] for row in drivers}
        report["reference_drivers_without_lap_rows"] = sorted(set(reference_completed) - observed)
        report["lap_drivers_not_in_reference"] = sorted(observed - set(reference_completed))
        report["reference_coverage_shortfall_drivers"] = [row["driver_number"] for row in drivers
            if row["reference_completed_laps"] is not None
            and row["observed_keys_within_reference"] < row["reference_completed_laps"]]
        report["reference_positive_drivers_without_lap_rows"] = sorted(
            driver for driver in set(reference_completed) - observed if reference_completed[driver] > 0)
    errors = invalid_keys or wrong_session or duplicates or invalid_times or invalid_durations
    if errors:
        report["status"] = "broken"
        report["findings"].append("Schema, identity, key, timestamp or duration contract violation")
    elif late or sparse or outside_window or report.get("reference_coverage_shortfall_drivers") or report.get("reference_positive_drivers_without_lap_rows"):
        report["status"] = "review"
        report["findings"].append("Coverage, time-window or reference discrepancies require inspection; screening is not a completeness proof")
    else:
        report["status"] = "unknown"
        report["findings"].append("No screening anomaly detected; provider completeness remains unknown")
    return report


def audit_telemetry(payload: bytes, session_key: int, *, max_gap_seconds: float = 1.0) -> dict:
    """Summarize observed channels and sampling gaps without imputing values."""
    rows = json.loads(payload)
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("Source response must be a JSON array of objects")
    if not np.isfinite(max_gap_seconds) or max_gap_seconds <= 0:
        raise ValueError("Gap threshold must be finite and positive")
    frame = pd.DataFrame(rows)
    required = {"session_key", "driver_number", "date"}
    missing = sorted(required - set(frame.columns))
    result: dict[str, Any] = {"content_sha256": sha256(payload), "rows": len(rows),
                              "missing_columns": missing, "completeness": "unknown"}
    if missing or frame.empty:
        return {**result, "status": "broken"}
    date = pd.to_datetime(frame.date, utc=True, errors="coerce", format="mixed")
    session_values = pd.to_numeric(frame.session_key, errors="coerce")
    driver_values = pd.to_numeric(frame.driver_number, errors="coerce")
    keys = frame.assign(_date=date, _session=session_values, _driver=driver_values)
    duplicates = int(keys.duplicated(["_session", "_driver", "_date"]).sum())
    invalid_keys = int((~np.isfinite(driver_values) | (driver_values % 1 != 0) | (driver_values <= 0)).sum())
    wrong_session = int((session_values != session_key).sum())
    missing_dates = int((date.isna() | ~frame.date.map(_timestamp_known)).sum())
    gaps: list[float] = []
    for _, group in keys.groupby("_driver"):
        values = group._date.dropna().sort_values()
        gaps.extend(values.diff().dt.total_seconds().dropna().tolist())
    channels = {}
    implausible = 0
    for column in ("speed", "throttle", "brake", "n_gear", "rpm", "drs"):
        values = pd.to_numeric(frame[column], errors="coerce") if column in frame else pd.Series(np.nan, index=frame.index)
        finite = np.isfinite(values)
        channels[column] = {"column_present": column in frame, "missing_or_nonfinite": int((~finite).sum()),
                            "observed_min": float(values[finite].min()) if finite.any() else None,
                            "observed_max": float(values[finite].max()) if finite.any() else None}
        if column in {"speed", "rpm"}:
            implausible += int((finite & (values < 0)).sum())
    result.update({"status": "broken" if duplicates or wrong_session or missing_dates or invalid_keys else
                   "review" if implausible or any(gap > max_gap_seconds for gap in gaps) else "unknown",
                   "duplicate_keys": duplicates, "wrong_session_rows": wrong_session, "invalid_driver_keys": invalid_keys,
                   "negative_speed_or_rpm_values": implausible, "invalid_or_missing_dates": missing_dates,
                   "gap_threshold_seconds": max_gap_seconds, "gaps_above_threshold": sum(g > max_gap_seconds for g in gaps),
                   "max_gap_seconds": max(gaps) if gaps else None,
                   "median_gap_seconds": float(np.median(gaps)) if gaps else None, "channels": channels,
                   "units": {"speed": "km/h", "throttle": "provider percent", "brake": "provider value",
                             "n_gear": "gear", "rpm": "rpm", "drs": "provider code"}})
    return result


def dataset_manifest(sources: list[dict], output: Path, *, transform_sha256: str,
                     feature_contract: dict, cutoff: str, unknown_rationale: str | None = None) -> dict:
    """Bind a dataset to verified raw bytes and an explicit transformation contract."""
    if not sources or len(transform_sha256) != 64 or not all(c in string.hexdigits for c in transform_sha256) or not cutoff.strip() or not feature_contract:
        raise ValueError("Sources, transformation SHA-256, feature contract and cutoff are required")
    inputs = []
    for source in sources:
        # Preserve the original screen, including optional reference evidence.
        # Re-screening without that reference must not release a quarantined input.
        require_research_input(source["audit"], acknowledge_unknown=unknown_rationale)
        snapshot = Path(source["snapshot"])
        if snapshot.is_symlink():
            raise ValueError("Source snapshot cannot be a symlink")
        data = snapshot.read_bytes()
        if sha256(data) != source["source_sha256"] or source["audit"].get("content_sha256") != source["source_sha256"]:
            raise ValueError("Source snapshot checksum mismatch")
        if source["provider"] != "OpenF1" or source["endpoint"] != "laps":
            raise ValueError("This gate currently supports only OpenF1 laps")
        report = audit_laps(data, int(source["parameters"]["session_key"]))
        require_research_input(report, acknowledge_unknown=unknown_rationale)
        inputs.append({"provider": source["provider"], "endpoint": source["endpoint"],
                       "parameters": source["parameters"], "sha256": source["source_sha256"],
                       "original_audit": source["audit"]})
    inputs.sort(key=lambda row: json.dumps(row, sort_keys=True))
    identity = {"schema_version": 1, "sources": inputs, "transform_sha256": transform_sha256,
                "feature_contract": feature_contract, "cutoff": cutoff, "output_sha256": sha256_file(output),
                "unknown_rationale": unknown_rationale}
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return {**identity, "dataset_id": "sha256:" + sha256(encoded), "completeness": "unknown",
            "unknown_rationale": unknown_rationale}


def publish_dataset_manifest(store: Path, manifest: dict) -> Path:
    """Write an immutable manifest and reject any attempted ID collision."""
    identity = {key: value for key, value in manifest.items() if key not in {"dataset_id", "completeness"}}
    digest = sha256(json.dumps(identity, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())
    if manifest.get("dataset_id") != "sha256:" + digest or manifest.get("completeness") != "unknown":
        raise ValueError("Dataset identity does not match its contract")
    payload = json.dumps(manifest, sort_keys=True, indent=2, allow_nan=False).encode()
    folder = store / "datasets"
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / f"{digest}.json"
    fd, tmp = tempfile.mkstemp(prefix=".staging-", dir=folder)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(tmp, destination)
            destination.chmod(0o444)
        except FileExistsError:
            if destination.is_symlink() or destination.read_bytes() != payload:
                raise ValueError("Existing dataset manifest differs from its identity") from None
    finally:
        Path(tmp).unlink(missing_ok=True)
    return destination


def verify_dataset_manifest(store: Path, manifest: dict, output: Path) -> None:
    """Recheck identity, output and every archived source before training."""
    identity = {key: value for key, value in manifest.items() if key not in {"dataset_id", "completeness"}}
    digest = sha256(json.dumps(identity, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())
    if manifest.get("dataset_id") != "sha256:" + digest or manifest.get("completeness") != "unknown":
        raise ValueError("Dataset identity does not match its contract")
    if sha256_file(output) != manifest["output_sha256"]:
        raise ValueError("Dataset output checksum mismatch")
    for source in manifest["sources"]:
        source_hash = source["sha256"]
        if len(source_hash) != 64 or any(c not in "0123456789abcdef" for c in source_hash):
            raise ValueError("Invalid source digest")
        path = store / "snapshots" / f"{source_hash}.json"
        if path.is_symlink():
            raise ValueError("Source snapshot cannot be a symlink")
        data = path.read_bytes()
        if sha256(data) != source_hash:
            raise ValueError("Source snapshot checksum mismatch")
        if source["original_audit"].get("content_sha256") != source_hash:
            raise ValueError("Original source audit checksum mismatch")
        require_research_input(source["original_audit"], acknowledge_unknown=manifest["unknown_rationale"])
        if source["provider"] != "OpenF1" or source["endpoint"] != "laps":
            raise ValueError("Unsupported source contract")
        require_research_input(audit_laps(data, int(source["parameters"]["session_key"])),
                               acknowledge_unknown=manifest["unknown_rationale"])


def archive(store: Path, payload: bytes, *, provider: str, endpoint: str, parameters: dict,
            retrieved_at_utc: str | None, report: dict, source_location: str | None = None,
            gate_decision: dict | None = None) -> dict:
    """Publish content-addressed bytes once; preserve every observation record."""
    digest = sha256(payload)
    if report.get("content_sha256") != digest:
        raise ValueError("Audit does not describe these source bytes")
    if retrieved_at_utc is not None:
        stamp = datetime.fromisoformat(retrieved_at_utc)
        if stamp.tzinfo is None:
            raise ValueError("Retrieval timestamp must be timezone-aware")
    folder = store / ("quarantine" if report["status"] in {"broken", "review"} else "snapshots")
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / f"{digest}.json"
    fd, tmp = tempfile.mkstemp(prefix=".staging-", dir=folder)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(tmp, destination)
            destination.chmod(0o444)
        except FileExistsError:
            if destination.is_symlink() or sha256(destination.read_bytes()) != digest:
                raise ValueError("Existing snapshot checksum mismatch") from None
    finally:
        Path(tmp).unlink(missing_ok=True)
    manifest = {"schema_version": 1, "provider": provider, "endpoint": endpoint, "parameters": parameters,
                "retrieved_at_utc": retrieved_at_utc, "audited_at_utc": datetime.now(UTC).isoformat(),
                "provider_base_url": "https://api.openf1.org/v1" if provider == "OpenF1" else None,
                "source_location": source_location, "source_sha256": digest, "source_bytes": len(payload),
                "snapshot": str(destination), "audit": report, "gate_decision": gate_decision}
    # Unique metadata records never overwrite another retrieval or audit.
    records = store / "records"
    records.mkdir(parents=True, exist_ok=True)
    payload_record = json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False).encode()
    fd, temporary = tempfile.mkstemp(prefix=".staging-", dir=records)
    record_path = records / f"{digest[:12]}-{uuid.uuid4().hex}.json"
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload_record)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, record_path)
        record_path.chmod(0o444)
    finally:
        Path(temporary).unlink(missing_ok=True)
    manifest["record"] = str(record_path)
    return manifest


def require_research_input(report: dict, *, acknowledge_unknown: str | None = None) -> None:
    """Fail closed on broken/review sources and require explicit uncertainty."""
    if report.get("status") in {"broken", "review"}:
        raise ValueError("Source requires review; do not use it as a new research input")
    if report.get("status") != "unknown" or not acknowledge_unknown or not acknowledge_unknown.strip():
        raise ValueError("Provider completeness is unknown; record an explicit scoped rationale")


def gated_lap_snapshot(store: Path, payload: bytes, session_key: int, *,
                       retrieved_at_utc: str | None, acknowledge_unknown: str | None = None,
                       reference_completed: dict[int, int] | None = None,
                       source_location: str | None = None) -> dict:
    """Archive before gating so rejected evidence and provenance are retained."""
    report = audit_laps(payload, session_key, reference_completed=reference_completed)
    item = archive(store, payload, provider="OpenF1", endpoint="laps", parameters={"session_key": session_key},
                   retrieved_at_utc=retrieved_at_utc, report=report, source_location=source_location,
                   gate_decision={"accepted": report["status"] == "unknown" and bool(acknowledge_unknown and acknowledge_unknown.strip()),
                                  "unknown_rationale": acknowledge_unknown})
    require_research_input(report, acknowledge_unknown=acknowledge_unknown)
    return item
