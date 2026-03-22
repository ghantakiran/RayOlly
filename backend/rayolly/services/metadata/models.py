"""SQLAlchemy ORM models for the RayOlly PostgreSQL metadata store."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from .database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Organisation & Identity
# ---------------------------------------------------------------------------


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    tier = Column(String(20), nullable=False, default="free")  # free | pro | enterprise
    settings = Column(JSONB, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # relationships
    users = relationship("User", back_populates="organization", lazy="selectin")
    teams = relationship("Team", back_populates="organization", lazy="selectin")


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(320), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    org_id = Column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role = Column(String(30), nullable=False, default="viewer")  # admin | editor | viewer
    is_active = Column(Boolean, nullable=False, default=True)
    last_login = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    organization = relationship("Organization", back_populates="users")


class Team(Base):
    __tablename__ = "teams"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    org_id = Column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    organization = relationship("Organization", back_populates="teams")
    memberships = relationship("TeamMembership", back_populates="team", lazy="selectin")


class TeamMembership(Base):
    __tablename__ = "team_memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "team_id", name="uq_team_membership"),
    )

    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    team_id = Column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True
    )
    role = Column(String(30), nullable=False, default="member")  # lead | member

    team = relationship("Team", back_populates="memberships")
    user = relationship("User")


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    key_prefix = Column(String(8), nullable=False, index=True)  # first 8 chars for lookup
    key_hash = Column(String(255), nullable=False)  # bcrypt hash of the full key
    tenant_id = Column(String(128), nullable=False, index=True)
    org_id = Column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scopes = Column(JSONB, nullable=False, server_default="[]")
    created_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    expires_at = Column(DateTime(timezone=True), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    organization = relationship("Organization")
    creator = relationship("User")


# ---------------------------------------------------------------------------
# Alerting & Incidents
# ---------------------------------------------------------------------------


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    tenant_id = Column(String(128), nullable=False, index=True)
    org_id = Column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    query = Column(Text, nullable=False)
    condition = Column(JSONB, nullable=False)  # {"operator": ">", "threshold": 95.0}
    severity = Column(String(20), nullable=False, default="warning")  # critical | warning | info
    evaluation_interval_seconds = Column(Integer, nullable=False, default=60)
    for_duration_seconds = Column(Integer, nullable=False, default=0)
    channels = Column(JSONB, nullable=False, server_default="[]")  # list of channel IDs
    labels = Column(JSONB, nullable=False, server_default="{}")
    annotations = Column(JSONB, nullable=False, server_default="{}")
    enabled = Column(Boolean, nullable=False, default=True)
    created_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    organization = relationship("Organization")
    creator = relationship("User")


class NotificationChannel(Base):
    __tablename__ = "notification_channels"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    tenant_id = Column(String(128), nullable=False, index=True)
    org_id = Column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type = Column(String(50), nullable=False)  # slack | pagerduty | email | webhook | opsgenie
    config = Column(JSONB, nullable=False, server_default="{}")  # encrypted at rest in production
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    organization = relationship("Organization")


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(500), nullable=False)
    tenant_id = Column(String(128), nullable=False, index=True)
    org_id = Column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    severity = Column(String(10), nullable=False, default="p3")  # p1 | p2 | p3 | p4 | p5
    status = Column(
        String(30),
        nullable=False,
        default="detected",
    )  # detected | acknowledged | investigating | mitigating | resolved | postmortem
    commander_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    alerts = Column(JSONB, nullable=False, server_default="[]")  # linked alert IDs
    timeline = Column(JSONB, nullable=False, server_default="[]")  # ordered list of events
    postmortem = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    organization = relationship("Organization")
    commander = relationship("User")


# ---------------------------------------------------------------------------
# Queries & Dashboards
# ---------------------------------------------------------------------------


class SavedQuery(Base):
    __tablename__ = "saved_queries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    tenant_id = Column(String(128), nullable=False, index=True)
    org_id = Column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    query = Column(Text, nullable=False)
    query_type = Column(String(50), nullable=False, default="logs")  # logs | metrics | traces | apm
    parameters = Column(JSONB, nullable=False, server_default="{}")
    columns = Column(JSONB, nullable=False, server_default="[]")
    sharing = Column(String(20), nullable=False, default="private")  # private | team | org
    tags = Column(JSONB, nullable=False, server_default="[]")
    created_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    organization = relationship("Organization")
    creator = relationship("User")


class Dashboard(Base):
    __tablename__ = "dashboards"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    tenant_id = Column(String(128), nullable=False, index=True)
    org_id = Column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    layout = Column(JSONB, nullable=False, server_default="[]")  # grid positions
    widgets = Column(JSONB, nullable=False, server_default="[]")  # widget configs
    variables = Column(JSONB, nullable=False, server_default="{}")
    sharing = Column(String(20), nullable=False, default="private")  # private | team | org
    tags = Column(JSONB, nullable=False, server_default="[]")
    folder = Column(String(255), nullable=True)
    version = Column(Integer, nullable=False, default=1)
    created_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    organization = relationship("Organization")
    creator = relationship("User")


# ---------------------------------------------------------------------------
# SLOs
# ---------------------------------------------------------------------------


class SLODefinition(Base):
    __tablename__ = "slo_definitions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    tenant_id = Column(String(128), nullable=False, index=True)
    org_id = Column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    service = Column(String(255), nullable=False)
    sli_type = Column(String(50), nullable=False)  # availability | latency | error_rate | throughput
    sli_query = Column(Text, nullable=False)
    target_percentage = Column(Float, nullable=False)  # e.g. 99.9
    window_days = Column(Integer, nullable=False, default=30)
    alert_burn_rates = Column(JSONB, nullable=False, server_default="[]")
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    organization = relationship("Organization")


# ---------------------------------------------------------------------------
# Integrations & Agents
# ---------------------------------------------------------------------------


class IntegrationInstance(Base):
    __tablename__ = "integration_instances"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    definition_id = Column(String(128), nullable=False)  # references integration catalog
    tenant_id = Column(String(128), nullable=False, index=True)
    org_id = Column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = Column(String(255), nullable=False)
    config = Column(JSONB, nullable=False, server_default="{}")  # encrypted at rest in production
    status = Column(String(30), nullable=False, default="pending")  # pending | active | error | disabled
    error_message = Column(Text, nullable=True)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    organization = relationship("Organization")


class AgentConfig(Base):
    __tablename__ = "agent_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(128), nullable=False, index=True)
    org_id = Column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_type = Column(String(50), nullable=False)  # root_cause | anomaly | capacity | cost | slo
    enabled = Column(Boolean, nullable=False, default=True)
    system_prompt_override = Column(Text, nullable=True)
    tool_overrides = Column(JSONB, nullable=False, server_default="{}")
    token_budget_daily = Column(Integer, nullable=True)
    model_override = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        UniqueConstraint("tenant_id", "agent_type", name="uq_agent_config_tenant_type"),
    )

    organization = relationship("Organization")
