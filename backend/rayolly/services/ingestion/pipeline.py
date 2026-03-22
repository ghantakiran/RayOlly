from __future__ import annotations

import time
from typing import Any

import structlog

from rayolly.services.ingestion.enrichment import Enricher
from rayolly.services.ingestion.models import (
    IngestionResult,
    LogRecord,
    MetricDataPoint,
    Span,
)
from rayolly.services.ingestion.pii import PIIDetector
from rayolly.services.ingestion.router import MessageRouter
from rayolly.services.ingestion.validators import validate_log, validate_metric, validate_span

logger = structlog.get_logger(__name__)


class PipelineMetrics:
    def __init__(self) -> None:
        self.accepted: int = 0
        self.rejected: int = 0
        self.errors: int = 0

    def reset(self) -> None:
        self.accepted = 0
        self.rejected = 0
        self.errors = 0


class IngestionPipeline:
    def __init__(
        self,
        router: MessageRouter | None = None,
        enricher: Enricher | None = None,
        pii_detector: PIIDetector | None = None,
        pipeline_config: dict[str, Any] | None = None,
        nats_client: Any = None,
        clickhouse_client: Any = None,
    ) -> None:
        if router is None and nats_client is not None:
            router = MessageRouter(nats_client)
        self._router = router
        self._enricher = enricher or Enricher()
        self._pii_detector = pii_detector or PIIDetector()
        self._config = pipeline_config or {}
        self._metrics = PipelineMetrics()
        self._buffer: list[dict] = []

        # Direct ClickHouse writer for immediate data availability
        self._direct_writer = None
        if clickhouse_client is not None:
            from rayolly.services.storage.direct_writer import DirectWriter
            self._direct_writer = DirectWriter(clickhouse_client)

    @property
    def metrics(self) -> PipelineMetrics:
        return self._metrics

    def _apply_transform(self, attributes: dict[str, Any]) -> dict[str, Any]:
        rename_map: dict[str, str] = self._config.get("rename_fields", {})
        drop_fields: set[str] = set(self._config.get("drop_fields", []))

        result = {}
        for key, value in attributes.items():
            if key in drop_fields:
                continue
            new_key = rename_map.get(key, key)
            result[new_key] = value
        return result

    async def process_logs(
        self, tenant_id: str, logs: list[LogRecord]
    ) -> IngestionResult:
        start = time.monotonic()
        accepted: list[LogRecord] = []
        rejected_errors: list[str] = []

        for record in logs:
            vr = validate_log(record)
            if not vr.valid:
                rejected_errors.extend(vr.errors)
                self._metrics.rejected += 1
                continue

            try:
                await self._enricher.enrich(record.attributes, record.resource_attributes)
                record.attributes = self._apply_transform(record.attributes)
                record.body = self._pii_detector.detect_and_redact(record.body, tenant_id)
                accepted.append(record)
            except Exception:
                logger.error("pipeline.log_processing_failed", exc_info=True)
                self._metrics.errors += 1
                rejected_errors.append("Internal processing error")

        if accepted:
            if self._router:
                try:
                    await self._router.route_logs(tenant_id, accepted)
                    self._metrics.accepted += len(accepted)
                except Exception:
                    logger.error("pipeline.log_routing_failed", tenant_id=tenant_id, exc_info=True)
                    self._metrics.errors += len(accepted)
                    try:
                        await self._router.route_dlq(tenant_id, accepted, "Routing failure")
                    except Exception:
                        pass
                    rejected_errors.append("Failed to route logs")
            else:
                self._buffer.extend([r.model_dump() for r in accepted])
                self._metrics.accepted += len(accepted)

            # Also write directly to ClickHouse for immediate query availability
            if self._direct_writer and accepted:
                self._direct_writer.write_logs(tenant_id, [r.model_dump() for r in accepted])

        elapsed_ms = (time.monotonic() - start) * 1000
        return IngestionResult(
            accepted=len(accepted),
            rejected=len(logs) - len(accepted),
            processing_time_ms=round(elapsed_ms, 2),
            errors=rejected_errors,
        )

    async def process_metrics(
        self, tenant_id: str, metrics: list[MetricDataPoint]
    ) -> IngestionResult:
        start = time.monotonic()
        accepted: list[MetricDataPoint] = []
        rejected_errors: list[str] = []

        for dp in metrics:
            vr = validate_metric(dp)
            if not vr.valid:
                rejected_errors.extend(vr.errors)
                self._metrics.rejected += 1
                continue

            try:
                await self._enricher.enrich(dp.labels, dp.resource_attributes)
                dp.labels = {
                    k: v
                    for k, v in self._apply_transform(dp.labels).items()
                    if isinstance(v, str)
                }
                accepted.append(dp)
            except Exception:
                logger.error("pipeline.metric_processing_failed", exc_info=True)
                self._metrics.errors += 1
                rejected_errors.append("Internal processing error")

        if accepted:
            if self._router:
                try:
                    await self._router.route_metrics(tenant_id, accepted)
                    self._metrics.accepted += len(accepted)
                except Exception:
                    logger.error("pipeline.metric_routing_failed", tenant_id=tenant_id, exc_info=True)
                    self._metrics.errors += len(accepted)
                    rejected_errors.append("Failed to route metrics")
            else:
                self._buffer.extend([r.model_dump() for r in accepted])
                self._metrics.accepted += len(accepted)

            if self._direct_writer and accepted:
                self._direct_writer.write_metrics(tenant_id, [r.model_dump() for r in accepted])

        elapsed_ms = (time.monotonic() - start) * 1000
        return IngestionResult(
            accepted=len(accepted),
            rejected=len(metrics) - len(accepted),
            processing_time_ms=round(elapsed_ms, 2),
            errors=rejected_errors,
        )

    async def process_traces(
        self, tenant_id: str, spans: list[Span]
    ) -> IngestionResult:
        start = time.monotonic()
        accepted: list[Span] = []
        rejected_errors: list[str] = []

        for span in spans:
            vr = validate_span(span)
            if not vr.valid:
                rejected_errors.extend(vr.errors)
                self._metrics.rejected += 1
                continue

            try:
                await self._enricher.enrich(span.attributes, span.resource_attributes)
                span.attributes = self._apply_transform(span.attributes)

                for event in span.events:
                    body = event.get("body", "")
                    if isinstance(body, str):
                        event["body"] = self._pii_detector.detect_and_redact(body, tenant_id)

                accepted.append(span)
            except Exception:
                logger.error("pipeline.span_processing_failed", exc_info=True)
                self._metrics.errors += 1
                rejected_errors.append("Internal processing error")

        if accepted:
            if self._router:
                try:
                    await self._router.route_traces(tenant_id, accepted)
                    self._metrics.accepted += len(accepted)
                except Exception:
                    logger.error("pipeline.trace_routing_failed", tenant_id=tenant_id, exc_info=True)
                    self._metrics.errors += len(accepted)
                    rejected_errors.append("Failed to route traces")
            else:
                self._buffer.extend([r.model_dump() for r in accepted])
                self._metrics.accepted += len(accepted)

            if self._direct_writer and accepted:
                self._direct_writer.write_traces(tenant_id, [r.model_dump() for r in accepted])

        elapsed_ms = (time.monotonic() - start) * 1000
        return IngestionResult(
            accepted=len(accepted),
            rejected=len(spans) - len(accepted),
            processing_time_ms=round(elapsed_ms, 2),
            errors=rejected_errors,
        )
