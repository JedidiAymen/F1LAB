"""Typed, versioned records shared by every F1LAB ML module.

``ModelCard`` is the model artifact contract: what was predicted, from which
data, under which split, with which settings and what it measured. Cards are
JSON, schema-versioned and content-hashed so a served model can be traced to
the exact training run.
"""
from __future__ import annotations

import hashlib
import json
import platform
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

CARD_SCHEMA_VERSION = 1
EvidenceKind = Literal["real", "synthetic", "mixed"]


class FeatureSpec(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    unit: str
    available_at: str = Field(description="When the value is known relative to the forecast cutoff")


class SplitSpec(BaseModel):
    policy: str
    train_groups: int
    validation_groups: int = 0
    test_groups: int
    group_key: str
    notes: str = ""


class ModelCard(BaseModel):
    schema_version: int = CARD_SCHEMA_VERSION
    model_id: str
    version: str
    task: str
    target: str
    evidence: EvidenceKind = "real"
    dataset_fingerprint: str
    dataset_rows: int
    features: list[FeatureSpec]
    split: SplitSpec
    hyperparameters: dict
    seed: int
    metrics: dict
    runtime: dict = Field(default_factory=dict)
    dependencies: dict[str, str]
    data_license: str
    data_provenance: str
    limitations: list[str]
    intended_use: str
    created_at_utc: str


def fingerprint_frame(frame: pd.DataFrame) -> str:
    """Order-insensitive-by-row but column-sensitive SHA-256 of a table's values."""
    ordered = frame.reindex(sorted(frame.columns), axis=1)
    hashed = pd.util.hash_pandas_object(ordered.reset_index(drop=True), index=False).to_numpy()
    digest = hashlib.sha256()
    digest.update(json.dumps(list(ordered.columns)).encode())
    digest.update(hashed.tobytes())
    return digest.hexdigest()


def dependency_versions(*packages: str) -> dict[str, str]:
    out = {"python": platform.python_version()}
    for name in packages:
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = "not-installed"
    return out


def now_utc() -> str:
    return datetime.now(UTC).isoformat()


def write_card(card: ModelCard, path: Path) -> str:
    """Write a card and return the SHA-256 of its canonical JSON."""
    payload = json.dumps(card.model_dump(mode="json"), indent=2, sort_keys=True)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(payload)
    return hashlib.sha256(payload.encode()).hexdigest()


def read_card(path: Path) -> ModelCard:
    card = ModelCard.model_validate_json(Path(path).read_text())
    if card.schema_version != CARD_SCHEMA_VERSION:
        raise ValueError(f"Unsupported model card schema {card.schema_version}")
    return card
