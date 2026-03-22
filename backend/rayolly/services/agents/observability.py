"""Agent Observability Service — monitor and analyze AI agent performance.

This is RayOlly's unique differentiator: observability for the AI agents
themselves.  Track executions, costs, tool usage, user satisfaction, and
automatically detect issues like high failure rates or runaway token spend.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class StepType(str, Enum):
    THINKING = "thinking"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    RESPONSE = "response"


class FeedbackRating(str, Enum):
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"


class IssueSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class AgentStep:
    """A single step inside an agent execution trace."""

    step_number: int
    type: StepType
    timestamp: datetime
    duration_ms: int
    content_preview: str
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    tool_output_preview: str | None = None
    tokens_used: int = 0


@dataclass
class AgentTrace:
    """Full execution trace for a single agent invocation."""

    execution_id: str
    agent_type: str
    tenant_id: str
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int = 0
    status: str = "running"  # running | completed | failed | cancelled
    steps: list[AgentStep] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    model_used: str = ""
    error_message: str | None = None


@dataclass
class AgentMetrics:
    """Aggregated metrics for a specific agent type."""

    agent_type: str
    total_executions: int = 0
    successful: int = 0
    failed: int = 0
    cancelled: int = 0
    avg_duration_seconds: float = 0.0
    p50_duration: float = 0.0
    p95_duration: float = 0.0
    avg_tokens_used: float = 0.0
    total_cost_usd: float = 0.0
    avg_tools_per_execution: float = 0.0
    success_rate_pct: float = 0.0
    user_satisfaction_rate: float = 0.0  # % thumbs-up from feedback


@dataclass
class AgentFeedback:
    """User feedback on an agent execution."""

    execution_id: str
    tenant_id: str
    user_id: str
    rating: FeedbackRating
    comment: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class AgentCostBreakdown:
    """Cost analysis for a given period."""

    period: str  # e.g. "24h", "7d", "30d"
    by_agent_type: dict[str, float] = field(default_factory=dict)
    by_tenant: dict[str, float] = field(default_factory=dict)
    by_model: dict[str, float] = field(default_factory=dict)
    total_cost_usd: float = 0.0


@dataclass
class ToolUsageStats:
    """Statistics for a single tool."""

    tool_name: str
    invocations: int = 0
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    error_count: int = 0
    error_rate_pct: float = 0.0


@dataclass
class AgentIssue:
    """An automatically detected issue with an agent."""

    issue_type: str
    severity: IssueSeverity
    agent_type: str
    description: str
    metric_value: float
    threshold: float
    recommendation: str
    detected_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ErrorAnalysis:
    """A common failure pattern with root-cause summary."""

    error_message: str
    count: int
    agent_type: str
    first_seen: datetime
    last_seen: datetime
    root_cause: str
    affected_executions: list[str] = field(default_factory=list)


@dataclass
class SatisfactionPoint:
    """A single data-point in a satisfaction trend."""

    timestamp: datetime
    thumbs_up: int = 0
    thumbs_down: int = 0
    satisfaction_pct: float = 0.0


@dataclass
class AgentDashboard:
    """Top-level dashboard payload returned to the UI."""

    agent_metrics: list[AgentMetrics]
    top_errors: list[ErrorAnalysis]
    cost_breakdown: AgentCostBreakdown
    satisfaction_trend: list[SatisfactionPoint]
    total_executions: int = 0
    overall_success_rate: float = 0.0
    total_cost_usd: float = 0.0
    avg_duration_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class AgentObservabilityService:
    """Reads and writes agent observability data backed by ClickHouse."""

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------

    async def record_execution(self, trace: AgentTrace, clickhouse: Any) -> None:
        """Persist an agent execution trace and its steps to ClickHouse."""

        await clickhouse.execute(
            """
            INSERT INTO agents.agent_executions (
                execution_id, agent_type, tenant_id, status,
                started_at, completed_at, duration_ms,
                input_tokens, output_tokens, total_tokens,
                cost_usd, model, tool_calls_count,
                error_message, steps_count
            ) VALUES
            """,
            [
                {
                    "execution_id": trace.execution_id,
                    "agent_type": trace.agent_type,
                    "tenant_id": trace.tenant_id,
                    "status": trace.status,
                    "started_at": trace.started_at,
                    "completed_at": trace.completed_at or trace.started_at,
                    "duration_ms": trace.duration_ms,
                    "input_tokens": trace.total_input_tokens,
                    "output_tokens": trace.total_output_tokens,
                    "total_tokens": trace.total_input_tokens + trace.total_output_tokens,
                    "cost_usd": trace.total_cost_usd,
                    "model": trace.model_used,
                    "tool_calls_count": sum(
                        1 for s in trace.steps if s.type == StepType.TOOL_CALL
                    ),
                    "error_message": trace.error_message or "",
                    "steps_count": len(trace.steps),
                },
            ],
        )

        if trace.steps:
            step_rows = [
                {
                    "execution_id": trace.execution_id,
                    "step_number": step.step_number,
                    "step_type": step.type.value,
                    "timestamp": step.timestamp,
                    "duration_ms": step.duration_ms,
                    "tool_name": step.tool_name or "",
                    "tokens_used": step.tokens_used,
                    "content_preview": step.content_preview[:500],
                }
                for step in trace.steps
            ]
            await clickhouse.execute(
                """
                INSERT INTO agents.agent_steps (
                    execution_id, step_number, step_type, timestamp,
                    duration_ms, tool_name, tokens_used, content_preview
                ) VALUES
                """,
                step_rows,
            )

        logger.info(
            "Recorded agent execution %s (%s, %s, %d steps)",
            trace.execution_id,
            trace.agent_type,
            trace.status,
            len(trace.steps),
        )

    async def record_feedback(self, feedback: AgentFeedback, clickhouse: Any) -> None:
        """Store user feedback for an agent execution."""

        await clickhouse.execute(
            """
            INSERT INTO agents.agent_feedback (
                execution_id, tenant_id, user_id,
                rating, comment, timestamp
            ) VALUES
            """,
            [
                {
                    "execution_id": feedback.execution_id,
                    "tenant_id": feedback.tenant_id,
                    "user_id": feedback.user_id,
                    "rating": feedback.rating.value,
                    "comment": feedback.comment,
                    "timestamp": feedback.timestamp,
                },
            ],
        )

        logger.info(
            "Recorded feedback for execution %s: %s",
            feedback.execution_id,
            feedback.rating.value,
        )

    # ------------------------------------------------------------------
    # Read path
    # ------------------------------------------------------------------

    async def get_agent_metrics(
        self,
        tenant_id: str,
        agent_type: str,
        time_range: str,
        clickhouse: Any,
    ) -> AgentMetrics:
        """Return aggregated metrics for a single agent type."""

        interval = _time_range_to_interval(time_range)

        rows = await clickhouse.execute(
            f"""
            SELECT
                count()                                          AS total_executions,
                countIf(status = 'completed')                    AS successful,
                countIf(status = 'failed')                       AS failed,
                countIf(status = 'cancelled')                    AS cancelled,
                avg(duration_ms) / 1000                          AS avg_duration_seconds,
                quantile(0.50)(duration_ms) / 1000               AS p50_duration,
                quantile(0.95)(duration_ms) / 1000               AS p95_duration,
                avg(total_tokens)                                AS avg_tokens_used,
                sum(cost_usd)                                    AS total_cost_usd,
                avg(tool_calls_count)                            AS avg_tools_per_execution
            FROM agents.agent_executions
            WHERE tenant_id = %(tenant_id)s
              AND agent_type = %(agent_type)s
              AND started_at >= now() - INTERVAL {interval}
            """,
            {"tenant_id": tenant_id, "agent_type": agent_type},
        )

        row = rows[0] if rows else [0] * 10

        total = row[0] or 0
        successful = row[1] or 0
        success_rate = (successful / total * 100) if total > 0 else 0.0

        # Satisfaction from feedback table
        sat_rows = await clickhouse.execute(
            f"""
            SELECT
                countIf(rating = 'thumbs_up')  AS up,
                count()                        AS total
            FROM agents.agent_feedback
            WHERE tenant_id = %(tenant_id)s
              AND execution_id IN (
                  SELECT execution_id
                  FROM agents.agent_executions
                  WHERE agent_type = %(agent_type)s
                    AND started_at >= now() - INTERVAL {interval}
              )
            """,
            {"tenant_id": tenant_id, "agent_type": agent_type},
        )

        sat_row = sat_rows[0] if sat_rows else [0, 0]
        sat_total = sat_row[1] or 0
        satisfaction = (sat_row[0] / sat_total * 100) if sat_total > 0 else 0.0

        return AgentMetrics(
            agent_type=agent_type,
            total_executions=total,
            successful=successful,
            failed=row[2] or 0,
            cancelled=row[3] or 0,
            avg_duration_seconds=row[4] or 0.0,
            p50_duration=row[5] or 0.0,
            p95_duration=row[6] or 0.0,
            avg_tokens_used=row[7] or 0.0,
            total_cost_usd=row[8] or 0.0,
            avg_tools_per_execution=row[9] or 0.0,
            success_rate_pct=success_rate,
            user_satisfaction_rate=satisfaction,
        )

    async def get_agent_dashboard(
        self,
        tenant_id: str,
        time_range: str,
        clickhouse: Any,
    ) -> AgentDashboard:
        """Build the full dashboard payload for all agent types."""

        interval = _time_range_to_interval(time_range)

        # Fetch per-agent-type metrics
        type_rows = await clickhouse.execute(
            f"""
            SELECT DISTINCT agent_type
            FROM agents.agent_executions
            WHERE tenant_id = %(tenant_id)s
              AND started_at >= now() - INTERVAL {interval}
            """,
            {"tenant_id": tenant_id},
        )

        agent_types = [r[0] for r in (type_rows or [])]
        agent_metrics: list[AgentMetrics] = []
        for at in agent_types:
            m = await self.get_agent_metrics(tenant_id, at, time_range, clickhouse)
            agent_metrics.append(m)

        # Top errors
        top_errors = await self.get_error_analysis(tenant_id, time_range, clickhouse)

        # Cost breakdown
        cost_breakdown = await self.get_cost_breakdown(tenant_id, time_range, clickhouse)

        # Satisfaction trend
        satisfaction_trend = await self.get_satisfaction_trend(
            tenant_id, time_range, clickhouse
        )

        total_execs = sum(m.total_executions for m in agent_metrics)
        total_success = sum(m.successful for m in agent_metrics)
        total_cost = sum(m.total_cost_usd for m in agent_metrics)
        avg_dur = (
            sum(m.avg_duration_seconds * m.total_executions for m in agent_metrics)
            / total_execs
            if total_execs > 0
            else 0.0
        )

        return AgentDashboard(
            agent_metrics=agent_metrics,
            top_errors=top_errors[:10],
            cost_breakdown=cost_breakdown,
            satisfaction_trend=satisfaction_trend,
            total_executions=total_execs,
            overall_success_rate=(total_success / total_execs * 100) if total_execs else 0.0,
            total_cost_usd=total_cost,
            avg_duration_seconds=avg_dur,
        )

    async def get_execution_trace(
        self,
        execution_id: str,
        clickhouse: Any,
    ) -> AgentTrace | None:
        """Return the full execution trace with all steps."""

        exec_rows = await clickhouse.execute(
            """
            SELECT
                execution_id, agent_type, tenant_id, status,
                started_at, completed_at, duration_ms,
                input_tokens, output_tokens, cost_usd,
                model, error_message
            FROM agents.agent_executions
            WHERE execution_id = %(execution_id)s
            LIMIT 1
            """,
            {"execution_id": execution_id},
        )

        if not exec_rows:
            return None

        row = exec_rows[0]

        step_rows = await clickhouse.execute(
            """
            SELECT
                step_number, step_type, timestamp, duration_ms,
                tool_name, tokens_used, content_preview
            FROM agents.agent_steps
            WHERE execution_id = %(execution_id)s
            ORDER BY step_number ASC
            """,
            {"execution_id": execution_id},
        )

        steps = [
            AgentStep(
                step_number=s[0],
                type=StepType(s[1]),
                timestamp=s[2],
                duration_ms=s[3],
                content_preview=s[6],
                tool_name=s[4] or None,
                tokens_used=s[5],
            )
            for s in (step_rows or [])
        ]

        return AgentTrace(
            execution_id=row[0],
            agent_type=row[1],
            tenant_id=row[2],
            status=row[3],
            started_at=row[4],
            completed_at=row[5],
            duration_ms=row[6],
            total_input_tokens=row[7],
            total_output_tokens=row[8],
            total_cost_usd=row[9],
            model_used=row[10],
            error_message=row[11] or None,
            steps=steps,
        )

    async def get_cost_breakdown(
        self,
        tenant_id: str,
        time_range: str,
        clickhouse: Any,
    ) -> AgentCostBreakdown:
        """Break down costs by agent type, tenant, and model."""

        interval = _time_range_to_interval(time_range)

        # By agent type
        by_type_rows = await clickhouse.execute(
            f"""
            SELECT agent_type, sum(cost_usd) AS cost
            FROM agents.agent_executions
            WHERE tenant_id = %(tenant_id)s
              AND started_at >= now() - INTERVAL {interval}
            GROUP BY agent_type
            ORDER BY cost DESC
            """,
            {"tenant_id": tenant_id},
        )

        # By model
        by_model_rows = await clickhouse.execute(
            f"""
            SELECT model, sum(cost_usd) AS cost
            FROM agents.agent_executions
            WHERE tenant_id = %(tenant_id)s
              AND started_at >= now() - INTERVAL {interval}
            GROUP BY model
            ORDER BY cost DESC
            """,
            {"tenant_id": tenant_id},
        )

        by_agent_type = {r[0]: float(r[1]) for r in (by_type_rows or [])}
        by_model = {r[0]: float(r[1]) for r in (by_model_rows or [])}
        total = sum(by_agent_type.values())

        return AgentCostBreakdown(
            period=time_range,
            by_agent_type=by_agent_type,
            by_tenant={tenant_id: total},
            by_model=by_model,
            total_cost_usd=total,
        )

    async def get_error_analysis(
        self,
        tenant_id: str,
        time_range: str,
        clickhouse: Any,
    ) -> list[ErrorAnalysis]:
        """Identify common failure patterns and group by root cause."""

        interval = _time_range_to_interval(time_range)

        rows = await clickhouse.execute(
            f"""
            SELECT
                error_message,
                count()                 AS cnt,
                agent_type,
                min(started_at)         AS first_seen,
                max(started_at)         AS last_seen,
                groupArray(10)(execution_id) AS sample_ids
            FROM agents.agent_executions
            WHERE tenant_id = %(tenant_id)s
              AND status = 'failed'
              AND error_message != ''
              AND started_at >= now() - INTERVAL {interval}
            GROUP BY error_message, agent_type
            ORDER BY cnt DESC
            LIMIT 20
            """,
            {"tenant_id": tenant_id},
        )

        results: list[ErrorAnalysis] = []
        for r in (rows or []):
            root_cause = _infer_root_cause(r[0])
            results.append(
                ErrorAnalysis(
                    error_message=r[0],
                    count=r[1],
                    agent_type=r[2],
                    first_seen=r[3],
                    last_seen=r[4],
                    root_cause=root_cause,
                    affected_executions=r[5] if len(r) > 5 else [],
                )
            )

        return results

    async def get_tool_usage(
        self,
        tenant_id: str,
        time_range: str,
        clickhouse: Any,
    ) -> list[ToolUsageStats]:
        """Return per-tool usage statistics (invocation count, latency, errors)."""

        interval = _time_range_to_interval(time_range)

        rows = await clickhouse.execute(
            f"""
            SELECT
                s.tool_name,
                count()                             AS invocations,
                avg(s.duration_ms)                  AS avg_latency_ms,
                quantile(0.95)(s.duration_ms)       AS p95_latency_ms,
                countIf(s.step_type = 'tool_result'
                        AND s.content_preview LIKE '%error%') AS error_count
            FROM agents.agent_steps AS s
            INNER JOIN agents.agent_executions AS e
                ON s.execution_id = e.execution_id
            WHERE e.tenant_id = %(tenant_id)s
              AND s.step_type = 'tool_call'
              AND s.tool_name != ''
              AND e.started_at >= now() - INTERVAL {interval}
            GROUP BY s.tool_name
            ORDER BY invocations DESC
            """,
            {"tenant_id": tenant_id},
        )

        results: list[ToolUsageStats] = []
        for r in (rows or []):
            invocations = r[1] or 1
            error_count = r[4] or 0
            results.append(
                ToolUsageStats(
                    tool_name=r[0],
                    invocations=invocations,
                    avg_latency_ms=r[2] or 0.0,
                    p95_latency_ms=r[3] or 0.0,
                    error_count=error_count,
                    error_rate_pct=(error_count / invocations * 100),
                )
            )

        return results

    async def detect_agent_issues(
        self,
        tenant_id: str,
        clickhouse: Any,
    ) -> list[AgentIssue]:
        """Proactively detect anomalies in agent behaviour."""

        issues: list[AgentIssue] = []

        # --- High failure rate (>20% in last 1h) ---
        rows = await clickhouse.execute(
            """
            SELECT
                agent_type,
                count()                          AS total,
                countIf(status = 'failed')       AS failed
            FROM agents.agent_executions
            WHERE tenant_id = %(tenant_id)s
              AND started_at >= now() - INTERVAL 1 HOUR
            GROUP BY agent_type
            HAVING total >= 5
            """,
            {"tenant_id": tenant_id},
        )

        for r in (rows or []):
            total, failed = r[1], r[2]
            rate = (failed / total * 100) if total else 0
            if rate > 20:
                issues.append(
                    AgentIssue(
                        issue_type="high_failure_rate",
                        severity=IssueSeverity.HIGH if rate > 50 else IssueSeverity.MEDIUM,
                        agent_type=r[0],
                        description=f"Agent {r[0]} has a {rate:.1f}% failure rate in the last hour ({failed}/{total} executions)",
                        metric_value=rate,
                        threshold=20.0,
                        recommendation="Check recent error messages and verify external dependencies are healthy.",
                    )
                )

        # --- Excessive token usage (>2x baseline) ---
        rows = await clickhouse.execute(
            """
            SELECT
                agent_type,
                avg(total_tokens)     AS recent_avg,
                (
                    SELECT avg(total_tokens)
                    FROM agents.agent_executions
                    WHERE tenant_id = %(tenant_id)s
                      AND started_at >= now() - INTERVAL 7 DAY
                      AND started_at < now() - INTERVAL 1 HOUR
                ) AS baseline_avg
            FROM agents.agent_executions
            WHERE tenant_id = %(tenant_id)s
              AND started_at >= now() - INTERVAL 1 HOUR
            GROUP BY agent_type
            HAVING recent_avg > baseline_avg * 2
               AND baseline_avg > 0
            """,
            {"tenant_id": tenant_id},
        )

        for r in (rows or []):
            issues.append(
                AgentIssue(
                    issue_type="excessive_token_usage",
                    severity=IssueSeverity.MEDIUM,
                    agent_type=r[0],
                    description=(
                        f"Agent {r[0]} is using {r[1]:.0f} tokens/execution "
                        f"vs {r[2]:.0f} baseline (>{2}x)"
                    ),
                    metric_value=float(r[1]),
                    threshold=float(r[2]) * 2,
                    recommendation="Review recent prompts and tool outputs for unnecessary verbosity.",
                )
            )

        # --- Slow agents (p95 > 60s in last 1h) ---
        rows = await clickhouse.execute(
            """
            SELECT
                agent_type,
                quantile(0.95)(duration_ms) / 1000 AS p95_seconds
            FROM agents.agent_executions
            WHERE tenant_id = %(tenant_id)s
              AND started_at >= now() - INTERVAL 1 HOUR
            GROUP BY agent_type
            HAVING p95_seconds > 60
            """,
            {"tenant_id": tenant_id},
        )

        for r in (rows or []):
            issues.append(
                AgentIssue(
                    issue_type="slow_agent",
                    severity=IssueSeverity.MEDIUM,
                    agent_type=r[0],
                    description=f"Agent {r[0]} p95 latency is {r[1]:.1f}s (threshold: 60s)",
                    metric_value=float(r[1]),
                    threshold=60.0,
                    recommendation="Consider reducing max iterations or optimising tool calls.",
                )
            )

        # --- Timeout spikes ---
        rows = await clickhouse.execute(
            """
            SELECT
                agent_type,
                countIf(error_message LIKE '%timed out%') AS timeouts,
                count()                                    AS total
            FROM agents.agent_executions
            WHERE tenant_id = %(tenant_id)s
              AND started_at >= now() - INTERVAL 1 HOUR
            GROUP BY agent_type
            HAVING timeouts >= 3
            """,
            {"tenant_id": tenant_id},
        )

        for r in (rows or []):
            issues.append(
                AgentIssue(
                    issue_type="timeout_spike",
                    severity=IssueSeverity.HIGH,
                    agent_type=r[0],
                    description=f"Agent {r[0]} had {r[1]} timeouts out of {r[2]} executions in the last hour",
                    metric_value=float(r[1]),
                    threshold=3.0,
                    recommendation="Increase timeout or investigate slow tool calls.",
                )
            )

        return issues

    async def get_satisfaction_trend(
        self,
        tenant_id: str,
        time_range: str,
        clickhouse: Any,
    ) -> list[SatisfactionPoint]:
        """Return a time-series of user satisfaction ratings."""

        interval = _time_range_to_interval(time_range)

        # Choose bucket size based on range
        if time_range in ("1h", "3h", "6h"):
            bucket = "toStartOfFifteenMinutes(timestamp)"
        elif time_range in ("24h", "48h"):
            bucket = "toStartOfHour(timestamp)"
        else:
            bucket = "toStartOfDay(timestamp)"

        rows = await clickhouse.execute(
            f"""
            SELECT
                {bucket}                                 AS ts,
                countIf(rating = 'thumbs_up')            AS thumbs_up,
                countIf(rating = 'thumbs_down')          AS thumbs_down,
                count()                                  AS total
            FROM agents.agent_feedback
            WHERE tenant_id = %(tenant_id)s
              AND timestamp >= now() - INTERVAL {interval}
            GROUP BY ts
            ORDER BY ts ASC
            """,
            {"tenant_id": tenant_id},
        )

        results: list[SatisfactionPoint] = []
        for r in (rows or []):
            total = r[3] or 1
            results.append(
                SatisfactionPoint(
                    timestamp=r[0],
                    thumbs_up=r[1],
                    thumbs_down=r[2],
                    satisfaction_pct=(r[1] / total * 100),
                )
            )

        return results

    async def list_executions(
        self,
        tenant_id: str,
        time_range: str,
        clickhouse: Any,
        agent_type: str | None = None,
        status_filter: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Return a paginated list of recent executions."""

        interval = _time_range_to_interval(time_range)

        conditions = [
            "tenant_id = %(tenant_id)s",
            f"started_at >= now() - INTERVAL {interval}",
        ]
        params: dict[str, Any] = {"tenant_id": tenant_id}

        if agent_type:
            conditions.append("agent_type = %(agent_type)s")
            params["agent_type"] = agent_type

        if status_filter:
            conditions.append("status = %(status_filter)s")
            params["status_filter"] = status_filter

        where = " AND ".join(conditions)

        rows = await clickhouse.execute(
            f"""
            SELECT
                execution_id, agent_type, status,
                started_at, completed_at, duration_ms,
                total_tokens, cost_usd, model,
                error_message, tool_calls_count, steps_count
            FROM agents.agent_executions
            WHERE {where}
            ORDER BY started_at DESC
            LIMIT %(limit)s OFFSET %(offset)s
            """,
            {**params, "limit": limit, "offset": offset},
        )

        return [
            {
                "execution_id": r[0],
                "agent_type": r[1],
                "status": r[2],
                "started_at": r[3].isoformat() if hasattr(r[3], "isoformat") else str(r[3]),
                "completed_at": r[4].isoformat() if r[4] and hasattr(r[4], "isoformat") else str(r[4]) if r[4] else None,
                "duration_ms": r[5],
                "total_tokens": r[6],
                "cost_usd": float(r[7]),
                "model": r[8],
                "error_message": r[9] or None,
                "tool_calls_count": r[10],
                "steps_count": r[11],
            }
            for r in (rows or [])
        ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TIME_RANGE_MAP: dict[str, str] = {
    "1h": "1 HOUR",
    "3h": "3 HOUR",
    "6h": "6 HOUR",
    "12h": "12 HOUR",
    "24h": "24 HOUR",
    "48h": "48 HOUR",
    "7d": "7 DAY",
    "14d": "14 DAY",
    "30d": "30 DAY",
    "90d": "90 DAY",
}


def _time_range_to_interval(time_range: str) -> str:
    """Convert a UI-friendly time range string to a ClickHouse interval."""
    return _TIME_RANGE_MAP.get(time_range, "24 HOUR")


def _infer_root_cause(error_message: str) -> str:
    """Simple heuristic root-cause inference from error text."""

    msg_lower = error_message.lower()

    if "timed out" in msg_lower or "timeout" in msg_lower:
        return "Execution exceeded the configured timeout. Likely caused by slow tool calls or excessive iterations."
    if "rate limit" in msg_lower or "429" in msg_lower:
        return "LLM API rate limit hit. Consider adding backoff/retry or upgrading API tier."
    if "connection" in msg_lower or "connect" in msg_lower:
        return "Network connectivity issue reaching an external dependency."
    if "authentication" in msg_lower or "401" in msg_lower or "403" in msg_lower:
        return "Authentication or authorisation failure when calling a tool or API."
    if "token" in msg_lower and ("limit" in msg_lower or "exceed" in msg_lower):
        return "Model context window exceeded. Reduce input size or conversation length."
    if "tool" in msg_lower and ("not found" in msg_lower or "unknown" in msg_lower):
        return "Agent tried to call a tool that is not registered."
    if "cancelled" in msg_lower:
        return "Execution was manually cancelled by a user."

    return "Unclassified error. Review execution trace for details."
