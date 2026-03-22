"""Advanced log exploration — search, facets, patterns, live tail, and analytics."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class LogSortField(str, Enum):
    TIMESTAMP = "timestamp"
    SEVERITY = "severity_number"
    SERVICE = "resource_service"


class LogSortOrder(str, Enum):
    ASC = "ASC"
    DESC = "DESC"


@dataclass
class LogSearchRequest:
    query: str = ""
    stream: str | None = None
    services: list[str] = field(default_factory=list)
    severities: list[str] = field(default_factory=list)
    hosts: list[str] = field(default_factory=list)
    trace_id: str | None = None
    from_time: str = ""
    to_time: str = ""
    sort_field: LogSortField = LogSortField.TIMESTAMP
    sort_order: LogSortOrder = LogSortOrder.DESC
    limit: int = 100
    offset: int = 0
    highlight: bool = True


@dataclass
class LogSearchResult:
    logs: list[dict[str, Any]]
    total: int
    took_ms: int
    facets: LogFacets | None = None
    histogram: list[HistogramBucket] | None = None


@dataclass
class LogFacets:
    services: list[FacetValue]
    severities: list[FacetValue]
    hosts: list[FacetValue]
    streams: list[FacetValue]
    namespaces: list[FacetValue]


@dataclass
class FacetValue:
    value: str
    count: int
    percentage: float = 0.0


@dataclass
class HistogramBucket:
    timestamp: str
    count: int
    error_count: int = 0
    warn_count: int = 0


@dataclass
class LogContext:
    """Surrounding log lines for context."""
    before: list[dict[str, Any]]
    target: dict[str, Any]
    after: list[dict[str, Any]]


@dataclass
class LogStream:
    name: str
    log_count: int
    first_seen: str
    last_seen: str
    fields: list[StreamField]
    retention_days: int
    size_bytes: int


@dataclass
class StreamField:
    name: str
    field_type: str
    cardinality: int
    sample_values: list[str]


class LogExplorer:
    """Advanced log search and exploration engine."""

    def __init__(self, clickhouse_client: Any, redis_client: Any = None) -> None:
        self.clickhouse = clickhouse_client
        self.redis = redis_client

    async def search(
        self, tenant_id: str, request: LogSearchRequest
    ) -> LogSearchResult:
        """Full-featured log search with facets and histogram."""
        import time

        start = time.monotonic()

        where_clauses = [f"tenant_id = '{tenant_id}'"]

        if request.from_time:
            where_clauses.append(f"timestamp >= '{request.from_time}'")
        if request.to_time:
            where_clauses.append(f"timestamp <= '{request.to_time}'")
        if request.query:
            terms = request.query.split()
            for term in terms:
                if ":" in term:
                    field_name, value = term.split(":", 1)
                    where_clauses.append(f"{field_name} = '{value}'")
                else:
                    where_clauses.append(f"hasToken(body, '{term}')")
        if request.services:
            svc_list = ", ".join(f"'{s}'" for s in request.services)
            where_clauses.append(f"resource_service IN ({svc_list})")
        if request.severities:
            sev_list = ", ".join(f"'{s}'" for s in request.severities)
            where_clauses.append(f"severity_text IN ({sev_list})")
        if request.hosts:
            host_list = ", ".join(f"'{h}'" for h in request.hosts)
            where_clauses.append(f"resource_host IN ({host_list})")
        if request.trace_id:
            where_clauses.append(f"trace_id = '{request.trace_id}'")
        if request.stream:
            where_clauses.append(f"stream = '{request.stream}'")

        where = " AND ".join(where_clauses)

        # Main query
        sql = (
            f"SELECT timestamp, resource_service, resource_host, "
            f"severity_text, severity_number, body, trace_id, span_id, "
            f"stream, attributes "
            f"FROM logs.log_entries "
            f"WHERE {where} "
            f"ORDER BY {request.sort_field.value} {request.sort_order.value} "
            f"LIMIT {request.limit} OFFSET {request.offset}"
        )

        # Count query
        count_sql = f"SELECT count() FROM logs.log_entries WHERE {where}"

        try:
            result = self.clickhouse.query(sql)
            count_result = self.clickhouse.query(count_sql)
            total = count_result.result_rows[0][0] if count_result.result_rows else 0

            logs = []
            for row in result.result_rows:
                logs.append({
                    "timestamp": str(row[0]),
                    "resource_service": row[1],
                    "resource_host": row[2],
                    "severity_text": row[3],
                    "severity_number": row[4],
                    "body": row[5],
                    "trace_id": row[6],
                    "span_id": row[7],
                    "stream": row[8],
                    "attributes": row[9] if len(row) > 9 else {},
                })

            # Fetch facets
            facets = await self._build_facets(tenant_id, where)

            # Fetch histogram
            histogram = await self._build_histogram(
                tenant_id, where, request.from_time, request.to_time
            )

            elapsed_ms = int((time.monotonic() - start) * 1000)

            return LogSearchResult(
                logs=logs,
                total=total,
                took_ms=elapsed_ms,
                facets=facets,
                histogram=histogram,
            )
        except Exception as e:
            logger.error("log_search_error", error=str(e))
            raise

    async def get_context(
        self, tenant_id: str, timestamp: str, service: str, lines: int = 20
    ) -> LogContext:
        """Get surrounding log lines for context (like grep -C)."""
        before_sql = (
            f"SELECT timestamp, severity_text, body FROM logs.log_entries "
            f"WHERE tenant_id = '{tenant_id}' "
            f"AND resource_service = '{service}' "
            f"AND timestamp < '{timestamp}' "
            f"ORDER BY timestamp DESC LIMIT {lines}"
        )
        after_sql = (
            f"SELECT timestamp, severity_text, body FROM logs.log_entries "
            f"WHERE tenant_id = '{tenant_id}' "
            f"AND resource_service = '{service}' "
            f"AND timestamp > '{timestamp}' "
            f"ORDER BY timestamp ASC LIMIT {lines}"
        )
        target_sql = (
            f"SELECT timestamp, severity_text, body, attributes FROM logs.log_entries "
            f"WHERE tenant_id = '{tenant_id}' "
            f"AND timestamp = '{timestamp}' AND resource_service = '{service}' "
            f"LIMIT 1"
        )

        before_result = self.clickhouse.query(before_sql)
        after_result = self.clickhouse.query(after_sql)
        target_result = self.clickhouse.query(target_sql)

        return LogContext(
            before=[
                {"timestamp": str(r[0]), "severity": r[1], "body": r[2]}
                for r in reversed(before_result.result_rows)
            ],
            target=(
                {
                    "timestamp": str(target_result.result_rows[0][0]),
                    "severity": target_result.result_rows[0][1],
                    "body": target_result.result_rows[0][2],
                    "attributes": target_result.result_rows[0][3],
                }
                if target_result.result_rows
                else {}
            ),
            after=[
                {"timestamp": str(r[0]), "severity": r[1], "body": r[2]}
                for r in after_result.result_rows
            ],
        )

    async def get_streams(self, tenant_id: str) -> list[LogStream]:
        """List all log streams for the tenant."""
        sql = (
            f"SELECT stream, count() as cnt, "
            f"min(timestamp) as first_seen, max(timestamp) as last_seen "
            f"FROM logs.log_entries "
            f"WHERE tenant_id = '{tenant_id}' "
            f"GROUP BY stream ORDER BY cnt DESC LIMIT 100"
        )
        result = self.clickhouse.query(sql)
        streams = []
        for row in result.result_rows:
            streams.append(LogStream(
                name=row[0],
                log_count=row[1],
                first_seen=str(row[2]),
                last_seen=str(row[3]),
                fields=[],
                retention_days=30,
                size_bytes=0,
            ))
        return streams

    async def get_field_values(
        self, tenant_id: str, field_name: str, prefix: str = "", limit: int = 50
    ) -> list[FacetValue]:
        """Get top values for a field (for autocomplete and faceting)."""
        field_col = self._map_field_name(field_name)
        prefix_filter = f"AND {field_col} LIKE '{prefix}%'" if prefix else ""
        sql = (
            f"SELECT {field_col} as val, count() as cnt "
            f"FROM logs.log_entries "
            f"WHERE tenant_id = '{tenant_id}' AND {field_col} != '' {prefix_filter} "
            f"GROUP BY val ORDER BY cnt DESC LIMIT {limit}"
        )
        result = self.clickhouse.query(sql)
        total = sum(row[1] for row in result.result_rows) or 1
        return [
            FacetValue(value=row[0], count=row[1], percentage=row[1] / total * 100)
            for row in result.result_rows
        ]

    async def get_log_analytics(
        self, tenant_id: str, time_range: tuple[str, str]
    ) -> dict:
        """Aggregate log analytics for the dashboard."""
        from_time, to_time = time_range
        base_where = (
            f"tenant_id = '{tenant_id}' "
            f"AND timestamp >= '{from_time}' AND timestamp <= '{to_time}'"
        )

        # Total volume
        volume_sql = f"SELECT count() FROM logs.log_entries WHERE {base_where}"
        # By severity
        severity_sql = (
            f"SELECT severity_text, count() as cnt FROM logs.log_entries "
            f"WHERE {base_where} GROUP BY severity_text ORDER BY cnt DESC"
        )
        # By service
        service_sql = (
            f"SELECT resource_service, count() as cnt FROM logs.log_entries "
            f"WHERE {base_where} GROUP BY resource_service ORDER BY cnt DESC LIMIT 20"
        )
        # Error rate
        error_sql = (
            f"SELECT countIf(severity_number >= 17) as errors, count() as total "
            f"FROM logs.log_entries WHERE {base_where}"
        )

        vol = self.clickhouse.query(volume_sql)
        sev = self.clickhouse.query(severity_sql)
        svc = self.clickhouse.query(service_sql)
        err = self.clickhouse.query(error_sql)

        error_row = err.result_rows[0] if err.result_rows else (0, 1)
        error_rate = error_row[0] / max(error_row[1], 1) * 100

        return {
            "total_logs": vol.result_rows[0][0] if vol.result_rows else 0,
            "by_severity": {r[0]: r[1] for r in sev.result_rows},
            "top_services": {r[0]: r[1] for r in svc.result_rows},
            "error_rate_pct": round(error_rate, 2),
            "error_count": error_row[0],
        }

    async def _build_facets(self, tenant_id: str, base_where: str) -> LogFacets:
        """Build facet counts for the sidebar."""
        facet_queries = {
            "services": "resource_service",
            "severities": "severity_text",
            "hosts": "resource_host",
            "streams": "stream",
            "namespaces": "resource_namespace",
        }

        facets = {}
        for facet_name, column in facet_queries.items():
            sql = (
                f"SELECT {column}, count() as cnt FROM logs.log_entries "
                f"WHERE {base_where} AND {column} != '' "
                f"GROUP BY {column} ORDER BY cnt DESC LIMIT 30"
            )
            try:
                result = self.clickhouse.query(sql)
                total = sum(r[1] for r in result.result_rows) or 1
                facets[facet_name] = [
                    FacetValue(value=r[0], count=r[1], percentage=r[1] / total * 100)
                    for r in result.result_rows
                ]
            except Exception:
                facets[facet_name] = []

        return LogFacets(**facets)

    async def _build_histogram(
        self, tenant_id: str, base_where: str, from_time: str, to_time: str
    ) -> list[HistogramBucket]:
        """Build time histogram for log volume chart."""
        sql = (
            f"SELECT toStartOfMinute(timestamp) as ts, "
            f"count() as cnt, "
            f"countIf(severity_number >= 17) as err_cnt, "
            f"countIf(severity_number >= 13 AND severity_number < 17) as warn_cnt "
            f"FROM logs.log_entries "
            f"WHERE {base_where} "
            f"GROUP BY ts ORDER BY ts"
        )
        try:
            result = self.clickhouse.query(sql)
            return [
                HistogramBucket(
                    timestamp=str(r[0]),
                    count=r[1],
                    error_count=r[2],
                    warn_count=r[3],
                )
                for r in result.result_rows
            ]
        except Exception:
            return []

    @staticmethod
    def _map_field_name(name: str) -> str:
        """Map user-friendly field names to ClickHouse columns."""
        mapping = {
            "service": "resource_service",
            "host": "resource_host",
            "severity": "severity_text",
            "level": "severity_text",
            "namespace": "resource_namespace",
            "pod": "resource_pod",
            "container": "resource_container",
            "stream": "stream",
        }
        return mapping.get(name, name)
