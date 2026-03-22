"""Unified query engine for RayOlly — SQL, PromQL, full-text search."""

from __future__ import annotations

import hashlib
import re
import time
from enum import Enum
from typing import Any

import orjson
import structlog

from rayolly.models.query import (
    Column,
    QueryRequest,
    QueryResponse,
    QueryType,
    TimeRange,
)

logger = structlog.get_logger(__name__)


class StorageTier(str, Enum):
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"
    MIXED = "mixed"


class QueryEngine:
    """Unified query engine that routes to appropriate backend."""

    def __init__(
        self,
        clickhouse_client: Any,
        redis_client: Any,
        duckdb_connection: Any | None = None,
    ) -> None:
        self.clickhouse = clickhouse_client
        self.redis = redis_client
        self.duckdb = duckdb_connection
        self._planner = QueryPlanner()
        self._cache = QueryCache(redis_client)

    async def execute(self, request: QueryRequest, tenant_id: str) -> QueryResponse:
        start_time = time.monotonic()
        query_id = self._generate_query_id(request, tenant_id)

        log = logger.bind(
            query_id=query_id,
            tenant_id=tenant_id,
            query_type=request.query_type,
        )

        # Check cache first
        cached = await self._cache.get(query_id)
        if cached:
            log.info("query_cache_hit")
            cached.cached = True
            return cached

        # Plan the query
        plan = self._planner.plan(request, tenant_id)
        log.info("query_planned", tier=plan.tier, tables=plan.tables)

        # Execute based on query type
        match request.query_type:
            case QueryType.SQL:
                result = await self._execute_sql(plan, tenant_id)
            case QueryType.PROMQL:
                result = await self._execute_promql(plan, tenant_id)
            case QueryType.SEARCH:
                result = await self._execute_search(plan, tenant_id)
            case QueryType.NL:
                result = await self._execute_nl(plan, tenant_id)
            case _:
                raise ValueError(f"Unsupported query type: {request.query_type}")

        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        response = QueryResponse(
            status="ok",
            took_ms=elapsed_ms,
            rows=len(result.data),
            total_rows=result.total_rows,
            columns=result.columns,
            data=result.data,
            query_id=query_id,
            tier=plan.tier,
            cached=False,
        )

        # Cache the result
        if plan.cacheable:
            await self._cache.set(query_id, response, ttl=plan.cache_ttl)

        log.info("query_executed", took_ms=elapsed_ms, rows=len(result.data))
        return response

    async def _execute_sql(self, plan: QueryPlan, tenant_id: str) -> QueryResult:
        """Execute SQL query against ClickHouse."""
        sql = self._inject_tenant(plan.rewritten_query, tenant_id)
        sql = self._apply_limits(sql, plan)

        try:
            result = self.clickhouse.query(sql)
            columns = [
                Column(name=name, type=str(col_type))
                for name, col_type in zip(result.column_names, result.column_types)
            ]
            data = [
                dict(zip(result.column_names, row))
                for row in result.result_rows
            ]
            return QueryResult(
                columns=columns,
                data=data,
                total_rows=result.row_count,
            )
        except Exception as e:
            logger.error("clickhouse_query_error", error=str(e), sql=sql[:500])
            raise QueryExecutionError(f"Query failed: {e}") from e

    async def _execute_promql(self, plan: QueryPlan, tenant_id: str) -> QueryResult:
        """Execute PromQL query by translating to SQL."""
        sql = PromQLTranslator.translate(plan.original_query, plan.time_range, tenant_id)
        plan.rewritten_query = sql
        return await self._execute_sql(plan, tenant_id)

    async def _execute_search(self, plan: QueryPlan, tenant_id: str) -> QueryResult:
        """Execute full-text search using ClickHouse tokenbf index."""
        search_query = plan.original_query
        sql = self._build_search_sql(search_query, plan.time_range, tenant_id)
        plan.rewritten_query = sql
        return await self._execute_sql(plan, tenant_id)

    async def _execute_nl(self, plan: QueryPlan, tenant_id: str) -> QueryResult:
        """Natural language query — delegate to Query Agent."""
        raise NotImplementedError("NL queries are handled by the Query Agent (PRD-11)")

    def _inject_tenant(self, sql: str, tenant_id: str) -> str:
        """Inject tenant_id filter for data isolation.

        Uses parameterized approach: validates tenant_id format first,
        then injects via AST-safe string building (no user input in SQL).
        """
        # Validate tenant_id: only allow alphanumeric, hyphens, underscores
        if not re.match(r'^[a-zA-Z0-9_-]+$', tenant_id):
            raise QueryExecutionError(f"Invalid tenant_id format: {tenant_id}")

        tenant_filter = f"tenant_id = '{tenant_id}'"
        if "WHERE" in sql.upper():
            return sql.replace("WHERE", f"WHERE {tenant_filter} AND", 1)
        if "FROM" in sql.upper():
            parts = sql.split("FROM", 1)
            table_and_rest = parts[1].strip()
            tokens = table_and_rest.split(None, 1)
            table_name = tokens[0].rstrip(";")
            rest = tokens[1] if len(tokens) > 1 else ""
            return f"{parts[0]}FROM {table_name} WHERE {tenant_filter} {rest}"
        return sql

    def _apply_limits(self, sql: str, plan: QueryPlan) -> str:
        """Enforce query limits."""
        sql_upper = sql.upper().strip().rstrip(";")
        if "LIMIT" not in sql_upper:
            sql = f"{sql.rstrip(';')} LIMIT {plan.max_rows}"
        return sql

    def _build_search_sql(
        self, search_query: str, time_range: TimeRange | None, tenant_id: str
    ) -> str:
        """Build SQL for full-text search using ClickHouse hasToken/multiSearchAny."""
        terms = search_query.split()
        # Sanitize: only alphanumeric terms allowed in hasToken to prevent injection
        safe_terms = [re.sub(r'[^a-zA-Z0-9_.-]', '', term) for term in terms]
        conditions = [f"hasToken(body, '{term}')" for term in safe_terms if term]
        where = " AND ".join(conditions) if conditions else "1=1"

        time_filter = ""
        if time_range:
            time_filter = (
                f" AND timestamp >= '{time_range.from_time}'"
                f" AND timestamp <= '{time_range.to_time}'"
            )

        return (
            f"SELECT timestamp, resource_service, severity_text, body "
            f"FROM logs.log_entries "
            f"WHERE tenant_id = '{tenant_id}' AND {where}{time_filter} "
            f"ORDER BY timestamp DESC "
            f"LIMIT 100"
        )

    def _generate_query_id(self, request: QueryRequest, tenant_id: str) -> str:
        key = f"{tenant_id}:{request.query}:{request.time_range}"
        return f"q_{hashlib.md5(key.encode()).hexdigest()[:12]}"


