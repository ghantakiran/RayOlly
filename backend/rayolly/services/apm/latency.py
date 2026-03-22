"""Latency analysis engine for APM.

Provides endpoint-level latency analysis, per-trace breakdowns,
time-range comparisons, and anomaly detection.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------

class ClickHouseClient(Protocol):
    async def execute(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]: ...


class AnomalyDetector(Protocol):
    """Pluggable anomaly detection backend."""

    async def is_anomalous(self, metric_name: str, current_value: float, history: list[float]) -> bool: ...


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HistogramBucket:
    le: float  # upper bound in ms
    count: int


@dataclass
class EndpointAnalysis:
    service: str
    operation: str
    p50: float
    p75: float
    p90: float
    p95: float
    p99: float
    max: float
    request_count: int
    error_count: int
    slow_trace_ids: list[str] = field(default_factory=list)
    latency_histogram_buckets: list[HistogramBucket] = field(default_factory=list)


@dataclass(frozen=True)
class SpanBreakdown:
    span_id: str
    name: str
    service: str
    duration_ms: float
    percentage_of_total: float
    is_critical_path: bool


@dataclass
class LatencyBreakdown:
    trace_id: str
    total_duration_ms: float
    spans: list[SpanBreakdown] = field(default_factory=list)


@dataclass(frozen=True)
class LatencySnapshot:
    p50: float
    p75: float
    p90: float
    p95: float
    p99: float
    request_count: int
    error_count: int


@dataclass
class LatencyComparison:
    service: str
    operation: str
    before: LatencySnapshot
    after: LatencySnapshot
    delta_p50: float
    delta_p99: float
    regression_detected: bool


@dataclass(frozen=True)
class AnomalousEndpoint:
    service: str
    operation: str
    current_p99: float
    baseline_p99: float
    deviation_factor: float


# ---------------------------------------------------------------------------
# Histogram helpers
# ---------------------------------------------------------------------------

_DEFAULT_BUCKET_BOUNDS = [5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, float("inf")]


def _build_histogram_query(bounds: list[float]) -> str:
    """Build a ClickHouse CASE expression that buckets durations."""
    parts: list[str] = []
    for b in bounds:
        if math.isinf(b):
            parts.append("'+Inf'")
        else:
            parts.append(f"CASE WHEN duration_ms <= {b} THEN {b} END")
    # Simpler approach: use arrayJoin with predefined bounds
    return ", ".join(str(b) for b in bounds if not math.isinf(b))


# ---------------------------------------------------------------------------
# LatencyAnalyzer
# ---------------------------------------------------------------------------

class LatencyAnalyzer:
    """Analyzes latency across endpoints, traces, and time ranges."""

    def __init__(self, histogram_bounds: list[float] | None = None) -> None:
        self._bounds = histogram_bounds or _DEFAULT_BUCKET_BOUNDS

    # ------------------------------------------------------------------
    # Endpoint analysis
    # ------------------------------------------------------------------

    async def analyze_endpoint(
        self,
        tenant_id: str,
        service: str,
        operation: str,
        time_range: tuple[datetime, datetime],
        clickhouse: ClickHouseClient,
    ) -> EndpointAnalysis:
        start, end = time_range

        rows = await clickhouse.execute(
            """
            SELECT
                count() AS request_count,
                countIf(status_code >= 400) AS error_count,
                quantile(0.50)(duration_ms) AS p50,
                quantile(0.75)(duration_ms) AS p75,
                quantile(0.90)(duration_ms) AS p90,
                quantile(0.95)(duration_ms) AS p95,
                quantile(0.99)(duration_ms) AS p99,
                max(duration_ms) AS max_latency
            FROM traces.spans
            WHERE tenant_id = %(tenant_id)s
              AND service_name = %(service)s
              AND operation_name = %(operation)s
              AND timestamp BETWEEN %(start)s AND %(end)s
              AND parent_span_id = ''
            """,
            {
                "tenant_id": tenant_id,
                "service": service,
                "operation": operation,
                "start": start,
                "end": end,
            },
        )

        r = rows[0] if rows else {}

        # Slow traces (p99+)
        p99_val = float(r.get("p99", 0))
        slow_rows = await clickhouse.execute(
            """
            SELECT trace_id
            FROM traces.spans
            WHERE tenant_id = %(tenant_id)s
              AND service_name = %(service)s
              AND operation_name = %(operation)s
              AND timestamp BETWEEN %(start)s AND %(end)s
              AND parent_span_id = ''
              AND duration_ms >= %(threshold)s
            ORDER BY duration_ms DESC
            LIMIT 10
            """,
            {
                "tenant_id": tenant_id,
                "service": service,
                "operation": operation,
                "start": start,
                "end": end,
                "threshold": p99_val,
            },
        )

        # Histogram
        hist_rows = await clickhouse.execute(
            """
            SELECT
                bucket,
                count() AS cnt
            FROM (
                SELECT
                    multiIf(
                        duration_ms <= 5, 5,
                        duration_ms <= 10, 10,
                        duration_ms <= 25, 25,
                        duration_ms <= 50, 50,
                        duration_ms <= 100, 100,
                        duration_ms <= 250, 250,
                        duration_ms <= 500, 500,
                        duration_ms <= 1000, 1000,
                        duration_ms <= 2500, 2500,
                        duration_ms <= 5000, 5000,
                        duration_ms <= 10000, 10000,
                        999999
                    ) AS bucket
                FROM traces.spans
                WHERE tenant_id = %(tenant_id)s
                  AND service_name = %(service)s
                  AND operation_name = %(operation)s
                  AND timestamp BETWEEN %(start)s AND %(end)s
                  AND parent_span_id = ''
            )
            GROUP BY bucket
            ORDER BY bucket
            """,
            {
                "tenant_id": tenant_id,
                "service": service,
                "operation": operation,
                "start": start,
                "end": end,
            },
        )

        return EndpointAnalysis(
            service=service,
            operation=operation,
            p50=float(r.get("p50", 0)),
            p75=float(r.get("p75", 0)),
            p90=float(r.get("p90", 0)),
            p95=float(r.get("p95", 0)),
            p99=p99_val,
            max=float(r.get("max_latency", 0)),
            request_count=int(r.get("request_count", 0)),
            error_count=int(r.get("error_count", 0)),
            slow_trace_ids=[row["trace_id"] for row in slow_rows],
            latency_histogram_buckets=[
                HistogramBucket(le=float(row["bucket"]), count=int(row["cnt"]))
                for row in hist_rows
            ],
        )

    # ------------------------------------------------------------------
    # Trace latency breakdown
    # ------------------------------------------------------------------

    async def breakdown_latency(
        self,
        tenant_id: str,
        trace_id: str,
        clickhouse: ClickHouseClient,
    ) -> LatencyBreakdown:
        rows = await clickhouse.execute(
            """
            SELECT
                span_id,
                parent_span_id,
                operation_name,
                service_name,
                duration_ms,
                start_time,
                end_time
            FROM traces.spans
            WHERE tenant_id = %(tenant_id)s
              AND trace_id = %(trace_id)s
            ORDER BY start_time
            """,
            {"tenant_id": tenant_id, "trace_id": trace_id},
        )

        if not rows:
            return LatencyBreakdown(trace_id=trace_id, total_duration_ms=0.0)

        # Find root span
        root = next((r for r in rows if not r.get("parent_span_id")), rows[0])
        total_ms = float(root["duration_ms"])
        if total_ms == 0:
            total_ms = 1.0  # avoid division by zero

        # Build children map for critical path detection
        children: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            pid = r.get("parent_span_id", "")
            children.setdefault(pid, []).append(r)

        # Critical path: longest child at each level
        critical_span_ids: set[str] = set()
        self._mark_critical_path(root["span_id"], children, critical_span_ids)

        spans = [
            SpanBreakdown(
                span_id=r["span_id"],
                name=r["operation_name"],
                service=r["service_name"],
                duration_ms=float(r["duration_ms"]),
                percentage_of_total=round(float(r["duration_ms"]) / total_ms * 100, 2),
                is_critical_path=r["span_id"] in critical_span_ids,
            )
            for r in rows
        ]

        return LatencyBreakdown(
            trace_id=trace_id,
            total_duration_ms=total_ms,
            spans=spans,
        )

    def _mark_critical_path(
        self,
        span_id: str,
        children: dict[str, list[dict[str, Any]]],
        result: set[str],
    ) -> None:
        result.add(span_id)
        kids = children.get(span_id, [])
        if kids:
            longest = max(kids, key=lambda s: float(s["duration_ms"]))
            self._mark_critical_path(longest["span_id"], children, result)

    # ------------------------------------------------------------------
    # Time-range comparison
    # ------------------------------------------------------------------

    async def compare_latency(
        self,
        tenant_id: str,
        service: str,
        operation: str,
        range_a: tuple[datetime, datetime],
        range_b: tuple[datetime, datetime],
        clickhouse: ClickHouseClient,
    ) -> LatencyComparison:
        async def _snapshot(tr: tuple[datetime, datetime]) -> LatencySnapshot:
            rows = await clickhouse.execute(
                """
                SELECT
                    count() AS request_count,
                    countIf(status_code >= 400) AS error_count,
                    quantile(0.50)(duration_ms) AS p50,
                    quantile(0.75)(duration_ms) AS p75,
                    quantile(0.90)(duration_ms) AS p90,
                    quantile(0.95)(duration_ms) AS p95,
                    quantile(0.99)(duration_ms) AS p99
                FROM traces.spans
                WHERE tenant_id = %(tenant_id)s
                  AND service_name = %(service)s
                  AND operation_name = %(operation)s
                  AND timestamp BETWEEN %(start)s AND %(end)s
                  AND parent_span_id = ''
                """,
                {
                    "tenant_id": tenant_id,
                    "service": service,
                    "operation": operation,
                    "start": tr[0],
                    "end": tr[1],
                },
            )
            r = rows[0] if rows else {}
            return LatencySnapshot(
                p50=float(r.get("p50", 0)),
                p75=float(r.get("p75", 0)),
                p90=float(r.get("p90", 0)),
                p95=float(r.get("p95", 0)),
                p99=float(r.get("p99", 0)),
                request_count=int(r.get("request_count", 0)),
                error_count=int(r.get("error_count", 0)),
            )

        before = await _snapshot(range_a)
        after = await _snapshot(range_b)

        delta_p50 = after.p50 - before.p50
        delta_p99 = after.p99 - before.p99

        # Regression: p99 increased by >20% and at least 10ms
        regression = (
            before.p99 > 0
            and delta_p99 > 10
            and (delta_p99 / before.p99) > 0.20
        )

        return LatencyComparison(
            service=service,
            operation=operation,
            before=before,
            after=after,
            delta_p50=round(delta_p50, 2),
            delta_p99=round(delta_p99, 2),
            regression_detected=regression,
        )

    # ------------------------------------------------------------------
    # Anomaly detection
    # ------------------------------------------------------------------

    async def detect_latency_anomalies(
        self,
        tenant_id: str,
        service: str,
        time_range: tuple[datetime, datetime],
        clickhouse: ClickHouseClient,
        anomaly_detector: AnomalyDetector,
    ) -> list[AnomalousEndpoint]:
        start, end = time_range

        rows = await clickhouse.execute(
            """
            SELECT
                operation_name,
                quantile(0.99)(duration_ms) AS p99
            FROM traces.spans
            WHERE tenant_id = %(tenant_id)s
              AND service_name = %(service)s
              AND timestamp BETWEEN %(start)s AND %(end)s
              AND parent_span_id = ''
            GROUP BY operation_name
            """,
            {"tenant_id": tenant_id, "service": service, "start": start, "end": end},
        )

        # Get baseline (7-day history, hourly p99)
        baseline_rows = await clickhouse.execute(
            """
            SELECT
                operation_name,
                toStartOfHour(timestamp) AS hour,
                quantile(0.99)(duration_ms) AS p99
            FROM traces.spans
            WHERE tenant_id = %(tenant_id)s
              AND service_name = %(service)s
              AND timestamp BETWEEN %(baseline_start)s AND %(start)s
              AND parent_span_id = ''
            GROUP BY operation_name, hour
            ORDER BY operation_name, hour
            """,
            {
                "tenant_id": tenant_id,
                "service": service,
                "start": start,
                "end": end,
                "baseline_start": datetime.fromtimestamp(start.timestamp() - 7 * 86400),
            },
        )

        # Build history per operation
        history_map: dict[str, list[float]] = {}
        for br in baseline_rows:
            history_map.setdefault(br["operation_name"], []).append(float(br["p99"]))

        anomalies: list[AnomalousEndpoint] = []
        for row in rows:
            op = row["operation_name"]
            current_p99 = float(row["p99"])
            history = history_map.get(op, [])
            if not history:
                continue

            metric_name = f"{service}.{op}.p99"
            if await anomaly_detector.is_anomalous(metric_name, current_p99, history):
                baseline_avg = sum(history) / len(history)
                deviation = current_p99 / baseline_avg if baseline_avg > 0 else 0
                anomalies.append(
                    AnomalousEndpoint(
                        service=service,
                        operation=op,
                        current_p99=current_p99,
                        baseline_p99=round(baseline_avg, 2),
                        deviation_factor=round(deviation, 2),
                    )
                )

        return anomalies
