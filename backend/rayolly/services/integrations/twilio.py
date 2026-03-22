"""Twilio integration for voice, SMS, and WhatsApp alerting."""

from __future__ import annotations

import asyncio
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

_TWILIO_API = "https://api.twilio.com/2010-04-01"
_TIMEOUT = 20.0
_MAX_RETRIES = 3
_ESCALATION_WAIT_SECONDS = 300  # 5 minutes


class TwilioIntegration(BaseIntegration):
    """Twilio integration for multi-channel alerting (SMS, voice, WhatsApp)."""

    name = "twilio"
    category = IntegrationCategory.COMMUNICATION
    description = "Twilio – SMS, voice calls, and WhatsApp alerting"
    icon_url = "/icons/integrations/twilio.svg"
    docs_url = "https://docs.rayolly.io/integrations/twilio"
    capabilities = ["send_sms", "make_voice_call", "send_whatsapp", "escalate"]
    config_schema: dict[str, Any] = {
        "type": "object",
        "required": ["account_sid", "auth_token", "from_phone_number"],
        "properties": {
            "account_sid": {"type": "string", "title": "Account SID"},
            "auth_token": {"type": "string", "title": "Auth Token", "format": "password"},
            "from_phone_number": {
                "type": "string",
                "title": "From Phone Number",
                "description": "Twilio phone number in E.164 format",
            },
            "escalation_phones": {
                "type": "array",
                "title": "Escalation Phone Numbers",
                "items": {"type": "string"},
                "description": "Ordered list of numbers to escalate through",
            },
        },
    }

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _auth(config: dict[str, Any]) -> httpx.BasicAuth:
        return httpx.BasicAuth(username=config["account_sid"], password=config["auth_token"])

    def _account_url(self, config: dict[str, Any]) -> str:
        return f"{_TWILIO_API}/Accounts/{config['account_sid']}"

    async def _post(
        self,
        config: dict[str, Any],
        path: str,
        data: dict[str, str],
    ) -> dict[str, Any]:
        url = f"{self._account_url(config)}{path}"
        auth = self._auth(config)

        last_exc: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                    resp = await client.post(url, data=data, auth=auth)
                    resp.raise_for_status()
                    return resp.json()
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                last_exc = exc
                logger.warning("Twilio request %s attempt %d/%d failed: %s", path, attempt, _MAX_RETRIES, exc)
        raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------
    # BaseIntegration interface
    # ------------------------------------------------------------------

    async def test_connection(self, config: dict[str, Any]) -> bool:
        """Verify the Twilio account credentials."""
        try:
            url = f"{self._account_url(config)}.json"
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(url, auth=self._auth(config))
                resp.raise_for_status()
            return True
        except Exception as exc:
            logger.error("Twilio connection test failed: %s", exc)
            return False

    async def sync(self, instance: IntegrationInstance) -> SyncResult:
        """Twilio does not require periodic sync – always returns success."""
        return SyncResult(success=True, items_synced=0)

    async def execute_action(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        config = params.get("config", {})
        dispatchers: dict[str, Any] = {
            "send_sms": lambda: self.send_sms(config, params["to_number"], params.get("message", "")),
            "make_voice_call": lambda: self.make_voice_call(config, params["to_number"], params.get("alert_data", {})),
            "send_whatsapp": lambda: self.send_whatsapp(config, params["to_number"], params.get("message", "")),
            "escalate": lambda: self.escalate(config, params.get("alert_data", {})),
        }
        handler = dispatchers.get(action)
        if handler is None:
            raise ValueError(f"Unknown Twilio action: {action}")
        return await handler()

    # ------------------------------------------------------------------
    # SMS
    # ------------------------------------------------------------------

    async def send_sms(
        self, config: dict[str, Any], to_number: str, message: str
    ) -> dict[str, Any]:
        """Send an SMS alert via Twilio."""
        if not message:
            raise ValueError("Message body is required")

        data = {
            "To": to_number,
            "From": config["from_phone_number"],
            "Body": message[:1600],  # Twilio allows multi-segment; truncate at a safe max
        }
        resp = await self._post(config, "/Messages.json", data)
        logger.info("Sent SMS to %s – SID %s", to_number, resp.get("sid"))
        return {"sid": resp.get("sid"), "status": resp.get("status")}

    # ------------------------------------------------------------------
    # Voice
    # ------------------------------------------------------------------

    async def make_voice_call(
        self, config: dict[str, Any], to_number: str, alert_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Initiate a voice call that reads alert details via TwiML."""
        twiml = self._generate_twiml(alert_data)
        data = {
            "To": to_number,
            "From": config["from_phone_number"],
            "Twiml": twiml,
        }
        resp = await self._post(config, "/Calls.json", data)
        logger.info("Initiated voice call to %s – SID %s", to_number, resp.get("sid"))
        return {"sid": resp.get("sid"), "status": resp.get("status")}

    # ------------------------------------------------------------------
    # WhatsApp
    # ------------------------------------------------------------------

    async def send_whatsapp(
        self, config: dict[str, Any], to_number: str, message: str
    ) -> dict[str, Any]:
        """Send a WhatsApp message via Twilio."""
        data = {
            "To": f"whatsapp:{to_number}",
            "From": f"whatsapp:{config['from_phone_number']}",
            "Body": message[:1600],
        }
        resp = await self._post(config, "/Messages.json", data)
        logger.info("Sent WhatsApp to %s – SID %s", to_number, resp.get("sid"))
        return {"sid": resp.get("sid"), "status": resp.get("status")}

    # ------------------------------------------------------------------
    # Escalation
    # ------------------------------------------------------------------

    async def escalate(
        self, config: dict[str, Any], alert_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Escalate an alert through SMS first, then voice calls through the phone list."""
        phones: list[str] = config.get("escalation_phones", [])
        if not phones:
            raise ValueError("No escalation phone numbers configured")

        sms_text = self._format_sms(alert_data)
        results: list[dict[str, Any]] = []

        for phone in phones:
            # Try SMS
            sms_result = await self.send_sms(config, phone, sms_text)
            results.append({"phone": phone, "channel": "sms", **sms_result})

            # Wait for acknowledgment window
            logger.info("Waiting %ds for SMS acknowledgment from %s", _ESCALATION_WAIT_SECONDS, phone)
            await asyncio.sleep(_ESCALATION_WAIT_SECONDS)

            # TODO: Check acknowledgment status via callback/webhook
            # For now, escalate to voice call
            try:
                call_result = await self.make_voice_call(config, phone, alert_data)
                results.append({"phone": phone, "channel": "voice", **call_result})
            except Exception as exc:
                logger.warning("Voice call to %s failed: %s", phone, exc)
                results.append({"phone": phone, "channel": "voice", "error": str(exc)})

        return {"escalation_results": results}

    # ------------------------------------------------------------------
    # Formatters
    # ------------------------------------------------------------------

    @staticmethod
    def _format_sms(alert_data: dict[str, Any]) -> str:
        """Format alert data into a concise SMS (target < 160 chars for single segment)."""
        severity = alert_data.get("severity", "WARN").upper()
        service = alert_data.get("service", "Unknown")
        summary = alert_data.get("summary", "Alert triggered")
        url = alert_data.get("rayolly_url", "")

        # Build concise message
        msg = f"[{severity}] {service}: {summary}"
        if url:
            # Reserve space for URL
            max_text = 160 - len(url) - 3  # 3 for " | "
            if len(msg) > max_text:
                msg = msg[: max_text - 1] + "\u2026"
            msg = f"{msg} | {url}"
        elif len(msg) > 160:
            msg = msg[:159] + "\u2026"
        return msg

    @staticmethod
    def _generate_twiml(alert_data: dict[str, Any]) -> str:
        """Generate TwiML for a voice alert with press-1-to-acknowledge."""
        severity = alert_data.get("severity", "warning").upper()
        service = alert_data.get("service", "unknown service")
        summary = alert_data.get("summary", "An alert has been triggered")

        return (
            "<Response>"
            "<Gather numDigits=\"1\" action=\"/api/v1/integrations/twilio/ack\" method=\"POST\">"
            f"<Say voice=\"alice\">Attention. This is a RayOlly {severity} alert "
            f"for {service}. {summary}. "
            "Press 1 to acknowledge this alert.</Say>"
            "</Gather>"
            "<Say voice=\"alice\">No input received. Escalating to next contact.</Say>"
            "</Response>"
        )
