"""Turns an agent run into a Server-Sent Events stream and makes sure the
bookkeeping happens no matter how the stream ends: finished, provider
blew up, or the user closed the tab halfway through.

Events the frontend gets, in order:
  meta        session id + provider we're about to try
  fallback    only if the first provider failed and we switched
  provider    who actually answered
  tool_start / tool_end   when the agent looks something up
  token       a chunk of text (lots of these)
  error       if it failed; the stream ends right after
  done        usage + ids, always last on success
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import anyio

from app.agent.providers.router import AllProvidersFailed, StreamInterrupted
from app.agent.runner import AgentRunner
from app.agent.types import Message, Usage
from app.container import Container
from app.db.models import ChatMessage, ChatSession
from app.services.agent.sse import sse
from app.services.billing.policy import estimate_tokens
from app.services.billing.service import BillingService
from app.core.security import utcnow

log = logging.getLogger(__name__)


@dataclass
class StreamState:
    provider: str
    model: str = ""
    status: str = "ok"
    error: str | None = None
    parts: list[str] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)


async def chat_event_stream(
    *,
    container: Container,
    runner: AgentRunner,
    history: list[Message],
    system: str,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    provider: str,
    profile: str,
) -> AsyncIterator[str]:
    started = time.perf_counter()
    state = StreamState(provider=provider)
    message_id = uuid.uuid4()
    prompt_chars = sum(len(m.content) for m in history) + len(system)

    yield sse("meta", {"session_id": str(session_id), "message_id": str(message_id), "provider": provider, "profile": profile})
    try:
        async for event in runner.run(history, system=system, preferred_provider=provider):
            if event.type == "text":
                state.parts.append(event.text)
                yield sse("token", {"text": event.text})
            elif event.type == "meta":
                state.provider = event.data["provider"]
                state.model = event.data.get("model", "")
                yield sse("provider", event.data)
            elif event.type == "fallback":
                state.status = "fallback"
                yield sse("fallback", event.data)
            elif event.type in ("tool_start", "tool_end"):
                yield sse(event.type, event.data)
            elif event.type == "usage" and event.usage:
                state.usage = state.usage + event.usage
    except AllProvidersFailed as exc:
        state.status, state.error = "error", str(exc)
        log.error("all providers failed: %s", exc)
        yield sse("error", {
            "code": "providers_unavailable",
            "message": "None of the AI providers responded. If you're running locally, check that Ollama is up.",
            "attempts": [{"provider": p, "reason": r} for p, r in exc.attempts],
        })
    except StreamInterrupted as exc:
        state.status, state.error = "error", str(exc)
        yield sse("error", {"code": "stream_interrupted", "message": f"{exc.provider} stopped responding partway through. Try again."})
    except (asyncio.CancelledError, GeneratorExit):
        state.status = "cancelled"
        log.info("client went away mid-stream after %d chunks", len(state.parts))
        raise
    except Exception as exc:  # noqa: BLE001
        state.status, state.error = "error", repr(exc)
        log.exception("unexpected failure while streaming")
        yield sse("error", {"code": "internal_error", "message": "Something went wrong on our side. It's been logged."})
    else:
        if not "".join(state.parts).strip():
            # A model can finish "successfully" having said nothing (small local ones do,
            # after a tool round). Reporting that as done would leave an empty bubble and
            # bill the user for it, so it's an error they can retry, and it isn't billed.
            state.status, state.error = "error", "model returned an empty answer"
            log.warning("empty answer from %s", state.provider)
            yield sse("error", {"code": "empty_answer", "message": f"{state.provider} finished without writing anything. Try again."})
            return
        latency = int((time.perf_counter() - started) * 1000)
        usage = _final_usage(state, prompt_chars)
        yield sse("done", {
            "message_id": str(message_id), "provider": state.provider, "model": state.model,
            "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens,
            "latency_ms": latency, "status": state.status,
        })
    finally:
        # Starlette cancels the task when the client disconnects, and anyio
        # cancellation re-fires on every await, so this has to be shielded or
        # the usage write would never land. Bounded so shutdown can't hang.
        with anyio.move_on_after(10, shield=True):
            await _persist(container, state, user_id, session_id, message_id, prompt_chars, int((time.perf_counter() - started) * 1000))


def _final_usage(state: StreamState, prompt_chars: int) -> Usage:
    usage = state.usage
    if usage.total == 0 and (state.parts or state.status != "error"):
        usage = Usage(prompt_chars // 4, estimate_tokens("".join(state.parts)))
    return usage


async def _persist(
    container: Container, state: StreamState, user_id: uuid.UUID, session_id: uuid.UUID,
    message_id: uuid.UUID, prompt_chars: int, latency_ms: int,
) -> None:
    text = "".join(state.parts)
    usage = _final_usage(state, prompt_chars)
    try:
        async with container.sessionmaker() as db:
            # Always leave a reply row, even an empty one, so the history never shows a
            # question with nothing after it and no explanation. Empty rows are skipped
            # when the conversation is fed back to the model.
            if text or state.status in ("error", "cancelled"):
                db.add(ChatMessage(
                    id=message_id, session_id=session_id, role="assistant",
                    content=text or ("" if state.status == "cancelled" else "(no response)"),
                    provider=state.provider, model=state.model,
                    status=state.status,
                ))
            session = await db.get(ChatSession, session_id)
            if session is not None:
                session.updated_at = utcnow()
            await db.commit()
            await BillingService(db, container.cache).record(
                user_id=user_id, session_id=session_id, provider=state.provider, model=state.model,
                input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
                status=state.status, latency_ms=latency_ms, error=state.error,
            )
    except Exception:  # noqa: BLE001
        # the user already has their answer; losing a usage row is bad but not
        # worth an exception nobody can see. Loud log so it gets noticed.
        log.exception("failed to persist chat result for session %s", session_id)
