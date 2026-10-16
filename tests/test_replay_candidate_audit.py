"""Synthetic provider fixtures verify audit semantics and missing resources."""

import httpx

from f1_racelab.session.audit_candidates import (
    TABLES,
    Candidate,
    audit_candidate,
)


class FixtureClient:
    def __init__(self) -> None:
        self.hashes: dict[str, str] = {}

    def get(self, endpoint: str, **params: int | str) -> list[dict]:
        if endpoint == "sessions":
            return [{"session_key": 42, "meeting_key": 9,
                     "session_name": "Race", "date_start": "2024-01-01T00:00:00Z"}]
        if endpoint == "pit":
            request = httpx.Request("GET", "https://api.openf1.org/v1/pit")
            response = httpx.Response(404, request=request)
            raise httpx.HTTPStatusError("missing", request=request, response=response)
        self.hashes[f"{endpoint}?session_key=42"] = endpoint
        if endpoint == "drivers":
            return [{"session_key": 42, "driver_number": 1}]
        if endpoint == "race_control":
            return [{"session_key": 42, "category": "SafetyCar",
                     "message": "VIRTUAL SAFETY CAR DEPLOYED",
                     "date": "2024-01-01T01:00:00Z"}]
        if endpoint == "weather":
            return [{"session_key": 42, "rainfall": 1}]
        if endpoint == "stints":
            return [{"session_key": 42, "compound": "INTERMEDIATE"}]
        return []


def test_audit_preserves_unavailable_versus_empty_resources() -> None:
    result = audit_candidate(FixtureClient(), Candidate(2024, "Brazil"))  # type: ignore[arg-type]
    assert result["resource_rows"]["pit"] is None
    assert result["resource_rows"]["position"] == 0
    assert result["resource_rows"].keys() == set(TABLES)
    assert result["rainfall_records"] == {"1": 1}
    assert result["critical_control"][0]["message"] == "VIRTUAL SAFETY CAR DEPLOYED"
    assert "pit" not in result["source_sha256"]
