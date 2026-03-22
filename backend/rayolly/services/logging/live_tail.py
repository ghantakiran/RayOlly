"""Live tail — real-time log streaming via WebSocket and NATS."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import orjson
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class TailFilter:
    """Filter criteria for live tail subscription."""
    services: list[str] = field(default_factory=list)
    severities: list[str] = field(default_factory=list)
    hosts: list[str] = field(default_factory=list)
    query: str = ""
    stream: str | None = None


@dataclass
class TailStats:
    """Statistics for the current tail session."""
    total_received: int = 0
    total_matched: int = 0
    total_dropped: int = 0
    logs_per_second: float = 0.0


class LiveTailService:
    """Provides real-time log streaming from NATS to WebSocket clients."""

    def __init__(self, nats_client: Any) -> None:
        self.nats = nats_client
        self._active_subscriptions: dict[str, Any] = {}

    async def subscribe(
        self,
        tenant_id: str,
        session_id: str,
        filters: TailFilter,
        max_rate: int = 1000,
    ) -> AsyncIterator[dict]:
        """Subscribe to live logs for a tenant with optional filters.

        Yields log records as they arrive, applying filters server-side.
        Rate-limited to max_rate logs/second to prevent client overload.
        """
        subject = f"rayolly.ingest.logs.{tenant_id}"
        queue = asyncio.Queue(maxsize=max_rate * 2)
        stats = TailStats()

        log = logger.bind(
            tenant_id=tenant_id,
            session_id=session_id,
            subject=subject,
        )
        log.info("live_tail_started", filters=filters)

        async def _message_handler(msg: Any) -> None:
            try:
                records = orjson.loads(msg.data)
                if isinstance(records, dict):
                    records = [records]

                for record in records:
                    stats.total_received += 1
                    if self._matches_filter(record, filters):
                        stats.total_matched += 1
                        try:
                            queue.put_nowait(record)
                        except asyncio.QueueFull:
                            stats.total_dropped += 1
            except Exception as e:
                log.warning("tail_message_error", error=str(e))

        try:
            js = self.nats.jetstream()
            sub = await js.subscribe(
                subject,
                deliver_policy="new",
            )
            self._active_subscriptions[session_id] = sub

            # Background task to consume NATS messages
            consumer_task = asyncio.create_task(self._consume(sub, _message_handler))

            try:
                while True:
                    try:
                        record = await asyncio.wait_for(queue.get(), timeout=30.0)
                        yield {
                            "type": "log",
                            "data": record,
                            "stats": {
                                "received": stats.total_received,
                                "matched": stats.total_matched,
                                "dropped": stats.total_dropped,
                            },
                        }
                    except TimeoutError:
                        # Send heartbeat
                        yield {
                            "type": "heartbeat",
                            "stats": {
                                "received": stats.total_received,
                                "matched": stats.total_matched,
                                "dropped": stats.total_dropped,
                            },
                        }
            finally:
                consumer_task.cancel()
                try:
                    await consumer_task
                except asyncio.CancelledError:
                    pass

        except Exception as e:
            log.error("live_tail_error", error=str(e))
            raise
        finally:
            await self.unsubscribe(session_id)
            log.info(
                "live_tail_stopped",
                total_received=stats.total_received,
                total_matched=stats.total_matched,
            )

    async def unsubscribe(self, session_id: str) -> None:
        """Stop a live tail subscription."""
        sub = self._active_subscriptions.pop(session_id, None)
        if sub:
            try:
                await sub.unsubscribe()
            except Exception:
                pass

    @staticmethod
    async def _consume(sub: Any, handler: Any) -> None:
        """Consume NATS messages and pass to handler."""
        try:
            async for msg in sub.messages:
                await handler(msg)
                await msg.ack()
        except asyncio.CancelledError:
            pass

    @staticmethod
    def _matches_filter(record: dict, filters: TailFilter) -> bool:
        """Check if a log record matches the filter criteria."""
        if filters.services:
            svc = record.get("resource_service", "")
            if svc not in filters.services:
                return False

        if filters.severities:
            sev = record.get("severity_text", "")
            if sev not in filters.severities:
                return False

        if filters.hosts:
            host = record.get("resource_host", "")
            if host not in filters.hosts:
                return False

        if filters.stream:
            if record.get("stream", "") != filters.stream:
                return False

        if filters.query:
            body = record.get("body", "").lower()
            terms = filters.query.lower().split()
            if not all(term in body for term in terms):
                return False

        return True

    @property
    def active_count(self) -> int:
        return len(self._active_subscriptions)
