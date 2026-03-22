"""Generic webhook integration for RayOlly."""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

import httpx

try:
    from jinja2 import Template
except ImportError:  # graceful fallback
    Template = None  # type: ignore[assignment,misc]

from datetime import UTC

from .registry import (
    BaseIntegration,
    IntegrationCategory,
    IntegrationInstance,
    SyncResult,
)

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3


class WebhookIntegration(BaseIntegration):
    """Generic outbound webhook integration with Jinja2 payload templating and HMAC signing."""

    name = "webhook"
    category = IntegrationCategory.CUSTOM
    description = "Generic Webhook – customisable outbound HTTP calls with templating"
    icon_url = "/icons/integrations/webhook.svg"
    docs_url = "https://docs.rayolly.io/integrations/webhook"
    capabilities = ["send"]
    config_schema: dict[str, Any] = {
        "type": "object",
        "required": ["url"],
        "properties": {
            "url": {"type": "string", "title": "Webhook URL"},
            "method": {
                "type": "string",
                "title": "HTTP Method",
                "enum": ["POST", "PUT"],
                "default": "POST",
            },
            "headers": {
                "type": "object",
                "title": "Custom Headers",
                "additionalProperties": {"type": "string"},
            },
            "auth_type": {
                "type": "string",
                "title": "Authentication Type",
                "enum": ["none", "bearer", "basic", "hmac"],
                "default": "none",
            },
            "auth_value": {
                "type": "string",
                "title": "Auth Value",
                "description": "Bearer token, basic credentials (user:pass), or HMAC secret",
                "format": "password",
            },
            "payload_template": {
                "type": "string",
                "title": "Payload Template",
                "description": "Jinja2 template for the JSON body. Variables: event, alert, timestamp",
            },
            "retry_count": {
                "type": "integer",
                "title": "Retry Count",
                "default": 3,
                "minimum": 0,
                "maximum": 10,
            },
            "timeout_seconds": {
                "type": "number",
                "title": "Timeout (seconds)",
                "default": 30,
                "minimum": 1,
                "maximum": 120,
            },
        },
    }

    # ------------------------------------------------------------------
    # BaseIntegration interface
    # ------------------------------------------------------------------

    async def test_connection(self, config: dict[str, Any]) -> bool:
        """Send a test ping to the webhook URL."""
        try:
            headers = self._build_headers(config)
            timeout = config.get("timeout_seconds", 30)
            async with httpx.AsyncClient(timeout=float(timeout)) as client:
                resp = await client.request(
                    config.get("method", "POST"),
                    config["url"],
                    headers=headers,
                    json={"event": "test", "source": "rayolly"},
                )
                # Accept 2xx and 3xx as success (some webhooks return 301/302)
                return resp.status_code < 400
        except Exception as exc:
            logger.error("Webhook connection test failed: %s", exc)
            return False

    async def sync(self, instance: IntegrationInstance) -> SyncResult:
        """Webhooks do not sync."""
        return SyncResult(success=True, items_synced=0)

    async def execute_action(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        config = params.get("config", {})
        if action != "send":
            raise ValueError(f"Unknown webhook action: {action}")
        return await self.send(config, params.get("event_data", {}))

    # ------------------------------------------------------------------
    # Core send
    # ------------------------------------------------------------------

    async def send(
        self, config: dict[str, Any], event_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Send the webhook with optional template rendering and HMAC signing."""
        method = config.get("method", "POST")
        url = config["url"]
        headers = self._build_headers(config)
        timeout = float(config.get("timeout_seconds", 30))
        retries = config.get("retry_count", _MAX_RETRIES)

        # Render payload
        template_str = config.get("payload_template")
        if template_str:
            body_str = self._render_payload(template_str, event_data)
            headers.setdefault("Content-Type", "application/json")
        else:
            import json

            body_str = json.dumps(event_data)
            headers.setdefault("Content-Type", "application/json")

        # HMAC signing
        if config.get("auth_type") == "hmac" and config.get("auth_value"):
            signature = self._sign_payload(body_str, config["auth_value"])
            headers["X-Signature-256"] = f"sha256={signature}"

        last_exc: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.request(method, url, headers=headers, content=body_str.encode())
                    resp.raise_for_status()
                    logger.info("Webhook sent to %s – status %d", url, resp.status_code)
                    return {
                        "status_code": resp.status_code,
                        "response_body": resp.text[:500],
                    }
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                last_exc = exc
                logger.warning("Webhook %s %s attempt %d/%d failed: %s", method, url, attempt, retries, exc)
        raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_headers(config: dict[str, Any]) -> dict[str, str]:
        """Build request headers including authentication."""
        headers: dict[str, str] = dict(config.get("headers", {}))

        auth_type = config.get("auth_type", "none")
        auth_value = config.get("auth_value", "")

        if auth_type == "bearer" and auth_value:
            headers["Authorization"] = f"Bearer {auth_value}"
        elif auth_type == "basic" and auth_value:
            import base64

            encoded = base64.b64encode(auth_value.encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"
        # hmac is handled via X-Signature-256 in send()

        return headers

    @staticmethod
    def _render_payload(template_str: str, data: dict[str, Any]) -> str:
        """Render a Jinja2 payload template with event data."""
        if Template is None:
            raise RuntimeError("jinja2 is required for payload templating – install it with: pip install jinja2")

        from datetime import datetime

        tmpl = Template(template_str)
        return tmpl.render(
            event=data,
            alert=data.get("alert", data),
            timestamp=datetime.now(UTC).isoformat(),
        )

    @staticmethod
    def _sign_payload(payload: str, secret: str) -> str:
        """Compute HMAC-SHA256 signature for webhook verification."""
        return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
