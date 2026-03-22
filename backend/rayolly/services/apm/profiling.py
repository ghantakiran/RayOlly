"""Continuous profiling integration for APM.

Stores, retrieves, and correlates application profiles (CPU, heap, etc.)
with traces. Supports pprof and JFR formats.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------

class S3Client(Protocol):
    async def put_object(self, bucket: str, key: str, body: bytes, **kwargs: Any) -> None: ...
    async def get_object(self, bucket: str, key: str) -> bytes: ...
    async def list_objects(self, bucket: str, prefix: str) -> list[dict[str, Any]]: ...


class ClickHouseClient(Protocol):
    async def execute(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]: ...


# ---------------------------------------------------------------------------
# Enums & Data classes
# ---------------------------------------------------------------------------

class ProfileType(str, Enum):
    CPU = "cpu"
    HEAP = "heap"
    ALLOCS = "allocs"
    GOROUTINE = "goroutine"
    MUTEX = "mutex"
    BLOCK = "block"
    WALL = "wall"


class ProfileFormat(str, Enum):
    PPROF = "pprof"
    JFR = "jfr"


@dataclass
class ProfileData:
    profile_type: ProfileType
    service: str
    timestamp: datetime
    duration_seconds: float
    sample_count: int
    data: bytes
    format: ProfileFormat


@dataclass
class ProfileMetadata:
    profile_id: str
    profile_type: ProfileType
    service: str
    timestamp: datetime
    duration_seconds: float
    sample_count: int
    format: ProfileFormat
    s3_key: str
    size_bytes: int


@dataclass
class FlameGraphNode:
    name: str
    self_value: int
    total_value: int
    children: list[FlameGraphNode] = field(default_factory=list)


# ---------------------------------------------------------------------------
# ProfilingService
# ---------------------------------------------------------------------------

_S3_BUCKET = "rayolly-profiles"


class ProfilingService:
    """Manages continuous profiling data ingestion, retrieval, and correlation."""

    def __init__(self, s3_client: S3Client, clickhouse: ClickHouseClient) -> None:
        self._s3 = s3_client
        self._ch = clickhouse

    async def ingest_profile(self, tenant_id: str, profile: ProfileData) -> str:
        """Store a profile in S3 and record metadata in ClickHouse.

        Returns the generated profile_id.
        """
        profile_id = str(uuid.uuid4())
        s3_key = (
            f"profiles/{tenant_id}/{profile.service}/{profile.profile_type.value}"
            f"/{profile.timestamp.strftime('%Y/%m/%d')}/{profile_id}.{profile.format.value}"
        )

        # Store binary data in S3
        try:
            await self._s3.put_object(
                bucket=_S3_BUCKET,
                key=s3_key,
                body=profile.data,
                content_type="application/octet-stream",
            )
        except Exception:
            logger.exception("Failed to upload profile %s to S3", profile_id)
            raise

        # Record metadata in ClickHouse
        await self._ch.execute(
            """
            INSERT INTO apm.profiles (
                tenant_id, profile_id, profile_type, service_name,
                timestamp, duration_seconds, sample_count, format,
                s3_key, size_bytes
            ) VALUES (
                %(tenant_id)s, %(profile_id)s, %(profile_type)s, %(service)s,
                %(timestamp)s, %(duration)s, %(samples)s, %(format)s,
                %(s3_key)s, %(size)s
            )
            """,
            {
                "tenant_id": tenant_id,
                "profile_id": profile_id,
                "profile_type": profile.profile_type.value,
                "service": profile.service,
                "timestamp": profile.timestamp,
                "duration": profile.duration_seconds,
                "samples": profile.sample_count,
                "format": profile.format.value,
                "s3_key": s3_key,
                "size": len(profile.data),
            },
        )

        logger.info(
            "Ingested profile %s for %s/%s (%d bytes)",
            profile_id,
            tenant_id,
            profile.service,
            len(profile.data),
        )
        return profile_id

    async def get_profiles(
        self,
        tenant_id: str,
        service: str,
        profile_type: ProfileType,
        time_range: tuple[datetime, datetime],
    ) -> list[ProfileMetadata]:
        """List profile metadata matching the given criteria."""
        start, end = time_range

        rows = await self._ch.execute(
            """
            SELECT
                profile_id, profile_type, service_name, timestamp,
                duration_seconds, sample_count, format, s3_key, size_bytes
            FROM apm.profiles
            WHERE tenant_id = %(tenant_id)s
              AND service_name = %(service)s
              AND profile_type = %(type)s
              AND timestamp BETWEEN %(start)s AND %(end)s
            ORDER BY timestamp DESC
            LIMIT 100
            """,
            {
                "tenant_id": tenant_id,
                "service": service,
                "type": profile_type.value,
                "start": start,
                "end": end,
            },
        )

        return [
            ProfileMetadata(
                profile_id=r["profile_id"],
                profile_type=ProfileType(r["profile_type"]),
                service=r["service_name"],
                timestamp=r["timestamp"],
                duration_seconds=float(r["duration_seconds"]),
                sample_count=int(r["sample_count"]),
                format=ProfileFormat(r["format"]),
                s3_key=r["s3_key"],
                size_bytes=int(r["size_bytes"]),
            )
            for r in rows
        ]

    async def get_flame_graph(self, tenant_id: str, profile_id: str) -> FlameGraphNode:
        """Retrieve a profile from S3 and parse it into a flame graph tree."""

        # Fetch metadata
        rows = await self._ch.execute(
            """
            SELECT s3_key, format
            FROM apm.profiles
            WHERE tenant_id = %(tenant_id)s AND profile_id = %(profile_id)s
            LIMIT 1
            """,
            {"tenant_id": tenant_id, "profile_id": profile_id},
        )

        if not rows:
            raise ValueError(f"Profile {profile_id} not found for tenant {tenant_id}")

        s3_key = rows[0]["s3_key"]
        profile_format = ProfileFormat(rows[0]["format"])

        raw_data = await self._s3.get_object(bucket=_S3_BUCKET, key=s3_key)

        return self._parse_profile_to_flame_graph(raw_data, profile_format)

    async def correlate_with_trace(
        self,
        tenant_id: str,
        trace_id: str,
    ) -> ProfileMetadata | None:
        """Find a profile that overlaps with the given trace's time window."""

        # Get trace time range
        trace_rows = await self._ch.execute(
            """
            SELECT
                service_name,
                min(start_time) AS trace_start,
                max(end_time) AS trace_end
            FROM traces.spans
            WHERE tenant_id = %(tenant_id)s AND trace_id = %(trace_id)s
            GROUP BY service_name
            LIMIT 1
            """,
            {"tenant_id": tenant_id, "trace_id": trace_id},
        )

        if not trace_rows:
            return None

        service = trace_rows[0]["service_name"]
        trace_start = trace_rows[0]["trace_start"]
        trace_end = trace_rows[0]["trace_end"]

        # Find overlapping profile
        profile_rows = await self._ch.execute(
            """
            SELECT
                profile_id, profile_type, service_name, timestamp,
                duration_seconds, sample_count, format, s3_key, size_bytes
            FROM apm.profiles
            WHERE tenant_id = %(tenant_id)s
              AND service_name = %(service)s
              AND timestamp <= %(trace_end)s
              AND timestamp + toIntervalSecond(duration_seconds) >= %(trace_start)s
            ORDER BY abs(dateDiff('second', timestamp, %(trace_start)s))
            LIMIT 1
            """,
            {
                "tenant_id": tenant_id,
                "service": service,
                "trace_start": trace_start,
                "trace_end": trace_end,
            },
        )

        if not profile_rows:
            return None

        r = profile_rows[0]
        return ProfileMetadata(
            profile_id=r["profile_id"],
            profile_type=ProfileType(r["profile_type"]),
            service=r["service_name"],
            timestamp=r["timestamp"],
            duration_seconds=float(r["duration_seconds"]),
            sample_count=int(r["sample_count"]),
            format=ProfileFormat(r["format"]),
            s3_key=r["s3_key"],
            size_bytes=int(r["size_bytes"]),
        )

    # ------------------------------------------------------------------
    # Internal parsing
    # ------------------------------------------------------------------

    def _parse_profile_to_flame_graph(
        self,
        raw_data: bytes,
        profile_format: ProfileFormat,
    ) -> FlameGraphNode:
        """Parse raw profile bytes into a FlameGraphNode tree.

        Supports pprof (protobuf) and JFR formats. The actual parsing
        delegates to format-specific parsers.
        """
        if profile_format == ProfileFormat.PPROF:
            return self._parse_pprof(raw_data)
        elif profile_format == ProfileFormat.JFR:
            return self._parse_jfr(raw_data)
        else:
            raise ValueError(f"Unsupported profile format: {profile_format}")

    def _parse_pprof(self, data: bytes) -> FlameGraphNode:
        """Parse a pprof protobuf profile into a flame graph.

        Uses a stack-folding approach: each sample's stack frames
        are walked to build a tree of FlameGraphNode objects.
        """
        # NOTE: In production, use google.protobuf to decode the pprof Profile message.
        # This implementation provides the structural parsing logic.
        try:
            import gzip

            decompressed = gzip.decompress(data)
        except Exception:
            decompressed = data

        return self._build_flame_tree_from_stacks(
            self._extract_stacks_from_pprof(decompressed)
        )

    def _parse_jfr(self, data: bytes) -> FlameGraphNode:
        """Parse a JFR recording into a flame graph.

        NOTE: In production, use a JFR parser library.
        """
        return self._build_flame_tree_from_stacks(
            self._extract_stacks_from_jfr(data)
        )

    def _extract_stacks_from_pprof(self, data: bytes) -> list[tuple[list[str], int]]:
        """Extract (stack_frames, value) tuples from pprof data.

        Placeholder: real implementation decodes protobuf.
        """
        _ = data
        return []

    def _extract_stacks_from_jfr(self, data: bytes) -> list[tuple[list[str], int]]:
        """Extract (stack_frames, value) tuples from JFR data.

        Placeholder: real implementation parses JFR chunks.
        """
        _ = data
        return []

    def _build_flame_tree_from_stacks(
        self,
        stacks: list[tuple[list[str], int]],
    ) -> FlameGraphNode:
        """Build a FlameGraphNode tree from folded stack samples."""
        root = FlameGraphNode(name="root", self_value=0, total_value=0)

        for frames, value in stacks:
            node = root
            node.total_value += value
            for frame in frames:
                # Find or create child
                child = next((c for c in node.children if c.name == frame), None)
                if child is None:
                    child = FlameGraphNode(name=frame, self_value=0, total_value=0)
                    node.children.append(child)
                child.total_value += value
                node = child
            # Leaf gets self_value
            node.self_value += value

        return root
