"""Offline builds require cached responses or explicit same-session absence evidence."""

import gzip
import hashlib
import json
from pathlib import Path

import httpx
import pytest

from f1_racelab.data.openf1_qualifying import OpenF1Client
from f1_racelab.session.catalog import DEFAULT_SESSION
from f1_racelab.session.openf1_replay import _prior_optional_absence, build_replay_pack


def test_offline_client_reads_cache_and_never_requests_missing_resource(tmp_path, monkeypatch):
    resource = "drivers?session_key=9912"
    key = hashlib.sha256(resource.encode()).hexdigest()[:20]
    destination = tmp_path / "drivers" / f"{key}.json"
    destination.parent.mkdir()
    destination.write_text('[{"driver_number":1}]')
    def forbidden(*args, **kwargs):
        pytest.fail("Offline client attempted HTTP")
    monkeypatch.setattr(httpx.Client, "get", forbidden)
    with OpenF1Client(tmp_path, offline=True) as client:
        assert client.get("drivers", session_key=9912) == [{"driver_number": 1}]
        assert client.hashes[resource] == hashlib.sha256(destination.read_bytes()).hexdigest()
        with pytest.raises(FileNotFoundError, match="Offline OpenF1 resource is not cached"):
            client.get("location", session_key=9912, driver_number=1)


def _manifest() -> dict:
    spec = DEFAULT_SESSION
    return {"session": {"season": spec.season, "round": spec.round, "kind": "race",
                        "provider_key": f"openf1:{spec.session_key}"},
            "coverage": {"unavailable_resources": {
                "pit": "HTTP 404: provider resource unavailable",
                "weather": "download failed", "laps": "HTTP 404: provider resource unavailable",
            }}}


def test_only_optional_explicit_404_is_reused_from_matching_session(tmp_path: Path) -> None:
    output = tmp_path / "pack.json.gz"
    path = output.with_suffix(".manifest.json")
    path.write_text(json.dumps(_manifest()))
    absence, checksum = _prior_optional_absence(output, DEFAULT_SESSION)
    assert absence == {"pit": "HTTP 404: provider resource unavailable"}
    assert checksum == hashlib.sha256(path.read_bytes()).hexdigest()
    output = tmp_path / "unknown.json.gz"
    assert _prior_optional_absence(output, DEFAULT_SESSION) == ({}, None)


def test_foreign_session_absence_cannot_be_reused(tmp_path: Path) -> None:
    output = tmp_path / "pack.json.gz"
    manifest = _manifest()
    manifest["session"]["provider_key"] = "openf1:9094"
    output.with_suffix(".manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="different session"):
        _prior_optional_absence(output, DEFAULT_SESSION)


def test_legacy_absence_requires_verified_pack_hash_and_matching_session(tmp_path: Path) -> None:
    output = tmp_path / "pack.json.gz"
    manifest = _manifest()
    session = manifest.pop("session")
    with gzip.open(output, "wt") as handle:
        json.dump({"session": session}, handle)
    manifest["sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".manifest.json").write_text(json.dumps(manifest))
    assert _prior_optional_absence(output, DEFAULT_SESSION)[0] == {
        "pit": "HTTP 404: provider resource unavailable",
    }
    output.write_bytes(b"changed")
    with pytest.raises(ValueError, match="cannot be bound"):
        _prior_optional_absence(output, DEFAULT_SESSION)


def test_offline_build_does_not_treat_uncached_optional_endpoint_as_unavailable(
    tmp_path: Path, monkeypatch,
) -> None:
    def cached(self, endpoint, **params):
        assert self.offline
        if endpoint == "sessions":
            spec = DEFAULT_SESSION
            return [{"meeting_key": spec.meeting_key, "date_start": spec.clock_origin.isoformat(),
                     "year": spec.season, "session_name": "Race"}]
        if endpoint == "pit":
            raise FileNotFoundError("uncached optional endpoint")
        return []
    monkeypatch.setattr(OpenF1Client, "get", cached)
    with pytest.raises(FileNotFoundError, match="uncached optional"):
        build_replay_pack(tmp_path / "pack.json.gz", offline=True)
