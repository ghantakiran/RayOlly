"""APM API routes.

Exposes service maps, latency analysis, error tracking, profiling,
and SLO management via a FastAPI router.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from rayolly.services.apm.errors import ErrorTracker
from rayolly.services.apm.latency import LatencyAnalyzer
from rayolly.services.apm.profiling import (
    ProfileData,
    ProfileFormat,
    ProfileType,
    ProfilingService,
)
from rayolly.services.apm.service_map import ServiceMapBuilder
from rayolly.services.apm.slo import (
    AlertSeverity,
    BurnRateAlert,
    SLIType,
    SLODefinition,
    SLOService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/apm", tags=["apm"])


# ---------------------------------------------------------------------------
# Dependency stubs — replace with real DI in production
# ---------------------------------------------------------------------------

async def get_clickhouse() -> Any:
    """Return the ClickHouse async client (injected at app startup)."""
    from rayolly.core.dependencies import get_clickhouse_client
    return await get_clickhouse_client()


async def get_s3() -> Any:
    from rayolly.core.dependencies import get_s3_client
    return await get_s3_client()


async def get_anomaly_detector() -> Any:
    from rayolly.core.dependencies import get_anomaly_detector as _get_anomaly_detector
    return await _get_anomaly_detector()


def get_tenant_id() -> str:
    """Extract tenant_id from auth context. Stub returns default."""
    return "default"


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class TimeRangeParams:
    """Common time range query parameters."""

    def __init__(
        self,
        start: datetime | None = Query(None, description="Start of time range (ISO 8601)"),
        end: datetime | None = Query(None, description="End of time range (ISO 8601)"),
        last: str | None = Query("1h", description="Relative time range, e.g. 1h, 6h, 24h, 7d"),
    ):
        if start and end:
            self.start = start
            self.end = end
        else:
            self.end = datetime.utcnow()
            self.start = self.end - self._parse_duration(last or "1h")

    @staticmethod
    def _parse_duration(s: str) -> timedelta:
        unit = s[-1]
        value = int(s[:-1])
        if unit == "m":
            return timedelta(minutes=value)
        if unit == "h":
            return timedelta(hours=value)
        if unit == "d":
            return timedelta(days=value)
        return timedelta(hours=1)

    @property
    def range(self) -> tuple[datetime, datetime]:
        return (self.start, self.end)


class CompareRequest(BaseModel):
    service: str
    operation: str
    range_a_start: datetime
    range_a_end: datetime
    range_b_start: datetime
    range_b_end: datetime


class SLOCreateRequest(BaseModel):
    name: str
    service: str
    sli_type: str  # availability, latency, throughput
    sli_query: str
    target_percentage: float = Field(ge=0, le=100)
    window_days: int = Field(ge=1, le=365)
    alert_burn_rates: list[dict[str, Any]] = Field(default_factory=list)


class ProfileIngestRequest(BaseModel):
    profile_type: str
    service: str
    duration_seconds: float
    sample_count: int
    format: str = "pprof"


# ---------------------------------------------------------------------------
# Service list & map
# ---------------------------------------------------------------------------

@router.get("/services")
async def list_services(
    tr: TimeRangeParams = Depends(),
    ch: Any = Depends(get_clickhouse),
    tenant_id: str = Depends(get_tenant_id),
) -> dict[str, Any]:
    """List all services with health status and key metrics."""
    builder = ServiceMapBuilder()
    svc_map = await builder.build_from_traces(tenant_id, tr.range, ch)
    return {
        "services": [
            {
                "name": n.service_name,
                "type": n.service_type.value,
                "health": n.health_status.value,
                "request_rate": n.metrics.request_rate,
                "error_rate": n.metrics.error_rate,
                "p50_latency": n.metrics.p50_latency,
                "p99_latency": n.metrics.p99_latency,
                "dependencies": n.dependencies,
            }
            for n in svc_map.nodes
        ],
        "last_updated": svc_map.last_updated.isoformat(),
    }


@router.get("/services/{service}/overview")
async def service_overview(
    service: str,
    tr: TimeRangeParams = Depends(),
    ch: Any = Depends(get_clickhouse),
    tenant_id: str = Depends(get_tenant_id),
) -> dict[str, Any]:
    """Detailed overview of a single service."""
    builder = ServiceMapBuilder()
    detail = await builder.get_service_detail(tenant_id, service, tr.range, ch)
    return {
        "service": detail.service_name,
        "type": detail.service_type.value,
        "health": detail.health_status.value,
        "metrics": {
            "request_rate": detail.metrics.request_rate,
            "error_rate": detail.metrics.error_rate,
            "p50_latency": detail.metrics.p50_latency,
            "p99_latency": detail.metrics.p99_latency,
        },
        "top_endpoints": [
            {
                "operation": ep.operation,
                "request_rate": ep.request_rate,
                "error_rate": ep.error_rate,
                "p50_latency": ep.p50_latency,
                "p99_latency": ep.p99_latency,
            }
            for ep in detail.top_endpoints
        ],
        "dependencies": detail.dependencies,
        "dependents": detail.dependents,
        "recent_errors": [
            {
                "message": e.message,
                "count": e.count,
                "first_seen": e.first_seen.isoformat(),
                "last_seen": e.last_seen.isoformat(),
            }
            for e in detail.recent_errors
        ],
        "deployments": [
            {
                "version": d.version,
                "deployed_at": d.deployed_at.isoformat(),
                "deployer": d.deployer,
            }
            for d in detail.deployment_history
        ],
    }


@router.get("/service-map")
async def service_map(
    tr: TimeRangeParams = Depends(),
    ch: Any = Depends(get_clickhouse),
    tenant_id: str = Depends(get_tenant_id),
) -> dict[str, Any]:
    """Get the full service dependency map."""
    builder = ServiceMapBuilder()
    svc_map = await builder.build_from_traces(tenant_id, tr.range, ch)
    return {
        "nodes": [
            {
                "id": n.service_name,
                "type": n.service_type.value,
                "health": n.health_status.value,
                "metrics": {
                    "request_rate": n.metrics.request_rate,
                    "error_rate": n.metrics.error_rate,
                    "p50_latency": n.metrics.p50_latency,
                    "p99_latency": n.metrics.p99_latency,
                },
            }
            for n in svc_map.nodes
        ],
        "edges": [
            {
                "source": e.source,
                "target": e.target,
                "protocol": e.protocol,
                "request_rate": e.request_rate,
                "error_rate": e.error_rate,
                "avg_latency_ms": e.avg_latency_ms,
            }
            for e in svc_map.edges
        ],
        "last_updated": svc_map.last_updated.isoformat(),
    }


# ---------------------------------------------------------------------------
# Endpoints & Latency
# ---------------------------------------------------------------------------

@router.get("/services/{service}/endpoints")
async def list_endpoints(
    service: str,
    tr: TimeRangeParams = Depends(),
    ch: Any = Depends(get_clickhouse),
    tenant_id: str = Depends(get_tenant_id),
) -> dict[str, Any]:
    """List endpoints with latency and error stats."""
    rows = await ch.execute(
        """
        SELECT
            operation_name,
            count() AS request_count,
            countIf(status_code >= 400) / count() AS error_rate,
            quantile(0.50)(duration_ms) AS p50,
            quantile(0.99)(duration_ms) AS p99
        FROM traces.spans
        WHERE tenant_id = %(tenant_id)s
          AND service_name = %(service)s
          AND timestamp BETWEEN %(start)s AND %(end)s
          AND parent_span_id = ''
        GROUP BY operation_name
        ORDER BY request_count DESC
        """,
        {"tenant_id": tenant_id, "service": service, "start": tr.start, "end": tr.end},
    )
    interval = max((tr.end - tr.start).total_seconds(), 1)
    return {
        "endpoints": [
            {
                "operation": r["operation_name"],
                "request_rate": float(r["request_count"]) / interval,
                "error_rate": float(r["error_rate"]),
                "p50_latency": float(r["p50"]),
                "p99_latency": float(r["p99"]),
            }
            for r in rows
        ]
    }


@router.get("/services/{service}/endpoints/{operation}/latency")
async def endpoint_latency(
    service: str,
    operation: str,
    tr: TimeRangeParams = Depends(),
    ch: Any = Depends(get_clickhouse),
    tenant_id: str = Depends(get_tenant_id),
) -> dict[str, Any]:
    """Latency analysis for a specific endpoint."""
    analyzer = LatencyAnalyzer()
    analysis = await analyzer.analyze_endpoint(tenant_id, service, operation, tr.range, ch)
    return {
        "service": analysis.service,
        "operation": analysis.operation,
        "p50": analysis.p50,
        "p75": analysis.p75,
        "p90": analysis.p90,
        "p95": analysis.p95,
        "p99": analysis.p99,
        "max": analysis.max,
        "request_count": analysis.request_count,
        "error_count": analysis.error_count,
        "slow_trace_ids": analysis.slow_trace_ids,
        "histogram": [
            {"le": b.le, "count": b.count} for b in analysis.latency_histogram_buckets
        ],
    }


@router.get("/traces/{trace_id}/breakdown")
async def trace_breakdown(
    trace_id: str,
    ch: Any = Depends(get_clickhouse),
    tenant_id: str = Depends(get_tenant_id),
) -> dict[str, Any]:
    """Latency breakdown for a specific trace."""
    analyzer = LatencyAnalyzer()
    breakdown = await analyzer.breakdown_latency(tenant_id, trace_id, ch)
    if not breakdown.spans:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")
    return {
        "trace_id": breakdown.trace_id,
        "total_duration_ms": breakdown.total_duration_ms,
        "spans": [
            {
                "span_id": s.span_id,
                "name": s.name,
                "service": s.service,
                "duration_ms": s.duration_ms,
                "percentage": s.percentage_of_total,
                "is_critical_path": s.is_critical_path,
            }
            for s in breakdown.spans
        ],
    }


@router.post("/compare")
async def compare_latency(
    body: CompareRequest,
    ch: Any = Depends(get_clickhouse),
    tenant_id: str = Depends(get_tenant_id),
) -> dict[str, Any]:
    """Compare latency between two time ranges."""
    analyzer = LatencyAnalyzer()
    comparison = await analyzer.compare_latency(
        tenant_id,
        body.service,
        body.operation,
        (body.range_a_start, body.range_a_end),
        (body.range_b_start, body.range_b_end),
        ch,
    )
    return {
        "service": comparison.service,
        "operation": comparison.operation,
        "before": {
            "p50": comparison.before.p50,
            "p99": comparison.before.p99,
            "request_count": comparison.before.request_count,
        },
        "after": {
            "p50": comparison.after.p50,
            "p99": comparison.after.p99,
            "request_count": comparison.after.request_count,
        },
        "delta_p50": comparison.delta_p50,
        "delta_p99": comparison.delta_p99,
        "regression_detected": comparison.regression_detected,
    }


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

@router.get("/services/{service}/errors")
async def list_errors(
    service: str,
    tr: TimeRangeParams = Depends(),
    ch: Any = Depends(get_clickhouse),
    tenant_id: str = Depends(get_tenant_id),
) -> dict[str, Any]:
    """List error groups for a service."""
    tracker = ErrorTracker()
    groups = await tracker.get_error_groups(tenant_id, service, tr.range, ch)
    return {
        "error_groups": [
            {
                "fingerprint": g.fingerprint,
                "message": g.message,
                "count": g.count,
                "status": g.status.value,
                "first_seen": g.first_seen.isoformat(),
                "last_seen": g.last_seen.isoformat(),
                "affected_users": g.affected_users,
                "sample_trace_ids": g.sample_trace_ids,
            }
            for g in groups
        ]
    }


@router.get("/services/{service}/errors/{fingerprint}")
async def error_detail(
    service: str,
    fingerprint: str,
    tr: TimeRangeParams = Depends(),
    ch: Any = Depends(get_clickhouse),
    tenant_id: str = Depends(get_tenant_id),
) -> dict[str, Any]:
    """Get detailed information about an error group."""
    tracker = ErrorTracker()
    groups = await tracker.get_error_groups(tenant_id, service, tr.range, ch)
    group = next((g for g in groups if g.fingerprint == fingerprint), None)
    if not group:
        raise HTTPException(status_code=404, detail=f"Error group {fingerprint} not found")

    classification = await tracker.classify_error(group.message, group.stack_trace)
    return {
        "fingerprint": group.fingerprint,
        "message": group.message,
        "count": group.count,
        "status": group.status.value,
        "first_seen": group.first_seen.isoformat(),
        "last_seen": group.last_seen.isoformat(),
        "affected_users": group.affected_users,
        "sample_trace_ids": group.sample_trace_ids,
        "stack_trace": group.stack_trace,
        "classification": {
            "type": classification.error_type,
            "category": classification.category.value,
            "is_known": classification.is_known,
            "suggested_fix": classification.suggested_fix,
        },
    }


# ---------------------------------------------------------------------------
# SLOs
# ---------------------------------------------------------------------------

@router.get("/slos")
async def list_slos(
    ch: Any = Depends(get_clickhouse),
    tenant_id: str = Depends(get_tenant_id),
) -> dict[str, Any]:
    """List all SLOs with their current status."""
    slo_service = SLOService()
    statuses = await slo_service.evaluate_all(tenant_id, ch)
    return {
        "slos": [
            {
                "id": s.definition.id,
                "name": s.definition.name,
                "service": s.definition.service,
                "sli_type": s.definition.sli_type.value,
                "target": s.definition.target_percentage,
                "current_value": s.current_value,
                "error_budget_remaining_pct": s.error_budget_remaining_pct,
                "burn_rate_1h": s.burn_rate_1h,
                "is_breaching": s.is_breaching,
                "predicted_breach_time": (
                    s.predicted_breach_time.isoformat() if s.predicted_breach_time else None
                ),
            }
            for s in statuses
        ]
    }


@router.post("/slos")
async def create_slo(
    body: SLOCreateRequest,
    ch: Any = Depends(get_clickhouse),
    tenant_id: str = Depends(get_tenant_id),
) -> dict[str, Any]:
    """Create a new SLO definition."""
    import uuid

    slo_id = str(uuid.uuid4())

    burn_rates = [
        BurnRateAlert(
            burn_rate=float(br.get("burn_rate", 14.4)),
            window=str(br.get("window", "1h")),
            severity=AlertSeverity(br.get("severity", "critical")),
        )
        for br in body.alert_burn_rates
    ]

    await ch.execute(
        """
        INSERT INTO apm.slo_definitions (
            tenant_id, id, name, service_name, sli_type, sli_query,
            target_percentage, window_days, alert_burn_rates
        ) VALUES (
            %(tenant_id)s, %(id)s, %(name)s, %(service)s, %(sli_type)s,
            %(sli_query)s, %(target)s, %(window_days)s, %(burn_rates)s
        )
        """,
        {
            "tenant_id": tenant_id,
            "id": slo_id,
            "name": body.name,
            "service": body.service,
            "sli_type": body.sli_type,
            "sli_query": body.sli_query,
            "target": body.target_percentage,
            "window_days": body.window_days,
            "burn_rates": str([
                {"burn_rate": br.burn_rate, "window": br.window, "severity": br.severity.value}
                for br in burn_rates
            ]),
        },
    )

    return {"id": slo_id, "name": body.name, "status": "created"}


@router.get("/slos/{slo_id}/status")
async def slo_status(
    slo_id: str,
    ch: Any = Depends(get_clickhouse),
    tenant_id: str = Depends(get_tenant_id),
) -> dict[str, Any]:
    """Get detailed SLO status including error budget history."""
    rows = await ch.execute(
        """
        SELECT id, name, service_name, sli_type, sli_query,
               target_percentage, window_days, alert_burn_rates
        FROM apm.slo_definitions
        WHERE tenant_id = %(tenant_id)s AND id = %(id)s
        LIMIT 1
        """,
        {"tenant_id": tenant_id, "id": slo_id},
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"SLO {slo_id} not found")

    row = rows[0]
    slo = SLODefinition(
        id=row["id"],
        name=row["name"],
        service=row["service_name"],
        sli_type=SLIType(row["sli_type"]),
        sli_query=row["sli_query"],
        target_percentage=float(row["target_percentage"]),
        window_days=int(row["window_days"]),
    )

    slo_service = SLOService()
    status = await slo_service.evaluate(tenant_id, slo, ch)

    budget_history = await slo_service.get_error_budget_history(
        tenant_id,
        slo_id,
        (datetime.utcnow() - timedelta(days=slo.window_days), datetime.utcnow()),
        ch,
    )

    return {
        "id": status.definition.id,
        "name": status.definition.name,
        "service": status.definition.service,
        "target": status.definition.target_percentage,
        "current_value": status.current_value,
        "error_budget_remaining_pct": status.error_budget_remaining_pct,
        "burn_rate_1h": status.burn_rate_1h,
        "burn_rate_6h": status.burn_rate_6h,
        "burn_rate_24h": status.burn_rate_24h,
        "is_breaching": status.is_breaching,
        "predicted_breach_time": (
            status.predicted_breach_time.isoformat() if status.predicted_breach_time else None
        ),
        "budget_history": [
            {"timestamp": p.timestamp.isoformat(), "remaining_pct": p.budget_remaining_pct}
            for p in budget_history
        ],
    }


# ---------------------------------------------------------------------------
# Profiling
# ---------------------------------------------------------------------------

@router.get("/profiles")
async def list_profiles(
    service: str = Query(...),
    profile_type: str = Query("cpu"),
    tr: TimeRangeParams = Depends(),
    ch: Any = Depends(get_clickhouse),
    s3: Any = Depends(get_s3),
    tenant_id: str = Depends(get_tenant_id),
) -> dict[str, Any]:
    """List available profiles."""
    profiling = ProfilingService(s3, ch)
    profiles = await profiling.get_profiles(
        tenant_id, service, ProfileType(profile_type), tr.range
    )
    return {
        "profiles": [
            {
                "profile_id": p.profile_id,
                "type": p.profile_type.value,
                "service": p.service,
                "timestamp": p.timestamp.isoformat(),
                "duration_seconds": p.duration_seconds,
                "sample_count": p.sample_count,
                "format": p.format.value,
                "size_bytes": p.size_bytes,
            }
            for p in profiles
        ]
    }


@router.post("/profiles/ingest")
async def ingest_profile(
    file: UploadFile = File(...),
    profile_type: str = Query("cpu"),
    service: str = Query(...),
    duration_seconds: float = Query(60.0),
    sample_count: int = Query(0),
    format: str = Query("pprof"),
    ch: Any = Depends(get_clickhouse),
    s3: Any = Depends(get_s3),
    tenant_id: str = Depends(get_tenant_id),
) -> dict[str, Any]:
    """Ingest a profile data file."""
    data = await file.read()
    profile = ProfileData(
        profile_type=ProfileType(profile_type),
        service=service,
        timestamp=datetime.utcnow(),
        duration_seconds=duration_seconds,
        sample_count=sample_count,
        data=data,
        format=ProfileFormat(format),
    )
    profiling = ProfilingService(s3, ch)
    profile_id = await profiling.ingest_profile(tenant_id, profile)
    return {"profile_id": profile_id, "size_bytes": len(data), "status": "ingested"}
