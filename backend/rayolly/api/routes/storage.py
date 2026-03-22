"""Storage management API -- retention policies, archival, GDPR erasure."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from rayolly.services.storage.cold_tier import ColdTierWriter
from rayolly.services.storage.retention import (
    RetentionEnforcer,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/storage", tags=["storage"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_enforcer(request: Request) -> RetentionEnforcer:
    """Build a RetentionEnforcer from app state."""
    ch = request.app.state.clickhouse
    if ch is None:
        raise HTTPException(status_code=503, detail="ClickHouse unavailable")

    cold_writer: ColdTierWriter | None = None
    s3 = getattr(request.app.state, "s3", None)
    if s3 is not None:
        cold_writer = ColdTierWriter(
            clickhouse_client=ch,
            s3_client=s3,
        )

    return RetentionEnforcer(clickhouse_client=ch, cold_tier_writer=cold_writer)


def _tenant_id(request: Request) -> str:
    tenant = getattr(request.state, "tenant_id", None)
    if not tenant:
        raise HTTPException(status_code=400, detail="Missing tenant_id")
    return tenant


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class RetentionPolicyUpdate(BaseModel):
    logs_hot_days: int | None = None
    logs_cold_days: int | None = None
    logs_delete_days: int | None = None
    metrics_hot_days: int | None = None
    metrics_cold_days: int | None = None
    traces_hot_days: int | None = None
    traces_cold_days: int | None = None
    compliance_hold: bool | None = None


class GDPREraseRequest(BaseModel):
    user_id: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/stats")
async def get_storage_stats(request: Request) -> dict[str, Any]:
    """Returns storage stats per table for the tenant."""
    tenant = _tenant_id(request)
    enforcer = _get_enforcer(request)
    return await enforcer.get_storage_stats(tenant)


@router.get("/retention")
async def get_retention_policy(request: Request) -> dict[str, Any]:
    """Returns current retention policy for the tenant."""
    tenant = _tenant_id(request)
    enforcer = _get_enforcer(request)
    policy = enforcer.get_policy(tenant)
    return {
        "tenant_id": tenant,
        "logs_hot_days": policy.logs_hot_days,
        "logs_cold_days": policy.logs_cold_days,
        "logs_delete_days": policy.logs_delete_days,
        "metrics_hot_days": policy.metrics_hot_days,
        "metrics_cold_days": policy.metrics_cold_days,
        "traces_hot_days": policy.traces_hot_days,
        "traces_cold_days": policy.traces_cold_days,
        "compliance_hold": policy.compliance_hold,
    }


@router.put("/retention")
async def update_retention_policy(
    body: RetentionPolicyUpdate,
    request: Request,
) -> dict[str, Any]:
    """Update retention policy (admin only)."""
    tenant = _tenant_id(request)
    enforcer = _get_enforcer(request)

    current = enforcer.get_policy(tenant)
    updates = body.model_dump(exclude_none=True)
    for field, value in updates.items():
        setattr(current, field, value)
    current.tenant_id = tenant

    enforcer.set_policy(tenant, current)
    logger.info("retention.policy_updated", tenant=tenant, updates=updates)
    return {"status": "updated", "policy": updates}


@router.post("/archive")
async def trigger_archive(request: Request) -> dict[str, Any]:
    """Trigger manual archive of old data to cold tier."""
    tenant = _tenant_id(request)
    enforcer = _get_enforcer(request)

    if enforcer.cold_writer is None:
        raise HTTPException(
            status_code=503,
            detail="Cold tier (S3) not configured",
        )

    policy = enforcer.get_policy(tenant)
    logs_result = await enforcer.cold_writer.archive_logs(
        tenant, policy.logs_hot_days
    )
    metrics_result = await enforcer.cold_writer.archive_metrics(
        tenant, policy.metrics_hot_days
    )

    return {"logs": logs_result, "metrics": metrics_result}


@router.post("/gdpr/erase")
async def gdpr_erase(body: GDPREraseRequest, request: Request) -> dict[str, Any]:
    """GDPR right-to-erasure for a specific user_id."""
    tenant = _tenant_id(request)
    enforcer = _get_enforcer(request)
    result = await enforcer.gdpr_erase(tenant, body.user_id)
    return {"status": "completed", "details": result}


@router.get("/cold/query")
async def query_cold_tier(
    request: Request,
    table: str = Query(..., description="Table name to query"),
    query: str = Query(..., description="SQL WHERE clause"),
    limit: int = Query(100, ge=1, le=1000),
) -> dict[str, Any]:
    """Query cold tier data (DuckDB on Parquet)."""
    tenant = _tenant_id(request)
    enforcer = _get_enforcer(request)

    if enforcer.cold_writer is None:
        raise HTTPException(
            status_code=503,
            detail="Cold tier (S3) not configured",
        )

    rows = await enforcer.cold_writer.query_cold(
        tenant,
        f"{query} LIMIT {limit}",
    )
    return {"rows": rows, "count": len(rows)}
