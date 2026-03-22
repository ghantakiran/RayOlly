"""Agent Cost Forecasting -- predict, track, and optimize AI agent spend.

Provides real-time cost tracking, daily/monthly forecasting based on usage
trends, budget management with alerts, and actionable optimization suggestions.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class AgentCostSummary:
    """Cost breakdown for a given period."""

    period: str
    total_cost_usd: float = 0.0
    by_agent_type: dict[str, float] = field(default_factory=dict)
    by_model: dict[str, float] = field(default_factory=dict)
    total_tokens: int = 0
    total_executions: int = 0
    avg_cost_per_execution: float = 0.0


@dataclass
class CostForecast:
    """Monthly cost projection based on current usage patterns."""

    current_daily_avg: float = 0.0
    projected_monthly: float = 0.0
    trend: str = "stable"  # "increasing", "stable", "decreasing"
    trend_pct: float = 0.0  # % change from last period
    confidence: float = 0.0  # 0.0 to 1.0


@dataclass
class BudgetStatus:
    """Current budget tracking status."""

    daily_budget: float = 0.0
    spent_today: float = 0.0
    remaining: float = 0.0
    on_track: bool = True
    projected_overage: float = 0.0  # 0 if on track


@dataclass
class CostSuggestion:
    """An actionable cost optimization suggestion."""

    suggestion: str
    potential_savings_pct: float
    effort: str  # "low", "medium", "high"
    details: str


@dataclass
class CostPerInvestigation:
    """Average cost metrics per agent investigation."""

    agent_type: str
    avg_cost: float = 0.0
    median_cost: float = 0.0
    p95_cost: float = 0.0
    min_cost: float = 0.0
    max_cost: float = 0.0
    total_investigations: int = 0
    cost_trend_7d: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class AgentCostForecaster:
    """Forecast and manage AI agent costs."""

    def __init__(self, clickhouse_client: Any) -> None:
        self.clickhouse = clickhouse_client

    # ------------------------------------------------------------------
    # Current costs
    # ------------------------------------------------------------------

    async def get_current_costs(
        self,
        tenant_id: str,
        period: str = "today",
    ) -> AgentCostSummary:
        """Get current period costs broken down by agent, model, tool."""
        interval_map = {
            "today": "toStartOfDay(now())",
            "yesterday": "toStartOfDay(now()) - INTERVAL 1 DAY",
            "7d": "now() - INTERVAL 7 DAY",
            "30d": "now() - INTERVAL 30 DAY",
        }
        since = interval_map.get(period, "toStartOfDay(now())")

        # Total + by agent type
        rows = await self.clickhouse.execute(
            f"""
            SELECT
                agent_type,
                count() AS executions,
                sum(cost_usd) AS total_cost,
                sum(total_tokens) AS total_tokens
            FROM agents.agent_executions
            WHERE tenant_id = %(tenant_id)s
              AND started_at >= {since}
            GROUP BY agent_type
            ORDER BY total_cost DESC
            """,
            {"tenant_id": tenant_id},
        )

        by_agent: dict[str, float] = {}
        total_cost = 0.0
        total_tokens = 0
        total_execs = 0

        for r in (rows or []):
            by_agent[r[0]] = float(r[2])
            total_cost += float(r[2])
            total_tokens += int(r[3])
            total_execs += int(r[1])

        # By model
        model_rows = await self.clickhouse.execute(
            f"""
            SELECT model, sum(cost_usd) AS cost
            FROM agents.agent_executions
            WHERE tenant_id = %(tenant_id)s
              AND started_at >= {since}
            GROUP BY model
            ORDER BY cost DESC
            """,
            {"tenant_id": tenant_id},
        )

        by_model = {r[0]: float(r[1]) for r in (model_rows or [])}
        avg_cost = total_cost / total_execs if total_execs > 0 else 0.0

        return AgentCostSummary(
            period=period,
            total_cost_usd=round(total_cost, 4),
            by_agent_type=by_agent,
            by_model=by_model,
            total_tokens=total_tokens,
            total_executions=total_execs,
            avg_cost_per_execution=round(avg_cost, 6),
        )

    # ------------------------------------------------------------------
    # Forecasting
    # ------------------------------------------------------------------

    async def forecast_monthly_cost(
        self,
        tenant_id: str,
    ) -> CostForecast:
        """Based on usage trend, predict monthly cost.

        Uses the last 14 days of data to compute daily averages and detect
        whether usage is trending up, down, or stable.
        """
        rows = await self.clickhouse.execute(
            """
            SELECT
                toDate(started_at) AS dt,
                sum(cost_usd) AS daily_cost
            FROM agents.agent_executions
            WHERE tenant_id = %(tenant_id)s
              AND started_at >= now() - INTERVAL 14 DAY
            GROUP BY dt
            ORDER BY dt ASC
            """,
            {"tenant_id": tenant_id},
        )

        if not rows or len(rows) < 2:
            return CostForecast(
                current_daily_avg=0.0,
                projected_monthly=0.0,
                trend="stable",
                trend_pct=0.0,
                confidence=0.0,
            )

        daily_costs = [float(r[1]) for r in rows]
        n = len(daily_costs)

        # Simple linear regression for trend
        x_mean = (n - 1) / 2
        y_mean = sum(daily_costs) / n
        numerator = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(daily_costs))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        slope = numerator / denominator if denominator > 0 else 0.0

        # Current daily average (last 7 days weighted more)
        recent = daily_costs[-7:] if n >= 7 else daily_costs
        current_daily = sum(recent) / len(recent)

        # Trend detection
        if n >= 7:
            first_half = sum(daily_costs[: n // 2]) / (n // 2)
            second_half = sum(daily_costs[n // 2 :]) / (n - n // 2)
            trend_pct = ((second_half - first_half) / first_half * 100) if first_half > 0 else 0.0
        else:
            trend_pct = 0.0

        if trend_pct > 10:
            trend = "increasing"
        elif trend_pct < -10:
            trend = "decreasing"
        else:
            trend = "stable"

        # Project 30 days forward using slope
        projected_daily = current_daily + slope * 15  # Mid-month estimate
        projected_monthly = max(0, projected_daily * 30)

        # Confidence based on data volume and variance
        variance = sum((c - y_mean) ** 2 for c in daily_costs) / n
        cv = math.sqrt(variance) / y_mean if y_mean > 0 else 1.0
        confidence = max(0.1, min(0.95, 1.0 - cv)) * min(1.0, n / 14)

        return CostForecast(
            current_daily_avg=round(current_daily, 4),
            projected_monthly=round(projected_monthly, 2),
            trend=trend,
            trend_pct=round(trend_pct, 1),
            confidence=round(confidence, 2),
        )

    # ------------------------------------------------------------------
    # Budget management
    # ------------------------------------------------------------------

    async def check_budget(
        self,
        tenant_id: str,
        daily_budget: float,
    ) -> BudgetStatus:
        """Check if tenant is within budget, alert if trending over."""
        rows = await self.clickhouse.execute(
            """
            SELECT
                sum(cost_usd) AS spent_today,
                count() AS exec_count
            FROM agents.agent_executions
            WHERE tenant_id = %(tenant_id)s
              AND started_at >= toStartOfDay(now())
            """,
            {"tenant_id": tenant_id},
        )

        spent = float(rows[0][0]) if rows and rows[0][0] else 0.0
        exec_count = int(rows[0][1]) if rows and rows[0][1] else 0

        remaining = max(0, daily_budget - spent)

        # Project based on time of day (assume linear distribution)
        hour_rows = await self.clickhouse.execute(
            """
            SELECT toHour(now()) AS current_hour
            """,
            {},
        )
        current_hour = int(hour_rows[0][0]) if hour_rows else 12
        hours_elapsed = max(1, current_hour)
        projected_daily = (spent / hours_elapsed) * 24
        projected_overage = max(0, projected_daily - daily_budget)
        on_track = projected_daily <= daily_budget * 1.1  # 10% buffer

        return BudgetStatus(
            daily_budget=daily_budget,
            spent_today=round(spent, 4),
            remaining=round(remaining, 4),
            on_track=on_track,
            projected_overage=round(projected_overage, 4),
        )

    # ------------------------------------------------------------------
    # Optimization suggestions
    # ------------------------------------------------------------------

    async def get_cost_optimization_suggestions(
        self,
        tenant_id: str,
    ) -> list[CostSuggestion]:
        """Suggest ways to reduce agent costs based on usage patterns."""
        suggestions: list[CostSuggestion] = []

        # 1. Check for agents using expensive models on simple queries
        model_rows = await self.clickhouse.execute(
            """
            SELECT
                agent_type, model,
                avg(total_tokens) AS avg_tokens,
                avg(duration_ms) AS avg_duration,
                count() AS executions,
                sum(cost_usd) AS total_cost
            FROM agents.agent_executions
            WHERE tenant_id = %(tenant_id)s
              AND started_at >= now() - INTERVAL 7 DAY
            GROUP BY agent_type, model
            ORDER BY total_cost DESC
            """,
            {"tenant_id": tenant_id},
        )

        for r in (model_rows or []):
            agent_type, model, avg_tokens, avg_duration, execs, cost = r
            avg_tokens = float(avg_tokens)

            # If using an expensive model but avg tokens is low, suggest cheaper model
            if "sonnet" in str(model).lower() and avg_tokens < 2000:
                savings = float(cost) * 0.7  # Haiku is ~10x cheaper
                suggestions.append(
                    CostSuggestion(
                        suggestion=f"Switch {agent_type} to Haiku for simple queries",
                        potential_savings_pct=70.0,
                        effort="low",
                        details=(
                            f"{agent_type} uses {model} with only {avg_tokens:.0f} avg tokens. "
                            f"Switching low-complexity queries to Haiku could save ~${savings:.2f}/week."
                        ),
                    )
                )

        # 2. Check for high retry rates (indicates wasted tokens)
        retry_rows = await self.clickhouse.execute(
            """
            SELECT
                agent_type,
                countIf(status = 'failed') AS failures,
                count() AS total,
                sum(cost_usd) AS wasted_cost
            FROM agents.agent_executions
            WHERE tenant_id = %(tenant_id)s
              AND started_at >= now() - INTERVAL 7 DAY
              AND status = 'failed'
            GROUP BY agent_type
            HAVING failures > 5
            """,
            {"tenant_id": tenant_id},
        )

        for r in (retry_rows or []):
            agent_type, failures, total, wasted = r
            suggestions.append(
                CostSuggestion(
                    suggestion=f"Reduce {agent_type} failure rate to avoid wasted spend",
                    potential_savings_pct=round(float(wasted) / max(float(total), 1) * 100, 1),
                    effort="medium",
                    details=(
                        f"{agent_type} had {failures} failures costing ${float(wasted):.2f}. "
                        f"Fixing common errors would recover this spend."
                    ),
                )
            )

        # 3. Check for executions with excessive iterations
        iter_rows = await self.clickhouse.execute(
            """
            SELECT
                agent_type,
                avg(steps_count) AS avg_steps,
                max(steps_count) AS max_steps,
                sum(cost_usd) AS total_cost
            FROM agents.agent_executions
            WHERE tenant_id = %(tenant_id)s
              AND started_at >= now() - INTERVAL 7 DAY
              AND steps_count > 10
            GROUP BY agent_type
            """,
            {"tenant_id": tenant_id},
        )

        for r in (iter_rows or []):
            agent_type, avg_steps, max_steps, cost = r
            suggestions.append(
                CostSuggestion(
                    suggestion=f"Cap {agent_type} max iterations (currently avg {float(avg_steps):.0f})",
                    potential_savings_pct=25.0,
                    effort="low",
                    details=(
                        f"{agent_type} averages {float(avg_steps):.0f} steps (max: {int(max_steps)}). "
                        f"Capping at 8 iterations could reduce cost by ~25%."
                    ),
                )
            )

        # 4. Always suggest caching
        suggestions.append(
            CostSuggestion(
                suggestion="Enable response caching for repeated queries",
                potential_savings_pct=15.0,
                effort="medium",
                details=(
                    "Many agent queries are similar or identical. Caching tool results "
                    "and agent responses for 5-minute windows can reduce redundant LLM calls."
                ),
            )
        )

        return suggestions

    # ------------------------------------------------------------------
    # Per-investigation cost
    # ------------------------------------------------------------------

    async def get_cost_per_investigation(
        self,
        tenant_id: str,
        agent_type: str,
    ) -> CostPerInvestigation:
        """Average cost per agent investigation over time."""
        rows = await self.clickhouse.execute(
            """
            SELECT
                avg(cost_usd) AS avg_cost,
                quantile(0.5)(cost_usd) AS median_cost,
                quantile(0.95)(cost_usd) AS p95_cost,
                min(cost_usd) AS min_cost,
                max(cost_usd) AS max_cost,
                count() AS total
            FROM agents.agent_executions
            WHERE tenant_id = %(tenant_id)s
              AND agent_type = %(agent_type)s
              AND started_at >= now() - INTERVAL 30 DAY
            """,
            {"tenant_id": tenant_id, "agent_type": agent_type},
        )

        row = rows[0] if rows else [0] * 6

        # 7-day trend
        trend_rows = await self.clickhouse.execute(
            """
            SELECT
                toDate(started_at) AS dt,
                avg(cost_usd) AS avg_cost,
                count() AS executions
            FROM agents.agent_executions
            WHERE tenant_id = %(tenant_id)s
              AND agent_type = %(agent_type)s
              AND started_at >= now() - INTERVAL 7 DAY
            GROUP BY dt
            ORDER BY dt ASC
            """,
            {"tenant_id": tenant_id, "agent_type": agent_type},
        )

        trend = [
            {"date": str(r[0]), "avg_cost": round(float(r[1]), 6), "executions": int(r[2])}
            for r in (trend_rows or [])
        ]

        return CostPerInvestigation(
            agent_type=agent_type,
            avg_cost=round(float(row[0] or 0), 6),
            median_cost=round(float(row[1] or 0), 6),
            p95_cost=round(float(row[2] or 0), 6),
            min_cost=round(float(row[3] or 0), 6),
            max_cost=round(float(row[4] or 0), 6),
            total_investigations=int(row[5] or 0),
            cost_trend_7d=trend,
        )
