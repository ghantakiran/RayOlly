"""Container monitoring for infrastructure observability.

Tracks container-level metrics across Docker, containerd, and CRI-O runtimes,
comparable to Datadog Container monitoring and Dynatrace container views.
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

class ContainerStatus(str, Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    PAUSED = "paused"
    RESTARTING = "restarting"


class ContainerRuntime(str, Enum):
    DOCKER = "docker"
    CONTAINERD = "containerd"
    CRI_O = "cri-o"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ContainerInfo:
    container_id: str
    name: str
    image: str
    image_tag: str
    host_id: str
    status: ContainerStatus
    cpu_pct: float = 0.0
    memory_used_bytes: int = 0
    memory_limit_bytes: int = 0
    network_in_bytes: int = 0
    network_out_bytes: int = 0
    disk_read_bytes: int = 0
    disk_write_bytes: int = 0
    pid_count: int = 0
    started_at: datetime | None = None
    runtime: ContainerRuntime = ContainerRuntime.DOCKER


@dataclass
class ContainerPort:
    container_port: int
    host_port: int | None
    protocol: str  # tcp, udp


@dataclass
class ContainerMount:
    source: str
    destination: str
    mode: str  # rw, ro
    mount_type: str  # bind, volume, tmpfs


@dataclass
class ContainerEnvVar:
    key: str
    value: str
    source: str  # env, secret, configmap


@dataclass
class ContainerLogEntry:
    timestamp: datetime
    stream: str  # stdout, stderr
    message: str


@dataclass
class ContainerDetail:
    info: ContainerInfo
    env_vars: list[ContainerEnvVar]
    mounts: list[ContainerMount]
    ports: list[ContainerPort]
    logs: list[ContainerLogEntry]
    labels: dict[str, str] = field(default_factory=dict)
    command: str = ""
    entrypoint: str = ""
    restart_count: int = 0


@dataclass
class TimeSeriesPoint:
    timestamp: datetime
    value: float


@dataclass
class ContainerTimeSeries:
    metric_name: str
    container_id: str
    data: list[TimeSeriesPoint]


@dataclass
class ContainerIssue:
    container_id: str
    container_name: str
    host_id: str
    issue_type: str  # high_cpu, high_memory, restart_loop, oom_risk
    severity: str  # warning, critical
    description: str
    current_value: float
    threshold: float
    detected_at: datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ISSUE_THRESHOLDS = {
    "cpu_critical": 90.0,
    "cpu_warning": 75.0,
    "memory_critical_pct": 90.0,
    "memory_warning_pct": 80.0,
    "restart_count_warning": 3,
    "restart_count_critical": 10,
}


# ---------------------------------------------------------------------------
# ContainerService
# ---------------------------------------------------------------------------

class ContainerService:
    """Service layer for container infrastructure monitoring."""

    async def list_containers(
        self,
        tenant_id: str,
        host_id: str | None = None,
        clickhouse: ClickHouseClient | None = None,
    ) -> list[ContainerInfo]:
        """List containers, optionally filtered by host.

        Returns the latest snapshot of container state.
        """
        assert clickhouse is not None, "clickhouse client is required"

        where_clauses = ["tenant_id = %(tenant_id)s"]
        params: dict[str, Any] = {"tenant_id": tenant_id}

        if host_id:
            where_clauses.append("host_id = %(host_id)s")
            params["host_id"] = host_id

        where = " AND ".join(where_clauses)

        rows = await clickhouse.execute(
            f"""
            SELECT
                container_id,
                name,
                image,
                image_tag,
                host_id,
                status,
                cpu_pct,
                memory_used_bytes,
                memory_limit_bytes,
                network_in_bytes,
                network_out_bytes,
                disk_read_bytes,
                disk_write_bytes,
                pid_count,
                started_at,
                runtime
            FROM infra.containers
            WHERE {where}
              AND timestamp = (
                  SELECT max(timestamp)
                  FROM infra.containers
                  WHERE {where}
              )
            ORDER BY name
            """,
            params,
        )

        containers = [
            ContainerInfo(
                container_id=r["container_id"],
                name=r["name"],
                image=r["image"],
                image_tag=r.get("image_tag", "latest"),
                host_id=r["host_id"],
                status=ContainerStatus(r.get("status", "running")),
                cpu_pct=float(r.get("cpu_pct", 0)),
                memory_used_bytes=int(r.get("memory_used_bytes", 0)),
                memory_limit_bytes=int(r.get("memory_limit_bytes", 0)),
                network_in_bytes=int(r.get("network_in_bytes", 0)),
                network_out_bytes=int(r.get("network_out_bytes", 0)),
                disk_read_bytes=int(r.get("disk_read_bytes", 0)),
                disk_write_bytes=int(r.get("disk_write_bytes", 0)),
                pid_count=int(r.get("pid_count", 0)),
                started_at=r.get("started_at"),
                runtime=ContainerRuntime(r.get("runtime", "docker")),
            )
            for r in rows
        ]

        logger.info(
            "Listed %d containers for tenant=%s host=%s",
            len(containers),
            tenant_id,
            host_id or "all",
        )
        return containers

    async def get_container_detail(
        self,
        tenant_id: str,
        container_id: str,
        clickhouse: ClickHouseClient,
    ) -> ContainerDetail:
        """Return detailed info for a single container including env, mounts, ports, and logs."""

        # Container info
        info_rows = await clickhouse.execute(
            """
            SELECT *
            FROM infra.containers
            WHERE tenant_id = %(tenant_id)s
              AND container_id = %(container_id)s
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            {"tenant_id": tenant_id, "container_id": container_id},
        )

        if not info_rows:
            raise ValueError(
                f"Container {container_id} not found for tenant {tenant_id}"
            )

        r = info_rows[0]
        info = ContainerInfo(
            container_id=r["container_id"],
            name=r["name"],
            image=r["image"],
            image_tag=r.get("image_tag", "latest"),
            host_id=r["host_id"],
            status=ContainerStatus(r.get("status", "running")),
            cpu_pct=float(r.get("cpu_pct", 0)),
            memory_used_bytes=int(r.get("memory_used_bytes", 0)),
            memory_limit_bytes=int(r.get("memory_limit_bytes", 0)),
            network_in_bytes=int(r.get("network_in_bytes", 0)),
            network_out_bytes=int(r.get("network_out_bytes", 0)),
            disk_read_bytes=int(r.get("disk_read_bytes", 0)),
            disk_write_bytes=int(r.get("disk_write_bytes", 0)),
            pid_count=int(r.get("pid_count", 0)),
            started_at=r.get("started_at"),
            runtime=ContainerRuntime(r.get("runtime", "docker")),
        )

        # Environment variables
        env_rows = await clickhouse.execute(
            """
            SELECT key, value, source
            FROM infra.container_env
            WHERE tenant_id = %(tenant_id)s
              AND container_id = %(container_id)s
            ORDER BY key
            """,
            {"tenant_id": tenant_id, "container_id": container_id},
        )
        env_vars = [
            ContainerEnvVar(key=e["key"], value=e["value"], source=e.get("source", "env"))
            for e in env_rows
        ]

        # Mounts
        mount_rows = await clickhouse.execute(
            """
            SELECT source, destination, mode, mount_type
            FROM infra.container_mounts
            WHERE tenant_id = %(tenant_id)s
              AND container_id = %(container_id)s
            ORDER BY destination
            """,
            {"tenant_id": tenant_id, "container_id": container_id},
        )
        mounts = [
            ContainerMount(
                source=m["source"],
                destination=m["destination"],
                mode=m.get("mode", "rw"),
                mount_type=m.get("mount_type", "bind"),
            )
            for m in mount_rows
        ]

        # Ports
        port_rows = await clickhouse.execute(
            """
            SELECT container_port, host_port, protocol
            FROM infra.container_ports
            WHERE tenant_id = %(tenant_id)s
              AND container_id = %(container_id)s
            ORDER BY container_port
            """,
            {"tenant_id": tenant_id, "container_id": container_id},
        )
        ports = [
            ContainerPort(
                container_port=int(p["container_port"]),
                host_port=int(p["host_port"]) if p.get("host_port") else None,
                protocol=p.get("protocol", "tcp"),
            )
            for p in port_rows
        ]

        # Recent logs
        log_rows = await clickhouse.execute(
            """
            SELECT timestamp, stream, message
            FROM infra.container_logs
            WHERE tenant_id = %(tenant_id)s
              AND container_id = %(container_id)s
            ORDER BY timestamp DESC
            LIMIT 200
            """,
            {"tenant_id": tenant_id, "container_id": container_id},
        )
        logs = [
            ContainerLogEntry(
                timestamp=l["timestamp"],
                stream=l.get("stream", "stdout"),
                message=l["message"],
            )
            for l in log_rows
        ]
        logs.reverse()  # Chronological order

        logger.info(
            "Fetched container detail for tenant=%s container=%s",
            tenant_id,
            container_id,
        )

        return ContainerDetail(
            info=info,
            env_vars=env_vars,
            mounts=mounts,
            ports=ports,
            logs=logs,
            labels=r.get("labels", {}),
            command=r.get("command", ""),
            entrypoint=r.get("entrypoint", ""),
            restart_count=int(r.get("restart_count", 0)),
        )

    async def get_container_metrics(
        self,
        tenant_id: str,
        container_id: str,
        time_range: tuple[datetime, datetime],
        clickhouse: ClickHouseClient,
    ) -> list[ContainerTimeSeries]:
        """Return time-series metrics for a container."""
        start, end = time_range

        metrics = [
            "cpu_pct",
            "memory_used_bytes",
            "network_in_bytes",
            "network_out_bytes",
            "disk_read_bytes",
            "disk_write_bytes",
            "pid_count",
        ]
        columns = ", ".join(metrics)

        rows = await clickhouse.execute(
            f"""
            SELECT timestamp, {columns}
            FROM infra.containers
            WHERE tenant_id = %(tenant_id)s
              AND container_id = %(container_id)s
              AND timestamp BETWEEN %(start)s AND %(end)s
            ORDER BY timestamp
            """,
            {
                "tenant_id": tenant_id,
                "container_id": container_id,
                "start": start,
                "end": end,
            },
        )

        series_map: dict[str, list[TimeSeriesPoint]] = {m: [] for m in metrics}
        for row in rows:
            ts = row["timestamp"]
            for metric in metrics:
                series_map[metric].append(
                    TimeSeriesPoint(timestamp=ts, value=float(row.get(metric, 0)))
                )

        result = [
            ContainerTimeSeries(metric_name=m, container_id=container_id, data=points)
            for m, points in series_map.items()
        ]

        logger.info(
            "Fetched container metrics for tenant=%s container=%s: %d series, %d points",
            tenant_id,
            container_id,
            len(result),
            len(rows),
        )
        return result

    async def detect_container_issues(
        self,
        tenant_id: str,
        clickhouse: ClickHouseClient,
    ) -> list[ContainerIssue]:
        """Detect containers with high CPU, high memory, or restart loops."""

        now = datetime.utcnow()
        issues: list[ContainerIssue] = []

        # High CPU containers
        cpu_rows = await clickhouse.execute(
            """
            SELECT container_id, name, host_id, cpu_pct
            FROM infra.containers
            WHERE tenant_id = %(tenant_id)s
              AND status = 'running'
              AND timestamp = (
                  SELECT max(timestamp)
                  FROM infra.containers
                  WHERE tenant_id = %(tenant_id)s
              )
              AND cpu_pct >= %(cpu_warning)s
            ORDER BY cpu_pct DESC
            """,
            {
                "tenant_id": tenant_id,
                "cpu_warning": _ISSUE_THRESHOLDS["cpu_warning"],
            },
        )

        for r in cpu_rows:
            cpu = float(r["cpu_pct"])
            severity = (
                "critical"
                if cpu >= _ISSUE_THRESHOLDS["cpu_critical"]
                else "warning"
            )
            issues.append(
                ContainerIssue(
                    container_id=r["container_id"],
                    container_name=r["name"],
                    host_id=r["host_id"],
                    issue_type="high_cpu",
                    severity=severity,
                    description=f"Container CPU usage at {cpu:.1f}%",
                    current_value=cpu,
                    threshold=_ISSUE_THRESHOLDS[f"cpu_{severity}"],
                    detected_at=now,
                )
            )

        # High memory containers
        mem_rows = await clickhouse.execute(
            """
            SELECT container_id, name, host_id,
                   memory_used_bytes, memory_limit_bytes,
                   memory_used_bytes / memory_limit_bytes * 100 AS memory_pct
            FROM infra.containers
            WHERE tenant_id = %(tenant_id)s
              AND status = 'running'
              AND memory_limit_bytes > 0
              AND timestamp = (
                  SELECT max(timestamp)
                  FROM infra.containers
                  WHERE tenant_id = %(tenant_id)s
              )
              AND memory_used_bytes / memory_limit_bytes * 100 >= %(mem_warning)s
            ORDER BY memory_pct DESC
            """,
            {
                "tenant_id": tenant_id,
                "mem_warning": _ISSUE_THRESHOLDS["memory_warning_pct"],
            },
        )

        for r in mem_rows:
            mem_pct = float(r["memory_pct"])
            severity = (
                "critical"
                if mem_pct >= _ISSUE_THRESHOLDS["memory_critical_pct"]
                else "warning"
            )
            issues.append(
                ContainerIssue(
                    container_id=r["container_id"],
                    container_name=r["name"],
                    host_id=r["host_id"],
                    issue_type="high_memory" if severity == "warning" else "oom_risk",
                    severity=severity,
                    description=f"Container memory at {mem_pct:.1f}% of limit",
                    current_value=mem_pct,
                    threshold=_ISSUE_THRESHOLDS[f"memory_{severity}_pct"],
                    detected_at=now,
                )
            )

        # Restart loops
        restart_rows = await clickhouse.execute(
            """
            SELECT container_id, name, host_id, restart_count
            FROM infra.containers
            WHERE tenant_id = %(tenant_id)s
              AND timestamp = (
                  SELECT max(timestamp)
                  FROM infra.containers
                  WHERE tenant_id = %(tenant_id)s
              )
              AND restart_count >= %(restart_warning)s
            ORDER BY restart_count DESC
            """,
            {
                "tenant_id": tenant_id,
                "restart_warning": _ISSUE_THRESHOLDS["restart_count_warning"],
            },
        )

        for r in restart_rows:
            count = int(r["restart_count"])
            severity = (
                "critical"
                if count >= _ISSUE_THRESHOLDS["restart_count_critical"]
                else "warning"
            )
            issues.append(
                ContainerIssue(
                    container_id=r["container_id"],
                    container_name=r["name"],
                    host_id=r["host_id"],
                    issue_type="restart_loop",
                    severity=severity,
                    description=f"Container has restarted {count} times",
                    current_value=float(count),
                    threshold=float(
                        _ISSUE_THRESHOLDS[f"restart_count_{severity}"]
                    ),
                    detected_at=now,
                )
            )

        logger.info(
            "Detected %d container issues for tenant=%s", len(issues), tenant_id
        )
        return issues
