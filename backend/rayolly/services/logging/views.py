"""Log views, saved searches, and log-based metrics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

import structlog

logger = structlog.get_logger(__name__)


class ViewSharing(str, Enum):
    PRIVATE = "private"
    TEAM = "team"
    ORG = "org"


@dataclass
class LogView:
    """Saved log view / search configuration."""
    id: str
    name: str
    description: str
    tenant_id: str
    query: str
    filters: dict[str, Any] = field(default_factory=dict)
    columns: list[str] = field(default_factory=lambda: [
        "timestamp", "resource_service", "severity_text", "body"
    ])
    sort_field: str = "timestamp"
    sort_order: str = "DESC"
    sharing: ViewSharing = ViewSharing.PRIVATE
    created_by: str = ""
    created_at: str = ""
    tags: list[str] = field(default_factory=list)
    alert_enabled: bool = False
    alert_config: dict | None = None


@dataclass
class LogToMetricRule:
    """Derive metrics from log patterns."""
    id: str
    name: str
    tenant_id: str
    description: str
    source_stream: str
    filter_query: str
    metric_name: str
    metric_type: str  # counter, gauge, histogram
    value_expression: str  # "1" for count, or field extraction
    dimensions: list[str]  # fields to use as metric labels
    buckets: list[float] | None = None  # for histogram type
    enabled: bool = True
    created_at: str = ""


@dataclass
class LogArchiveConfig:
    """Configuration for log archival to cold storage."""
    id: str
    tenant_id: str
    stream_pattern: str  # glob pattern for streams to archive
    destination: str  # s3://bucket/prefix
    format: str  # parquet, json_gz
    partition_by: str  # hourly, daily
    retention_days: int
    compression: str  # zstd, lz4, gzip
    enabled: bool = True


class LogViewService:
    """Manage saved log views and searches."""

    def __init__(self, metadata_store: Any = None) -> None:
        self._store = metadata_store
        self._views: dict[str, LogView] = {}  # In-memory fallback

    async def create_view(self, view: LogView) -> LogView:
        if not view.id:
            view.id = f"lv_{uuid4().hex[:12]}"
        if not view.created_at:
            view.created_at = datetime.utcnow().isoformat()
        self._views[view.id] = view
        logger.info("log_view_created", view_id=view.id, name=view.name)
        return view

    async def list_views(
        self, tenant_id: str, sharing: ViewSharing | None = None
    ) -> list[LogView]:
        views = [v for v in self._views.values() if v.tenant_id == tenant_id]
        if sharing:
            views = [v for v in views if v.sharing == sharing]
        return sorted(views, key=lambda v: v.created_at, reverse=True)

    async def get_view(self, view_id: str) -> LogView | None:
        return self._views.get(view_id)

    async def update_view(self, view_id: str, updates: dict) -> LogView | None:
        view = self._views.get(view_id)
        if not view:
            return None
        for key, value in updates.items():
            if hasattr(view, key):
                setattr(view, key, value)
        return view

    async def delete_view(self, view_id: str) -> bool:
        return self._views.pop(view_id, None) is not None


class LogToMetricService:
    """Derive metrics from log patterns for cost-effective monitoring."""

    def __init__(self, clickhouse_client: Any = None) -> None:
        self.clickhouse = clickhouse_client
        self._rules: dict[str, LogToMetricRule] = {}

    async def create_rule(self, rule: LogToMetricRule) -> LogToMetricRule:
        if not rule.id:
            rule.id = f"l2m_{uuid4().hex[:12]}"
        self._rules[rule.id] = rule
        logger.info("log_to_metric_rule_created", rule_id=rule.id, name=rule.name)
        return rule

    async def list_rules(self, tenant_id: str) -> list[LogToMetricRule]:
        return [r for r in self._rules.values() if r.tenant_id == tenant_id]

    async def evaluate_rule(
        self, rule: LogToMetricRule, log_record: dict
    ) -> dict | None:
        """Evaluate a log-to-metric rule against a log record.

        Returns a metric data point if the rule matches, None otherwise.
        """
        # Check stream match
        if rule.source_stream and log_record.get("stream") != rule.source_stream:
            return None

        # Check filter query (simplified: keyword match)
        if rule.filter_query:
            body = log_record.get("body", "")
            if rule.filter_query not in body:
                return None

        # Extract dimensions
        labels = {}
        for dim in rule.dimensions:
            if dim.startswith("attributes."):
                attr_key = dim.replace("attributes.", "")
                labels[attr_key] = log_record.get("attributes", {}).get(attr_key, "")
            else:
                labels[dim] = log_record.get(dim, "")

        # Extract value
        if rule.value_expression == "1":
            value = 1.0
        else:
            try:
                value = float(
                    log_record.get("attributes", {}).get(rule.value_expression, 0)
                )
            except (ValueError, TypeError):
                value = 1.0

        return {
            "metric_name": rule.metric_name,
            "metric_type": rule.metric_type,
            "value": value,
            "labels": labels,
            "timestamp": log_record.get("timestamp", ""),
            "tenant_id": rule.tenant_id,
        }

    async def delete_rule(self, rule_id: str) -> bool:
        return self._rules.pop(rule_id, None) is not None
