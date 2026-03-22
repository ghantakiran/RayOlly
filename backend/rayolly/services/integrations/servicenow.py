"""ServiceNow ITSM integration for RayOlly."""

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

_MAX_RETRIES = 3
_TIMEOUT = 30.0


class ServiceNowIntegration(BaseIntegration):
    """Integrates RayOlly with ServiceNow for incident, change-request, and CMDB management."""

    name = "servicenow"
    category = IntegrationCategory.ITSM
    description = "ServiceNow ITSM – incidents, change requests, and CMDB sync"
    icon_url = "/icons/integrations/servicenow.svg"
    docs_url = "https://docs.rayolly.io/integrations/servicenow"
    capabilities = [
        "create_incident",
        "update_incident",
        "close_incident",
        "create_change_request",
        "sync_cmdb",
        "get_incident",
        "search_incidents",
    ]
    config_schema: dict[str, Any] = {
        "type": "object",
        "required": ["instance_url", "username", "password"],
        "properties": {
            "instance_url": {
                "type": "string",
                "title": "Instance URL",
                "description": "ServiceNow instance URL (e.g. https://mycompany.service-now.com)",
            },
            "username": {"type": "string", "title": "Username"},
            "password": {"type": "string", "title": "Password", "format": "password"},
            "client_id": {
                "type": "string",
                "title": "OAuth Client ID",
                "description": "Optional – used for OAuth2 authentication",
            },
            "client_secret": {
                "type": "string",
                "title": "OAuth Client Secret",
                "format": "password",
            },
        },
    }

    # ------------------------------------------------------------------
    # Severity mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _map_severity(rayolly_severity: str) -> tuple[int, int]:
        """Map RayOlly alert severity to ServiceNow (impact, urgency).

        ServiceNow uses 1 (High) → 3 (Low) for both fields.
        """
        mapping: dict[str, tuple[int, int]] = {
            "critical": (1, 1),
            "high": (1, 2),
            "warning": (2, 2),
            "medium": (2, 3),
            "low": (3, 3),
            "info": (3, 3),
        }
        return mapping.get(rayolly_severity.lower(), (2, 2))

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_headers(config: dict[str, Any]) -> dict[str, str]:
        """Return request headers. Uses basic auth (OAuth flow handled separately)."""
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _base_url(self, config: dict[str, Any]) -> str:
        return config["instance_url"].rstrip("/")

    def _auth(self, config: dict[str, Any]) -> httpx.BasicAuth:
        return httpx.BasicAuth(username=config["username"], password=config["password"])

    async def _request(
        self,
        method: str,
        config: dict[str, Any],
        path: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
    ) -> dict[str, Any]:
        """Execute an HTTP request with retries."""
        url = f"{self._base_url(config)}{path}"
        headers = self._build_headers(config)
        auth = self._auth(config)

        last_exc: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                    resp = await client.request(
                        method,
                        url,
                        headers=headers,
                        auth=auth,
                        json=json,
                        params=params,
                    )
                    resp.raise_for_status()
                    return resp.json()
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                last_exc = exc
                logger.warning(
                    "ServiceNow request %s %s attempt %d/%d failed: %s",
                    method,
                    path,
                    attempt,
                    _MAX_RETRIES,
                    exc,
                )
        raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------
    # BaseIntegration interface
    # ------------------------------------------------------------------

    async def test_connection(self, config: dict[str, Any]) -> bool:
        """Test ServiceNow connectivity by fetching the sys_user table."""
        try:
            await self._request(
                "GET",
                config,
                "/api/now/table/sys_user",
                params={"sysparm_limit": "1"},
            )
            return True
        except Exception as exc:
            logger.error("ServiceNow connection test failed: %s", exc)
            return False

    async def sync(self, instance: IntegrationInstance) -> SyncResult:
        """Sync CMDB configuration items from ServiceNow."""
        try:
            result = await self.sync_cmdb(instance.config, [])
            return result
        except Exception as exc:
            logger.exception("ServiceNow sync failed")
            return SyncResult(success=False, errors=[str(exc)])

    async def execute_action(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        """Dispatch to the appropriate ServiceNow action."""
        config = params.get("config", {})
        dispatchers: dict[str, Any] = {
            "create_incident": lambda: self.create_incident(config, params.get("incident_data", {})),
            "update_incident": lambda: self.update_incident(
                config, params["incident_number"], params.get("updates", {})
            ),
            "close_incident": lambda: self.close_incident(
                config, params["incident_number"], params.get("resolution_notes", "")
            ),
            "create_change_request": lambda: self.create_change_request(
                config, params.get("change_data", {})
            ),
            "get_incident": lambda: self.get_incident(config, params["incident_number"]),
            "search_incidents": lambda: self.search_incidents(config, params.get("query", "")),
        }
        handler = dispatchers.get(action)
        if handler is None:
            raise ValueError(f"Unknown ServiceNow action: {action}")
        return await handler()

    # ------------------------------------------------------------------
    # Incident operations
    # ------------------------------------------------------------------

    async def create_incident(
        self, config: dict[str, Any], incident_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Create a ServiceNow incident from RayOlly alert data.

        Returns a dict containing the ServiceNow incident ``number`` and ``sys_id``.
        """
        severity = incident_data.get("severity", "medium")
        impact, urgency = self._map_severity(severity)

        payload = {
            "short_description": incident_data.get(
                "title", "RayOlly Alert"
            ),
            "description": self._build_description(incident_data),
            "impact": str(impact),
            "urgency": str(urgency),
            "category": "Software",
            "subcategory": "Application",
            "caller_id": config.get("username", ""),
            "assignment_group": incident_data.get("assignment_group", ""),
        }

        resp = await self._request("POST", config, "/api/now/table/incident", json=payload)
        result = resp.get("result", {})
        logger.info("Created ServiceNow incident %s", result.get("number"))
        return {
            "number": result.get("number"),
            "sys_id": result.get("sys_id"),
            "state": result.get("state"),
        }

    async def update_incident(
        self,
        config: dict[str, Any],
        incident_number: str,
        updates: dict[str, Any],
    ) -> dict[str, Any]:
        """Update fields on an existing ServiceNow incident."""
        incidents = await self._request(
            "GET",
            config,
            "/api/now/table/incident",
            params={"sysparm_query": f"number={incident_number}", "sysparm_limit": "1"},
        )
        records = incidents.get("result", [])
        if not records:
            raise ValueError(f"Incident {incident_number} not found")

        sys_id = records[0]["sys_id"]
        resp = await self._request(
            "PATCH", config, f"/api/now/table/incident/{sys_id}", json=updates
        )
        return resp.get("result", {})

    async def close_incident(
        self,
        config: dict[str, Any],
        incident_number: str,
        resolution_notes: str,
    ) -> dict[str, Any]:
        """Close a ServiceNow incident with resolution notes."""
        return await self.update_incident(
            config,
            incident_number,
            {
                "state": "7",  # Closed
                "close_code": "Solved (Permanently)",
                "close_notes": resolution_notes,
            },
        )

    async def get_incident(
        self, config: dict[str, Any], incident_number: str
    ) -> dict[str, Any]:
        """Fetch a single incident by number."""
        resp = await self._request(
            "GET",
            config,
            "/api/now/table/incident",
            params={"sysparm_query": f"number={incident_number}", "sysparm_limit": "1"},
        )
        records = resp.get("result", [])
        if not records:
            raise ValueError(f"Incident {incident_number} not found")
        return records[0]

    async def search_incidents(
        self, config: dict[str, Any], query: str
    ) -> list[dict[str, Any]]:
        """Search incidents using a ServiceNow encoded query string."""
        resp = await self._request(
            "GET",
            config,
            "/api/now/table/incident",
            params={"sysparm_query": query, "sysparm_limit": "50"},
        )
        return resp.get("result", [])

    # ------------------------------------------------------------------
    # Change requests
    # ------------------------------------------------------------------

    async def create_change_request(
        self, config: dict[str, Any], change_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Create a change request for deployment tracking."""
        payload = {
            "short_description": change_data.get("title", "RayOlly Deployment"),
            "description": change_data.get("description", ""),
            "type": change_data.get("type", "Normal"),
            "category": "Software",
            "assignment_group": change_data.get("assignment_group", ""),
            "start_date": change_data.get("start_date", ""),
            "end_date": change_data.get("end_date", ""),
        }
        resp = await self._request(
            "POST", config, "/api/now/table/change_request", json=payload
        )
        result = resp.get("result", {})
        logger.info("Created ServiceNow change request %s", result.get("number"))
        return {
            "number": result.get("number"),
            "sys_id": result.get("sys_id"),
        }

    # ------------------------------------------------------------------
    # CMDB sync
    # ------------------------------------------------------------------

    async def sync_cmdb(
        self, config: dict[str, Any], services: list[dict[str, Any]]
    ) -> SyncResult:
        """Sync RayOlly service catalog entries with ServiceNow CMDB."""
        synced = 0
        failed = 0
        errors: list[str] = []

        for svc in services:
            try:
                payload = {
                    "name": svc.get("name", ""),
                    "short_description": svc.get("description", ""),
                    "operational_status": "1",  # Operational
                    "u_rayolly_id": svc.get("id", ""),
                }
                await self._request(
                    "POST",
                    config,
                    "/api/now/table/cmdb_ci_service",
                    json=payload,
                )
                synced += 1
            except Exception as exc:
                failed += 1
                errors.append(f"Failed to sync service {svc.get('name')}: {exc}")
                logger.warning("CMDB sync error for service %s: %s", svc.get("name"), exc)

        return SyncResult(
            success=failed == 0,
            items_synced=synced,
            items_failed=failed,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_description(incident_data: dict[str, Any]) -> str:
        """Compose a ServiceNow description from RayOlly alert data."""
        parts = [
            f"Service: {incident_data.get('service', 'N/A')}",
            f"Severity: {incident_data.get('severity', 'N/A')}",
            f"Summary: {incident_data.get('summary', '')}",
        ]
        if incident_data.get("rca_summary"):
            parts.append(f"\nAI Root-Cause Analysis:\n{incident_data['rca_summary']}")
        if incident_data.get("service_map_context"):
            parts.append(f"\nService Map Context:\n{incident_data['service_map_context']}")
        if incident_data.get("rayolly_url"):
            parts.append(f"\nRayOlly Link: {incident_data['rayolly_url']}")
        return "\n".join(parts)
