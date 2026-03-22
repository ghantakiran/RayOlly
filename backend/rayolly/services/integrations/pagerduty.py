"""PagerDuty integration for RayOlly incident management."""

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

_EVENTS_API = "https://events.pagerduty.com/v2/enqueue"
_REST_API = "https://api.pagerduty.com"
_TIMEOUT = 15.0
_MAX_RETRIES = 3

_SEVERITY_MAP: dict[str, str] = {
    "critical": "critical",
    "high": "error",
    "warning": "warning",
    "medium": "warning",
    "low": "info",
    "info": "info",
}


class PagerDutyIntegration(BaseIntegration):
    """PagerDuty integration for triggering, acknowledging, and resolving incidents."""

    name = "pagerduty"
    category = IntegrationCategory.COMMUNICATION
    description = "PagerDuty – incident triggering, on-call schedules, and escalation"
    icon_url = "/icons/integrations/pagerduty.svg"
    docs_url = "https://docs.rayolly.io/integrations/pagerduty"
    capabilities = [
        "trigger_incident",
        "resolve_incident",
        "acknowledge_incident",
        "get_oncall",
        "sync_oncall",
    ]
    config_schema: dict[str, Any] = {
        "type": "object",
        "required": ["api_key", "routing_key"],
        "properties": {
            "api_key": {
                "type": "string",
                "title": "REST API Key",
                "format": "password",
            },
            "service_id": {"type": "string", "title": "Service ID"},
            "routing_key": {
                "type": "string",
                "title": "Events API Routing Key",
                "description": "Integration key for the Events API v2",
            },
            "escalation_policy_id": {"type": "string", "title": "Escalation Policy ID"},
        },
    }

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    async def _events_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Send a request to the PagerDuty Events API v2."""
        last_exc: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                    resp = await client.post(_EVENTS_API, json=payload)
                    resp.raise_for_status()
                    return resp.json()
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                last_exc = exc
                logger.warning("PagerDuty Events API attempt %d/%d failed: %s", attempt, _MAX_RETRIES, exc)
        raise last_exc  # type: ignore[misc]

    async def _rest_request(
        self,
        method: str,
        config: dict[str, Any],
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Call the PagerDuty REST API with retries."""
        url = f"{_REST_API}{path}"
        headers = {
            "Authorization": f"Token token={config['api_key']}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.pagerduty+json;version=2",
        }

        last_exc: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                    resp = await client.request(method, url, headers=headers, json=json_body, params=params)
                    resp.raise_for_status()
                    return resp.json()
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                last_exc = exc
                logger.warning("PagerDuty REST %s %s attempt %d/%d failed: %s", method, path, attempt, _MAX_RETRIES, exc)
        raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------
    # BaseIntegration interface
    # ------------------------------------------------------------------

    async def test_connection(self, config: dict[str, Any]) -> bool:
        """Verify API key by listing abilities."""
        try:
            await self._rest_request("GET", config, "/abilities")
            return True
        except Exception as exc:
            logger.error("PagerDuty connection test failed: %s", exc)
            return False

    async def sync(self, instance: IntegrationInstance) -> SyncResult:
        """Sync on-call schedules from PagerDuty."""
        try:
            result = await self.sync_oncall(instance.config)
            users = result.get("users", [])
            return SyncResult(success=True, items_synced=len(users))
        except Exception as exc:
            logger.exception("PagerDuty sync failed")
            return SyncResult(success=False, errors=[str(exc)])

    async def execute_action(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        config = params.get("config", {})
        dispatchers: dict[str, Any] = {
            "trigger_incident": lambda: self.trigger_incident(config, params.get("alert_data", {})),
            "resolve_incident": lambda: self.resolve_incident(config, params["dedup_key"]),
            "acknowledge_incident": lambda: self.acknowledge_incident(config, params["dedup_key"]),
            "get_oncall": lambda: self.get_oncall(config),
            "sync_oncall": lambda: self.sync_oncall(config),
        }
        handler = dispatchers.get(action)
        if handler is None:
            raise ValueError(f"Unknown PagerDuty action: {action}")
        return await handler()

    # ------------------------------------------------------------------
    # Incident operations
    # ------------------------------------------------------------------

    async def trigger_incident(
        self, config: dict[str, Any], alert_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Trigger a PagerDuty incident via Events API v2."""
        severity = alert_data.get("severity", "warning")
        pd_severity = _SEVERITY_MAP.get(severity.lower(), "warning")

        payload = {
            "routing_key": config["routing_key"],
            "event_action": "trigger",
            "dedup_key": alert_data.get("dedup_key", alert_data.get("id", "")),
            "payload": {
                "summary": f"[RayOlly] {alert_data.get('service', 'Unknown')}: {alert_data.get('summary', 'Alert')}",
                "severity": pd_severity,
                "source": alert_data.get("service", "rayolly"),
                "component": alert_data.get("component", ""),
                "group": alert_data.get("group", ""),
                "class": alert_data.get("alert_type", ""),
                "custom_details": {
                    "rayolly_alert_id": alert_data.get("id", ""),
                    "rayolly_url": alert_data.get("rayolly_url", ""),
                    "rca_summary": alert_data.get("rca_summary", ""),
                },
            },
            "links": [
                {
                    "href": alert_data.get("rayolly_url", "https://app.rayolly.io"),
                    "text": "View in RayOlly",
                }
            ],
        }

        resp = await self._events_request(payload)
        logger.info("Triggered PagerDuty incident – dedup_key=%s", payload["dedup_key"])
        return {
            "status": resp.get("status"),
            "dedup_key": resp.get("dedup_key"),
            "message": resp.get("message"),
        }

    async def resolve_incident(
        self, config: dict[str, Any], dedup_key: str
    ) -> dict[str, Any]:
        """Resolve a PagerDuty incident."""
        payload = {
            "routing_key": config["routing_key"],
            "event_action": "resolve",
            "dedup_key": dedup_key,
        }
        resp = await self._events_request(payload)
        logger.info("Resolved PagerDuty incident – dedup_key=%s", dedup_key)
        return {"status": resp.get("status"), "dedup_key": dedup_key}

    async def acknowledge_incident(
        self, config: dict[str, Any], dedup_key: str
    ) -> dict[str, Any]:
        """Acknowledge a PagerDuty incident."""
        payload = {
            "routing_key": config["routing_key"],
            "event_action": "acknowledge",
            "dedup_key": dedup_key,
        }
        resp = await self._events_request(payload)
        logger.info("Acknowledged PagerDuty incident – dedup_key=%s", dedup_key)
        return {"status": resp.get("status"), "dedup_key": dedup_key}

    # ------------------------------------------------------------------
    # On-call
    # ------------------------------------------------------------------

    async def get_oncall(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        """Get current on-call users from PagerDuty."""
        params: dict[str, str] = {}
        if config.get("escalation_policy_id"):
            params["escalation_policy_ids[]"] = config["escalation_policy_id"]

        resp = await self._rest_request("GET", config, "/oncalls", params=params)
        oncalls = resp.get("oncalls", [])

        users: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for entry in oncalls:
            user = entry.get("user", {})
            uid = user.get("id", "")
            if uid and uid not in seen_ids:
                seen_ids.add(uid)
                users.append({
                    "id": uid,
                    "name": user.get("summary", ""),
                    "email": user.get("email", ""),
                    "escalation_level": entry.get("escalation_level"),
                })
        return users

    async def sync_oncall(self, config: dict[str, Any]) -> dict[str, Any]:
        """Sync on-call schedules to RayOlly."""
        users = await self.get_oncall(config)
        logger.info("Synced %d on-call users from PagerDuty", len(users))
        return {"users": users, "count": len(users)}
