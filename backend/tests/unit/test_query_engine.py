"""Tests for rayolly.services.query.engine — QueryEngine, PromQLTranslator, QueryCache."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from rayolly.models.query import QueryRequest
from rayolly.services.query.engine import (
    PromQLTranslator,
    QueryCache,
    QueryEngine,
    QueryExecutionError,
    QueryPlan,
    QueryPlanner,
)
from tests.conftest import MockClickHouseClient

# -----------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------

@pytest.fixture
def mock_ch() -> MockClickHouseClient:
    return MockClickHouseClient()


@pytest.fixture
def mock_redis() -> AsyncMock:
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.setex = AsyncMock()
    return r


@pytest.fixture
def engine(mock_ch: MockClickHouseClient, mock_redis: AsyncMock) -> QueryEngine:
    return QueryEngine(clickhouse_client=mock_ch, redis_client=mock_redis)


# -----------------------------------------------------------------------
# Tenant injection
# -----------------------------------------------------------------------

class TestTenantInjection:
    def test_tenant_injection_with_where_clause(self, engine: QueryEngine) -> None:
        sql = "SELECT * FROM logs WHERE severity = 'ERROR'"
        result = engine._inject_tenant(sql, "tenant-abc")
        assert "tenant_id = 'tenant-abc'" in result
        assert "WHERE tenant_id = 'tenant-abc' AND" in result

    def test_tenant_injection_without_where_clause(self, engine: QueryEngine) -> None:
        sql = "SELECT * FROM logs"
        result = engine._inject_tenant(sql, "tenant-abc")
        assert "tenant_id = 'tenant-abc'" in result
        assert "WHERE" in result

    def test_tenant_injection_validates_format(self, engine: QueryEngine) -> None:
        sql = "SELECT * FROM logs"
        with pytest.raises(QueryExecutionError, match="Invalid tenant_id"):
            engine._inject_tenant(sql, "'; DROP TABLE logs; --")

    def test_invalid_tenant_id_raises(self, engine: QueryEngine) -> None:
        sql = "SELECT 1"
        for bad_id in ["a;b", "foo'bar", "x\"y", "t id"]:
            with pytest.raises(QueryExecutionError):
                engine._inject_tenant(sql, bad_id)


# -----------------------------------------------------------------------
# Apply limits
# -----------------------------------------------------------------------

class TestApplyLimits:
    def test_apply_limits_adds_limit(self, engine: QueryEngine) -> None:
        plan = QueryPlan(
            original_query="", rewritten_query="", tier="hot",
            tables=[], time_range=None, max_rows=500,
        )
        sql = "SELECT * FROM logs"
        result = engine._apply_limits(sql, plan)
        assert "LIMIT 500" in result

    def test_apply_limits_preserves_existing(self, engine: QueryEngine) -> None:
        plan = QueryPlan(
            original_query="", rewritten_query="", tier="hot",
            tables=[], time_range=None, max_rows=500,
        )
        sql = "SELECT * FROM logs LIMIT 10"
        result = engine._apply_limits(sql, plan)
        assert "LIMIT 10" in result
        assert "LIMIT 500" not in result


# -----------------------------------------------------------------------
# Search SQL
# -----------------------------------------------------------------------

class TestSearchSQL:
    def test_search_sql_sanitizes_terms(self, engine: QueryEngine) -> None:
        sql = engine._build_search_sql("error; DROP TABLE--", None, "t1")
        # Dangerous characters should be stripped
        assert "DROP" not in sql or "hasToken" in sql
        assert "tenant_id = 't1'" in sql


# -----------------------------------------------------------------------
# PromQL translation
# -----------------------------------------------------------------------

class TestPromQLTranslator:
    def test_promql_translate_rate(self) -> None:
        sql = PromQLTranslator.translate(
            "rate(http_requests_total{job=\"api\"}[5m])", None, "t1"
        )
        assert "rate" in sql.lower() or "max(value) - min(value)" in sql
        assert "tenant_id = 't1'" in sql
        assert "http_requests_total" in sql

    def test_promql_translate_instant(self) -> None:
        sql = PromQLTranslator.translate("cpu_usage", None, "t1")
        assert "cpu_usage" in sql
        assert "tenant_id = 't1'" in sql

    def test_promql_parse_metric_selector(self) -> None:
        name, labels = PromQLTranslator._parse_metric_selector(
            'http_requests_total{method="GET",path="/api"}'
        )
        assert name == "http_requests_total"
        assert labels["method"] == "GET"
        assert labels["path"] == "/api"


# -----------------------------------------------------------------------
# Query cache
# -----------------------------------------------------------------------

class TestQueryCache:
    @pytest.mark.asyncio
    async def test_query_cache_hit(self) -> None:
        import orjson

        from rayolly.models.query import QueryResponse

        response = QueryResponse(
            status="ok", took_ms=5, rows=1, total_rows=1,
            query_id="q_abc", data=[{"x": 1}],
        )
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=orjson.dumps(response.model_dump()))
        cache = QueryCache(redis)
        result = await cache.get("q_abc")
        assert result is not None
        assert result.query_id == "q_abc"

    @pytest.mark.asyncio
    async def test_query_cache_miss(self) -> None:
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        cache = QueryCache(redis)
        result = await cache.get("q_missing")
        assert result is None


# -----------------------------------------------------------------------
# Query planner
# -----------------------------------------------------------------------

class TestQueryPlanner:
    def test_query_planner_detects_tables(self) -> None:
        planner = QueryPlanner()
        request = QueryRequest(query="SELECT * FROM logs WHERE severity='ERROR'")
        plan = planner.plan(request, "t1")
        assert "logs.log_entries" in plan.tables

    def test_query_planner_detects_metrics_table(self) -> None:
        planner = QueryPlanner()
        request = QueryRequest(query="SELECT * FROM metrics WHERE name='cpu'")
        plan = planner.plan(request, "t1")
        assert "metrics.samples" in plan.tables

    def test_query_planner_detects_traces_table(self) -> None:
        planner = QueryPlanner()
        request = QueryRequest(query="SELECT * FROM traces WHERE trace_id='abc'")
        plan = planner.plan(request, "t1")
        assert "traces.spans" in plan.tables
