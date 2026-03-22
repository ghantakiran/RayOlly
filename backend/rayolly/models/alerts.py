from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AlertStatus(StrEnum):
    FIRING = "FIRING"
    RESOLVED = "RESOLVED"
    PENDING = "PENDING"
    SUPPRESSED = "SUPPRESSED"


class AlertSeverity(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class ChannelType(StrEnum):
    SLACK = "SLACK"
    PAGERDUTY = "PAGERDUTY"
    OPSGENIE = "OPSGENIE"
    EMAIL = "EMAIL"
    WEBHOOK = "WEBHOOK"
    TEAMS = "TEAMS"


class IncidentStatus(StrEnum):
    DETECTED = "DETECTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    INVESTIGATING = "INVESTIGATING"
    MITIGATING = "MITIGATING"
    RESOLVED = "RESOLVED"
    POSTMORTEM = "POSTMORTEM"


class ComparisonOperator(StrEnum):
    GT = "GT"
    GTE = "GTE"
    LT = "LT"
    LTE = "LTE"
    EQ = "EQ"
    NEQ = "NEQ"


class AlertCondition(BaseModel):
    operator: ComparisonOperator
    threshold: float
    for_duration: str = "5m"


class NotificationChannel(BaseModel):
    id: UUID
    name: str
    type: ChannelType
    config: dict[str, Any] = Field(default_factory=dict)


class AlertRule(BaseModel):
    id: UUID
    name: str
    query: str
    condition: AlertCondition
    severity: AlertSeverity = AlertSeverity.MEDIUM
    channels: list[UUID] = Field(default_factory=list)
    enabled: bool = True
    evaluation_interval: str = "1m"
    labels: dict[str, str] = Field(default_factory=dict)


class Alert(BaseModel):
    id: UUID
    rule_id: UUID
    status: AlertStatus = AlertStatus.PENDING
    value: float
    started_at: datetime
    resolved_at: datetime | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)


class TimelineEntry(BaseModel):
    timestamp: datetime
    action: str
    actor: str = ""
    details: str = ""


class Incident(BaseModel):
    id: UUID
    title: str
    severity: AlertSeverity
    status: IncidentStatus = IncidentStatus.DETECTED
    alerts: list[UUID] = Field(default_factory=list)
    timeline: list[TimelineEntry] = Field(default_factory=list)
    commander: str | None = None
    created_at: datetime
