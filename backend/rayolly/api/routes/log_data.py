"""Real log data API — queries ClickHouse directly for log entries."""

from __future__ import annotations

import re
from typing import Any

import structlog
from fastapi import APIRouter, Query, Request

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/data/logs", tags=["log-data"])

_TENANT_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _validate_tenant(tenant_id: str) -> bool:
    return bool(_TENANT_RE.match(tenant_id))


@router.get("/search")
async def search_logs(
    request: Request,
    q: str | None = None,
    service: str | None = None,
    severity: str | None = None,
    from_time: str | None = Query(default=None, alias="from"),
    to_time: str | None = Query(default=None, alias="to"),
    limit: int = Query(default=100, le=1000),
) -> dict[str, Any]:
    """Search log entries with optional filters."""
    ch = request.app.state.clickhouse
    tenant_id = getattr(request.state, "tenant_id", "default")

    if ch is None or not _validate_tenant(tenant_id):
        return {"logs": [], "total": 0}

    try:
        conditions = [f"tenant_id = '{tenant_id}'"]

        if q:
            # Escape single quotes in search term
            safe_q = q.replace("'", "\\'")
            conditions.append(f"hasToken(body, '{safe_q}')")

        if service:
            safe_svc = service.replace("'", "\\'")
            conditions.append(f"service = '{safe_svc}'")

        if severity:
            safe_sev = severity.replace("'", "\\'")
            conditions.append(f"severity = '{safe_sev}'")

        if from_time:
            safe_from = from_time.replace("'", "\\'")
            conditions.append(f"timestamp >= '{safe_from}'")

        if to_time:
            safe_to = to_time.replace("'", "\\'")
            conditions.append(f"timestamp <= '{safe_to}'")

        where = " AND ".join(conditions)

        # Get total count
        count_result = ch.query(f"SELECT count() FROM logs.log_entries WHERE {where}")
        total = count_result.result_rows[0][0] if count_result.result_rows else 0

        # Get log rows
        result = ch.query(
            f"SELECT timestamp, service, host, severity, body, attributes "
            f"FROM logs.log_entries "
            f"WHERE {where} "
            f"ORDER BY timestamp DESC LIMIT {limit}"
        )

        logs = [
            {
                "timestamp": str(row[0]),
                "service": row[1],
                "host": row[2],
                "severity": row[3],
                "body": row[4],
                "attributes": dict(row[5]) if row[5] else {},
            }
            for row in result.result_rows
        ]
        return {"logs": logs, "total": total}
    except Exception as e:
        logger.error("log_search_error", error=str(e))
        return {"logs": [], "total": 0}


@router.get("/volume")
async def log_volume(
    request: Request,
    from_time: str | None = Query(default=None, alias="from"),
    to_time: str | None = Query(default=None, alias="to"),
    interval: str = Query(default="1 minute"),
) -> dict[str, Any]:
    """Time series of log volume broken down by severity."""
    ch = request.app.state.clickhouse
    tenant_id = getattr(request.state, "tenant_id", "default")

    if ch is None or not _validate_tenant(tenant_id):
        return {"data": []}

    # Validate interval to prevent injection
    allowed_intervals = {
        "1 minute", "5 minute", "10 minute", "15 minute", "30 minute",
        "1 hour", "6 hour", "1 day",
    }
    if interval not in allowed_intervals:
        interval = "1 minute"

    try:
        conditions = [f"tenant_id = '{tenant_id}'"]
        if from_time:
            safe_from = from_time.replace("'", "\\'")
            conditions.append(f"timestamp >= '{safe_from}'")
        if to_time:
            safe_to = to_time.replace("'", "\\'")
            conditions.append(f"timestamp <= '{safe_to}'")

        # Default to last 6 hours if no time range specified
        if not from_time and not to_time:
            conditions.append("timestamp >= now() - INTERVAL 6 HOUR")

        where = " AND ".join(conditions)

        # Map interval string to ClickHouse toStartOf function
        interval_map = {
            "1 minute": "toStartOfMinute(timestamp)",
            "5 minute": "toStartOfFiveMinutes(timestamp)",
            "10 minute": "toStartOfTenMinutes(timestamp)",
            "15 minute": "toStartOfFifteenMinutes(timestamp)",
            "30 minute": "toStartOfInterval(timestamp, INTERVAL 30 MINUTE)",
            "1 hour": "toStartOfHour(timestamp)",
            "6 hour": "toStartOfInterval(timestamp, INTERVAL 6 HOUR)",
            "1 day": "toStartOfDay(timestamp)",
        }
        ts_expr = interval_map.get(interval, "toStartOfMinute(timestamp)")

        result = ch.query(
            f"SELECT {ts_expr} AS ts, "
            f"count() AS cnt, "
            f"countIf(severity = 'INFO') AS info_cnt, "
            f"countIf(severity = 'WARN' OR severity = 'WARNING') AS warn_cnt, "
            f"countIf(severity IN ('ERROR', 'FATAL', 'CRITICAL')) AS err_cnt "
            f"FROM logs.log_entries "
            f"WHERE {where} "
            f"GROUP BY ts ORDER BY ts"
        )

        data = [
            {
                "timestamp": str(row[0]),
                "count": row[1],
                "info_count": row[2],
                "warn_count": row[3],
                "error_count": row[4],
            }
            for row in result.result_rows
        ]
        return {"data": data}
    except Exception as e:
        logger.error("log_volume_error", error=str(e))
        return {"data": []}


@router.get("/services")
async def log_services(request: Request) -> dict[str, Any]:
    """Distinct services with log counts."""
    ch = request.app.state.clickhouse
    tenant_id = getattr(request.state, "tenant_id", "default")

    if ch is None or not _validate_tenant(tenant_id):
        return {"services": []}

    try:
        result = ch.query(
            f"SELECT service, count() AS cnt "
            f"FROM logs.log_entries "
            f"WHERE tenant_id = '{tenant_id}' AND timestamp >= now() - INTERVAL 24 HOUR "
            f"GROUP BY service ORDER BY cnt DESC"
        )
        services = [
            {"service": row[0], "count": row[1]}
            for row in result.result_rows
        ]
        return {"services": services}
    except Exception as e:
        logger.error("log_services_error", error=str(e))
        return {"services": []}


@router.get("/severities")
async def log_severities(request: Request) -> dict[str, Any]:
    """Log count by severity."""
    ch = request.app.state.clickhouse
    tenant_id = getattr(request.state, "tenant_id", "default")

    if ch is None or not _validate_tenant(tenant_id):
        return {"severities": []}

    try:
        result = ch.query(
            f"SELECT severity, count() AS cnt "
            f"FROM logs.log_entries "
            f"WHERE tenant_id = '{tenant_id}' AND timestamp >= now() - INTERVAL 24 HOUR "
            f"GROUP BY severity ORDER BY cnt DESC"
        )
        severities = [
            {"severity": row[0], "count": row[1]}
            for row in result.result_rows
        ]
        return {"severities": severities}
    except Exception as e:
        logger.error("log_severities_error", error=str(e))
        return {"severities": []}
