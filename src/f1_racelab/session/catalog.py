"""Explicit, audited historical sessions supported by the replay builder."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

PACK_ROOT = Path(__file__).resolve().parents[3] / "data/processed/replay_packs"


@dataclass(frozen=True)
class ReplaySpec:
    slug: str
    season: int
    round: int
    session_key: int
    meeting_key: int
    clock_origin: datetime
    title: str
    circuit: str
    scheduled_laps: int
    display_name: str

    @property
    def pack_path(self) -> Path:
        return PACK_ROOT / f"{self.slug.replace('-', '_')}_race.json.gz"


SESSIONS = {
    spec.slug: spec for spec in (
        ReplaySpec("monza-2025", 2025, 16, 9912, 1268,
                   datetime(2025, 9, 7, 13, tzinfo=UTC),
                   "2025 Italian Grand Prix", "Autodromo Nazionale Monza", 53, "Monza"),
        ReplaySpec("monaco-2023", 2023, 6, 9094, 1210,
                   datetime(2023, 5, 28, 13, tzinfo=UTC),
                   "2023 Monaco Grand Prix", "Circuit de Monaco", 78, "Monaco"),
        ReplaySpec("brazil-2024", 2024, 21, 9636, 1249,
                   datetime(2024, 11, 3, 15, 30, tzinfo=UTC),
                   "2024 São Paulo Grand Prix", "Autódromo José Carlos Pace", 71, "São Paulo"),
    )
}
DEFAULT_SESSION = SESSIONS["monza-2025"]
