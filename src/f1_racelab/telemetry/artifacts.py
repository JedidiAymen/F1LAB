"""Paths for generated, ignored telemetry comparison artifacts."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
COMPARISON_ROOT = PROJECT_ROOT / "data/processed/telemetry_comparisons"
