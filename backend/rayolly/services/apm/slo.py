"""SLO (Service Level Objective) management for APM.

Defines, evaluates, and monitors SLOs with error budget tracking
and burn rate alerting.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------

class ClickHouseClient(Protocol):
    async def execute(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]: ...


# ---------------------------------------------------------------------------
# Enums & Data classes
# ---------------------------------------------------------------------------

class SLIType(str, Enum):
    AVAILABILITY = "availability"
    LATENCY = "latency"
    THROUGHPUT = "throughput"


class AlertSeverity(str, Enum):
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class BurnRateAlert:
    burn_rate: float  # e.g. 14.4 for fast burn
    window: str  # e.g. "1h", "6h"
    severity: AlertSeverity


@dataclass
class SLODefinition:
    id: str
    name: str
    service: str
    sli_type: SLIType
    sli_query: str  # ClickHouse SQL query that returns a ratio 0..1
    target_percentage: float  # e.g. 99.95
    window_days: int  # e.g. 30
    alert_burn_rates: list[BurnRateAlert] = field(default_factory=list)


@dataclass
class SLOStatus:
    definition: SLODefinition
    current_value: float  # actual SLI value as percentage (e.g. 99.92)
    error_budget_remaining_pct: float
    burn_rate_1h: float
    burn_rate_6h: float
    burn_rate_24h: float
    is_breaching: bool
    predicted_breach_time: datetime | None


@dataclass(frozen=True)
class ErrorBudgetPoint:
    timestamp: datetime
    budget_remaining_pct: float


# ---------------------------------------------------------------------------
# SLOService
# ---------------------------------------------------------------------------

class SLOService:
    """Evaluates SLOs and tracks error budgets."""

    async def evaluate(
        self,
        tenant_id: str,
        slo: SLODefinition,
        clickhouse: ClickHouseClient,
    ) -> SLOStatus:
        """Evaluate a single SLO and return its current status."""
        now = datetime.utcnow()
        window_start = now - timedelta(days=slo.window_days)

        # Evaluate the SLI over the full window
        current_value = await self._evaluate_sli(
            tenant_id, slo, window_start, now, clickhouse
        )

        # Error budget: how much of the allowed error has been consumed
        target_ratio = slo.target_percentage / 100.0
        error_budget_total = 1.0 - target_ratio  # e.g. 0.0005 for 99.95%
        actual_error_ratio = 1.0 - (current_value / 100.0)

        if error_budget_total > 0:
            budget_consumed_pct = (actual_error_ratio / error_budget_total) * 100.0
            budget_remaining_pct = max(0.0, 100.0 - budget_consumed_pct)
        else:
            budget_remaining_pct = 0.0 if actual_error_ratio > 0 else 100.0

        # Burn rates for different windows
        burn_rate_1h = await self._compute_burn_rate(
            tenant_id, slo, timedelta(hours=1), error_budget_total, clickhouse
        )
        burn_rate_6h = await self._compute_burn_rate(
            tenant_id, slo, timedelta(hours=6), error_budget_total, clickhouse
        )
        burn_rate_24h = await self._compute_burn_rate(
            tenant_id, slo, timedelta(hours=24), error_budget_total, clickhouse
        )

        is_breaching = current_value < slo.target_percentage

        predicted_breach = await self.predict_breach(
            SLOStatus(
                definition=slo,
                current_value=current_value,
                error_budget_remaining_pct=budget_remaining_pct,
                burn_rate_1h=burn_rate_1h,
                burn_rate_6h=burn_rate_6h,
                burn_rate_24h=burn_rate_24h,
                is_breaching=is_breaching,
                predicted_breach_time=None,
            )
        )

        return SLOStatus(
            definition=slo,
            current_value=round(current_value, 4),
            error_budget_remaining_pct=round(budget_remaining_pct, 2),
            burn_rate_1h=round(burn_rate_1h, 2),
            burn_rate_6h=round(burn_rate_6h, 2),
            burn_rate_24h=round(burn_rate_24h, 2),
            is_breaching=is_breaching,
            predicted_breach_time=predicted_breach,
        )

    async def evaluate_all(
        self,
        tenant_id: str,
        clickhouse: ClickHouseClient,
    ) -> list[SLOStatus]:
        """Evaluate all SLOs for a tenant."""
        slo_rows = await clickhouse.execute(
            """
            SELECT
                id, name, service_name, sli_type, sli_query,
                target_percentage, window_days, alert_burn_rates
            FROM apm.slo_definitions
            WHERE tenant_id = %(tenant_id)s
            """,
            {"tenant_id": tenant_id},
        )

        results: list[SLOStatus] = []
        for row in slo_rows:
            burn_rates = self._parse_burn_rates(row.get("alert_burn_rates", "[]"))
            slo = SLODefinition(
                id=row["id"],
                name=row["name"],
                service=row["service_name"],
                sli_type=SLIType(row["sli_type"]),
                sli_query=row["sli_query"],
                target_percentage=float(row["target_percentage"]),
                window_days=int(row["window_days"]),
                alert_burn_rates=burn_rates,
            )
            try:
                status = await self.evaluate(tenant_id, slo, clickhouse)
                results.append(status)
            except Exception:
                logger.exception("Failed to evaluate SLO %s for tenant %s", slo.id, tenant_id)

        return results

    async def predict_breach(self, slo_status: SLOStatus) -> datetime | None:
        """Predict when the error budget will be exhausted based on current burn rate.

        Uses the 6-hour burn rate as the most reliable short-term trend.
        """
        if slo_status.error_budget_remaining_pct <= 0:
            return None  # already breached

        burn_rate = slo_status.burn_rate_6h
        if burn_rate <= 1.0:
            return None  # burning at or below sustainable rate

        slo = slo_status.definition
        error_budget_total = 1.0 - (slo.target_percentage / 100.0)
        budget_remaining_ratio = slo_status.error_budget_remaining_pct / 100.0
        remaining_budget = error_budget_total * budget_remaining_ratio

        # At current burn rate, how many hours of the window-equivalent error
        # budget remain?
        window_hours = slo.window_days * 24
        sustainable_rate = error_budget_total / window_hours if window_hours > 0 else 0
        current_consumption_rate = sustainable_rate * burn_rate

        if current_consumption_rate <= 0:
            return None

        hours_until_breach = remaining_budget / current_consumption_rate
        if math.isinf(hours_until_breach) or hours_until_breach > window_hours:
            return None

        return datetime.utcnow() + timedelta(hours=hours_until_breach)

    async def get_error_budget_history(
        self,
        tenant_id: str,
        slo_id: str,
        time_range: tuple[datetime, datetime],
        clickhouse: ClickHouseClient,
    ) -> list[ErrorBudgetPoint]:
        """Return error budget remaining over time."""
        start, end = time_range

        rows = await clickhouse.execute(
            """
            SELECT timestamp, budget_remaining_pct
            FROM apm.slo_budget_history
            WHERE tenant_id = %(tenant_id)s
              AND slo_id = %(slo_id)s
              AND timestamp BETWEEN %(start)s AND %(end)s
            ORDER BY timestamp
            """,
            {"tenant_id": tenant_id, "slo_id": slo_id, "start": start, "end": end},
        )

        return [
            ErrorBudgetPoint(
                timestamp=r["timestamp"],
                budget_remaining_pct=float(r["budget_remaining_pct"]),
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _evaluate_sli(
        self,
        tenant_id: str,
        slo: SLODefinition,
        start: datetime,
        end: datetime,
        clickhouse: ClickHouseClient,
    ) -> float:
        """Execute the SLI query and return the result as a percentage."""
        if slo.sli_type == SLIType.AVAILABILITY:
            rows = await clickhouse.execute(
                """
                SELECT
                    countIf(status_code < 500) / count() * 100 AS sli_value
                FROM traces.spans
                WHERE tenant_id = %(tenant_id)s
                  AND service_name = %(service)s
                  AND timestamp BETWEEN %(start)s AND %(end)s
                  AND parent_span_id = ''
                """,
                {"tenant_id": tenant_id, "service": slo.service, "start": start, "end": end},
            )
        elif slo.sli_type == SLIType.LATENCY:
            rows = await clickhouse.execute(
                """
                SELECT
                    countIf(duration_ms <= %(threshold)s) / count() * 100 AS sli_value
                FROM traces.spans
                WHERE tenant_id = %(tenant_id)s
                  AND service_name = %(service)s
                  AND timestamp BETWEEN %(start)s AND %(end)s
                  AND parent_span_id = ''
                """,
                {
                    "tenant_id": tenant_id,
                    "service": slo.service,
                    "start": start,
                    "end": end,
                    "threshold": self._extract_latency_threshold(slo.sli_query),
                },
            )
        elif slo.sli_type == SLIType.THROUGHPUT:
            # For throughput SLOs, evaluate using the custom query
            rows = await clickhouse.execute(
                slo.sli_query,
                {"tenant_id": tenant_id, "service": slo.service, "start": start, "end": end},
            )
        else:
            raise ValueError(f"Unsupported SLI type: {slo.sli_type}")

        if rows and "sli_value" in rows[0]:
            return float(rows[0]["sli_value"])
        return 100.0

    async def _compute_burn_rate(
        self,
        tenant_id: str,
        slo: SLODefinition,
        window: timedelta,
        error_budget_total: float,
        clickhouse: ClickHouseClient,
    ) -> float:
        """Compute the burn rate over a given window.

        Burn rate = (actual error rate in window) / (allowed error rate).
        A burn rate of 1.0 means consuming budget at exactly the sustainable pace.
        """
        now = datetime.utcnow()
        window_start = now - window

        sli_value = await self._evaluate_sli(
            tenant_id, slo, window_start, now, clickhouse
        )
        actual_error_ratio = 1.0 - (sli_value / 100.0)

        if error_budget_total <= 0:
            return float("inf") if actual_error_ratio > 0 else 0.0

        # Normalize: what fraction of the full-window budget was consumed
        # in this sub-window?
        window_fraction = window.total_seconds() / (slo.window_days * 86400)
        expected_budget_in_window = error_budget_total * window_fraction

        if expected_budget_in_window <= 0:
            return 0.0

        return actual_error_ratio / expected_budget_in_window

    @staticmethod
    def _extract_latency_threshold(sli_query: str) -> float:
        """Extract a latency threshold from the SLI query string.

        Expects a query or annotation like 'latency_threshold=200' or
        simply a numeric string representing milliseconds.
        """
        import re

        match = re.search(r"(\d+(?:\.\d+)?)", sli_query)
        if match:
            return float(match.group(1))
        return 500.0  # default 500ms

    @staticmethod
    def _parse_burn_rates(raw: str) -> list[BurnRateAlert]:
        """Parse burn rate alerts from a JSON string."""
        import json

        try:
            items = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            return []

        result: list[BurnRateAlert] = []
        for item in items:
            try:
                result.append(
                    BurnRateAlert(
                        burn_rate=float(item["burn_rate"]),
                        window=str(item["window"]),
                        severity=AlertSeverity(item["severity"]),
                    )
                )
            except (KeyError, ValueError):
                continue
        return result
