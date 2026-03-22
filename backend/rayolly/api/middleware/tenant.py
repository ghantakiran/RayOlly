from __future__ import annotations

from datetime import UTC

import jwt
import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from rayolly.core.config import get_settings
from rayolly.services.metadata.auth import AuthService
from rayolly.services.metadata.repositories import APIKeyRepository

logger = structlog.get_logger(__name__)

PUBLIC_PATHS = {"/healthz", "/readyz", "/docs", "/openapi.json", "/redoc"}
PUBLIC_PREFIXES = ("/api/v1/auth/", "/scim/v2/")


class TenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path in PUBLIC_PATHS or any(
            request.url.path.startswith(p) for p in PUBLIC_PREFIXES
        ):
            request.state.tenant_id = None
            request.state.user_role = None
            return await call_next(request)

        tenant_id, user_role = await self._extract_tenant(request)
        if not tenant_id:
            return JSONResponse(
                status_code=401,
                content={"detail": "Tenant identification required"},
            )

        request.state.tenant_id = tenant_id
        request.state.user_role = user_role
        return await call_next(request)

    async def _extract_tenant(self, request: Request) -> tuple[str | None, str | None]:
        """Return (tenant_id, user_role) or (None, None)."""
        tenant_header = request.headers.get("X-RayOlly-Tenant")
        if tenant_header:
            return tenant_header, None

        api_key = request.headers.get("X-RayOlly-API-Key")
        if api_key:
            tenant_id = await self._resolve_tenant_from_api_key(api_key, request.app.state)
            if tenant_id:
                return tenant_id, None
            return None, None

        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return self._resolve_tenant_from_jwt(auth_header.removeprefix("Bearer "))

        return None, None

    async def _resolve_tenant_from_api_key(self, api_key: str, app_state) -> str | None:
        """Look up the API key in PostgreSQL and return the associated tenant_id."""
        db_factory = getattr(app_state, "db_session_factory", None)
        if db_factory is None:
            return None

        if len(api_key) < 8:
            return None

        try:
            async with db_factory() as session:
                api_key_repo = APIKeyRepository(session)
                prefix = api_key[:8]
                db_key = await api_key_repo.get_by_prefix(prefix)
                if db_key is None:
                    return None

                # Verify full key against stored bcrypt hash
                if not AuthService.verify_password(api_key, db_key.key_hash):
                    return None

                # Check expiration and active status
                if not db_key.is_active:
                    return None

                from datetime import datetime
                if db_key.expires_at is not None:
                    if datetime.now(UTC) >= db_key.expires_at:
                        return None

                # Update last-used timestamp
                await api_key_repo.update_last_used(db_key.id)
                await session.commit()

                return db_key.tenant_id
        except Exception as e:
            logger.warning("api_key_lookup_failed", error=str(e))
            return None

    def _resolve_tenant_from_jwt(self, token: str) -> tuple[str | None, str | None]:
        """Return (tenant_id, role) from a JWT token."""
        settings = get_settings()
        try:
            payload = jwt.decode(
                token,
                settings.auth.jwt_secret,
                algorithms=[settings.auth.jwt_algorithm],
            )
            return payload.get("tenant_id"), payload.get("role")
        except jwt.InvalidTokenError:
            return None, None
