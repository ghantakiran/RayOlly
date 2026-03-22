from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from functools import lru_cache
from typing import TYPE_CHECKING, Any

import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from redis.asyncio import Redis

from rayolly.core.config import Settings

if TYPE_CHECKING:
    import nats
    from clickhouse_driver import Client as ClickHouseClient


@lru_cache
def get_settings() -> Settings:
    return Settings()


async def get_clickhouse(request: Request) -> AsyncGenerator[ClickHouseClient, None]:
    client = request.app.state.clickhouse
    yield client


async def get_nats(request: Request) -> nats.NATS:
    return request.app.state.nats


async def get_redis(request: Request) -> Redis:
    return request.app.state.redis


async def get_current_tenant(
    request: Request,
    x_rayolly_tenant: str | None = Header(None),
) -> str:
    if x_rayolly_tenant:
        return x_rayolly_tenant

    if hasattr(request.state, "tenant_id") and request.state.tenant_id:
        return request.state.tenant_id

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Tenant identification required",
    )


async def get_current_user(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
        )

    token = auth_header.removeprefix("Bearer ")
    try:
        payload = jwt.decode(
            token,
            settings.auth.jwt_secret,
            algorithms=[settings.auth.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    return payload


# ---------------------------------------------------------------------------
# Stub dependency providers for use outside of a request context
# (e.g. lazy imports inside route-level helpers in apm.py).
# Replace with real implementations backed by app state or a DI container.
# ---------------------------------------------------------------------------

async def get_clickhouse_client() -> Any:
    """Return a ClickHouse client outside of a request context.

    This is a stub — production code should use ``get_clickhouse`` with
    FastAPI ``Depends`` instead.
    """
    return None


async def get_s3_client() -> Any:
    """Return an S3-compatible client.  Stub — returns *None*."""
    return None


async def get_anomaly_detector() -> Any:
    """Return an anomaly-detector service instance.  Stub — returns *None*."""
    return None


class RateLimiter:
    def __init__(self, requests_per_second: int = 100, burst: int = 200):
        self.rps = requests_per_second
        self.burst = burst

    async def __call__(
        self,
        request: Request,
        redis: Redis = Depends(get_redis),
    ) -> None:
        tenant_id = getattr(request.state, "tenant_id", "anonymous")
        key = f"ratelimit:{tenant_id}:{request.url.path}"
        now = time.time()

        pipe = redis.pipeline()
        pipe.zremrangebyscore(key, 0, now - 1.0)
        pipe.zcard(key)
        pipe.zadd(key, {str(now): now})
        pipe.expire(key, 2)
        results = await pipe.execute()

        current_count = results[1]
        if current_count >= self.burst:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers={"Retry-After": "1"},
            )
