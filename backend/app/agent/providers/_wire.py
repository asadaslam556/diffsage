"""Translation to and from each provider's wire format.

No I/O in here on purpose. The adapters feed raw chunks in and get
StreamEvents out, which means all the fiddly parsing can be unit tested
with plain dicts.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from app.agent.providers.base import ProviderError
from app.agent.types import Message, StreamEvent, ToolCall, ToolSpec


def _parse_args(raw: str | dict | None) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        # models occasionally emit broken JSON; hand the tool the raw text
        # and let it complain, rather than killing the whole turn
        return {"_raw": raw}
    return value if isinstance(value, dict) else {"value": value}


def _new_call_id() -> str:
    return f"call_{uuid.uuid4().hex[:12]}"


# --- OpenAI-compatible (OpenAI, DeepSeek, Groq, LM Studio, vLLM...) ---------

def openai_messages(messages: list[Message], system: str | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [{"role": "system", "content": system}] if system else []
    for m in messages:
        if m.role == "tool":
            out.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content})
        elif m.role == "assistant" and m.tool_calls:
            out.append({
                "role": "assistant",
                "content": m.content or None,
                "tool_calls": [
                    {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": json.dumps(c.arguments)}}
                    for c in m.tool_calls
                ],
            })
        else:
            out.append({"role": m.role, "content": m.content})
    return out


def openai_tools(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    return [
        {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
        for t in tools
    ]


class OpenAIStreamParser:
    """Tool call arguments arrive in fragments keyed by index, so we buffer
    them and only emit complete calls once the stream is done."""

    def __init__(self) -> None:
        self._calls: dict[int, dict[str, str]] = {}

    def feed(self, chunk: dict[str, Any]) -> list[StreamEvent]:
        events: list[StreamEvent] = []
        if chunk.get("error"):
            err = chunk["error"]
            raise ProviderError("openai-compatible", err.get("message", str(err)) if isinstance(err, dict) else str(err))
        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}
            if delta.get("content"):
                events.append(StreamEvent.text_chunk(delta["content"]))
            for tc in delta.get("tool_calls") or []:
                slot = self._calls.setdefault(tc.get("index", 0), {"id": "", "name": "", "arguments": ""})
                if tc.get("id"):
                    slot["id"] = tc["id"]
                fn = tc.get("function") or {}
                slot["name"] += fn.get("name") or ""
                slot["arguments"] += fn.get("arguments") or ""
        usage = chunk.get("usage")
        if usage:
            events.append(StreamEvent.usage_report(usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)))
        return events

    def finish(self) -> list[StreamEvent]:
        events = [
            StreamEvent.tool(ToolCall(slot["id"] or _new_call_id(), slot["name"], _parse_args(slot["arguments"])))
            for _, slot in sorted(self._calls.items())
            if slot["name"]
        ]
        self._calls.clear()
        return events


# --- Anthropic Messages API ------------------------------------------------

def anthropic_messages(messages: list[Message]) -> list[dict[str, Any]]:
    """Anthropic wants strictly alternating user/assistant turns with content
    blocks, and tool results travel back as blocks inside a *user* turn.
    Consecutive same-role entries get merged."""
    out: list[dict[str, Any]] = []

    def push(role: str, blocks: list[dict[str, Any]]) -> None:
        if not blocks:
            return
        if out and out[-1]["role"] == role:
            out[-1]["content"].extend(blocks)
        else:
            out.append({"role": role, "content": list(blocks)})

    for m in messages:
        if m.role == "tool":
            push("user", [{"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content or "(empty)"}])
        elif m.role == "assistant":
            blocks: list[dict[str, Any]] = []
            if m.content.strip():
                blocks.append({"type": "text", "text": m.content})
            blocks += [{"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments} for c in m.tool_calls]
            push("assistant", blocks)
        elif m.content.strip():
            push("user", [{"type": "text", "text": m.content}])
    # The history window is cut by message count, so it can start on an
    # assistant turn (or an orphaned tool_use). Anthropic 400s on that.
    while out and (out[0]["role"] != "user" or all(b["type"] == "tool_result" for b in out[0]["content"])):
        out.pop(0)
    return out


def anthropic_tools(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    return [{"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tools]


class AnthropicStreamParser:
    def __init__(self) -> None:
        self._blocks: dict[int, dict[str, str]] = {}
        self._input_tokens = 0
        self._output_tokens = 0

    def feed(self, data: dict[str, Any]) -> list[StreamEvent]:
        kind = data.get("type")
        if kind == "error":
            err = data.get("error") or {}
            raise ProviderError("anthropic", f"{err.get('type', 'error')}: {err.get('message', 'unknown')}")
        if kind == "message_start":
            usage = (data.get("message") or {}).get("usage") or {}
            self._input_tokens = int(usage.get("input_tokens", 0))
            self._output_tokens = int(usage.get("output_tokens", 0))
        elif kind == "content_block_start":
            block = data.get("content_block") or {}
            if block.get("type") == "tool_use":
                self._blocks[data.get("index", 0)] = {"id": block.get("id", ""), "name": block.get("name", ""), "json": ""}
        elif kind == "content_block_delta":
            delta = data.get("delta") or {}
            if delta.get("type") == "text_delta" and delta.get("text"):
                return [StreamEvent.text_chunk(delta["text"])]
            if delta.get("type") == "input_json_delta":
                slot = self._blocks.get(data.get("index", 0))
                if slot is not None:
                    slot["json"] += delta.get("partial_json", "")
        elif kind == "content_block_stop":
            slot = self._blocks.pop(data.get("index", 0), None)
            if slot:
                return [StreamEvent.tool(ToolCall(slot["id"] or _new_call_id(), slot["name"], _parse_args(slot["json"])))]
        elif kind == "message_delta":
            usage = data.get("usage") or {}
            # output_tokens here is cumulative, not a delta
            self._output_tokens = int(usage.get("output_tokens", self._output_tokens))
        elif kind == "message_stop":
            return [StreamEvent.usage_report(self._input_tokens, self._output_tokens)]
        return []


# --- Ollama /api/chat --------------------------------------------------------

def ollama_messages(messages: list[Message], system: str | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [{"role": "system", "content": system}] if system else []
    for m in messages:
        if m.role == "tool":
            out.append({"role": "tool", "content": m.content, "tool_name": m.name or ""})
        elif m.role == "assistant" and m.tool_calls:
            out.append({
                "role": "assistant",
                "content": m.content,
                "tool_calls": [{"function": {"name": c.name, "arguments": c.arguments}} for c in m.tool_calls],
            })
        else:
            out.append({"role": m.role, "content": m.content})
    return out


class OllamaStreamParser:
    """Ollama streams newline-delimited JSON. Tool calls show up whole,
    never in fragments, and usage only on the final done=true line."""

    def feed(self, chunk: dict[str, Any]) -> list[StreamEvent]:
        if chunk.get("error"):
            raise ProviderError("ollama", str(chunk["error"]))
        events: list[StreamEvent] = []
        message = chunk.get("message") or {}
        if message.get("content"):
            events.append(StreamEvent.text_chunk(message["content"]))
        for tc in message.get("tool_calls") or []:
            fn = tc.get("function") or {}
            if fn.get("name"):
                events.append(StreamEvent.tool(ToolCall(tc.get("id") or _new_call_id(), fn["name"], _parse_args(fn.get("arguments")))))
        if chunk.get("done"):
            events.append(StreamEvent.usage_report(chunk.get("prompt_eval_count", 0), chunk.get("eval_count", 0)))
        return events
