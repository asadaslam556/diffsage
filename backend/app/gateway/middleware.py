"""The API gateway.

Two plain ASGI middlewares (not BaseHTTPMiddleware, which has a history of
misbehaving with streaming responses):

RequestContextMiddleware  request id, access log, a couple of safety headers
GatewayMiddleware         route lookup, token check, rate limit

Order in main.py: CORS -> RequestContext -> Gateway -> service routers.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from typing import Any

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import AuthError
from app.core.logging import request_id_var, user_id_var
from app.core.security import decode_access_token
from app.gateway.routes import agent_may_call, match_route

log = logging.getLogger("app.gateway")
access_log = logging.getLogger("app.access")

_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def error_response(status: int, code: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": message, "request_id": request_id_var.get()}},
        status_code=status,
        headers=headers,
    )


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get("x-request-id", "")
        request_id = incoming if _SAFE_REQUEST_ID.match(incoming) else uuid.uuid4().hex[:16]
        rid_token = request_id_var.set(request_id)
        uid_token = user_id_var.set("-")
        started = time.perf_counter()
        status = {"code": 500}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("Referrer-Policy", "same-origin")
            await send(message)

        started_response = False

        async def tracked_send(message: Message) -> None:
            nonlocal started_response
            if message["type"] == "http.response.start":
                started_response = True
            await send_wrapper(message)

        try:
            await self.app(scope, receive, tracked_send)
        except Exception:
            # Answer unhandled errors here rather than in Starlette's outermost handler,
            # which runs after the request id below has been reset. This way the 500 body,
            # its X-Request-ID header and the traceback all carry the same id.
            log.exception("unhandled error")
            if started_response:
                raise  # mid-stream: nothing sensible to send, let the server close it
            await error_response(500, "internal_error", "Something went wrong on our side. It's been logged.")(
                scope, receive, tracked_send
            )
        finally:
            # for streams this measures the whole stream, which is what we want
            access_log.info(
                "%s %s -> %s in %dms",
                scope["method"], scope["path"], status["code"], int((time.perf_counter() - started) * 1000),
                extra={"status": status["code"], "path": scope["path"], "method": scope["method"]},
            )
            request_id_var.reset(rid_token)
            user_id_var.reset(uid_token)


class GatewayMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith("/api"):
            await self.app(scope, receive, send)
            return

        route = match_route(scope["path"])
        if route is None:
            await error_response(404, "no_route", f"No API route for {scope['path']}")(scope, receive, send)
            return
        if scope["method"] == "OPTIONS":  # CORS preflight, handled further out
            await self.app(scope, receive, send)
            return

        container = scope["app"].state.container
        settings = container.settings
        state = scope.setdefault("state", {})
        state["service"] = route.service
        headers = Headers(scope=scope)

        user_id: str | None = None
        if not route.public:
            auth = headers.get("authorization", "")
            scheme, _, token = auth.partition(" ")
            if scheme.lower() != "bearer" or not token:
                await error_response(401, "missing_token", "Sign in first.", {"WWW-Authenticate": "Bearer"})(scope, receive, send)
                return
            try:
                payload = decode_access_token(token.strip(), settings.jwt_secret, settings.jwt_algorithm)
            except AuthError as exc:
                await error_response(401, exc.code, exc.message, {"WWW-Authenticate": "Bearer"})(scope, receive, send)
                return
            if payload.scope == "agent" and not agent_may_call(scope["method"], scope["path"]):
                log.warning("agent token tried %s %s, blocked", scope["method"], scope["path"])
                await error_response(403, "agent_scope", "Agent tokens can't call this endpoint.")(scope, receive, send)
                return
            user_id = str(payload.user_id)
            state["user_id"] = user_id
            state["token_scope"] = payload.scope
            user_id_var.set(user_id)

        rule = settings.rate_limits.get(route.rate_bucket) or settings.rate_limits["default"]
        subject = f"u:{user_id}" if user_id else f"ip:{_client_ip(scope, headers, settings.trust_proxy_headers)}"
        result: Any = None
        try:
            result = await container.rate_limiter.hit(f"{route.rate_bucket}:{subject}", rule)
        except Exception as exc:  # noqa: BLE001
            if not settings.rate_limit_fail_open:
                log.error("rate limiter unavailable, rejecting (fail_open=false): %s", exc)
                await error_response(503, "rate_limiter_down", "Service temporarily unavailable.")(scope, receive, send)
                return
            log.warning("rate limiter unavailable, letting request through: %s", exc)

        if result is not None and not result.allowed:
            log.info("rate limited %s on %s", subject, route.rate_bucket)
            await error_response(
                429, "rate_limited",
                f"Too many requests. Try again in {result.reset_after}s.",
                {**result.headers(), "Retry-After": str(result.reset_after)},
            )(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start" and result is not None:
                response_headers = MutableHeaders(scope=message)
                for key, value in result.headers().items():
                    response_headers[key] = value
            await send(message)

        await self.app(scope, receive, send_wrapper)


def _client_ip(scope: Scope, headers: Headers, trust_proxy: bool) -> str:
    if trust_proxy:
        # Rightmost hop, not leftmost. Everything to the left of our own proxy's
        # entry was written by the client, and trusting that would let anyone
        # dodge the per-IP login limit by sending a fresh fake address each time.
        forwarded = headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[-1].strip()
    client = scope.get("client")
    return client[0] if client else "unknown"
