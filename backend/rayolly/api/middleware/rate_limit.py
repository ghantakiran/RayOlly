"""Rate limiting middleware using Redis sliding window."""
import time

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = structlog.get_logger(__name__)

# Tier-based rate limits (requests per minute)
RATE_LIMITS = {
    "free": 60,
    "pro": 600,
    "enterprise": 6000,
    "default": 300,
}

class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip rate limiting for health checks and auth
        if request.url.path in ("/healthz", "/readyz") or request.url.path.startswith("/api/v1/auth/"):
            return await call_next(request)

        tenant_id = getattr(request.state, "tenant_id", None)
        if not tenant_id:
            return await call_next(request)

        redis = getattr(request.app.state, "redis", None)
        if not redis:
            return await call_next(request)

        # Sliding window rate limiting
        key = f"ratelimit:{tenant_id}:{int(time.time()) // 60}"
        try:
            current = await redis.incr(key)
            if current == 1:
                await redis.expire(key, 120)  # 2 minute TTL

            limit = RATE_LIMITS.get("default", 300)  # TODO: look up tenant tier

            if current > limit:
                logger.warning("rate_limit_exceeded", tenant_id=tenant_id, current=current, limit=limit)
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded", "retry_after": 60},
                    headers={"Retry-After": "60", "X-RateLimit-Limit": str(limit), "X-RateLimit-Remaining": "0"}
                )

            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(limit)
            response.headers["X-RateLimit-Remaining"] = str(max(0, limit - current))
            return response
        except Exception:
            # If Redis fails, allow the request (fail open)
            return await call_next(request)
