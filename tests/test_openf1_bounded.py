"""Bound decoded payloads without weakening caching, retries or offline behavior."""
import gzip

import httpx
import pytest

from f1_racelab.data.openf1_qualifying import OpenF1Client


def client_with(tmp_path, handler, budget):
    client = OpenF1Client(tmp_path, interval=0, max_response_bytes=budget)
    client._http.close()
    client._http = httpx.Client(transport=httpx.MockTransport(handler))
    client._sleep = lambda seconds: None
    return client


def test_bounded_stream_caches_exact_payload_and_can_replay_offline(tmp_path):
    payload = b'[{"speed":123}]'
    with client_with(tmp_path, lambda req: httpx.Response(200, content=payload), len(payload)) as client:
        assert client.get("car_data", session_key=1) == [{"speed": 123}]
    with OpenF1Client(tmp_path, offline=True, max_response_bytes=len(payload)) as client:
        assert client.get("car_data", session_key=1) == [{"speed": 123}]
    with (OpenF1Client(tmp_path, offline=True, max_response_bytes=1) as client,
          pytest.raises(ValueError, match="Cached.*budget")):
        client.get("car_data", session_key=1)


def test_oversized_decoded_payload_aborts_without_retry_or_partial_cache(tmp_path):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, content=gzip.compress(b'[{"large":"' + b'x' * 1000 + b'"}]'),
                              headers={"Content-Encoding": "gzip"})
    with client_with(tmp_path, handler, 100) as client, pytest.raises(ValueError, match="budget"):
        client.get("car_data", session_key=1)
    assert len(requests) == 1 and not list(tmp_path.rglob("*.json"))


def test_streamed_retry_preserves_retry_after_and_http_failure(tmp_path):
    replies = iter([httpx.Response(429, headers={"Retry-After": "1"}), httpx.Response(200, json=[])])
    with client_with(tmp_path, lambda req: next(replies), 100) as client:
        waits = []
        client._sleep = waits.append
        assert client.get("car_data", session_key=1) == []
        assert 1.0 in waits
    with (client_with(tmp_path, lambda req: httpx.Response(403), 100) as client,
          pytest.raises(httpx.HTTPStatusError)):
        client.get("car_data", session_key=2)
