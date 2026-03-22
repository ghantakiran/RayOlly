"""Agent Observability API routes — monitor AI agent performance.

Exposes dashboards, metrics, traces, cost breakdowns, error analysis,
tool usage statistics, satisfaction trends, automated issue detection,
execution waterfalls, accuracy tracking, hallucination detection,
cost forecasting, A/B testing, and agent SLOs.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from rayolly.core.dependencies import get_clickhouse, get_current_tenant
from rayolly.services.agents.ab_testing import (
    ABExperiment,
    ABVariant,
    AgentABTestService,
)
from rayolly.services.agents.accuracy import AgentAccuracyTracker
from rayolly.services.agents.cost_forecaster import AgentCostForecaster
from rayolly.services.agents.observability import (
    AgentFeedback,
    AgentObservabilityService,
    FeedbackRating,
)
from rayolly.services.agents.slos import AgentSLO, AgentSLOService
from rayolly.services.agents.tracing import AgentTracer

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/agents/observability",
    tags=["agent-observability"],
)

# Singleton service instance
_service = AgentObservabilityService()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class FeedbackRequest(BaseModel):
    execution_id: str
    rating: str = Field(..., description="thumbs_up or thumbs_down")
    comment: str = ""


class FeedbackResponse(BaseModel):
    status: str = "recorded"
    execution_id: str


class DashboardResponse(BaseModel):
    agent_metrics: list[dict[str, Any]]
    top_errors: list[dict[str, Any]]
    cost_breakdown: dict[str, Any]
    satisfaction_trend: list[dict[str, Any]]
    total_executions: int
    overall_success_rate: float
    total_cost_usd: float
    avg_duration_seconds: float


class MetricsResponse(BaseModel):
    agent_type: str
    total_executions: int
    successful: int
    failed: int
    cancelled: int
    avg_duration_seconds: float
    p50_duration: float
    p95_duration: float
    avg_tokens_used: float
    total_cost_usd: float
    avg_tools_per_execution: float
    success_rate_pct: float
    user_satisfaction_rate: float


class TraceResponse(BaseModel):
    execution_id: str
    agent_type: str
    tenant_id: str
    started_at: str
    completed_at: str | None
    duration_ms: int
    status: str
    steps: list[dict[str, Any]]
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    model_used: str
    error_message: str | None


class IssueResponse(BaseModel):
    issue_type: str
    severity: str
    agent_type: str
    description: str
    metric_value: float
    threshold: float
    recommendation: str
    detected_at: str


class CreateExperimentRequest(BaseModel):
    agent_type: str
    name: str
    description: str = ""
    variant_a_description: str = "Control"
    variant_a_model: str | None = None
    variant_b_description: str = "Treatment"
    variant_b_model: str | None = None
    traffic_split: float = 0.5
    success_metric: str = "accuracy"
    min_sample_size: int = 100


class CreateSLORequest(BaseModel):
    name: str
    agent_type: str
    sli_type: str = Field(..., description="success_rate, latency_p95, cost_per_execution, accuracy")
    target: float
    window_days: int = 30


# ---------------------------------------------------------------------------
# Existing routes
# ---------------------------------------------------------------------------

@router.get("/dashboard", response_model=DashboardResponse)
async def get_agent_dashboard(
    time_range: str = Query("24h", description="Time range: 1h, 6h, 24h, 7d, 30d"),
    tenant_id: str = Depends(get_current_tenant),
    clickhouse: Any = Depends(get_clickhouse),
) -> Any:
    """Return the full agent observability dashboard."""

    dashboard = await _service.get_agent_dashboard(tenant_id, time_range, clickhouse)

    return DashboardResponse(
        agent_metrics=[asdict(m) for m in dashboard.agent_metrics],
        top_errors=[asdict(e) for e in dashboard.top_errors],
        cost_breakdown=asdict(dashboard.cost_breakdown),
        satisfaction_trend=[
            {
                "timestamp": p.timestamp.isoformat() if hasattr(p.timestamp, "isoformat") else str(p.timestamp),
                "thumbs_up": p.thumbs_up,
                "thumbs_down": p.thumbs_down,
                "satisfaction_pct": p.satisfaction_pct,
            }
            for p in dashboard.satisfaction_trend
        ],
        total_executions=dashboard.total_executions,
        overall_success_rate=dashboard.overall_success_rate,
        total_cost_usd=dashboard.total_cost_usd,
        avg_duration_seconds=dashboard.avg_duration_seconds,
    )


@router.get("/metrics", response_model=MetricsResponse)
async def get_agent_metrics(
    agent_type: str = Query(..., description="Agent type: rca, query, incident, anomaly"),
    time_range: str = Query("24h"),
    tenant_id: str = Depends(get_current_tenant),
    clickhouse: Any = Depends(get_clickhouse),
) -> Any:
    """Return metrics for a specific agent type."""

    metrics = await _service.get_agent_metrics(
        tenant_id, agent_type, time_range, clickhouse
    )
    return MetricsResponse(**asdict(metrics))


@router.get("/executions")
async def list_executions(
    time_range: str = Query("24h"),
    agent_type: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    tenant_id: str = Depends(get_current_tenant),
    clickhouse: Any = Depends(get_clickhouse),
) -> dict[str, Any]:
    """List recent agent executions with summary data."""

    executions = await _service.list_executions(
        tenant_id=tenant_id,
        time_range=time_range,
        clickhouse=clickhouse,
        agent_type=agent_type,
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )

    return {"executions": executions, "count": len(executions)}


@router.get("/executions/{execution_id}/trace", response_model=TraceResponse)
async def get_execution_trace(
    execution_id: str,
    tenant_id: str = Depends(get_current_tenant),
    clickhouse: Any = Depends(get_clickhouse),
) -> Any:
    """Return the full execution trace with all steps."""

    trace = await _service.get_execution_trace(execution_id, clickhouse)

    if trace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execution trace {execution_id} not found",
        )

    if trace.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return TraceResponse(
        execution_id=trace.execution_id,
        agent_type=trace.agent_type,
        tenant_id=trace.tenant_id,
        started_at=trace.started_at.isoformat() if hasattr(trace.started_at, "isoformat") else str(trace.started_at),
        completed_at=trace.completed_at.isoformat() if trace.completed_at and hasattr(trace.completed_at, "isoformat") else None,
        duration_ms=trace.duration_ms,
        status=trace.status,
        steps=[
            {
                "step_number": s.step_number,
                "type": s.type.value,
                "timestamp": s.timestamp.isoformat() if hasattr(s.timestamp, "isoformat") else str(s.timestamp),
                "duration_ms": s.duration_ms,
                "content_preview": s.content_preview,
                "tool_name": s.tool_name,
                "tool_input": s.tool_input,
                "tool_output_preview": s.tool_output_preview,
                "tokens_used": s.tokens_used,
            }
            for s in trace.steps
        ],
        total_input_tokens=trace.total_input_tokens,
        total_output_tokens=trace.total_output_tokens,
        total_cost_usd=trace.total_cost_usd,
        model_used=trace.model_used,
        error_message=trace.error_message,
    )


@router.get("/costs")
async def get_cost_breakdown(
    time_range: str = Query("24h"),
    tenant_id: str = Depends(get_current_tenant),
    clickhouse: Any = Depends(get_clickhouse),
) -> dict[str, Any]:
    """Return cost breakdown by agent type, tenant, and model."""

    breakdown = await _service.get_cost_breakdown(tenant_id, time_range, clickhouse)
    return asdict(breakdown)


@router.get("/errors")
async def get_error_analysis(
    time_range: str = Query("24h"),
    tenant_id: str = Depends(get_current_tenant),
    clickhouse: Any = Depends(get_clickhouse),
) -> dict[str, Any]:
    """Return common failure patterns with root-cause analysis."""

    errors = await _service.get_error_analysis(tenant_id, time_range, clickhouse)
    return {"errors": [asdict(e) for e in errors], "count": len(errors)}


@router.get("/tools")
async def get_tool_usage(
    time_range: str = Query("24h"),
    tenant_id: str = Depends(get_current_tenant),
    clickhouse: Any = Depends(get_clickhouse),
) -> dict[str, Any]:
    """Return tool usage statistics across all agents."""

    tools = await _service.get_tool_usage(tenant_id, time_range, clickhouse)
    return {"tools": [asdict(t) for t in tools], "count": len(tools)}


@router.get("/satisfaction")
async def get_satisfaction_trend(
    time_range: str = Query("24h"),
    tenant_id: str = Depends(get_current_tenant),
    clickhouse: Any = Depends(get_clickhouse),
) -> dict[str, Any]:
    """Return satisfaction trend over time."""

    trend = await _service.get_satisfaction_trend(tenant_id, time_range, clickhouse)
    return {
        "trend": [
            {
                "timestamp": p.timestamp.isoformat() if hasattr(p.timestamp, "isoformat") else str(p.timestamp),
                "thumbs_up": p.thumbs_up,
                "thumbs_down": p.thumbs_down,
                "satisfaction_pct": p.satisfaction_pct,
            }
            for p in trend
        ],
        "count": len(trend),
    }


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    body: FeedbackRequest,
    tenant_id: str = Depends(get_current_tenant),
    clickhouse: Any = Depends(get_clickhouse),
) -> FeedbackResponse:
    """Submit user feedback (thumbs up/down) for an agent execution."""

    try:
        rating = FeedbackRating(body.rating)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid rating: {body.rating}. Must be 'thumbs_up' or 'thumbs_down'.",
        )

    feedback = AgentFeedback(
        execution_id=body.execution_id,
        tenant_id=tenant_id,
        user_id="",  # Populated from auth context in production
        rating=rating,
        comment=body.comment,
    )

    await _service.record_feedback(feedback, clickhouse)

    return FeedbackResponse(
        status="recorded",
        execution_id=body.execution_id,
    )


@router.get("/issues")
async def get_detected_issues(
    tenant_id: str = Depends(get_current_tenant),
    clickhouse: Any = Depends(get_clickhouse),
) -> dict[str, Any]:
    """Return automatically detected agent issues."""

    issues = await _service.detect_agent_issues(tenant_id, clickhouse)

    return {
        "issues": [
            {
                "issue_type": i.issue_type,
                "severity": i.severity.value,
                "agent_type": i.agent_type,
                "description": i.description,
                "metric_value": i.metric_value,
                "threshold": i.threshold,
                "recommendation": i.recommendation,
                "detected_at": i.detected_at.isoformat(),
            }
            for i in issues
        ],
        "count": len(issues),
    }


# ---------------------------------------------------------------------------
# NEW: Execution Waterfall Traces
# ---------------------------------------------------------------------------

@router.get("/executions/{execution_id}/waterfall")
async def get_execution_waterfall(
    execution_id: str,
    tenant_id: str = Depends(get_current_tenant),
    clickhouse: Any = Depends(get_clickhouse),
) -> dict[str, Any]:
    """Return execution waterfall trace with span-level timing data.

    Provides a Gantt-chart-style view of every step in an agent execution,
    including thinking, LLM calls, tool calls, and responses with their
    duration, token usage, and cost.
    """
    waterfall = await AgentTracer.load_waterfall(execution_id, clickhouse)

    if waterfall is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Waterfall data for execution {execution_id} not found",
        )

    return waterfall.to_dict()


# ---------------------------------------------------------------------------
# NEW: Accuracy & Hallucination Detection
# ---------------------------------------------------------------------------

@router.get("/accuracy")
async def get_accuracy_trend(
    agent_type: str | None = Query(None),
    days: int = Query(30, ge=1, le=90),
    tenant_id: str = Depends(get_current_tenant),
    clickhouse: Any = Depends(get_clickhouse),
) -> dict[str, Any]:
    """Return accuracy trend over time, optionally filtered by agent type."""
    tracker = AgentAccuracyTracker(clickhouse)
    trend = await tracker.get_accuracy_trend(tenant_id, agent_type, days)

    return {
        "trend": [asdict(p) for p in trend],
        "count": len(trend),
    }


@router.get("/accuracy/{execution_id}")
async def validate_execution_accuracy(
    execution_id: str,
    tenant_id: str = Depends(get_current_tenant),
    clickhouse: Any = Depends(get_clickhouse),
) -> dict[str, Any]:
    """Validate accuracy of a specific execution's output against tool results."""
    tracker = AgentAccuracyTracker(clickhouse)
    report = await tracker.validate_execution(execution_id, tenant_id)

    return {
        "execution_id": report.execution_id,
        "total_claims": report.total_claims,
        "valid_claims": report.valid_claims,
        "invalid_claims": report.invalid_claims,
        "accuracy_pct": report.accuracy_pct,
        "hallucinations": [
            {
                "execution_id": h.execution_id,
                "step_number": h.step_number,
                "claim_text": h.claim_text,
                "expected_data": h.expected_data,
                "actual_data": h.actual_data,
                "severity": h.severity,
            }
            for h in report.hallucinations
        ],
    }


