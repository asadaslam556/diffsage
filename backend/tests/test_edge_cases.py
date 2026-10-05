"""Edge cases found in review: races, stale data, and paths that used to fail quietly."""

from __future__ import annotations

import asyncio
import dataclasses
import uuid

import pytest
from sqlalchemy import delete, event, select

from app.agent.providers.router import ProviderRouter, StreamInterrupted
from app.agent.runner import AgentRunner
from app.agent.tools import ToolContext, ToolExecutor
from app.agent.types import Message, StreamEvent, Usage
from app.core.config import RateLimitRule
from app.db.models import ChatMessage, Plan, UsageRecord
from app.services.agent.stream import StreamState, _final_usage
from app.vectorstore.store import QdrantStore, VectorStoreError
from tests.conftest import bearer, parse_sse, register
from tests.fakes import FakeGateway, FakeProvider, text, tool_call


async def chat(client, auth, message="def f(x): return x*2", **extra):
    response = await client.post("/api/agent/chat", json={"message": message, **extra}, headers=auth)
    return response, parse_sse(response.text) if response.status_code == 200 else []


async def user_id(client, auth) -> uuid.UUID:
    return uuid.UUID((await client.get("/api/app/me", headers=auth)).json()["id"])


# --- auth ---------------------------------------------------------------------------


async def test_two_tabs_refreshing_at_once_get_a_retryable_answer(client):
    await register(client)
    old = client.cookies.get("ds_refresh")
    assert (await client.post("/api/auth/refresh")).status_code == 200

    # the second tab still sent the old cookie: not theft, just a race
    client.cookies.clear()
    raced = await client.post("/api/auth/refresh", headers={"Cookie": f"ds_refresh={old}"})
    assert raced.status_code == 401
    assert raced.json()["error"]["code"] == "refresh_raced"


async def test_sign_up_works_when_the_plans_were_never_synced(client, container):
    @event.listens_for(container.engine.sync_engine, "connect")
    def foreign_keys_on(conn, _):  # SQLite ignores foreign keys unless asked
        conn.execute("PRAGMA foreign_keys=ON")

    async with container.sessionmaker() as db:
        await db.execute(delete(Plan))
        await db.commit()

    # used to come back as 409 "email already exists"
    await register(client, "first@example.com")
    async with container.sessionmaker() as db:
        assert await db.scalar(select(Plan.id).where(Plan.id == "free")) == "free"


async def test_refresh_and_sign_out_dont_use_up_sign_in_attempts(client, container):
    await register(client)
    container.settings = dataclasses.replace(
        container.settings, rate_limits={**container.settings.rate_limits, "auth": RateLimitRule(1, 60)},
    )
    for _ in range(3):
        assert (await client.post("/api/auth/refresh")).status_code == 200


# --- agent service ---------------------------------------------------------------------


async def test_unknown_provider_is_refused_before_the_stream(client, auth, container):
    async with container.sessionmaker() as db:
        await db.execute(Plan.__table__.update().values(allowed_providers=["*"], can_switch_provider=True))
        await db.commit()
    response, _ = await chat(client, auth, provider="nope")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unknown_provider"


async def test_unknown_profile_names_the_profile(client, auth):
    response, _ = await chat(client, auth, profile="poet")
    assert response.status_code == 422
    assert "'poet'" in response.json()["error"]["message"]


async def test_reviews_still_streaming_count_against_the_daily_cap(client, auth, container):
    uid = await user_id(client, auth)
    async with container.sessionmaker() as db:
        for _ in range(24):
            db.add(UsageRecord(user_id=uid, provider="ollama", model="m", status="ok", input_tokens=1, output_tokens=1))
        await db.commit()

    # one review of the 25 is already running in another tab
    await container.cache.incr(f"inflight:{uid}", 1, 60)
    response, _ = await chat(client, auth)
    assert response.status_code == 402
    assert await container.cache.incr(f"inflight:{uid}", 0, 60) == 1  # the refused one gave its slot back


async def test_a_finished_review_gives_its_slot_back(client, auth, container):
    _, events = await chat(client, auth)
    assert events[-1][0] == "done"
    assert await container.cache.incr(f"inflight:{await user_id(client, auth)}", 0, 60) == 0


