"""The shapes the agent passes around.

Providers translate between these and their own wire formats, so nothing
above the provider layer ever sees an Anthropic content block or an OpenAI
delta.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["user", "assistant", "tool"]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class Message:
    role: Role
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None  # set on role="tool" replies
    name: str | None = None          # tool name, some APIs want it on the reply


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON schema


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(self.input_tokens + other.input_tokens, self.output_tokens + other.output_tokens)

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


EventType = Literal["text", "tool_call", "usage", "meta", "fallback", "tool_start", "tool_end"]


@dataclass
class StreamEvent:
    type: EventType
    text: str = ""
    tool_call: ToolCall | None = None
    usage: Usage | None = None
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def text_chunk(cls, text: str) -> "StreamEvent":
        return cls("text", text=text)

    @classmethod
    def tool(cls, call: ToolCall) -> "StreamEvent":
        return cls("tool_call", tool_call=call)

    @classmethod
    def usage_report(cls, input_tokens: int = 0, output_tokens: int = 0) -> "StreamEvent":
        return cls("usage", usage=Usage(int(input_tokens or 0), int(output_tokens or 0)))


@dataclass
class ChatResult:
    text: str
    tool_calls: list[ToolCall]
    usage: Usage
    provider: str
    model: str
