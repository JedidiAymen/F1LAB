"""Check the production HTTP boundary; optionally require local real replay packs.

No provider calls, writes, synthetic telemetry or model-quality claims. This
also works against any running instance with the same API contract.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence
from pathlib import Path

import httpx


def smoke(base_url: str, *, require_data: bool = False, require_model: bool = False) -> dict:
    with httpx.Client(base_url=base_url.rstrip("/"), timeout=30) as client:
        response = client.get("/")
        response.raise_for_status()
        assert '<div id="root">' in response.text
        response = client.get("/research/incident/replay")
        response.raise_for_status()
        assert '<div id="root">' in response.text  # SPA navigation fallback
        response = client.get("/api/v1/readiness", headers={"X-Request-ID": "compose-smoke"})
        response.raise_for_status()
        assert response.headers["x-request-id"] == "compose-smoke"
        ready = response.json()
        assert ready["artifact_check"] == "presence_only"
        assert client.get("/api/v1/not-a-route").status_code == 404
        paired = client.get("/api/v1/research/agent-paired")
        paired.raise_for_status()
        assert len(paired.json()["cases"]) == 32
        assert "synthetic" in paired.json()["evidence"]
        sessions = client.get("/api/v1/replays").json()
        assert len(sessions) == 3
        checked = []
        for session in sessions:
            slug = session["slug"]
            if require_data:
                assert session["available"], f"Missing real replay {slug}"
            if session["available"]:
                response = client.get(f"/api/v1/replay/{slug}/state", params={"seconds": 0})
                response.raise_for_status()
                assert response.json()["session_time_seconds"] == 0
                checked.append(slug)
        result = {"status": "passed", "real_replays_checked": checked, "readiness": ready}
        if require_model:
            import pandas as pd

            from f1_racelab.ml.pace.inference import PaceFeatures

            frame = pd.read_parquet(Path("data/processed/race_pace/pace_frame.parquet"))
            row = frame.dropna(subset=list(PaceFeatures.model_fields)).iloc[0]
            payload = PaceFeatures.model_validate({key: row[key] for key in PaceFeatures.model_fields})
            health = client.get("/api/v1/pace/health")
            health.raise_for_status()
            forecast = client.post("/api/v1/pace/predict", json=payload.model_dump(mode="json"))
            forecast.raise_for_status()
            result["real_model_inference"] = forecast.json()
        if require_data:
            async def socket_probe() -> str:
                from websockets.asyncio.client import connect

                url = base_url.rstrip("/").replace("http://", "ws://").replace("https://", "wss://")
                async with connect(f"{url}/ws/live/monza-2025", open_timeout=10) as socket:
                    snapshot = json.loads(await asyncio.wait_for(socket.recv(), timeout=20))
                    assert snapshot["badge"] == "SIMULATED LIVE" and snapshot["type"] == "snapshot"
                    return snapshot["badge"]

            result["websocket_proxy"] = asyncio.run(socket_probe())
        return result


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--require-data", action="store_true")
    parser.add_argument("--require-model", action="store_true")
    args = parser.parse_args(argv)
    print(json.dumps(smoke(args.base_url, require_data=args.require_data, require_model=args.require_model), indent=2))


if __name__ == "__main__":
    main()
