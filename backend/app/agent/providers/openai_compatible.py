"""Anything that speaks the OpenAI chat completions API.

OpenAI and DeepSeek are thin subclasses. For Groq, Together, LM Studio,
vLLM and friends you don't even need a subclass; add a settings table with
adapter = "openai_compatible" and set <NAME>_API_KEY.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from app.agent.providers._http import health_from_response, iter_sse_data, raise_for_status, timed_get, wrap_transport_error
from app.agent.providers._wire import OpenAIStreamParser, openai_messages, openai_tools
from app.agent.providers.base import LLMProvider, ProviderError, ProviderHealth
from app.agent.providers.registry import register_provider
from app.agent.types import Message, StreamEvent, ToolSpec


@register_provider("openai_compatible")
class OpenAICompatibleProvider(LLMProvider):
    def _headers(self) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        if self.config.api_key:
            headers["authorization"] = f"Bearer {self.config.api_key}"
        return headers

    def _body(self, messages: list[Message], system: str | None, tools: list[ToolSpec] | None, temperature: float) -> dict:
        body = {
            "model": self.model,
            "messages": openai_messages(messages, system),
            "stream": True,
            "stream_options": {"include_usage": True},
            "temperature": temperature,
            "max_tokens": self.config.max_tokens,
        }
        if tools:
            body["tools"] = openai_tools(tools)
        return body

    async def stream_response(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.2,
    ) -> AsyncIterator[StreamEvent]:
        parser = OpenAIStreamParser()
        body = self._body(messages, system, tools, temperature)
        try:
            async with self.client.stream("POST", f"{self.config.base_url}/chat/completions", json=body, headers=self._headers()) as response:
                await raise_for_status(response, self.name)
                async for chunk in iter_sse_data(response):
                    try:
                        events = parser.feed(chunk)
                    except ProviderError as exc:
                        raise ProviderError(self.name, exc.message) from exc
                    for event in events:
                        yield event
            for event in parser.finish():
                yield event
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise wrap_transport_error(self.name, exc) from exc

    async def health_check(self) -> ProviderHealth:
        if not self.is_configured():
            return ProviderHealth("not_configured", f"{self.name.upper()}_API_KEY isn't set")
        response, latency, error = await timed_get(self.client, f"{self.config.base_url}/models", headers=self._headers())
        return health_from_response(response, latency, error)
