"""App factory.

    uvicorn app.main:create_app --factory

Tests call create_app(container=...) with their own in-memory wiring.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import InterfaceError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.container import Container, build_container, close_container
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.logging import configure_logging
from app.gateway.middleware import GatewayMiddleware, RequestContextMiddleware, error_response
from app.services.agent.router import router as agent_router
from app.services.billing.router import router as billing_router
from app.services.business.app_router import router as app_router
from app.services.business.auth_router import router as auth_router
from app.services.health.router import router as health_router

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    settings = settings or (container.settings if container else get_settings())
    configure_logging(settings.log_level, settings.log_format)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        owns_container = container is None
        app.state.container = container or await build_container(settings)
        log.info(
            "%s started (env=%s, default provider=%s, fallback=%s)",
            settings.app_name, settings.environment, settings.default_provider, settings.fallback_provider,
        )
        try:
            yield
        finally:
            if owns_container:
                await close_container(app.state.container)
            log.info("shut down cleanly")

    app = FastAPI(
        title=f"{settings.app_name} API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )
    if container is not None:
        # set now as well as in lifespan, so tests that skip lifespan still work
        app.state.container = container

    # every service sits behind the same gateway; see app/gateway/routes.py
    for router in (health_router, auth_router, app_router, agent_router, billing_router):
        app.include_router(router)

    # added innermost first: CORS ends up outermost, the gateway innermost
    app.add_middleware(GatewayMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset", "Retry-After"],
    )
    _register_error_handlers(app)
    return app


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError):
        if exc.status_code >= 500:
            log.error("%s: %s", exc.code, exc.message)
        return error_response(exc.status_code, exc.code, exc.message, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        problems = []
        for err in exc.errors():
            where = ".".join(str(p) for p in err.get("loc", ()) if p != "body")
            msg = str(err.get("msg", "invalid")).removeprefix("Value error, ")
            problems.append(f"{where}: {msg}" if where else msg)
        return error_response(422, "validation_failed", "; ".join(problems) or "Invalid request.")

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        return error_response(exc.status_code, "http_error", str(exc.detail), getattr(exc, "headers", None))

    async def database_error(_: Request, exc: Exception):
        log.error("database unreachable: %s", exc)
        return error_response(503, "database_unavailable", "The database isn't reachable right now. Try again shortly.")

    # connection-level failures only; constraint violations etc. are real bugs and should 500
    for exc_type in (OperationalError, InterfaceError):
        app.add_exception_handler(exc_type, database_error)

    async def backend_unreachable(_: Request, exc: Exception):
        # Raw network errors that nothing wrapped: asyncpg raises socket.gaierror straight
        # through SQLAlchemy when the database host can't even be resolved. Everything the
        # routes call on purpose (Redis, Qdrant, model APIs) catches its own errors, so
        # reaching here means a backing service is gone, not that the code is broken.
        log.error("backing service unreachable: %s: %s", exc.__class__.__name__, exc)
        return error_response(503, "service_unavailable", "A service this needs isn't reachable right now. Try again shortly.")

    for exc_type in (OSError, TimeoutError):  # OSError covers ConnectionError and gaierror
        app.add_exception_handler(exc_type, backend_unreachable)

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        log.exception("unhandled error")
        return error_response(500, "internal_error", "Something went wrong on our side. It's been logged.")

