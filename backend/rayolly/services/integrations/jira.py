"""Jira integration for RayOlly issue tracking."""

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

_TIMEOUT = 20.0
_MAX_RETRIES = 3

_PRIORITY_MAP: dict[str, str] = {
    "critical": "Highest",
    "high": "High",
    "warning": "Medium",
    "medium": "Medium",
    "low": "Low",
    "info": "Lowest",
}


class JiraIntegration(BaseIntegration):
    """Jira integration for creating and managing issues from RayOlly alerts."""

    name = "jira"
    category = IntegrationCategory.ITSM
    description = "Jira – issue creation, status sync, and incident linking"
    icon_url = "/icons/integrations/jira.svg"
    docs_url = "https://docs.rayolly.io/integrations/jira"
    capabilities = [
        "create_issue",
        "update_issue",
        "add_comment",
        "transition_issue",
        "link_incident",
        "sync_status",
    ]
    config_schema: dict[str, Any] = {
        "type": "object",
        "required": ["url", "email", "api_token", "project_key"],
        "properties": {
            "url": {
                "type": "string",
                "title": "Jira URL",
                "description": "Jira Cloud or Server URL (e.g. https://mycompany.atlassian.net)",
            },
            "email": {"type": "string", "title": "Email"},
            "api_token": {"type": "string", "title": "API Token", "format": "password"},
            "project_key": {
                "type": "string",
                "title": "Project Key",
                "description": "Default Jira project key (e.g. OPS)",
            },
            "issue_type": {
                "type": "string",
                "title": "Default Issue Type",
                "default": "Bug",
            },
        },
    }

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _base_url(self, config: dict[str, Any]) -> str:
        return config["url"].rstrip("/")

    def _auth(self, config: dict[str, Any]) -> httpx.BasicAuth:
        return httpx.BasicAuth(username=config["email"], password=config["api_token"])

    async def _request(
        self,
        method: str,
        config: dict[str, Any],
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url = f"{self._base_url(config)}/rest/api/3{path}"
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        auth = self._auth(config)

        last_exc: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                    resp = await client.request(method, url, headers=headers, auth=auth, json=json_body, params=params)
                    resp.raise_for_status()
                    if resp.status_code == 204:
                        return {}
                    return resp.json()
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                last_exc = exc
                logger.warning("Jira %s %s attempt %d/%d failed: %s", method, path, attempt, _MAX_RETRIES, exc)
        raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------
    # BaseIntegration interface
    # ------------------------------------------------------------------

    async def test_connection(self, config: dict[str, Any]) -> bool:
        try:
            await self._request("GET", config, "/myself")
            return True
        except Exception as exc:
            logger.error("Jira connection test failed: %s", exc)
            return False

    async def sync(self, instance: IntegrationInstance) -> SyncResult:
        """Jira sync is a no-op; statuses are checked on demand."""
        return SyncResult(success=True, items_synced=0)

    async def execute_action(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        config = params.get("config", {})
        dispatchers: dict[str, Any] = {
            "create_issue": lambda: self.create_issue(config, params.get("issue_data", {})),
            "update_issue": lambda: self.update_issue(config, params["issue_key"], params.get("updates", {})),
            "add_comment": lambda: self.add_comment(config, params["issue_key"], params.get("comment", "")),
            "transition_issue": lambda: self.transition_issue(config, params["issue_key"], params.get("transition_name", "")),
        }
        handler = dispatchers.get(action)
        if handler is None:
            raise ValueError(f"Unknown Jira action: {action}")
        return await handler()

    # ------------------------------------------------------------------
    # Issue operations
    # ------------------------------------------------------------------

    async def create_issue(
        self, config: dict[str, Any], issue_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Create a Jira issue from alert/incident data."""
        severity = issue_data.get("severity", "medium")
        priority = _PRIORITY_MAP.get(severity.lower(), "Medium")
        project_key = issue_data.get("project_key", config["project_key"])
        issue_type = issue_data.get("issue_type", config.get("issue_type", "Bug"))

        description_parts = [
            issue_data.get("description", "Alert created by RayOlly."),
        ]
        if issue_data.get("rca_summary"):
            description_parts.append(f"\nh3. AI Root-Cause Analysis\n{issue_data['rca_summary']}")
        if issue_data.get("rayolly_url"):
            description_parts.append(f"\n[View in RayOlly|{issue_data['rayolly_url']}]")

        payload = {
            "fields": {
                "project": {"key": project_key},
                "summary": issue_data.get("title", "RayOlly Alert"),
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "\n".join(description_parts)}],
                        }
                    ],
                },
                "issuetype": {"name": issue_type},
                "priority": {"name": priority},
                "labels": issue_data.get("labels", ["rayolly", "auto-created"]),
            }
        }

        resp = await self._request("POST", config, "/issue", json_body=payload)
        logger.info("Created Jira issue %s", resp.get("key"))
        return {"key": resp.get("key"), "id": resp.get("id"), "self": resp.get("self")}

    async def update_issue(
        self, config: dict[str, Any], issue_key: str, updates: dict[str, Any]
    ) -> dict[str, Any]:
        """Update fields on an existing Jira issue."""
        payload = {"fields": updates}
        await self._request("PUT", config, f"/issue/{issue_key}", json_body=payload)
        logger.info("Updated Jira issue %s", issue_key)
        return {"key": issue_key, "updated": True}

    async def add_comment(
        self, config: dict[str, Any], issue_key: str, comment: str
    ) -> dict[str, Any]:
        """Add a comment to a Jira issue."""
        payload = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": comment}],
                    }
                ],
            }
        }
        resp = await self._request("POST", config, f"/issue/{issue_key}/comment", json_body=payload)
        logger.info("Added comment to Jira issue %s", issue_key)
        return {"id": resp.get("id"), "issue_key": issue_key}

    async def transition_issue(
        self, config: dict[str, Any], issue_key: str, transition_name: str
    ) -> dict[str, Any]:
        """Transition a Jira issue to a new status by transition name."""
        # First, get available transitions
        resp = await self._request("GET", config, f"/issue/{issue_key}/transitions")
        transitions = resp.get("transitions", [])

        target = None
        for t in transitions:
            if t.get("name", "").lower() == transition_name.lower():
                target = t
                break

        if target is None:
            available = [t.get("name") for t in transitions]
            raise ValueError(
                f"Transition '{transition_name}' not found. Available: {available}"
            )

        await self._request(
            "POST",
            config,
            f"/issue/{issue_key}/transitions",
            json_body={"transition": {"id": target["id"]}},
        )
        logger.info("Transitioned Jira issue %s to '%s'", issue_key, transition_name)
        return {"issue_key": issue_key, "transition": transition_name}