async def test_past_reviews_tool_skips_failed_replies(client, auth, container):
    await chat(client, auth)
    async with container.sessionmaker() as db:
        await db.execute(ChatMessage.__table__.update().where(ChatMessage.role == "assistant").values(status="error"))
        await db.commit()
    await chat(client, auth, "another one")
    tools = container.providers["ollama"].calls[-1]["tools"] or []
    assert "get_past_reviews" not in [t.name for t in tools]


async def test_provider_list_has_health_without_calling_health_first(client, auth):
    body = (await client.get("/api/agent/providers", headers=auth)).json()
    ollama = next(p for p in body["providers"] if p["name"] == "ollama")
    assert ollama["health"]["status"] == "ok"


async def test_usage_chart_counts_what_the_quota_counts(client, auth, container):
    uid = await user_id(client, auth)
    async with container.sessionmaker() as db:
        db.add(UsageRecord(user_id=uid, provider="ollama", model="m", status="error", input_tokens=0, output_tokens=0))
        db.add(UsageRecord(user_id=uid, provider="ollama", model="m", status="ok", input_tokens=3, output_tokens=2))
        await db.commit()
    history = (await client.get("/api/billing/usage?days=1", headers=auth)).json()
    assert history["daily"][-1]["requests"] == 1
    assert len(history["recent"]) == 2  # the failure is still listed, just not counted


async def test_agent_tool_calls_have_their_own_rate_counter(client, container):
    from app.core.security import create_access_token

    body = await register(client)
    container.settings = dataclasses.replace(
        container.settings, rate_limits={**container.settings.rate_limits, "default": RateLimitRule(1, 60)},
    )
    agent = create_access_token(body["user"]["id"], container.settings.jwt_secret, minutes=5, scope="agent")
    assert (await client.get("/api/app/reviews/recent", headers=bearer(agent))).status_code == 200
    # the browser's own allowance is untouched by the agent's call
    assert (await client.get("/api/app/me", headers=bearer(body["access_token"]))).status_code == 200


# --- agent loop and stream ---------------------------------------------------------------


def run(provider, max_rounds=3):
    router = ProviderRouter({provider.name: provider}, default=provider.name, fallback=provider.name)
    executor = ToolExecutor(("get_past_reviews",), ToolContext("u", "s", FakeGateway({"/api/app/reviews/recent": {"reviews": []}})))
    runner = AgentRunner(router, executor, max_rounds=max_rounds)

    async def go():
        events: list = []
        try:
            async for e in runner.run([Message("user", "review")], system="s", preferred_provider=None):
                events.append(e)
        except StreamInterrupted:
            events.append("interrupted")
        return events

    return asyncio.run(go())


def test_a_tool_call_on_the_last_round_is_ignored_not_run():
    provider = FakeProvider("ollama", [[tool_call("get_past_reviews", limit=1)], text("Partial answer.") + [tool_call("get_past_reviews", limit=2)]])
    events = run(provider, max_rounds=1)
    assert [e.type for e in events].count("tool_start") == 1  # only the first round's call ran
    assert "Partial answer." in "".join(e.text for e in events if e.type == "text")


def test_usage_from_earlier_rounds_survives_a_later_failure():
    provider = FakeProvider(
        "ollama",
        [[tool_call("get_past_reviews"), StreamEvent.usage_report(20, 5)], text("half ", "an ", "answer")],
        fail_after=2,
    )
    events = run(provider)
    assert events[-1] == "interrupted"
    assert events[-2].type == "usage" and events[-2].usage.total == 25


@pytest.mark.parametrize("status", ["cancelled", "error"])
def test_nothing_written_costs_no_tokens(status):
    assert _final_usage(StreamState(provider="ollama", status=status), prompt_chars=4000) == Usage()


# --- vector store -----------------------------------------------------------------------


async def test_qdrant_collection_with_the_wrong_size_is_a_clear_error():
    httpx = pytest.importorskip("httpx")

    def handler(request):
        return httpx.Response(200, json={"result": {"config": {"params": {"vectors": {"size": 384, "distance": "Cosine"}}}}})

    client = httpx.AsyncClient(base_url="http://qdrant", transport=httpx.MockTransport(handler))
    store = QdrantStore("http://qdrant", "guidelines_ollama_768", 768, client=client)
    with pytest.raises(VectorStoreError, match="384-d"):
        await store.ensure_ready()
    await client.aclose()

