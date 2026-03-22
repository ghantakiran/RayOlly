"""Enhanced Slack integration for RayOlly – rich alerting with Block Kit."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .registry import (
    BaseIntegration,
    IntegrationCategory,
    IntegrationInstance,
    SyncResult,
)

logger = logging.getLogger(__name__)

_SLACK_API = "https://slack.com/api"
_TIMEOUT = 15.0
_MAX_RETRIES = 3

_SEVERITY_COLORS: dict[str, str] = {
    "critical": "#FF0000",
    "high": "#FF6600",
    "warning": "#FFCC00",
    "medium": "#FFCC00",
    "low": "#36A64F",
    "info": "#2196F3",
}


class SlackIntegration(BaseIntegration):
    """Rich Slack integration with Block Kit messages, interactive actions, and incident channels."""

    name = "slack"
    category = IntegrationCategory.COMMUNICATION
    description = "Slack – rich alerts, interactive actions, and incident channels"
    icon_url = "/icons/integrations/slack.svg"
    docs_url = "https://docs.rayolly.io/integrations/slack"
    capabilities = [
        "send_alert",
        "interactive_actions",
        "slash_commands",
        "thread_updates",
        "post_rca_report",
        "create_incident_channel",
    ]
    config_schema: dict[str, Any] = {
        "type": "object",
        "required": ["bot_token"],
        "properties": {
            "bot_token": {
                "type": "string",
                "title": "Bot Token",
                "description": "Slack Bot User OAuth Token (xoxb-...)",
                "format": "password",
            },
            "app_token": {
                "type": "string",
                "title": "App-Level Token",
                "description": "For Socket Mode (xapp-...)",
                "format": "password",
            },
            "default_channel": {
                "type": "string",
                "title": "Default Channel",
                "description": "Channel ID for general alerts",
            },
            "incident_channel": {
                "type": "string",
                "title": "Incident Channel",
                "description": "Channel ID for incident notifications",
            },
        },
    }

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    async def _api(
        self,
        config: dict[str, Any],
        method: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Call the Slack Web API with retries."""
        url = f"{_SLACK_API}/{method}"
        headers = {
            "Authorization": f"Bearer {config['bot_token']}",
            "Content-Type": "application/json; charset=utf-8",
        }

        last_exc: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                    resp = await client.post(url, headers=headers, json=json_body or {}, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                    if not data.get("ok"):
                        error = data.get("error", "unknown_error")
                        raise RuntimeError(f"Slack API error: {error}")
                    return data
            except (httpx.HTTPStatusError, httpx.TransportError, RuntimeError) as exc:
                last_exc = exc
                logger.warning("Slack %s attempt %d/%d failed: %s", method, attempt, _MAX_RETRIES, exc)
        raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------
    # BaseIntegration interface
    # ------------------------------------------------------------------

    async def test_connection(self, config: dict[str, Any]) -> bool:
        """Test the bot token by calling auth.test."""
        try:
            await self._api(config, "auth.test")
            return True
        except Exception as exc:
            logger.error("Slack connection test failed: %s", exc)
            return False

    async def sync(self, instance: IntegrationInstance) -> SyncResult:
        """Slack does not require periodic sync."""
        return SyncResult(success=True, items_synced=0)

    async def execute_action(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        config = params.get("config", {})
        dispatchers: dict[str, Any] = {
            "send_alert": lambda: self.send_alert(
                config,
                params.get("channel", config.get("default_channel", "")),
                params.get("alert_data", {}),
            ),
            "send_incident_update": lambda: self.send_incident_update(
                config,
                params.get("channel", config.get("incident_channel", "")),
                params.get("incident_data", {}),
                params.get("thread_ts"),
            ),
            "handle_interaction": lambda: self.handle_interaction(params.get("payload", {})),
            "post_rca_report": lambda: self.post_rca_report(
                config,
                params.get("channel", config.get("default_channel", "")),
                params.get("rca_report", {}),
            ),
            "create_incident_channel": lambda: self.create_incident_channel(
                config, params.get("incident_id", "unknown"),
            ),
        }
        handler = dispatchers.get(action)
        if handler is None:
            raise ValueError(f"Unknown Slack action: {action}")
        return await handler()

    # ------------------------------------------------------------------
    # Alert messaging
    # ------------------------------------------------------------------

    async def send_alert(
        self, config: dict[str, Any], channel: str, alert_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Send a rich Block Kit alert message."""
        blocks = self._build_alert_blocks(alert_data)
        severity = alert_data.get("severity", "info")
        color = _SEVERITY_COLORS.get(severity.lower(), "#CCCCCC")

        payload: dict[str, Any] = {
            "channel": channel,
            "text": f"[{severity.upper()}] {alert_data.get('service', 'Unknown')}: {alert_data.get('summary', '')}",
            "attachments": [{"color": color, "blocks": blocks}],
        }
        resp = await self._api(config, "chat.postMessage", json_body=payload)
        return {"ts": resp.get("ts"), "channel": resp.get("channel")}

    async def send_incident_update(
        self,
        config: dict[str, Any],
        channel: str,
        incident_data: dict[str, Any],
        thread_ts: str | None = None,
    ) -> dict[str, Any]:
        """Post a threaded incident update."""
        status = incident_data.get("status", "update")
        text = f"*Incident Update* – {status}\n{incident_data.get('message', '')}"

        payload: dict[str, Any] = {
            "channel": channel,
            "text": text,
        }
        if thread_ts:
            payload["thread_ts"] = thread_ts

        resp = await self._api(config, "chat.postMessage", json_body=payload)
        return {"ts": resp.get("ts"), "channel": resp.get("channel")}

    # ------------------------------------------------------------------
    # Interactive actions
    # ------------------------------------------------------------------

    async def handle_interaction(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Handle a Slack interactive component callback (button click, etc.)."""
        actions = payload.get("actions", [])
        if not actions:
            return {"handled": False, "reason": "no_actions"}

        action = actions[0]
        action_id = action.get("action_id", "")
        user = payload.get("user", {}).get("username", "unknown")

        logger.info("Slack interaction: user=%s action=%s", user, action_id)

        response_map: dict[str, dict[str, Any]] = {
            "acknowledge_alert": {"handled": True, "action": "acknowledge", "user": user},
            "silence_alert": {"handled": True, "action": "silence", "user": user},
            "escalate_alert": {"handled": True, "action": "escalate", "user": user},
            "invoke_ai_agent": {"handled": True, "action": "invoke_ai", "user": user},
        }

        result = response_map.get(action_id, {"handled": False, "reason": f"unknown_action:{action_id}"})
        return result

    # ------------------------------------------------------------------
    # RCA report
    # ------------------------------------------------------------------

    async def post_rca_report(
        self, config: dict[str, Any], channel: str, rca_report: dict[str, Any]
    ) -> dict[str, Any]:
        """Post a formatted Root-Cause Analysis report."""
        blocks = self._build_rca_blocks(rca_report)
        payload: dict[str, Any] = {
            "channel": channel,
            "text": f"RCA Report: {rca_report.get('title', 'Incident Analysis')}",
            "blocks": blocks,
        }
        resp = await self._api(config, "chat.postMessage", json_body=payload)
        return {"ts": resp.get("ts"), "channel": resp.get("channel")}

    # ------------------------------------------------------------------
    # Incident channel
    # ------------------------------------------------------------------

    async def create_incident_channel(
        self, config: dict[str, Any], incident_id: str
    ) -> dict[str, Any]:
        """Create a dedicated Slack channel for an incident."""
        channel_name = f"inc-{incident_id}".lower().replace(" ", "-")[:80]
        resp = await self._api(
            config,
            "conversations.create",
            json_body={"name": channel_name, "is_private": False},
        )
        channel_info = resp.get("channel", {})
        logger.info("Created incident channel #%s (%s)", channel_name, channel_info.get("id"))
        return {
            "channel_id": channel_info.get("id"),
            "channel_name": channel_name,
        }

    # ------------------------------------------------------------------
    # Block Kit builders
    # ------------------------------------------------------------------

    @staticmethod
    def _build_alert_blocks(alert_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Build Slack Block Kit blocks for a rich alert message."""
        severity = alert_data.get("severity", "info").upper()
        service = alert_data.get("service", "Unknown Service")
        summary = alert_data.get("summary", "No summary available")
        timestamp = alert_data.get("timestamp", "")
        alert_id = alert_data.get("id", "")

        blocks: list[dict[str, Any]] = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"\u26a0\ufe0f {severity} Alert – {service}", "emoji": True},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": summary},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Severity:*\n{severity}"},
                    {"type": "mrkdwn", "text": f"*Service:*\n{service}"},
                    {"type": "mrkdwn", "text": f"*Time:*\n{timestamp}"},
                    {"type": "mrkdwn", "text": f"*Alert ID:*\n`{alert_id}`"},
                ],
            },
            {"type": "divider"},
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Acknowledge"},
                        "style": "primary",
                        "action_id": "acknowledge_alert",
                        "value": alert_id,
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Silence"},
                        "action_id": "silence_alert",
                        "value": alert_id,
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Investigate"},
                        "style": "danger",
                        "action_id": "invoke_ai_agent",
                        "value": alert_id,
                    },
                ],
            },
        ]
        return blocks

    @staticmethod
    def _build_rca_blocks(rca_report: dict[str, Any]) -> list[dict[str, Any]]:
        """Build Slack Block Kit blocks for an RCA report."""
        title = rca_report.get("title", "Root-Cause Analysis")
        root_cause = rca_report.get("root_cause", "Under investigation")
        impact = rca_report.get("impact", "N/A")
        timeline = rca_report.get("timeline", "N/A")
        remediation = rca_report.get("remediation", "N/A")
        confidence = rca_report.get("confidence", "N/A")

        blocks: list[dict[str, Any]] = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"RCA: {title}", "emoji": True},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Root Cause:*\n{root_cause}"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Impact:*\n{impact}"},
                    {"type": "mrkdwn", "text": f"*Confidence:*\n{confidence}"},
                ],
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Timeline:*\n{timeline}"},
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Remediation:*\n{remediation}"},
            },
        ]
        return blocks
