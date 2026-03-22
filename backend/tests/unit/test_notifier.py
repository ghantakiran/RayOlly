"""Tests for rayolly.services.alerting.notifier — Notifier."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from rayolly.models.alerts import ChannelType, NotificationChannel
from rayolly.services.alerting.notifier import Notifier


@pytest.fixture
def notifier() -> Notifier:
    return Notifier()


def _channel(ctype: ChannelType, config: dict | None = None) -> NotificationChannel:
    return NotificationChannel(
        id=uuid4(),
        name=f"test-{ctype.value}",
        type=ctype,
        config=config or {},
    )


def _alert_data(status: str = "FIRING", severity: str = "critical") -> dict:
    return {
        "alert_id": "alert-001",
        "rule_name": "HighCPU",
        "summary": "CPU usage above 90%",
        "severity": severity,
        "status": status,
        "value": 95.2,
        "timestamp": 1700000000,
    }


# -----------------------------------------------------------------------
# Slack
# -----------------------------------------------------------------------

class TestSlack:
    @pytest.mark.asyncio
    async def test_send_slack(self, notifier: Notifier) -> None:
        channel = _channel(ChannelType.SLACK, {"webhook_url": "https://hooks.slack.com/test"})
        with patch.object(notifier._http_client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            result = await notifier.send(channel, _alert_data())
        assert result is True
        mock_post.assert_awaited_once()
        call_kwargs = mock_post.call_args
        assert "https://hooks.slack.com/test" in call_kwargs.args


# -----------------------------------------------------------------------
# Webhook
# -----------------------------------------------------------------------

class TestWebhook:
    @pytest.mark.asyncio
    async def test_send_webhook(self, notifier: Notifier) -> None:
        channel = _channel(ChannelType.WEBHOOK, {"url": "https://example.com/hook"})
        with patch.object(notifier._http_client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            result = await notifier.send(channel, _alert_data())
        assert result is True
        mock_post.assert_awaited_once()


# -----------------------------------------------------------------------
# PagerDuty
# -----------------------------------------------------------------------

class TestPagerDuty:
    @pytest.mark.asyncio
    async def test_send_pagerduty_trigger(self, notifier: Notifier) -> None:
        channel = _channel(ChannelType.PAGERDUTY, {"routing_key": "fake-key"})
        with patch.object(notifier._http_client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = MagicMock(status_code=202)
            result = await notifier.send(channel, _alert_data(status="FIRING"))
        assert result is True
        payload = mock_post.call_args.kwargs["json"]
        assert payload["event_action"] == "trigger"

    @pytest.mark.asyncio
    async def test_send_pagerduty_resolve(self, notifier: Notifier) -> None:
        channel = _channel(ChannelType.PAGERDUTY, {"routing_key": "fake-key"})
        with patch.object(notifier._http_client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = MagicMock(status_code=202)
            result = await notifier.send(channel, _alert_data(status="RESOLVED"))
        assert result is True
        payload = mock_post.call_args.kwargs["json"]
        assert payload["event_action"] == "resolve"


# -----------------------------------------------------------------------
# Unsupported / Failure
# -----------------------------------------------------------------------

class TestFailurePaths:
    @pytest.mark.asyncio
    async def test_unsupported_channel_returns_false(self, notifier: Notifier) -> None:
        # Manually override handlers to simulate unsupported
        channel = _channel(ChannelType.SLACK, {})
        notifier._handlers.clear()
        result = await notifier.send(channel, _alert_data())
        assert result is False

    @pytest.mark.asyncio
    async def test_send_failure_returns_false(self, notifier: Notifier) -> None:
        channel = _channel(ChannelType.SLACK, {"webhook_url": "https://hooks.slack.com/test"})
        with patch.object(
            notifier._http_client, "post", new_callable=AsyncMock,
            side_effect=Exception("connection refused"),
        ):
            result = await notifier.send(channel, _alert_data())
        assert result is False


# -----------------------------------------------------------------------
# Severity color mapping
# -----------------------------------------------------------------------

class TestSeverityColorMapping:
    @pytest.mark.asyncio
    async def test_severity_color_mapping(self, notifier: Notifier) -> None:
        channel = _channel(ChannelType.SLACK, {"webhook_url": "https://hooks.slack.com/test"})
        for severity in ("critical", "high", "medium", "low", "info"):
            with patch.object(notifier._http_client, "post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = MagicMock(status_code=200)
                await notifier.send(channel, _alert_data(severity=severity))
                payload = mock_post.call_args.kwargs["json"]
                color = payload["attachments"][0]["color"]
                assert color.startswith("#")
