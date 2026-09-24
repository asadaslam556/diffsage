"""Each real adapter against a mocked HTTP server.

No network: httpx.MockTransport plays the provider. The payloads are the
shapes the real APIs send, trimmed down.
"""

from __future__ import annotations

import json

import pytest

httpx = pytest.importorskip("httpx")

from app.agent.providers.base import ProviderError  # noqa: E402
from app.agent.providers.registry import build_providers, discover_adapters  # noqa: E402
from app.agent.types import Message  # noqa: E402
from app.core.config import ProviderConfig  # noqa: E402


def make(adapter: str, handler, *, name: str | None = None, api_key: str | None = "sk-test", base_url: str = "http://mock", model: str = "m"):
    cls = discover_adapters()[adapter]
    cfg = ProviderConfig(name=name or adapter, adapter=adapter, base_url=base_url, model=model, api_key=api_key)
    return cls(cfg, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def sse_body(*payloads: dict | str) -> bytes:
    lines = []
    for p in payloads:
        lines.append("data: " + (p if isinstance(p, str) else json.dumps(p)))
    return ("\n\n".join(lines) + "\n\n").encode()


HELLO = [Message("user", "hello?")]


def test_discovery_finds_every_adapter():
    assert {"ollama", "anthropic", "openai", "deepseek", "openai_compatible"} <= set(discover_adapters())


def test_new_openai_style_provider_is_config_only():
    providers = build_providers({
        "groq": ProviderConfig(name="groq", adapter="openai_compatible", base_url="https://api.groq.com/openai/v1", model="llama", api_key="k"),
        "typo": ProviderConfig(name="typo", adapter="nope", base_url="x", model="y"),
    })
    assert providers["groq"].is_configured()
    assert "typo" not in providers  # logged and skipped, doesn't crash startup


async def test_openai_streams_text_and_usage():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse_body(
            {"choices": [{"delta": {"content": "Hel"}}]},
            {"choices": [{"delta": {"content": "lo"}}]},
            {"choices": [], "usage": {"prompt_tokens": 4, "completion_tokens": 2}},
            "[DONE]",
        ))

    result = await make("openai", handler).send_message(HELLO, system="be brief")
    assert result.text == "Hello"
    assert result.usage.total == 6
    assert seen["url"] == "http://mock/chat/completions"
    assert seen["auth"] == "Bearer sk-test"
    assert seen["body"]["stream"] is True
    assert seen["body"]["messages"][0] == {"role": "system", "content": "be brief"}


async def test_anthropic_streams_text_and_sends_the_right_headers():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = request.headers
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse_body(
            {"type": "message_start", "message": {"usage": {"input_tokens": 7, "output_tokens": 1}}},
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Looks "}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "fine"}},
            {"type": "content_block_stop", "index": 0},
            {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 3}},
            {"type": "message_stop"},
        ))

    result = await make("anthropic", handler).send_message(HELLO, system="sys")
    assert result.text == "Looks fine"
    assert (result.usage.input_tokens, result.usage.output_tokens) == (7, 3)
    assert seen["url"] == "http://mock/v1/messages"
    assert seen["headers"]["x-api-key"] == "sk-test"
    assert "anthropic-version" in seen["headers"]
    assert seen["body"]["system"] == "sys"
    assert "temperature" not in seen["body"]


async def test_ollama_streams_ndjson():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        lines = [
            {"message": {"role": "assistant", "content": "Hi "}, "done": False},
            {"message": {"role": "assistant", "content": "Asad"}, "done": False},
            {"message": {"role": "assistant", "content": ""}, "done": True, "prompt_eval_count": 3, "eval_count": 2},
        ]
        return httpx.Response(200, content="\n".join(json.dumps(line) for line in lines).encode())

    events = [e async for e in make("ollama", handler, api_key=None).stream_response(HELLO)]
    assert [e.text for e in events if e.type == "text"] == ["Hi ", "Asad"]


async def test_auth_errors_become_provider_errors_with_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "invalid x-api-key"}})

    with pytest.raises(ProviderError) as err:
        await make("anthropic", handler).send_message(HELLO)
    assert err.value.status_code == 401
    assert "check the API key" in err.value.message


async def test_connection_refused_is_a_readable_provider_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(ProviderError) as err:
        await make("ollama", handler, api_key=None).send_message(HELLO)
    assert "couldn't connect" in err.value.message


async def test_error_chunk_mid_stream_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=sse_body(
            {"choices": [{"delta": {"content": "par"}}]},
            {"error": {"message": "server overloaded"}},
        ))

    provider = make("deepseek", handler)
    got = []
    with pytest.raises(ProviderError):
        async for event in provider.stream_response(HELLO):
            got.append(event)
    assert [e.text for e in got] == ["par"]


async def test_paid_provider_without_key_is_not_configured():
    provider = make("openai", lambda r: httpx.Response(200), api_key=None)
    assert not provider.is_configured()


async def test_ollama_health_notices_a_missing_model():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": [{"name": "llama3.1:8b"}]})

    health = await make("ollama", handler, api_key=None, model="qwen2.5-coder:7b").health_check()
    assert health.status == "degraded"
    assert "ollama pull qwen2.5-coder:7b" in health.detail

    ok = await make("ollama", handler, api_key=None, model="llama3.1:8b").health_check()
    assert ok.status == "ok"


async def test_health_reports_bad_keys_as_down():
    health = await make("openai", lambda r: httpx.Response(401)).health_check()
    assert health.status == "down"
    assert "rejected" in health.detail