@router.get("/hallucinations")
async def get_recent_hallucinations(
    limit: int = Query(50, ge=1, le=200),
    tenant_id: str = Depends(get_current_tenant),
    clickhouse: Any = Depends(get_clickhouse),
) -> dict[str, Any]:
    """Return recently detected hallucinations across all agent executions."""
    tracker = AgentAccuracyTracker(clickhouse)
    results = await tracker.get_recent_hallucinations(tenant_id, limit)

    return {"hallucinations": results, "count": len(results)}


# ---------------------------------------------------------------------------
# NEW: Cost Forecasting & Budget Management
# ---------------------------------------------------------------------------

@router.get("/costs/forecast")
async def get_cost_forecast(
    tenant_id: str = Depends(get_current_tenant),
    clickhouse: Any = Depends(get_clickhouse),
) -> dict[str, Any]:
    """Return monthly cost forecast based on current usage trends."""
    forecaster = AgentCostForecaster(clickhouse)
    forecast = await forecaster.forecast_monthly_cost(tenant_id)

    return asdict(forecast)


@router.get("/costs/budget")
async def get_budget_status(
    daily_budget: float = Query(100.0, ge=0, description="Daily budget in USD"),
    tenant_id: str = Depends(get_current_tenant),
    clickhouse: Any = Depends(get_clickhouse),
) -> dict[str, Any]:
    """Check current budget status and projected overage."""
    forecaster = AgentCostForecaster(clickhouse)
    budget = await forecaster.check_budget(tenant_id, daily_budget)

    return asdict(budget)


