"""A read-only API must not initialise the ingestion cache at import time."""
import importlib
from unittest.mock import Mock

from f1_racelab.data import fastf1_source


def test_cache_is_created_only_when_loading_a_provider_session(tmp_path, monkeypatch):
    cache = tmp_path / "provider-cache"
    monkeypatch.setenv("FASTF1_CACHE_DIR", str(cache))
    enable = Mock()
    session = Mock()
    monkeypatch.setattr(fastf1_source.fastf1.Cache, "enable_cache", enable)
    monkeypatch.setattr(fastf1_source.fastf1, "get_session", Mock(return_value=session))
    importlib.reload(fastf1_source)
    try:
        assert not cache.exists()
        enable.assert_not_called()
        assert fastf1_source.load_session(2025, "Italy", "FP3") is session
        assert cache.is_dir()
        enable.assert_called_once_with(str(cache))
        session.load.assert_called_once_with(telemetry=False, weather=False, messages=False)
    finally:
        monkeypatch.delenv("FASTF1_CACHE_DIR")
        importlib.reload(fastf1_source)
