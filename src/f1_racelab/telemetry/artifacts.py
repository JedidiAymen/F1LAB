"""Audited historical comparison selections and generated artifact paths.

Selections identify source laps; they do not certify equal tyres, fuel, weather
or unobstructed running. In particular Monaco has no cached pit endpoint.
"""

from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
COMPARISON_ROOT = PROJECT_ROOT / "data/processed/telemetry_comparisons"


@dataclass(frozen=True)
class ComparisonSpec:
    session_slug: str
    driver_a: int
    lap_a: int
    driver_b: int
    lap_b: int

    @property
    def comparison_id(self) -> str:
        return f"driver-{self.driver_a}-lap-{self.lap_a}-vs-driver-{self.driver_b}-lap-{self.lap_b}"

    @property
    def label(self) -> str:
        return f"#{self.driver_a} L{self.lap_a} vs #{self.driver_b} L{self.lap_b}"

    @property
    def path(self) -> Path:
        return COMPARISON_ROOT / (
            f"{self.session_slug}_driver_{self.driver_a}_lap_{self.lap_a}_"
            f"vs_{self.driver_b}_lap_{self.lap_b}.json")


COMPARISONS = {
    spec.session_slug: spec for spec in (
        ComparisonSpec("monza-2025", 1, 50, 4, 50),
        ComparisonSpec("monaco-2023", 1, 40, 31, 40),
        ComparisonSpec("brazil-2024", 1, 52, 31, 52),
    )
}