@router.get("/costs/suggestions")
async def get_cost_suggestions(
    tenant_id: str = Depends(get_current_tenant),
    clickhouse: Any = Depends(get_clickhouse),
) -> dict[str, Any]:
    """Return actionable cost optimization suggestions."""
    forecaster = AgentCostForecaster(clickhouse)
    suggestions = await forecaster.get_cost_optimization_suggestions(tenant_id)

    return {
        "suggestions": [asdict(s) for s in suggestions],
        "count": len(suggestions),
    }


# ---------------------------------------------------------------------------
# NEW: A/B Testing
# ---------------------------------------------------------------------------

@router.get("/experiments")
async def list_experiments(
    status_filter: str | None = Query(None, alias="status"),
    tenant_id: str = Depends(get_current_tenant),
    clickhouse: Any = Depends(get_clickhouse),
) -> dict[str, Any]:
    """List all A/B test experiments."""
    ab_service = AgentABTestService(clickhouse)
    experiments = await ab_service.list_experiments(tenant_id, status_filter)

    return {"experiments": experiments, "count": len(experiments)}


@router.post("/experiments")
async def create_experiment(
    body: CreateExperimentRequest,
    tenant_id: str = Depends(get_current_tenant),
    clickhouse: Any = Depends(get_clickhouse),
) -> dict[str, Any]:
    """Create a new A/B test experiment for an agent type."""
    ab_service = AgentABTestService(clickhouse)

    experiment = ABExperiment(
        id="",
        tenant_id=tenant_id,
        agent_type=body.agent_type,
        name=body.name,
        description=body.description,
        variant_a=ABVariant(
            name="A",
            description=body.variant_a_description,
            model=body.variant_a_model,
        ),
        variant_b=ABVariant(
            name="B",
            description=body.variant_b_description,
            model=body.variant_b_model,
        ),
        traffic_split=body.traffic_split,
        success_metric=body.success_metric,
        min_sample_size=body.min_sample_size,
    )

    result = await ab_service.create_experiment(tenant_id, experiment)

    return {
        "id": result.id,
        "name": result.name,
        "agent_type": result.agent_type,
        "status": result.status,
        "started_at": result.started_at,
    }


