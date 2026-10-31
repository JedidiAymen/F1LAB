"""Per-process HTTP telemetry with bounded labels and no request-body logging.

Durations use monotonic seconds. Labels are registered route templates rather
than URLs, driver IDs or query strings. One Uvicorn process owns one registry;
replicas are scraped separately. WebSocket frames are not HTTP requests.
"""
from __future__ import annotations

import logging
import re
import time
import uuid

from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest
from starlette.types import ASGIApp, Message, Receive, Scope, Send

LOGGER = logging.getLogger("f1lab.operations")
_REQUEST_ID = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


class HttpTelemetry:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.requests = Counter("f1lab_http_requests", "Completed HTTP requests",
                                ["method", "route", "status"], registry=self.registry)
        self.duration = Histogram("f1lab_http_request_duration_seconds", "HTTP response latency in seconds",
                                  ["method", "route"], registry=self.registry,
                                  buckets=(0.005, 0.025, 0.1, 0.5, 1, 5, 15, 60))

    def render(self) -> bytes:
        return generate_latest(self.registry)


class RequestTelemetryMiddleware:
    def __init__(self, app: ASGIApp, telemetry: HttpTelemetry) -> None:
        self.app, self.telemetry = app, telemetry

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        incoming = dict(scope.get("headers", [])).get(b"x-request-id", b"").decode("ascii", errors="ignore")
        request_id = incoming if _REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex
        status = 500

        async def traced_send(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"] = list(message.get("headers", [])) + [(b"x-request-id", request_id.encode())]
            await send(message)

        try:
            await self.app(scope, receive, traced_send)
        except Exception:
            # No exception text: model paths, SQL and payloads may be sensitive.
            LOGGER.error("request_failed request_id=%s", request_id)
            raise
        finally:
            route = getattr(scope.get("route"), "path", "unmatched")
            method = scope["method"] if scope["method"] in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"} else "OTHER"
            seconds = time.perf_counter() - started
            # Avoid monitoring traffic dominating the application histograms.
            if route not in {"/metrics", "/healthz"}:
                self.telemetry.requests.labels(method, route, str(status)).inc()
                self.telemetry.duration.labels(method, route).observe(seconds)
            if status >= 500:
                LOGGER.warning("request_unavailable request_id=%s route=%s status=%d seconds=%.6f",
                               request_id, route, status, seconds)
