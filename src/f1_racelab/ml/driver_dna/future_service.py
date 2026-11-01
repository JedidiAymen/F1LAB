"""Read-only saved future-performance research; never trains or serves a live model."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from f1_racelab.ml.driver_dna.future_data import OUT, ROOT, SESSIONS

DEFAULT = OUT / "verified"
BUNDLED = ROOT / "docs/research/evidence/dna_future_20261031"


def report(root: Path = DEFAULT) -> dict:
    aggregate = root == DEFAULT and not (root / "study.json").is_file()
    if aggregate:
        root = BUNDLED
    payload = (root / "study.json").read_bytes()
    if hashlib.sha256(payload).hexdigest() != (root / "study.sha256").read_text().strip():
        raise ValueError("Study checksum mismatch")
    result = json.loads(payload)
    if not aggregate and hashlib.sha256((root / "predictions.parquet").read_bytes()).hexdigest() != result["prediction_sha256"]:
        raise ValueError("Prediction checksum mismatch")
    return {**result, "artifact_mode": "aggregate_only" if aggregate else "local_predictions_and_prefixes"}


def summary(root: Path = DEFAULT) -> dict:
    result = report(root)
    catalog = [{"session_key": key, "circuit": value[0]} for key, value in SESSIONS.items() if value[2] == "test"]
    if result["artifact_mode"] == "aggregate_only":
        return {**result, "cases": [], "session_catalog": catalog}
    frame = pd.read_parquet(root / "predictions.parquet")
    cases = frame[frame.split == "test"].copy()
    cases.insert(0, "case_id", cases.index)
    return {**result, "cases": cases.to_dict("records"), "session_catalog": catalog}


def incident(case_id: int, root: Path = DEFAULT) -> dict:
    result = report(root)
    if result["artifact_mode"] == "aggregate_only":
        raise FileNotFoundError("Individual telemetry prefixes remain local; only aggregate metrics are bundled")
    dataset = result["dataset"]
    for name, checksum in dataset["files"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != checksum:
            raise ValueError("Prefix dataset checksum mismatch")
    meta = pd.read_parquet(root / "prefixes_meta.parquet")
    if not 0 <= case_id < len(meta) or meta.iloc[case_id].split != "test":
        raise IndexError("Select a held-out case from this study")
    with np.load(root / "prefixes.npz", allow_pickle=False) as saved:
        x = saved["x"][case_id]
    return {"case_id": case_id, "evidence": "observed OpenF1 prefix, resampled; no future telemetry",
            "seconds": np.linspace(0, dataset["window_seconds"], dataset["grid"]).tolist(),
            "channels": {name: x[index].tolist() for index, name in enumerate(dataset["channels"])},
            "cutoff_seconds": dataset["window_seconds"]}
