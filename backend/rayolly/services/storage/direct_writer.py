"""Direct ClickHouse writer — writes data immediately on ingest for low-latency queries."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class DirectWriter:
    """Writes telemetry directly to ClickHouse on ingest.

    This bypasses NATS for immediate data availability.
    In production, NATS is used for durability and the StorageWriter
    batch-inserts for throughput. DirectWriter is for MVP/low-volume.
    """

    def __init__(self, clickhouse_client: Any) -> None:
        self.ch = clickhouse_client

    def write_logs(self, tenant_id: str, logs: list[dict]) -> int:
        if not self.ch or not logs:
            return 0

        rows = []
        for log in logs:
            ts = log.get("timestamp", 0)
            if isinstance(ts, (int, float)) and ts > 1e15:
                # Nanoseconds — convert to datetime
                dt = datetime.fromtimestamp(ts / 1e9, tz=UTC)
            elif isinstance(ts, (int, float)) and ts > 1e9:
                dt = datetime.fromtimestamp(ts, tz=UTC)
            elif isinstance(ts, str):
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except ValueError:
                    dt = datetime.now(UTC)
            else:
                dt = datetime.now(UTC)

            sev = log.get("severity", log.get("severity_text", "INFO"))
            sev_map = {"TRACE": 1, "DEBUG": 5, "INFO": 9, "WARN": 13, "ERROR": 17, "FATAL": 21}

            rows.append([
                tenant_id,
                dt,
                str(sev),
                sev_map.get(str(sev).upper(), 9),
                log.get("resource_service", log.get("service", "")),
                log.get("resource_host", log.get("host", "")),
                log.get("body", ""),
                log.get("attributes", {}),
                log.get("resource_attributes", {}),
                log.get("trace_id", "") or "",
                log.get("span_id", "") or "",
                log.get("stream", "default"),
            ])

        try:
            self.ch.insert(
                "logs.log_entries",
                rows,
                column_names=[
                    "tenant_id", "timestamp", "severity", "severity_number",
                    "service", "host", "body", "attributes", "resource_attrs",
                    "trace_id", "span_id", "stream",
                ],
            )
            logger.info("direct_write.logs", count=len(rows), tenant=tenant_id)
            return len(rows)
        except Exception as e:
            logger.error("direct_write.logs_failed", error=str(e), count=len(rows))
            return 0

    def write_metrics(self, tenant_id: str, metrics: list[dict]) -> int:
        if not self.ch or not metrics:
            return 0

        rows = []
        for m in metrics:
            ts = m.get("timestamp", 0)
            if isinstance(ts, (int, float)) and ts > 1e15:
                dt = datetime.fromtimestamp(ts / 1e9, tz=UTC)
            elif isinstance(ts, (int, float)) and ts > 1e9:
                dt = datetime.fromtimestamp(ts, tz=UTC)
            elif isinstance(ts, str):
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except ValueError:
                    dt = datetime.now(UTC)
            else:
                dt = datetime.now(UTC)

            labels = m.get("labels", {})
            rows.append([
                tenant_id,
                m.get("name", m.get("metric_name", "")),
                m.get("type", m.get("metric_type", "gauge")),
                dt,
                float(m.get("value", 0)),
                labels,
                labels.get("service", ""),
                labels.get("host", ""),
            ])

        try:
            self.ch.insert(
                "metrics.samples",
                rows,
                column_names=[
                    "tenant_id", "metric_name", "metric_type", "timestamp",
                    "value", "labels", "label_service", "label_host",
                ],
            )
            logger.info("direct_write.metrics", count=len(rows), tenant=tenant_id)
            return len(rows)
        except Exception as e:
            logger.error("direct_write.metrics_failed", error=str(e), count=len(rows))
            return 0

    def write_traces(self, tenant_id: str, spans: list[dict]) -> int:
        if not self.ch or not spans:
            return 0

        rows = []
        for s in spans:
            start = s.get("start_time", 0)
            end = s.get("end_time", 0)
            if isinstance(start, (int, float)) and start > 1e15:
                start_dt = datetime.fromtimestamp(start / 1e9, tz=UTC)
                end_dt = datetime.fromtimestamp(end / 1e9, tz=UTC) if end else start_dt
                duration = end - start if end else 0
            else:
                start_dt = datetime.now(UTC)
                end_dt = start_dt
                duration = 0

            res_attrs = s.get("resource_attributes", {})
            rows.append([
                tenant_id,
                s.get("trace_id", ""),
                s.get("span_id", ""),
                s.get("parent_span_id", ""),
                s.get("name", s.get("operation_name", "")),
                res_attrs.get("service.name", s.get("service", "")),
                s.get("kind", "INTERNAL"),
                start_dt,
                end_dt,
                int(duration),
                s.get("status_code", s.get("status", "OK")),
                s.get("attributes", {}),
                res_attrs,
            ])

        try:
            self.ch.insert(
                "traces.spans",
                rows,
                column_names=[
                    "tenant_id", "trace_id", "span_id", "parent_span_id",
                    "operation_name", "service", "span_kind",
                    "start_time", "end_time", "duration_ns",
                    "status_code", "attributes", "resource_attrs",
                ],
            )
            logger.info("direct_write.traces", count=len(rows), tenant=tenant_id)
            return len(rows)
        except Exception as e:
            logger.error("direct_write.traces_failed", error=str(e), count=len(rows))
            return 0

    def query(self, sql: str) -> Any:
        """Execute a raw query and return results."""
        if not self.ch:
            return None
        return self.ch.query(sql)
