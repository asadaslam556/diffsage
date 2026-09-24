from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.container import Container
from app.services.deps import get_container
from app.services.health.checks import run_health_checks

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("/live")
async def live() -> dict:
    """Liveness only: the process is up and serving. Use /api/health for readiness."""
    return {"status": "ok"}


@router.get("")
async def ready(container: Container = Depends(get_container)) -> JSONResponse:
    report = await run_health_checks(container)
    # 503 only when we genuinely can't serve; degraded still takes traffic
    return JSONResponse(report, status_code=503 if report["status"] == "down" else 200)
