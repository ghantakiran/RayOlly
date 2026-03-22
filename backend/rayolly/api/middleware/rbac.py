"""RBAC enforcement -- check user role before allowing write operations."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
WRITE_ROLES = {"admin", "editor", "owner"}

# Paths that allow writes without role checks (auth endpoints, data ingestion)
PUBLIC_WRITE_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/logs/ingest",
    "/api/v1/metrics/ingest",
    "/api/v1/events/ingest",
    "/v1/logs",
    "/v1/metrics",
    "/v1/traces",
    "/services/collector/event",
    "/_bulk",
    "/loki/api/v1/push",
    "/api/v1/prometheus/write",
}


class RBACMiddleware(BaseHTTPMiddleware):
    """Enforce role-based access control on write operations.

    This middleware runs after TenantMiddleware, which sets
    ``request.state.user_role`` from the JWT or API key lookup.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.method in WRITE_METHODS:
            # Skip ingestion and auth endpoints (authenticated via API key or open)
            if request.url.path in PUBLIC_WRITE_PATHS:
                return await call_next(request)

            role = getattr(request.state, "user_role", None) or "viewer"
            if role not in WRITE_ROLES:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Insufficient permissions"},
                )

        return await call_next(request)
