"""The one interface every model provider implements.

To add a provider: drop a module in this package, subclass LLMProvider,
decorate it with @register_provider("name"), and add a [providers.name]
table to settings.toml. Nothing else in the codebase needs to change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.agent.types import ChatResult, Message, StreamEvent, ToolSpec, Usage
from app.core.config import ProviderConfig

if TYPE_CHECKING:  # httpx isn't needed to import this module
    import httpx


class ProviderError(Exception):
    """Something went wrong talking to a provider. Always carries the provider name."""

    def __init__(self, provider: str, message: str, *, status_code: int | None = None):
        super().__init__(f"{provider}: {message}")
        self.provider = provider
        self.message = message
        self.status_code = status_code


class ProviderNotConfigured(ProviderError):
    pass


class EmbeddingsNotSupported(ProviderError):
    pass


@dataclass
class ProviderHealth:
    status: str  # "ok" | "degraded" | "down" | "not_configured"
    detail: str = ""
    latency_ms: int | None = None


class LLMProvider(ABC):
    #: set by @register_provider
    adapter_name: str = ""
    requires_api_key: bool = True
    supports_tools: bool = True

    def __init__(self, config: ProviderConfig, client: "httpx.AsyncClient | None" = None):
        self.config = config
        self.name = config.name
        self.model = config.model
        self._client = client

    # --- things subclasses must do ---------------------------------------

    @abstractmethod
    def stream_response(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.2,
    ) -> AsyncIterator[StreamEvent]:
        """Yield text chunks as they arrive, then any tool calls, then usage.

        Raise ProviderError for anything that went wrong. Don't swallow it,
        the router needs to see it to decide on fallback.
        """

    @abstractmethod
    async def health_check(self) -> ProviderHealth:
        """Cheap liveness probe. Must not spend tokens."""

    # --- shared behaviour -------------------------------------------------

    def is_configured(self) -> bool:
        if not self.config.enabled or not self.config.base_url or not self.config.model:
            return False
        return bool(self.config.api_key) or not self.requires_api_key

    async def send_message(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.2,
    ) -> ChatResult:
        """Non-streaming convenience. Just drains stream_response."""
        text: list[str] = []
        calls = []
        usage = Usage()
        async for event in self.stream_response(messages, system=system, tools=tools, temperature=temperature):
            if event.type == "text":
                text.append(event.text)
            elif event.type == "tool_call" and event.tool_call:
                calls.append(event.tool_call)
            elif event.type == "usage" and event.usage:
                usage = usage + event.usage
        return ChatResult("".join(text), calls, usage, self.name, self.model)

    async def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        raise EmbeddingsNotSupported(self.name, "this provider doesn't do embeddings here")

    @property
    def client(self) -> "httpx.AsyncClient":
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.timeout_seconds, connect=5.0)
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "adapter": self.adapter_name,
            "model": self.model,
            "configured": self.is_configured(),
            "supports_tools": self.supports_tools,
        }
