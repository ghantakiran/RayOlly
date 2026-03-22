from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class SeverityLevel(StrEnum):
    TRACE = "TRACE"
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    FATAL = "FATAL"


class MetricType(StrEnum):
    GAUGE = "gauge"
    COUNTER = "counter"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


def _parse_timestamp(v: Any) -> int:
    """Accept int (nanoseconds), float (seconds), or ISO string."""
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v * 1_000_000_000)
    if isinstance(v, str):
        from datetime import datetime
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return int(dt.timestamp() * 1_000_000_000)
        except ValueError:
            return int(v) if v.isdigit() else 0
    return 0


class LogRecord(BaseModel):
    timestamp: int = 0  # nanoseconds since epoch
    body: str = ""
    severity: SeverityLevel = SeverityLevel.INFO
    attributes: dict[str, Any] = Field(default_factory=dict)
    resource_attributes: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = None
    span_id: str | None = None
    stream: str = "default"

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, v: Any) -> int:
        return _parse_timestamp(v)


class MetricDataPoint(BaseModel):
    name: str
    type: MetricType = MetricType.GAUGE
    value: float = 0.0
    timestamp: int = 0  # nanoseconds since epoch
    labels: dict[str, str] = Field(default_factory=dict)
    resource_attributes: dict[str, Any] = Field(default_factory=dict)
    unit: str = ""
    description: str = ""

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, v: Any) -> int:
        return _parse_timestamp(v)


class Span(BaseModel):
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    name: str
    kind: str = "INTERNAL"
    start_time: int  # nanoseconds since epoch
    end_time: int  # nanoseconds since epoch
    attributes: dict[str, Any] = Field(default_factory=dict)
    resource_attributes: dict[str, Any] = Field(default_factory=dict)
    status_code: str = "OK"
    status_message: str = ""
    events: list[dict[str, Any]] = Field(default_factory=list)
    links: list[dict[str, Any]] = Field(default_factory=list)


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)


@dataclass
class PIIMatch:
    type: str
    start: int
    end: int
    replacement: str


@dataclass
class IngestionResult:
    accepted: int
    rejected: int
    processing_time_ms: float
    errors: list[str] = field(default_factory=list)
