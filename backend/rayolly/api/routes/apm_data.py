"""Real APM data API -- queries ClickHouse traces.spans for service-level APM metrics."""

from __future__ import annotations

import re
from typing import Any

import structlog
from fastapi import APIRouter, Request

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/data/apm", tags=["apm-data"])

_TENANT_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _validate_tenant(tenant_id: str) -> bool:
    return bool(_TENANT_RE.match(tenant_id))


def _health_status(error_rate: float, p99_ms: float) -> str:
    """Derive health from error rate and p99 latency."""
    if error_rate > 10.0 or p99_ms > 5000:
        return "critical"
    if error_rate > 5.0 or p99_ms > 1000:
        return "warning"
    return "healthy"


@router.get("/services")
async def apm_services(request: Request) -> dict[str, Any]:
    """Discover services with real metrics from traces.spans."""
    ch = request.app.state.clickhouse
    tenant_id = getattr(request.state, "tenant_id", "default")

    if ch is None or not _validate_tenant(tenant_id):
        return {"services": []}

    try:
        result = ch.query(
            f"SELECT "
            f"  service, "
            f"  count() AS request_count, "
            f"  countIf(status_code = 'ERROR') AS error_count, "
            f"  countIf(status_code = 'ERROR') / count() * 100 AS error_rate, "
            f"  avg(duration_ns) / 1000000.0 AS avg_duration_ms, "
            f"  quantile(0.99)(duration_ns) / 1000000.0 AS p99_duration_ms "
            f"FROM traces.spans "
            f"WHERE tenant_id = '{tenant_id}' "
            f"  AND service != '' "
            f"  AND start_time >= now() - INTERVAL 1 HOUR "
            f"GROUP BY service "
            f"ORDER BY request_count DESC"
        )

        services = []
        for row in result.result_rows:
            error_rate = round(float(row[3]), 2)
            p99_ms = round(float(row[5]), 2)
            services.append({
                "service": row[0],
                "request_count": row[1],
                "error_count": row[2],
                "error_rate": error_rate,
                "avg_duration_ms": round(float(row[4]), 2),
                "p99_duration_ms": p99_ms,
                "status": _health_status(error_rate, p99_ms),
            })
        return {"services": services}
    except Exception as e:
        logger.error("apm_services_error", error=str(e))
        return {"services": []}


@router.get("/service-map")
async def service_map(request: Request) -> dict[str, Any]:
    """Build service dependency graph from parent-child span relationships."""
    ch = request.app.state.clickhouse
    tenant_id = getattr(request.state, "tenant_id", "default")

    if ch is None or not _validate_tenant(tenant_id):
        return {"nodes": [], "edges": []}

    try:
        # Step 1: Get nodes (services with metrics)
        svc_result = ch.query(
            f"SELECT "
            f"  service, "
            f"  count() AS request_count, "
            f"  countIf(status_code = 'ERROR') / count() * 100 AS error_rate, "
            f"  avg(duration_ns) / 1000000.0 AS avg_ms, "
            f"  quantile(0.99)(duration_ns) / 1000000.0 AS p99_ms "
            f"FROM traces.spans "
            f"WHERE tenant_id = '{tenant_id}' "
            f"  AND service != '' "
            f"  AND start_time >= now() - INTERVAL 1 HOUR "
            f"GROUP BY service "
            f"ORDER BY request_count DESC"
        )

        nodes = []
        for row in svc_result.result_rows:
            error_rate = round(float(row[2]), 2)
            p99_ms = round(float(row[4]), 2)
            nodes.append({
                "id": row[0],
                "service": row[0],
                "type": "service",
                "health": _health_status(error_rate, p99_ms),
                "metrics": {
                    "request_count": row[1],
                    "error_rate": error_rate,
                    "avg_ms": round(float(row[3]), 2),
                    "p99_ms": p99_ms,
                },
            })

        # Step 2: Get edges (caller -> callee via parent-child span join)
        edge_result = ch.query(
            f"SELECT "
            f"  parent.service AS caller, "
            f"  child.service AS callee, "
            f"  count() AS request_count, "
            f"  countIf(child.status_code = 'ERROR') / count() * 100 AS error_rate, "
            f"  avg(child.duration_ns) / 1000000.0 AS avg_latency_ms "
            f"FROM traces.spans AS child "
            f"INNER JOIN traces.spans AS parent "
            f"  ON child.parent_span_id = parent.span_id "
            f"  AND child.trace_id = parent.trace_id "
            f"  AND parent.tenant_id = '{tenant_id}' "
            f"WHERE child.tenant_id = '{tenant_id}' "
            f"  AND child.service != parent.service "
            f"  AND child.service != '' "
            f"  AND parent.service != '' "
            f"  AND child.start_time >= now() - INTERVAL 1 HOUR "
            f"GROUP BY caller, callee "
            f"ORDER BY request_count DESC"
        )

        edges = []
        for row in edge_result.result_rows:
            edges.append({
                "source": row[0],
                "target": row[1],
                "request_count": row[2],
                "error_rate": round(float(row[3]), 2),
                "avg_latency_ms": round(float(row[4]), 2),
            })

        return {"nodes": nodes, "edges": edges}
    except Exception as e:
        logger.error("service_map_error", error=str(e))
        return {"nodes": [], "edges": []}


