from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class QueryType(StrEnum):
    SQL = "SQL"
    PROMQL = "PROMQL"
    SEARCH = "SEARCH"
    NL = "NL"


class ExportFormat(StrEnum):
    JSON = "JSON"
    CSV = "CSV"
    PARQUET = "PARQUET"
    ARROW = "ARROW"


class TimeRange(BaseModel):
    from_time: datetime
    to_time: datetime


class Column(BaseModel):
    name: str
    type: str


class QueryRequest(BaseModel):
    query: str
    query_type: QueryType = QueryType.SQL
    time_range: TimeRange | None = None
    format: ExportFormat = ExportFormat.JSON
    timeout: int = 30
    parameters: dict[str, Any] = Field(default_factory=dict)


class QueryResponse(BaseModel):
    status: str
    took_ms: float
    rows: int
    total_rows: int
    columns: list[Column] = Field(default_factory=list)
    data: list[dict[str, Any]] = Field(default_factory=list)
    query_id: str
    tier: str = ""
    cached: bool = False


class SavedQuery(BaseModel):
    id: UUID
    name: str
    query: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    schedule: str | None = None
    sharing: str = "private"
    tags: list[str] = Field(default_factory=list)
