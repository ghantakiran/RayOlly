"""Synthetics monitoring API routes.

Provides CRUD for synthetic monitors, manual check triggering,
results history, uptime stats, and public status page data.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ...services.synthetics.monitor import (
    AssertionOperator,
    AssertionType,
    MonitorAssertion,
    MonitorConfig,
    MonitorType,
    SyntheticMonitorService,
)
from ...services.synthetics.scheduler import SyntheticScheduler

router = APIRouter(prefix="/api/v1/synthetics", tags=["synthetics"])


# ── Request / Response Models ───────────────────────────────────────────

class AssertionModel(BaseModel):
    type: AssertionType
    operator: AssertionOperator
    expected_value: str


class CreateMonitorRequest(BaseModel):
    name: str
    type: MonitorType
    target: str
    method: str = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    assertions: list[AssertionModel] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=lambda: ["us-east-1"])
    interval_seconds: int = Field(default=300, ge=60, le=3600)
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    alert_channels: list[str] = Field(default_factory=list)
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)


class UpdateMonitorRequest(BaseModel):
    name: str | None = None
    type: MonitorType | None = None
    target: str | None = None
    method: str | None = None
    headers: dict[str, str] | None = None
    body: str | None = None
    assertions: list[AssertionModel] | None = None
    locations: list[str] | None = None
    interval_seconds: int | None = Field(default=None, ge=60, le=3600)
    timeout_seconds: int | None = Field(default=None, ge=1, le=120)
    alert_channels: list[str] | None = None
    enabled: bool | None = None
    tags: list[str] | None = None


class MonitorResponse(BaseModel):
    id: str
    name: str
    type: MonitorType
    target: str
    method: str
    headers: dict[str, str]
    assertions: list[AssertionModel]
    locations: list[str]
    interval_seconds: int
    timeout_seconds: int
    alert_channels: list[str]
    enabled: bool
    tags: list[str]


class CheckResultResponse(BaseModel):
    monitor_id: str
    location: str
    timestamp: str
    status: str
    response_time_ms: float
    status_code: int | None
    dns_time_ms: float
    connect_time_ms: float
    tls_time_ms: float
    ttfb_ms: float
    body_size_bytes: int
    assertions_passed: list[bool]
    error_message: str | None


class UptimeResponse(BaseModel):
    uptime_pct: float
    checks_total: int
    checks_passed: int
    avg_response_time_ms: float
    p95_response_time_ms: float
    incidents: list[dict]


class StatusPageEntry(BaseModel):
    monitor_id: str
    name: str
    type: str
    target: str
    status: str
    uptime_pct_24h: float
    avg_response_time_ms: float
    last_check: str | None
    last_error: str | None


# ── Dependencies ────────────────────────────────────────────────────────

def get_tenant_id(request: Request) -> str:
    tenant_id = request.headers.get("X-Tenant-ID")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-ID header is required")
    return tenant_id


def get_monitor_service(request: Request) -> SyntheticMonitorService:
    return request.app.state.synthetic_monitor_service


def get_scheduler(request: Request) -> SyntheticScheduler:
    return request.app.state.synthetic_scheduler


def get_clickhouse(request: Request):
    return getattr(request.app.state, "clickhouse", None)


# ── In-memory store (production would use ClickHouse) ───────────────────

_monitors: dict[str, MonitorConfig] = {}


def _to_monitor_config(req: CreateMonitorRequest, tenant_id: str) -> MonitorConfig:
    return MonitorConfig(
        id=str(uuid.uuid4()),
        name=req.name,
        type=req.type,
        target=req.target,
        method=req.method,
        headers=req.headers,
        body=req.body,
        assertions=[
            MonitorAssertion(type=a.type, operator=a.operator, expected_value=a.expected_value)
            for a in req.assertions
        ],
        locations=req.locations,
        interval_seconds=req.interval_seconds,
        timeout_seconds=req.timeout_seconds,
        alert_channels=req.alert_channels,
        enabled=req.enabled,
        tags=req.tags,
        tenant_id=tenant_id,
    )


def _to_response(monitor: MonitorConfig) -> MonitorResponse:
    return MonitorResponse(
        id=monitor.id,
        name=monitor.name,
        type=monitor.type,
        target=monitor.target,
        method=monitor.method,
        headers=monitor.headers,
        assertions=[
            AssertionModel(type=a.type, operator=a.operator, expected_value=a.expected_value)
            for a in monitor.assertions
        ],
        locations=monitor.locations,
        interval_seconds=monitor.interval_seconds,
        timeout_seconds=monitor.timeout_seconds,
        alert_channels=monitor.alert_channels,
        enabled=monitor.enabled,
        tags=monitor.tags,
    )


# ── CRUD Endpoints ──────────────────────────────────────────────────────

@router.get("/monitors", response_model=list[MonitorResponse])
async def list_monitors(
    tenant_id: str = Depends(get_tenant_id),
) -> list[MonitorResponse]:
    """List all synthetic monitors for the tenant."""
    return [
        _to_response(m)
        for m in _monitors.values()
        if m.tenant_id == tenant_id
    ]


@router.post("/monitors", response_model=MonitorResponse, status_code=201)
async def create_monitor(
    req: CreateMonitorRequest,
    tenant_id: str = Depends(get_tenant_id),
    scheduler: SyntheticScheduler = Depends(get_scheduler),
) -> MonitorResponse:
    """Create a new synthetic monitor and schedule it."""
    monitor = _to_monitor_config(req, tenant_id)
    _monitors[monitor.id] = monitor

    if monitor.enabled:
        await scheduler.add_monitor(monitor)

    return _to_response(monitor)


@router.get("/monitors/{monitor_id}", response_model=MonitorResponse)
async def get_monitor(
    monitor_id: str,
    tenant_id: str = Depends(get_tenant_id),
) -> MonitorResponse:
    """Get monitor details by ID."""
    monitor = _monitors.get(monitor_id)
    if monitor is None or monitor.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Monitor not found")
    return _to_response(monitor)


@router.put("/monitors/{monitor_id}", response_model=MonitorResponse)
async def update_monitor(
    monitor_id: str,
    req: UpdateMonitorRequest,
    tenant_id: str = Depends(get_tenant_id),
    scheduler: SyntheticScheduler = Depends(get_scheduler),
) -> MonitorResponse:
    """Update an existing monitor and reschedule it."""
    monitor = _monitors.get(monitor_id)
    if monitor is None or monitor.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Monitor not found")

    # Apply partial updates
    if req.name is not None:
        monitor.name = req.name
    if req.type is not None:
        monitor.type = req.type
    if req.target is not None:
        monitor.target = req.target
    if req.method is not None:
        monitor.method = req.method
    if req.headers is not None:
        monitor.headers = req.headers
    if req.body is not None:
        monitor.body = req.body
    if req.assertions is not None:
        monitor.assertions = [
            MonitorAssertion(type=a.type, operator=a.operator, expected_value=a.expected_value)
            for a in req.assertions
        ]
    if req.locations is not None:
        monitor.locations = req.locations
    if req.interval_seconds is not None:
        monitor.interval_seconds = req.interval_seconds
    if req.timeout_seconds is not None:
        monitor.timeout_seconds = req.timeout_seconds
    if req.alert_channels is not None:
        monitor.alert_channels = req.alert_channels
    if req.enabled is not None:
        monitor.enabled = req.enabled
    if req.tags is not None:
        monitor.tags = req.tags

    _monitors[monitor_id] = monitor

    # Reschedule
    await scheduler.remove_monitor(monitor_id)
    if monitor.enabled:
        await scheduler.add_monitor(monitor)

    return _to_response(monitor)


@router.delete("/monitors/{monitor_id}", status_code=204)
async def delete_monitor(
    monitor_id: str,
    tenant_id: str = Depends(get_tenant_id),
    scheduler: SyntheticScheduler = Depends(get_scheduler),
) -> None:
    """Delete a monitor and cancel its scheduled checks."""
    monitor = _monitors.get(monitor_id)
    if monitor is None or monitor.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Monitor not found")

    await scheduler.remove_monitor(monitor_id)
    del _monitors[monitor_id]


# ── Execution Endpoints ─────────────────────────────────────────────────

@router.post("/monitors/{monitor_id}/run", response_model=CheckResultResponse)
async def run_monitor(
    monitor_id: str,
    location: str = Query(default="us-east-1", description="Location to run check from"),
    tenant_id: str = Depends(get_tenant_id),
    service: SyntheticMonitorService = Depends(get_monitor_service),
) -> CheckResultResponse:
    """Trigger a manual check for a monitor."""
    monitor = _monitors.get(monitor_id)
    if monitor is None or monitor.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Monitor not found")

    result = await service.execute_check(monitor, location)

    return CheckResultResponse(
        monitor_id=result.monitor_id,
        location=result.location,
        timestamp=result.timestamp.isoformat(),
        status=result.status.value,
        response_time_ms=result.response_time_ms,
        status_code=result.status_code,
        dns_time_ms=result.dns_time_ms,
        connect_time_ms=result.connect_time_ms,
        tls_time_ms=result.tls_time_ms,
        ttfb_ms=result.ttfb_ms,
        body_size_bytes=result.body_size_bytes,
        assertions_passed=result.assertions_passed,
        error_message=result.error_message,
    )


@router.get("/monitors/{monitor_id}/results", response_model=list[CheckResultResponse])
async def get_results(
    monitor_id: str,
    start: datetime = Query(...),
    end: datetime = Query(...),
    location: str | None = Query(None),
    tenant_id: str = Depends(get_tenant_id),
    ch=Depends(get_clickhouse),
) -> list[CheckResultResponse]:
    """Get check results history for a monitor."""
    monitor = _monitors.get(monitor_id)
    if monitor is None or monitor.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Monitor not found")

    if ch is None:
        return []

    location_filter = ""
    params = {
        "tenant_id": tenant_id,
        "monitor_id": monitor_id,
        "start": start.isoformat(),
        "end": end.isoformat(),
    }
    if location:
        location_filter = "AND location = %(location)s"
        params["location"] = location

    query = f"""
        SELECT *
        FROM synthetic_check_results
        WHERE tenant_id = %(tenant_id)s
          AND monitor_id = %(monitor_id)s
          AND timestamp >= %(start)s
          AND timestamp < %(end)s
          {location_filter}
        ORDER BY timestamp DESC
        LIMIT 1000
    """

    rows = await ch.fetch(query, params)

    return [
        CheckResultResponse(
            monitor_id=row["monitor_id"],
            location=row["location"],
            timestamp=row["timestamp"].isoformat() if hasattr(row["timestamp"], "isoformat") else str(row["timestamp"]),
            status=row["status"],
            response_time_ms=row["response_time_ms"],
            status_code=row.get("status_code"),
            dns_time_ms=row.get("dns_time_ms", 0),
            connect_time_ms=row.get("connect_time_ms", 0),
            tls_time_ms=row.get("tls_time_ms", 0),
            ttfb_ms=row.get("ttfb_ms", 0),
            body_size_bytes=row.get("body_size_bytes", 0),
            assertions_passed=row.get("assertions_passed", []),
            error_message=row.get("error_message"),
        )
        for row in rows
    ]


@router.get("/monitors/{monitor_id}/uptime", response_model=UptimeResponse)
async def get_uptime(
    monitor_id: str,
    start: datetime = Query(...),
    end: datetime = Query(...),
    tenant_id: str = Depends(get_tenant_id),
    service: SyntheticMonitorService = Depends(get_monitor_service),
) -> UptimeResponse:
    """Get uptime stats and incidents for a monitor."""
    monitor = _monitors.get(monitor_id)
    if monitor is None or monitor.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Monitor not found")

    stats = await service.get_uptime(tenant_id, monitor_id, (start, end))

    return UptimeResponse(
        uptime_pct=stats.uptime_pct,
        checks_total=stats.checks_total,
        checks_passed=stats.checks_passed,
        avg_response_time_ms=stats.avg_response_time_ms,
        p95_response_time_ms=stats.p95_response_time_ms,
        incidents=[
            {
                "started_at": inc.started_at.isoformat(),
                "ended_at": inc.ended_at.isoformat() if inc.ended_at else None,
                "duration_seconds": inc.duration_seconds,
                "location": inc.location,
                "error_message": inc.error_message,
            }
            for inc in stats.incidents
        ],
    )


@router.get("/status-page", response_model=list[StatusPageEntry])
async def get_status_page(
    tenant_id: str = Depends(get_tenant_id),
    service: SyntheticMonitorService = Depends(get_monitor_service),
) -> list[StatusPageEntry]:
    """Return current status of all monitors for the public status page."""
    statuses = await service.get_status_page(tenant_id)

    return [
        StatusPageEntry(
            monitor_id=s.monitor_id,
            name=s.name,
            type=s.type.value,
            target=s.target,
            status=s.status.value,
            uptime_pct_24h=s.uptime_pct_24h,
            avg_response_time_ms=s.avg_response_time_ms,
            last_check=s.last_check.isoformat() if s.last_check else None,
            last_error=s.last_error,
        )
        for s in statuses
    ]
