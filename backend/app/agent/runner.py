"""The agent loop.

Stream a turn from the model. If it asked for tools, run them, append the
results and go again. Stop when a turn comes back with no tool calls or we
hit max_rounds. The last allowed round is sent without tools, so the model
is forced to actually answer instead of looping on lookups.

The runner knows nothing about HTTP, databases or specific providers,
which is what makes the profiles swappable.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import AsyncIterator, Callable

from app.agent.providers.router import ProviderRouter
from app.agent.tools import ToolExecutor, args_preview, preview
from app.agent.types import Message, StreamEvent, ToolCall, Usage

log = logging.getLogger(__name__)

# Small local models (qwen2.5-coder:3b is a regular) often write the tool call
# as a JSON blob in the reply instead of using the API's tool-call field. Left
# alone, the user gets raw JSON instead of a review and the lookup never runs.
# So while a turn's text *could* still be such a blob we hold it back, and if
# it turns out to be one we run it as a real tool call. Normal answers start
# with prose or a heading, so they're never held.
HOLD_LIMIT = 2000
ANSWER_NOW = "You have what you need from the tools. Write your answer to my original message now, in the format you were given."
REPEATED_CALL = "You already made this exact call; its result is above. Don't call it again. Answer using what you have."
_FENCED = re.compile(r"^```[\w-]*[ \t]*\n(.*?)\n?```$", re.S)


def could_be_text_tool_call(text: str) -> bool:
    s = text.lstrip()
    if len(s) >= HOLD_LIMIT:
        return False
    if not s or s.startswith("{"):
        return True
    if s.startswith("```"):
        newline = s.find("\n")
        body = s[newline + 1:].lstrip() if newline != -1 else ""
        return not body or body.startswith("{")
    return "```".startswith(s)  # a lone ` or `` that may become a fence


def text_tool_call(text: str, allowed: set[str]) -> ToolCall | None:
    s = text.strip()
    fenced = _FENCED.match(s)
    if fenced:
        s = fenced.group(1).strip()
    if not s.startswith("{"):
        return None
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    name = data.get("name")
    args = data.get("arguments", data.get("parameters", {}))
    if name not in allowed or not isinstance(args, dict):
        return None
    return ToolCall(f"call_{uuid.uuid4().hex[:12]}", name, args)


class AgentRunner:
    def __init__(
        self, router: ProviderRouter, executor: ToolExecutor, *, max_rounds: int = 3,
        allow_provider: Callable[[str], bool] | None = None,
    ):
        self.router = router
        self.executor = executor
        self.max_rounds = max_rounds
        self.allow_provider = allow_provider  # the user's plan, so fallbacks never go past it

    async def run(
        self,
        history: list[Message],
        *,
        system: str,
        preferred_provider: str | None,
    ) -> AsyncIterator[StreamEvent]:
        messages = list(history)
        provider = preferred_provider
        total = Usage()
        seen: set[str] = set()  # tool calls already answered in this run
        answer_now = False  # set once the model starts repeating itself
        used_tools = False

        for round_no in range(self.max_rounds + 1):
            offer = round_no < self.max_rounds and not answer_now
            tools = self.executor.specs if offer else None
            if not tools and used_tools:
                # Without this, small models often answer a tool result with nothing at
                # all once the tools are taken away. Only lives in this run's message list.
                messages.append(Message(role="user", content=ANSWER_NOW))
            text_parts: list[str] = []
            calls: list[ToolCall] = []
            # Hold back possible JSON tool calls whenever the profile has tools at all, even on
            # rounds where none were offered: a small model will still "call" one it read about.
            known = set(self.executor.tools) | self.executor.withheld
            holding = bool(known)
            held: list[str] = []

            async for event in self.router.stream(messages, preferred=provider, system=system, tools=tools or None, allow=self.allow_provider):
                if event.type == "meta":
                    # stick with whoever actually answered for the rest of this run
                    provider = event.data["provider"]
                    yield event
                elif event.type == "text":
                    text_parts.append(event.text)
                    if holding:
                        held.append(event.text)
                        if could_be_text_tool_call("".join(held)):
                            continue
                        holding = False
                        yield StreamEvent.text_chunk("".join(held))
                        held = []
                        continue
                    yield event
                elif event.type == "tool_call" and event.tool_call:
                    calls.append(event.tool_call)
                elif event.type == "usage" and event.usage:
                    total = total + event.usage
                else:
                    yield event  # fallback notices and anything new pass straight through

            if held:
                recovered = None if calls else text_tool_call("".join(held), known)
                if recovered and round_no == self.max_rounds:
                    # out of rounds and still asking; showing raw JSON helps nobody, so drop it
                    # and let the stream report an empty answer the user can retry
                    log.warning("model still calling %s on the last round, dropping it", recovered.name)
                    text_parts.clear()
                elif recovered:
                    log.info("model wrote tool call %s as text, running it as a real call", recovered.name)
                    calls.append(recovered)
                    text_parts.clear()  # the JSON was never meant to be part of the answer
                else:
                    yield StreamEvent.text_chunk("".join(held))

            if not calls:
                break

            used_tools = True
            messages.append(Message(role="assistant", content="".join(text_parts), tool_calls=calls))
            for call in calls:
                key = f"{call.name}:{json.dumps(call.arguments, sort_keys=True, default=str)}"
                if key in seen:
                    # asking again won't change the answer; stop offering tools so it writes one
                    log.info("model repeated tool call %s, moving it on to the answer", call.name)
                    answer_now = True
                    messages.append(Message(role="tool", content=REPEATED_CALL, tool_call_id=call.id, name=call.name))
                    continue
                seen.add(key)
                if call.name in self.executor.withheld:
                    answer_now = True  # nothing to look up, so go straight to the answer next round
                yield StreamEvent("tool_start", data={"id": call.id, "name": call.name, "args": args_preview(call.arguments)})
                ok, output = await self.executor.execute(call)
                log.info("tool %s ok=%s (%d chars)", call.name, ok, len(output))
                yield StreamEvent("tool_end", data={"id": call.id, "name": call.name, "ok": ok, "preview": preview(output)})
                messages.append(Message(role="tool", content=output, tool_call_id=call.id, name=call.name))
            if text_parts:
                # keep the streamed pre-tool text visually separate from the answer
                yield StreamEvent.text_chunk("\n\n")

        yield StreamEvent("usage", usage=total)
