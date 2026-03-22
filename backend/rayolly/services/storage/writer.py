"""Storage writer — consumes from NATS and writes to ClickHouse."""

from __future__ import annotations

import time
from typing import Any

import orjson
import structlog

logger = structlog.get_logger(__name__)

BATCH_SIZE = 5000
FLUSH_INTERVAL_SECONDS = 5


class StorageWriter:
    """Consumes telemetry from NATS JetStream and batch-writes to ClickHouse."""

    def __init__(self, clickhouse_client: Any, nats_client: Any) -> None:
        self.clickhouse = clickhouse_client
        self.nats = nats_client
        self._log_buffer: list[dict] = []
        self._metric_buffer: list[dict] = []
        self._trace_buffer: list[dict] = []
        self._last_flush = time.monotonic()

    async def start(self) -> None:
        """Subscribe to NATS subjects and start consuming."""
        js = self.nats.jetstream()

        await js.subscribe(
            "rayolly.ingest.logs.*",
            cb=self._handle_log,
            durable="storage-writer-logs",
        )
        await js.subscribe(
            "rayolly.ingest.metrics.*",
            cb=self._handle_metric,
            durable="storage-writer-metrics",
        )
        await js.subscribe(
            "rayolly.ingest.traces.*",
            cb=self._handle_trace,
            durable="storage-writer-traces",
        )

        logger.info("storage_writer_started")

    async def _handle_log(self, msg: Any) -> None:
        records = orjson.loads(msg.data)
        if isinstance(records, dict):
            records = [records]
        self._log_buffer.extend(records)
        await msg.ack()

        if len(self._log_buffer) >= BATCH_SIZE or self._should_flush():
            await self._flush_logs()

    async def _handle_metric(self, msg: Any) -> None:
        records = orjson.loads(msg.data)
        if isinstance(records, dict):
            records = [records]
        self._metric_buffer.extend(records)
        await msg.ack()

        if len(self._metric_buffer) >= BATCH_SIZE or self._should_flush():
            await self._flush_metrics()

    async def _handle_trace(self, msg: Any) -> None:
        records = orjson.loads(msg.data)
        if isinstance(records, dict):
            records = [records]
        self._trace_buffer.extend(records)
        await msg.ack()

        if len(self._trace_buffer) >= BATCH_SIZE or self._should_flush():
            await self._flush_traces()

    def _should_flush(self) -> bool:
        return (time.monotonic() - self._last_flush) >= FLUSH_INTERVAL_SECONDS

    async def _flush_logs(self) -> None:
        if not self._log_buffer:
            return

        batch = self._log_buffer[:]
        self._log_buffer.clear()
        self._last_flush = time.monotonic()

        try:
            columns = [
                "timestamp", "observed_timestamp", "tenant_id", "stream",
                "trace_id", "span_id", "severity_number", "severity_text",
                "body", "resource_service", "resource_host", "resource_namespace",
                "attributes",
            ]
            rows = []
            for record in batch:
                rows.append([
                    record.get("timestamp", ""),
                    record.get("observed_timestamp", ""),
                    record.get("tenant_id", ""),
                    record.get("stream", "default"),
                    record.get("trace_id", ""),
                    record.get("span_id", ""),
                    record.get("severity_number", 9),
                    record.get("severity_text", "INFO"),
                    record.get("body", ""),
                    record.get("resource_service", ""),
                    record.get("resource_host", ""),
                    record.get("resource_namespace", ""),
                    record.get("attributes", {}),
                ])

            self.clickhouse.insert(
                "logs.log_entries",
                rows,
                column_names=columns,
            )
            logger.info("logs_flushed", count=len(batch))
        except Exception as e:
            logger.error("log_flush_error", error=str(e), count=len(batch))
            # Re-queue failed records
            self._log_buffer.extend(batch)

    async def _flush_metrics(self) -> None:
        if not self._metric_buffer:
            return

        batch = self._metric_buffer[:]
        self._metric_buffer.clear()
        self._last_flush = time.monotonic()

        try:
            columns = [
                "tenant_id", "metric_name", "metric_type", "timestamp",
                "value", "labels", "label_service", "label_host",
            ]
            rows = []
            for record in batch:
                labels = record.get("labels", {})
                rows.append([
                    record.get("tenant_id", ""),
                    record.get("metric_name", ""),
                    record.get("metric_type", "gauge"),
                    record.get("timestamp", ""),
                    record.get("value", 0.0),
                    labels,
                    labels.get("service", ""),
                    labels.get("host", ""),
                ])

            self.clickhouse.insert(
                "metrics.samples",
                rows,
                column_names=columns,
            )
            logger.info("metrics_flushed", count=len(batch))
        except Exception as e:
            logger.error("metric_flush_error", error=str(e), count=len(batch))
            self._metric_buffer.extend(batch)

    async def _flush_traces(self) -> None:
        if not self._trace_buffer:
            return

        batch = self._trace_buffer[:]
        self._trace_buffer.clear()
        self._last_flush = time.monotonic()

        try:
            columns = [
                "tenant_id", "trace_id", "span_id", "parent_span_id",
                "operation_name", "resource_service", "span_kind",
                "start_time", "end_time", "duration_ns",
                "status_code", "attributes",
            ]
            rows = []
            for record in batch:
                rows.append([
                    record.get("tenant_id", ""),
                    record.get("trace_id", ""),
                    record.get("span_id", ""),
                    record.get("parent_span_id", ""),
                    record.get("name", ""),
                    record.get("resource_service", ""),
                    record.get("kind", "INTERNAL"),
                    record.get("start_time", ""),
                    record.get("end_time", ""),
                    record.get("duration_ns", 0),
                    record.get("status", "OK"),
                    record.get("attributes", {}),
                ])

            self.clickhouse.insert(
                "traces.spans",
                rows,
                column_names=columns,
            )
            logger.info("traces_flushed", count=len(batch))
        except Exception as e:
            logger.error("trace_flush_error", error=str(e), count=len(batch))
            self._trace_buffer.extend(batch)

    async def stop(self) -> None:
        """Flush remaining buffers and stop."""
        await self._flush_logs()
        await self._flush_metrics()
        await self._flush_traces()
        logger.info("storage_writer_stopped")