@router.get("/services/{service}/endpoints")
async def service_endpoints(service: str, request: Request) -> dict[str, Any]:
    """List endpoints for a service with latency stats."""
    ch = request.app.state.clickhouse
    tenant_id = getattr(request.state, "tenant_id", "default")

    if ch is None or not _validate_tenant(tenant_id):
        return {"endpoints": []}

    safe_svc = service.replace("'", "\\'")

    try:
        result = ch.query(
            f"SELECT "
            f"  span_name AS operation, "
            f"  count() AS request_count, "
            f"  countIf(status_code = 'ERROR') AS error_count, "
            f"  avg(duration_ns) / 1000000.0 AS avg_ms, "
            f"  quantile(0.50)(duration_ns) / 1000000.0 AS p50_ms, "
            f"  quantile(0.99)(duration_ns) / 1000000.0 AS p99_ms "
            f"FROM traces.spans "
            f"WHERE tenant_id = '{tenant_id}' "
            f"  AND service = '{safe_svc}' "
            f"  AND start_time >= now() - INTERVAL 1 HOUR "
            f"GROUP BY operation "
            f"ORDER BY request_count DESC "
            f"LIMIT 50"
        )

        endpoints = [
            {
                "operation": row[0],
                "request_count": row[1],
                "error_count": row[2],
                "avg_ms": round(float(row[3]), 2),
                "p50_ms": round(float(row[4]), 2),
                "p99_ms": round(float(row[5]), 2),
            }
            for row in result.result_rows
        ]
        return {"endpoints": endpoints}
    except Exception as e:
        logger.error("service_endpoints_error", error=str(e), service=service)
        return {"endpoints": []}


@router.get("/services/{service}/errors")
async def service_errors(service: str, request: Request) -> dict[str, Any]:
    """List error groups for a service."""
    ch = request.app.state.clickhouse
    tenant_id = getattr(request.state, "tenant_id", "default")

    if ch is None or not _validate_tenant(tenant_id):
        return {"errors": []}

    safe_svc = service.replace("'", "\\'")

    try:
        result = ch.query(
            f"SELECT "
            f"  status_message AS message, "
            f"  count() AS cnt, "
            f"  min(start_time) AS first_seen, "
            f"  max(start_time) AS last_seen, "
            f"  any(trace_id) AS sample_trace_id "
            f"FROM traces.spans "
            f"WHERE tenant_id = '{tenant_id}' "
            f"  AND service = '{safe_svc}' "
            f"  AND status_code = 'ERROR' "
            f"  AND start_time >= now() - INTERVAL 24 HOUR "
            f"GROUP BY message "
            f"ORDER BY cnt DESC "
            f"LIMIT 20"
        )

        errors = [
            {
                "message": row[0] if row[0] else "Unknown error",
                "count": row[1],
                "first_seen": str(row[2]),
                "last_seen": str(row[3]),
                "sample_trace_id": row[4].strip('\x00') if isinstance(row[4], str) else str(row[4]),
            }
            for row in result.result_rows
        ]
        return {"errors": errors}
    except Exception as e:
        logger.error("service_errors_error", error=str(e), service=service)
        return {"errors": []}
