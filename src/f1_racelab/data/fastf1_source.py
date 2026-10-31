import os
from pathlib import Path

import fastf1

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR = Path(os.environ.get("FASTF1_CACHE_DIR", PROJECT_ROOT / "data" / "cache" / "fastf1"))


def load_session(
    year: int,
    event: str | int,
    session_code: str,
    *,
    telemetry: bool = False,
):
    """
    Load one F1 session through FastF1.

    Examples
    --------
    load_session(2025, "Italy", "FP3")
    load_session(2025, "Italy", "Q")
    """
    # Read-only API imports must not create a cache or initialise an ingester.
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(CACHE_DIR))
    session = fastf1.get_session(year, event, session_code)

    session.load(
        telemetry=telemetry,
        weather=False,
        messages=False,
    )

    return session
