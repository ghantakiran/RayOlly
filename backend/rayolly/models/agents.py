from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AgentType(StrEnum):
    RCA = "RCA"
    INCIDENT = "INCIDENT"
    QUERY = "QUERY"
    ANOMALY = "ANOMALY"
    CAPACITY = "CAPACITY"
    SLO = "SLO"
    RUNBOOK = "RUNBOOK"
    CUSTOM = "CUSTOM"


class AgentStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TriggerType(StrEnum):
    ALERT = "ALERT"
    ANOMALY = "ANOMALY"
    SCHEDULE = "SCHEDULE"
    MANUAL = "MANUAL"
    WEBHOOK = "WEBHOOK"


class AgentTool(BaseModel):
    name: str
    description: str
    parameters_schema: dict[str, Any] = Field(default_factory=dict)
    handler: str


class AgentTrigger(BaseModel):
    type: TriggerType
    condition: str = ""


class AgentMemory(BaseModel):
    short_term: list[dict[str, Any]] = Field(default_factory=list)
    long_term_key: str = ""


class AgentDefinition(BaseModel):
    id: UUID
    name: str
    description: str = ""
    type: AgentType
    tools: list[AgentTool] = Field(default_factory=list)
    triggers: list[AgentTrigger] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    version: str = "1.0.0"


class AgentExecution(BaseModel):
    id: UUID
    agent_id: UUID
    tenant_id: str
    status: AgentStatus = AgentStatus.PENDING
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime
    completed_at: datetime | None = None
    tokens_used: int = 0
    cost: float = 0.0
