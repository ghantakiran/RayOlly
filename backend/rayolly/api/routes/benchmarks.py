"""Benchmark & performance status API routes.

Admin-only endpoints for running performance benchmarks and retrieving
real-time system health metrics.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request

from rayolly.core.benchmarks import Benchmark
from rayolly.core.dependencies import get_current_user

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/admin/benchmarks", tags=["benchmarks"])


def _require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Ensure the caller has admin privileges."""
    role = user.get("role", "")
    if role not in ("admin", "superadmin", "owner"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@router.get("/run")
async def run_benchmarks(
    request: Request,
    _user: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """Run the full performance benchmark suite.

    Returns per-query and per-operation latency statistics including
    p50, p99, avg, min, and max in milliseconds.
    """
    bench = Benchmark(
        clickhouse_client=request.app.state.clickhouse,
        redis_client=request.app.state.redis,
    )
    try:
        results = await bench.run_all()
    except Exception as e:
        logger.error("benchmarks.run_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Benchmark run failed: {e}")

    return {
        "status": "ok",
        "results": results,
    }


@router.get("/status")
async def performance_status(
    request: Request,
    _user: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """Return current performance indicators.

    Provides a lightweight snapshot without running full benchmarks:
    ingestion rate, query latency, cache hit rate, and connection counts.
    """
    ch = request.app.state.clickhouse
    redis = request.app.state.redis

    status: dict[str, Any] = {
        "clickhouse_connected": ch is not None,
        "redis_connected": redis is not None,
        "ingestion_rate_per_sec": 0,
        "query_latency_p99_ms": 0,
        "cache_hit_rate": 0.0,
        "active_connections": 0,
    }

    # ClickHouse: measure a trivial query to gauge current latency
    if ch:
        import time

        start = time.perf_counter()
        try:
            ch.query("SELECT 1")
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            status["query_latency_p99_ms"] = latency_ms
            status["clickhouse_connected"] = True
        except Exception:
            status["clickhouse_connected"] = False

    # Redis: read cache stats if available
    if redis:
        try:
            hits = await redis.get("rayolly:stats:cache_hits")
            misses = await redis.get("rayolly:stats:cache_misses")
            hits_int = int(hits) if hits else 0
            misses_int = int(misses) if misses else 0
            total = hits_int + misses_int
            status["cache_hit_rate"] = round(hits_int / total, 4) if total > 0 else 0.0

            ingestion_rate = await redis.get("rayolly:stats:ingestion_rate")
            status["ingestion_rate_per_sec"] = int(ingestion_rate) if ingestion_rate else 0
        except Exception:
            pass

    # Connection pool stats (if using ClickHousePool)
    pool = getattr(request.app.state, "clickhouse_pool", None)
    if pool is not None:
        status["active_connections"] = getattr(pool, "size", 0)
        status["available_connections"] = getattr(pool, "available_count", 0)

    return {
        "status": "ok",
        "performance": status,
    }
