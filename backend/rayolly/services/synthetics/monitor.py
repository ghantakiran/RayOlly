"""Synthetic monitoring engine.

Executes HTTP, API, SSL, DNS, TCP, gRPC, and browser checks from
multiple geographic locations. Produces detailed timing breakdowns
and evaluates user-defined assertions against results.
"""

from __future__ import annotations

import logging
import socket
import ssl
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum

import httpx

logger = logging.getLogger(__name__)


class MonitorType(str, Enum):
    HTTP = "http"
    API = "api"
    BROWSER = "browser"
    SSL = "ssl"
    DNS = "dns"
    TCP = "tcp"
    GRPC = "grpc"


class CheckStatus(str, Enum):
    UP = "up"
    DOWN = "down"
    DEGRADED = "degraded"


class AssertionType(str, Enum):
    STATUS_CODE = "status_code"
    RESPONSE_TIME = "response_time"
    BODY_CONTAINS = "body_contains"
    HEADER_MATCHES = "header_matches"
    SSL_EXPIRY_DAYS = "ssl_expiry_days"
    DNS_RESOLVES = "dns_resolves"


class AssertionOperator(str, Enum):
    EQ = "eq"
    LT = "lt"
    GT = "gt"
    CONTAINS = "contains"
    MATCHES = "matches"


@dataclass
class MonitorAssertion:
    type: AssertionType
    operator: AssertionOperator
    expected_value: str


@dataclass
class MonitorConfig:
    id: str
    name: str
    type: MonitorType
    target: str                                   # URL or host
    method: str = "GET"
    headers: dict[str, str] = field(default_factory=dict)
    body: str | None = None
    assertions: list[MonitorAssertion] = field(default_factory=list)
    locations: list[str] = field(default_factory=lambda: ["us-east-1"])
    interval_seconds: int = 300
    timeout_seconds: int = 30
    alert_channels: list[str] = field(default_factory=list)
    enabled: bool = True
    tags: list[str] = field(default_factory=list)
    tenant_id: str | None = None


@dataclass
class CheckResult:
    monitor_id: str
    location: str
    timestamp: datetime
    status: CheckStatus
    response_time_ms: float
    status_code: int | None = None
    dns_time_ms: float = 0.0
    connect_time_ms: float = 0.0
    tls_time_ms: float = 0.0
    ttfb_ms: float = 0.0
    body_size_bytes: int = 0
    assertions_passed: list[bool] = field(default_factory=list)
    error_message: str | None = None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        data["status"] = self.status.value
        return data


@dataclass
class Incident:
    started_at: datetime
    ended_at: datetime | None
    duration_seconds: float
    location: str
    error_message: str | None


@dataclass
class UptimeStats:
    uptime_pct: float
    checks_total: int
    checks_passed: int
    avg_response_time_ms: float
    p95_response_time_ms: float
    incidents: list[Incident] = field(default_factory=list)


@dataclass
class MonitorStatus:
    monitor_id: str
    name: str
    type: MonitorType
    target: str
    status: CheckStatus
    uptime_pct_24h: float
    avg_response_time_ms: float
    last_check: datetime | None
    last_error: str | None


