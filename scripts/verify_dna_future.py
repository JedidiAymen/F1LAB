"""Independent saved-model inference/metric check; requires local real artifacts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from f1_racelab.ml.driver_dna.future_data import OUT


def verify(root: Path = OUT / "verified") -> dict:
    import torch

    from f1_racelab.ml.driver_dna.future_nets import RemainingLapNet

    payload = (root / "study.json").read_bytes()
    if hashlib.sha256(payload).hexdigest() != (root / "study.sha256").read_text().strip():
        raise ValueError("Study checksum mismatch; refusing artifact deserialization")
    study = json.loads(payload)
    for filename, expected in study["artifacts_sha256"].items():
        if Path(filename).name != filename:
            raise ValueError("Artifact manifest must contain local filenames")
        if hashlib.sha256((root / "models" / filename).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Artifact checksum mismatch: {filename}")
    frame = pd.read_parquet(root / "predictions.parquet")
    test = frame[frame.split == "test"]
    selected = test.sample(n=min(8, len(test)), random_state=42).index.to_numpy()
    x = np.load(root / "prefixes.npz", allow_pickle=False)["x"][selected]
    ctx = frame.loc[selected, ["last_lap_seconds", "recent_three_seconds", "lap_number"]].to_numpy(np.float32)
    features = np.column_stack([ctx, x.mean(-1), x.std(-1),
                               (np.diff((x[:, 2] > 20).astype(int), axis=1) == 1).sum(1),
                               (np.diff(x[:, 3], axis=1) != 0).sum(1),
                               (np.abs(np.diff(x[:, 1], axis=1)) > 20).sum(1)]).astype(np.float32)
    base = np.maximum(frame.loc[selected, "last_lap_seconds"].to_numpy() - 20, 0)
    normalization = np.load(root / "models/preprocessing.npz", allow_pickle=False)
    xn = ((x - normalization["x_mean"]) / normalization["x_scale"]).astype(np.float32)
    cn = ((ctx - normalization["context_mean"]) / normalization["context_scale"]).astype(np.float32)
    torch.set_num_threads(2)
    checked = {}
    for row in study["results"]:
        name = row["model"]
        error = test[name] - test.remaining_seconds
        actual = {"mae_s": error.abs().mean(), "median_ae_s": error.abs().median(),
                  "rmse_s": np.sqrt((error**2).mean()), "bias_s": error.mean()}
        for metric, value in actual.items():
            np.testing.assert_allclose(value, row["test"][metric], atol=1e-10)
        if name.startswith("tcn_"):
            model = RemainingLapNet(context="no_context" not in name)
            model.load_state_dict(torch.load(root / "models" / f"{name}.pt", weights_only=True))
            model.eval()
            with torch.no_grad():
                residual = model(torch.from_numpy(xn), torch.from_numpy(cn)).numpy()
            predicted = np.maximum(base + residual * normalization["target_scale"] + normalization["target_mean"], 0)
        elif name in {"context_ridge", "prefix_ridge", "prefix_lightgbm"}:
            model = joblib.load(root / "models" / f"{name}.joblib")
            predicted = np.maximum(base + model.predict(ctx if name == "context_ridge" else features), 0)
        else:
            continue
        expected = frame.loc[selected, name].to_numpy()
        np.testing.assert_allclose(predicted, expected, rtol=0, atol=0.001)
        checked[name] = {"points": len(selected), "max_reloaded_difference_s": float(np.abs(predicted - expected).max())}
    return {"evidence": "real saved model reload; independent pandas metric recomputation",
            "verified_artifact_files": len(study["artifacts_sha256"]), "metric_models": len(study["results"]), "test_rows": len(test), "models": checked}


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
