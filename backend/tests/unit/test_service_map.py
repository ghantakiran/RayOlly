"""Tests for rayolly.services.apm.service_map — ServiceMapBuilder."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from rayolly.services.apm.service_map import (
    HealthStatus,
    ServiceEdge,
    ServiceMap,
    ServiceMapBuilder,
    ServiceMetrics,
    ServiceNode,
    ServiceType,
    TopologyChangeType,
    _classify_health,
    _infer_service_type,
)

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

def _time_range() -> tuple[datetime, datetime]:
    end = datetime.utcnow()
    start = end - timedelta(hours=1)
    return start, end


def _mock_clickhouse(service_rows: list[dict], edge_rows: list[dict]) -> AsyncMock:
    """Return a mock ClickHouse client that returns service_rows then edge_rows."""
    ch = AsyncMock()
    ch.execute = AsyncMock(side_effect=[service_rows, edge_rows])
    return ch


# -----------------------------------------------------------------------
# Health classification
# -----------------------------------------------------------------------

class TestClassifyHealth:
    def test_healthy(self) -> None:
        assert _classify_health(0.001, 200) == HealthStatus.HEALTHY

    def test_degraded_by_error_rate(self) -> None:
        assert _classify_health(0.02, 200) == HealthStatus.DEGRADED

    def test_degraded_by_latency(self) -> None:
        assert _classify_health(0.001, 2000) == HealthStatus.DEGRADED

    def test_critical_by_error_rate(self) -> None:
        assert _classify_health(0.06, 200) == HealthStatus.CRITICAL

    def test_critical_by_latency(self) -> None:
        assert _classify_health(0.001, 6000) == HealthStatus.CRITICAL


# -----------------------------------------------------------------------
# Service type inference
# -----------------------------------------------------------------------

class TestInferServiceType:
    def test_database_by_name(self) -> None:
        assert _infer_service_type("postgres-primary", set()) == ServiceType.DATABASE

    def test_cache_by_name(self) -> None:
        assert _infer_service_type("redis-sessions", set()) == ServiceType.CACHE

    def test_queue_by_name(self) -> None:
        assert _infer_service_type("kafka-events", set()) == ServiceType.QUEUE

    def test_database_by_protocol(self) -> None:
        assert _infer_service_type("backend-svc", {"sql"}) == ServiceType.DATABASE

    def test_web_default(self) -> None:
        assert _infer_service_type("api-gateway", {"http"}) == ServiceType.WEB


# -----------------------------------------------------------------------
# build_from_traces
# -----------------------------------------------------------------------

class TestBuildFromTraces:
    @pytest.mark.asyncio
    async def test_build_service_map(self) -> None:
        service_rows = [
            {
                "service_name": "api-gateway",
                "request_count": 1000,
                "error_rate": 0.002,
                "p50": 50.0,
                "p99": 200.0,
            },
            {
                "service_name": "postgres-db",
                "request_count": 500,
                "error_rate": 0.0,
                "p50": 5.0,
                "p99": 20.0,
            },
        ]
        edge_rows = [
            {
                "source_service": "api-gateway",
                "target_service": "postgres-db",
                "protocol": "sql",
                "request_count": 500,
                "error_rate": 0.0,
                "avg_latency_ms": 10.0,
            },
        ]
        ch = _mock_clickhouse(service_rows, edge_rows)
        builder = ServiceMapBuilder()
        smap = await builder.build_from_traces("t1", _time_range(), ch)

        assert isinstance(smap, ServiceMap)
        assert len(smap.nodes) == 2
        assert len(smap.edges) == 1
        # postgres should be identified as DATABASE
        db_node = next(n for n in smap.nodes if n.service_name == "postgres-db")
        assert db_node.service_type == ServiceType.DATABASE

    @pytest.mark.asyncio
    async def test_empty_traces(self) -> None:
        ch = _mock_clickhouse([], [])
        builder = ServiceMapBuilder()
        smap = await builder.build_from_traces("t1", _time_range(), ch)
        assert smap.nodes == []
        assert smap.edges == []


# -----------------------------------------------------------------------
# Topology change detection
# -----------------------------------------------------------------------

class TestTopologyChanges:
    @pytest.mark.asyncio
    async def test_detect_new_service(self) -> None:
        previous = ServiceMap(nodes=[], edges=[])
        current = ServiceMap(
            nodes=[
                ServiceNode(
                    service_name="new-svc",
                    service_type=ServiceType.WEB,
                    health_status=HealthStatus.HEALTHY,
                    metrics=ServiceMetrics(),
                )
            ],
            edges=[],
        )
        builder = ServiceMapBuilder()
        changes = await builder.detect_topology_changes("t1", current, previous)
        assert any(c.change_type == TopologyChangeType.NEW_SERVICE for c in changes)

    @pytest.mark.asyncio
    async def test_detect_removed_service(self) -> None:
        previous = ServiceMap(
            nodes=[
                ServiceNode(
                    service_name="old-svc",
                    service_type=ServiceType.WEB,
                    health_status=HealthStatus.HEALTHY,
                    metrics=ServiceMetrics(),
                )
            ],
            edges=[],
        )
        current = ServiceMap(nodes=[], edges=[])
        builder = ServiceMapBuilder()
        changes = await builder.detect_topology_changes("t1", current, previous)
        assert any(c.change_type == TopologyChangeType.REMOVED_SERVICE for c in changes)

    @pytest.mark.asyncio
    async def test_detect_health_change(self) -> None:
        node_prev = ServiceNode(
            service_name="api",
            service_type=ServiceType.WEB,
            health_status=HealthStatus.HEALTHY,
            metrics=ServiceMetrics(),
        )
        node_curr = ServiceNode(
            service_name="api",
            service_type=ServiceType.WEB,
            health_status=HealthStatus.CRITICAL,
            metrics=ServiceMetrics(),
        )
        previous = ServiceMap(nodes=[node_prev], edges=[])
        current = ServiceMap(nodes=[node_curr], edges=[])
        builder = ServiceMapBuilder()
        changes = await builder.detect_topology_changes("t1", current, previous)
        assert any(c.change_type == TopologyChangeType.HEALTH_CHANGED for c in changes)

    @pytest.mark.asyncio
    async def test_detect_new_dependency(self) -> None:
        node = ServiceNode(
            service_name="api",
            service_type=ServiceType.WEB,
            health_status=HealthStatus.HEALTHY,
            metrics=ServiceMetrics(),
        )
        previous = ServiceMap(nodes=[node], edges=[])
        current = ServiceMap(
            nodes=[node],
            edges=[ServiceEdge(source="api", target="db", protocol="sql")],
        )
        builder = ServiceMapBuilder()
        changes = await builder.detect_topology_changes("t1", current, previous)
        assert any(c.change_type == TopologyChangeType.NEW_DEPENDENCY for c in changes)
