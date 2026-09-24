"""Tools the model can call.

Each tool is a spec (what the model sees) plus a handler (what actually
runs). Handlers get a ToolContext and must return a string. Errors are
returned to the model as text instead of raised; a failed lookup
shouldn't kill the whole review, and the model can usually work around it.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

from app.agent.gateway_client import GatewayCallError
from app.agent.types import ToolCall, ToolSpec

log = logging.getLogger(__name__)

MAX_TOOL_OUTPUT = 6_000  # chars; keeps a chatty tool from eating the context window


class GatewayLike(Protocol):
    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any: ...


@dataclass
class ToolContext:
    user_id: str
    session_id: str
    gateway: GatewayLike


Handler = Callable[[ToolContext, dict[str, Any]], Awaitable[str]]


@dataclass(frozen=True)
class Tool:
    spec: ToolSpec
    handler: Handler


def _int_arg(args: dict[str, Any], key: str, default: int, low: int, high: int) -> int:
    # small models sometimes echo the schema back ({"type": "integer", ...}) or send
    # "four"; a bad number shouldn't cost the whole lookup, so fall back to the default
    try:
        value = int(args.get(key) or default)
    except (TypeError, ValueError):
        value = default
    return max(low, min(value, high))


async def _search_guidelines(ctx: ToolContext, args: dict[str, Any]) -> str:
    query = args.get("query")
    query = query.strip() if isinstance(query, str) else ""
    if not query:
        # raise rather than return, so it's reported (and shown) as a failed lookup
        raise ValueError("'query' must be a short text description of what to look for")
    top_k = _int_arg(args, "top_k", 4, 1, 8)
    data = await ctx.gateway.get("/api/app/documents/search", {"q": query, "k": top_k})
    hits = data.get("results", [])
    if not hits:
        return "No uploaded guidelines matched. Review using general best practice."
    return "\n\n".join(f"[{h['filename']} score={h['score']:.2f}]\n{h['text']}" for h in hits)


async def _get_past_reviews(ctx: ToolContext, args: dict[str, Any]) -> str:
    limit = _int_arg(args, "limit", 3, 1, 5)
    data = await ctx.gateway.get("/api/app/reviews/recent", {"limit": limit, "exclude_session": ctx.session_id})
    reviews = data.get("reviews", [])
    if not reviews:
        return "No earlier reviews for this user."
    return "\n\n---\n\n".join(f"{r['created_at']} ({r['session_title']}):\n{r['excerpt']}" for r in reviews)


TOOLS: dict[str, Tool] = {
    "search_guidelines": Tool(
        ToolSpec(
            name="search_guidelines",
            description="Search the team's uploaded coding guidelines and docs. Returns the most relevant excerpts.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to look for, e.g. 'python error handling conventions'"},
                    "top_k": {"type": "integer", "description": "How many excerpts, 1-8", "default": 4},
                },
                "required": ["query"],
            },
        ),
        _search_guidelines,
    ),
    "get_past_reviews": Tool(
        ToolSpec(
            name="get_past_reviews",
            description="Fetch excerpts of this user's most recent earlier reviews.",
            parameters={
                "type": "object",
                "properties": {"limit": {"type": "integer", "description": "1-5", "default": 3}},
            },
        ),
        _get_past_reviews,
    ),
}


class ToolExecutor:
    def __init__(
        self, allowed: tuple[str, ...], context: ToolContext, registry: dict[str, Tool] | None = None,
        *, withheld: tuple[str, ...] = (),
    ):
        registry = registry if registry is not None else TOOLS
        self.tools = {name: registry[name] for name in allowed if name in registry}
        # tools the profile has but that weren't offered this time (nothing to look up).
        # Small models call them anyway because the system prompt mentions them.
        self.withheld = frozenset(withheld)
        self.context = context

    @property
    def specs(self) -> list[ToolSpec]:
        return [tool.spec for tool in self.tools.values()]

    async def execute(self, call: ToolCall) -> tuple[bool, str]:
        tool = self.tools.get(call.name)
        if tool is None and call.name in self.withheld:
            return False, f"{call.name} has nothing to look up for this user yet. Answer without it."
        if tool is None:
            return False, f"error: there's no tool called '{call.name}'"
        if "_raw" in call.arguments:
            return False, f"error: arguments weren't valid JSON: {call.arguments['_raw'][:200]}"
        try:
            output = await tool.handler(self.context, call.arguments)
        except Exception as exc:  # noqa: BLE001 - reported back to the model, and logged
            # gateway errors (quota, 404...) and bad arguments from the model are routine, so no traceback
            expected = isinstance(exc, (GatewayCallError, ValueError))  # bad model input is routine
            log.warning("tool %s failed: %s", call.name, exc, exc_info=not expected)
            message = getattr(exc, "message", None) or str(exc) or exc.__class__.__name__
            return False, f"error: {call.name} failed ({message})"
        if len(output) > MAX_TOOL_OUTPUT:
            output = output[:MAX_TOOL_OUTPUT] + "\n...[truncated]"
        return True, output


def preview(text: str, limit: int = 160) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def args_preview(arguments: dict[str, Any]) -> str:
    return preview(json.dumps(arguments, ensure_ascii=False), 120)
