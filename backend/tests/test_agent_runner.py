import asyncio

from app.agent.gateway_client import GatewayCallError
from app.agent.providers.router import ProviderRouter
from app.agent.runner import AgentRunner
from app.agent.tools import ToolContext, ToolExecutor
from app.agent.types import Message, StreamEvent
from tests.fakes import FakeGateway, FakeProvider, text, tool_call

TOOLS = ("search_guidelines", "get_past_reviews")
GUIDELINES = {"/api/app/documents/search": {"results": [{"text": "Use snake_case.", "score": 0.91, "filename": "style.md", "document_id": "d1"}]}}


def run(provider, gateway, max_rounds=3):
    router = ProviderRouter({provider.name: provider}, default=provider.name, fallback=provider.name)
    executor = ToolExecutor(TOOLS, ToolContext("user-1", "session-1", gateway))
    runner = AgentRunner(router, executor, max_rounds=max_rounds)

    async def go():
        return [e async for e in runner.run([Message("user", "def Foo(): pass")], system="review", preferred_provider=None)]

    return asyncio.run(go())


def test_plain_answer_has_no_tool_round():
    provider = FakeProvider("ollama", [text("Fine.") + [StreamEvent.usage_report(5, 2)]])
    events = run(provider, FakeGateway())
    assert "".join(e.text for e in events if e.type == "text") == "Fine."
    assert len(provider.calls) == 1
    assert events[-1].type == "usage" and events[-1].usage.total == 7


def test_tool_round_calls_back_through_the_gateway():
    provider = FakeProvider("ollama", [
        [tool_call("search_guidelines", query="naming"), StreamEvent.usage_report(20, 5)],
        text("Rename Foo to foo, per style.md.") + [StreamEvent.usage_report(60, 12)],
    ])
    gateway = FakeGateway(GUIDELINES)
    events = run(provider, gateway)

    assert gateway.requests == [("/api/app/documents/search", {"q": "naming", "k": 4})]
    kinds = [e.type for e in events]
    assert kinds.index("tool_start") < kinds.index("tool_end") < kinds.index("text")
    assert next(e for e in events if e.type == "tool_end").data["ok"] is True

    second_turn = provider.calls[1]["messages"]
    assert second_turn[-2].role == "assistant" and second_turn[-2].tool_calls[0].name == "search_guidelines"
    assert second_turn[-1].role == "tool" and "snake_case" in second_turn[-1].content
    assert events[-1].usage.total == 97  # both rounds counted


def test_tool_failure_goes_back_to_the_model_instead_of_crashing():
    provider = FakeProvider("ollama", [[tool_call("search_guidelines", query="x")], text("Reviewed without guidelines.")])
    events = run(provider, FakeGateway(fail=GatewayCallError(429, "Too many requests.")))
    end = next(e for e in events if e.type == "tool_end")
    assert end.data["ok"] is False
    assert "Too many requests" in provider.calls[1]["messages"][-1].content
    assert "Reviewed without guidelines." in "".join(e.text for e in events if e.type == "text")


def test_unknown_tool_is_reported_to_the_model():
    provider = FakeProvider("ollama", [[tool_call("rm_rf")], text("ok")])
    run(provider, FakeGateway())
    assert "no tool called 'rm_rf'" in provider.calls[1]["messages"][-1].content


def test_last_round_gets_no_tools_so_the_loop_always_ends():
    # a model that asks for a tool every single time
    provider = FakeProvider("ollama", [[tool_call("get_past_reviews", limit=1)]])
    gateway = FakeGateway({"/api/app/reviews/recent": {"reviews": []}})
    run(provider, gateway, max_rounds=2)
    assert len(provider.calls) == 3
    assert provider.calls[0]["tools"] and provider.calls[1]["tools"]
    assert provider.calls[2]["tools"] is None


