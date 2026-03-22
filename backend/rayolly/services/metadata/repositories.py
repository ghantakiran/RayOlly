"""Repository pattern for CRUD operations against the RayOlly metadata store.

Every repository operates on a single :class:`AsyncSession` and uses
SQLAlchemy 2.0-style ``select()`` / ``insert()`` / ``update()`` / ``delete()``
statements.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    AgentConfig,
    AlertRule,
    APIKey,
    Dashboard,
    Incident,
    IntegrationInstance,
    Organization,
    SavedQuery,
    SLODefinition,
    User,
)

__all__ = [
    "BaseRepository",
    "OrganizationRepository",
    "UserRepository",
    "APIKeyRepository",
    "AlertRuleRepository",
    "SavedQueryRepository",
    "DashboardRepository",
    "IncidentRepository",
    "SLORepository",
    "IntegrationInstanceRepository",
    "AgentConfigRepository",
]


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class BaseRepository:
    """Thin base that holds a reference to the current async session."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session


# ---------------------------------------------------------------------------
# Organisation & Identity
# ---------------------------------------------------------------------------


class OrganizationRepository(BaseRepository):
    async def create(
        self,
        name: str,
        slug: str,
        tier: str = "free",
    ) -> Organization:
        org = Organization(name=name, slug=slug, tier=tier)
        self.session.add(org)
        await self.session.flush()
        return org

    async def get_by_id(self, org_id: uuid.UUID) -> Organization | None:
        result = await self.session.execute(
            select(Organization).where(Organization.id == org_id)
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Organization | None:
        result = await self.session.execute(
            select(Organization).where(Organization.slug == slug)
        )
        return result.scalar_one_or_none()


class UserRepository(BaseRepository):
    async def create(
        self,
        email: str,
        name: str,
        password_hash: str,
        org_id: uuid.UUID,
        role: str = "viewer",
    ) -> User:
        user = User(
            email=email,
            name=name,
            password_hash=password_hash,
            org_id=org_id,
            role=role,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def list_by_org(self, org_id: uuid.UUID) -> Sequence[User]:
        result = await self.session.execute(
            select(User).where(User.org_id == org_id).order_by(User.created_at)
        )
        return result.scalars().all()


# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------


class APIKeyRepository(BaseRepository):
    async def create(
        self,
        name: str,
        key_hash: str,
        key_prefix: str,
        tenant_id: str,
        org_id: uuid.UUID,
        scopes: list[str],
        created_by: uuid.UUID,
        expires_at: datetime | None = None,
    ) -> APIKey:
        api_key = APIKey(
            name=name,
            key_hash=key_hash,
            key_prefix=key_prefix,
            tenant_id=tenant_id,
            org_id=org_id,
            scopes=scopes,
            created_by=created_by,
            expires_at=expires_at,
        )
        self.session.add(api_key)
        await self.session.flush()
        return api_key

    async def get_by_prefix(self, key_prefix: str) -> APIKey | None:
        result = await self.session.execute(
            select(APIKey).where(
                APIKey.key_prefix == key_prefix,
                APIKey.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def list_by_tenant(self, tenant_id: str) -> Sequence[APIKey]:
        result = await self.session.execute(
            select(APIKey)
            .where(APIKey.tenant_id == tenant_id)
            .order_by(APIKey.created_at.desc())
        )
        return result.scalars().all()

    async def revoke(self, key_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            update(APIKey)
            .where(APIKey.id == key_id)
            .values(is_active=False)
        )
        return result.rowcount > 0

    async def update_last_used(self, key_id: uuid.UUID) -> None:
        await self.session.execute(
            update(APIKey)
            .where(APIKey.id == key_id)
            .values(last_used_at=datetime.now(UTC))
        )


# ---------------------------------------------------------------------------
# Alert Rules
# ---------------------------------------------------------------------------


class AlertRuleRepository(BaseRepository):
    async def create(self, **kwargs: Any) -> AlertRule:
        rule = AlertRule(**kwargs)
        self.session.add(rule)
        await self.session.flush()
        return rule

    async def get_by_id(self, rule_id: uuid.UUID) -> AlertRule | None:
        result = await self.session.execute(
            select(AlertRule).where(AlertRule.id == rule_id)
        )
        return result.scalar_one_or_none()

    async def list_by_tenant(
        self,
        tenant_id: str,
        enabled_only: bool = False,
    ) -> Sequence[AlertRule]:
        stmt = select(AlertRule).where(AlertRule.tenant_id == tenant_id)
        if enabled_only:
            stmt = stmt.where(AlertRule.enabled.is_(True))
        stmt = stmt.order_by(AlertRule.created_at.desc())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def update(self, rule_id: uuid.UUID, **kwargs: Any) -> AlertRule | None:
        kwargs["updated_at"] = datetime.now(UTC)
        result = await self.session.execute(
            update(AlertRule).where(AlertRule.id == rule_id).values(**kwargs)
        )
        if result.rowcount == 0:
            return None
        return await self.get_by_id(rule_id)

    async def delete(self, rule_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            delete(AlertRule).where(AlertRule.id == rule_id)
        )
        return result.rowcount > 0


# ---------------------------------------------------------------------------
# Saved Queries
# ---------------------------------------------------------------------------


class SavedQueryRepository(BaseRepository):
    async def create(self, **kwargs: Any) -> SavedQuery:
        sq = SavedQuery(**kwargs)
        self.session.add(sq)
        await self.session.flush()
        return sq

    async def list_by_tenant(
        self,
        tenant_id: str,
        sharing: str | None = None,
    ) -> Sequence[SavedQuery]:
        stmt = select(SavedQuery).where(SavedQuery.tenant_id == tenant_id)
        if sharing is not None:
            stmt = stmt.where(SavedQuery.sharing == sharing)
        stmt = stmt.order_by(SavedQuery.updated_at.desc())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_id(self, query_id: uuid.UUID) -> SavedQuery | None:
        result = await self.session.execute(
            select(SavedQuery).where(SavedQuery.id == query_id)
        )
        return result.scalar_one_or_none()

    async def delete(self, query_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            delete(SavedQuery).where(SavedQuery.id == query_id)
        )
        return result.rowcount > 0


# ---------------------------------------------------------------------------
# Dashboards
# ---------------------------------------------------------------------------


class DashboardRepository(BaseRepository):
    async def create(self, **kwargs: Any) -> Dashboard:
        dashboard = Dashboard(**kwargs)
        self.session.add(dashboard)
        await self.session.flush()
        return dashboard

    async def list_by_tenant(self, tenant_id: str) -> Sequence[Dashboard]:
        result = await self.session.execute(
            select(Dashboard)
            .where(Dashboard.tenant_id == tenant_id)
            .order_by(Dashboard.updated_at.desc())
        )
        return result.scalars().all()

    async def get_by_id(self, dashboard_id: uuid.UUID) -> Dashboard | None:
        result = await self.session.execute(
            select(Dashboard).where(Dashboard.id == dashboard_id)
        )
        return result.scalar_one_or_none()

    async def update(self, dashboard_id: uuid.UUID, **kwargs: Any) -> Dashboard | None:
        kwargs["updated_at"] = datetime.now(UTC)
        kwargs.setdefault("version", Dashboard.version + 1)
        result = await self.session.execute(
            update(Dashboard).where(Dashboard.id == dashboard_id).values(**kwargs)
        )
        if result.rowcount == 0:
            return None
        return await self.get_by_id(dashboard_id)

    async def delete(self, dashboard_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            delete(Dashboard).where(Dashboard.id == dashboard_id)
        )
        return result.rowcount > 0


# ---------------------------------------------------------------------------
# Incidents
# ---------------------------------------------------------------------------


class IncidentRepository(BaseRepository):
    async def create(self, **kwargs: Any) -> Incident:
        incident = Incident(**kwargs)
        self.session.add(incident)
        await self.session.flush()
        return incident

    async def get_by_id(self, incident_id: uuid.UUID) -> Incident | None:
        result = await self.session.execute(
            select(Incident).where(Incident.id == incident_id)
        )
        return result.scalar_one_or_none()

    async def list_by_tenant(
        self,
        tenant_id: str,
        status: str | None = None,
    ) -> Sequence[Incident]:
        stmt = select(Incident).where(Incident.tenant_id == tenant_id)
        if status is not None:
            stmt = stmt.where(Incident.status == status)
        stmt = stmt.order_by(Incident.created_at.desc())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def update(self, incident_id: uuid.UUID, **kwargs: Any) -> Incident | None:
        result = await self.session.execute(
            update(Incident).where(Incident.id == incident_id).values(**kwargs)
        )
        if result.rowcount == 0:
            return None
        return await self.get_by_id(incident_id)

    async def add_timeline_event(
        self,
        incident_id: uuid.UUID,
        event: dict[str, Any],
    ) -> Incident | None:
        incident = await self.get_by_id(incident_id)
        if incident is None:
            return None
        timeline: list[dict[str, Any]] = list(incident.timeline or [])
        event.setdefault("timestamp", datetime.now(UTC).isoformat())
        timeline.append(event)
        await self.session.execute(
            update(Incident)
            .where(Incident.id == incident_id)
            .values(timeline=timeline)
        )
        await self.session.refresh(incident)
        return incident


# ---------------------------------------------------------------------------
# SLOs
# ---------------------------------------------------------------------------


class SLORepository(BaseRepository):
    async def create(self, **kwargs: Any) -> SLODefinition:
        slo = SLODefinition(**kwargs)
        self.session.add(slo)
        await self.session.flush()
        return slo

    async def list_by_tenant(self, tenant_id: str) -> Sequence[SLODefinition]:
        result = await self.session.execute(
            select(SLODefinition)
            .where(SLODefinition.tenant_id == tenant_id)
            .order_by(SLODefinition.created_at.desc())
        )
        return result.scalars().all()

    async def get_by_id(self, slo_id: uuid.UUID) -> SLODefinition | None:
        result = await self.session.execute(
            select(SLODefinition).where(SLODefinition.id == slo_id)
        )
        return result.scalar_one_or_none()

    async def delete(self, slo_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            delete(SLODefinition).where(SLODefinition.id == slo_id)
        )
        return result.rowcount > 0


# ---------------------------------------------------------------------------
# Integration Instances
# ---------------------------------------------------------------------------


class IntegrationInstanceRepository(BaseRepository):
    async def create(self, **kwargs: Any) -> IntegrationInstance:
        instance = IntegrationInstance(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def list_by_tenant(self, tenant_id: str) -> Sequence[IntegrationInstance]:
        result = await self.session.execute(
            select(IntegrationInstance)
            .where(IntegrationInstance.tenant_id == tenant_id)
            .order_by(IntegrationInstance.created_at.desc())
        )
        return result.scalars().all()

    async def get_by_id(self, instance_id: uuid.UUID) -> IntegrationInstance | None:
        result = await self.session.execute(
            select(IntegrationInstance).where(IntegrationInstance.id == instance_id)
        )
        return result.scalar_one_or_none()

    async def update(
        self,
        instance_id: uuid.UUID,
        **kwargs: Any,
    ) -> IntegrationInstance | None:
        result = await self.session.execute(
            update(IntegrationInstance)
            .where(IntegrationInstance.id == instance_id)
            .values(**kwargs)
        )
        if result.rowcount == 0:
            return None
        return await self.get_by_id(instance_id)

    async def delete(self, instance_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            delete(IntegrationInstance).where(IntegrationInstance.id == instance_id)
        )
        return result.rowcount > 0


# ---------------------------------------------------------------------------
# Agent Configs
# ---------------------------------------------------------------------------


class AgentConfigRepository(BaseRepository):
    async def get_or_create(
        self,
        tenant_id: str,
        agent_type: str,
    ) -> AgentConfig:
        result = await self.session.execute(
            select(AgentConfig).where(
                AgentConfig.tenant_id == tenant_id,
                AgentConfig.agent_type == agent_type,
            )
        )
        config = result.scalar_one_or_none()
        if config is not None:
            return config

        config = AgentConfig(tenant_id=tenant_id, agent_type=agent_type)
        self.session.add(config)
        await self.session.flush()
        return config

    async def update(self, config_id: uuid.UUID, **kwargs: Any) -> AgentConfig | None:
        kwargs["updated_at"] = datetime.now(UTC)
        result = await self.session.execute(
            update(AgentConfig)
            .where(AgentConfig.id == config_id)
            .values(**kwargs)
        )
        if result.rowcount == 0:
            return None
        res = await self.session.execute(
            select(AgentConfig).where(AgentConfig.id == config_id)
        )
        return res.scalar_one_or_none()

    async def list_by_tenant(self, tenant_id: str) -> Sequence[AgentConfig]:
        result = await self.session.execute(
            select(AgentConfig)
            .where(AgentConfig.tenant_id == tenant_id)
            .order_by(AgentConfig.agent_type)
        )
        return result.scalars().all()
