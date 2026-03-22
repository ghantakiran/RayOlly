"""GitHub integration for RayOlly deployment tracking and change correlation."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from .registry import (
    BaseIntegration,
    IntegrationCategory,
    IntegrationInstance,
    SyncResult,
)

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"
_TIMEOUT = 20.0
_MAX_RETRIES = 3


class GitHubIntegration(BaseIntegration):
    """GitHub integration for deployment tracking, commit correlation, and issue creation."""

    name = "github"
    category = IntegrationCategory.CI_CD
    description = "GitHub – deployment tracking, commit correlation, and issue creation"
    icon_url = "/icons/integrations/github.svg"
    docs_url = "https://docs.rayolly.io/integrations/github"
    capabilities = [
        "track_deployments",
        "create_issue",
        "get_recent_commits",
        "correlate_changes",
    ]
    config_schema: dict[str, Any] = {
        "type": "object",
        "required": ["token", "org"],
        "properties": {
            "token": {
                "type": "string",
                "title": "Personal Access Token",
                "format": "password",
            },
            "org": {"type": "string", "title": "Organization"},
            "repos": {
                "type": "array",
                "title": "Repositories",
                "items": {"type": "string"},
                "description": "List of repository names to track",
            },
        },
    }

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _headers(config: dict[str, Any]) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {config['token']}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def _request(
        self,
        method: str,
        config: dict[str, Any],
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> Any:
        url = f"{_GITHUB_API}{path}"
        headers = self._headers(config)

        last_exc: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                    resp = await client.request(method, url, headers=headers, json=json_body, params=params)
                    resp.raise_for_status()
                    if resp.status_code == 204:
                        return {}
                    return resp.json()
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                last_exc = exc
                logger.warning("GitHub %s %s attempt %d/%d failed: %s", method, path, attempt, _MAX_RETRIES, exc)
        raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------
    # BaseIntegration interface
    # ------------------------------------------------------------------

    async def test_connection(self, config: dict[str, Any]) -> bool:
        try:
            await self._request("GET", config, "/user")
            return True
        except Exception as exc:
            logger.error("GitHub connection test failed: %s", exc)
            return False

    async def sync(self, instance: IntegrationInstance) -> SyncResult:
        """Sync recent deployments across configured repos."""
        repos = instance.config.get("repos", [])
        org = instance.config.get("org", "")
        synced = 0
        errors: list[str] = []

        for repo in repos:
            try:
                deployments = await self.get_recent_deployments(
                    instance.config, f"{org}/{repo}", since=None
                )
                synced += len(deployments)
            except Exception as exc:
                errors.append(f"{repo}: {exc}")

        return SyncResult(
            success=len(errors) == 0,
            items_synced=synced,
            items_failed=len(errors),
            errors=errors,
        )

    async def execute_action(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        config = params.get("config", {})
        dispatchers: dict[str, Any] = {
            "get_recent_deployments": lambda: self.get_recent_deployments(
                config, params["repo"], params.get("since")
            ),
            "get_recent_commits": lambda: self.get_recent_commits(
                config, params["repo"], params.get("since")
            ),
            "create_issue": lambda: self.create_issue(
                config, params["repo"], params.get("title", ""), params.get("body", ""), params.get("labels", [])
            ),
            "correlate_deployment": lambda: self.correlate_deployment(
                config, params.get("incident_time")
            ),
        }
        handler = dispatchers.get(action)
        if handler is None:
            raise ValueError(f"Unknown GitHub action: {action}")
        result = await handler()
        # Ensure we always return a dict
        if isinstance(result, list):
            return {"items": result, "count": len(result)}
        return result

    # ------------------------------------------------------------------
    # Deployments
    # ------------------------------------------------------------------

    async def get_recent_deployments(
        self, config: dict[str, Any], repo: str, since: str | None = None
    ) -> list[dict[str, Any]]:
        """Get recent deployments for a repository."""
        params: dict[str, str] = {"per_page": "30"}
        resp = await self._request("GET", config, f"/repos/{repo}/deployments", params=params)

        deployments: list[dict[str, Any]] = []
        for d in resp if isinstance(resp, list) else []:
            created = d.get("created_at", "")
            if since and created < since:
                continue
            deployments.append({
                "id": d.get("id"),
                "ref": d.get("ref"),
                "environment": d.get("environment"),
                "description": d.get("description", ""),
                "created_at": created,
                "creator": d.get("creator", {}).get("login", ""),
            })
        return deployments

    # ------------------------------------------------------------------
    # Commits
    # ------------------------------------------------------------------

    async def get_recent_commits(
        self, config: dict[str, Any], repo: str, since: str | None = None
    ) -> list[dict[str, Any]]:
        """Get recent commits for change correlation."""
        params: dict[str, str] = {"per_page": "50"}
        if since:
            params["since"] = since

        resp = await self._request("GET", config, f"/repos/{repo}/commits", params=params)

        commits: list[dict[str, Any]] = []
        for c in resp if isinstance(resp, list) else []:
            commit_info = c.get("commit", {})
            commits.append({
                "sha": c.get("sha", "")[:8],
                "message": commit_info.get("message", "").split("\n")[0],
                "author": commit_info.get("author", {}).get("name", ""),
                "date": commit_info.get("author", {}).get("date", ""),
                "url": c.get("html_url", ""),
            })
        return commits

    # ------------------------------------------------------------------
    # Issues
    # ------------------------------------------------------------------

    async def create_issue(
        self,
        config: dict[str, Any],
        repo: str,
        title: str,
        body: str,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a GitHub issue from an incident."""
        payload: dict[str, Any] = {"title": title, "body": body}
        if labels:
            payload["labels"] = labels

        resp = await self._request("POST", config, f"/repos/{repo}/issues", json_body=payload)
        logger.info("Created GitHub issue #%s in %s", resp.get("number"), repo)
        return {
            "number": resp.get("number"),
            "url": resp.get("html_url"),
            "id": resp.get("id"),
        }

    # ------------------------------------------------------------------
    # Correlation
    # ------------------------------------------------------------------

    async def correlate_deployment(
        self, config: dict[str, Any], incident_time: str | None = None
    ) -> list[dict[str, Any]]:
        """Find deployments across all tracked repos near the incident time."""
        repos = config.get("repos", [])
        org = config.get("org", "")

        # Default to last 2 hours if no incident time provided
        if incident_time is None:
            from datetime import timedelta

            incident_time = (datetime.now(UTC) - timedelta(hours=2)).isoformat()

        correlated: list[dict[str, Any]] = []
        for repo_name in repos:
            repo = f"{org}/{repo_name}"
            try:
                deployments = await self.get_recent_deployments(config, repo, since=incident_time)
                for d in deployments:
                    d["repo"] = repo
                    correlated.append(d)
            except Exception as exc:
                logger.warning("Failed to fetch deployments for %s: %s", repo, exc)

        correlated.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return correlated
