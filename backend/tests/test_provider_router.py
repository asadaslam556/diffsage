"""Provider switching and fallback, using fake providers."""

import asyncio

import pytest

from app.agent.providers.base import LLMProvider
from app.agent.providers.registry import _ADAPTERS, build_providers, register_provider
from app.agent.providers.router import AllProvidersFailed, ProviderRouter, StreamInterrupted
from app.agent.types import Message, ToolSpec
from app.core.config import ProviderConfig
from tests.fakes import FakeProvider, text

HELLO = [Message(role="user", content="review this")]


def collect(router, **kwargs):
    async def go():
        return [event async for event in router.stream(HELLO, **kwargs)]

    return asyncio.run(go())


def texts(events):
    return "".join(e.text for e in events if e.type == "text")


def test_uses_the_preferred_provider():
    claude = FakeProvider("anthropic", [text("from claude")])
    ollama = FakeProvider("ollama", [text("from ollama")])
    router = ProviderRouter({"anthropic": claude, "ollama": ollama}, default="ollama", fallback="ollama")
    events = collect(router, preferred="anthropic")
    assert texts(events) == "from claude"
    assert events[0].type == "meta" and events[0].data["provider"] == "anthropic"
    assert ollama.calls == []


def test_uses_the_default_when_nothing_is_preferred():
    router = ProviderRouter(
        {"deepseek": FakeProvider("deepseek", [text("ds")]), "ollama": FakeProvider("ollama")},
        default="deepseek", fallback="ollama",
    )
    assert texts(collect(router)) == "ds"


def test_falls_back_to_ollama_when_the_paid_provider_errors():
    claude = FakeProvider("anthropic", fail="HTTP 529: overloaded")
    ollama = FakeProvider("ollama", [text("local answer")])
    router = ProviderRouter({"anthropic": claude, "ollama": ollama}, default="ollama", fallback="ollama")
    events = collect(router, preferred="anthropic")
    fallback = next(e for e in events if e.type == "fallback")
    assert fallback.data == {"from": "anthropic", "to": "ollama", "reason": "HTTP 529: overloaded"}
    assert next(e for e in events if e.type == "meta").data["provider"] == "ollama"
    assert texts(events) == "local answer"


def test_falls_back_when_the_paid_provider_isnt_configured():
    claude = FakeProvider("anthropic", configured=False)
    router = ProviderRouter({"anthropic": claude, "ollama": FakeProvider("ollama", [text("ok")])}, default="ollama", fallback="ollama")
    events = collect(router, preferred="anthropic")
    assert "not configured" in next(e for e in events if e.type == "fallback").data["reason"]
    assert claude.calls == []


def test_falls_back_on_first_token_timeout():
    slow = FakeProvider("openai", [text("too late")], delay=1.0)
    router = ProviderRouter(
        {"openai": slow, "ollama": FakeProvider("ollama", [text("fast")])},
        default="ollama", fallback="ollama", first_token_timeout=0.05,
    )
    events = collect(router, preferred="openai")
    assert "within" in next(e for e in events if e.type == "fallback").data["reason"]
    assert texts(events) == "fast"


def test_last_provider_in_the_chain_is_not_cut_off_by_the_first_token_timeout():
    # ollama is both default and fallback here, so timing it out would just fail the request
    slow_local = FakeProvider("ollama", [text("slow but fine")], delay=0.2)
    router = ProviderRouter({"ollama": slow_local}, default="ollama", fallback="ollama", first_token_timeout=0.05)
    assert texts(collect(router)) == "slow but fine"


def test_does_not_switch_providers_mid_stream():
    flaky = FakeProvider("anthropic", [text("half ", "an ", "answer")], fail_after=2)
    ollama = FakeProvider("ollama", [text("other model")])
    router = ProviderRouter({"anthropic": flaky, "ollama": ollama}, default="ollama", fallback="ollama")

    async def go():
        seen = []
        with pytest.raises(StreamInterrupted):
            async for event in router.stream(HELLO, preferred="anthropic"):
                seen.append(event)
        return seen

    seen = asyncio.run(go())
    assert texts(seen) == "half an "
    assert ollama.calls == []


def test_raises_when_everything_fails():
    router = ProviderRouter(
        {"anthropic": FakeProvider("anthropic", fail="401"), "ollama": FakeProvider("ollama", fail="couldn't connect")},
        default="ollama", fallback="ollama",
    )
    with pytest.raises(AllProvidersFailed) as err:
        collect(router, preferred="anthropic")
    assert [name for name, _ in err.value.attempts] == ["anthropic", "ollama"]


def test_fallback_list_is_tried_in_order():
    router = ProviderRouter(
        {
            "anthropic": FakeProvider("anthropic", fail="HTTP 400"),
            "deepseek": FakeProvider("deepseek", fail="HTTP 503"),
            "ollama": FakeProvider("ollama", [text("local answer")]),
        },
        default="anthropic", fallback=("deepseek", "ollama"),
    )
    events = collect(router)
    assert [(e.data["from"], e.data["to"]) for e in events if e.type == "fallback"] == [("anthropic", "deepseek"), ("deepseek", "ollama")]
    assert texts(events) == "local answer"


def test_fallbacks_outside_the_plan_are_skipped():
    deepseek = FakeProvider("deepseek", [text("paid answer")])
    router = ProviderRouter(
        {"ollama": FakeProvider("ollama", fail="down"), "deepseek": deepseek},
        default="ollama", fallback=("deepseek", "ollama"),
    )
    with pytest.raises(AllProvidersFailed):
        collect(router, allow=lambda name: name == "ollama")  # a Free plan
    assert deepseek.calls == []


def test_ollama_failing_as_default_has_nowhere_else_to_go():
    router = ProviderRouter({"ollama": FakeProvider("ollama", fail="down")}, default="ollama", fallback="ollama")
    with pytest.raises(AllProvidersFailed):
        collect(router)


def test_tools_are_withheld_from_providers_that_cant_use_them():
    reasoner = FakeProvider("deepseek", [text("ok")], supports_tools=False)
    router = ProviderRouter({"deepseek": reasoner}, default="deepseek", fallback="deepseek")
    spec = ToolSpec("search_guidelines", "x", {"type": "object"})
    collect(router, tools=[spec])
    assert reasoner.calls[0]["tools"] is None


def test_new_adapter_plugs_in_through_the_registry_only():
    @register_provider("test_echo")
    class EchoProvider(LLMProvider):
        requires_api_key = False

        async def stream_response(self, messages, *, system=None, tools=None, temperature=0.2):
            yield text(messages[-1].content)[0]

        async def health_check(self):
            raise NotImplementedError

    try:
        configs = {
            "echo": ProviderConfig(name="echo", adapter="test_echo", base_url="http://x", model="m"),
            "typo": ProviderConfig(name="typo", adapter="does_not_exist", base_url="http://x", model="m"),
        }
        providers = build_providers(configs, discover=False)
        assert set(providers) == {"echo"}  # bad adapter name is skipped, not fatal
        router = ProviderRouter(providers, default="echo", fallback="echo")
        assert texts(collect(router)) == "review this"
    finally:
        _ADAPTERS.pop("test_echo", None)


def test_registering_two_adapters_under_one_name_is_an_error():
    @register_provider("test_dupe")
    class A(FakeProvider):
        pass

    try:
        with pytest.raises(RuntimeError):
            @register_provider("test_dupe")
            class B(FakeProvider):
                pass
    finally:
        _ADAPTERS.pop("test_dupe", None)
