"""Alert rule evaluator — periodically checks alert conditions."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import structlog

from rayolly.models.alerts import (
    Alert,
    AlertRule,
    AlertStatus,
)

logger = structlog.get_logger(__name__)


class AlertEvaluator:
    """Evaluates alert rules against current data and fires/resolves alerts."""

    def __init__(
        self,
        clickhouse_client: Any,
        redis_client: Any,
        nats_client: Any,
    ) -> None:
        self.clickhouse = clickhouse_client
        self.redis = redis_client
        self.nats = nats_client
        self._running = False
        self._active_alerts: dict[str, Alert] = {}

    async def start(self) -> None:
        """Start the alert evaluation loop."""
        self._running = True
        logger.info("alert_evaluator_started")

        while self._running:
            try:
                rules = await self._load_rules()
                for rule in rules:
                    if rule.enabled:
                        await self._evaluate_rule(rule)
            except Exception as e:
                logger.error("alert_evaluation_error", error=str(e))

            await asyncio.sleep(30)  # Default evaluation interval

    async def stop(self) -> None:
        self._running = False
        logger.info("alert_evaluator_stopped")

    async def _load_rules(self) -> list[AlertRule]:
        """Load active alert rules from metadata store."""
        # TODO: Load from PostgreSQL metadata DB
        return []

    async def _evaluate_rule(self, rule: AlertRule) -> None:
        """Evaluate a single alert rule."""
        log = logger.bind(rule_id=rule.id, rule_name=rule.name)

        try:
            result = self.clickhouse.query(rule.query)

            if not result.result_rows:
                await self._maybe_resolve(rule)
                return

            # Check condition
            for row in result.result_rows:
                value = float(row[0]) if row else 0
                should_fire = self._check_condition(value, rule)

                if should_fire:
                    await self._fire_alert(rule, value)
                else:
                    await self._maybe_resolve(rule)

        except Exception as e:
            log.error("rule_evaluation_failed", error=str(e))

    def _check_condition(self, value: float, rule: AlertRule) -> bool:
        """Check if value meets the alert condition."""
        condition = rule.condition
        match condition.operator:
            case "gt":
                return value > condition.threshold
            case "gte":
                return value >= condition.threshold
            case "lt":
                return value < condition.threshold
            case "lte":
                return value <= condition.threshold
            case "eq":
                return value == condition.threshold
            case "neq":
                return value != condition.threshold
            case _:
                return False

    async def _fire_alert(self, rule: AlertRule, value: float) -> None:
        """Fire an alert if not already active."""
        if rule.id in self._active_alerts:
            return  # Already firing

        alert = Alert(
            id=f"alert_{uuid4().hex[:12]}",
            rule_id=rule.id,
            status=AlertStatus.FIRING,
            value=value,
            started_at=datetime.now(UTC),
            labels=rule.labels,
            annotations={"summary": f"{rule.name}: value={value}"},
        )
        self._active_alerts[rule.id] = alert

        logger.info(
            "alert_fired",
            rule_id=rule.id,
            alert_id=alert.id,
            value=value,
            severity=rule.severity,
        )

        # Publish alert event to NATS for notification routing and agent triggering
        await self._publish_alert_event(alert, rule)

    async def _maybe_resolve(self, rule: AlertRule) -> None:
        """Resolve an alert if it was previously firing."""
        if rule.id not in self._active_alerts:
            return

        alert = self._active_alerts.pop(rule.id)
        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.now(UTC)

        logger.info("alert_resolved", rule_id=rule.id, alert_id=alert.id)
        await self._publish_alert_event(alert, rule)

    async def _publish_alert_event(self, alert: Alert, rule: AlertRule) -> None:
        """Publish alert event to NATS for downstream consumption."""
        import orjson

        event = {
            "type": "alert",
            "alert_id": alert.id,
            "rule_id": rule.id,
            "rule_name": rule.name,
            "status": alert.status,
            "severity": rule.severity,
            "value": alert.value,
            "started_at": alert.started_at.isoformat() if alert.started_at else None,
            "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
            "labels": alert.labels,
        }

        try:
            js = self.nats.jetstream()
            await js.publish(
                "rayolly.alerts.events",
                orjson.dumps(event),
            )
        except Exception as e:
            logger.error("alert_event_publish_error", error=str(e))
