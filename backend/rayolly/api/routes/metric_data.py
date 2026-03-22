"""Real metric data API — queries ClickHouse metrics.samples directly."""

from __future__ import annotations

import json
import re
from typing import Any

import structlog
from fastapi import APIRouter, Query, Request

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/data/metrics", tags=["metric-data"])

_TENANT_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _validate_tenant(tenant_id: str) -> bool:
    return bool(_TENANT_RE.match(tenant_id))


@router.get("/list")
async def list_metrics(request: Request) -> dict[str, Any]:
    """Distinct metric names with type and point count."""
    ch = request.app.state.clickhouse
    tenant_id = getattr(request.state, "tenant_id", "default")

    if ch is None or not _validate_tenant(tenant_id):
        return {"metrics": []}

    try:
        result = ch.query(
            f"SELECT metric_name, any(metric_type) AS mtype, count() AS point_count, "
            f"any(labels) AS labels_sample "
            f"FROM metrics.samples "
            f"WHERE tenant_id = '{tenant_id}' "
            f"GROUP BY metric_name ORDER BY point_count DESC"
        )
        metrics = [
            {
                "name": row[0],
                "type": row[1],
                "point_count": row[2],
                "labels_sample": dict(row[3]) if row[3] else {},
            }
            for row in result.result_rows
        ]
        return {"metrics": metrics}
    except Exception as e:
        logger.error("list_metrics_error", error=str(e))
        return {"metrics": []}


@router.get("/query")
async def query_metric(
    request: Request,
    name: str = Query(..., description="Metric name"),
    from_time: str | None = Query(default=None, alias="from"),
    to_time: str | None = Query(default=None, alias="to"),
    labels: str | None = Query(default=None, description="JSON label filters"),
) -> dict[str, Any]:
    """Time series for a specific metric."""
    ch = request.app.state.clickhouse
    tenant_id = getattr(request.state, "tenant_id", "default")

    if ch is None or not _validate_tenant(tenant_id):
        return {"data": []}

    try:
        safe_name = name.replace("'", "\\'")
        conditions = [
            f"tenant_id = '{tenant_id}'",
            f"metric_name = '{safe_name}'",
        ]

        if from_time:
            safe_from = from_time.replace("'", "\\'")
            conditions.append(f"timestamp >= '{safe_from}'")
        if to_time:
            safe_to = to_time.replace("'", "\\'")
            conditions.append(f"timestamp <= '{safe_to}'")

        # Default to last 1 hour if no time range
        if not from_time and not to_time:
            conditions.append("timestamp >= now() - INTERVAL 1 HOUR")

        # Optional label filters
        if labels:
            try:
                label_filters = json.loads(labels)
                for k, v in label_filters.items():
                    safe_k = k.replace("'", "\\'")
                    safe_v = v.replace("'", "\\'")
                    conditions.append(f"labels['{safe_k}'] = '{safe_v}'")
            except (json.JSONDecodeError, AttributeError):
                pass  # Ignore invalid label JSON

        where = " AND ".join(conditions)

        result = ch.query(
            f"SELECT timestamp, value "
            f"FROM metrics.samples "
            f"WHERE {where} "
            f"ORDER BY timestamp"
        )

        data = [
            {"timestamp": str(row[0]), "value": row[1]}
            for row in result.result_rows
        ]
        return {"data": data}
    except Exception as e:
        logger.error("query_metric_error", error=str(e))
        return {"data": []}


@router.get("/latest")
async def latest_metrics(request: Request) -> dict[str, Any]:
    """Latest value for each metric."""
    ch = request.app.state.clickhouse
    tenant_id = getattr(request.state, "tenant_id", "default")

    if ch is None or not _validate_tenant(tenant_id):
        return {"metrics": []}

    try:
        result = ch.query(
            f"SELECT metric_name, argMax(value, timestamp) AS latest_value, "
            f"max(timestamp) AS latest_ts, argMax(labels, timestamp) AS latest_labels "
            f"FROM metrics.samples "
            f"WHERE tenant_id = '{tenant_id}' AND timestamp >= now() - INTERVAL 1 HOUR "
            f"GROUP BY metric_name ORDER BY metric_name"
        )
        metrics = [
            {
                "name": row[0],
                "value": row[1],
                "timestamp": str(row[2]),
                "labels": dict(row[3]) if row[3] else {},
            }
            for row in result.result_rows
        ]
        return {"metrics": metrics}
    except Exception as e:
        logger.error("latest_metrics_error", error=str(e))
        return {"metrics": []}
