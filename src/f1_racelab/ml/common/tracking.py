"""Local run provenance and opt-in MLflow REST tracking, without an SDK dependency.

The registry calls this after a successful fit/save. Importing an older model
is a distinct ``artifact_import`` operation; it never becomes a new training
measurement. Local checksums/cards remain authoritative when MLflow is down.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Literal

import httpx

from f1_racelab.ml.common.contracts import ModelCard, now_utc, read_card

ROOT = Path(__file__).resolve().parents[4]
LOGGER = logging.getLogger(__name__)


def source_revision() -> dict:
    try:
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, timeout=3).strip()
        dirty = bool(subprocess.check_output(
            ["git", "status", "--porcelain", "--", "src", "scripts", "pyproject.toml", "uv.lock"],
            cwd=ROOT, text=True, timeout=3).strip())
        return {"sha": sha, "dirty": dirty}
    except (OSError, subprocess.SubprocessError):
        return {"sha": os.environ.get("F1LAB_SOURCE_SHA", "unknown"), "dirty": None}


def numeric_metrics(value: object, prefix: str = "") -> dict[str, float]:
    """Flatten named metric tables, keeping units in their original key names."""
    out: dict[str, float] = {}
    if isinstance(value, dict):
        for key, child in value.items():
            out.update(numeric_metrics(child, f"{prefix}.{key}".strip(".")))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            label = child.get("model", index) if isinstance(child, dict) else index
            out.update(numeric_metrics(child, f"{prefix}.{label}"))
    elif isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value):
        out[prefix] = float(value)
    return out


def _write(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True))
    temporary.replace(path)


def _sync(client: httpx.Client, manifest: dict, root: Path, name: str, card: ModelCard) -> None:
    def post(endpoint: str, payload: dict) -> dict:
        response = client.post(f"/api/2.0/mlflow/{endpoint}", json=payload)
        response.raise_for_status()
        return response.json()

    experiment_name = f"F1LAB/{card.model_id}"
    response = client.get("/api/2.0/mlflow/experiments/get-by-name", params={"experiment_name": experiment_name})
    if response.status_code == 404:
        experiment_id = post("experiments/create", {"name": experiment_name})["experiment_id"]
    else:
        response.raise_for_status()
        experiment_id = response.json()["experiment"]["experiment_id"]
    tags = {"mlflow.runName": f"{card.model_id}-v{card.version}-{manifest['run_kind']}",
            "f1lab.run_kind": manifest["run_kind"], "f1lab.evidence": card.evidence,
            "f1lab.source_sha": manifest["source"]["sha"],
            "f1lab.source_dirty": str(manifest["source"]["dirty"]),
            "f1lab.dataset_fingerprint": card.dataset_fingerprint,
            "f1lab.model_sha256": manifest["files"][f"{name}.joblib"],
            "f1lab.data_license": card.data_license}
    run = post("runs/create", {"experiment_id": experiment_id, "start_time": int(time.time() * 1000),
                               "tags": [{"key": key, "value": value} for key, value in tags.items()]})["run"]
    run_id = run["info"]["run_id"]
    manifest["tracking"] = {"status": "syncing", "run_id": run_id, "experiment_id": experiment_id}
    try:
        timestamp = int(time.time() * 1000)
        post("runs/log-batch", {"run_id": run_id,
                               "params": [{"key": key, "value": str(value)} for key, value in
                                          {**card.hyperparameters, "seed": card.seed,
                                           "dataset_rows": card.dataset_rows, "split_policy": card.split.policy}.items()],
                               "metrics": [{"key": key, "value": value, "timestamp": timestamp, "step": 0}
                                           for key, value in numeric_metrics(card.metrics).items()]})
        uri = run["info"]["artifact_uri"]
        if not uri.startswith("mlflow-artifacts:/"):
            raise ValueError("MLflow must proxy artifacts (--serve-artifacts); external artifact stores are not used")
        artifact_path = uri.removeprefix("mlflow-artifacts:/").strip("/")
        for filename in manifest["files"]:
            response = client.put(f"/api/2.0/mlflow-artifacts/artifacts/{artifact_path}/{filename}",
                                  content=(root / filename).read_bytes(),
                                  headers={"Content-Type": "application/octet-stream"})
            response.raise_for_status()
        manifest["tracking"]["status"] = "synced"
        response = client.put(f"/api/2.0/mlflow-artifacts/artifacts/{artifact_path}/{name}.run.json",
                              content=json.dumps(manifest).encode(), headers={"Content-Type": "application/json"})
        response.raise_for_status()
        post("runs/update", {"run_id": run_id, "status": "FINISHED", "end_time": int(time.time() * 1000)})
    except Exception:
        try:
            post("runs/update", {"run_id": run_id, "status": "FAILED", "end_time": int(time.time() * 1000)})
        except httpx.HTTPError:
            pass
        raise


def record_artifact(root: Path, name: str, card: ModelCard, *,
                    run_kind: Literal["training", "artifact_import"] = "training",
                    tracking_uri: str | None = None, client: httpx.Client | None = None) -> dict:
    """Verify bytes, save a manifest, and optionally track; remote failures are explicit."""
    files = {f"{name}{suffix}": hashlib.sha256((root / f"{name}{suffix}").read_bytes()).hexdigest()
             for suffix in (".joblib", ".card.json", ".sha256")}
    if files[f"{name}.joblib"] != (root / f"{name}.sha256").read_text().strip():
        raise ValueError("Artifact SHA-256 mismatch; refusing to track")
    manifest: dict = {"schema_version": 1, "run_kind": run_kind, "recorded_at_utc": now_utc(),
                "model_id": card.model_id, "model_version": card.version, "evidence": card.evidence,
                "dataset_fingerprint": card.dataset_fingerprint, "source": source_revision(),
                "files": files, "dependencies": card.dependencies, "metrics": card.metrics,
                "tracking": {"status": "disabled"}}
    uri = tracking_uri or os.environ.get("MLFLOW_TRACKING_URI")
    if uri:
        try:
            if client is not None:
                _sync(client, manifest, root, name, card)
            else:
                with httpx.Client(base_url=uri.rstrip("/"), timeout=10) as remote:
                    _sync(remote, manifest, root, name, card)
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            manifest["tracking"].update(status="failed", error_type=type(exc).__name__)
            LOGGER.warning("mlflow_sync_failed model_id=%s error_type=%s", card.model_id, type(exc).__name__)
    _write(root / f"{name}.run.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--tracking-uri")
    args = parser.parse_args()
    card = read_card(args.root / f"{args.name}.card.json")
    manifest = record_artifact(args.root, args.name, card, run_kind="artifact_import", tracking_uri=args.tracking_uri)
    print(json.dumps(manifest, indent=2))
    if manifest["tracking"]["status"] == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
