"""Background scheduler for data lifecycle tasks."""

from __future__ import annotations

import asyncio

import structlog

logger = structlog.get_logger(__name__)


class LifecycleScheduler:
    """Runs retention enforcement on a periodic interval for all tenants."""

    def __init__(
        self,
        retention_enforcer: object,
        tenants: list[str] | None = None,
    ) -> None:
        self.enforcer = retention_enforcer
        self.tenants = tenants or ["demo"]
        self._running = False

    async def start(self, interval_hours: int = 24) -> None:
        """Run retention enforcement periodically."""
        self._running = True
        logger.info(
            "lifecycle_scheduler.started",
            interval_hours=interval_hours,
            tenants=self.tenants,
        )

        while self._running:
            for tenant in self.tenants:
                try:
                    await self.enforcer.enforce(tenant)
                except Exception as e:
                    logger.error(
                        "lifecycle_scheduler.enforce_failed",
                        tenant=tenant,
                        error=str(e),
                    )
            await asyncio.sleep(interval_hours * 3600)

    async def stop(self) -> None:
        """Signal the scheduler to stop after the current cycle."""
        self._running = False
        logger.info("lifecycle_scheduler.stopped")