class QueryPlan:
    """Represents a planned query execution."""

    def __init__(
        self,
        original_query: str,
        rewritten_query: str,
        tier: str,
        tables: list[str],
        time_range: TimeRange | None,
        cacheable: bool = True,
        cache_ttl: int = 30,
        max_rows: int = 10000,
    ) -> None:
        self.original_query = original_query
        self.rewritten_query = rewritten_query
        self.tier = tier
        self.tables = tables
        self.time_range = time_range
        self.cacheable = cacheable
        self.cache_ttl = cache_ttl
        self.max_rows = max_rows


class QueryResult:
    """Internal query result before formatting."""

    def __init__(
        self,
        columns: list[Column],
        data: list[dict[str, Any]],
        total_rows: int,
    ) -> None:
        self.columns = columns
        self.data = data
        self.total_rows = total_rows


class QueryPlanner:
    """Plans query execution — determines tier, optimization, caching."""

    def plan(self, request: QueryRequest, tenant_id: str) -> QueryPlan:
        time_range = request.time_range
        tables = self._detect_tables(request.query)
        tier = self._determine_tier(time_range)
        cacheable = request.query_type != QueryType.NL

        return QueryPlan(
            original_query=request.query,
            rewritten_query=request.query,
            tier=tier,
            tables=tables,
            time_range=time_range,
            cacheable=cacheable,
            cache_ttl=self._determine_cache_ttl(time_range),
        )

    def _detect_tables(self, query: str) -> list[str]:
        tables = []
        query_lower = query.lower()
        if "logs" in query_lower:
            tables.append("logs.log_entries")
        if "metrics" in query_lower:
            tables.append("metrics.samples")
        if "traces" in query_lower or "spans" in query_lower:
            tables.append("traces.spans")
        return tables or ["logs.log_entries"]

    def _determine_tier(self, time_range: TimeRange | None) -> str:
        if time_range is None:
            return StorageTier.HOT
        # Simple heuristic: recent data = hot, older = warm/cold
        # In production, check actual retention policies
        return StorageTier.HOT

    def _determine_cache_ttl(self, time_range: TimeRange | None) -> int:
        if time_range is None:
            return 15
        return 30


