"""Wire-format parsing for each provider, fed with recorded-shape chunks."""

import pytest

from app.agent.providers._wire import (
    AnthropicStreamParser, OllamaStreamParser, OpenAIStreamParser,
    anthropic_messages, ollama_messages, openai_messages,
)
from app.agent.providers.base import ProviderError
from app.agent.types import Message, ToolCall


def test_openai_text_fragmented_tool_call_and_usage():
    p = OpenAIStreamParser()
    events = []
    for chunk in [
        {"choices": [{"delta": {"content": "Let me "}}]},
        {"choices": [{"delta": {"content": "check."}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_a", "function": {"name": "search_guidelines", "arguments": '{"que'}}]}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": 'ry": "naming"}'}}]}}]},
        {"choices": [], "usage": {"prompt_tokens": 12, "completion_tokens": 7}},
    ]:
        events += p.feed(chunk)
    events += p.finish()
    assert "".join(e.text for e in events if e.type == "text") == "Let me check."
    call = next(e.tool_call for e in events if e.type == "tool_call")
    assert (call.id, call.name, call.arguments) == ("call_a", "search_guidelines", {"query": "naming"})
    usage = next(e.usage for e in events if e.type == "usage")
    assert (usage.input_tokens, usage.output_tokens) == (12, 7)


def test_openai_broken_arguments_become_raw():
    p = OpenAIStreamParser()
    p.feed({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c", "function": {"name": "t", "arguments": "{not json"}}]}}]})
    [event] = p.finish()
    assert event.tool_call.arguments == {"_raw": "{not json"}


def test_openai_error_chunk_raises():
    with pytest.raises(ProviderError):
        OpenAIStreamParser().feed({"error": {"message": "quota"}})


def test_anthropic_stream():
    p = AnthropicStreamParser()
    events = []
    for data in [
        {"type": "message_start", "message": {"usage": {"input_tokens": 40, "output_tokens": 1}}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hi "}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "there"}},
        {"type": "content_block_stop", "index": 0},
        {"type": "content_block_start", "index": 1, "content_block": {"type": "tool_use", "id": "toolu_1", "name": "get_past_reviews", "input": {}}},
        {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": '{"limit"'}},
        {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": ": 2}"}},
        {"type": "content_block_stop", "index": 1},
        {"type": "message_delta", "delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": 25}},
        {"type": "message_stop"},
    ]:
        events += p.feed(data)
    assert "".join(e.text for e in events if e.type == "text") == "Hi there"
    call = next(e.tool_call for e in events if e.type == "tool_call")
    assert (call.id, call.arguments) == ("toolu_1", {"limit": 2})
    usage = next(e.usage for e in events if e.type == "usage")
    assert (usage.input_tokens, usage.output_tokens) == (40, 25)


def test_anthropic_error_event_raises():
    with pytest.raises(ProviderError) as err:
        AnthropicStreamParser().feed({"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}})
    assert "overloaded" in str(err.value)


def test_anthropic_messages_merge_tool_results_into_one_user_turn():
    calls = [ToolCall("t1", "a", {}), ToolCall("t2", "b", {"x": 1})]
    wire = anthropic_messages([
        Message("user", "review"),
        Message("assistant", "", tool_calls=calls),
        Message("tool", "result a", tool_call_id="t1", name="a"),
        Message("tool", "result b", tool_call_id="t2", name="b"),
    ])
    assert [m["role"] for m in wire] == ["user", "assistant", "user"]
    assert [b["type"] for b in wire[1]["content"]] == ["tool_use", "tool_use"]  # empty text block dropped
    assert [b["tool_use_id"] for b in wire[2]["content"]] == ["t1", "t2"]


def test_anthropic_messages_merge_back_to_back_user_turns():
    wire = anthropic_messages([Message("user", "one"), Message("user", "two")])
    assert len(wire) == 1 and len(wire[0]["content"]) == 2


def test_openai_messages_shape():
    wire = openai_messages(
        [Message("assistant", "", tool_calls=[ToolCall("c1", "t", {"q": "x"})]), Message("tool", "out", tool_call_id="c1")],
        system="be nice",
    )
    assert wire[0] == {"role": "system", "content": "be nice"}
    assert wire[1]["tool_calls"][0]["function"] == {"name": "t", "arguments": '{"q": "x"}'}
    assert wire[2] == {"role": "tool", "tool_call_id": "c1", "content": "out"}


def test_ollama_stream_and_messages():
    p = OllamaStreamParser()
    events = p.feed({"message": {"role": "assistant", "content": "Hel"}, "done": False})
    events += p.feed({"message": {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "search_guidelines", "arguments": {"query": "x"}}}]}, "done": False})
    events += p.feed({"message": {"role": "assistant", "content": "lo"}, "done": True, "prompt_eval_count": 9, "eval_count": 3})
    assert "".join(e.text for e in events if e.type == "text") == "Hello"
    call = next(e.tool_call for e in events if e.type == "tool_call")
    assert call.name == "search_guidelines" and call.id.startswith("call_")
    assert next(e.usage for e in events if e.type == "usage").total == 12
    with pytest.raises(ProviderError):
        p.feed({"error": "model 'x' not found"})
    wire = ollama_messages([Message("tool", "r", tool_call_id="c", name="search_guidelines")], None)
    assert wire == [{"role": "tool", "content": "r", "tool_name": "search_guidelines"}]


def test_anthropic_messages_never_start_on_an_assistant_turn():
    # a count-limited history window can open mid-exchange, and Anthropic rejects that
    wire = anthropic_messages([
        Message(role="assistant", content="", tool_calls=[ToolCall("t1", "search_guidelines", {"query": "x"})]),
        Message(role="tool", content="hits", tool_call_id="t1", name="search_guidelines"),
        Message(role="assistant", content="earlier review"),
        Message(role="user", content="and this one?"),
    ])
    assert [turn["role"] for turn in wire] == ["user"]
    assert wire[0]["content"] == [{"type": "text", "text": "and this one?"}]
