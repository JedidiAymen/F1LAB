"""Operational contracts use isolated apps and synthetic/missing artifacts."""
from fastapi.testclient import TestClient

from f1_racelab.api import create_app


def test_liveness_and_readiness_do_not_require_data(tmp_path):
    app = create_app(pack_paths={slug: tmp_path / slug for slug in
                                ("monza-2025", "monaco-2023", "brazil-2024")})
    with TestClient(app) as client:
        assert client.get("/healthz").json()["status"] == "ok"
        ready = client.get("/api/v1/readiness").json()
        assert ready["artifact_check"] == "presence_only"
        assert not any(ready["replay_packs"].values())
        response = client.get("/api/v1/replay/monza-2025/state?seconds=0",
                              headers={"X-Request-ID": "incident_42"})
        assert response.status_code == 503
        assert response.headers["x-request-id"] == "incident_42"
        text = client.get("/metrics").text
        assert 'route="/api/v1/replay/{slug}/state",status="503"} 1.0' in text
        assert 'route="/api/v1/readiness"' in text
        assert "incident_42" not in text and "monza-2025" not in text and "seconds=0" not in text


def test_unmatched_paths_and_methods_have_bounded_labels():
    with TestClient(create_app()) as client:
        response = client.request("SOMETHING", "/unknown-123", headers={"X-Request-ID": "bad value"})
        assert len(response.headers["x-request-id"]) == 32
        client.get("/unknown-456")
        text = client.get("/metrics").text
        assert 'method="OTHER",route="unmatched"' in text
        assert "unknown-123" not in text and "unknown-456" not in text
    with TestClient(create_app()) as client:
        assert "f1lab_http_requests_total{" not in client.get("/metrics").text


def test_lifespan_stops_background_sessions(monkeypatch):
    calls = []

    async def stop_all():
        calls.append("stopped")

    monkeypatch.setattr("f1_racelab.api.live_registry.stop_all", stop_all)
    with TestClient(create_app()):
        assert calls == []
    assert calls == ["stopped"]
