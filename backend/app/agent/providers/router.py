"""Picks a provider for a request and falls back when it fails.

The rule is simple: try the requested provider, and if it errors or doesn't
produce anything within first_token_timeout, switch to the next fallback
(Ollama by default; can be a list like deepseek,ollama) and tell the client
we did. Fallbacks the user's plan doesn't include are skipped. Once tokens have started
flowing we don't switch. Splicing half an answer from one model onto
another reads terribly, so a mid-stream failure is surfaced as an error.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable, Sequence

from app.agent.providers.base import LLMProvider, ProviderError, ProviderNotConfigured
from app.agent.types import Message, StreamEvent, ToolSpec

log = logging.getLogger(__name__)


class AllProvidersFailed(Exception):
    def __init__(self, attempts: list[tuple[str, str]]):
        self.attempts = attempts
        summary = "; ".join(f"{name}: {reason}" for name, reason in attempts)
        super().__init__(f"no provider could handle the request ({summary})")


class StreamInterrupted(Exception):
    def __init__(self, provider: str, reason: str):
        self.provider = provider
        self.reason = reason
        super().__init__(f"{provider} failed mid-stream: {reason}")


class ProviderRouter:
    def __init__(
        self,
        providers: dict[str, LLMProvider],
        *,
        default: str,
        fallback: str | Sequence[str],
        first_token_timeout: float = 25.0,
    ):
        self.providers = providers
        self.default = default
        self.fallbacks = (fallback,) if isinstance(fallback, str) else tuple(fallback)
        self.first_token_timeout = first_token_timeout

    def chain_for(self, preferred: str | None, allow: Callable[[str], bool] | None = None) -> list[str]:
        # the primary was already checked against the plan by pick_provider
        chain = [preferred or self.default]
        for name in self.fallbacks:
            if name not in chain and (allow is None or allow(name)):
                chain.append(name)
        return chain

    def configured_names(self) -> list[str]:
        return [name for name, p in self.providers.items() if p.is_configured()]

    def _provider(self, name: str) -> LLMProvider:
        provider = self.providers.get(name)
        if provider is None:
            raise ProviderNotConfigured(name, "unknown provider")
        if not provider.is_configured():
            hint = f" (set {name.upper()}_API_KEY)" if provider.requires_api_key else ""
            raise ProviderNotConfigured(name, f"not configured{hint}")
        return provider

    async def stream(
        self,
        messages: list[Message],
        *,
        preferred: str | None = None,
        system: str | None = None,
        tools: list[ToolSpec] | None = None,
        allow: Callable[[str], bool] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        chain = self.chain_for(preferred, allow)
        attempts: list[tuple[str, str]] = []

        for position, name in enumerate(chain):
            is_last = position == len(chain) - 1
            try:
                provider = self._provider(name)
                use_tools = tools if provider.supports_tools else None
                events = provider.stream_response(messages, system=system, tools=use_tools)
                # The last provider in the chain has nobody to hand over to, so cutting it off
                # early only turns "slow" into "failed". A cold 7B model on a CPU can easily take
                # longer than the cutoff to load. It still has its own request timeout.
                first = await self._first_event(events, name, None if is_last else self.first_token_timeout)
            except Exception as exc:  # noqa: BLE001 - ProviderError, TimeoutError and surprises all mean "try the next one"
                reason = _describe(exc)
                attempts.append((name, reason))
                if isinstance(exc, ProviderNotConfigured):
                    log.info("skipping %s: %s", name, reason)
                else:
                    expected = isinstance(exc, (ProviderError, asyncio.TimeoutError))
                    log.warning("provider %s failed before first token: %s", name, reason, exc_info=not expected)
                if is_last:
                    raise AllProvidersFailed(attempts) from exc
                yield StreamEvent("fallback", data={"from": name, "to": chain[position + 1], "reason": reason})
                continue

            yield StreamEvent("meta", data={"provider": name, "model": provider.model})
            if first is not None:
                yield first
                try:
                    async for event in events:
                        yield event
                except (ProviderError, Exception) as exc:  # noqa: BLE001
                    log.error("provider %s died mid-stream: %s", name, _describe(exc))
                    raise StreamInterrupted(name, _describe(exc)) from exc
            return

    async def _first_event(self, events: AsyncIterator[StreamEvent], name: str, timeout: float | None) -> StreamEvent | None:
        try:
            return await asyncio.wait_for(events.__anext__(), timeout=timeout)
        except StopAsyncIteration:
            return None  # empty reply, odd but not an error
        except asyncio.TimeoutError as exc:
            await _close_quietly(events)
            raise asyncio.TimeoutError(f"no response from {name} within {timeout:.0f}s") from exc
        except BaseException:
            await _close_quietly(events)
            raise


async def _close_quietly(events: AsyncIterator[StreamEvent]) -> None:
    aclose = getattr(events, "aclose", None)
    if aclose is None:
        return
    try:
        await aclose()
    except Exception:  # noqa: BLE001 - already failing, don't mask the original error
        pass


def _describe(exc: BaseException) -> str:
    if isinstance(exc, ProviderError):
        return exc.message
    text = str(exc).strip()
    return text or exc.__class__.__name__
