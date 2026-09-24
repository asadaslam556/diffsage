"""Claude via the Anthropic Messages API. Raw HTTP, no SDK, so it streams
through the same code path as everything else."""

from __future__ import annotations

from collections.abc import AsyncIterator

from app.agent.providers._http import iter_sse_data, raise_for_status, timed_get, health_from_response, wrap_transport_error
from app.agent.providers._wire import AnthropicStreamParser, anthropic_messages, anthropic_tools
from app.agent.providers.base import LLMProvider, ProviderError, ProviderHealth
from app.agent.providers.registry import register_provider
from app.agent.types import Message, StreamEvent, ToolSpec

API_VERSION = "2023-06-01"


@register_provider("anthropic")
class AnthropicProvider(LLMProvider):
    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.config.api_key or "",
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        }

    async def stream_response(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.2,
    ) -> AsyncIterator[StreamEvent]:
        # no temperature: current Claude models reject it with a 400
        body = {
            "model": self.model,
            "max_tokens": self.config.max_tokens,
            "messages": anthropic_messages(messages),
            "stream": True,
        }
        if system:
            body["system"] = system
        if tools:
            body["tools"] = anthropic_tools(tools)
        parser = AnthropicStreamParser()
        try:
            async with self.client.stream("POST", f"{self.config.base_url}/v1/messages", json=body, headers=self._headers()) as response:
                await raise_for_status(response, self.name)
                async for data in iter_sse_data(response):
                    for event in parser.feed(data):
                        yield event
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise wrap_transport_error(self.name, exc) from exc

    async def health_check(self) -> ProviderHealth:
        if not self.is_configured():
            return ProviderHealth("not_configured", "ANTHROPIC_API_KEY isn't set")
        # listing models is free and proves both reachability and the key
        response, latency, error = await timed_get(self.client, f"{self.config.base_url}/v1/models", headers=self._headers())
        return health_from_response(response, latency, error)
