"""Audit logger that writes admin/write actions to ClickHouse events table.

Usage::

    audit = AuditLogger(clickhouse_client)
    audit.log(
        tenant_id="acme",
        user_id="user-uuid",
        action="create",
        resource_type="alert_rule",
        resource_id="rule-uuid",
        details={"name": "High Error Rate"},
    )
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class AuditLogger:
    """Write audit events to the ClickHouse ``events.events`` table.

    Gracefully degrades (logs a warning) if ClickHouse is unavailable.
    """

    def __init__(self, clickhouse_client) -> None:
        self.ch = clickhouse_client

    def log(
        self,
        tenant_id: str,
        user_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Insert an audit event into ClickHouse.

        Args:
            tenant_id: The tenant that owns the resource.
            user_id: ID of the user performing the action.
            action: Action verb (create, update, delete, login, etc.).
            resource_type: Kind of resource (alert_rule, api_key, user, etc.).
            resource_id: ID of the affected resource.
            details: Optional JSON-serialisable dict with additional context.
        """
        if self.ch is None:
            logger.debug(
                "audit_log_skipped_no_clickhouse",
                action=action,
                resource_type=resource_type,
            )
            return

        now = datetime.now(UTC)
        event_id = str(uuid.uuid4())
        detail_str = ""
        if details:
            import json
            try:
                detail_str = json.dumps(details)
            except (TypeError, ValueError):
                detail_str = str(details)

        try:
            self.ch.command(
                "INSERT INTO events.events "
                "(event_id, tenant_id, event_type, timestamp, source, severity, body) "
                "VALUES "
                "({event_id:String}, {tenant_id:String}, {event_type:String}, "
                "{timestamp:DateTime64(3)}, {source:String}, {severity:String}, {body:String})",
                parameters={
                    "event_id": event_id,
                    "tenant_id": tenant_id,
                    "event_type": "audit",
                    "timestamp": now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                    "source": f"user:{user_id}",
                    "severity": "info",
                    "body": f"action={action} resource_type={resource_type} "
                            f"resource_id={resource_id} {detail_str}".strip(),
                },
            )
        except Exception as e:
            # Never let audit logging break the request
            logger.warning(
                "audit_log_write_failed",
                error=str(e),
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
            )
