"""Enhanced Logs API routes — search, live tail, views, streams, analytics."""

from __future__ import annotations

from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, Query, Request, WebSocket, WebSocketDisconnect

from rayolly.services.logging.explorer import (
    LogExplorer,
    LogSearchRequest,
)
from rayolly.services.logging.live_tail import LiveTailService, TailFilter
from rayolly.services.logging.views import LogView, LogViewService

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/logs", tags=["logs"])


def get_explorer(request: Request) -> LogExplorer:
    return LogExplorer(
        clickhouse_client=request.app.state.clickhouse,
        redis_client=getattr(request.app.state, "redis", None),
    )


# --- Search ---


@router.post("/search")
async def search_logs(
    body: dict,
    request: Request,
    explorer: LogExplorer = Depends(get_explorer),
) -> dict:
    """Advanced log search with facets and histogram."""
    tenant_id = getattr(request.state, "tenant_id", "default")
    search_req = LogSearchRequest(
        query=body.get("query", ""),
        stream=body.get("stream"),
        services=body.get("services", []),
        severities=body.get("severities", []),
        hosts=body.get("hosts", []),
        trace_id=body.get("trace_id"),
        from_time=body.get("from", ""),
        to_time=body.get("to", ""),
        limit=min(body.get("limit", 100), 10000),
        offset=body.get("offset", 0),
        highlight=body.get("highlight", True),
    )
    result = await explorer.search(tenant_id, search_req)
    return {
        "logs": result.logs,
        "total": result.total,
        "took_ms": result.took_ms,
        "facets": (
            {
                "services": [{"value": f.value, "count": f.count} for f in result.facets.services],
                "severities": [{"value": f.value, "count": f.count} for f in result.facets.severities],
                "hosts": [{"value": f.value, "count": f.count} for f in result.facets.hosts],
                "streams": [{"value": f.value, "count": f.count} for f in result.facets.streams],
            }
            if result.facets
            else None
        ),
        "histogram": (
            [{"timestamp": b.timestamp, "count": b.count, "errors": b.error_count}
             for b in result.histogram]
            if result.histogram
            else None
        ),
    }


@router.get("/context")
async def get_log_context(
    request: Request,
    timestamp: str = Query(...),
    service: str = Query(...),
    lines: int = Query(default=20, le=100),
    explorer: LogExplorer = Depends(get_explorer),
) -> dict:
    """Get surrounding log lines for context."""
    tenant_id = getattr(request.state, "tenant_id", "default")
    ctx = await explorer.get_context(tenant_id, timestamp, service, lines)
    return {
        "before": ctx.before,
        "target": ctx.target,
        "after": ctx.after,
    }


# --- Live Tail (WebSocket) ---


@router.websocket("/tail")
async def live_tail(websocket: WebSocket) -> None:
    """WebSocket endpoint for live log tailing."""
    await websocket.accept()

    nats_client = websocket.app.state.nats
    tail_service = LiveTailService(nats_client)
    session_id = uuid4().hex[:12]

    try:
        # Receive initial filter config
        config_data = await websocket.receive_json()
        tenant_id = config_data.get("tenant_id", "default")
        filters = TailFilter(
            services=config_data.get("services", []),
            severities=config_data.get("severities", []),
            hosts=config_data.get("hosts", []),
            query=config_data.get("query", ""),
            stream=config_data.get("stream"),
        )

        async for event in tail_service.subscribe(tenant_id, session_id, filters):
            await websocket.send_json(event)

    except WebSocketDisconnect:
        logger.info("live_tail_disconnected", session_id=session_id)
    except Exception as e:
        logger.error("live_tail_error", error=str(e), session_id=session_id)
    finally:
        await tail_service.unsubscribe(session_id)


# --- Streams ---


@router.get("/streams")
async def list_streams(
    request: Request,
    explorer: LogExplorer = Depends(get_explorer),
) -> dict:
    """List all log streams for the tenant."""
    tenant_id = getattr(request.state, "tenant_id", "default")
    streams = await explorer.get_streams(tenant_id)
    return {
        "streams": [
            {
                "name": s.name,
                "log_count": s.log_count,
                "first_seen": s.first_seen,
                "last_seen": s.last_seen,
                "retention_days": s.retention_days,
            }
            for s in streams
        ]
    }


# --- Field Values (Autocomplete) ---


@router.get("/fields/{field_name}/values")
async def get_field_values(
    field_name: str,
    request: Request,
    prefix: str = "",
    limit: int = Query(default=50, le=200),
    explorer: LogExplorer = Depends(get_explorer),
) -> dict:
    """Get top values for a field (for autocomplete and faceting)."""
    tenant_id = getattr(request.state, "tenant_id", "default")
    values = await explorer.get_field_values(tenant_id, field_name, prefix, limit)
    return {"values": [{"value": v.value, "count": v.count} for v in values]}


# --- Analytics ---


@router.get("/analytics")
async def log_analytics(
    request: Request,
    from_time: str = Query(..., alias="from"),
    to_time: str = Query(..., alias="to"),
    explorer: LogExplorer = Depends(get_explorer),
) -> dict:
    """Get log analytics summary."""
    tenant_id = getattr(request.state, "tenant_id", "default")
    return await explorer.get_log_analytics(tenant_id, (from_time, to_time))


# --- Views ---

_view_service = LogViewService()


@router.get("/views")
async def list_views(request: Request) -> dict:
    tenant_id = getattr(request.state, "tenant_id", "default")
    views = await _view_service.list_views(tenant_id)
    return {"views": [v.__dict__ for v in views]}


@router.post("/views")
async def create_view(body: dict, request: Request) -> dict:
    tenant_id = getattr(request.state, "tenant_id", "default")
    view = LogView(
        id="",
        name=body.get("name", "Untitled"),
        description=body.get("description", ""),
        tenant_id=tenant_id,
        query=body.get("query", ""),
        filters=body.get("filters", {}),
        columns=body.get("columns", ["timestamp", "resource_service", "severity_text", "body"]),
        tags=body.get("tags", []),
    )
    created = await _view_service.create_view(view)
    return {"id": created.id, "status": "created"}


@router.delete("/views/{view_id}")
async def delete_view(view_id: str, request: Request) -> dict:
    deleted = await _view_service.delete_view(view_id)
    if not deleted:
        return {"status": "not_found"}
    return {"status": "deleted"}


# --- Log-to-Metrics ---

_l2m_service = LogViewService()


@router.get("/log-to-metrics/rules")
async def list_l2m_rules(request: Request) -> dict:
    return {"rules": []}


@router.post("/log-to-metrics/rules")
async def create_l2m_rule(body: dict, request: Request) -> dict:
    return {"id": "l2m_placeholder", "status": "created"}


# --- Export ---


@router.post("/export")
async def export_logs(
    body: dict,
    request: Request,
    explorer: LogExplorer = Depends(get_explorer),
) -> dict:
    """Export log search results."""
    tenant_id = getattr(request.state, "tenant_id", "default")
    export_format = body.get("format", "json")
    search_req = LogSearchRequest(
        query=body.get("query", ""),
        from_time=body.get("from", ""),
        to_time=body.get("to", ""),
        limit=min(body.get("limit", 10000), 100000),
    )
    result = await explorer.search(tenant_id, search_req)
    return {
        "format": export_format,
        "rows": len(result.logs),
        "data": result.logs,
    }
