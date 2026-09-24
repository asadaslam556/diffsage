"""End-to-end-ish tests: real FastAPI app, real gateway middleware, SQLite,
fake models. If these pass, the request path from the diagram works:
gateway -> business / agent / billing -> storage -> streamed response.
"""

from __future__ import annotations

import dataclasses
import uuid

import pytest

from app.core.config import RateLimitRule
from app.agent.types import StreamEvent
from app.db.models import UsageRecord
from tests.conftest import PASSWORD, bearer, parse_sse, register
from tests.fakes import text, tool_call

# --- auth -----------------------------------------------------------------------


async def test_register_login_refresh_logout(client):
    body = await register(client)
    assert body["user"]["plan_id"] == "free"
    assert "ds_refresh" in client.cookies

    # can't sign up twice with the same email (case doesn't matter)
    dup = await client.post("/api/auth/register", json={"email": "DEV@example.com", "password": PASSWORD})
    assert dup.status_code == 409

    bad = await client.post("/api/auth/login", json={"email": "dev@example.com", "password": "not the password"})
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "bad_credentials"

    good = await client.post("/api/auth/login", json={"email": "dev@example.com", "password": PASSWORD})
    assert good.status_code == 200

    refreshed = await client.post("/api/auth/refresh")
    assert refreshed.status_code == 200
    me = await client.get("/api/app/me", headers=bearer(refreshed.json()["access_token"]))
    assert me.json()["email"] == "dev@example.com"

    assert (await client.post("/api/auth/logout")).status_code == 204
    assert (await client.post("/api/auth/refresh")).status_code == 401


async def test_refresh_token_reuse_revokes_everything(client, monkeypatch):
    from app.services.business import auth_router

    await register(client)
    stolen = client.cookies.get("ds_refresh")
    assert (await client.post("/api/auth/refresh")).status_code == 200

    # no grace period, so replaying the old token counts as reuse right away
    monkeypatch.setattr(auth_router, "REUSE_GRACE", auth_router.timedelta(0))
    client.cookies.clear()
    replay = await client.post("/api/auth/refresh", headers={"Cookie": f"ds_refresh={stolen}"})
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "refresh_reused"


async def test_protected_routes_need_a_token(client):
    response = await client.get("/api/app/me")
    assert response.status_code == 401
    error = response.json()["error"]
    assert error["code"] == "missing_token"
    assert error["request_id"]  # every error carries one, handy for support

    forged = await client.get("/api/app/me", headers=bearer("not.a.jwt"))
    assert forged.status_code == 401


