"""Query API routes."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from rayolly.models.query import (
    QueryRequest,
    QueryResponse,
    QueryType,
    TimeRange,
)
from rayolly.services.query.engine import QueryEngine, QueryExecutionError

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["query"])


def get_query_engine(request: Request) -> QueryEngine:
    return QueryEngine(
        clickhouse_client=request.app.state.clickhouse,
        redis_client=request.app.state.redis,
    )


@router.post("/query", response_model=QueryResponse)
async def execute_query(
    body: QueryRequest,
    request: Request,
    engine: QueryEngine = Depends(get_query_engine),
) -> QueryResponse:
    """Execute a SQL/PromQL/search query."""
    tenant_id = getattr(request.state, "tenant_id", "default")
    try:
        return await engine.execute(body, tenant_id)
    except QueryExecutionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except TimeoutError:
        raise HTTPException(status_code=408, detail="Query timed out")


@router.post("/search")
async def search_logs(
    request: Request,
    query: str,
    stream: str | None = None,
    from_time: str | None = None,
    to_time: str | None = None,
    limit: int = Query(default=100, le=10000),
    highlight: bool = False,
    engine: QueryEngine = Depends(get_query_engine),
) -> QueryResponse:
    """Full-text search across logs."""
    tenant_id = getattr(request.state, "tenant_id", "default")
    time_range = None
    if from_time and to_time:
        time_range = TimeRange(from_time=from_time, to_time=to_time)

    req = QueryRequest(
        query=query,
        query_type=QueryType.SEARCH,
        time_range=time_range,
        timeout=30,
    )
    return await engine.execute(req, tenant_id)


# --- Prometheus API Compatibility ---


@router.get("/prometheus/query")
async def prometheus_instant_query(
    request: Request,
    query: str = Query(..., alias="query"),
    time: str | None = None,
    engine: QueryEngine = Depends(get_query_engine),
) -> dict:
    """Prometheus-compatible instant query endpoint."""
    tenant_id = getattr(request.state, "tenant_id", "default")
    req = QueryRequest(
        query=query,
        query_type=QueryType.PROMQL,
        timeout=30,
    )
    try:
        result = await engine.execute(req, tenant_id)
        return _format_prometheus_response("vector", result)
    except QueryExecutionError as e:
        return {"status": "error", "errorType": "execution", "error": str(e)}


@router.get("/prometheus/query_range")
async def prometheus_range_query(
    request: Request,
    query: str = Query(..., alias="query"),
    start: str = Query(...),
    end: str = Query(...),
    step: str = Query(default="60s"),
    engine: QueryEngine = Depends(get_query_engine),
) -> dict:
    """Prometheus-compatible range query endpoint."""
    tenant_id = getattr(request.state, "tenant_id", "default")
    req = QueryRequest(
        query=query,
        query_type=QueryType.PROMQL,
        time_range=TimeRange(from_time=start, to_time=end),
        timeout=60,
    )
    try:
        result = await engine.execute(req, tenant_id)
        return _format_prometheus_response("matrix", result)
    except QueryExecutionError as e:
        return {"status": "error", "errorType": "execution", "error": str(e)}


@router.get("/prometheus/labels")
async def prometheus_labels(request: Request) -> dict:
    """Prometheus-compatible label names endpoint."""
    return {
        "status": "success",
        "data": [
            "__name__", "instance", "job", "service",
            "namespace", "pod", "host", "region",
        ],
    }


@router.get("/prometheus/label/{label_name}/values")
async def prometheus_label_values(
    label_name: str,
    request: Request,
    engine: QueryEngine = Depends(get_query_engine),
) -> dict:
    """Prometheus-compatible label values endpoint."""
    tenant_id = getattr(request.state, "tenant_id", "default")
    req = QueryRequest(
        query=(
            f"SELECT DISTINCT labels['{label_name}'] AS val "
            f"FROM metrics.samples "
            f"WHERE labels['{label_name}'] != '' "
            f"LIMIT 1000"
        ),
        query_type=QueryType.SQL,
        timeout=10,
    )
    try:
        result = await engine.execute(req, tenant_id)
        values = [row.get("val", "") for row in result.data]
        return {"status": "success", "data": values}
    except QueryExecutionError:
        return {"status": "success", "data": []}


# --- Saved Queries ---


@router.get("/queries/saved")
async def list_saved_queries(request: Request) -> dict:
    """List saved queries for the current tenant."""
    # TODO: Implement with PostgreSQL metadata store
    return {"queries": []}


@router.post("/queries/saved")
async def save_query(request: Request, body: dict) -> dict:
    """Save a query."""
    # TODO: Implement
    return {"id": "sq_placeholder", "status": "saved"}


@router.get("/queries/history")
async def query_history(request: Request) -> dict:
    """Get recent query history."""
    # TODO: Implement
    return {"queries": []}


@router.post("/queries/explain")
async def explain_query(
    body: QueryRequest,
    request: Request,
    engine: QueryEngine = Depends(get_query_engine),
) -> dict:
    """Get query execution plan."""
    tenant_id = getattr(request.state, "tenant_id", "default")
    plan = engine._planner.plan(body, tenant_id)
    return {
        "original_query": plan.original_query,
        "rewritten_query": plan.rewritten_query,
        "tier": plan.tier,
        "tables": plan.tables,
        "cacheable": plan.cacheable,
        "estimated_rows": "unknown",
    }


def _format_prometheus_response(result_type: str, result: QueryResponse) -> dict:
    """Format query result as Prometheus API response."""
    if result_type == "vector":
        prom_result = []
        for row in result.data:
            prom_result.append({
                "metric": {k: v for k, v in row.items() if k not in ("timestamp", "value", "ts", "rate")},
                "value": [
                    row.get("timestamp", row.get("ts", 0)),
                    str(row.get("value", row.get("rate", 0))),
                ],
            })
        return {"status": "success", "data": {"resultType": "vector", "result": prom_result}}

    # matrix
    prom_result = []
    series: dict[str, list] = {}
    for row in result.data:
        key = str({k: v for k, v in row.items() if k not in ("timestamp", "value", "ts", "rate")})
        if key not in series:
            series[key] = []
        series[key].append([
            row.get("timestamp", row.get("ts", 0)),
            str(row.get("value", row.get("rate", 0))),
        ])

    for key, values in series.items():
        prom_result.append({"metric": {}, "values": values})

    return {"status": "success", "data": {"resultType": "matrix", "result": prom_result}}
