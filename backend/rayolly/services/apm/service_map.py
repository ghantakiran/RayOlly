"""Service dependency graph builder for APM.

Builds and maintains a real-time service dependency graph,
comparable to Dynatrace SmartScape or Datadog Service Map.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------

class ClickHouseClient(Protocol):
    """Minimal ClickHouse async client interface."""

    async def execute(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]: ...


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ServiceType(str, Enum):
    WEB = "web"
    DATABASE = "database"
    CACHE = "cache"
    QUEUE = "queue"
    EXTERNAL = "external"


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"


class TopologyChangeType(str, Enum):
    NEW_SERVICE = "new_service"
    REMOVED_SERVICE = "removed_service"
    NEW_DEPENDENCY = "new_dependency"
    REMOVED_DEPENDENCY = "removed_dependency"
    HEALTH_CHANGED = "health_changed"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ServiceMetrics:
    request_rate: float = 0.0
    error_rate: float = 0.0
    p50_latency: float = 0.0
    p99_latency: float = 0.0


@dataclass
class ServiceNode:
    service_name: str
    service_type: ServiceType
    health_status: HealthStatus
    metrics: ServiceMetrics
    dependencies: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ServiceEdge:
    source: str
    target: str
    protocol: str  # http, grpc, sql, redis, kafka
    request_rate: float = 0.0
    error_rate: float = 0.0
    avg_latency_ms: float = 0.0


@dataclass
class ServiceMap:
    nodes: list[ServiceNode] = field(default_factory=list)
    edges: list[ServiceEdge] = field(default_factory=list)
    last_updated: datetime = field(default_factory=datetime.utcnow)


@dataclass
class EndpointSummary:
    operation: str
    request_rate: float
    error_rate: float
    p50_latency: float
    p99_latency: float


@dataclass
class ErrorSummary:
    message: str
    count: int
    first_seen: datetime
    last_seen: datetime


@dataclass
class DeploymentRecord:
    version: str
    deployed_at: datetime
    deployer: str


@dataclass
class ServiceDetail:
    service_name: str
    service_type: ServiceType
    health_status: HealthStatus
    metrics: ServiceMetrics
    top_endpoints: list[EndpointSummary]
    dependencies: list[str]
    dependents: list[str]
    recent_errors: list[ErrorSummary]
    deployment_history: list[DeploymentRecord]


@dataclass(frozen=True)
class TopologyChange:
    change_type: TopologyChangeType
    subject: str  # service name or "source -> target" for edges
    details: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HEALTH_THRESHOLDS = {
    "error_rate_critical": 0.05,
    "error_rate_degraded": 0.01,
    "p99_critical_ms": 5000,
    "p99_degraded_ms": 1000,
}


def _classify_health(error_rate: float, p99_latency: float) -> HealthStatus:
    if (
        error_rate >= _HEALTH_THRESHOLDS["error_rate_critical"]
        or p99_latency >= _HEALTH_THRESHOLDS["p99_critical_ms"]
    ):
        return HealthStatus.CRITICAL
    if (
        error_rate >= _HEALTH_THRESHOLDS["error_rate_degraded"]
        or p99_latency >= _HEALTH_THRESHOLDS["p99_degraded_ms"]
    ):
        return HealthStatus.DEGRADED
    return HealthStatus.HEALTHY


def _infer_service_type(service_name: str, protocols: set[str]) -> ServiceType:
    name_lower = service_name.lower()
    if any(k in name_lower for k in ("postgres", "mysql", "mongo", "clickhouse", "db")):
        return ServiceType.DATABASE
    if any(k in name_lower for k in ("redis", "memcached", "cache")):
        return ServiceType.CACHE
    if any(k in name_lower for k in ("kafka", "rabbitmq", "sqs", "queue", "nats")):
        return ServiceType.QUEUE
    if "sql" in protocols:
        return ServiceType.DATABASE
    if "redis" in protocols:
        return ServiceType.CACHE
    if "kafka" in protocols:
        return ServiceType.QUEUE
    return ServiceType.WEB


# ---------------------------------------------------------------------------
# ServiceMapBuilder
# ---------------------------------------------------------------------------

class ServiceMapBuilder:
    """Builds a real-time service dependency graph from trace data."""

    async def build_from_traces(
        self,
        tenant_id: str,
        time_range: tuple[datetime, datetime],
        clickhouse_client: ClickHouseClient,
    ) -> ServiceMap:
        """Query traces.spans and traces.service_edges to build the service map."""

        start, end = time_range

        # ---- Fetch per-service metrics ----
        service_rows = await clickhouse_client.execute(
            """
            SELECT
                service_name,
                count() AS request_count,
                countIf(status_code >= 400) / count() AS error_rate,
                quantile(0.50)(duration_ms) AS p50,
                quantile(0.99)(duration_ms) AS p99
            FROM traces.spans
            WHERE tenant_id = %(tenant_id)s
              AND timestamp BETWEEN %(start)s AND %(end)s
              AND parent_span_id = ''
            GROUP BY service_name
            """,
            {"tenant_id": tenant_id, "start": start, "end": end},
        )

        # ---- Fetch edges ----
        edge_rows = await clickhouse_client.execute(
            """
            SELECT
                source_service,
                target_service,
                protocol,
                count() AS request_count,
                countIf(status_code >= 400) / count() AS error_rate,
                avg(duration_ms) AS avg_latency_ms
            FROM traces.service_edges
            WHERE tenant_id = %(tenant_id)s
              AND timestamp BETWEEN %(start)s AND %(end)s
            GROUP BY source_service, target_service, protocol
            """,
            {"tenant_id": tenant_id, "start": start, "end": end},
        )

        # Build lookup: service -> set of protocols it is *targeted* with
        target_protocols: dict[str, set[str]] = {}
        deps_map: dict[str, list[str]] = {}
        for row in edge_rows:
            target = row["target_service"]
            target_protocols.setdefault(target, set()).add(row["protocol"])
            deps_map.setdefault(row["source_service"], []).append(target)

        interval_seconds = max((end - start).total_seconds(), 1)

        nodes: list[ServiceNode] = []
        for row in service_rows:
            svc = row["service_name"]
            error_rate = float(row["error_rate"])
            p99 = float(row["p99"])
            metrics = ServiceMetrics(
                request_rate=float(row["request_count"]) / interval_seconds,
                error_rate=error_rate,
                p50_latency=float(row["p50"]),
                p99_latency=p99,
            )
            nodes.append(
                ServiceNode(
                    service_name=svc,
                    service_type=_infer_service_type(svc, target_protocols.get(svc, set())),
                    health_status=_classify_health(error_rate, p99),
                    metrics=metrics,
                    dependencies=deps_map.get(svc, []),
                )
            )

        edges: list[ServiceEdge] = [
            ServiceEdge(
                source=row["source_service"],
                target=row["target_service"],
                protocol=row["protocol"],
                request_rate=float(row["request_count"]) / interval_seconds,
                error_rate=float(row["error_rate"]),
                avg_latency_ms=float(row["avg_latency_ms"]),
            )
            for row in edge_rows
        ]

        logger.info(
            "Built service map for tenant=%s: %d nodes, %d edges",
            tenant_id,
            len(nodes),
            len(edges),
        )

        return ServiceMap(nodes=nodes, edges=edges, last_updated=datetime.utcnow())

    async def get_service_detail(
        self,
        tenant_id: str,
        service_name: str,
        time_range: tuple[datetime, datetime],
        clickhouse: ClickHouseClient,
    ) -> ServiceDetail:
        """Return detailed information about a single service."""

        start, end = time_range

        # Overview metrics
        overview_rows = await clickhouse.execute(
            """
            SELECT
                count() AS request_count,
                countIf(status_code >= 400) / count() AS error_rate,
                quantile(0.50)(duration_ms) AS p50,
                quantile(0.99)(duration_ms) AS p99
            FROM traces.spans
            WHERE tenant_id = %(tenant_id)s
              AND service_name = %(service)s
              AND timestamp BETWEEN %(start)s AND %(end)s
              AND parent_span_id = ''
            """,
            {"tenant_id": tenant_id, "service": service_name, "start": start, "end": end},
        )

        interval_seconds = max((end - start).total_seconds(), 1)
        ov = overview_rows[0] if overview_rows else {}
        error_rate = float(ov.get("error_rate", 0))
        p99 = float(ov.get("p99", 0))
        metrics = ServiceMetrics(
            request_rate=float(ov.get("request_count", 0)) / interval_seconds,
            error_rate=error_rate,
            p50_latency=float(ov.get("p50", 0)),
            p99_latency=p99,
        )

        # Top endpoints
        ep_rows = await clickhouse.execute(
            """
            SELECT
                operation_name,
                count() AS req,
                countIf(status_code >= 400) / count() AS err,
                quantile(0.50)(duration_ms) AS p50,
                quantile(0.99)(duration_ms) AS p99
            FROM traces.spans
            WHERE tenant_id = %(tenant_id)s
              AND service_name = %(service)s
              AND timestamp BETWEEN %(start)s AND %(end)s
              AND parent_span_id = ''
            GROUP BY operation_name
            ORDER BY req DESC
            LIMIT 20
            """,
            {"tenant_id": tenant_id, "service": service_name, "start": start, "end": end},
        )
        top_endpoints = [
            EndpointSummary(
                operation=r["operation_name"],
                request_rate=float(r["req"]) / interval_seconds,
                error_rate=float(r["err"]),
                p50_latency=float(r["p50"]),
                p99_latency=float(r["p99"]),
            )
            for r in ep_rows
        ]

        # Dependencies and dependents
        dep_rows = await clickhouse.execute(
            """
            SELECT DISTINCT target_service
            FROM traces.service_edges
            WHERE tenant_id = %(tenant_id)s
              AND source_service = %(service)s
              AND timestamp BETWEEN %(start)s AND %(end)s
            """,
            {"tenant_id": tenant_id, "service": service_name, "start": start, "end": end},
        )
        dependencies = [r["target_service"] for r in dep_rows]

        dnt_rows = await clickhouse.execute(
            """
            SELECT DISTINCT source_service
            FROM traces.service_edges
            WHERE tenant_id = %(tenant_id)s
              AND target_service = %(service)s
              AND timestamp BETWEEN %(start)s AND %(end)s
            """,
            {"tenant_id": tenant_id, "service": service_name, "start": start, "end": end},
        )
        dependents = [r["source_service"] for r in dnt_rows]

        # Recent errors
        err_rows = await clickhouse.execute(
            """
            SELECT
                exception_message,
                count() AS cnt,
                min(timestamp) AS first_seen,
                max(timestamp) AS last_seen
            FROM traces.spans
            WHERE tenant_id = %(tenant_id)s
              AND service_name = %(service)s
              AND status_code >= 400
              AND timestamp BETWEEN %(start)s AND %(end)s
            GROUP BY exception_message
            ORDER BY cnt DESC
            LIMIT 10
            """,
            {"tenant_id": tenant_id, "service": service_name, "start": start, "end": end},
        )
        recent_errors = [
            ErrorSummary(
                message=r["exception_message"],
                count=int(r["cnt"]),
                first_seen=r["first_seen"],
                last_seen=r["last_seen"],
            )
            for r in err_rows
        ]

        # Deployment history
        deploy_rows = await clickhouse.execute(
            """
            SELECT version, deployed_at, deployer
            FROM apm.deployments
            WHERE tenant_id = %(tenant_id)s
              AND service_name = %(service)s
            ORDER BY deployed_at DESC
            LIMIT 10
            """,
            {"tenant_id": tenant_id, "service": service_name},
        )
        deployment_history = [
            DeploymentRecord(
                version=r["version"],
                deployed_at=r["deployed_at"],
                deployer=r["deployer"],
            )
            for r in deploy_rows
        ]

        # Infer type from dependency protocols
        proto_rows = await clickhouse.execute(
            """
            SELECT DISTINCT protocol
            FROM traces.service_edges
            WHERE tenant_id = %(tenant_id)s
              AND target_service = %(service)s
              AND timestamp BETWEEN %(start)s AND %(end)s
            """,
            {"tenant_id": tenant_id, "service": service_name, "start": start, "end": end},
        )
        protocols = {r["protocol"] for r in proto_rows}

        return ServiceDetail(
            service_name=service_name,
            service_type=_infer_service_type(service_name, protocols),
            health_status=_classify_health(error_rate, p99),
            metrics=metrics,
            top_endpoints=top_endpoints,
            dependencies=dependencies,
            dependents=dependents,
            recent_errors=recent_errors,
            deployment_history=deployment_history,
        )

    async def detect_topology_changes(
        self,
        tenant_id: str,
        current_map: ServiceMap,
        previous_map: ServiceMap,
    ) -> list[TopologyChange]:
        """Compare two service maps and return topology changes."""

        _ = tenant_id  # reserved for future audit logging
        changes: list[TopologyChange] = []

        current_services = {n.service_name for n in current_map.nodes}
        previous_services = {n.service_name for n in previous_map.nodes}

        for svc in current_services - previous_services:
            changes.append(TopologyChange(TopologyChangeType.NEW_SERVICE, svc))
        for svc in previous_services - current_services:
            changes.append(TopologyChange(TopologyChangeType.REMOVED_SERVICE, svc))

        current_edges = {(e.source, e.target) for e in current_map.edges}
        previous_edges = {(e.source, e.target) for e in previous_map.edges}

        for src, tgt in current_edges - previous_edges:
            changes.append(
                TopologyChange(TopologyChangeType.NEW_DEPENDENCY, f"{src} -> {tgt}")
            )
        for src, tgt in previous_edges - current_edges:
            changes.append(
                TopologyChange(TopologyChangeType.REMOVED_DEPENDENCY, f"{src} -> {tgt}")
            )

        prev_health = {n.service_name: n.health_status for n in previous_map.nodes}
        for node in current_map.nodes:
            old = prev_health.get(node.service_name)
            if old is not None and old != node.health_status:
                changes.append(
                    TopologyChange(
                        TopologyChangeType.HEALTH_CHANGED,
                        node.service_name,
                        details=f"{old.value} -> {node.health_status.value}",
                    )
                )

        return changes