async def test_validation_errors_are_readable(client):
    response = await client.post("/api/auth/register", json={"email": "nope", "password": "short"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


async def test_unknown_api_routes_stop_at_the_gateway(client, auth):
    response = await client.get("/api/definitely/not/here", headers=auth)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "no_route"


# --- gateway rate limiting --------------------------------------------------------


async def test_rate_limit_kicks_in_with_headers(client, container):
    container.settings = dataclasses.replace(
        container.settings,
        rate_limits={**container.settings.rate_limits, "auth": RateLimitRule(2, 60)},
    )
    creds = {"email": "rl@example.com", "password": PASSWORD}
    first = await client.post("/api/auth/login", json=creds)
    assert first.headers["X-RateLimit-Limit"] == "2"
    await client.post("/api/auth/login", json=creds)
    blocked = await client.post("/api/auth/login", json=creds)
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert int(blocked.headers["Retry-After"]) >= 1


async def test_agent_tokens_cant_call_arbitrary_endpoints(client, container):
    from app.core.security import create_access_token

    body = await register(client)
    token = create_access_token(body["user"]["id"], container.settings.jwt_secret, minutes=5, scope="agent")
    assert (await client.get("/api/app/reviews/recent", headers=bearer(token))).status_code == 200
    blocked = await client.post("/api/agent/chat", json={"message": "hi"}, headers=bearer(token))
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "agent_scope"


# --- agent streaming --------------------------------------------------------------


async def chat(client, auth, message="def f(x): return x*2", **extra):
    response = await client.post("/api/agent/chat", json={"message": message, **extra}, headers=auth)
    return response, parse_sse(response.text) if response.status_code == 200 else []


async def test_chat_streams_tokens_and_records_usage(client, auth, container):
    response, events = await chat(client, auth)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    names = [name for name, _ in events]
    assert names[0] == "meta"
    assert names[-1] == "done"
    assert names.count("token") == 3
    assert "".join(d["text"] for n, d in events if n == "token") == "Looks good to me."
    done = events[-1][1]
    assert done["provider"] == "ollama" and done["status"] == "ok"

    session_id = events[0][1]["session_id"]
    detail = (await client.get(f"/api/app/sessions/{session_id}", headers=auth)).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][1]["content"] == "Looks good to me."

    billing = (await client.get("/api/billing/me", headers=auth)).json()
    assert billing["usage"]["requests_today"] == 1
    assert billing["usage"]["tokens_this_month"] == 15  # 10 in + 5 out from the fake

    history = (await client.get("/api/billing/usage?days=7", headers=auth)).json()
    assert sum(day["requests"] for day in history["daily"]) == 1


async def test_follow_up_goes_to_the_same_session_with_history(client, auth, container):
    _, first = await chat(client, auth, "first question")
    session_id = first[0][1]["session_id"]
    _, second = await chat(client, auth, "and a follow-up", session_id=session_id)
    assert second[0][1]["session_id"] == session_id

    last_call = container.providers["ollama"].calls[-1]["messages"]
    assert [m.role for m in last_call] == ["user", "assistant", "user"]


async def test_free_plan_is_capped_per_day(client, auth, container):
    user_id = uuid.UUID((await client.get("/api/app/me", headers=auth)).json()["id"])
    async with container.sessionmaker() as db:
        for _ in range(25):
            db.add(UsageRecord(user_id=user_id, provider="ollama", model="m", status="ok", input_tokens=1, output_tokens=1))
        await db.commit()

    response, _ = await chat(client, auth)
    assert response.status_code == 402
    assert response.json()["error"]["code"] == "daily_limit_reached"
    assert "Retry-After" in response.headers


async def test_free_plan_cant_pick_a_paid_provider(client, auth):
    response, _ = await chat(client, auth, provider="anthropic")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "provider_not_in_plan"

    patch = await client.patch("/api/app/me", json={"preferred_provider": "anthropic"}, headers=auth)
    assert patch.status_code == 403


async def test_oversized_input_is_rejected_before_streaming(client, auth):
    response, _ = await chat(client, auth, message="x" * 13_000)  # free plan takes 12k
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "input_too_large"


async def test_upgrade_then_switch_provider(client, auth, container):
    upgraded = await client.post("/api/billing/plan", json={"plan_id": "pro"}, headers=auth)
    assert upgraded.status_code == 200
    assert upgraded.json()["plan"]["id"] == "pro"

    # deepseek has no API key in the test setup
    missing_key = await client.patch("/api/app/me", json={"preferred_provider": "deepseek"}, headers=auth)
    assert missing_key.status_code == 422
    assert missing_key.json()["error"]["code"] == "provider_not_configured"

    ok = await client.patch("/api/app/me", json={"preferred_provider": "anthropic"}, headers=auth)
    assert ok.status_code == 200 and ok.json()["preferred_provider"] == "anthropic"

    _, events = await chat(client, auth)
    assert events[-1][1]["provider"] == "anthropic"
    assert len(container.providers["anthropic"].calls) == 1
    assert container.providers["ollama"].calls == []

    listing = (await client.get("/api/agent/providers", headers=auth)).json()
    assert listing["can_switch"] and listing["selected"] == "anthropic"

    # dropping back to free clears the paid preference
    await client.post("/api/billing/plan", json={"plan_id": "free"}, headers=auth)
    assert (await client.get("/api/app/me", headers=auth)).json()["preferred_provider"] is None


async def test_paid_provider_failure_falls_back_to_ollama(client, auth, container):
    await client.post("/api/billing/plan", json={"plan_id": "pro"}, headers=auth)
    container.providers["anthropic"].fail = "HTTP 529: overloaded"

    _, events = await chat(client, auth, provider="anthropic")
    names = [n for n, _ in events]
    assert "fallback" in names
    fallback = dict(events)["fallback"]
    assert fallback["from"] == "anthropic" and fallback["to"] == "ollama"
    assert events[-1][0] == "done"
    assert events[-1][1]["provider"] == "ollama"
    assert events[-1][1]["status"] == "fallback"


async def test_free_plan_never_falls_back_to_a_paid_provider(client, auth, container):
    container.router.fallbacks = ("anthropic", "ollama")
    container.providers["ollama"].fail = "couldn't connect"
    _, events = await chat(client, auth)
    assert events[-1][1]["code"] == "providers_unavailable"
    assert container.providers["anthropic"].calls == []


async def test_everything_down_gives_a_clean_error_event(client, auth, container):
    container.providers["ollama"].fail = "couldn't connect"
    response, events = await chat(client, auth)
    assert response.status_code == 200  # the stream had already started
    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "providers_unavailable"

    # failed requests don't count against the quota
    billing = (await client.get("/api/billing/me", headers=auth)).json()
    assert billing["usage"]["requests_today"] == 0


async def test_mid_stream_failure_is_reported_not_spliced(client, auth, container):
    container.providers["ollama"].fail_after = 1
    _, events = await chat(client, auth)
    assert [n for n, _ in events].count("token") == 1
    assert events[-1] == ("error", {"code": "stream_interrupted", "message": events[-1][1]["message"]})


# --- the "agent may call again" loop ------------------------------------------------


async def test_agent_tool_calls_back_through_the_gateway(client, auth, container):
    upload = await client.post(
        "/api/app/documents",
        json={"filename": "STYLE.md", "content": "Use snake_case for every function name. Never use camelCase."},
        headers=auth,
    )
    assert upload.status_code == 201

    container.providers["ollama"].rounds = [
        [tool_call("search_guidelines", query="function naming snake_case")],
        text("Rename ", "fooBar ", "to foo_bar."),
    ]
    _, events = await chat(client, auth, "def fooBar(): pass")
    names = [n for n, _ in events]
    assert "tool_start" in names and "tool_end" in names
    assert dict(events)["tool_end"]["ok"] is True

    # second model round got the guideline text back as a tool result
    second_round = container.providers["ollama"].calls[1]["messages"]
    tool_replies = [m for m in second_round if m.role == "tool"]
    assert tool_replies and "snake_case" in tool_replies[0].content


async def test_tools_with_nothing_behind_them_are_not_offered(client, auth, container):
    # a brand-new user has no guidelines and no earlier reviews, so both lookups
    # could only come back empty; offering them just buys an extra model round
    container.providers["ollama"].rounds = [text("Looks fine.")]
    await chat(client, auth, "def f(): pass")
    assert container.providers["ollama"].calls[0]["tools"] is None


async def test_documents_and_sessions_are_private(client, container):
    alice = bearer((await register(client, "alice@example.com"))["access_token"])
    _, events = await chat(client, alice)
    session_id = events[0][1]["session_id"]

    client.cookies.clear()
    bob = bearer((await register(client, "bob@example.com"))["access_token"])
    assert (await client.get(f"/api/app/sessions/{session_id}", headers=bob)).status_code == 404
    assert (await client.get("/api/app/sessions", headers=bob)).json() == []


@pytest.mark.parametrize("path", ["/api/billing/plans", "/api/agent/profiles"])
async def test_catalog_endpoints(client, auth, path):
    response = await client.get(path, headers=auth)
    assert response.status_code == 200
    assert len(response.json()) >= 3


async def test_an_empty_answer_is_an_error_not_a_silent_success(client, auth, container):
    container.providers["ollama"].rounds = [[StreamEvent.usage_report(40, 0)]]
    _, events = await chat(client, auth, "def f(): pass")
    assert events[-1][0] == "error" and events[-1][1]["code"] == "empty_answer"
    usage = (await client.get("/api/billing/me", headers=auth)).json()["usage"]
    assert usage["requests_today"] == 0  # not billed
