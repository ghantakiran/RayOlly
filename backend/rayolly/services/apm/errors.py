"""Error tracking and classification for APM.

Groups errors by fingerprint, classifies them, and detects regressions.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------

class ClickHouseClient(Protocol):
    async def execute(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]: ...


# ---------------------------------------------------------------------------
# Enums & Data classes
# ---------------------------------------------------------------------------

class ErrorStatus(str, Enum):
    NEW = "new"
    ONGOING = "ongoing"
    REGRESSED = "regressed"
    RESOLVED = "resolved"


class ErrorCategory(str, Enum):
    NETWORK = "network"
    DATABASE = "database"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    VALIDATION = "validation"
    TIMEOUT = "timeout"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    CONFIGURATION = "configuration"
    DEPENDENCY = "dependency"
    APPLICATION = "application"
    UNKNOWN = "unknown"


@dataclass
class ErrorGroup:
    fingerprint: str
    message: str
    count: int
    first_seen: datetime
    last_seen: datetime
    status: ErrorStatus
    affected_users: int
    sample_trace_ids: list[str] = field(default_factory=list)
    stack_trace: str = ""


@dataclass(frozen=True)
class ErrorClassification:
    error_type: str
    category: ErrorCategory
    is_known: bool
    suggested_fix: str


@dataclass
class RegressionInfo:
    fingerprint: str
    message: str
    resolved_at: datetime
    reappeared_at: datetime
    current_count: int


# ---------------------------------------------------------------------------
# Fingerprinting
# ---------------------------------------------------------------------------

# Patterns to normalize before fingerprinting
_NORMALIZATIONS: list[tuple[re.Pattern[str], str]] = [
    # UUIDs
    (re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I), "<UUID>"),
    # Hex IDs (16+ chars)
    (re.compile(r"\b[0-9a-f]{16,}\b", re.I), "<HEX_ID>"),
    # Numeric IDs
    (re.compile(r"\b\d{4,}\b"), "<NUM>"),
    # IP addresses
    (re.compile(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(:\d+)?"), "<IP>"),
    # Timestamps
    (re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[\w.:+-]*"), "<TIMESTAMP>"),
    # File paths with line numbers
    (re.compile(r"line \d+"), "line <N>"),
    # Memory addresses
    (re.compile(r"0x[0-9a-f]+", re.I), "<ADDR>"),
    # Quoted strings (keep first 20 chars)
    (re.compile(r'"[^"]{20,}"'), '"<STRING>"'),
    (re.compile(r"'[^']{20,}'"), "'<STRING>'"),
]


def _normalize(text: str) -> str:
    result = text
    for pattern, replacement in _NORMALIZATIONS:
        result = pattern.sub(replacement, result)
    return result


def _fingerprint(error_message: str, stack_trace: str) -> str:
    """Generate a stable fingerprint by normalizing variable parts."""
    normalized_msg = _normalize(error_message)

    # For stack traces, keep only function names and file names (not line numbers)
    normalized_stack = _normalize(stack_trace)

    combined = f"{normalized_msg}\n{normalized_stack}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Classification rules
# ---------------------------------------------------------------------------

_CLASSIFICATION_RULES: list[tuple[list[str], str, ErrorCategory, str]] = [
    # (keywords, error_type, category, suggested_fix)
    (
        ["connection refused", "ECONNREFUSED", "connect ECONNREFUSED"],
        "ConnectionRefused",
        ErrorCategory.NETWORK,
        "Check that the target service is running and reachable. Verify network policies and firewall rules.",
    ),
    (
        ["connection reset", "ECONNRESET", "broken pipe"],
        "ConnectionReset",
        ErrorCategory.NETWORK,
        "Check for load balancer timeouts, keepalive settings, or upstream service restarts.",
    ),
    (
        ["timeout", "timed out", "deadline exceeded", "context deadline"],
        "Timeout",
        ErrorCategory.TIMEOUT,
        "Increase timeout thresholds or investigate slow downstream dependencies.",
    ),
    (
        ["ENOMEM", "out of memory", "OOM", "memory allocation"],
        "OutOfMemory",
        ErrorCategory.RESOURCE_EXHAUSTION,
        "Increase memory limits, check for memory leaks, or reduce batch sizes.",
    ),
    (
        ["too many open files", "EMFILE", "ENFILE"],
        "FileDescriptorExhaustion",
        ErrorCategory.RESOURCE_EXHAUSTION,
        "Increase file descriptor limits (ulimit -n) or check for fd leaks.",
    ),
    (
        ["deadlock", "lock wait timeout"],
        "DatabaseDeadlock",
        ErrorCategory.DATABASE,
        "Review transaction isolation levels and query ordering to prevent deadlocks.",
    ),
    (
        ["duplicate key", "unique constraint", "unique violation"],
        "DuplicateKey",
        ErrorCategory.DATABASE,
        "Add idempotency checks or use upsert/ON CONFLICT clauses.",
    ),
    (
        ["unauthorized", "401", "authentication failed", "invalid token", "token expired"],
        "AuthenticationFailure",
        ErrorCategory.AUTHENTICATION,
        "Check token expiry, credential rotation, or identity provider availability.",
    ),
    (
        ["forbidden", "403", "permission denied", "access denied"],
        "AuthorizationFailure",
        ErrorCategory.AUTHORIZATION,
        "Review RBAC policies and ensure the caller has the required permissions.",
    ),
    (
        ["validation", "invalid", "bad request", "400", "schema"],
        "ValidationError",
        ErrorCategory.VALIDATION,
        "Check request payload against the API schema and fix the caller.",
    ),
    (
        ["no such host", "dns", "name resolution", "ENOTFOUND"],
        "DNSResolution",
        ErrorCategory.NETWORK,
        "Check DNS configuration and ensure the hostname is resolvable.",
    ),
    (
        ["certificate", "TLS", "SSL", "x509"],
        "TLSError",
        ErrorCategory.CONFIGURATION,
        "Check certificate expiry, CA trust chain, and TLS configuration.",
    ),
    (
        ["rate limit", "429", "too many requests", "throttl"],
        "RateLimited",
        ErrorCategory.DEPENDENCY,
        "Implement backoff/retry logic or request a rate limit increase.",
    ),
]


# ---------------------------------------------------------------------------
# ErrorTracker
# ---------------------------------------------------------------------------

class ErrorTracker:
    """Tracks, groups, classifies, and detects regressions in errors."""

    async def get_error_groups(
        self,
        tenant_id: str,
        service: str,
        time_range: tuple[datetime, datetime],
        clickhouse: ClickHouseClient,
    ) -> list[ErrorGroup]:
        start, end = time_range

        rows = await clickhouse.execute(
            """
            SELECT
                exception_message,
                exception_stacktrace,
                count() AS cnt,
                min(timestamp) AS first_seen,
                max(timestamp) AS last_seen,
                uniqExact(user_id) AS affected_users,
                groupArray(10)(trace_id) AS sample_traces
            FROM traces.spans
            WHERE tenant_id = %(tenant_id)s
              AND service_name = %(service)s
              AND status_code >= 400
              AND timestamp BETWEEN %(start)s AND %(end)s
            GROUP BY exception_message, exception_stacktrace
            ORDER BY cnt DESC
            """,
            {"tenant_id": tenant_id, "service": service, "start": start, "end": end},
        )

        # Check for previously resolved errors to detect regressions
        resolved_fingerprints = await self._get_resolved_fingerprints(tenant_id, service, clickhouse)

        groups: list[ErrorGroup] = []
        for row in rows:
            msg = row["exception_message"]
            stack = row.get("exception_stacktrace", "")
            fp = _fingerprint(msg, stack)
            first_seen: datetime = row["first_seen"]
            last_seen: datetime = row["last_seen"]

            # Determine status
            if fp in resolved_fingerprints:
                status = ErrorStatus.REGRESSED
            elif (last_seen - first_seen).total_seconds() < 3600:
                status = ErrorStatus.NEW
            else:
                status = ErrorStatus.ONGOING

            groups.append(
                ErrorGroup(
                    fingerprint=fp,
                    message=msg,
                    count=int(row["cnt"]),
                    first_seen=first_seen,
                    last_seen=last_seen,
                    status=status,
                    affected_users=int(row["affected_users"]),
                    sample_trace_ids=row.get("sample_traces", []),
                    stack_trace=stack,
                )
            )

        return groups

    async def classify_error(
        self,
        error_message: str,
        stack_trace: str,
    ) -> ErrorClassification:
        """Classify an error based on its message and stack trace."""
        combined = f"{error_message} {stack_trace}".lower()

        for keywords, error_type, category, fix in _CLASSIFICATION_RULES:
            if any(kw.lower() in combined for kw in keywords):
                return ErrorClassification(
                    error_type=error_type,
                    category=category,
                    is_known=True,
                    suggested_fix=fix,
                )

        return ErrorClassification(
            error_type="Unknown",
            category=ErrorCategory.UNKNOWN,
            is_known=False,
            suggested_fix="Examine the stack trace and error message for root cause. Check application logs for additional context.",
        )

    async def detect_regressions(
        self,
        tenant_id: str,
        service: str,
        time_range: tuple[datetime, datetime],
        clickhouse: ClickHouseClient,
    ) -> list[RegressionInfo]:
        """Detect errors that were marked resolved but have reappeared."""
        start, end = time_range

        # Get currently resolved errors
        resolved_rows = await clickhouse.execute(
            """
            SELECT fingerprint, message, resolved_at
            FROM apm.error_resolutions
            WHERE tenant_id = %(tenant_id)s
              AND service_name = %(service)s
              AND resolved_at < %(end)s
            """,
            {"tenant_id": tenant_id, "service": service, "end": end},
        )

        if not resolved_rows:
            return []

        resolved_map: dict[str, dict[str, Any]] = {}
        for r in resolved_rows:
            resolved_map[r["fingerprint"]] = r

        # Get current errors and check if any match resolved fingerprints
        current_groups = await self.get_error_groups(tenant_id, service, time_range, clickhouse)

        regressions: list[RegressionInfo] = []
        for group in current_groups:
            resolved = resolved_map.get(group.fingerprint)
            if resolved and group.first_seen > resolved["resolved_at"]:
                regressions.append(
                    RegressionInfo(
                        fingerprint=group.fingerprint,
                        message=group.message,
                        resolved_at=resolved["resolved_at"],
                        reappeared_at=group.first_seen,
                        current_count=group.count,
                    )
                )

        return regressions

    async def _get_resolved_fingerprints(
        self,
        tenant_id: str,
        service: str,
        clickhouse: ClickHouseClient,
    ) -> set[str]:
        rows = await clickhouse.execute(
            """
            SELECT fingerprint
            FROM apm.error_resolutions
            WHERE tenant_id = %(tenant_id)s
              AND service_name = %(service)s
            """,
            {"tenant_id": tenant_id, "service": service},
        )
        return {r["fingerprint"] for r in rows}