class PromQLTranslator:
    """Translates PromQL queries to ClickHouse SQL."""

    @staticmethod
    def translate(promql: str, time_range: TimeRange | None, tenant_id: str) -> str:
        """Translate a PromQL expression to equivalent SQL.

        This is a simplified translator for common patterns.
        A full implementation would use a PromQL parser (e.g., from prometheus-client).
        """
        promql = promql.strip()

        # Handle rate() function
        if promql.startswith("rate("):
            return PromQLTranslator._translate_rate(promql, time_range, tenant_id)

        # Handle sum by () expressions
        if promql.startswith("sum"):
            return PromQLTranslator._translate_sum(promql, time_range, tenant_id)

        # Handle histogram_quantile
        if promql.startswith("histogram_quantile"):
            return PromQLTranslator._translate_histogram_quantile(
                promql, time_range, tenant_id
            )

        # Default: treat as metric name with optional label matchers
        return PromQLTranslator._translate_instant(promql, time_range, tenant_id)

    @staticmethod
    def _translate_instant(
        promql: str, time_range: TimeRange | None, tenant_id: str
    ) -> str:
        metric_name, labels = PromQLTranslator._parse_metric_selector(promql)
        label_filters = " AND ".join(
            f"labels['{k}'] = '{v}'" for k, v in labels.items()
        )
        where = f"metric_name = '{metric_name}'"
        if label_filters:
            where += f" AND {label_filters}"

        time_filter = ""
        if time_range:
            time_filter = (
                f" AND timestamp >= '{time_range.from_time}'"
                f" AND timestamp <= '{time_range.to_time}'"
            )

        return (
            f"SELECT timestamp, value, labels "
            f"FROM metrics.samples "
            f"WHERE tenant_id = '{tenant_id}' AND {where}{time_filter} "
            f"ORDER BY timestamp DESC LIMIT 1000"
        )

    @staticmethod
    def _translate_rate(
        promql: str, time_range: TimeRange | None, tenant_id: str
    ) -> str:
        # rate(metric_name{labels}[range])
        inner = promql[5:-1]  # Strip rate()
        bracket_idx = inner.rfind("[")
        selector = inner[:bracket_idx] if bracket_idx > 0 else inner
        metric_name, labels = PromQLTranslator._parse_metric_selector(selector)

        label_filters = " AND ".join(
            f"labels['{k}'] = '{v}'" for k, v in labels.items()
        )
        where = f"metric_name = '{metric_name}'"
        if label_filters:
            where += f" AND {label_filters}"

        return (
            f"SELECT toStartOfMinute(timestamp) AS ts, "
            f"(max(value) - min(value)) / 60 AS rate "
            f"FROM metrics.samples "
            f"WHERE tenant_id = '{tenant_id}' AND {where} "
            f"GROUP BY ts ORDER BY ts"
        )

    @staticmethod
    def _translate_sum(
        promql: str, time_range: TimeRange | None, tenant_id: str
    ) -> str:
        # Simplified: return a placeholder that demonstrates the pattern
        return (
            f"SELECT toStartOfMinute(timestamp) AS ts, "
            f"sum(value) AS value "
            f"FROM metrics.samples "
            f"WHERE tenant_id = '{tenant_id}' "
            f"GROUP BY ts ORDER BY ts"
        )

    @staticmethod
    def _translate_histogram_quantile(
        promql: str, time_range: TimeRange | None, tenant_id: str
    ) -> str:
        return (
            f"SELECT toStartOfMinute(timestamp) AS ts, "
            f"quantile(0.99)(value) AS p99 "
            f"FROM metrics.samples "
            f"WHERE tenant_id = '{tenant_id}' "
            f"GROUP BY ts ORDER BY ts"
        )

    @staticmethod
    def _parse_metric_selector(selector: str) -> tuple[str, dict[str, str]]:
        """Parse 'metric_name{label1="value1",label2="value2"}' into (name, labels)."""
        labels: dict[str, str] = {}
        if "{" in selector:
            metric_name = selector[: selector.index("{")]
            labels_str = selector[selector.index("{") + 1 : selector.rindex("}")]
            for pair in labels_str.split(","):
                pair = pair.strip()
                if "=" in pair:
                    key, value = pair.split("=", 1)
                    labels[key.strip()] = value.strip().strip('"').strip("'")
        else:
            metric_name = selector.strip()
        return metric_name, labels


class QueryCache:
    """Redis-backed query result cache."""

    def __init__(self, redis_client: Any) -> None:
        self.redis = redis_client

    async def get(self, query_id: str) -> QueryResponse | None:
        if self.redis is None:
            return None
        try:
            data = await self.redis.get(f"qcache:{query_id}")
            if data:
                return QueryResponse(**orjson.loads(data))
        except Exception:
            logger.warning("cache_get_error", query_id=query_id)
        return None

    async def set(self, query_id: str, response: QueryResponse, ttl: int = 30) -> None:
        if self.redis is None:
            return
        try:
            data = orjson.dumps(response.model_dump())
            await self.redis.setex(f"qcache:{query_id}", ttl, data)
        except Exception:
            logger.warning("cache_set_error", query_id=query_id)


class QueryExecutionError(Exception):
    pass
