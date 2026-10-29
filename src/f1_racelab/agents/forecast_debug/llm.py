"""Chat-model clients for the forecast-debugging agent.

The agent speaks a plain JSON protocol (one JSON object per reply) instead of a provider-specific tool-calling
API, so any local model served by Ollama can drive it, and tests can replay a fixed script.
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any, Protocol

Message = dict[str, str]
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class ChatModel(Protocol):
    name: str

    def complete(self, messages: list[Message]) -> str: ...


def extract_json(text: str) -> dict[str, Any] | None:
    """Return the first top-level JSON object in ``text`` (ignoring <think> blocks and code fences), else None."""
    cleaned = _THINK.sub("", text)
    start = cleaned.find("{")
    while start != -1:
        depth, in_string, escaped = 0, False, False
        for i in range(start, len(cleaned)):
            ch = cleaned[i]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
            elif ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        value = json.loads(cleaned[start:i + 1])
                    except json.JSONDecodeError:
                        break
                    return value if isinstance(value, dict) else None
        start = cleaned.find("{", start + 1)
    return None


class OllamaChat:
    """A model served by a local Ollama instance (``ollama pull qwen3:8b``)."""

    def __init__(self, model: str = "qwen3:8b", host: str = "http://localhost:11434", temperature: float = 0.0,
                 num_ctx: int = 16384, timeout: float = 300.0) -> None:
        self.name = f"ollama:{model}"
        self._model, self._url = model, host.rstrip("/") + "/api/chat"
        self._options = {"temperature": temperature, "num_ctx": num_ctx}
        self._timeout = timeout

    def complete(self, messages: list[Message]) -> str:
        import httpx

        response = httpx.post(self._url, timeout=self._timeout, json={
            "model": self._model, "messages": messages, "stream": False, "format": "json", "options": self._options})
        response.raise_for_status()
        return str(response.json()["message"]["content"])


class ScriptedChat:
    """Replays fixed replies; used by tests and to exercise the harness without a model."""

    def __init__(self, replies: Iterable[str | dict[str, Any]], name: str = "scripted") -> None:
        self.name = name
        self._replies = [r if isinstance(r, str) else json.dumps(r) for r in replies]
        self.seen: list[list[Message]] = []

    def complete(self, messages: list[Message]) -> str:
        self.seen.append(list(messages))
        if not self._replies:
            return "{}"
        return self._replies.pop(0)
