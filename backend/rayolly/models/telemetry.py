from __future__ import annotations

from datetime import datetime
from enum import IntEnum, StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SeverityNumber(IntEnum):
    TRACE = 1
    TRACE2 = 2
    TRACE3 = 3
    TRACE4 = 4
    DEBUG = 5
    DEBUG2 = 6
    DEBUG3 = 7
    DEBUG4 = 8
    INFO = 9
    INFO2 = 10
    INFO3 = 11
    INFO4 = 12
    WARN = 13
    WARN2 = 14
    WARN3 = 15
    WARN4 = 16
    ERROR = 17
    ERROR2 = 18
    ERROR3 = 19
    ERROR4 = 20
    FATAL = 21
    FATAL2 = 22
    FATAL3 = 23
    FATAL4 = 24


class SpanKind(StrEnum):
    INTERNAL = "INTERNAL"
    SERVER = "SERVER"
    CLIENT = "CLIENT"
    PRODUCER = "PRODUCER"
    CONSUMER = "CONSUMER"


class MetricType(StrEnum):
    GAUGE = "GAUGE"
    COUNTER = "COUNTER"
    HISTOGRAM = "HISTOGRAM"
    SUMMARY = "SUMMARY"


class Resource(BaseModel):
    attributes: dict[str, Any] = Field(default_factory=dict)


class LogRecord(BaseModel):
    timestamp: datetime
    observed_timestamp: datetime | None = None
    severity_number: SeverityNumber = SeverityNumber.INFO
    severity_text: str = ""
    body: str = ""
    resource: Resource = Field(default_factory=Resource)
    attributes: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = None
    span_id: str | None = None


class MetricDataPoint(BaseModel):
    metric_name: str
    metric_type: MetricType
    value: float
    timestamp: datetime
    labels: dict[str, str] = Field(default_factory=dict)
    resource: Resource = Field(default_factory=Resource)


class SpanEvent(BaseModel):
    name: str
    timestamp: datetime
    attributes: dict[str, Any] = Field(default_factory=dict)


class SpanLink(BaseModel):
    trace_id: str
    span_id: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class SpanStatus(BaseModel):
    code: str = "UNSET"
    message: str = ""


class Span(BaseModel):
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    name: str
    kind: SpanKind = SpanKind.INTERNAL
    start_time: datetime
    end_time: datetime
    duration_ns: int
    status: SpanStatus = Field(default_factory=SpanStatus)
    attributes: dict[str, Any] = Field(default_factory=dict)
    events: list[SpanEvent] = Field(default_factory=list)
    links: list[SpanLink] = Field(default_factory=list)
    resource: Resource = Field(default_factory=Resource)
