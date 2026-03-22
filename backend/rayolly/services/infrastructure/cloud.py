"""Cloud infrastructure monitoring.

Tracks cloud resources across AWS, GCP, and Azure including inventory,
metrics, cost data, and topology, comparable to Datadog Cloud Infrastructure
and Dynatrace cloud monitoring.
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

    async def execute(
        self, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]: ...


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class CloudProvider(str, Enum):
    AWS = "aws"
    GCP = "gcp"
    AZURE = "azure"


class ResourceStatus(str, Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    TERMINATED = "terminated"
    PENDING = "pending"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CloudResource:
    provider: CloudProvider
    resource_type: str  # ec2, rds, s3, lambda, gce, cloud_sql, etc.
    resource_id: str
    name: str
    region: str
    tags: dict[str, str] = field(default_factory=dict)
    status: ResourceStatus = ResourceStatus.RUNNING
    metrics: dict[str, float] = field(default_factory=dict)
    account: str = ""
    created_at: datetime | None = None
    instance_type: str = ""
    vpc_id: str = ""


@dataclass
class CloudCostData:
    provider: CloudProvider
    service: str
    resource_id: str
    daily_cost: float
    monthly_projected: float
    currency: str = "USD"
    account: str = ""
    region: str = ""
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class CostSummary:
    total_daily: float
    total_monthly_projected: float
    currency: str
    by_service: list[ServiceCost]
    by_resource: list[CloudCostData]


@dataclass
class ServiceCost:
    service: str
    daily_cost: float
    monthly_projected: float
    resource_count: int
    change_pct: float = 0.0  # vs previous period


@dataclass
class IdleResource:
    resource: CloudResource
    idle_reason: str  # low_cpu, no_connections, no_requests, etc.
    avg_utilization_pct: float
    estimated_monthly_savings: float
    recommendation: str


@dataclass
class TopologyNode:
    resource_id: str
    resource_type: str
    name: str
    status: ResourceStatus


@dataclass
class TopologyEdge:
    source_id: str
    target_id: str
    relationship: str  # connects_to, depends_on, routes_to


@dataclass
class CloudTopology:
    provider: CloudProvider
    region: str
    nodes: list[TopologyNode]
    edges: list[TopologyEdge]


@dataclass
class TimeSeriesPoint:
    timestamp: datetime
    value: float


@dataclass
class ResourceTimeSeries:
    metric_name: str
    resource_id: str
    data: list[TimeSeriesPoint]


# ---------------------------------------------------------------------------
# CloudService
# ---------------------------------------------------------------------------

class CloudService:
    """Service layer for cloud infrastructure monitoring."""

    async def list_resources(
        self,
        tenant_id: str,
        provider: CloudProvider | None = None,
        resource_type: str | None = None,
        clickhouse: ClickHouseClient | None = None,
    ) -> list[CloudResource]:
        """List cloud resources with optional provider and type filters."""
        assert clickhouse is not None

        where_clauses = ["tenant_id = %(tenant_id)s"]
        params: dict[str, Any] = {"tenant_id": tenant_id}

        if provider:
            where_clauses.append("provider = %(provider)s")
            params["provider"] = provider.value
        if resource_type:
            where_clauses.append("resource_type = %(resource_type)s")
            params["resource_type"] = resource_type

        where = " AND ".join(where_clauses)

        rows = await clickhouse.execute(
            f"""
            SELECT
                provider, resource_type, resource_id, name, region,
                tags, status, account, created_at, instance_type, vpc_id,
                metrics
            FROM infra.cloud_resources
            WHERE {where}
              AND timestamp = (
                  SELECT max(timestamp)
                  FROM infra.cloud_resources
                  WHERE {where}
              )
            ORDER BY provider, resource_type, name
            """,
            params,
        )

        resources = [
            CloudResource(
                provider=CloudProvider(r.get("provider", "aws")),
                resource_type=r.get("resource_type", ""),
                resource_id=r["resource_id"],
                name=r.get("name", ""),
                region=r.get("region", ""),
                tags=r.get("tags", {}),
                status=ResourceStatus(r.get("status", "running")),
                metrics=r.get("metrics", {}),
                account=r.get("account", ""),
                created_at=r.get("created_at"),
                instance_type=r.get("instance_type", ""),
                vpc_id=r.get("vpc_id", ""),
            )
            for r in rows
        ]

        logger.info(
            "Listed %d cloud resources for tenant=%s provider=%s type=%s",
            len(resources),
            tenant_id,
            provider.value if provider else "all",
            resource_type or "all",
        )
        return resources

    async def get_resource_metrics(
        self,
        tenant_id: str,
        resource_id: str,
        metric_names: list[str],
        time_range: tuple[datetime, datetime],
        clickhouse: ClickHouseClient,
    ) -> list[ResourceTimeSeries]:
        """Return time-series metrics for a cloud resource."""
        start, end = time_range

        results: list[ResourceTimeSeries] = []

        for metric_name in metric_names:
            rows = await clickhouse.execute(
                """
                SELECT timestamp, value
                FROM infra.cloud_resource_metrics
                WHERE tenant_id = %(tenant_id)s
                  AND resource_id = %(resource_id)s
                  AND metric_name = %(metric_name)s
                  AND timestamp BETWEEN %(start)s AND %(end)s
                ORDER BY timestamp
                """,
                {
                    "tenant_id": tenant_id,
                    "resource_id": resource_id,
                    "metric_name": metric_name,
                    "start": start,
                    "end": end,
                },
            )

            points = [
                TimeSeriesPoint(
                    timestamp=r["timestamp"], value=float(r.get("value", 0))
                )
                for r in rows
            ]

            results.append(
                ResourceTimeSeries(
                    metric_name=metric_name,
                    resource_id=resource_id,
                    data=points,
                )
            )

        logger.info(
            "Fetched %d metric series for tenant=%s resource=%s",
            len(results),
            tenant_id,
            resource_id,
        )
        return results

    async def get_cost_summary(
        self,
        tenant_id: str,
        provider: CloudProvider | None = None,
        time_range: tuple[datetime, datetime] | None = None,
        clickhouse: ClickHouseClient | None = None,
    ) -> CostSummary:
        """Return cost summary grouped by service and resource."""
        assert clickhouse is not None

        where_clauses = ["tenant_id = %(tenant_id)s"]
        params: dict[str, Any] = {"tenant_id": tenant_id}

        if provider:
            where_clauses.append("provider = %(provider)s")
            params["provider"] = provider.value

        if time_range:
            start, end = time_range
            where_clauses.append("date BETWEEN %(start)s AND %(end)s")
            params["start"] = start
            params["end"] = end

        where = " AND ".join(where_clauses)

        # Cost by service
        svc_rows = await clickhouse.execute(
            f"""
            SELECT
                service,
                sum(daily_cost) AS total_daily,
                sum(daily_cost) * 30 AS monthly_projected,
                uniq(resource_id) AS resource_count
            FROM infra.cloud_costs
            WHERE {where}
              AND date = today()
            GROUP BY service
            ORDER BY total_daily DESC
            """,
            params,
        )

        by_service = [
            ServiceCost(
                service=r["service"],
                daily_cost=float(r.get("total_daily", 0)),
                monthly_projected=float(r.get("monthly_projected", 0)),
                resource_count=int(r.get("resource_count", 0)),
            )
            for r in svc_rows
        ]

        # Top resources by cost
        res_rows = await clickhouse.execute(
            f"""
            SELECT
                provider, service, resource_id, daily_cost,
                daily_cost * 30 AS monthly_projected,
                account, region, tags
            FROM infra.cloud_costs
            WHERE {where}
              AND date = today()
            ORDER BY daily_cost DESC
            LIMIT 50
            """,
            params,
        )

        by_resource = [
            CloudCostData(
                provider=CloudProvider(r.get("provider", "aws")),
                service=r.get("service", ""),
                resource_id=r["resource_id"],
                daily_cost=float(r.get("daily_cost", 0)),
                monthly_projected=float(r.get("monthly_projected", 0)),
                account=r.get("account", ""),
                region=r.get("region", ""),
                tags=r.get("tags", {}),
            )
            for r in res_rows
        ]

        total_daily = sum(s.daily_cost for s in by_service)
        total_monthly = sum(s.monthly_projected for s in by_service)

        logger.info(
            "Cost summary for tenant=%s: $%.2f/day, $%.2f/month projected",
            tenant_id,
            total_daily,
            total_monthly,
        )

        return CostSummary(
            total_daily=total_daily,
            total_monthly_projected=total_monthly,
            currency="USD",
            by_service=by_service,
            by_resource=by_resource,
        )

    async def detect_idle_resources(
        self,
        tenant_id: str,
        provider: CloudProvider | None = None,
        clickhouse: ClickHouseClient | None = None,
    ) -> list[IdleResource]:
        """Detect underutilized cloud resources with savings estimates."""
        assert clickhouse is not None

        where_clauses = ["tenant_id = %(tenant_id)s"]
        params: dict[str, Any] = {"tenant_id": tenant_id}

        if provider:
            where_clauses.append("provider = %(provider)s")
            params["provider"] = provider.value

        where = " AND ".join(where_clauses)

        # Low CPU instances (avg < 5% over past 7 days)
        cpu_rows = await clickhouse.execute(
            f"""
            SELECT
                r.provider, r.resource_type, r.resource_id, r.name,
                r.region, r.tags, r.status, r.account, r.instance_type,
                avg(m.value) AS avg_cpu,
                c.daily_cost
            FROM infra.cloud_resources AS r
            JOIN infra.cloud_resource_metrics AS m
                ON r.resource_id = m.resource_id
                AND m.metric_name = 'cpu_utilization'
                AND m.timestamp > now() - INTERVAL 7 DAY
            LEFT JOIN (
                SELECT resource_id, avg(daily_cost) AS daily_cost
                FROM infra.cloud_costs
                WHERE date > today() - 7
                GROUP BY resource_id
            ) AS c ON r.resource_id = c.resource_id
            WHERE r.{where.replace("tenant_id", "tenant_id")}
              AND r.resource_type IN ('ec2', 'gce', 'azure_vm')
              AND r.status = 'running'
            GROUP BY r.provider, r.resource_type, r.resource_id, r.name,
                     r.region, r.tags, r.status, r.account, r.instance_type,
                     c.daily_cost
            HAVING avg_cpu < 5
            ORDER BY c.daily_cost DESC
            """,
            params,
        )

        idle_resources: list[IdleResource] = []

        for r in cpu_rows:
            resource = CloudResource(
                provider=CloudProvider(r.get("provider", "aws")),
                resource_type=r.get("resource_type", ""),
                resource_id=r["resource_id"],
                name=r.get("name", ""),
                region=r.get("region", ""),
                tags=r.get("tags", {}),
                status=ResourceStatus(r.get("status", "running")),
                account=r.get("account", ""),
                instance_type=r.get("instance_type", ""),
            )
            daily_cost = float(r.get("daily_cost", 0))
            avg_cpu = float(r.get("avg_cpu", 0))

            idle_resources.append(
                IdleResource(
                    resource=resource,
                    idle_reason="low_cpu",
                    avg_utilization_pct=avg_cpu,
                    estimated_monthly_savings=daily_cost * 30 * 0.7,  # 70% savings
                    recommendation=(
                        "Consider downsizing or terminating this instance. "
                        f"Average CPU utilization is only {avg_cpu:.1f}% over 7 days."
                    ),
                )
            )

        # Unattached EBS volumes / persistent disks
        disk_rows = await clickhouse.execute(
            f"""
            SELECT
                r.provider, r.resource_type, r.resource_id, r.name,
                r.region, r.tags, r.status, r.account,
                c.daily_cost
            FROM infra.cloud_resources AS r
            LEFT JOIN (
                SELECT resource_id, avg(daily_cost) AS daily_cost
                FROM infra.cloud_costs
                WHERE date > today() - 7
                GROUP BY resource_id
            ) AS c ON r.resource_id = c.resource_id
            WHERE r.{where.replace("tenant_id", "tenant_id")}
              AND r.resource_type IN ('ebs', 'persistent_disk', 'azure_disk')
              AND r.status = 'available'
            ORDER BY c.daily_cost DESC
            """,
            params,
        )

        for r in disk_rows:
            resource = CloudResource(
                provider=CloudProvider(r.get("provider", "aws")),
                resource_type=r.get("resource_type", ""),
                resource_id=r["resource_id"],
                name=r.get("name", ""),
                region=r.get("region", ""),
                tags=r.get("tags", {}),
                status=ResourceStatus(r.get("status", "running")),
                account=r.get("account", ""),
            )
            daily_cost = float(r.get("daily_cost", 0))

            idle_resources.append(
                IdleResource(
                    resource=resource,
                    idle_reason="no_connections",
                    avg_utilization_pct=0.0,
                    estimated_monthly_savings=daily_cost * 30,
                    recommendation=(
                        "This volume is unattached. Consider creating a snapshot "
                        "and deleting it to save costs."
                    ),
                )
            )

        logger.info(
            "Detected %d idle resources for tenant=%s provider=%s",
            len(idle_resources),
            tenant_id,
            provider.value if provider else "all",
        )
        return idle_resources

    async def get_cloud_topology(
        self,
        tenant_id: str,
        provider: CloudProvider,
        region: str,
        clickhouse: ClickHouseClient,
    ) -> CloudTopology:
        """Build a resource dependency graph for a specific provider/region."""

        # Fetch resources
        resource_rows = await clickhouse.execute(
            """
            SELECT resource_id, resource_type, name, status
            FROM infra.cloud_resources
            WHERE tenant_id = %(tenant_id)s
              AND provider = %(provider)s
              AND region = %(region)s
              AND timestamp = (
                  SELECT max(timestamp)
                  FROM infra.cloud_resources
                  WHERE tenant_id = %(tenant_id)s
                    AND provider = %(provider)s
                    AND region = %(region)s
              )
            """,
            {
                "tenant_id": tenant_id,
                "provider": provider.value,
                "region": region,
            },
        )

        nodes = [
            TopologyNode(
                resource_id=r["resource_id"],
                resource_type=r.get("resource_type", ""),
                name=r.get("name", ""),
                status=ResourceStatus(r.get("status", "running")),
            )
            for r in resource_rows
        ]

        # Fetch relationships
        edge_rows = await clickhouse.execute(
            """
            SELECT source_id, target_id, relationship
            FROM infra.cloud_resource_edges
            WHERE tenant_id = %(tenant_id)s
              AND provider = %(provider)s
              AND region = %(region)s
            """,
            {
                "tenant_id": tenant_id,
                "provider": provider.value,
                "region": region,
            },
        )

        edges = [
            TopologyEdge(
                source_id=r["source_id"],
                target_id=r["target_id"],
                relationship=r.get("relationship", "connects_to"),
            )
            for r in edge_rows
        ]

        logger.info(
            "Built cloud topology for tenant=%s provider=%s region=%s: %d nodes, %d edges",
            tenant_id,
            provider.value,
            region,
            len(nodes),
            len(edges),
        )

        return CloudTopology(
            provider=provider,
            region=region,
            nodes=nodes,
            edges=edges,
        )
