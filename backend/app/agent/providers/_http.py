"""Small HTTP helpers shared by the adapters."""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.agent.providers.base import ProviderError, ProviderHealth


async def raise_for_status(response: httpx.Response, provider: str) -> None:
    if response.status_code < 400:
        return
    body = (await response.aread()).decode("utf-8", "replace")[:500]
    detail = body
    try:
        parsed = json.loads(body)
        err = parsed.get("error", parsed)
        detail = err.get("message", body) if isinstance(err, dict) else str(err)
    except (json.JSONDecodeError, AttributeError):
        pass
    if response.status_code in (401, 403):
        detail = f"auth rejected ({response.status_code}), check the API key. {detail}"
    elif response.status_code == 429:
        detail = f"rate limited by provider. {detail}"
    raise ProviderError(provider, f"HTTP {response.status_code}: {detail}".strip(), status_code=response.status_code)


async def iter_sse_data(response: httpx.Response) -> AsyncIterator[dict[str, Any]]:
    """Yield the JSON payload of every `data:` line. Stops at [DONE]."""
    async for line in response.aiter_lines():
        if not line or not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            return
        try:
            yield json.loads(payload)
        except json.JSONDecodeError:
            continue  # keep-alive junk, partial proxies, etc.


async def iter_ndjson(response: httpx.Response) -> AsyncIterator[dict[str, Any]]:
    async for line in response.aiter_lines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def wrap_transport_error(provider: str, exc: Exception) -> ProviderError:
    if isinstance(exc, ProviderError):
        return exc
    if isinstance(exc, httpx.TimeoutException):
        return ProviderError(provider, "request timed out")
    if isinstance(exc, httpx.ConnectError):
        return ProviderError(provider, "couldn't connect, is it running and is the URL right?")
    if isinstance(exc, httpx.HTTPError):
        return ProviderError(provider, f"network error: {exc.__class__.__name__}")
    return ProviderError(provider, f"unexpected error: {exc!r}")


async def timed_get(client: httpx.AsyncClient, url: str, *, headers: dict[str, str] | None = None, timeout: float = 4.0) -> tuple[httpx.Response | None, int, str]:
    started = time.perf_counter()
    try:
        response = await client.get(url, headers=headers, timeout=timeout)
    except httpx.HTTPError as exc:
        return None, int((time.perf_counter() - started) * 1000), wrap_transport_error("", exc).message
    return response, int((time.perf_counter() - started) * 1000), ""


def health_from_response(response: httpx.Response | None, latency: int, error: str) -> ProviderHealth:
    if response is None:
        return ProviderHealth("down", error, latency)
    if response.status_code in (401, 403):
        return ProviderHealth("down", "API key rejected", latency)
    if response.status_code >= 400:
        return ProviderHealth("down", f"HTTP {response.status_code}", latency)
    return ProviderHealth("ok", "", latency)
