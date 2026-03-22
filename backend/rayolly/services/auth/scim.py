"""SCIM 2.0 — automatic user and group provisioning from identity providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class SCIMUser:
    id: str
    userName: str
    name: dict  # {"givenName": "...", "familyName": "..."}
    emails: list[dict]  # [{"value": "...", "primary": true}]
    active: bool = True
    groups: list[dict] = field(default_factory=list)
    externalId: str = ""


@dataclass
class SCIMGroup:
    id: str
    displayName: str
    members: list[dict] = field(default_factory=list)


class SCIMService:
    """SCIM 2.0 service for user/group provisioning."""

    def __init__(self, user_repo: Any = None, team_repo: Any = None) -> None:
        self.user_repo = user_repo
        self.team_repo = team_repo
        self._users: dict[str, SCIMUser] = {}
        self._groups: dict[str, SCIMGroup] = {}

    # ── User operations ───────────────────────────────────────────────────

    async def create_user(self, scim_user: dict) -> SCIMUser:
        user = SCIMUser(
            id=scim_user.get("externalId", scim_user.get("userName", "")),
            userName=scim_user.get("userName", ""),
            name=scim_user.get("name", {}),
            emails=scim_user.get("emails", []),
            active=scim_user.get("active", True),
            externalId=scim_user.get("externalId", ""),
        )
        self._users[user.id] = user
        logger.info("scim.user_created", user=user.userName)
        # TODO: Create in PostgreSQL via user_repo
        return user

    async def get_user(self, user_id: str) -> SCIMUser | None:
        return self._users.get(user_id)

    async def update_user(self, user_id: str, updates: dict) -> SCIMUser | None:
        user = self._users.get(user_id)
        if not user:
            return None
        if "active" in updates:
            user.active = updates["active"]
        if "name" in updates:
            user.name = updates["name"]
        logger.info("scim.user_updated", user=user.userName, updates=list(updates.keys()))
        return user

    async def delete_user(self, user_id: str) -> bool:
        user = self._users.pop(user_id, None)
        if user:
            logger.info("scim.user_deactivated", user=user.userName)
        return user is not None

    async def list_users(
        self, filter_str: str = "", start: int = 1, count: int = 100
    ) -> dict:
        users = list(self._users.values())
        if filter_str and "userName eq" in filter_str:
            target = filter_str.split('"')[1] if '"' in filter_str else ""
            users = [u for u in users if u.userName == target]
        return {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
            "totalResults": len(users),
            "startIndex": start,
            "itemsPerPage": count,
            "Resources": [
                self._user_to_dict(u) for u in users[start - 1 : start - 1 + count]
            ],
        }

    # ── Group operations ──────────────────────────────────────────────────

    async def create_group(self, scim_group: dict) -> SCIMGroup:
        group = SCIMGroup(
            id=scim_group.get("displayName", ""),
            displayName=scim_group.get("displayName", ""),
            members=scim_group.get("members", []),
        )
        self._groups[group.id] = group
        logger.info("scim.group_created", group=group.displayName)
        return group

    async def list_groups(self, start: int = 1, count: int = 100) -> dict:
        groups = list(self._groups.values())
        return {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
            "totalResults": len(groups),
            "Resources": [
                {"id": g.id, "displayName": g.displayName, "members": g.members}
                for g in groups
            ],
        }

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _user_to_dict(user: SCIMUser) -> dict:
        return {
            "schemas": ["urn:ietf:params:scim:core:2.0:User"],
            "id": user.id,
            "userName": user.userName,
            "name": user.name,
            "emails": user.emails,
            "active": user.active,
            "externalId": user.externalId,
        }
