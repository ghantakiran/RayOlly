"""Dashboard overview API — aggregates key metrics for the home page."""

from __future__ import annotations

import re
from typing import Any

import structlog
from fastapi import APIRouter, Request

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])

_TENANT_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _validate_tenant(tenant_id: str) -> bool:
    return bool(_TENANT_RE.match(tenant_id))


def _empty_overview() -> dict[str, Any]:
    return {
        "total_services": 0,
        "service_health": {"healthy": 0, "warning": 0, "critical": 0},
        "total_logs_24h": 0,
        "total_errors_24h": 0,
        "error_rate_pct": 0.0,
        "ingestion_rate": 0.0,
    }


@router.get("/overview")
async def dashboard_overview(request: Request) -> dict[str, Any]:
    """Key metrics for the dashboard home page."""
    ch = request.app.state.clickhouse
    tenant_id = getattr(request.state, "tenant_id", "default")

    if ch is None or not _validate_tenant(tenant_id):
        return _empty_overview()

    try:
        # Total distinct services (from logs + traces)
        svc_result = ch.query(
            f"SELECT uniqExact(service) FROM logs.log_entries "
            f"WHERE tenant_id = '{tenant_id}' AND timestamp >= now() - INTERVAL 24 HOUR"
        )
        total_services = svc_result.result_rows[0][0] if svc_result.result_rows else 0

        # Log stats last 24h
        log_result = ch.query(
            f"SELECT count() AS total, "
            f"countIf(severity IN ('ERROR', 'FATAL', 'CRITICAL')) AS errors "
            f"FROM logs.log_entries "
            f"WHERE tenant_id = '{tenant_id}' AND timestamp >= now() - INTERVAL 24 HOUR"
        )
        total_logs = log_result.result_rows[0][0] if log_result.result_rows else 0
        total_errors = log_result.result_rows[0][1] if log_result.result_rows else 0
        error_rate = round((total_errors / total_logs * 100), 2) if total_logs > 0 else 0.0

        # Ingestion rate (logs per minute over last hour)
        rate_result = ch.query(
            f"SELECT count() / 60.0 FROM logs.log_entries "
            f"WHERE tenant_id = '{tenant_id}' AND timestamp >= now() - INTERVAL 1 HOUR"
        )
        ingestion_rate = round(rate_result.result_rows[0][0], 2) if rate_result.result_rows else 0.0

        # Service health breakdown based on per-service error rate
        health_result = ch.query(
            f"SELECT service, count() AS total, "
            f"countIf(severity IN ('ERROR', 'FATAL', 'CRITICAL')) AS errs "
            f"FROM logs.log_entries "
            f"WHERE tenant_id = '{tenant_id}' AND timestamp >= now() - INTERVAL 1 HOUR "
            f"GROUP BY service"
        )
        healthy = warning = critical = 0
        for row in health_result.result_rows:
            svc_total, svc_errs = row[1], row[2]
            rate = (svc_errs / svc_total * 100) if svc_total > 0 else 0
            if rate >= 10:
                critical += 1
            elif rate >= 2:
                warning += 1
            else:
                healthy += 1

        return {
            "total_services": total_services,
            "service_health": {"healthy": healthy, "warning": warning, "critical": critical},
            "total_logs_24h": total_logs,
            "total_errors_24h": total_errors,
            "error_rate_pct": error_rate,
            "ingestion_rate": ingestion_rate,
        }
    except Exception as e:
        logger.error("dashboard_overview_error", error=str(e))
        return _empty_overview()


@router.get("/ingestion-chart")
async def ingestion_chart(request: Request) -> dict[str, Any]:
    """Time series of log volume per minute for the last 6 hours."""
    ch = request.app.state.clickhouse
    tenant_id = getattr(request.state, "tenant_id", "default")

    if ch is None or not _validate_tenant(tenant_id):
        return {"data": []}

    try:
        result = ch.query(
            f"SELECT toStartOfMinute(timestamp) AS ts, "
            f"count() AS cnt, "
            f"countIf(severity IN ('ERROR', 'FATAL', 'CRITICAL')) AS err_cnt "
            f"FROM logs.log_entries "
            f"WHERE tenant_id = '{tenant_id}' AND timestamp >= now() - INTERVAL 6 HOUR "
            f"GROUP BY ts ORDER BY ts"
        )
        data = [
            {
                "timestamp": str(row[0]),
                "count": row[1],
                "error_count": row[2],
            }
            for row in result.result_rows
        ]
        return {"data": data}
    except Exception as e:
        logger.error("ingestion_chart_error", error=str(e))
        return {"data": []}


