"""Agent SLOs -- define and track Service Level Objectives for AI agents.

Enables teams to set SLOs on agent success rate, latency, cost, and accuracy,
then monitors compliance with error budget tracking and multi-window burn rate
alerting (the same approach Google SRE uses for service SLOs).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class AgentSLO:
    """Definition of an SLO for a specific agent type."""

    id: str
    name: str
    agent_type: str
    sli_type: str  # "success_rate", "latency_p95", "cost_per_execution", "accuracy"
    target: float  # e.g. 0.9 for 90% success rate, 30000 for 30s p95
    window_days: int = 30  # Rolling window
    burn_rate_thresholds: list[dict[str, Any]] = field(default_factory=list)
    # [{rate: 14.4, window: "1h", severity: "critical"}, ...]
    tenant_id: str = ""


@dataclass
class AgentSLOStatus:
    """Current evaluation status of an SLO."""

    slo: AgentSLO
    current_value: float = 0.0
    target: float = 0.0
    is_meeting: bool = True
    error_budget_remaining_pct: float = 100.0
    burn_rate_1h: float = 0.0
    burn_rate_6h: float = 0.0
    trend: str = "stable"  # "improving", "stable", "degrading"


@dataclass
class ErrorBudget:
    """Error budget consumption details."""

    total_budget: float = 0.0  # Allowed failures in window
    consumed: float = 0.0
    remaining: float = 0.0
    remaining_pct: float = 100.0
    projected_exhaustion: str | None = None  # ISO datetime or None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class AgentSLOService:
    """Define and track SLOs for AI agents."""

    def __init__(self, clickhouse_client: Any) -> None:
        self.clickhouse = clickhouse_client

    # ------------------------------------------------------------------
    # SLO management
    # ------------------------------------------------------------------

    async def create_slo(
        self,
        tenant_id: str,
        slo: AgentSLO,
    ) -> AgentSLO:
        """Persist a new agent SLO definition."""
        if not slo.id:
            slo.id = uuid.uuid4().hex[:12]
        slo.tenant_id = tenant_id

        # Default burn rate thresholds if not provided
        if not slo.burn_rate_thresholds:
            slo.burn_rate_thresholds = [
                {"rate": 14.4, "window": "1h", "severity": "critical"},
                {"rate": 6.0, "window": "6h", "severity": "high"},
                {"rate": 3.0, "window": "1d", "severity": "medium"},
                {"rate": 1.0, "window": "3d", "severity": "low"},
            ]

        await self.clickhouse.execute(
            """
            INSERT INTO agents.agent_slos (
                slo_id, tenant_id, name, agent_type,
                sli_type, target, window_days
            ) VALUES
            """,
            [
                {
                    "slo_id": slo.id,
                    "tenant_id": tenant_id,
                    "name": slo.name,
                    "agent_type": slo.agent_type,
                    "sli_type": slo.sli_type,
                    "target": slo.target,
                    "window_days": slo.window_days,
                },
            ],
        )

        logger.info("Created agent SLO %s: %s (%s)", slo.id, slo.name, slo.sli_type)
        return slo

    async def list_slos(self, tenant_id: str) -> list[AgentSLO]:
        """List all SLOs for a tenant."""
        rows = await self.clickhouse.execute(
            """
            SELECT slo_id, name, agent_type, sli_type, target, window_days
            FROM agents.agent_slos
            WHERE tenant_id = %(tenant_id)s
            ORDER BY agent_type, name
            """,
            {"tenant_id": tenant_id},
        )

        return [
            AgentSLO(
                id=r[0],
                name=r[1],
                agent_type=r[2],
                sli_type=r[3],
                target=float(r[4]),
                window_days=int(r[5]),
                tenant_id=tenant_id,
            )
            for r in (rows or [])
        ]

    # ------------------------------------------------------------------
    # SLO evaluation
    # ------------------------------------------------------------------

    async def evaluate_slo(
        self,
        tenant_id: str,
        slo: AgentSLO,
    ) -> AgentSLOStatus:
        """Evaluate current SLO status against the rolling window."""
        current_value = await self._measure_sli(tenant_id, slo)

        # Calculate error budget
        error_budget = await self.get_error_budget(tenant_id, slo)

        # Burn rates
        burn_1h = await self._calculate_burn_rate(tenant_id, slo, "1 HOUR")
        burn_6h = await self._calculate_burn_rate(tenant_id, slo, "6 HOUR")

        # Trend: compare current window vs previous window
        trend = await self._calculate_trend(tenant_id, slo)

        # For success_rate and accuracy, higher is better (current >= target is meeting)
        # For latency and cost, lower is better (current <= target is meeting)
        if slo.sli_type in ("success_rate", "accuracy"):
            is_meeting = current_value >= slo.target
        else:
            is_meeting = current_value <= slo.target

        return AgentSLOStatus(
            slo=slo,
            current_value=round(current_value, 4),
            target=slo.target,
            is_meeting=is_meeting,
            error_budget_remaining_pct=round(error_budget.remaining_pct, 2),
            burn_rate_1h=round(burn_1h, 2),
            burn_rate_6h=round(burn_6h, 2),
            trend=trend,
        )

    async def evaluate_all(
        self,
        tenant_id: str,
    ) -> list[AgentSLOStatus]:
        """Evaluate all agent SLOs for a tenant."""
        slos = await self.list_slos(tenant_id)
        results: list[AgentSLOStatus] = []

        for slo in slos:
            status = await self.evaluate_slo(tenant_id, slo)
            results.append(status)

        return results

    # ------------------------------------------------------------------
    # SLI measurement
    # ------------------------------------------------------------------

    async def _measure_sli(
        self,
        tenant_id: str,
        slo: AgentSLO,
    ) -> float:
        """Measure the current SLI value for a given SLO definition."""
        window = f"{slo.window_days} DAY"

        if slo.sli_type == "success_rate":
            rows = await self.clickhouse.execute(
                f"""
                SELECT
                    countIf(status = 'completed') / count() AS success_rate
                FROM agents.agent_executions
                WHERE tenant_id = %(tenant_id)s
                  AND agent_type = %(agent_type)s
                  AND started_at >= now() - INTERVAL {window}
                HAVING count() > 0
                """,
                {"tenant_id": tenant_id, "agent_type": slo.agent_type},
            )
            return float(rows[0][0]) if rows and rows[0][0] else 0.0

        elif slo.sli_type == "latency_p95":
            rows = await self.clickhouse.execute(
                f"""
                SELECT quantile(0.95)(duration_ms) AS p95
                FROM agents.agent_executions
                WHERE tenant_id = %(tenant_id)s
                  AND agent_type = %(agent_type)s
                  AND started_at >= now() - INTERVAL {window}
                """,
                {"tenant_id": tenant_id, "agent_type": slo.agent_type},
            )
            return float(rows[0][0]) if rows and rows[0][0] else 0.0

        elif slo.sli_type == "cost_per_execution":
            rows = await self.clickhouse.execute(
                f"""
                SELECT avg(cost_usd) AS avg_cost
                FROM agents.agent_executions
                WHERE tenant_id = %(tenant_id)s
                  AND agent_type = %(agent_type)s
                  AND started_at >= now() - INTERVAL {window}
                """,
                {"tenant_id": tenant_id, "agent_type": slo.agent_type},
            )
            return float(rows[0][0]) if rows and rows[0][0] else 0.0

        elif slo.sli_type == "accuracy":
            rows = await self.clickhouse.execute(
                f"""
                SELECT avg(accuracy_pct) / 100 AS avg_accuracy
                FROM agents.agent_accuracy_reports AS a
                INNER JOIN agents.agent_executions AS e
                    ON a.execution_id = e.execution_id
                WHERE a.tenant_id = %(tenant_id)s
                  AND e.agent_type = %(agent_type)s
                  AND e.started_at >= now() - INTERVAL {window}
                """,
                {"tenant_id": tenant_id, "agent_type": slo.agent_type},
            )
            return float(rows[0][0]) if rows and rows[0][0] else 0.0

        return 0.0

    # ------------------------------------------------------------------
    # Error budget
    # ------------------------------------------------------------------

    async def get_error_budget(
        self,
        tenant_id: str,
        slo: AgentSLO | str,
    ) -> ErrorBudget:
        """Get remaining error budget for an SLO."""
        if isinstance(slo, str):
            # Load SLO by id
            slos = await self.list_slos(tenant_id)
            matched = [s for s in slos if s.id == slo]
            if not matched:
                return ErrorBudget()
            slo = matched[0]

        window = f"{slo.window_days} DAY"

        rows = await self.clickhouse.execute(
            f"""
            SELECT
                count() AS total,
                countIf(status = 'failed') AS failures
            FROM agents.agent_executions
            WHERE tenant_id = %(tenant_id)s
              AND agent_type = %(agent_type)s
              AND started_at >= now() - INTERVAL {window}
            """,
            {"tenant_id": tenant_id, "agent_type": slo.agent_type},
        )

        total = int(rows[0][0]) if rows and rows[0][0] else 0
        failures = int(rows[0][1]) if rows and rows[0][1] else 0

        if total == 0:
            return ErrorBudget(
                total_budget=0,
                consumed=0,
                remaining=0,
                remaining_pct=100.0,
            )

        # For success_rate SLO: allowed_failures = total * (1 - target)
        if slo.sli_type == "success_rate":
            allowed_failures = total * (1 - slo.target)
            consumed = failures
        else:
            # For other types, use a simplified budget model
            allowed_failures = total * 0.1  # 10% budget
            consumed = failures

        remaining = max(0, allowed_failures - consumed)
        remaining_pct = (remaining / allowed_failures * 100) if allowed_failures > 0 else 100.0

        # Project exhaustion
        projected_exhaustion = None
        if consumed > 0 and remaining > 0:
            # Calculate days until budget runs out at current rate
            daily_consumption = consumed / slo.window_days
            if daily_consumption > 0:
                days_remaining = remaining / daily_consumption
                from datetime import datetime, timedelta
                exhaust_date = datetime.now(UTC) + timedelta(days=days_remaining)
                projected_exhaustion = exhaust_date.isoformat()

        return ErrorBudget(
            total_budget=round(allowed_failures, 2),
            consumed=round(consumed, 2),
            remaining=round(remaining, 2),
            remaining_pct=round(remaining_pct, 2),
            projected_exhaustion=projected_exhaustion,
        )

    # ------------------------------------------------------------------
    # Burn rate calculation
    # ------------------------------------------------------------------

    async def _calculate_burn_rate(
        self,
        tenant_id: str,
        slo: AgentSLO,
        interval: str,
    ) -> float:
        """Calculate burn rate for a specific time window.

        Burn rate = (error rate in window) / (allowed error rate).
        A burn rate of 1.0 means consuming the budget at exactly the expected rate.
        A burn rate of 14.4 means the budget will be exhausted in 1/14.4 of the window.
        """
        rows = await self.clickhouse.execute(
            f"""
            SELECT
                count() AS total,
                countIf(status = 'failed') AS failures
            FROM agents.agent_executions
            WHERE tenant_id = %(tenant_id)s
              AND agent_type = %(agent_type)s
              AND started_at >= now() - INTERVAL {interval}
            """,
            {"tenant_id": tenant_id, "agent_type": slo.agent_type},
        )

        total = int(rows[0][0]) if rows and rows[0][0] else 0
        failures = int(rows[0][1]) if rows and rows[0][1] else 0

        if total == 0:
            return 0.0

        error_rate = failures / total
        allowed_error_rate = 1 - slo.target if slo.sli_type == "success_rate" else 0.1

        if allowed_error_rate <= 0:
            return float("inf") if error_rate > 0 else 0.0

        return error_rate / allowed_error_rate

    # ------------------------------------------------------------------
    # Trend analysis
    # ------------------------------------------------------------------

    async def _calculate_trend(
        self,
        tenant_id: str,
        slo: AgentSLO,
    ) -> str:
        """Compare current window performance vs previous window."""
        half_window = max(1, slo.window_days // 2)

        current = await self._measure_sli_for_interval(
            tenant_id, slo, f"{half_window} DAY",
        )
        previous = await self._measure_sli_for_interval_offset(
            tenant_id, slo, half_window, half_window,
        )

        if previous == 0:
            return "stable"

        change_pct = ((current - previous) / abs(previous)) * 100

        # For success_rate/accuracy: positive change = improving
        # For latency/cost: negative change = improving
        if slo.sli_type in ("success_rate", "accuracy"):
            if change_pct > 5:
                return "improving"
            elif change_pct < -5:
                return "degrading"
        else:
            if change_pct < -5:
                return "improving"
            elif change_pct > 5:
                return "degrading"

        return "stable"

    async def _measure_sli_for_interval(
        self,
        tenant_id: str,
        slo: AgentSLO,
        interval: str,
    ) -> float:
        """Measure SLI for a specific interval (helper for trend)."""
        if slo.sli_type == "success_rate":
            rows = await self.clickhouse.execute(
                f"""
                SELECT countIf(status = 'completed') / count() AS rate
                FROM agents.agent_executions
                WHERE tenant_id = %(tenant_id)s
                  AND agent_type = %(agent_type)s
                  AND started_at >= now() - INTERVAL {interval}
                HAVING count() > 0
                """,
                {"tenant_id": tenant_id, "agent_type": slo.agent_type},
            )
            return float(rows[0][0]) if rows and rows[0][0] else 0.0
        return 0.0

    async def _measure_sli_for_interval_offset(
        self,
        tenant_id: str,
        slo: AgentSLO,
        offset_days: int,
        window_days: int,
    ) -> float:
        """Measure SLI for a historical window (offset from now)."""
        if slo.sli_type == "success_rate":
            rows = await self.clickhouse.execute(
                f"""
                SELECT countIf(status = 'completed') / count() AS rate
                FROM agents.agent_executions
                WHERE tenant_id = %(tenant_id)s
                  AND agent_type = %(agent_type)s
                  AND started_at >= now() - INTERVAL {offset_days + window_days} DAY
                  AND started_at < now() - INTERVAL {offset_days} DAY
                HAVING count() > 0
                """,
                {"tenant_id": tenant_id, "agent_type": slo.agent_type},
            )
            return float(rows[0][0]) if rows and rows[0][0] else 0.0
        return 0.0