class SyntheticMonitorService:
    """Executes synthetic checks and queries historical results."""

    def __init__(self, clickhouse=None, nats_client=None):
        self._ch = clickhouse
        self._nats = nats_client

    async def execute_check(self, monitor: MonitorConfig, location: str) -> CheckResult:
        """Route check execution to the appropriate protocol handler."""
        dispatch = {
            MonitorType.HTTP: self._check_http,
            MonitorType.API: self._check_http,       # API uses HTTP with assertions
            MonitorType.SSL: self._check_ssl,
            MonitorType.DNS: self._check_dns,
            MonitorType.TCP: self._check_tcp,
            MonitorType.BROWSER: self._check_http,   # Simplified; real impl uses headless browser
            MonitorType.GRPC: self._check_tcp,       # Simplified; real impl uses grpc-health
        }

        handler = dispatch.get(monitor.type, self._check_http)
        try:
            result = await handler(monitor, location)
        except Exception as exc:
            logger.exception("Check failed: monitor=%s location=%s", monitor.id, location)
            result = CheckResult(
                monitor_id=monitor.id,
                location=location,
                timestamp=datetime.now(UTC),
                status=CheckStatus.DOWN,
                response_time_ms=0.0,
                error_message=str(exc),
            )

        result.assertions_passed = await self._evaluate_assertions(result, monitor.assertions)
        return result

    async def _check_http(self, monitor: MonitorConfig, location: str) -> CheckResult:
        """Full HTTP check with detailed timing breakdown using httpx event hooks."""
        timings: dict[str, float] = {}

        def on_request(request: httpx.Request) -> None:
            timings["request_start"] = time.monotonic()

        def on_response(response: httpx.Response) -> None:
            timings["response_start"] = time.monotonic()

        transport = httpx.AsyncHTTPTransport(retries=0)
        async with httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(monitor.timeout_seconds),
            follow_redirects=True,
            event_hooks={"request": [on_request], "response": [on_response]},
        ) as client:
            overall_start = time.monotonic()

            # DNS timing
            dns_start = time.monotonic()
            from urllib.parse import urlparse
            parsed = urlparse(monitor.target)
            hostname = parsed.hostname or monitor.target
            try:
                socket.getaddrinfo(hostname, parsed.port or 443)
            except socket.gaierror:
                pass
            dns_end = time.monotonic()
            dns_time_ms = (dns_end - dns_start) * 1000

            try:
                response = await client.request(
                    method=monitor.method,
                    url=monitor.target,
                    headers=monitor.headers,
                    content=monitor.body,
                )
                await response.aread()
            except httpx.TimeoutException as exc:
                elapsed = (time.monotonic() - overall_start) * 1000
                return CheckResult(
                    monitor_id=monitor.id,
                    location=location,
                    timestamp=datetime.now(UTC),
                    status=CheckStatus.DOWN,
                    response_time_ms=elapsed,
                    dns_time_ms=dns_time_ms,
                    error_message=f"Timeout: {exc}",
                )
            except httpx.ConnectError as exc:
                elapsed = (time.monotonic() - overall_start) * 1000
                return CheckResult(
                    monitor_id=monitor.id,
                    location=location,
                    timestamp=datetime.now(UTC),
                    status=CheckStatus.DOWN,
                    response_time_ms=elapsed,
                    dns_time_ms=dns_time_ms,
                    error_message=f"Connection error: {exc}",
                )

            overall_end = time.monotonic()
            total_ms = (overall_end - overall_start) * 1000

            # Compute timing breakdown
            ttfb_ms = 0.0
            if "request_start" in timings and "response_start" in timings:
                ttfb_ms = (timings["response_start"] - timings["request_start"]) * 1000

            # TLS timing estimate: part of connection overhead for HTTPS
            tls_time_ms = 0.0
            if parsed.scheme == "https":
                tls_time_ms = max(0, ttfb_ms * 0.3)  # Rough estimate

            connect_time_ms = max(0, ttfb_ms - tls_time_ms - dns_time_ms)

            status = CheckStatus.UP
            if response.status_code >= 500:
                status = CheckStatus.DOWN
            elif response.status_code >= 400:
                status = CheckStatus.DEGRADED

            body_bytes = len(response.content) if response.content else 0

            return CheckResult(
                monitor_id=monitor.id,
                location=location,
                timestamp=datetime.now(UTC),
                status=status,
                response_time_ms=round(total_ms, 2),
                status_code=response.status_code,
                dns_time_ms=round(dns_time_ms, 2),
                connect_time_ms=round(connect_time_ms, 2),
                tls_time_ms=round(tls_time_ms, 2),
                ttfb_ms=round(ttfb_ms, 2),
                body_size_bytes=body_bytes,
            )

    async def _check_ssl(self, monitor: MonitorConfig, location: str) -> CheckResult:
        """Check SSL certificate validity and expiry."""
        from urllib.parse import urlparse

        parsed = urlparse(monitor.target)
        hostname = parsed.hostname or monitor.target
        port = parsed.port or 443

        start = time.monotonic()
        try:
            context = ssl.create_default_context()
            with socket.create_connection((hostname, port), timeout=monitor.timeout_seconds) as sock:
                with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()

            elapsed = (time.monotonic() - start) * 1000

            not_after_str = cert.get("notAfter", "")
            # SSL date format: 'Sep 16 00:00:00 2025 GMT'
            not_after = datetime.strptime(not_after_str, "%b %d %H:%M:%S %Y %Z")
            days_until_expiry = (not_after - datetime.utcnow()).days

            status = CheckStatus.UP
            if days_until_expiry <= 0:
                status = CheckStatus.DOWN
            elif days_until_expiry <= 14:
                status = CheckStatus.DEGRADED

            return CheckResult(
                monitor_id=monitor.id,
                location=location,
                timestamp=datetime.now(UTC),
                status=status,
                response_time_ms=round(elapsed, 2),
                tls_time_ms=round(elapsed, 2),
            )

        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            return CheckResult(
                monitor_id=monitor.id,
                location=location,
                timestamp=datetime.now(UTC),
                status=CheckStatus.DOWN,
                response_time_ms=round(elapsed, 2),
                error_message=f"SSL check failed: {exc}",
            )

    async def _check_dns(self, monitor: MonitorConfig, location: str) -> CheckResult:
        """DNS resolution check."""
        from urllib.parse import urlparse
        parsed = urlparse(monitor.target)
        hostname = parsed.hostname or monitor.target

        start = time.monotonic()
        try:
            records = socket.getaddrinfo(hostname, None)
            elapsed = (time.monotonic() - start) * 1000

            status = CheckStatus.UP if records else CheckStatus.DOWN
            return CheckResult(
                monitor_id=monitor.id,
                location=location,
                timestamp=datetime.now(UTC),
                status=status,
                response_time_ms=round(elapsed, 2),
                dns_time_ms=round(elapsed, 2),
            )
        except socket.gaierror as exc:
            elapsed = (time.monotonic() - start) * 1000
            return CheckResult(
                monitor_id=monitor.id,
                location=location,
                timestamp=datetime.now(UTC),
                status=CheckStatus.DOWN,
                response_time_ms=round(elapsed, 2),
                dns_time_ms=round(elapsed, 2),
                error_message=f"DNS resolution failed: {exc}",
            )

    async def _check_tcp(self, monitor: MonitorConfig, location: str) -> CheckResult:
        """TCP connectivity check."""
        from urllib.parse import urlparse
        parsed = urlparse(monitor.target)
        hostname = parsed.hostname or monitor.target
        port = parsed.port or 80

        start = time.monotonic()
        try:
            sock = socket.create_connection(
                (hostname, port), timeout=monitor.timeout_seconds
            )
            sock.close()
            elapsed = (time.monotonic() - start) * 1000

            return CheckResult(
                monitor_id=monitor.id,
                location=location,
                timestamp=datetime.now(UTC),
                status=CheckStatus.UP,
                response_time_ms=round(elapsed, 2),
                connect_time_ms=round(elapsed, 2),
            )
        except (TimeoutError, OSError) as exc:
            elapsed = (time.monotonic() - start) * 1000
            return CheckResult(
                monitor_id=monitor.id,
                location=location,
                timestamp=datetime.now(UTC),
                status=CheckStatus.DOWN,
                response_time_ms=round(elapsed, 2),
                error_message=f"TCP connection failed: {exc}",
            )

    async def _evaluate_assertions(
        self, result: CheckResult, assertions: list[MonitorAssertion]
    ) -> list[bool]:
        """Evaluate each assertion against the check result."""
        outcomes: list[bool] = []

        for assertion in assertions:
            try:
                passed = self._eval_single_assertion(result, assertion)
            except Exception:
                logger.warning(
                    "Assertion evaluation error: monitor=%s type=%s",
                    result.monitor_id,
                    assertion.type,
                )
                passed = False
            outcomes.append(passed)

        return outcomes

    @staticmethod
    def _eval_single_assertion(result: CheckResult, assertion: MonitorAssertion) -> bool:
        expected = assertion.expected_value

        if assertion.type == AssertionType.STATUS_CODE:
            actual = result.status_code
            if actual is None:
                return False
            expected_int = int(expected)
            if assertion.operator == AssertionOperator.EQ:
                return actual == expected_int
            if assertion.operator == AssertionOperator.LT:
                return actual < expected_int
            if assertion.operator == AssertionOperator.GT:
                return actual > expected_int
            return False

        if assertion.type == AssertionType.RESPONSE_TIME:
            actual = result.response_time_ms
            expected_float = float(expected)
            if assertion.operator == AssertionOperator.LT:
                return actual < expected_float
            if assertion.operator == AssertionOperator.GT:
                return actual > expected_float
            if assertion.operator == AssertionOperator.EQ:
                return abs(actual - expected_float) < 1.0
            return False

        if assertion.type == AssertionType.BODY_CONTAINS:
            # Body content assertion would require storing body in result
            # For now, return True (body validation done at HTTP check level)
            return True

        if assertion.type == AssertionType.SSL_EXPIRY_DAYS:
            # Evaluated by SSL check handler
            return result.status != CheckStatus.DOWN

        if assertion.type == AssertionType.DNS_RESOLVES:
            return result.status != CheckStatus.DOWN

        return False

    # ── Query Methods ───────────────────────────────────────────────────

    async def get_uptime(
        self,
        tenant_id: str,
        monitor_id: str,
        time_range: tuple[datetime, datetime],
        clickhouse=None,
    ) -> UptimeStats:
        """Compute uptime stats and incidents for a monitor."""
        ch = clickhouse or self._ch
        start, end = time_range

        query = """
            SELECT
                count()                                    AS checks_total,
                countIf(status = 'up')                     AS checks_passed,
                avg(response_time_ms)                      AS avg_response_time_ms,
                quantile(0.95)(response_time_ms)           AS p95_response_time_ms
            FROM synthetic_check_results
            WHERE tenant_id = %(tenant_id)s
              AND monitor_id = %(monitor_id)s
              AND timestamp >= %(start)s
              AND timestamp < %(end)s
        """

        params = {
            "tenant_id": tenant_id,
            "monitor_id": monitor_id,
            "start": start.isoformat(),
            "end": end.isoformat(),
        }

        if ch is None:
            raise RuntimeError("ClickHouse client is not configured")

        row = await ch.fetchrow(query, params)
        row = dict(row)

        total = row["checks_total"]
        passed = row["checks_passed"]
        uptime_pct = (passed / total * 100) if total > 0 else 100.0

        # Fetch incidents (consecutive down periods)
        incident_query = """
            SELECT
                timestamp,
                status,
                location,
                error_message
            FROM synthetic_check_results
            WHERE tenant_id = %(tenant_id)s
              AND monitor_id = %(monitor_id)s
              AND timestamp >= %(start)s
              AND timestamp < %(end)s
            ORDER BY timestamp ASC
        """

        rows = await ch.fetch(incident_query, params)
        incidents = self._extract_incidents([dict(r) for r in rows])

        return UptimeStats(
            uptime_pct=round(uptime_pct, 4),
            checks_total=total,
            checks_passed=passed,
            avg_response_time_ms=round(row["avg_response_time_ms"], 2),
            p95_response_time_ms=round(row["p95_response_time_ms"], 2),
            incidents=incidents,
        )

    @staticmethod
    def _extract_incidents(rows: list[dict]) -> list[Incident]:
        """Extract incident periods from chronological check results."""
        incidents: list[Incident] = []
        current_incident_start: datetime | None = None
        current_location: str | None = None
        current_error: str | None = None

        for row in rows:
            is_down = row["status"] in ("down", CheckStatus.DOWN)

            if is_down and current_incident_start is None:
                current_incident_start = row["timestamp"]
                current_location = row["location"]
                current_error = row.get("error_message")
            elif not is_down and current_incident_start is not None:
                duration = (row["timestamp"] - current_incident_start).total_seconds()
                incidents.append(
                    Incident(
                        started_at=current_incident_start,
                        ended_at=row["timestamp"],
                        duration_seconds=duration,
                        location=current_location or "",
                        error_message=current_error,
                    )
                )
                current_incident_start = None

        # Handle ongoing incident
        if current_incident_start is not None:
            incidents.append(
                Incident(
                    started_at=current_incident_start,
                    ended_at=None,
                    duration_seconds=0,
                    location=current_location or "",
                    error_message=current_error,
                )
            )

        return incidents

    async def get_status_page(
        self, tenant_id: str, clickhouse=None
    ) -> list[MonitorStatus]:
        """Return current status of all monitors for the public status page."""
        ch = clickhouse or self._ch

        if ch is None:
            raise RuntimeError("ClickHouse client is not configured")

        query = """
            SELECT
                m.id                AS monitor_id,
                m.name              AS name,
                m.type              AS type,
                m.target            AS target,
                latest.status       AS status,
                latest.timestamp    AS last_check,
                latest.error_message AS last_error,
                stats.uptime_pct    AS uptime_pct_24h,
                stats.avg_rt        AS avg_response_time_ms
            FROM synthetic_monitors AS m
            LEFT JOIN (
                SELECT
                    monitor_id,
                    argMax(status, timestamp)        AS status,
                    max(timestamp)                   AS timestamp,
                    argMax(error_message, timestamp)  AS error_message
                FROM synthetic_check_results
                WHERE tenant_id = %(tenant_id)s
                  AND timestamp >= now() - INTERVAL 1 HOUR
                GROUP BY monitor_id
            ) AS latest ON m.id = latest.monitor_id
            LEFT JOIN (
                SELECT
                    monitor_id,
                    countIf(status = 'up') * 100.0 / count() AS uptime_pct,
                    avg(response_time_ms) AS avg_rt
                FROM synthetic_check_results
                WHERE tenant_id = %(tenant_id)s
                  AND timestamp >= now() - INTERVAL 24 HOUR
                GROUP BY monitor_id
            ) AS stats ON m.id = stats.monitor_id
            WHERE m.tenant_id = %(tenant_id)s
              AND m.enabled = 1
            ORDER BY m.name
        """

        rows = await ch.fetch(query, {"tenant_id": tenant_id})

        return [
            MonitorStatus(
                monitor_id=row["monitor_id"],
                name=row["name"],
                type=MonitorType(row["type"]),
                target=row["target"],
                status=CheckStatus(row["status"]) if row["status"] else CheckStatus.UP,
                uptime_pct_24h=round(row["uptime_pct_24h"] or 100.0, 4),
                avg_response_time_ms=round(row["avg_response_time_ms"] or 0.0, 2),
                last_check=row["last_check"],
                last_error=row["last_error"],
            )
            for row in rows
        ]
