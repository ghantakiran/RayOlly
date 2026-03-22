from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class Role(StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    EDITOR = "EDITOR"
    VIEWER = "VIEWER"


class OrgTier(StrEnum):
    FREE = "FREE"
    PRO = "PRO"
    ENTERPRISE = "ENTERPRISE"


class User(BaseModel):
    id: UUID
    email: EmailStr
    name: str
    org_id: UUID
    team_ids: list[UUID] = Field(default_factory=list)
    role: Role = Role.VIEWER
    is_active: bool = True
    created_at: datetime


class Organization(BaseModel):
    id: UUID
    name: str
    slug: str
    tier: OrgTier = OrgTier.FREE
    settings: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class Team(BaseModel):
    id: UUID
    name: str
    org_id: UUID
    members: list[UUID] = Field(default_factory=list)


class APIKey(BaseModel):
    id: UUID
    name: str
    key_hash: str
    tenant_id: str
    scopes: list[str] = Field(default_factory=list)
    created_by: UUID
    expires_at: datetime | None = None
    last_used_at: datetime | None = None


class TokenPayload(BaseModel):
    sub: str
    tenant_id: str
    org_id: str
    role: Role
    scopes: list[str] = Field(default_factory=list)
    exp: int
    iat: int
