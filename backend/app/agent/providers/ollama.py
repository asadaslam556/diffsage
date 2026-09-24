"""Ollama, running locally. The default and the safety net."""

from __future__ import annotations

from collections.abc import AsyncIterator

from app.agent.providers._http import iter_ndjson, raise_for_status, timed_get, wrap_transport_error
from app.agent.providers._wire import OllamaStreamParser, ollama_messages, openai_tools
from app.agent.providers.base import LLMProvider, ProviderError, ProviderHealth
from app.agent.providers.registry import register_provider
from app.agent.types import Message, StreamEvent, ToolSpec


@register_provider("ollama")
class OllamaProvider(LLMProvider):
    requires_api_key = False

    async def stream_response(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.2,
    ) -> AsyncIterator[StreamEvent]:
        body = {
            "model": self.model,
            "messages": ollama_messages(messages, system),
            "stream": True,
            "options": {"temperature": temperature},
        }
        if tools:
            body["tools"] = openai_tools(tools)  # same schema as OpenAI's
        parser = OllamaStreamParser()
        try:
            async with self.client.stream("POST", f"{self.config.base_url}/api/chat", json=body) as response:
                await raise_for_status(response, self.name)
                async for chunk in iter_ndjson(response):
                    for event in parser.feed(chunk):
                        yield event
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise wrap_transport_error(self.name, exc) from exc

    async def health_check(self) -> ProviderHealth:
        response, latency, error = await timed_get(self.client, f"{self.config.base_url}/api/tags")
        if response is None:
            return ProviderHealth("down", error, latency)
        if response.status_code >= 400:
            return ProviderHealth("down", f"HTTP {response.status_code}", latency)
        names = {m.get("name", "") for m in response.json().get("models", [])}
        wanted = self.model if ":" in self.model else f"{self.model}:latest"
        if wanted not in names and self.model not in names:
            return ProviderHealth("degraded", f"running, but model '{self.model}' isn't pulled (ollama pull {self.model})", latency)
        return ProviderHealth("ok", "", latency)

    async def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        try:
            response = await self.client.post(
                f"{self.config.base_url}/api/embed",
                json={"model": model or self.config.extra.get("embedding_model", "nomic-embed-text"), "input": texts},
            )
            await raise_for_status(response, self.name)
            vectors = response.json().get("embeddings")
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise wrap_transport_error(self.name, exc) from exc
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise ProviderError(self.name, "embedding response didn't match the input")
        return vectors
