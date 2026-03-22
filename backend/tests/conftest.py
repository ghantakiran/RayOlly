"""Shared test fixtures for RayOlly backend test suite."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# ClickHouse mock
# ---------------------------------------------------------------------------

class MockClickHouseResult:
    """Configurable result object returned by MockClickHouseClient.query()."""

    def __init__(
        self,
        result_rows: list[tuple] | None = None,
        column_names: list[str] | None = None,
        column_types: list[str] | None = None,
        row_count: int | None = None,
    ) -> None:
        self.result_rows = result_rows or []
        self.column_names = column_names or []
        self.column_types = column_types or []
        self.row_count = row_count if row_count is not None else len(self.result_rows)


class MockClickHouseClient:
    """Mock ClickHouse client with configurable query results."""

    def __init__(self) -> None:
        self._results: list[MockClickHouseResult] = []
        self._default_result = MockClickHouseResult()
        self.queries: list[str] = []

    def set_results(self, results: list[MockClickHouseResult]) -> None:
        self._results = list(results)

    def set_default_result(self, result: MockClickHouseResult) -> None:
        self._default_result = result

    def query(self, sql: str) -> MockClickHouseResult:
        self.queries.append(sql)
        if self._results:
            return self._results.pop(0)
        return self._default_result

    async def execute(
        self, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        self.queries.append(query)
        if self._results:
            r = self._results.pop(0)
            return [
                dict(zip(r.column_names, row)) for row in r.result_rows
            ]
        return []

    def insert(
        self,
        table: str,
        rows: list[tuple],
        column_names: list[str] | None = None,
    ) -> None:
        pass


@pytest.fixture
def mock_clickhouse() -> MockClickHouseClient:
    return MockClickHouseClient()


# ---------------------------------------------------------------------------
# NATS mock
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_nats() -> MagicMock:
    nc = MagicMock()
    nc.is_connected = True
    nc.stats = {"out_bytes": 0, "in_bytes": 0}

    js = AsyncMock()
    js.publish = AsyncMock()
    js.subscribe = AsyncMock()
    nc.jetstream.return_value = js

    return nc


# ---------------------------------------------------------------------------
# Redis mock
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_redis() -> AsyncMock:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    redis.setex = AsyncMock()
    redis.delete = AsyncMock()
    return redis


# ---------------------------------------------------------------------------
# Tenant ID
# ---------------------------------------------------------------------------

@pytest.fixture
def test_tenant_id() -> str:
    return "test-tenant-001"


# ---------------------------------------------------------------------------
# Sample telemetry records
# ---------------------------------------------------------------------------

def _now_ns() -> int:
    return int(time.time() * 1_000_000_000)


@pytest.fixture
def sample_log_record() -> dict[str, Any]:
    return {
        "timestamp": _now_ns(),
        "body": "User login successful for user_id=42",
        "severity": "INFO",
        "attributes": {"http.method": "POST", "http.path": "/login"},
        "resource_attributes": {"service.name": "auth-service"},
        "trace_id": None,
        "span_id": None,
        "stream": "default",
    }


@pytest.fixture
def sample_metric() -> dict[str, Any]:
    return {
        "name": "http_request_duration_seconds",
        "type": "histogram",
        "value": 0.123,
        "timestamp": _now_ns(),
        "labels": {"method": "GET", "path": "/api/v1/logs"},
        "resource_attributes": {"service.name": "api-gateway"},
        "unit": "seconds",
        "description": "HTTP request duration",
    }


@pytest.fixture
def sample_span() -> dict[str, Any]:
    ts = _now_ns()
    return {
        "trace_id": "abcdef1234567890abcdef1234567890",
        "span_id": "1234567890abcdef",
        "parent_span_id": None,
        "name": "GET /api/v1/logs",
        "kind": "SERVER",
        "start_time": ts,
        "end_time": ts + 50_000_000,  # +50ms
        "attributes": {"http.status_code": 200},
        "resource_attributes": {"service.name": "api-gateway"},
        "status_code": "OK",
        "status_message": "",
        "events": [],
        "links": [],
    }