@router.get("/experiments/{experiment_id}/results")
async def get_experiment_results(
    experiment_id: str,
    tenant_id: str = Depends(get_current_tenant),
    clickhouse: Any = Depends(get_clickhouse),
) -> dict[str, Any]:
    """Get A/B experiment results with statistical significance analysis."""
    ab_service = AgentABTestService(clickhouse)
    results = await ab_service.get_results(experiment_id, tenant_id)

    return {
        "experiment": {
            "id": results.experiment.id,
            "name": results.experiment.name,
            "agent_type": results.experiment.agent_type,
            "status": results.experiment.status,
            "success_metric": results.experiment.success_metric,
        },
        "variant_a": asdict(results.variant_a_metrics),
        "variant_b": asdict(results.variant_b_metrics),
        "sample_size_a": results.sample_size_a,
        "sample_size_b": results.sample_size_b,
        "winner": results.winner,
        "confidence": results.confidence,
        "is_significant": results.is_significant,
    }


# ---------------------------------------------------------------------------
# NEW: Agent SLOs
# ---------------------------------------------------------------------------

@router.get("/slos")
async def get_agent_slos(
    tenant_id: str = Depends(get_current_tenant),
    clickhouse: Any = Depends(get_clickhouse),
) -> dict[str, Any]:
    """Evaluate and return all agent SLO statuses."""
    slo_service = AgentSLOService(clickhouse)
    statuses = await slo_service.evaluate_all(tenant_id)

    return {
        "slos": [
            {
                "id": s.slo.id,
                "name": s.slo.name,
                "agent_type": s.slo.agent_type,
                "sli_type": s.slo.sli_type,
                "target": s.target,
                "current_value": s.current_value,
                "is_meeting": s.is_meeting,
                "error_budget_remaining_pct": s.error_budget_remaining_pct,
                "burn_rate_1h": s.burn_rate_1h,
                "burn_rate_6h": s.burn_rate_6h,
                "trend": s.trend,
            }
            for s in statuses
        ],
        "count": len(statuses),
    }


@router.post("/slos")
async def create_agent_slo(
    body: CreateSLORequest,
    tenant_id: str = Depends(get_current_tenant),
    clickhouse: Any = Depends(get_clickhouse),
) -> dict[str, Any]:
    """Create a new agent SLO definition."""
    slo_service = AgentSLOService(clickhouse)

    slo = AgentSLO(
        id="",
        name=body.name,
        agent_type=body.agent_type,
        sli_type=body.sli_type,
        target=body.target,
        window_days=body.window_days,
    )

    result = await slo_service.create_slo(tenant_id, slo)

    return {
        "id": result.id,
        "name": result.name,
        "agent_type": result.agent_type,
        "sli_type": result.sli_type,
        "target": result.target,
        "window_days": result.window_days,
    }
