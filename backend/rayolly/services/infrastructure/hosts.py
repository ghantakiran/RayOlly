"""Host monitoring for infrastructure observability.

Tracks host-level metrics (CPU, memory, disk, network), agent health,
and provides a host map visualization comparable to Datadog Infrastructure.
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


class AnomalyDetector(Protocol):
    """Interface for anomaly detection on metric series."""

    async def detect(
        self, series: list[dict[str, Any]], metric_name: str
    ) -> list[dict[str, Any]]: ...


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class HostStatus(str, Enum):
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNREACHABLE = "unreachable"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HostInfo:
    host_id: str
    hostname: str
    ip_addresses: list[str]
    os: str
    os_version: str
    arch: str
    cpu_count: int
    memory_total_bytes: int
    cloud_provider: str | None = None
    cloud_region: str | None = None
    cloud_instance_type: str | None = None
    cloud_account: str | None = None
    tags: dict[str, str] = field(default_factory=dict)
    agent_version: str = ""
    last_seen: datetime | None = None


@dataclass(frozen=True)
class HostMetrics:
    host_id: str
    timestamp: datetime
    cpu_user_pct: float = 0.0
    cpu_system_pct: float = 0.0
    cpu_iowait_pct: float = 0.0
    cpu_idle_pct: float = 0.0
    memory_used_bytes: int = 0
    memory_free_bytes: int = 0
    memory_cached_bytes: int = 0
    memory_swap_used_bytes: int = 0
    disk_read_bytes_sec: float = 0.0
    disk_write_bytes_sec: float = 0.0
    disk_iops: float = 0.0
    network_in_bytes_sec: float = 0.0
    network_out_bytes_sec: float = 0.0
    network_errors: int = 0
    load_1m: float = 0.0
    load_5m: float = 0.0
    load_15m: float = 0.0
    open_file_descriptors: int = 0
    process_count: int = 0


@dataclass
class ProcessInfo:
    pid: int
    name: str
    user: str
    cpu_pct: float
    memory_pct: float
    memory_rss_bytes: int
    state: str
    started_at: datetime | None = None


@dataclass
class NetworkInterface:
    name: str
    ip_address: str
    mac_address: str
    speed_mbps: int
    in_bytes_sec: float
    out_bytes_sec: float
    errors: int
    drops: int


@dataclass
class DiskMount:
    device: str
    mount_point: str
    filesystem: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    inode_used_pct: float


@dataclass
class InstalledAgent:
    name: str
    version: str
    status: str
    last_check: datetime | None = None


@dataclass
class ContainerSummary:
    container_id: str
    name: str
    image: str
    status: str
    cpu_pct: float
    memory_used_bytes: int


@dataclass
class HostDetail:
    info: HostInfo
    status: HostStatus
    current_metrics: HostMetrics | None
    processes: list[ProcessInfo]
    containers: list[ContainerSummary]
    network_interfaces: list[NetworkInterface]
    disk_mounts: list[DiskMount]
    installed_agents: list[InstalledAgent]


@dataclass
class HostMapEntry:
    host_id: str
    hostname: str
    group_value: str
    color_value: float
    size_value: float
    status: HostStatus
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class HostMapGroup:
    group_name: str
    hosts: list[HostMapEntry]


@dataclass
class HostMapData:
    group_by: str
    color_by: str
    size_by: str
    groups: list[HostMapGroup]


@dataclass
class TimeSeriesPoint:
    timestamp: datetime
    value: float


@dataclass
class MetricTimeSeries:
    metric_name: str
    host_id: str
    data: list[TimeSeriesPoint]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_STATUS_THRESHOLDS = {
    "cpu_critical": 90.0,
    "cpu_warning": 75.0,
    "memory_critical": 90.0,
    "memory_warning": 80.0,
    "unreachable_seconds": 300,
}


def _classify_host_status(
    cpu_total_pct: float,
    memory_used_pct: float,
    last_seen: datetime | None,
) -> HostStatus:
    """Derive host status from current metrics."""
    if last_seen is not None:
        age = (datetime.utcnow() - last_seen).total_seconds()
        if age > _STATUS_THRESHOLDS["unreachable_seconds"]:
            return HostStatus.UNREACHABLE

    if (
        cpu_total_pct >= _STATUS_THRESHOLDS["cpu_critical"]
        or memory_used_pct >= _STATUS_THRESHOLDS["memory_critical"]
    ):
        return HostStatus.CRITICAL

    if (
        cpu_total_pct >= _STATUS_THRESHOLDS["cpu_warning"]
        or memory_used_pct >= _STATUS_THRESHOLDS["memory_warning"]
    ):
        return HostStatus.WARNING

    return HostStatus.HEALTHY


# ---------------------------------------------------------------------------
# HostService
# ---------------------------------------------------------------------------

class HostService:
    """Service layer for host infrastructure monitoring."""

    async def list_hosts(
        self,
        tenant_id: str,
        filters: dict[str, Any] | None = None,
        clickhouse: ClickHouseClient | None = None,
    ) -> list[tuple[HostInfo, HostStatus]]:
        """Return all hosts with their current status.

        Filters support: cloud_provider, cloud_region, tags, hostname pattern,
        status, and agent_version.
        """
        assert clickhouse is not None, "clickhouse client is required"

        where_clauses = ["tenant_id = %(tenant_id)s"]
        params: dict[str, Any] = {"tenant_id": tenant_id}

        if filters:
            if "cloud_provider" in filters:
                where_clauses.append("cloud_provider = %(cloud_provider)s")
                params["cloud_provider"] = filters["cloud_provider"]
            if "cloud_region" in filters:
                where_clauses.append("cloud_region = %(cloud_region)s")
                params["cloud_region"] = filters["cloud_region"]
            if "hostname" in filters:
                where_clauses.append("hostname ILIKE %(hostname)s")
                params["hostname"] = f"%{filters['hostname']}%"

        where = " AND ".join(where_clauses)

        rows = await clickhouse.execute(
            f"""
            SELECT
                h.host_id,
                h.hostname,
                h.ip_addresses,
                h.os,
                h.os_version,
                h.arch,
                h.cpu_count,
                h.memory_total_bytes,
                h.cloud_provider,
                h.cloud_region,
                h.cloud_instance_type,
                h.cloud_account,
                h.tags,
                h.agent_version,
                h.last_seen,
                m.cpu_user_pct + m.cpu_system_pct AS cpu_total_pct,
                m.memory_used_bytes
            FROM infra.hosts AS h
            LEFT JOIN (
                SELECT host_id,
                       argMax(cpu_user_pct, timestamp) AS cpu_user_pct,
                       argMax(cpu_system_pct, timestamp) AS cpu_system_pct,
                       argMax(memory_used_bytes, timestamp) AS memory_used_bytes
                FROM infra.host_metrics
                WHERE tenant_id = %(tenant_id)s
                GROUP BY host_id
            ) AS m ON h.host_id = m.host_id
            WHERE {where}
            ORDER BY h.hostname
            """,
            params,
        )

        results: list[tuple[HostInfo, HostStatus]] = []
        for row in rows:
            info = HostInfo(
                host_id=row["host_id"],
                hostname=row["hostname"],
                ip_addresses=row.get("ip_addresses", []),
                os=row.get("os", ""),
                os_version=row.get("os_version", ""),
                arch=row.get("arch", ""),
                cpu_count=int(row.get("cpu_count", 0)),
                memory_total_bytes=int(row.get("memory_total_bytes", 0)),
                cloud_provider=row.get("cloud_provider"),
                cloud_region=row.get("cloud_region"),
                cloud_instance_type=row.get("cloud_instance_type"),
                cloud_account=row.get("cloud_account"),
                tags=row.get("tags", {}),
                agent_version=row.get("agent_version", ""),
                last_seen=row.get("last_seen"),
            )
            cpu_total = float(row.get("cpu_total_pct", 0))
            mem_total = info.memory_total_bytes or 1
            mem_used_pct = float(row.get("memory_used_bytes", 0)) / mem_total * 100
            status = _classify_host_status(cpu_total, mem_used_pct, info.last_seen)
            results.append((info, status))

        logger.info(
            "Listed hosts for tenant=%s: %d results", tenant_id, len(results)
        )
        return results

    async def get_host_detail(
        self,
        tenant_id: str,
        host_id: str,
        time_range: tuple[datetime, datetime],
        clickhouse: ClickHouseClient,
    ) -> HostDetail:
        """Return comprehensive detail for a single host."""
        start, end = time_range

        # Host info
        info_rows = await clickhouse.execute(
            """
            SELECT *
            FROM infra.hosts
            WHERE tenant_id = %(tenant_id)s AND host_id = %(host_id)s
            LIMIT 1
            """,
            {"tenant_id": tenant_id, "host_id": host_id},
        )

        if not info_rows:
            raise ValueError(f"Host {host_id} not found for tenant {tenant_id}")

        row = info_rows[0]
        info = HostInfo(
            host_id=row["host_id"],
            hostname=row["hostname"],
            ip_addresses=row.get("ip_addresses", []),
            os=row.get("os", ""),
            os_version=row.get("os_version", ""),
            arch=row.get("arch", ""),
            cpu_count=int(row.get("cpu_count", 0)),
            memory_total_bytes=int(row.get("memory_total_bytes", 0)),
            cloud_provider=row.get("cloud_provider"),
            cloud_region=row.get("cloud_region"),
            cloud_instance_type=row.get("cloud_instance_type"),
            cloud_account=row.get("cloud_account"),
            tags=row.get("tags", {}),
            agent_version=row.get("agent_version", ""),
            last_seen=row.get("last_seen"),
        )

        # Latest metrics
        metric_rows = await clickhouse.execute(
            """
            SELECT *
            FROM infra.host_metrics
            WHERE tenant_id = %(tenant_id)s
              AND host_id = %(host_id)s
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            {"tenant_id": tenant_id, "host_id": host_id},
        )

        current_metrics: HostMetrics | None = None
        if metric_rows:
            m = metric_rows[0]
            current_metrics = HostMetrics(
                host_id=host_id,
                timestamp=m["timestamp"],
                cpu_user_pct=float(m.get("cpu_user_pct", 0)),
                cpu_system_pct=float(m.get("cpu_system_pct", 0)),
                cpu_iowait_pct=float(m.get("cpu_iowait_pct", 0)),
                cpu_idle_pct=float(m.get("cpu_idle_pct", 0)),
                memory_used_bytes=int(m.get("memory_used_bytes", 0)),
                memory_free_bytes=int(m.get("memory_free_bytes", 0)),
                memory_cached_bytes=int(m.get("memory_cached_bytes", 0)),
                memory_swap_used_bytes=int(m.get("memory_swap_used_bytes", 0)),
                disk_read_bytes_sec=float(m.get("disk_read_bytes_sec", 0)),
                disk_write_bytes_sec=float(m.get("disk_write_bytes_sec", 0)),
                disk_iops=float(m.get("disk_iops", 0)),
                network_in_bytes_sec=float(m.get("network_in_bytes_sec", 0)),
                network_out_bytes_sec=float(m.get("network_out_bytes_sec", 0)),
                network_errors=int(m.get("network_errors", 0)),
                load_1m=float(m.get("load_1m", 0)),
                load_5m=float(m.get("load_5m", 0)),
                load_15m=float(m.get("load_15m", 0)),
                open_file_descriptors=int(m.get("open_file_descriptors", 0)),
                process_count=int(m.get("process_count", 0)),
            )

        # Top processes
        proc_rows = await clickhouse.execute(
            """
            SELECT pid, name, user, cpu_pct, memory_pct,
                   memory_rss_bytes, state, started_at
            FROM infra.host_processes
            WHERE tenant_id = %(tenant_id)s
              AND host_id = %(host_id)s
              AND timestamp = (
                  SELECT max(timestamp)
                  FROM infra.host_processes
                  WHERE tenant_id = %(tenant_id)s AND host_id = %(host_id)s
              )
            ORDER BY cpu_pct DESC
            LIMIT 50
            """,
            {"tenant_id": tenant_id, "host_id": host_id},
        )
        processes = [
            ProcessInfo(
                pid=int(r["pid"]),
                name=r["name"],
                user=r["user"],
                cpu_pct=float(r["cpu_pct"]),
                memory_pct=float(r["memory_pct"]),
                memory_rss_bytes=int(r["memory_rss_bytes"]),
                state=r["state"],
                started_at=r.get("started_at"),
            )
            for r in proc_rows
        ]

        # Containers on this host
        container_rows = await clickhouse.execute(
            """
            SELECT container_id, name, image, status,
                   cpu_pct, memory_used_bytes
            FROM infra.containers
            WHERE tenant_id = %(tenant_id)s
              AND host_id = %(host_id)s
              AND timestamp = (
                  SELECT max(timestamp)
                  FROM infra.containers
                  WHERE tenant_id = %(tenant_id)s AND host_id = %(host_id)s
              )
            ORDER BY cpu_pct DESC
            """,
            {"tenant_id": tenant_id, "host_id": host_id},
        )
        containers = [
            ContainerSummary(
                container_id=r["container_id"],
                name=r["name"],
                image=r["image"],
                status=r["status"],
                cpu_pct=float(r["cpu_pct"]),
                memory_used_bytes=int(r["memory_used_bytes"]),
            )
            for r in container_rows
        ]

        # Network interfaces
        nic_rows = await clickhouse.execute(
            """
            SELECT name, ip_address, mac_address, speed_mbps,
                   in_bytes_sec, out_bytes_sec, errors, drops
            FROM infra.host_network_interfaces
            WHERE tenant_id = %(tenant_id)s AND host_id = %(host_id)s
            ORDER BY name
            """,
            {"tenant_id": tenant_id, "host_id": host_id},
        )
        network_interfaces = [
            NetworkInterface(
                name=r["name"],
                ip_address=r["ip_address"],
                mac_address=r["mac_address"],
                speed_mbps=int(r["speed_mbps"]),
                in_bytes_sec=float(r["in_bytes_sec"]),
                out_bytes_sec=float(r["out_bytes_sec"]),
                errors=int(r["errors"]),
                drops=int(r["drops"]),
            )
            for r in nic_rows
        ]

        # Disk mounts
        disk_rows = await clickhouse.execute(
            """
            SELECT device, mount_point, filesystem,
                   total_bytes, used_bytes, free_bytes, inode_used_pct
            FROM infra.host_disk_mounts
            WHERE tenant_id = %(tenant_id)s AND host_id = %(host_id)s
            ORDER BY mount_point
            """,
            {"tenant_id": tenant_id, "host_id": host_id},
        )
        disk_mounts = [
            DiskMount(
                device=r["device"],
                mount_point=r["mount_point"],
                filesystem=r["filesystem"],
                total_bytes=int(r["total_bytes"]),
                used_bytes=int(r["used_bytes"]),
                free_bytes=int(r["free_bytes"]),
                inode_used_pct=float(r["inode_used_pct"]),
            )
            for r in disk_rows
        ]

        # Installed agents
        agent_rows = await clickhouse.execute(
            """
            SELECT name, version, status, last_check
            FROM infra.host_agents
            WHERE tenant_id = %(tenant_id)s AND host_id = %(host_id)s
            ORDER BY name
            """,
            {"tenant_id": tenant_id, "host_id": host_id},
        )
        installed_agents = [
            InstalledAgent(
                name=r["name"],
                version=r["version"],
                status=r["status"],
                last_check=r.get("last_check"),
            )
            for r in agent_rows
        ]

        # Determine status
        cpu_total = 0.0
        mem_used_pct = 0.0
        if current_metrics:
            cpu_total = current_metrics.cpu_user_pct + current_metrics.cpu_system_pct
            mem_total = info.memory_total_bytes or 1
            mem_used_pct = current_metrics.memory_used_bytes / mem_total * 100

        status = _classify_host_status(cpu_total, mem_used_pct, info.last_seen)

        logger.info(
            "Fetched host detail for tenant=%s host=%s status=%s",
            tenant_id,
            host_id,
            status.value,
        )

        return HostDetail(
            info=info,
            status=status,
            current_metrics=current_metrics,
            processes=processes,
            containers=containers,
            network_interfaces=network_interfaces,
            disk_mounts=disk_mounts,
            installed_agents=installed_agents,
        )

    async def get_host_metrics(
        self,
        tenant_id: str,
        host_id: str,
        metric_names: list[str],
        time_range: tuple[datetime, datetime],
        clickhouse: ClickHouseClient,
    ) -> list[MetricTimeSeries]:
        """Return time-series data for requested host metrics."""
        start, end = time_range

        # Build select columns from requested metric names
        valid_metrics = {
            "cpu_user_pct", "cpu_system_pct", "cpu_iowait_pct", "cpu_idle_pct",
            "memory_used_bytes", "memory_free_bytes", "memory_cached_bytes",
            "memory_swap_used_bytes", "disk_read_bytes_sec", "disk_write_bytes_sec",
            "disk_iops", "network_in_bytes_sec", "network_out_bytes_sec",
            "network_errors", "load_1m", "load_5m", "load_15m",
            "open_file_descriptors", "process_count",
        }

        requested = [m for m in metric_names if m in valid_metrics]
        if not requested:
            return []

        columns = ", ".join(requested)
        rows = await clickhouse.execute(
            f"""
            SELECT timestamp, {columns}
            FROM infra.host_metrics
            WHERE tenant_id = %(tenant_id)s
              AND host_id = %(host_id)s
              AND timestamp BETWEEN %(start)s AND %(end)s
            ORDER BY timestamp
            """,
            {"tenant_id": tenant_id, "host_id": host_id, "start": start, "end": end},
        )

        series_map: dict[str, list[TimeSeriesPoint]] = {m: [] for m in requested}
        for row in rows:
            ts = row["timestamp"]
            for metric in requested:
                series_map[metric].append(
                    TimeSeriesPoint(timestamp=ts, value=float(row.get(metric, 0)))
                )

        result = [
            MetricTimeSeries(metric_name=m, host_id=host_id, data=points)
            for m, points in series_map.items()
        ]

        logger.info(
            "Fetched %d metrics for tenant=%s host=%s (%d points each)",
            len(result),
            tenant_id,
            host_id,
            len(rows),
        )
        return result

    async def detect_host_anomalies(
        self,
        tenant_id: str,
        host_id: str,
        clickhouse: ClickHouseClient,
        anomaly_detector: AnomalyDetector,
    ) -> list[dict[str, Any]]:
        """Run anomaly detection on recent host metrics."""

        # Fetch the last hour of metrics at 10s granularity
        rows = await clickhouse.execute(
            """
            SELECT timestamp,
                   cpu_user_pct + cpu_system_pct AS cpu_total_pct,
                   memory_used_bytes,
                   disk_iops,
                   network_in_bytes_sec + network_out_bytes_sec AS network_total_bytes_sec,
                   load_5m
            FROM infra.host_metrics
            WHERE tenant_id = %(tenant_id)s
              AND host_id = %(host_id)s
              AND timestamp >= now() - INTERVAL 1 HOUR
            ORDER BY timestamp
            """,
            {"tenant_id": tenant_id, "host_id": host_id},
        )

        if not rows:
            return []

        anomalies: list[dict[str, Any]] = []
        metric_columns = [
            "cpu_total_pct",
            "memory_used_bytes",
            "disk_iops",
            "network_total_bytes_sec",
            "load_5m",
        ]

        for metric in metric_columns:
            series = [
                {"timestamp": r["timestamp"], "value": float(r.get(metric, 0))}
                for r in rows
            ]
            detected = await anomaly_detector.detect(series, metric)
            for anomaly in detected:
                anomalies.append({
                    "host_id": host_id,
                    "metric": metric,
                    "timestamp": anomaly.get("timestamp"),
                    "value": anomaly.get("value"),
                    "expected_range": anomaly.get("expected_range"),
                    "severity": anomaly.get("severity", "warning"),
                })

        logger.info(
            "Detected %d anomalies for tenant=%s host=%s",
            len(anomalies),
            tenant_id,
            host_id,
        )
        return anomalies

    async def get_host_map(
        self,
        tenant_id: str,
        group_by: str,
        color_by: str,
        size_by: str,
        clickhouse: ClickHouseClient,
    ) -> HostMapData:
        """Build host map data for visualization.

        Parameters:
            group_by: Field to group hosts (e.g. cloud_region, cloud_provider,
                      cloud_instance_type, or a tag key like "tag:env").
            color_by: Metric to use for coloring (e.g. cpu_user_pct, memory_used_pct).
            size_by:  Metric to use for sizing (e.g. memory_total_bytes, cpu_count).
        """

        # Resolve group_by column
        if group_by.startswith("tag:"):
            tag_key = group_by[4:]
            group_expr = f"h.tags['{tag_key}']"
        else:
            group_expr = f"h.{group_by}"

        # Map color_by / size_by to metric expressions
        metric_expr_map = {
            "cpu_user_pct": "m.cpu_user_pct",
            "cpu_total_pct": "m.cpu_user_pct + m.cpu_system_pct",
            "memory_used_pct": "m.memory_used_bytes / h.memory_total_bytes * 100",
            "memory_total_bytes": "h.memory_total_bytes",
            "cpu_count": "h.cpu_count",
            "load_5m": "m.load_5m",
            "disk_iops": "m.disk_iops",
            "network_total_bytes_sec": "m.network_in_bytes_sec + m.network_out_bytes_sec",
        }

        color_expr = metric_expr_map.get(color_by, "m.cpu_user_pct + m.cpu_system_pct")
        size_expr = metric_expr_map.get(size_by, "h.memory_total_bytes")

        rows = await clickhouse.execute(
            f"""
            SELECT
                h.host_id,
                h.hostname,
                {group_expr} AS group_value,
                ({color_expr}) AS color_value,
                ({size_expr}) AS size_value,
                h.tags,
                h.last_seen,
                m.cpu_user_pct + m.cpu_system_pct AS cpu_total,
                m.memory_used_bytes / h.memory_total_bytes * 100 AS mem_used_pct
            FROM infra.hosts AS h
            LEFT JOIN (
                SELECT host_id,
                       argMax(cpu_user_pct, timestamp) AS cpu_user_pct,
                       argMax(cpu_system_pct, timestamp) AS cpu_system_pct,
                       argMax(memory_used_bytes, timestamp) AS memory_used_bytes,
                       argMax(load_5m, timestamp) AS load_5m,
                       argMax(disk_iops, timestamp) AS disk_iops,
                       argMax(network_in_bytes_sec, timestamp) AS network_in_bytes_sec,
                       argMax(network_out_bytes_sec, timestamp) AS network_out_bytes_sec
                FROM infra.host_metrics
                WHERE tenant_id = %(tenant_id)s
                GROUP BY host_id
            ) AS m ON h.host_id = m.host_id
            WHERE h.tenant_id = %(tenant_id)s
            ORDER BY group_value, h.hostname
            """,
            {"tenant_id": tenant_id},
        )

        groups_dict: dict[str, list[HostMapEntry]] = {}
        for row in rows:
            gv = str(row.get("group_value", "unknown"))
            status = _classify_host_status(
                float(row.get("cpu_total", 0)),
                float(row.get("mem_used_pct", 0)),
                row.get("last_seen"),
            )
            entry = HostMapEntry(
                host_id=row["host_id"],
                hostname=row["hostname"],
                group_value=gv,
                color_value=float(row.get("color_value", 0)),
                size_value=float(row.get("size_value", 0)),
                status=status,
                tags=row.get("tags", {}),
            )
            groups_dict.setdefault(gv, []).append(entry)

        groups = [
            HostMapGroup(group_name=name, hosts=hosts)
            for name, hosts in groups_dict.items()
        ]

        logger.info(
            "Built host map for tenant=%s: %d groups, %d total hosts",
            tenant_id,
            len(groups),
            sum(len(g.hosts) for g in groups),
        )

        return HostMapData(
            group_by=group_by,
            color_by=color_by,
            size_by=size_by,
            groups=groups,
        )
