"""Alert notification dispatcher — sends alerts to configured channels."""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from rayolly.models.alerts import ChannelType, NotificationChannel

logger = structlog.get_logger(__name__)


class Notifier:
    """Dispatches alert notifications to configured channels."""

    def __init__(self) -> None:
        self._http_client = httpx.AsyncClient(timeout=30)
        self._handlers: dict[ChannelType, Any] = {
            ChannelType.SLACK: self._send_slack,
            ChannelType.WEBHOOK: self._send_webhook,
            ChannelType.PAGERDUTY: self._send_pagerduty,
            ChannelType.EMAIL: self._send_email,
            ChannelType.OPSGENIE: self._send_opsgenie,
            ChannelType.TEAMS: self._send_teams,
        }

    async def send(
        self,
        channel: NotificationChannel,
        alert_data: dict,
    ) -> bool:
        handler = self._handlers.get(channel.type)
        if not handler:
            logger.warning("unsupported_channel_type", type=channel.type)
            return False

        try:
            await handler(channel, alert_data)
            logger.info(
                "notification_sent",
                channel=channel.name,
                type=channel.type,
                alert_id=alert_data.get("alert_id"),
            )
            return True
        except Exception as e:
            logger.error(
                "notification_failed",
                channel=channel.name,
                type=channel.type,
                error=str(e),
            )
            return False

    async def _send_slack(self, channel: NotificationChannel, alert_data: dict) -> None:
        webhook_url = channel.config.get("webhook_url")
        if not webhook_url:
            raise ValueError("Slack webhook_url not configured")

        severity = alert_data.get("severity", "info")
        color_map = {
            "critical": "#FF0000",
            "high": "#FF6600",
            "medium": "#FFCC00",
            "low": "#00CC00",
            "info": "#0066FF",
        }

        payload = {
            "attachments": [
                {
                    "color": color_map.get(severity, "#808080"),
                    "title": f"[{alert_data.get('status', 'FIRING').upper()}] {alert_data.get('rule_name', 'Alert')}",
                    "text": alert_data.get("summary", ""),
                    "fields": [
                        {"title": "Severity", "value": severity, "short": True},
                        {"title": "Value", "value": str(alert_data.get("value", "")), "short": True},
                    ],
                    "footer": "RayOlly Alerting",
                    "ts": alert_data.get("timestamp", ""),
                }
            ]
        }

        await self._http_client.post(webhook_url, json=payload)

    async def _send_webhook(self, channel: NotificationChannel, alert_data: dict) -> None:
        url = channel.config.get("url")
        if not url:
            raise ValueError("Webhook URL not configured")

        headers = channel.config.get("headers", {})
        await self._http_client.post(url, json=alert_data, headers=headers)

    async def _send_pagerduty(self, channel: NotificationChannel, alert_data: dict) -> None:
        routing_key = channel.config.get("routing_key")
        if not routing_key:
            raise ValueError("PagerDuty routing_key not configured")

        event_action = "trigger" if alert_data.get("status") == "FIRING" else "resolve"

        payload = {
            "routing_key": routing_key,
            "event_action": event_action,
            "dedup_key": alert_data.get("alert_id", ""),
            "payload": {
                "summary": f"{alert_data.get('rule_name', 'Alert')}: {alert_data.get('summary', '')}",
                "severity": alert_data.get("severity", "warning"),
                "source": "rayolly",
                "custom_details": alert_data,
            },
        }

        await self._http_client.post(
            "https://events.pagerduty.com/v2/enqueue",
            json=payload,
        )

    async def _send_email(self, channel: NotificationChannel, alert_data: dict) -> None:
        # TODO: Implement email sending via SMTP or SES
        logger.info("email_notification_stub", to=channel.config.get("to"))

    async def _send_opsgenie(self, channel: NotificationChannel, alert_data: dict) -> None:
        api_key = channel.config.get("api_key")
        if not api_key:
            raise ValueError("OpsGenie api_key not configured")

        payload = {
            "message": f"{alert_data.get('rule_name', 'Alert')}",
            "description": alert_data.get("summary", ""),
            "priority": self._map_severity_to_opsgenie(alert_data.get("severity", "medium")),
            "alias": alert_data.get("alert_id", ""),
        }

        await self._http_client.post(
            "https://api.opsgenie.com/v2/alerts",
            json=payload,
            headers={"Authorization": f"GenieKey {api_key}"},
        )

    async def _send_teams(self, channel: NotificationChannel, alert_data: dict) -> None:
        webhook_url = channel.config.get("webhook_url")
        if not webhook_url:
            raise ValueError("Teams webhook_url not configured")

        payload = {
            "@type": "MessageCard",
            "summary": alert_data.get("rule_name", "Alert"),
            "themeColor": "FF0000" if alert_data.get("status") == "FIRING" else "00CC00",
            "title": f"[{alert_data.get('status', 'FIRING')}] {alert_data.get('rule_name', 'Alert')}",
            "sections": [
                {
                    "facts": [
                        {"name": "Severity", "value": alert_data.get("severity", "")},
                        {"name": "Value", "value": str(alert_data.get("value", ""))},
                    ],
                    "text": alert_data.get("summary", ""),
                }
            ],
        }

        await self._http_client.post(webhook_url, json=payload)

    @staticmethod
    def _map_severity_to_opsgenie(severity: str) -> str:
        mapping = {
            "critical": "P1",
            "high": "P2",
            "medium": "P3",
            "low": "P4",
            "info": "P5",
        }
        return mapping.get(severity, "P3")

    async def close(self) -> None:
        await self._http_client.aclose()
