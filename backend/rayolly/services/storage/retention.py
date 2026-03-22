"""Data retention -- enforce per-tenant retention policies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class RetentionPolicy:
    """Per-tenant data retention configuration."""

    tenant_id: str
    logs_hot_days: int = 7  # Keep in ClickHouse
    logs_cold_days: int = 90  # Keep in S3
    logs_delete_days: int = 365  # Delete permanently
    metrics_hot_days: int = 30
    metrics_cold_days: int = 365
    traces_hot_days: int = 14
    traces_cold_days: int = 90
    compliance_hold: bool = False  # Legal hold -- prevent deletion


DEFAULT_POLICIES: dict[str, RetentionPolicy] = {
    "free": RetentionPolicy(
        tenant_id="",
        logs_hot_days=3,
        logs_cold_days=30,
        logs_delete_days=30,
    ),
    "pro": RetentionPolicy(
        tenant_id="",
        logs_hot_days=7,
        logs_cold_days=90,
        logs_delete_days=365,
    ),
    "enterprise": RetentionPolicy(
        tenant_id="",
        logs_hot_days=30,
        logs_cold_days=365,
        logs_delete_days=2555,
    ),
}


class RetentionEnforcer:
    """Applies retention rules: hot -> cold archival and permanent deletion."""

    def __init__(
        self,
        clickhouse_client: Any,
        cold_tier_writer: Any | None = None,
    ) -> None:
        self.ch = clickhouse_client
        self.cold_writer = cold_tier_writer
        self._policies: dict[str, RetentionPolicy] = {}

    def set_policy(self, tenant_id: str, policy: RetentionPolicy) -> None:
        policy.tenant_id = tenant_id
        self._policies[tenant_id] = policy

    def get_policy(
        self,
        tenant_id: str,
        tier: str = "pro",
    ) -> RetentionPolicy:
        return self._policies.get(
            tenant_id,
            DEFAULT_POLICIES.get(tier, DEFAULT_POLICIES["pro"]),
        )

    async def enforce(self, tenant_id: str) -> dict:
        """Enforce retention policy for a tenant. Returns summary of actions."""
        policy = self.get_policy(tenant_id)

        if policy.compliance_hold:
            logger.info("retention.skipped_compliance_hold", tenant=tenant_id)
            return {"status": "skipped", "reason": "compliance_hold"}

        actions: dict[str, Any] = {}

        # Archive hot -> cold
        if self.cold_writer:
            actions["logs_archived"] = await self.cold_writer.archive_logs(
                tenant_id, policy.logs_hot_days
            )
            actions["metrics_archived"] = await self.cold_writer.archive_metrics(
                tenant_id, policy.metrics_hot_days
            )

        # Delete expired data beyond total retention window
        table_configs = [
            ("logs.log_entries", policy.logs_delete_days, "timestamp"),
            (
                "metrics.samples",
                policy.metrics_cold_days + policy.metrics_hot_days,
                "timestamp",
            ),
            (
                "traces.spans",
                policy.traces_cold_days + policy.traces_hot_days,
                "start_time",
            ),
        ]

        for table, days_total, ts_col in table_configs:
            cutoff = datetime.now(UTC) - timedelta(days=days_total)
            try:
                self.ch.command(
                    f"ALTER TABLE {table} DELETE "
                    f"WHERE tenant_id = '{tenant_id}' "
                    f"AND {ts_col} < '{cutoff.isoformat()}'"
                )
                actions[f"{table}_deleted_before"] = cutoff.isoformat()
            except Exception as e:
                logger.error(
                    "retention.delete_failed",
                    table=table,
                    tenant=tenant_id,
                    error=str(e),
                )

        logger.info("retention.enforced", tenant=tenant_id, actions=actions)
        return actions

    async def gdpr_erase(self, tenant_id: str, user_id: str) -> dict:
        """GDPR right-to-erasure: delete all data containing a user's PII."""
        erased: dict[str, str] = {}

        for table in [
            "logs.log_entries",
            "metrics.samples",
            "traces.spans",
        ]:
            try:
                self.ch.command(
                    f"ALTER TABLE {table} DELETE "
                    f"WHERE tenant_id = '{tenant_id}' "
                    f"AND attributes['user_id'] = '{user_id}'"
                )
                erased[table] = "erased"
            except Exception as e:
                erased[table] = f"error: {e}"

        logger.info(
            "gdpr.erasure_complete",
            tenant=tenant_id,
            user_id=user_id,
            result=erased,
        )
        return erased

    async def get_storage_stats(self, tenant_id: str) -> dict:
        """Get storage usage per tier for a tenant."""
        stats: dict[str, dict] = {}

        table_configs = [
            ("logs.log_entries", "logs", "timestamp"),
            ("metrics.samples", "metrics", "timestamp"),
            ("traces.spans", "traces", "start_time"),
        ]

        for table, name, ts_col in table_configs:
            try:
                result = self.ch.query(
                    f"SELECT count() AS cnt, min({ts_col}) AS oldest, "
                    f"max({ts_col}) AS newest "
                    f"FROM {table} WHERE tenant_id = '{tenant_id}'"
                )
                row = result.result_rows[0] if result.result_rows else (0, None, None)
                stats[name] = {
                    "rows": row[0],
                    "oldest": str(row[1]),
                    "newest": str(row[2]),
                }
            except Exception:
                stats[name] = {"rows": 0}

        return stats
