"""Real trace data API — queries ClickHouse traces.spans directly."""

from __future__ import annotations

import re
from typing import Any

import structlog
from fastapi import APIRouter, Query, Request

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/data/traces", tags=["trace-data"])

_TENANT_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _validate_tenant(tenant_id: str) -> bool:
    return bool(_TENANT_RE.match(tenant_id))


@router.get("/search")
async def search_traces(
    request: Request,
    service: str | None = None,
    operation: str | None = None,
    min_duration_ms: float | None = None,
    status: str | None = None,
    from_time: str | None = Query(default=None, alias="from"),
    to_time: str | None = Query(default=None, alias="to"),
    limit: int = Query(default=50, le=500),
) -> dict[str, Any]:
    """Search traces with filters. Returns root-level trace summaries."""
    ch = request.app.state.clickhouse
    tenant_id = getattr(request.state, "tenant_id", "default")

    if ch is None or not _validate_tenant(tenant_id):
        return {"traces": []}

    try:
        conditions = [f"tenant_id = '{tenant_id}'"]

        if service:
            safe_svc = service.replace("'", "\\'")
            conditions.append(f"service = '{safe_svc}'")

        if operation:
            safe_op = operation.replace("'", "\\'")
            conditions.append(f"span_name = '{safe_op}'")

        if min_duration_ms is not None:
            min_ns = int(min_duration_ms * 1_000_000)
            conditions.append(f"duration_ns >= {min_ns}")

        if status:
            safe_status = status.replace("'", "\\'")
            conditions.append(f"status_code = '{safe_status}'")

        if from_time:
            safe_from = from_time.replace("'", "\\'")
            conditions.append(f"start_time >= '{safe_from}'")

        if to_time:
            safe_to = to_time.replace("'", "\\'")
            conditions.append(f"start_time <= '{safe_to}'")

        # Default to last 1 hour
        if not from_time and not to_time:
            conditions.append("start_time >= now() - INTERVAL 1 HOUR")

        where = " AND ".join(conditions)

        # Group by trace_id to get trace-level summaries
        result = ch.query(
            f"SELECT trace_id, "
            f"argMin(service, start_time) AS root_service, "
            f"argMin(span_name, start_time) AS root_operation, "
            f"(max(end_time) - min(start_time)) / 1000000 AS duration_ms, "
            f"count() AS span_count, "
            f"if(countIf(status_code = 'ERROR') > 0, 'ERROR', 'OK') AS status, "
            f"min(start_time) AS ts "
            f"FROM traces.spans "
            f"WHERE {where} "
            f"GROUP BY trace_id "
            f"ORDER BY ts DESC LIMIT {limit}"
        )

        traces = [
            {
                "trace_id": row[0].strip('\x00') if isinstance(row[0], str) else row[0],
                "root_service": row[1],
                "root_operation": row[2],
                "duration_ms": round(float(row[3]), 2) if row[3] else 0,
                "span_count": row[4],
                "status": row[5],
                "timestamp": str(row[6]),
            }
            for row in result.result_rows
        ]
        return {"traces": traces}
    except Exception as e:
        logger.error("trace_search_error", error=str(e))
        return {"traces": []}


@router.get("/services")
async def trace_services(request: Request) -> dict[str, Any]:
    """Service list from trace data with stats."""
    ch = request.app.state.clickhouse
    tenant_id = getattr(request.state, "tenant_id", "default")

    if ch is None or not _validate_tenant(tenant_id):
        return {"services": []}

    try:
        result = ch.query(
            f"SELECT service, count() AS span_count, "
            f"avg(duration_ns / 1000000.0) AS avg_duration_ms, "
            f"countIf(status_code = 'ERROR') / count() * 100 AS error_rate "
            f"FROM traces.spans "
            f"WHERE tenant_id = '{tenant_id}' AND start_time >= now() - INTERVAL 1 HOUR "
            f"GROUP BY service ORDER BY span_count DESC"
        )
        services = [
            {
                "service": row[0],
                "span_count": row[1],
                "avg_duration_ms": round(float(row[2]), 2),
                "error_rate": round(float(row[3]), 2),
            }
            for row in result.result_rows
        ]
        return {"services": services}
    except Exception as e:
        logger.error("trace_services_error", error=str(e))
        return {"services": []}


@router.get("/{trace_id}")
async def get_trace(trace_id: str, request: Request) -> dict[str, Any]:
    """All spans for a specific trace."""
    ch = request.app.state.clickhouse
    tenant_id = getattr(request.state, "tenant_id", "default")

    if ch is None or not _validate_tenant(tenant_id):
        return {"spans": []}

    # Validate trace_id format (hex string up to 32 chars)
    if not re.match(r"^[a-fA-F0-9]+$", trace_id):
        return {"spans": [], "error": "Invalid trace_id format"}

    try:
        safe_tid = trace_id.replace("'", "\\'")
        result = ch.query(
            f"SELECT span_id, parent_span_id, service, span_name, "
            f"duration_ns / 1000000.0 AS duration_ms, "
            f"status_code, attributes, start_time, end_time "
            f"FROM traces.spans "
            f"WHERE tenant_id = '{tenant_id}' AND trace_id = '{safe_tid}' "
            f"ORDER BY start_time"
        )

        spans = [
            {
                "span_id": row[0].strip('\x00') if isinstance(row[0], str) else row[0],
                "parent_span_id": row[1].strip('\x00') if isinstance(row[1], str) else row[1],
                "service": row[2],
                "operation": row[3],
                "duration_ms": round(float(row[4]), 2),
                "status": row[5],
                "attributes": dict(row[6]) if row[6] else {},
                "start_time": str(row[7]),
                "end_time": str(row[8]),
            }
            for row in result.result_rows
        ]
        return {"spans": spans}
    except Exception as e:
        logger.error("get_trace_error", error=str(e), trace_id=trace_id)
        return {"spans": []}
