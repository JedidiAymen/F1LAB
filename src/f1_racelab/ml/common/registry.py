"""Checksum-verified model artifacts: fitted object + card, loaded fail-closed."""
from __future__ import annotations

import hashlib
from pathlib import Path

import joblib

from f1_racelab.ml.common.contracts import ModelCard, read_card, write_card


class ArtifactUnavailable(RuntimeError):
    """Raised with a reproduction hint when a model artifact is missing or altered."""


def save_artifact(root: Path, name: str, model: object, card: ModelCard) -> dict:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    model_path = root / f"{name}.joblib"
    joblib.dump(model, model_path, compress=3)
    digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
    card_digest = write_card(card, root / f"{name}.card.json")
    (root / f"{name}.sha256").write_text(f"{digest}\n")
    return {"model_sha256": digest, "card_sha256": card_digest}


def load_artifact(root: Path, name: str, *, reproduce: str) -> tuple[object, ModelCard]:
    root = Path(root)
    model_path, card_path, sha_path = (root / f"{name}.joblib", root / f"{name}.card.json",
                                       root / f"{name}.sha256")
    if not (model_path.is_file() and card_path.is_file() and sha_path.is_file()):
        raise ArtifactUnavailable(f"Model '{name}' is not trained. Run: {reproduce}")
    if hashlib.sha256(model_path.read_bytes()).hexdigest() != sha_path.read_text().strip():
        raise ArtifactUnavailable(f"Model '{name}' failed its SHA-256 check. Retrain: {reproduce}")
    return joblib.load(model_path), read_card(card_path)
