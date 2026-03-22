from __future__ import annotations

from typing import Any

import nats
import nats.js
import orjson
import structlog
from nats.aio.client import Client as NATSClient
from nats.js import JetStreamContext

from rayolly.services.ingestion.models import LogRecord, MetricDataPoint, Span

logger = structlog.get_logger(__name__)

SUBJECT_LOGS = "rayolly.ingest.logs.{tenant_id}"
SUBJECT_METRICS = "rayolly.ingest.metrics.{tenant_id}"
SUBJECT_TRACES = "rayolly.ingest.traces.{tenant_id}"
SUBJECT_DLQ = "rayolly.dlq.{tenant_id}"

DEFAULT_BATCH_SIZE = 100
MAX_PENDING_BYTES = 64 * 1024 * 1024  # 64 MB backpressure threshold


class MessageRouter:
    def __init__(
        self,
        nc: NATSClient | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_pending_bytes: int = MAX_PENDING_BYTES,
    ) -> None:
        self._nc = nc
        self._js: JetStreamContext | None = None
        self._batch_size = batch_size
        self._max_pending_bytes = max_pending_bytes

    async def start(self, nats_url: str = "nats://localhost:4222") -> None:
        if self._nc is None or not self._nc.is_connected:
            self._nc = await nats.connect(nats_url)
        self._js = self._nc.jetstream()
        logger.info("message_router.started", nats_url=nats_url)

    async def stop(self) -> None:
        if self._nc and self._nc.is_connected:
            await self._nc.drain()
            logger.info("message_router.stopped")

    def _serialize_records(self, records: list[Any]) -> list[bytes]:
        results: list[bytes] = []
        for record in records:
            if hasattr(record, "model_dump"):
                results.append(orjson.dumps(record.model_dump()))
            else:
                results.append(orjson.dumps(record))
        return results

    async def _check_backpressure(self) -> bool:
        if self._nc is None:
            return False
        stats = self._nc.stats
        pending = stats.get("out_bytes", 0) - stats.get("in_bytes", 0)
        if pending > self._max_pending_bytes:
            logger.warning(
                "message_router.backpressure",
                pending_bytes=pending,
                threshold=self._max_pending_bytes,
            )
            return True
        return False

    async def _ensure_js(self) -> None:
        """Lazy-initialize JetStream context."""
        if self._js is None and self._nc is not None and self._nc.is_connected:
            self._js = self._nc.jetstream()

    async def _publish_batch(self, subject: str, payloads: list[bytes]) -> int:
        await self._ensure_js()
        if self._js is None:
            raise RuntimeError("MessageRouter: NATS JetStream not available")

        if await self._check_backpressure():
            raise RuntimeError(f"Backpressure exceeded on subject {subject}")

        published = 0
        for i in range(0, len(payloads), self._batch_size):
            batch = payloads[i : i + self._batch_size]
            for payload in batch:
                try:
                    await self._js.publish(subject, payload)
                    published += 1
                except Exception:
                    logger.error(
                        "message_router.publish_failed",
                        subject=subject,
                        exc_info=True,
                    )

        logger.debug("message_router.published", subject=subject, count=published)
        return published

    async def route_logs(self, tenant_id: str, logs: list[LogRecord]) -> int:
        subject = SUBJECT_LOGS.format(tenant_id=tenant_id)
        payloads = self._serialize_records(logs)
        return await self._publish_batch(subject, payloads)

    async def route_metrics(self, tenant_id: str, metrics: list[MetricDataPoint]) -> int:
        subject = SUBJECT_METRICS.format(tenant_id=tenant_id)
        payloads = self._serialize_records(metrics)
        return await self._publish_batch(subject, payloads)

    async def route_traces(self, tenant_id: str, spans: list[Span]) -> int:
        subject = SUBJECT_TRACES.format(tenant_id=tenant_id)
        payloads = self._serialize_records(spans)
        return await self._publish_batch(subject, payloads)

    async def route_dlq(
        self,
        tenant_id: str,
        failed_records: list[Any],
        error: str,
    ) -> int:
        subject = SUBJECT_DLQ.format(tenant_id=tenant_id)
        envelope = {
            "error": error,
            "record_count": len(failed_records),
            "records": [
                r.model_dump() if hasattr(r, "model_dump") else r for r in failed_records
            ],
        }
        payload = orjson.dumps(envelope)
        if self._js is None:
            raise RuntimeError("MessageRouter not started; call start() first")
        try:
            await self._js.publish(subject, payload)
            logger.info("message_router.dlq_published", tenant_id=tenant_id, count=len(failed_records))
            return len(failed_records)
        except Exception:
            logger.error("message_router.dlq_publish_failed", tenant_id=tenant_id, exc_info=True)
            return 0
