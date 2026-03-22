from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from rayolly.core.health import check_health

router = APIRouter()


@router.get("/healthz")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readiness(request: Request) -> dict[str, Any]:
    result = await check_health(request.app.state)

    # Map component statuses for backward-compatible "checks" format
    checks: dict[str, str] = {}
    for name, info in result["components"].items():
        status = info["status"]
        if status == "healthy":
            checks[name] = "ok"
        elif status == "not_configured":
            checks[name] = "not_configured"
        else:
            checks[name] = f"error: {info.get('error', 'unknown')}"

    all_ok = all(v == "ok" for v in checks.values())
    return {"status": "ok" if all_ok else "degraded", "checks": checks}


@router.get("/api/v1/status")
async def platform_status(request: Request) -> dict[str, Any]:
    from rayolly import __version__

    result = await check_health(request.app.state)
    return {
        "version": __version__,
        "status": result["status"],
        "components": result["components"],
    }
