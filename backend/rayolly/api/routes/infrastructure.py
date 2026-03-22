"""Infrastructure monitoring API routes.

Provides endpoints for host monitoring, Kubernetes observability,
cloud resource inventory, container monitoring, and cost tracking.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Query, Request

from rayolly.services.infrastructure.cloud import CloudProvider, CloudService
from rayolly.services.infrastructure.containers import ContainerService
from rayolly.services.infrastructure.hosts import HostService
from rayolly.services.infrastructure.kubernetes import KubernetesService

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/infra", tags=["infrastructure"])


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

def _clickhouse(request: Request) -> Any:
    return request.app.state.clickhouse


def _tenant_id(request: Request) -> str:
    return getattr(request.state, "tenant_id", "default")


def _time_range(
    from_time: str | None = None,
    to_time: str | None = None,
) -> tuple[datetime, datetime]:
    """Parse optional time range, defaulting to the last hour."""
    end = datetime.fromisoformat(to_time) if to_time else datetime.utcnow()
    start = datetime.fromisoformat(from_time) if from_time else end - timedelta(hours=1)
    return start, end


# ---------------------------------------------------------------------------
# Host endpoints
# ---------------------------------------------------------------------------

_host_svc = HostService()


@router.get("/hosts")
async def list_hosts(
    request: Request,
    cloud_provider: str | None = None,
    cloud_region: str | None = None,
    hostname: str | None = None,
) -> dict:
    """List hosts with status and key metrics."""
    tenant_id = _tenant_id(request)
    ch = _clickhouse(request)

    filters: dict[str, Any] = {}
    if cloud_provider:
        filters["cloud_provider"] = cloud_provider
    if cloud_region:
        filters["cloud_region"] = cloud_region
    if hostname:
        filters["hostname"] = hostname

    try:
        results = await _host_svc.list_hosts(tenant_id, filters, ch)
    except Exception as exc:
        logger.error("Failed to list hosts", tenant_id=tenant_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to list hosts")

    return {
        "hosts": [
            {
                "host_id": info.host_id,
                "hostname": info.hostname,
                "ip_addresses": info.ip_addresses,
                "os": info.os,
                "arch": info.arch,
                "cpu_count": info.cpu_count,
                "memory_total_bytes": info.memory_total_bytes,
                "cloud_provider": info.cloud_provider,
                "cloud_region": info.cloud_region,
                "cloud_instance_type": info.cloud_instance_type,
                "tags": info.tags,
                "agent_version": info.agent_version,
                "last_seen": info.last_seen.isoformat() if info.last_seen else None,
                "status": status.value,
            }
            for info, status in results
        ],
        "total": len(results),
    }


@router.get("/hosts/{host_id}")
async def get_host_detail(
    host_id: str,
    request: Request,
    from_time: str | None = None,
    to_time: str | None = None,
) -> dict:
    """Get detailed information for a single host."""
    tenant_id = _tenant_id(request)
    ch = _clickhouse(request)
    time_range = _time_range(from_time, to_time)

    try:
        detail = await _host_svc.get_host_detail(tenant_id, host_id, time_range, ch)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error("Failed to get host detail", host_id=host_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to get host detail")

    return {
        "host_id": detail.info.host_id,
        "hostname": detail.info.hostname,
        "status": detail.status.value,
        "info": {
            "os": detail.info.os,
            "os_version": detail.info.os_version,
            "arch": detail.info.arch,
            "cpu_count": detail.info.cpu_count,
            "memory_total_bytes": detail.info.memory_total_bytes,
            "cloud_provider": detail.info.cloud_provider,
            "cloud_region": detail.info.cloud_region,
            "cloud_instance_type": detail.info.cloud_instance_type,
            "tags": detail.info.tags,
            "agent_version": detail.info.agent_version,
        },
        "current_metrics": (
            {
                "cpu_user_pct": detail.current_metrics.cpu_user_pct,
                "cpu_system_pct": detail.current_metrics.cpu_system_pct,
                "cpu_iowait_pct": detail.current_metrics.cpu_iowait_pct,
                "memory_used_bytes": detail.current_metrics.memory_used_bytes,
                "memory_free_bytes": detail.current_metrics.memory_free_bytes,
                "disk_read_bytes_sec": detail.current_metrics.disk_read_bytes_sec,
                "disk_write_bytes_sec": detail.current_metrics.disk_write_bytes_sec,
                "network_in_bytes_sec": detail.current_metrics.network_in_bytes_sec,
                "network_out_bytes_sec": detail.current_metrics.network_out_bytes_sec,
                "load_1m": detail.current_metrics.load_1m,
                "load_5m": detail.current_metrics.load_5m,
                "load_15m": detail.current_metrics.load_15m,
                "process_count": detail.current_metrics.process_count,
            }
            if detail.current_metrics
            else None
        ),
        "process_count": len(detail.processes),
        "container_count": len(detail.containers),
        "disk_mounts": [
            {
                "device": d.device,
                "mount_point": d.mount_point,
                "total_bytes": d.total_bytes,
                "used_bytes": d.used_bytes,
                "free_bytes": d.free_bytes,
            }
            for d in detail.disk_mounts
        ],
        "network_interfaces": [
            {
                "name": n.name,
                "ip_address": n.ip_address,
                "speed_mbps": n.speed_mbps,
                "in_bytes_sec": n.in_bytes_sec,
                "out_bytes_sec": n.out_bytes_sec,
            }
            for n in detail.network_interfaces
        ],
        "installed_agents": [
            {"name": a.name, "version": a.version, "status": a.status}
            for a in detail.installed_agents
        ],
    }


@router.get("/hosts/{host_id}/metrics")
async def get_host_metrics(
    host_id: str,
    request: Request,
    metrics: str = Query(
        default="cpu_user_pct,cpu_system_pct,memory_used_bytes",
        description="Comma-separated metric names",
    ),
    from_time: str | None = None,
    to_time: str | None = None,
) -> dict:
    """Get time-series metrics for a host."""
    tenant_id = _tenant_id(request)
    ch = _clickhouse(request)
    time_range = _time_range(from_time, to_time)
    metric_names = [m.strip() for m in metrics.split(",") if m.strip()]

    try:
        series = await _host_svc.get_host_metrics(
            tenant_id, host_id, metric_names, time_range, ch
        )
    except Exception as exc:
        logger.error("Failed to get host metrics", host_id=host_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to get host metrics")

    return {
        "host_id": host_id,
        "series": [
            {
                "metric": s.metric_name,
                "data": [
                    {"timestamp": p.timestamp.isoformat(), "value": p.value}
                    for p in s.data
                ],
            }
            for s in series
        ],
    }


@router.get("/host-map")
async def get_host_map(
    request: Request,
    group_by: str = Query(default="cloud_region", description="Field to group by"),
    color_by: str = Query(default="cpu_total_pct", description="Metric for coloring"),
    size_by: str = Query(default="memory_total_bytes", description="Metric for sizing"),
) -> dict:
    """Get host map visualization data."""
    tenant_id = _tenant_id(request)
    ch = _clickhouse(request)

    try:
        data = await _host_svc.get_host_map(tenant_id, group_by, color_by, size_by, ch)
    except Exception as exc:
        logger.error("Failed to build host map", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to build host map")

    return {
        "group_by": data.group_by,
        "color_by": data.color_by,
        "size_by": data.size_by,
        "groups": [
            {
                "group_name": g.group_name,
                "hosts": [
                    {
                        "host_id": h.host_id,
                        "hostname": h.hostname,
                        "color_value": h.color_value,
                        "size_value": h.size_value,
                        "status": h.status.value,
                        "tags": h.tags,
                    }
                    for h in g.hosts
                ],
            }
            for g in data.groups
        ],
    }


# ---------------------------------------------------------------------------
# Kubernetes endpoints
# ---------------------------------------------------------------------------

_k8s_svc = KubernetesService()


@router.get("/kubernetes/clusters")
async def list_kubernetes_clusters(request: Request) -> dict:
    """List Kubernetes clusters."""
    tenant_id = _tenant_id(request)
    ch = _clickhouse(request)

    try:
        rows = await ch.execute(
            """
            SELECT DISTINCT cluster_name
            FROM infra.k8s_clusters
            WHERE tenant_id = %(tenant_id)s
            ORDER BY cluster_name
            """,
            {"tenant_id": tenant_id},
        )
    except Exception as exc:
        logger.error("Failed to list K8s clusters", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to list clusters")

    clusters = []
    for row in rows:
        name = row["cluster_name"]
        try:
            overview = await _k8s_svc.get_cluster_overview(tenant_id, name, ch)
            clusters.append({
                "name": overview.name,
                "version": overview.version,
                "node_count": overview.node_count,
                "pod_count": overview.pod_count,
                "namespace_count": overview.namespace_count,
                "health_status": overview.health_status.value,
                "cpu_capacity_cores": overview.cpu_capacity_cores,
                "cpu_used_cores": overview.cpu_used_cores,
                "memory_capacity_bytes": overview.memory_capacity_bytes,
                "memory_used_bytes": overview.memory_used_bytes,
            })
        except Exception as exc:
            logger.warning("Failed to get overview for cluster %s: %s", name, exc)
            clusters.append({"name": name, "health_status": "unknown"})

    return {"clusters": clusters, "total": len(clusters)}


@router.get("/kubernetes/clusters/{name}/overview")
async def get_cluster_overview(name: str, request: Request) -> dict:
    """Get Kubernetes cluster overview."""
    tenant_id = _tenant_id(request)
    ch = _clickhouse(request)

    try:
        cluster = await _k8s_svc.get_cluster_overview(tenant_id, name, ch)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error("Failed to get cluster overview", cluster=name, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to get cluster overview")

    return {
        "name": cluster.name,
        "version": cluster.version,
        "node_count": cluster.node_count,
        "pod_count": cluster.pod_count,
        "namespace_count": cluster.namespace_count,
        "health_status": cluster.health_status.value,
        "cpu_capacity_cores": cluster.cpu_capacity_cores,
        "cpu_used_cores": cluster.cpu_used_cores,
        "memory_capacity_bytes": cluster.memory_capacity_bytes,
        "memory_used_bytes": cluster.memory_used_bytes,
    }


@router.get("/kubernetes/clusters/{name}/nodes")
async def list_cluster_nodes(name: str, request: Request) -> dict:
    """List nodes in a Kubernetes cluster."""
    tenant_id = _tenant_id(request)
    ch = _clickhouse(request)

    try:
        nodes = await _k8s_svc.list_nodes(tenant_id, name, ch)
    except Exception as exc:
        logger.error("Failed to list nodes", cluster=name, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to list nodes")

    return {
        "nodes": [
            {
                "name": n.name,
                "status": n.status.value,
                "roles": n.roles,
                "cpu_capacity": n.cpu_capacity,
                "cpu_allocatable": n.cpu_allocatable,
                "cpu_used": n.cpu_used,
                "memory_capacity": n.memory_capacity,
                "memory_allocatable": n.memory_allocatable,
                "memory_used": n.memory_used,
                "pod_count": n.pod_count,
                "kubelet_version": n.kubelet_version,
            }
            for n in nodes
        ],
        "total": len(nodes),
    }


@router.get("/kubernetes/clusters/{name}/pods")
async def list_cluster_pods(
    name: str,
    request: Request,
    namespace: str | None = None,
) -> dict:
    """List pods in a Kubernetes cluster."""
    tenant_id = _tenant_id(request)
    ch = _clickhouse(request)

    try:
        pods = await _k8s_svc.list_pods(tenant_id, name, namespace, clickhouse=ch)
    except Exception as exc:
        logger.error("Failed to list pods", cluster=name, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to list pods")

    return {
        "pods": [
            {
                "name": p.name,
                "namespace": p.namespace,
                "node": p.node,
                "status": p.status.value,
                "restart_count": p.restart_count,
                "cpu_request": p.cpu_request,
                "cpu_limit": p.cpu_limit,
                "cpu_used": p.cpu_used,
                "memory_request": p.memory_request,
                "memory_limit": p.memory_limit,
                "memory_used": p.memory_used,
                "containers": len(p.containers),
                "owner_kind": p.owner_kind,
                "owner_name": p.owner_name,
                "start_time": p.start_time.isoformat() if p.start_time else None,
            }
            for p in pods
        ],
        "total": len(pods),
    }


@router.get("/kubernetes/clusters/{name}/deployments")
async def list_cluster_deployments(
    name: str,
    request: Request,
    namespace: str | None = None,
) -> dict:
    """List deployments in a Kubernetes cluster."""
    tenant_id = _tenant_id(request)
    ch = _clickhouse(request)

    try:
        deployments = await _k8s_svc.list_deployments(
            tenant_id, name, namespace, clickhouse=ch
        )
    except Exception as exc:
        logger.error("Failed to list deployments", cluster=name, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to list deployments")

    return {
        "deployments": [
            {
                "name": d.name,
                "namespace": d.namespace,
                "replicas_desired": d.replicas_desired,
                "replicas_available": d.replicas_available,
                "replicas_updated": d.replicas_updated,
                "strategy": d.strategy,
            }
            for d in deployments
        ],
        "total": len(deployments),
    }


@router.get("/kubernetes/clusters/{name}/events")
async def list_cluster_events(
    name: str,
    request: Request,
    namespace: str | None = None,
) -> dict:
    """List events in a Kubernetes cluster."""
    tenant_id = _tenant_id(request)
    ch = _clickhouse(request)

    try:
        events = await _k8s_svc.get_events(
            tenant_id, name, namespace, clickhouse=ch
        )
    except Exception as exc:
        logger.error("Failed to list events", cluster=name, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to list events")

    return {
        "events": [
            {
                "type": e.type.value,
                "reason": e.reason,
                "message": e.message,
                "object": e.object,
                "namespace": e.namespace,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                "count": e.count,
            }
            for e in events
        ],
        "total": len(events),
    }


@router.get("/kubernetes/clusters/{name}/issues")
async def list_cluster_issues(name: str, request: Request) -> dict:
    """Detect issues in a Kubernetes cluster."""
    tenant_id = _tenant_id(request)
    ch = _clickhouse(request)

    try:
        issues = await _k8s_svc.detect_issues(tenant_id, name, ch)
    except Exception as exc:
        logger.error("Failed to detect issues", cluster=name, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to detect issues")

    return {
        "issues": [
            {
                "issue_type": i.issue_type,
                "severity": i.severity,
                "resource_kind": i.resource_kind,
                "resource_name": i.resource_name,
                "namespace": i.namespace,
                "description": i.description,
                "detected_at": i.detected_at.isoformat(),
            }
            for i in issues
        ],
        "total": len(issues),
        "critical_count": sum(1 for i in issues if i.severity == "critical"),
        "warning_count": sum(1 for i in issues if i.severity == "warning"),
    }


# ---------------------------------------------------------------------------
# Cloud endpoints
# ---------------------------------------------------------------------------

_cloud_svc = CloudService()


@router.get("/cloud/resources")
async def list_cloud_resources(
    request: Request,
    provider: str | None = None,
    resource_type: str | None = None,
) -> dict:
    """List cloud resources across providers."""
    tenant_id = _tenant_id(request)
    ch = _clickhouse(request)

    cloud_provider = CloudProvider(provider) if provider else None

    try:
        resources = await _cloud_svc.list_resources(
            tenant_id, cloud_provider, resource_type, clickhouse=ch
        )
    except Exception as exc:
        logger.error("Failed to list cloud resources", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to list cloud resources")

    return {
        "resources": [
            {
                "provider": r.provider.value,
                "resource_type": r.resource_type,
                "resource_id": r.resource_id,
                "name": r.name,
                "region": r.region,
                "status": r.status.value,
                "instance_type": r.instance_type,
                "tags": r.tags,
                "metrics": r.metrics,
            }
            for r in resources
        ],
        "total": len(resources),
    }


@router.get("/cloud/costs")
async def get_cloud_costs(
    request: Request,
    provider: str | None = None,
    from_time: str | None = None,
    to_time: str | None = None,
) -> dict:
    """Get cloud cost summary."""
    tenant_id = _tenant_id(request)
    ch = _clickhouse(request)

    cloud_provider = CloudProvider(provider) if provider else None
    time_range = _time_range(from_time, to_time) if from_time else None

    try:
        summary = await _cloud_svc.get_cost_summary(
            tenant_id, cloud_provider, time_range, clickhouse=ch
        )
    except Exception as exc:
        logger.error("Failed to get cloud costs", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to get cloud costs")

    return {
        "total_daily": summary.total_daily,
        "total_monthly_projected": summary.total_monthly_projected,
        "currency": summary.currency,
        "by_service": [
            {
                "service": s.service,
                "daily_cost": s.daily_cost,
                "monthly_projected": s.monthly_projected,
                "resource_count": s.resource_count,
            }
            for s in summary.by_service
        ],
        "top_resources": [
            {
                "resource_id": r.resource_id,
                "service": r.service,
                "daily_cost": r.daily_cost,
                "monthly_projected": r.monthly_projected,
                "region": r.region,
            }
            for r in summary.by_resource[:20]
        ],
    }


@router.get("/cloud/idle")
async def get_idle_resources(
    request: Request,
    provider: str | None = None,
) -> dict:
    """Get idle resource recommendations."""
    tenant_id = _tenant_id(request)
    ch = _clickhouse(request)

    cloud_provider = CloudProvider(provider) if provider else None

    try:
        idle = await _cloud_svc.detect_idle_resources(
            tenant_id, cloud_provider, clickhouse=ch
        )
    except Exception as exc:
        logger.error("Failed to detect idle resources", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to detect idle resources")

    total_savings = sum(i.estimated_monthly_savings for i in idle)

    return {
        "idle_resources": [
            {
                "resource_id": i.resource.resource_id,
                "name": i.resource.name,
                "resource_type": i.resource.resource_type,
                "provider": i.resource.provider.value,
                "region": i.resource.region,
                "idle_reason": i.idle_reason,
                "avg_utilization_pct": i.avg_utilization_pct,
                "estimated_monthly_savings": i.estimated_monthly_savings,
                "recommendation": i.recommendation,
            }
            for i in idle
        ],
        "total": len(idle),
        "total_estimated_monthly_savings": total_savings,
    }


# ---------------------------------------------------------------------------
# Container endpoints
# ---------------------------------------------------------------------------

_container_svc = ContainerService()


@router.get("/containers")
async def list_containers(
    request: Request,
    host_id: str | None = None,
) -> dict:
    """List containers across hosts."""
    tenant_id = _tenant_id(request)
    ch = _clickhouse(request)

    try:
        containers = await _container_svc.list_containers(
            tenant_id, host_id, clickhouse=ch
        )
    except Exception as exc:
        logger.error("Failed to list containers", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to list containers")

    return {
        "containers": [
            {
                "container_id": c.container_id,
                "name": c.name,
                "image": c.image,
                "image_tag": c.image_tag,
                "host_id": c.host_id,
                "status": c.status.value,
                "cpu_pct": c.cpu_pct,
                "memory_used_bytes": c.memory_used_bytes,
                "memory_limit_bytes": c.memory_limit_bytes,
                "network_in_bytes": c.network_in_bytes,
                "network_out_bytes": c.network_out_bytes,
                "pid_count": c.pid_count,
                "runtime": c.runtime.value,
            }
            for c in containers
        ],
        "total": len(containers),
    }
