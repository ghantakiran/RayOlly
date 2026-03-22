"""Agent Execution Tracing -- visualize agent thinking like a distributed trace.

Provides span-level observability for every step of an agent's execution,
enabling waterfall visualizations similar to distributed tracing (Jaeger/Zipkin)
but purpose-built for AI agent reasoning chains.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums & data models
# ---------------------------------------------------------------------------

class AgentSpanType(str, Enum):
    THINKING = "thinking"
    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    PLANNING = "planning"
    RESPONSE = "response"
    DELEGATION = "delegation"  # When one agent calls another


# Approximate per-token costs (USD) for common models
_MODEL_COSTS: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-20250514": (3.0e-6, 15.0e-6),
    "claude-haiku": (0.25e-6, 1.25e-6),
    "gpt-4o": (2.5e-6, 10.0e-6),
    "gpt-4o-mini": (0.15e-6, 0.6e-6),
}


def _estimate_cost(model: str, tokens_input: int, tokens_output: int) -> float:
    """Estimate USD cost from token counts and model name."""
    input_rate, output_rate = _MODEL_COSTS.get(model, (3.0e-6, 15.0e-6))
    return tokens_input * input_rate + tokens_output * output_rate


@dataclass
class AgentSpan:
    """A single span inside an agent execution trace."""

    span_id: str
    parent_span_id: str  # For nested tool calls ("" for root spans)
    name: str
    span_type: AgentSpanType
    start_time_ms: float  # Relative to execution start
    duration_ms: float = 0.0
    input_preview: str = ""  # First 500 chars
    output_preview: str = ""
    tokens_input: int = 0
    tokens_output: int = 0
    cost_usd: float = 0.0
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentSpanContext:
    """Handle returned by start_span, passed back to end_span."""

    span_id: str
    parent_span_id: str
    name: str
    span_type: AgentSpanType
    start_monotonic: float  # time.monotonic() at span start
    start_time_ms: float  # Relative to execution start


@dataclass
class AgentWaterfall:
    """Visualization data for the execution waterfall (like a Gantt chart)."""

    execution_id: str
    agent_type: str
    total_duration_ms: float
    total_cost_usd: float
    total_tokens: int
    spans: list[AgentSpan]
    critical_path: list[str]  # span_ids that form the longest path

    def to_dict(self) -> dict[str, Any]:
        """Serialize for API response."""
        return {
            "execution_id": self.execution_id,
            "agent_type": self.agent_type,
            "total_duration_ms": round(self.total_duration_ms, 2),
            "total_cost_usd": round(self.total_cost_usd, 6),
            "total_tokens": self.total_tokens,
            "critical_path": self.critical_path,
            "spans": [
                {
                    "span_id": s.span_id,
                    "parent_span_id": s.parent_span_id,
                    "name": s.name,
                    "span_type": s.span_type.value,
                    "start_time_ms": round(s.start_time_ms, 2),
                    "duration_ms": round(s.duration_ms, 2),
                    "input_preview": s.input_preview,
                    "output_preview": s.output_preview,
                    "tokens_input": s.tokens_input,
                    "tokens_output": s.tokens_output,
                    "cost_usd": round(s.cost_usd, 6),
                    "error": s.error,
                    "metadata": s.metadata,
                }
                for s in self.spans
            ],
        }


# ---------------------------------------------------------------------------
# Tracer
# ---------------------------------------------------------------------------

class AgentTracer:
    """Records every step of an agent's execution as a trace with spans.

    Usage::

        tracer = AgentTracer(clickhouse, tenant_id, exec_id, "rca")
        ctx = tracer.start_span("analyse_logs", AgentSpanType.TOOL_CALL)
        # ... do work ...
        tracer.end_span(ctx, output="Found 42 errors", tokens=1200)
        await tracer.flush()
    """

    def __init__(
        self,
        clickhouse_client: Any,
        tenant_id: str,
        execution_id: str,
        agent_type: str,
        model: str = "claude-sonnet-4-20250514",
    ) -> None:
        self.clickhouse = clickhouse_client
        self.tenant_id = tenant_id
        self.execution_id = execution_id
        self.agent_type = agent_type
        self.model = model
        self.spans: list[AgentSpan] = []
        self._start_monotonic = time.monotonic()
        self._active_spans: dict[str, AgentSpanContext] = {}

    # ------------------------------------------------------------------
    # Span lifecycle
    # ------------------------------------------------------------------

    def start_span(
        self,
        name: str,
        span_type: AgentSpanType,
        parent_span_id: str = "",
        input_preview: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> AgentSpanContext:
        """Start a new span (thinking, tool_call, tool_result, llm_call, etc.)."""
        now = time.monotonic()
        span_id = uuid.uuid4().hex[:16]
        relative_ms = (now - self._start_monotonic) * 1000

        ctx = AgentSpanContext(
            span_id=span_id,
            parent_span_id=parent_span_id,
            name=name,
            span_type=span_type,
            start_monotonic=now,
            start_time_ms=relative_ms,
        )
        self._active_spans[span_id] = ctx

        # Pre-create the span so we capture input_preview immediately
        span = AgentSpan(
            span_id=span_id,
            parent_span_id=parent_span_id,
            name=name,
            span_type=span_type,
            start_time_ms=relative_ms,
            input_preview=input_preview[:500] if input_preview else "",
            metadata=metadata or {},
        )
        self.spans.append(span)

        return ctx

    def end_span(
        self,
        ctx: AgentSpanContext,
        output: str = "",
        tokens_input: int = 0,
        tokens_output: int = 0,
        error: str = "",
    ) -> None:
        """End span and record duration, tokens, and cost."""
        now = time.monotonic()
        duration_ms = (now - ctx.start_monotonic) * 1000

        # Find the span we pre-created
        for span in self.spans:
            if span.span_id == ctx.span_id:
                span.duration_ms = duration_ms
                span.output_preview = output[:500] if output else ""
                span.tokens_input = tokens_input
                span.tokens_output = tokens_output
                span.cost_usd = _estimate_cost(self.model, tokens_input, tokens_output)
                span.error = error
                break

        self._active_spans.pop(ctx.span_id, None)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def flush(self) -> None:
        """Write all spans to ClickHouse agent_spans table."""
        if not self.spans:
            return

        rows = [
            {
                "execution_id": self.execution_id,
                "tenant_id": self.tenant_id,
                "span_id": s.span_id,
                "parent_span_id": s.parent_span_id,
                "name": s.name,
                "span_type": s.span_type.value,
                "start_time_ms": s.start_time_ms,
                "duration_ms": s.duration_ms,
                "input_preview": s.input_preview,
                "output_preview": s.output_preview,
                "tokens_input": s.tokens_input,
                "tokens_output": s.tokens_output,
                "cost_usd": s.cost_usd,
                "error": s.error,
                "metadata": s.metadata,
            }
            for s in self.spans
        ]

        await self.clickhouse.execute(
            """
            INSERT INTO agents.agent_spans (
                execution_id, tenant_id, span_id, parent_span_id,
                name, span_type, start_time_ms, duration_ms,
                input_preview, output_preview,
                tokens_input, tokens_output, cost_usd,
                error, metadata
            ) VALUES
            """,
            rows,
        )

        logger.info(
            "Flushed %d spans for execution %s",
            len(self.spans),
            self.execution_id,
        )

    # ------------------------------------------------------------------
    # Waterfall construction
    # ------------------------------------------------------------------

    def get_waterfall(self) -> AgentWaterfall:
        """Build waterfall visualization data from recorded spans."""
        total_duration = max(
            (s.start_time_ms + s.duration_ms for s in self.spans),
            default=0.0,
        )
        total_cost = sum(s.cost_usd for s in self.spans)
        total_tokens = sum(s.tokens_input + s.tokens_output for s in self.spans)

        critical_path = self._compute_critical_path()

        return AgentWaterfall(
            execution_id=self.execution_id,
            agent_type=self.agent_type,
            total_duration_ms=total_duration,
            total_cost_usd=total_cost,
            total_tokens=total_tokens,
            spans=list(self.spans),
            critical_path=critical_path,
        )

    def _compute_critical_path(self) -> list[str]:
        """Find the span chain that forms the longest wall-clock path.

        Uses a simple approach: for each leaf span (no children), compute the
        total duration from root to leaf, then pick the longest chain.
        """
        if not self.spans:
            return []

        # Build parent->children map
        children_map: dict[str, list[str]] = {}
        span_map: dict[str, AgentSpan] = {}
        for s in self.spans:
            span_map[s.span_id] = s
            children_map.setdefault(s.parent_span_id, []).append(s.span_id)

        # Find root spans (parent_span_id == "")
        roots = [s.span_id for s in self.spans if s.parent_span_id == ""]

        # DFS to find longest path
        best_path: list[str] = []
        best_duration = 0.0

        def dfs(span_id: str, path: list[str], cumulative: float) -> None:
            nonlocal best_path, best_duration
            span = span_map[span_id]
            new_cumulative = cumulative + span.duration_ms
            new_path = path + [span_id]

            kids = children_map.get(span_id, [])
            if not kids:
                if new_cumulative > best_duration:
                    best_duration = new_cumulative
                    best_path = new_path
            else:
                for kid in kids:
                    dfs(kid, new_path, new_cumulative)

        for root in roots:
            dfs(root, [], 0.0)

        return best_path

    # ------------------------------------------------------------------
    # Query existing traces from ClickHouse
    # ------------------------------------------------------------------

    @staticmethod
    async def load_waterfall(
        execution_id: str,
        clickhouse: Any,
    ) -> AgentWaterfall | None:
        """Load a previously persisted execution waterfall from ClickHouse."""
        exec_rows = await clickhouse.execute(
            """
            SELECT agent_type, duration_ms, cost_usd, total_tokens
            FROM agents.agent_executions
            WHERE execution_id = %(execution_id)s
            LIMIT 1
            """,
            {"execution_id": execution_id},
        )
        if not exec_rows:
            return None

        agent_type = exec_rows[0][0]

        span_rows = await clickhouse.execute(
            """
            SELECT
                span_id, parent_span_id, name, span_type,
                start_time_ms, duration_ms,
                input_preview, output_preview,
                tokens_input, tokens_output, cost_usd,
                error
            FROM agents.agent_spans
            WHERE execution_id = %(execution_id)s
            ORDER BY start_time_ms ASC
            """,
            {"execution_id": execution_id},
        )

        spans: list[AgentSpan] = []
        for r in (span_rows or []):
            spans.append(
                AgentSpan(
                    span_id=r[0],
                    parent_span_id=r[1],
                    name=r[2],
                    span_type=AgentSpanType(r[3]),
                    start_time_ms=float(r[4]),
                    duration_ms=float(r[5]),
                    input_preview=r[6],
                    output_preview=r[7],
                    tokens_input=r[8],
                    tokens_output=r[9],
                    cost_usd=float(r[10]),
                    error=r[11],
                )
            )

        total_duration = max(
            (s.start_time_ms + s.duration_ms for s in spans),
            default=0.0,
        )
        total_cost = sum(s.cost_usd for s in spans)
        total_tokens = sum(s.tokens_input + s.tokens_output for s in spans)

        # Compute critical path
        tracer = AgentTracer.__new__(AgentTracer)
        tracer.spans = spans
        tracer.execution_id = execution_id
        tracer.agent_type = agent_type
        critical_path = tracer._compute_critical_path()

        return AgentWaterfall(
            execution_id=execution_id,
            agent_type=agent_type,
            total_duration_ms=total_duration,
            total_cost_usd=total_cost,
            total_tokens=total_tokens,
            spans=spans,
            critical_path=critical_path,
        )
