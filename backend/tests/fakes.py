"""Scriptable fake provider for tests. No network, no httpx."""

from __future__ import annotations

import asyncio

from app.agent.providers.base import LLMProvider, ProviderError, ProviderHealth
from app.agent.types import StreamEvent, ToolCall
from app.core.config import ProviderConfig


def text(*chunks: str) -> list[StreamEvent]:
    return [StreamEvent.text_chunk(c) for c in chunks]


def tool_call(name: str, call_id: str = "call_1", **arguments) -> StreamEvent:
    return StreamEvent.tool(ToolCall(call_id, name, arguments))


class FakeProvider(LLMProvider):
    requires_api_key = False
    adapter_name = "fake"

    def __init__(
        self,
        name: str,
        rounds: list[list[StreamEvent]] | None = None,
        *,
        fail: str | None = None,
        delay: float = 0.0,
        fail_after: int | None = None,
        configured: bool = True,
        health: str = "ok",
        supports_tools: bool = True,
    ):
        super().__init__(ProviderConfig(name=name, adapter="fake", base_url="http://fake", model=f"{name}-model"))
        self.rounds = rounds or [text("Looks ", "good ", "to me.") + [StreamEvent.usage_report(10, 5)]]
        self.fail = fail
        self.delay = delay
        self.fail_after = fail_after
        self._configured = configured
        self._health = health
        self.supports_tools = supports_tools
        self.calls: list[dict] = []

    def is_configured(self) -> bool:
        return self._configured

    async def stream_response(self, messages, *, system=None, tools=None, temperature=0.2):
        self.calls.append({"messages": list(messages), "tools": tools, "system": system})
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise ProviderError(self.name, self.fail)
        script = self.rounds[min(len(self.calls) - 1, len(self.rounds) - 1)]
        for index, event in enumerate(script):
            if self.fail_after is not None and index == self.fail_after:
                raise ProviderError(self.name, "connection reset by peer")
            yield event

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(self._health, "" if self._health == "ok" else "fake says no", 1)


class FakeGateway:
    def __init__(self, responses: dict[str, object] | None = None, fail: Exception | None = None):
        self.responses = responses or {}
        self.fail = fail
        self.requests: list[tuple[str, dict | None]] = []

    async def get(self, path, params=None):
        self.requests.append((path, params))
        if self.fail:
            raise self.fail
        return self.responses[path]