@router.get("/top-services")
async def top_services(request: Request) -> dict[str, Any]:
    """Top 10 services by log volume with error rate."""
    ch = request.app.state.clickhouse
    tenant_id = getattr(request.state, "tenant_id", "default")

    if ch is None or not _validate_tenant(tenant_id):
        return {"services": []}

    try:
        result = ch.query(
            f"SELECT service, count() AS log_count, "
            f"countIf(severity IN ('ERROR', 'FATAL', 'CRITICAL')) AS error_count "
            f"FROM logs.log_entries "
            f"WHERE tenant_id = '{tenant_id}' AND timestamp >= now() - INTERVAL 24 HOUR "
            f"GROUP BY service ORDER BY log_count DESC LIMIT 10"
        )
        services = [
            {
                "service": row[0],
                "log_count": row[1],
                "error_count": row[2],
                "error_rate_pct": round((row[2] / row[1] * 100), 2) if row[1] > 0 else 0.0,
            }
            for row in result.result_rows
        ]
        return {"services": services}
    except Exception as e:
        logger.error("top_services_error", error=str(e))
        return {"services": []}


@router.get("/recent-errors")
async def recent_errors(request: Request) -> dict[str, Any]:
    """Last 20 error logs."""
    ch = request.app.state.clickhouse
    tenant_id = getattr(request.state, "tenant_id", "default")

    if ch is None or not _validate_tenant(tenant_id):
        return {"errors": []}

    try:
        result = ch.query(
            f"SELECT timestamp, service, body, attributes "
            f"FROM logs.log_entries "
            f"WHERE tenant_id = '{tenant_id}' "
            f"AND severity IN ('ERROR', 'FATAL', 'CRITICAL') "
            f"ORDER BY timestamp DESC LIMIT 20"
        )
        errors = [
            {
                "timestamp": str(row[0]),
                "service": row[1],
                "body": row[2],
                "attributes": dict(row[3]) if row[3] else {},
            }
            for row in result.result_rows
        ]
        return {"errors": errors}
    except Exception as e:
        logger.error("recent_errors_error", error=str(e))
        return {"errors": []}


@router.get("/service-health")
async def service_health(request: Request) -> dict[str, Any]:
    """All services with health status based on error rate and latency."""
    ch = request.app.state.clickhouse
    tenant_id = getattr(request.state, "tenant_id", "default")

    if ch is None or not _validate_tenant(tenant_id):
        return {"services": []}

    try:
        # Get per-service log error rates
        log_result = ch.query(
            f"SELECT service, count() AS request_count, "
            f"countIf(severity IN ('ERROR', 'FATAL', 'CRITICAL')) AS error_count "
            f"FROM logs.log_entries "
            f"WHERE tenant_id = '{tenant_id}' AND timestamp >= now() - INTERVAL 1 HOUR "
            f"GROUP BY service"
        )

        # Get per-service p99 latency from traces
        trace_result = ch.query(
            f"SELECT service, quantile(0.99)(duration_ns / 1000000.0) AS p99_ms "
            f"FROM traces.spans "
            f"WHERE tenant_id = '{tenant_id}' AND start_time >= now() - INTERVAL 1 HOUR "
            f"GROUP BY service"
        )
        latency_map: dict[str, float] = {}
        for row in trace_result.result_rows:
            latency_map[row[0]] = round(row[1], 2)

        services = []
        for row in log_result.result_rows:
            svc_name, req_count, err_count = row[0], row[1], row[2]
            err_rate = round((err_count / req_count * 100), 2) if req_count > 0 else 0.0
            p99 = latency_map.get(svc_name, 0.0)

            if err_rate >= 10:
                status = "critical"
            elif err_rate >= 2:
                status = "warning"
            else:
                status = "healthy"

            services.append({
                "service": svc_name,
                "status": status,
                "request_count": req_count,
                "error_count": err_count,
                "error_rate": err_rate,
                "p99_latency": p99,
            })

        return {"services": services}
    except Exception as e:
        logger.error("service_health_error", error=str(e))
        return {"services": []}
