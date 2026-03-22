"""Synthetic check scheduler.

Manages the lifecycle of synthetic monitors — loading, scheduling,
executing checks at configured intervals, detecting state transitions,
and firing alerts on status changes.
"""

from __future__ import annotations

import asyncio
import logging

from .monitor import (
    CheckResult,
    CheckStatus,
    MonitorConfig,
    SyntheticMonitorService,
)

logger = logging.getLogger(__name__)


class SyntheticScheduler:
    """Loads enabled monitors and schedules periodic checks using asyncio.

    Detects state transitions (up->down, down->up) and fires alerts on change.
    """

    def __init__(
        self,
        monitor_service: SyntheticMonitorService,
        clickhouse=None,
        nats_client=None,
        alert_service=None,
    ):
        self._monitor_service = monitor_service
        self._ch = clickhouse
        self._nats = nats_client
        self._alert_service = alert_service

        self._tasks: dict[str, asyncio.Task] = {}
        self._monitors: dict[str, MonitorConfig] = {}
        self._last_status: dict[str, CheckStatus] = {}
        self._running = False

    async def start(self) -> None:
        """Load all enabled monitors and schedule them."""
        if self._running:
            logger.warning("Scheduler is already running")
            return

        self._running = True
        logger.info("Starting synthetic scheduler")

        monitors = await self._load_monitors()
        for monitor in monitors:
            if monitor.enabled:
                await self._schedule_monitor(monitor)

        logger.info("Scheduled %d monitors", len(self._tasks))

    async def stop(self) -> None:
        """Cancel all scheduled monitor tasks and shut down."""
        self._running = False
        logger.info("Stopping synthetic scheduler, cancelling %d tasks", len(self._tasks))

        for monitor_id, task in self._tasks.items():
            task.cancel()
            logger.debug("Cancelled task for monitor %s", monitor_id)

        # Wait for all tasks to complete cancellation
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)

        self._tasks.clear()
        self._monitors.clear()
        logger.info("Synthetic scheduler stopped")

    async def add_monitor(self, monitor: MonitorConfig) -> None:
        """Add and schedule a new monitor at runtime."""
        if monitor.id in self._tasks:
            logger.warning("Monitor %s is already scheduled; removing first", monitor.id)
            await self.remove_monitor(monitor.id)

        self._monitors[monitor.id] = monitor
        if monitor.enabled:
            await self._schedule_monitor(monitor)

    async def remove_monitor(self, monitor_id: str) -> None:
        """Remove and cancel a monitor's scheduled task."""
        task = self._tasks.pop(monitor_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._monitors.pop(monitor_id, None)
        self._last_status.pop(monitor_id, None)
        logger.info("Removed monitor %s", monitor_id)

    async def _schedule_monitor(self, monitor: MonitorConfig) -> None:
        """Create an asyncio task that runs the check at the configured interval."""
        self._monitors[monitor.id] = monitor
        task = asyncio.create_task(
            self._monitor_loop(monitor),
            name=f"synthetic-{monitor.id}",
        )
        self._tasks[monitor.id] = task
        logger.info(
            "Scheduled monitor %s (%s) every %ds from %d locations",
            monitor.id,
            monitor.name,
            monitor.interval_seconds,
            len(monitor.locations),
        )

    async def _monitor_loop(self, monitor: MonitorConfig) -> None:
        """Periodically execute checks for a monitor across all locations."""
        while self._running:
            try:
                # Run checks from all configured locations concurrently
                check_tasks = [
                    self._execute_and_process(monitor, location)
                    for location in monitor.locations
                ]
                await asyncio.gather(*check_tasks, return_exceptions=True)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Unexpected error in monitor loop: %s", monitor.id)

            try:
                await asyncio.sleep(monitor.interval_seconds)
            except asyncio.CancelledError:
                raise

    async def _execute_and_process(self, monitor: MonitorConfig, location: str) -> None:
        """Execute a single check and process the result."""
        try:
            result = await self._monitor_service.execute_check(monitor, location)
            await self._process_result(monitor, result)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Failed to execute check: monitor=%s location=%s",
                monitor.id,
                location,
            )

    async def _process_result(self, monitor: MonitorConfig, result: CheckResult) -> None:
        """Store result in ClickHouse, detect state transitions, and fire alerts."""
        # Store in ClickHouse
        await self._store_result(monitor, result)

        # Detect state transitions
        previous_status = self._last_status.get(monitor.id)
        current_status = result.status
        self._last_status[monitor.id] = current_status

        if previous_status is not None and previous_status != current_status:
            await self._handle_state_transition(monitor, result, previous_status, current_status)

        # Publish result to NATS for real-time consumers
        await self._publish_result(monitor, result)

    async def _store_result(self, monitor: MonitorConfig, result: CheckResult) -> None:
        """Insert check result into ClickHouse."""
        if self._ch is None:
            logger.debug("ClickHouse not configured; skipping result storage")
            return

        query = """
            INSERT INTO synthetic_check_results (
                tenant_id, monitor_id, location, timestamp, status,
                response_time_ms, status_code, dns_time_ms, connect_time_ms,
                tls_time_ms, ttfb_ms, body_size_bytes, error_message
            ) VALUES (
                %(tenant_id)s, %(monitor_id)s, %(location)s, %(timestamp)s, %(status)s,
                %(response_time_ms)s, %(status_code)s, %(dns_time_ms)s, %(connect_time_ms)s,
                %(tls_time_ms)s, %(ttfb_ms)s, %(body_size_bytes)s, %(error_message)s
            )
        """
        params = {
            "tenant_id": monitor.tenant_id,
            "monitor_id": result.monitor_id,
            "location": result.location,
            "timestamp": result.timestamp.isoformat(),
            "status": result.status.value,
            "response_time_ms": result.response_time_ms,
            "status_code": result.status_code,
            "dns_time_ms": result.dns_time_ms,
            "connect_time_ms": result.connect_time_ms,
            "tls_time_ms": result.tls_time_ms,
            "ttfb_ms": result.ttfb_ms,
            "body_size_bytes": result.body_size_bytes,
            "error_message": result.error_message,
        }
        try:
            await self._ch.execute(query, params)
        except Exception:
            logger.exception("Failed to store check result: monitor=%s", result.monitor_id)

    async def _handle_state_transition(
        self,
        monitor: MonitorConfig,
        result: CheckResult,
        previous: CheckStatus,
        current: CheckStatus,
    ) -> None:
        """Handle monitor state transitions by firing alerts."""
        is_recovery = previous in (CheckStatus.DOWN, CheckStatus.DEGRADED) and current == CheckStatus.UP
        is_failure = previous == CheckStatus.UP and current in (CheckStatus.DOWN, CheckStatus.DEGRADED)

        if is_failure:
            logger.warning(
                "Monitor DOWN: %s (%s) %s -> %s | error: %s",
                monitor.id,
                monitor.name,
                previous.value,
                current.value,
                result.error_message,
            )
            alert_type = "monitor_down"
        elif is_recovery:
            logger.info(
                "Monitor RECOVERED: %s (%s) %s -> %s",
                monitor.id,
                monitor.name,
                previous.value,
                current.value,
            )
            alert_type = "monitor_recovered"
        else:
            logger.info(
                "Monitor state change: %s (%s) %s -> %s",
                monitor.id,
                monitor.name,
                previous.value,
                current.value,
            )
            alert_type = "monitor_state_change"

        if self._alert_service and monitor.alert_channels:
            try:
                await self._alert_service.send_alert(
                    channels=monitor.alert_channels,
                    alert_type=alert_type,
                    monitor_name=monitor.name,
                    monitor_id=monitor.id,
                    target=monitor.target,
                    previous_status=previous.value,
                    current_status=current.value,
                    error_message=result.error_message,
                    response_time_ms=result.response_time_ms,
                    location=result.location,
                    timestamp=result.timestamp.isoformat(),
                )
            except Exception:
                logger.exception(
                    "Failed to send alert for monitor %s state transition",
                    monitor.id,
                )

    async def _publish_result(self, monitor: MonitorConfig, result: CheckResult) -> None:
        """Publish check result to NATS for real-time dashboards."""
        if self._nats is None:
            return

        import json
        subject = f"synthetics.result.{monitor.tenant_id}.{monitor.id}"
        payload = json.dumps(result.to_dict()).encode("utf-8")
        try:
            await self._nats.publish(subject, payload)
        except Exception:
            logger.warning("Failed to publish result to NATS: monitor=%s", monitor.id)

    async def _load_monitors(self) -> list[MonitorConfig]:
        """Load all enabled monitors from ClickHouse."""
        if self._ch is None:
            logger.warning("ClickHouse not configured; no monitors to load")
            return []

        query = """
            SELECT *
            FROM synthetic_monitors
            WHERE enabled = 1
            ORDER BY name
        """
        try:
            rows = await self._ch.fetch(query, {})
            monitors = []
            for row in rows:
                row = dict(row)
                monitors.append(
                    MonitorConfig(
                        id=row["id"],
                        name=row["name"],
                        type=row["type"],
                        target=row["target"],
                        method=row.get("method", "GET"),
                        headers=row.get("headers", {}),
                        body=row.get("body"),
                        assertions=row.get("assertions", []),
                        locations=row.get("locations", ["us-east-1"]),
                        interval_seconds=row.get("interval_seconds", 300),
                        timeout_seconds=row.get("timeout_seconds", 30),
                        alert_channels=row.get("alert_channels", []),
                        enabled=row.get("enabled", True),
                        tags=row.get("tags", []),
                        tenant_id=row.get("tenant_id"),
                    )
                )
            return monitors
        except Exception:
            logger.exception("Failed to load monitors from ClickHouse")
            return []
