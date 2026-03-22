"""RUM (Real User Monitoring) API routes.

Provides endpoints for ingesting RUM beacon data from browser agents
and querying aggregated analytics for dashboards.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ...services.rum.analytics import RUMAnalytics
from ...services.rum.collector import (
    ActionType,
    ConnectionType,
    DeviceType,
    JSError,
    PageView,
    ReplayEventType,
    ResourceTiming,
    ResourceType,
    RUMCollector,
    SessionReplayEvent,
    UserAction,
)

router = APIRouter(prefix="/api/v1/rum", tags=["rum"])


# ── Request / Response Models ───────────────────────────────────────────

class PageViewPayload(BaseModel):
    session_id: str
    user_id: str | None = None
    page_url: str
    referrer: str | None = None
    timestamp: datetime
    load_time_ms: float
    dom_ready_ms: float
    first_contentful_paint_ms: float
    largest_contentful_paint_ms: float
    first_input_delay_ms: float
    cumulative_layout_shift: float
    time_to_interactive_ms: float
    browser: str
    os: str
    device_type: DeviceType
    country: str | None = None
    city: str | None = None
    connection_type: ConnectionType = ConnectionType.UNKNOWN


class UserActionPayload(BaseModel):
    session_id: str
    action_type: ActionType
    target_element: str
    timestamp: datetime
    duration_ms: float
    error: str | None = None


class ResourceTimingPayload(BaseModel):
    session_id: str
    page_url: str
    resource_url: str
    resource_type: ResourceType
    duration_ms: float
    transfer_size_bytes: int
    timestamp: datetime


class JSErrorPayload(BaseModel):
    session_id: str
    page_url: str
    message: str
    stack_trace: str
    filename: str
    line: int
    column: int
    timestamp: datetime
    user_agent: str
    user_id: str | None = None


class IngestPayload(BaseModel):
    page_views: list[PageViewPayload] = Field(default_factory=list)
    actions: list[UserActionPayload] = Field(default_factory=list)
    resources: list[ResourceTimingPayload] = Field(default_factory=list)
    errors: list[JSErrorPayload] = Field(default_factory=list)


class SessionReplayPayload(BaseModel):
    session_id: str
    event_type: ReplayEventType
    timestamp: datetime
    data: dict = Field(default_factory=dict)


class IngestResponse(BaseModel):
    accepted: int
    errors: int


class WebVitalsResponse(BaseModel):
    lcp_p75: float
    lcp_rating: str
    fid_p75: float
    fid_rating: str
    cls_p75: float
    cls_rating: str
    fcp_p75: float
    fcp_rating: str
    tti_p75: float
    tti_rating: str
    sample_count: int


# ── Dependencies ────────────────────────────────────────────────────────

def get_tenant_id(request: Request) -> str:
    tenant_id = request.headers.get("X-Tenant-ID")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-ID header is required")
    return tenant_id


def get_rum_collector(request: Request) -> RUMCollector:
    return request.app.state.rum_collector


def get_rum_analytics(request: Request) -> RUMAnalytics:
    return request.app.state.rum_analytics


# ── Ingest Endpoints ────────────────────────────────────────────────────

@router.post("/ingest", response_model=IngestResponse)
async def ingest_rum_data(
    payload: IngestPayload,
    tenant_id: str = Depends(get_tenant_id),
    collector: RUMCollector = Depends(get_rum_collector),
) -> IngestResponse:
    """Ingest RUM beacon data: page views, user actions, resource timings, and JS errors."""
    accepted = 0
    errors = 0

    for pv in payload.page_views:
        try:
            await collector.process_page_view(
                tenant_id,
                PageView(
                    session_id=pv.session_id,
                    user_id=pv.user_id,
                    page_url=pv.page_url,
                    referrer=pv.referrer,
                    timestamp=pv.timestamp,
                    load_time_ms=pv.load_time_ms,
                    dom_ready_ms=pv.dom_ready_ms,
                    first_contentful_paint_ms=pv.first_contentful_paint_ms,
                    largest_contentful_paint_ms=pv.largest_contentful_paint_ms,
                    first_input_delay_ms=pv.first_input_delay_ms,
                    cumulative_layout_shift=pv.cumulative_layout_shift,
                    time_to_interactive_ms=pv.time_to_interactive_ms,
                    browser=pv.browser,
                    os=pv.os,
                    device_type=pv.device_type,
                    country=pv.country,
                    city=pv.city,
                    connection_type=pv.connection_type,
                ),
            )
            accepted += 1
        except Exception:
            errors += 1

    for action in payload.actions:
        try:
            await collector.process_action(
                tenant_id,
                UserAction(
                    session_id=action.session_id,
                    action_type=action.action_type,
                    target_element=action.target_element,
                    timestamp=action.timestamp,
                    duration_ms=action.duration_ms,
                    error=action.error,
                ),
            )
            accepted += 1
        except Exception:
            errors += 1

    for res in payload.resources:
        try:
            await collector.process_resource(
                tenant_id,
                ResourceTiming(
                    session_id=res.session_id,
                    page_url=res.page_url,
                    resource_url=res.resource_url,
                    resource_type=res.resource_type,
                    duration_ms=res.duration_ms,
                    transfer_size_bytes=res.transfer_size_bytes,
                    timestamp=res.timestamp,
                ),
            )
            accepted += 1
        except Exception:
            errors += 1

    for err in payload.errors:
        try:
            await collector.process_js_error(
                tenant_id,
                JSError(
                    session_id=err.session_id,
                    page_url=err.page_url,
                    message=err.message,
                    stack_trace=err.stack_trace,
                    filename=err.filename,
                    line=err.line,
                    column=err.column,
                    timestamp=err.timestamp,
                    user_agent=err.user_agent,
                    user_id=err.user_id,
                ),
            )
            accepted += 1
        except Exception:
            errors += 1

    return IngestResponse(accepted=accepted, errors=errors)


@router.post("/session-replay")
async def ingest_session_replay(
    events: list[SessionReplayPayload],
    tenant_id: str = Depends(get_tenant_id),
    collector: RUMCollector = Depends(get_rum_collector),
) -> dict:
    """Ingest session replay events and store them in S3."""
    if not events:
        raise HTTPException(status_code=400, detail="Events list must not be empty")

    replay_events = [
        SessionReplayEvent(
            session_id=e.session_id,
            event_type=e.event_type,
            timestamp=e.timestamp,
            data=e.data,
        )
        for e in events
    ]

    s3_key = await collector.process_session_replay(tenant_id, replay_events)
    return {"status": "accepted", "events": len(events), "s3_key": s3_key}


# ── Analytics Endpoints ─────────────────────────────────────────────────

@router.get("/web-vitals", response_model=WebVitalsResponse)
async def get_web_vitals(
    start: datetime = Query(..., description="Start of time range (ISO 8601)"),
    end: datetime = Query(..., description="End of time range (ISO 8601)"),
    page_url: str | None = Query(None, description="Filter by page URL"),
    tenant_id: str = Depends(get_tenant_id),
    analytics: RUMAnalytics = Depends(get_rum_analytics),
) -> WebVitalsResponse:
    """Return Core Web Vitals (p75) with pass/fail ratings against Google thresholds."""
    vitals = await analytics.get_web_vitals(tenant_id, (start, end), page_url=page_url)
    return WebVitalsResponse(
        lcp_p75=vitals.lcp_p75,
        lcp_rating=vitals.lcp_rating.value,
        fid_p75=vitals.fid_p75,
        fid_rating=vitals.fid_rating.value,
        cls_p75=vitals.cls_p75,
        cls_rating=vitals.cls_rating.value,
        fcp_p75=vitals.fcp_p75,
        fcp_rating=vitals.fcp_rating.value,
        tti_p75=vitals.tti_p75,
        tti_rating=vitals.tti_rating.value,
        sample_count=vitals.sample_count,
    )


@router.get("/pages")
async def get_pages(
    start: datetime = Query(...),
    end: datetime = Query(...),
    tenant_id: str = Depends(get_tenant_id),
    analytics: RUMAnalytics = Depends(get_rum_analytics),
) -> list[dict]:
    """Return page performance metrics grouped by URL."""
    pages = await analytics.get_page_performance(tenant_id, (start, end))
    return [
        {
            "url": p.url,
            "views": p.views,
            "avg_load_time_ms": p.avg_load_time_ms,
            "bounce_rate": p.bounce_rate,
            "error_rate": p.error_rate,
            "web_vitals": {
                "lcp_p75": p.web_vitals.lcp_p75,
                "lcp_rating": p.web_vitals.lcp_rating.value,
                "fid_p75": p.web_vitals.fid_p75,
                "fid_rating": p.web_vitals.fid_rating.value,
                "cls_p75": p.web_vitals.cls_p75,
                "cls_rating": p.web_vitals.cls_rating.value,
            }
            if p.web_vitals
            else None,
        }
        for p in pages
    ]


@router.get("/sessions")
async def get_sessions(
    start: datetime = Query(...),
    end: datetime = Query(...),
    user_id: str | None = Query(None),
    tenant_id: str = Depends(get_tenant_id),
    analytics: RUMAnalytics = Depends(get_rum_analytics),
) -> list[dict]:
    """Return user session summaries."""
    sessions = await analytics.get_user_sessions(tenant_id, (start, end), user_id=user_id)
    return [
        {
            "session_id": s.session_id,
            "user_id": s.user_id,
            "start_time": s.start_time.isoformat(),
            "end_time": s.end_time.isoformat(),
            "page_count": s.page_count,
            "action_count": s.action_count,
            "error_count": s.error_count,
            "duration_ms": s.duration_ms,
            "device_type": s.device_type,
            "browser": s.browser,
            "os": s.os,
            "country": s.country,
        }
        for s in sessions
    ]


@router.get("/sessions/{session_id}")
async def get_session_detail(
    session_id: str,
    tenant_id: str = Depends(get_tenant_id),
    analytics: RUMAnalytics = Depends(get_rum_analytics),
) -> dict:
    """Return detailed session information with replay link."""
    now = datetime.now(UTC)
    time_range = (datetime(2000, 1, 1, tzinfo=UTC), now)

    sessions = await analytics.get_user_sessions(tenant_id, time_range)
    session = next((s for s in sessions if s.session_id == session_id), None)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": session.session_id,
        "user_id": session.user_id,
        "start_time": session.start_time.isoformat(),
        "end_time": session.end_time.isoformat(),
        "page_count": session.page_count,
        "action_count": session.action_count,
        "error_count": session.error_count,
        "duration_ms": session.duration_ms,
        "device_type": session.device_type,
        "browser": session.browser,
        "os": session.os,
        "country": session.country,
        "pages": session.pages,
        "replay_url": f"/api/v1/rum/session-replay/{session_id}",
    }


@router.get("/errors")
async def get_errors(
    start: datetime = Query(...),
    end: datetime = Query(...),
    tenant_id: str = Depends(get_tenant_id),
    analytics: RUMAnalytics = Depends(get_rum_analytics),
) -> list[dict]:
    """Return JS error groups with counts and sample stack traces."""
    error_groups = await analytics.get_error_summary(tenant_id, (start, end))
    return [
        {
            "fingerprint": eg.fingerprint,
            "message": eg.message,
            "filename": eg.filename,
            "line": eg.line,
            "count": eg.count,
            "affected_sessions": eg.affected_sessions,
            "first_seen": eg.first_seen.isoformat(),
            "last_seen": eg.last_seen.isoformat(),
            "sample_stack_trace": eg.sample_stack_trace,
        }
        for eg in error_groups
    ]


@router.get("/geography")
async def get_geography(
    start: datetime = Query(...),
    end: datetime = Query(...),
    tenant_id: str = Depends(get_tenant_id),
    analytics: RUMAnalytics = Depends(get_rum_analytics),
) -> list[dict]:
    """Return performance metrics broken down by country and city."""
    geo = await analytics.get_geography_breakdown(tenant_id, (start, end))
    return [
        {
            "country": g.country,
            "city": g.city,
            "page_views": g.page_views,
            "avg_load_time_ms": g.avg_load_time_ms,
            "lcp_p75": g.lcp_p75,
            "fid_p75": g.fid_p75,
            "cls_p75": g.cls_p75,
            "error_rate": g.error_rate,
        }
        for g in geo
    ]


@router.get("/devices")
async def get_devices(
    start: datetime = Query(...),
    end: datetime = Query(...),
    tenant_id: str = Depends(get_tenant_id),
    analytics: RUMAnalytics = Depends(get_rum_analytics),
) -> list[dict]:
    """Return performance metrics broken down by browser, OS, and device type."""
    devices = await analytics.get_device_breakdown(tenant_id, (start, end))
    return [
        {
            "dimension": d.dimension,
            "dimension_type": d.dimension_type,
            "page_views": d.page_views,
            "avg_load_time_ms": d.avg_load_time_ms,
            "lcp_p75": d.lcp_p75,
            "fid_p75": d.fid_p75,
            "cls_p75": d.cls_p75,
            "error_rate": d.error_rate,
        }
        for d in devices
    ]
