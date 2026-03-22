"""Kubernetes monitoring for infrastructure observability.

Tracks cluster, node, pod, deployment, and event data,
comparable to Datadog Kubernetes monitoring and Dynatrace Kubernetes views.
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

class ClusterHealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"


class NodeStatus(str, Enum):
    READY = "Ready"
    NOT_READY = "NotReady"
    UNKNOWN = "Unknown"


class PodStatus(str, Enum):
    RUNNING = "Running"
    PENDING = "Pending"
    FAILED = "Failed"
    SUCCEEDED = "Succeeded"
    CRASH_LOOP_BACK_OFF = "CrashLoopBackOff"


class K8sEventType(str, Enum):
    NORMAL = "Normal"
    WARNING = "Warning"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class K8sCluster:
    name: str
    version: str
    node_count: int
    pod_count: int
    namespace_count: int
    health_status: ClusterHealthStatus
    cpu_capacity_cores: float = 0.0
    cpu_used_cores: float = 0.0
    memory_capacity_bytes: int = 0
    memory_used_bytes: int = 0


@dataclass
class NodeCondition:
    condition_type: str  # Ready, DiskPressure, MemoryPressure, PIDPressure
    status: str  # True, False, Unknown
    reason: str = ""
    message: str = ""
    last_transition: datetime | None = None


@dataclass
class K8sNode:
    name: str
    status: NodeStatus
    roles: list[str]
    cpu_capacity: float
    cpu_allocatable: float
    cpu_used: float
    memory_capacity: int
    memory_allocatable: int
    memory_used: int
    pod_count: int
    conditions: list[NodeCondition] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)
    kernel_version: str = ""
    container_runtime: str = ""
    kubelet_version: str = ""


@dataclass
class K8sContainerStatus:
    name: str
    image: str
    ready: bool
    restart_count: int
    state: str  # running, waiting, terminated
    reason: str = ""


@dataclass
class K8sPod:
    name: str
    namespace: str
    node: str
    status: PodStatus
    restart_count: int
    cpu_request: float
    cpu_limit: float
    cpu_used: float
    memory_request: int
    memory_limit: int
    memory_used: int
    containers: list[K8sContainerStatus] = field(default_factory=list)
    start_time: datetime | None = None
    labels: dict[str, str] = field(default_factory=dict)
    owner_kind: str = ""  # Deployment, StatefulSet, DaemonSet, Job
    owner_name: str = ""
    ip: str = ""


@dataclass
class DeploymentCondition:
    condition_type: str  # Available, Progressing, ReplicaFailure
    status: str
    reason: str = ""
    message: str = ""


@dataclass
class K8sDeployment:
    name: str
    namespace: str
    replicas_desired: int
    replicas_available: int
    replicas_updated: int
    strategy: str  # RollingUpdate, Recreate
    conditions: list[DeploymentCondition] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)
    created_at: datetime | None = None


@dataclass
class K8sEvent:
    type: K8sEventType
    reason: str
    message: str
    object: str  # e.g. "Pod/my-pod-xyz"
    timestamp: datetime | None = None
    count: int = 1
    source: str = ""
    namespace: str = ""


@dataclass
class ResourceUtilization:
    resource_type: str  # cpu, memory
    capacity: float
    allocatable: float
    requested: float
    used: float
    unit: str  # cores, bytes


@dataclass
class K8sIssue:
    issue_type: str  # crash_loop, oom_killed, pending_pod, node_pressure
    severity: str  # warning, critical
    resource_kind: str  # Pod, Node
    resource_name: str
    namespace: str
    description: str
    detected_at: datetime


@dataclass
class PodDetail:
    pod: K8sPod
    events: list[K8sEvent]
    logs: list[dict[str, Any]]  # {container, timestamp, message}


# ---------------------------------------------------------------------------
# KubernetesService
# ---------------------------------------------------------------------------

class KubernetesService:
    """Service layer for Kubernetes infrastructure monitoring."""

    async def get_cluster_overview(
        self,
        tenant_id: str,
        cluster_name: str,
        clickhouse: ClickHouseClient,
    ) -> K8sCluster:
        """Return cluster-level overview with resource utilization."""

        rows = await clickhouse.execute(
            """
            SELECT
                cluster_name,
                version,
                node_count,
                pod_count,
                namespace_count,
                cpu_capacity_cores,
                cpu_used_cores,
                memory_capacity_bytes,
                memory_used_bytes
            FROM infra.k8s_clusters
            WHERE tenant_id = %(tenant_id)s
              AND cluster_name = %(cluster_name)s
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            {"tenant_id": tenant_id, "cluster_name": cluster_name},
        )

        if not rows:
            raise ValueError(
                f"Cluster {cluster_name} not found for tenant {tenant_id}"
            )

        r = rows[0]

        # Determine cluster health from node/pod issues
        issue_rows = await clickhouse.execute(
            """
            SELECT count() AS issue_count,
                   countIf(severity = 'critical') AS critical_count
            FROM infra.k8s_issues
            WHERE tenant_id = %(tenant_id)s
              AND cluster_name = %(cluster_name)s
              AND resolved_at IS NULL
            """,
            {"tenant_id": tenant_id, "cluster_name": cluster_name},
        )

        health = ClusterHealthStatus.HEALTHY
        if issue_rows:
            critical = int(issue_rows[0].get("critical_count", 0))
            total = int(issue_rows[0].get("issue_count", 0))
            if critical > 0:
                health = ClusterHealthStatus.CRITICAL
            elif total > 0:
                health = ClusterHealthStatus.DEGRADED

        cluster = K8sCluster(
            name=r["cluster_name"],
            version=r.get("version", ""),
            node_count=int(r.get("node_count", 0)),
            pod_count=int(r.get("pod_count", 0)),
            namespace_count=int(r.get("namespace_count", 0)),
            health_status=health,
            cpu_capacity_cores=float(r.get("cpu_capacity_cores", 0)),
            cpu_used_cores=float(r.get("cpu_used_cores", 0)),
            memory_capacity_bytes=int(r.get("memory_capacity_bytes", 0)),
            memory_used_bytes=int(r.get("memory_used_bytes", 0)),
        )

        logger.info(
            "Cluster overview for tenant=%s cluster=%s: %d nodes, %d pods, status=%s",
            tenant_id,
            cluster_name,
            cluster.node_count,
            cluster.pod_count,
            health.value,
        )
        return cluster

    async def list_nodes(
        self,
        tenant_id: str,
        cluster: str,
        clickhouse: ClickHouseClient,
    ) -> list[K8sNode]:
        """Return all nodes in a cluster with current resource usage."""

        rows = await clickhouse.execute(
            """
            SELECT
                name, status, roles, labels,
                cpu_capacity, cpu_allocatable, cpu_used,
                memory_capacity, memory_allocatable, memory_used,
                pod_count, conditions,
                kernel_version, container_runtime, kubelet_version
            FROM infra.k8s_nodes
            WHERE tenant_id = %(tenant_id)s
              AND cluster_name = %(cluster)s
              AND timestamp = (
                  SELECT max(timestamp)
                  FROM infra.k8s_nodes
                  WHERE tenant_id = %(tenant_id)s AND cluster_name = %(cluster)s
              )
            ORDER BY name
            """,
            {"tenant_id": tenant_id, "cluster": cluster},
        )

        nodes = []
        for r in rows:
            conditions = []
            for c in r.get("conditions", []):
                conditions.append(
                    NodeCondition(
                        condition_type=c.get("type", ""),
                        status=c.get("status", ""),
                        reason=c.get("reason", ""),
                        message=c.get("message", ""),
                        last_transition=c.get("lastTransitionTime"),
                    )
                )

            nodes.append(
                K8sNode(
                    name=r["name"],
                    status=NodeStatus(r.get("status", "Unknown")),
                    roles=r.get("roles", []),
                    cpu_capacity=float(r.get("cpu_capacity", 0)),
                    cpu_allocatable=float(r.get("cpu_allocatable", 0)),
                    cpu_used=float(r.get("cpu_used", 0)),
                    memory_capacity=int(r.get("memory_capacity", 0)),
                    memory_allocatable=int(r.get("memory_allocatable", 0)),
                    memory_used=int(r.get("memory_used", 0)),
                    pod_count=int(r.get("pod_count", 0)),
                    conditions=conditions,
                    labels=r.get("labels", {}),
                    kernel_version=r.get("kernel_version", ""),
                    container_runtime=r.get("container_runtime", ""),
                    kubelet_version=r.get("kubelet_version", ""),
                )
            )

        logger.info(
            "Listed %d nodes for tenant=%s cluster=%s",
            len(nodes),
            tenant_id,
            cluster,
        )
        return nodes

    async def list_pods(
        self,
        tenant_id: str,
        cluster: str,
        namespace: str | None = None,
        clickhouse: ClickHouseClient | None = None,
    ) -> list[K8sPod]:
        """List pods in a cluster, optionally filtered by namespace."""
        assert clickhouse is not None

        where_clauses = [
            "tenant_id = %(tenant_id)s",
            "cluster_name = %(cluster)s",
        ]
        params: dict[str, Any] = {"tenant_id": tenant_id, "cluster": cluster}

        if namespace:
            where_clauses.append("namespace = %(namespace)s")
            params["namespace"] = namespace

        where = " AND ".join(where_clauses)

        rows = await clickhouse.execute(
            f"""
            SELECT
                name, namespace, node, status, restart_count,
                cpu_request, cpu_limit, cpu_used,
                memory_request, memory_limit, memory_used,
                containers, start_time, labels,
                owner_kind, owner_name, ip
            FROM infra.k8s_pods
            WHERE {where}
              AND timestamp = (
                  SELECT max(timestamp)
                  FROM infra.k8s_pods
                  WHERE {where}
              )
            ORDER BY namespace, name
            """,
            params,
        )

        pods = []
        for r in rows:
            container_statuses = []
            for c in r.get("containers", []):
                container_statuses.append(
                    K8sContainerStatus(
                        name=c.get("name", ""),
                        image=c.get("image", ""),
                        ready=c.get("ready", False),
                        restart_count=int(c.get("restartCount", 0)),
                        state=c.get("state", "unknown"),
                        reason=c.get("reason", ""),
                    )
                )

            pods.append(
                K8sPod(
                    name=r["name"],
                    namespace=r["namespace"],
                    node=r.get("node", ""),
                    status=PodStatus(r.get("status", "Running")),
                    restart_count=int(r.get("restart_count", 0)),
                    cpu_request=float(r.get("cpu_request", 0)),
                    cpu_limit=float(r.get("cpu_limit", 0)),
                    cpu_used=float(r.get("cpu_used", 0)),
                    memory_request=int(r.get("memory_request", 0)),
                    memory_limit=int(r.get("memory_limit", 0)),
                    memory_used=int(r.get("memory_used", 0)),
                    containers=container_statuses,
                    start_time=r.get("start_time"),
                    labels=r.get("labels", {}),
                    owner_kind=r.get("owner_kind", ""),
                    owner_name=r.get("owner_name", ""),
                    ip=r.get("ip", ""),
                )
            )

        logger.info(
            "Listed %d pods for tenant=%s cluster=%s namespace=%s",
            len(pods),
            tenant_id,
            cluster,
            namespace or "all",
        )
        return pods

    async def list_deployments(
        self,
        tenant_id: str,
        cluster: str,
        namespace: str | None = None,
        clickhouse: ClickHouseClient | None = None,
    ) -> list[K8sDeployment]:
        """List deployments in a cluster."""
        assert clickhouse is not None

        where_clauses = [
            "tenant_id = %(tenant_id)s",
            "cluster_name = %(cluster)s",
        ]
        params: dict[str, Any] = {"tenant_id": tenant_id, "cluster": cluster}

        if namespace:
            where_clauses.append("namespace = %(namespace)s")
            params["namespace"] = namespace

        where = " AND ".join(where_clauses)

        rows = await clickhouse.execute(
            f"""
            SELECT
                name, namespace, replicas_desired, replicas_available,
                replicas_updated, strategy, conditions, labels, created_at
            FROM infra.k8s_deployments
            WHERE {where}
              AND timestamp = (
                  SELECT max(timestamp)
                  FROM infra.k8s_deployments
                  WHERE {where}
              )
            ORDER BY namespace, name
            """,
            params,
        )

        deployments = []
        for r in rows:
            conditions = []
            for c in r.get("conditions", []):
                conditions.append(
                    DeploymentCondition(
                        condition_type=c.get("type", ""),
                        status=c.get("status", ""),
                        reason=c.get("reason", ""),
                        message=c.get("message", ""),
                    )
                )

            deployments.append(
                K8sDeployment(
                    name=r["name"],
                    namespace=r["namespace"],
                    replicas_desired=int(r.get("replicas_desired", 0)),
                    replicas_available=int(r.get("replicas_available", 0)),
                    replicas_updated=int(r.get("replicas_updated", 0)),
                    strategy=r.get("strategy", "RollingUpdate"),
                    conditions=conditions,
                    labels=r.get("labels", {}),
                    created_at=r.get("created_at"),
                )
            )

        logger.info(
            "Listed %d deployments for tenant=%s cluster=%s",
            len(deployments),
            tenant_id,
            cluster,
        )
        return deployments

    async def get_pod_detail(
        self,
        tenant_id: str,
        cluster: str,
        namespace: str,
        pod_name: str,
        clickhouse: ClickHouseClient,
    ) -> PodDetail:
        """Return detailed pod information with events and logs."""

        pods = await self.list_pods(
            tenant_id, cluster, namespace, clickhouse=clickhouse
        )
        pod = next((p for p in pods if p.name == pod_name), None)
        if not pod:
            raise ValueError(
                f"Pod {namespace}/{pod_name} not found in cluster {cluster}"
            )

        # Events for this pod
        event_rows = await clickhouse.execute(
            """
            SELECT type, reason, message, object, timestamp, count, source
            FROM infra.k8s_events
            WHERE tenant_id = %(tenant_id)s
              AND cluster_name = %(cluster)s
              AND namespace = %(namespace)s
              AND object LIKE %(pod_pattern)s
            ORDER BY timestamp DESC
            LIMIT 100
            """,
            {
                "tenant_id": tenant_id,
                "cluster": cluster,
                "namespace": namespace,
                "pod_pattern": f"Pod/{pod_name}%",
            },
        )
        events = [
            K8sEvent(
                type=K8sEventType(r.get("type", "Normal")),
                reason=r.get("reason", ""),
                message=r.get("message", ""),
                object=r.get("object", ""),
                timestamp=r.get("timestamp"),
                count=int(r.get("count", 1)),
                source=r.get("source", ""),
                namespace=namespace,
            )
            for r in event_rows
        ]

        # Container logs
        log_rows = await clickhouse.execute(
            """
            SELECT container_name, timestamp, message
            FROM infra.k8s_pod_logs
            WHERE tenant_id = %(tenant_id)s
              AND cluster_name = %(cluster)s
              AND namespace = %(namespace)s
              AND pod_name = %(pod_name)s
            ORDER BY timestamp DESC
            LIMIT 500
            """,
            {
                "tenant_id": tenant_id,
                "cluster": cluster,
                "namespace": namespace,
                "pod_name": pod_name,
            },
        )
        logs = [
            {
                "container": r.get("container_name", ""),
                "timestamp": r["timestamp"],
                "message": r["message"],
            }
            for r in log_rows
        ]
        logs.reverse()

        return PodDetail(pod=pod, events=events, logs=logs)

    async def get_events(
        self,
        tenant_id: str,
        cluster: str,
        namespace: str | None = None,
        clickhouse: ClickHouseClient | None = None,
    ) -> list[K8sEvent]:
        """Return cluster events, optionally filtered by namespace."""
        assert clickhouse is not None

        where_clauses = [
            "tenant_id = %(tenant_id)s",
            "cluster_name = %(cluster)s",
        ]
        params: dict[str, Any] = {"tenant_id": tenant_id, "cluster": cluster}

        if namespace:
            where_clauses.append("namespace = %(namespace)s")
            params["namespace"] = namespace

        where = " AND ".join(where_clauses)

        rows = await clickhouse.execute(
            f"""
            SELECT type, reason, message, object, timestamp, count, source, namespace
            FROM infra.k8s_events
            WHERE {where}
            ORDER BY timestamp DESC
            LIMIT 500
            """,
            params,
        )

        events = [
            K8sEvent(
                type=K8sEventType(r.get("type", "Normal")),
                reason=r.get("reason", ""),
                message=r.get("message", ""),
                object=r.get("object", ""),
                timestamp=r.get("timestamp"),
                count=int(r.get("count", 1)),
                source=r.get("source", ""),
                namespace=r.get("namespace", ""),
            )
            for r in rows
        ]

        logger.info(
            "Listed %d events for tenant=%s cluster=%s", len(events), tenant_id, cluster
        )
        return events

    async def get_resource_utilization(
        self,
        tenant_id: str,
        cluster: str,
        clickhouse: ClickHouseClient,
    ) -> list[ResourceUtilization]:
        """Return cluster-level CPU and memory: capacity vs allocated vs used."""

        rows = await clickhouse.execute(
            """
            SELECT
                sum(cpu_capacity) AS cpu_capacity,
                sum(cpu_allocatable) AS cpu_allocatable,
                sum(cpu_used) AS cpu_used,
                sum(memory_capacity) AS memory_capacity,
                sum(memory_allocatable) AS memory_allocatable,
                sum(memory_used) AS memory_used
            FROM infra.k8s_nodes
            WHERE tenant_id = %(tenant_id)s
              AND cluster_name = %(cluster)s
              AND timestamp = (
                  SELECT max(timestamp)
                  FROM infra.k8s_nodes
                  WHERE tenant_id = %(tenant_id)s AND cluster_name = %(cluster)s
              )
            """,
            {"tenant_id": tenant_id, "cluster": cluster},
        )

        if not rows:
            return []

        r = rows[0]

        # Get total requested from pods
        req_rows = await clickhouse.execute(
            """
            SELECT
                sum(cpu_request) AS cpu_requested,
                sum(memory_request) AS memory_requested
            FROM infra.k8s_pods
            WHERE tenant_id = %(tenant_id)s
              AND cluster_name = %(cluster)s
              AND status IN ('Running', 'Pending')
              AND timestamp = (
                  SELECT max(timestamp)
                  FROM infra.k8s_pods
                  WHERE tenant_id = %(tenant_id)s AND cluster_name = %(cluster)s
              )
            """,
            {"tenant_id": tenant_id, "cluster": cluster},
        )

        req = req_rows[0] if req_rows else {}

        utilization = [
            ResourceUtilization(
                resource_type="cpu",
                capacity=float(r.get("cpu_capacity", 0)),
                allocatable=float(r.get("cpu_allocatable", 0)),
                requested=float(req.get("cpu_requested", 0)),
                used=float(r.get("cpu_used", 0)),
                unit="cores",
            ),
            ResourceUtilization(
                resource_type="memory",
                capacity=float(r.get("memory_capacity", 0)),
                allocatable=float(r.get("memory_allocatable", 0)),
                requested=float(req.get("memory_requested", 0)),
                used=float(r.get("memory_used", 0)),
                unit="bytes",
            ),
        ]

        return utilization

    async def detect_issues(
        self,
        tenant_id: str,
        cluster: str,
        clickhouse: ClickHouseClient,
    ) -> list[K8sIssue]:
        """Detect common Kubernetes issues across the cluster."""

        now = datetime.utcnow()
        issues: list[K8sIssue] = []

        # CrashLoopBackOff pods
        crash_rows = await clickhouse.execute(
            """
            SELECT name, namespace, restart_count
            FROM infra.k8s_pods
            WHERE tenant_id = %(tenant_id)s
              AND cluster_name = %(cluster)s
              AND status = 'CrashLoopBackOff'
              AND timestamp = (
                  SELECT max(timestamp)
                  FROM infra.k8s_pods
                  WHERE tenant_id = %(tenant_id)s AND cluster_name = %(cluster)s
              )
            """,
            {"tenant_id": tenant_id, "cluster": cluster},
        )
        for r in crash_rows:
            issues.append(
                K8sIssue(
                    issue_type="crash_loop",
                    severity="critical",
                    resource_kind="Pod",
                    resource_name=r["name"],
                    namespace=r["namespace"],
                    description=(
                        f"Pod is in CrashLoopBackOff with "
                        f"{r.get('restart_count', 0)} restarts"
                    ),
                    detected_at=now,
                )
            )

        # Pending pods (stuck for > 5 minutes)
        pending_rows = await clickhouse.execute(
            """
            SELECT name, namespace, start_time
            FROM infra.k8s_pods
            WHERE tenant_id = %(tenant_id)s
              AND cluster_name = %(cluster)s
              AND status = 'Pending'
              AND start_time < now() - INTERVAL 5 MINUTE
              AND timestamp = (
                  SELECT max(timestamp)
                  FROM infra.k8s_pods
                  WHERE tenant_id = %(tenant_id)s AND cluster_name = %(cluster)s
              )
            """,
            {"tenant_id": tenant_id, "cluster": cluster},
        )
        for r in pending_rows:
            issues.append(
                K8sIssue(
                    issue_type="pending_pod",
                    severity="warning",
                    resource_kind="Pod",
                    resource_name=r["name"],
                    namespace=r["namespace"],
                    description="Pod has been pending for more than 5 minutes",
                    detected_at=now,
                )
            )

        # OOMKilled containers (from recent events)
        oom_rows = await clickhouse.execute(
            """
            SELECT object, namespace, message
            FROM infra.k8s_events
            WHERE tenant_id = %(tenant_id)s
              AND cluster_name = %(cluster)s
              AND reason = 'OOMKilled'
              AND timestamp > now() - INTERVAL 1 HOUR
            ORDER BY timestamp DESC
            """,
            {"tenant_id": tenant_id, "cluster": cluster},
        )
        for r in oom_rows:
            issues.append(
                K8sIssue(
                    issue_type="oom_killed",
                    severity="critical",
                    resource_kind="Pod",
                    resource_name=r.get("object", "unknown"),
                    namespace=r.get("namespace", ""),
                    description=f"Container was OOMKilled: {r.get('message', '')}",
                    detected_at=now,
                )
            )

        # Node pressure (DiskPressure, MemoryPressure, PIDPressure)
        pressure_rows = await clickhouse.execute(
            """
            SELECT name, conditions
            FROM infra.k8s_nodes
            WHERE tenant_id = %(tenant_id)s
              AND cluster_name = %(cluster)s
              AND (
                  status = 'NotReady'
                  OR has(arrayMap(x -> x.1, conditions), 'DiskPressure')
                  OR has(arrayMap(x -> x.1, conditions), 'MemoryPressure')
              )
              AND timestamp = (
                  SELECT max(timestamp)
                  FROM infra.k8s_nodes
                  WHERE tenant_id = %(tenant_id)s AND cluster_name = %(cluster)s
              )
            """,
            {"tenant_id": tenant_id, "cluster": cluster},
        )
        for r in pressure_rows:
            conditions = r.get("conditions", [])
            pressure_types = []
            for c in conditions:
                ctype = c.get("type", "") if isinstance(c, dict) else ""
                cstatus = c.get("status", "") if isinstance(c, dict) else ""
                if ctype in ("DiskPressure", "MemoryPressure", "PIDPressure") and cstatus == "True":
                    pressure_types.append(ctype)

            if pressure_types:
                issues.append(
                    K8sIssue(
                        issue_type="node_pressure",
                        severity="critical",
                        resource_kind="Node",
                        resource_name=r["name"],
                        namespace="",
                        description=f"Node experiencing: {', '.join(pressure_types)}",
                        detected_at=now,
                    )
                )

        logger.info(
            "Detected %d issues for tenant=%s cluster=%s",
            len(issues),
            tenant_id,
            cluster,
        )
        return issues