def test_tool_call_written_as_text_is_run_instead_of_shown():
    # what qwen2.5-coder:3b actually sends through Ollama: a fenced JSON blob, in pieces
    blob = ['```json\n{"name": "search_', 'guidelines", "arguments": ', '{"query": "file handling"}}\n```']
    provider = FakeProvider("ollama", [text(*blob), text("## Summary\nUse a with block.")])
    gateway = FakeGateway(GUIDELINES)
    events = run(provider, gateway)
    shown = "".join(e.text for e in events if e.type == "text")
    assert gateway.requests == [("/api/app/documents/search", {"q": "file handling", "k": 4})]
    assert "search_guidelines" not in shown and shown.startswith("## Summary")
    assert provider.calls[1]["messages"][-2].content == ""  # the blob isn't kept as assistant text


def test_answers_that_start_with_code_still_stream_normally():
    provider = FakeProvider("ollama", [text("```python\n", "with open(p) as f:\n", "    ...\n```\nBetter.")])
    events = run(provider, FakeGateway())
    chunks = [e.text for e in events if e.type == "text"]
    assert "".join(chunks) == "```python\nwith open(p) as f:\n    ...\n```\nBetter."
    assert len(chunks) > 1  # released as soon as it's clearly not JSON, not held to the end
    assert len(provider.calls) == 1


def test_json_that_is_not_a_known_tool_is_shown_as_is():
    provider = FakeProvider("ollama", [text('{"name": "rm_rf", "arguments": {}}')])
    events = run(provider, FakeGateway())
    assert "".join(e.text for e in events if e.type == "text") == '{"name": "rm_rf", "arguments": {}}'


def test_tool_arguments_that_echo_the_schema_fall_back_to_defaults():
    # seen from qwen2.5-coder:3b: {"top_k": {"type": "integer", "default": 4}}
    provider = FakeProvider("ollama", [[tool_call("search_guidelines", query="naming", top_k={"type": "integer"})], text("ok")])
    gateway = FakeGateway(GUIDELINES)
    events = run(provider, gateway)
    assert gateway.requests == [("/api/app/documents/search", {"q": "naming", "k": 4})]
    assert next(e for e in events if e.type == "tool_end").data["ok"] is True


def test_repeating_the_same_tool_call_moves_the_model_on_to_the_answer():
    # seen live: qwen2.5-coder:3b asked for get_past_reviews(limit=3) three rounds running
    provider = FakeProvider("ollama", [
        [tool_call("get_past_reviews", limit=3)],
        [tool_call("get_past_reviews", "call_2", limit=3)],
        text("Here's the review."),
    ])
    gateway = FakeGateway({"/api/app/reviews/recent": {"reviews": []}})
    events = run(provider, gateway)
    assert len(gateway.requests) == 1  # the repeat wasn't executed again
    assert provider.calls[2]["tools"] is None  # and the next round had to answer
    assert provider.calls[2]["messages"][-1].role == "user"  # with a nudge to actually write it
    assert "".join(e.text for e in events if e.type == "text") == "Here's the review."


def test_a_withheld_tool_called_as_text_gets_a_clean_answer_not_raw_json():
    # nothing uploaded, so search_guidelines isn't offered, but the prompt mentions it
    provider = FakeProvider("ollama", [text('{"name": "search_guidelines", "arguments": {"query": "sql"}}'), text("Use parameters.")])
    router = ProviderRouter({"ollama": provider}, default="ollama", fallback="ollama")
    executor = ToolExecutor((), ToolContext("u", "s", FakeGateway()), withheld=("search_guidelines",))

    async def go():
        return [e async for e in AgentRunner(router, executor).run([Message("user", "q")], system="s", preferred_provider=None)]

    events = asyncio.run(go())
    assert "".join(e.text for e in events if e.type == "text") == "Use parameters."
    assert "nothing to look up" in provider.calls[1]["messages"][-2].content
    assert provider.calls[1]["tools"] is None


def test_a_lookup_with_a_malformed_query_is_reported_as_failed():
    # seen live: the model sent the schema instead of a string, and the UI showed it as a success
    provider = FakeProvider("ollama", [[tool_call("search_guidelines", query={"type": "string"})], text("ok")])
    gateway = FakeGateway(GUIDELINES)
    events = run(provider, gateway)
    assert gateway.requests == []
    assert next(e for e in events if e.type == "tool_end").data["ok"] is False
