"""RUM analytics engine.

Queries ClickHouse for aggregated Real User Monitoring metrics including
Core Web Vitals, page performance, session analysis, error summaries,
and geographic/device breakdowns.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


# ── Google Core Web Vitals Thresholds ───────────────────────────────────

class VitalRating(str, Enum):
    GOOD = "good"
    NEEDS_IMPROVEMENT = "needs_improvement"
    POOR = "poor"


# Thresholds: (good_upper, needs_improvement_upper)
WEB_VITAL_THRESHOLDS = {
    "lcp_ms": (2500, 4000),       # Largest Contentful Paint
    "fid_ms": (100, 300),         # First Input Delay
    "cls": (0.1, 0.25),           # Cumulative Layout Shift
    "fcp_ms": (1800, 3000),       # First Contentful Paint
    "tti_ms": (3800, 7300),       # Time to Interactive
}


def rate_vital(metric: str, value: float) -> VitalRating:
    thresholds = WEB_VITAL_THRESHOLDS.get(metric)
    if thresholds is None:
        return VitalRating.GOOD
    if value <= thresholds[0]:
        return VitalRating.GOOD
    if value <= thresholds[1]:
        return VitalRating.NEEDS_IMPROVEMENT
    return VitalRating.POOR


# ── Result Dataclasses ──────────────────────────────────────────────────

@dataclass
class WebVitals:
    lcp_p75: float
    lcp_rating: VitalRating
    fid_p75: float
    fid_rating: VitalRating
    cls_p75: float
    cls_rating: VitalRating
    fcp_p75: float
    fcp_rating: VitalRating
    tti_p75: float
    tti_rating: VitalRating
    sample_count: int = 0


@dataclass
class PagePerformance:
    url: str
    views: int
    avg_load_time_ms: float
    bounce_rate: float
    error_rate: float
    web_vitals: WebVitals | None = None


@dataclass
class SessionAction:
    action_type: str
    target_element: str
    timestamp: datetime
    duration_ms: float
    error: str | None = None


@dataclass
class SessionDetail:
    session_id: str
    user_id: str | None
    start_time: datetime
    end_time: datetime
    page_count: int
    action_count: int
    error_count: int
    duration_ms: float
    device_type: str
    browser: str
    os: str
    country: str | None
    actions: list[SessionAction] = field(default_factory=list)
    pages: list[str] = field(default_factory=list)


@dataclass
class ErrorGroup:
    fingerprint: str
    message: str
    filename: str
    line: int
    count: int
    affected_sessions: int
    first_seen: datetime
    last_seen: datetime
    sample_stack_trace: str


@dataclass
class GeoPerformance:
    country: str
    city: str | None
    page_views: int
    avg_load_time_ms: float
    lcp_p75: float
    fid_p75: float
    cls_p75: float
    error_rate: float


@dataclass
class DevicePerformance:
    dimension: str          # browser name, OS name, or device type
    dimension_type: str     # "browser", "os", "device_type"
    page_views: int
    avg_load_time_ms: float
    lcp_p75: float
    fid_p75: float
    cls_p75: float
    error_rate: float


class RUMAnalytics:
    """Provides analytical queries over RUM data stored in ClickHouse."""

    def __init__(self, clickhouse=None):
        self._ch = clickhouse

    async def get_web_vitals(
        self,
        tenant_id: str,
        time_range: tuple[datetime, datetime],
        page_url: str | None = None,
        clickhouse=None,
    ) -> WebVitals:
        """Return p75 Core Web Vitals with pass/fail ratings against Google thresholds."""
        ch = clickhouse or self._ch
        start, end = time_range

        url_filter = ""
        params = {
            "tenant_id": tenant_id,
            "start": start.isoformat(),
            "end": end.isoformat(),
        }
        if page_url:
            url_filter = "AND page_url = %(page_url)s"
            params["page_url"] = page_url

        query = f"""
            SELECT
                quantile(0.75)(largest_contentful_paint_ms) AS lcp_p75,
                quantile(0.75)(first_input_delay_ms)        AS fid_p75,
                quantile(0.75)(cumulative_layout_shift)     AS cls_p75,
                quantile(0.75)(first_contentful_paint_ms)   AS fcp_p75,
                quantile(0.75)(time_to_interactive_ms)      AS tti_p75,
                count()                                     AS sample_count
            FROM rum_page_views
            WHERE tenant_id = %(tenant_id)s
              AND timestamp >= %(start)s
              AND timestamp < %(end)s
              {url_filter}
        """

        row = await self._query_one(ch, query, params)

        lcp = row["lcp_p75"]
        fid = row["fid_p75"]
        cls_ = row["cls_p75"]
        fcp = row["fcp_p75"]
        tti = row["tti_p75"]

        return WebVitals(
            lcp_p75=lcp,
            lcp_rating=rate_vital("lcp_ms", lcp),
            fid_p75=fid,
            fid_rating=rate_vital("fid_ms", fid),
            cls_p75=cls_,
            cls_rating=rate_vital("cls", cls_),
            fcp_p75=fcp,
            fcp_rating=rate_vital("fcp_ms", fcp),
            tti_p75=tti,
            tti_rating=rate_vital("tti_ms", tti),
            sample_count=row["sample_count"],
        )

    async def get_page_performance(
        self,
        tenant_id: str,
        time_range: tuple[datetime, datetime],
        clickhouse=None,
    ) -> list[PagePerformance]:
        """Return performance metrics grouped by page URL."""
        ch = clickhouse or self._ch
        start, end = time_range

        query = """
            SELECT
                page_url,
                count()                                     AS views,
                avg(load_time_ms)                           AS avg_load_time_ms,
                countIf(action_count = 1) / count()         AS bounce_rate,
                sumIf(1, has_error = 1) / count()           AS error_rate,
                quantile(0.75)(largest_contentful_paint_ms) AS lcp_p75,
                quantile(0.75)(first_input_delay_ms)        AS fid_p75,
                quantile(0.75)(cumulative_layout_shift)     AS cls_p75,
                quantile(0.75)(first_contentful_paint_ms)   AS fcp_p75,
                quantile(0.75)(time_to_interactive_ms)      AS tti_p75
            FROM rum_page_views
            WHERE tenant_id = %(tenant_id)s
              AND timestamp >= %(start)s
              AND timestamp < %(end)s
            GROUP BY page_url
            ORDER BY views DESC
            LIMIT 100
        """

        params = {
            "tenant_id": tenant_id,
            "start": start.isoformat(),
            "end": end.isoformat(),
        }

        rows = await self._query_all(ch, query, params)

        results = []
        for row in rows:
            vitals = WebVitals(
                lcp_p75=row["lcp_p75"],
                lcp_rating=rate_vital("lcp_ms", row["lcp_p75"]),
                fid_p75=row["fid_p75"],
                fid_rating=rate_vital("fid_ms", row["fid_p75"]),
                cls_p75=row["cls_p75"],
                cls_rating=rate_vital("cls", row["cls_p75"]),
                fcp_p75=row["fcp_p75"],
                fcp_rating=rate_vital("fcp_ms", row["fcp_p75"]),
                tti_p75=row["tti_p75"],
                tti_rating=rate_vital("tti_ms", row["tti_p75"]),
            )
            results.append(
                PagePerformance(
                    url=row["page_url"],
                    views=row["views"],
                    avg_load_time_ms=row["avg_load_time_ms"],
                    bounce_rate=row["bounce_rate"],
                    error_rate=row["error_rate"],
                    web_vitals=vitals,
                )
            )
        return results

    async def get_user_sessions(
        self,
        tenant_id: str,
        time_range: tuple[datetime, datetime],
        user_id: str | None = None,
        clickhouse=None,
    ) -> list[SessionDetail]:
        """Return user sessions with actions and errors."""
        ch = clickhouse or self._ch
        start, end = time_range

        user_filter = ""
        params = {
            "tenant_id": tenant_id,
            "start": start.isoformat(),
            "end": end.isoformat(),
        }
        if user_id:
            user_filter = "AND user_id = %(user_id)s"
            params["user_id"] = user_id

        query = f"""
            SELECT
                session_id,
                any(user_id)       AS user_id,
                min(timestamp)     AS start_time,
                max(timestamp)     AS end_time,
                uniqExact(page_url) AS page_count,
                count()            AS action_count,
                sumIf(1, error IS NOT NULL) AS error_count,
                dateDiff('millisecond', min(timestamp), max(timestamp)) AS duration_ms,
                any(device_type)   AS device_type,
                any(browser)       AS browser,
                any(os)            AS os,
                any(country)       AS country,
                groupArray(page_url) AS pages
            FROM rum_page_views
            WHERE tenant_id = %(tenant_id)s
              AND timestamp >= %(start)s
              AND timestamp < %(end)s
              {user_filter}
            GROUP BY session_id
            ORDER BY start_time DESC
            LIMIT 50
        """

        rows = await self._query_all(ch, query, params)

        sessions = []
        for row in rows:
            sessions.append(
                SessionDetail(
                    session_id=row["session_id"],
                    user_id=row["user_id"],
                    start_time=row["start_time"],
                    end_time=row["end_time"],
                    page_count=row["page_count"],
                    action_count=row["action_count"],
                    error_count=row["error_count"],
                    duration_ms=row["duration_ms"],
                    device_type=row["device_type"],
                    browser=row["browser"],
                    os=row["os"],
                    country=row["country"],
                    pages=row.get("pages", []),
                )
            )
        return sessions

    async def get_error_summary(
        self,
        tenant_id: str,
        time_range: tuple[datetime, datetime],
        clickhouse=None,
    ) -> list[ErrorGroup]:
        """Return JS errors grouped by fingerprint with counts."""
        ch = clickhouse or self._ch
        start, end = time_range

        query = """
            SELECT
                cityHash64(concat(message, filename, toString(line))) AS fingerprint,
                any(message)        AS message,
                any(filename)       AS filename,
                any(line)           AS line,
                count()             AS count,
                uniqExact(session_id) AS affected_sessions,
                min(timestamp)      AS first_seen,
                max(timestamp)      AS last_seen,
                any(stack_trace)    AS sample_stack_trace
            FROM rum_js_errors
            WHERE tenant_id = %(tenant_id)s
              AND timestamp >= %(start)s
              AND timestamp < %(end)s
            GROUP BY fingerprint
            ORDER BY count DESC
            LIMIT 100
        """

        params = {
            "tenant_id": tenant_id,
            "start": start.isoformat(),
            "end": end.isoformat(),
        }

        rows = await self._query_all(ch, query, params)

        return [
            ErrorGroup(
                fingerprint=str(row["fingerprint"]),
                message=row["message"],
                filename=row["filename"],
                line=row["line"],
                count=row["count"],
                affected_sessions=row["affected_sessions"],
                first_seen=row["first_seen"],
                last_seen=row["last_seen"],
                sample_stack_trace=row["sample_stack_trace"],
            )
            for row in rows
        ]

    async def get_geography_breakdown(
        self,
        tenant_id: str,
        time_range: tuple[datetime, datetime],
        clickhouse=None,
    ) -> list[GeoPerformance]:
        """Return performance metrics broken down by country and city."""
        ch = clickhouse or self._ch
        start, end = time_range

        query = """
            SELECT
                country,
                city,
                count()                                     AS page_views,
                avg(load_time_ms)                           AS avg_load_time_ms,
                quantile(0.75)(largest_contentful_paint_ms) AS lcp_p75,
                quantile(0.75)(first_input_delay_ms)        AS fid_p75,
                quantile(0.75)(cumulative_layout_shift)     AS cls_p75,
                sumIf(1, has_error = 1) / count()           AS error_rate
            FROM rum_page_views
            WHERE tenant_id = %(tenant_id)s
              AND timestamp >= %(start)s
              AND timestamp < %(end)s
              AND country IS NOT NULL
            GROUP BY country, city
            ORDER BY page_views DESC
            LIMIT 200
        """

        params = {
            "tenant_id": tenant_id,
            "start": start.isoformat(),
            "end": end.isoformat(),
        }

        rows = await self._query_all(ch, query, params)

        return [
            GeoPerformance(
                country=row["country"],
                city=row.get("city"),
                page_views=row["page_views"],
                avg_load_time_ms=row["avg_load_time_ms"],
                lcp_p75=row["lcp_p75"],
                fid_p75=row["fid_p75"],
                cls_p75=row["cls_p75"],
                error_rate=row["error_rate"],
            )
            for row in rows
        ]

    async def get_device_breakdown(
        self,
        tenant_id: str,
        time_range: tuple[datetime, datetime],
        clickhouse=None,
    ) -> list[DevicePerformance]:
        """Return performance metrics broken down by browser, OS, and device type."""
        ch = clickhouse or self._ch
        start, end = time_range
        params = {
            "tenant_id": tenant_id,
            "start": start.isoformat(),
            "end": end.isoformat(),
        }

        results: list[DevicePerformance] = []

        for dimension_col, dimension_type in [
            ("browser", "browser"),
            ("os", "os"),
            ("device_type", "device_type"),
        ]:
            query = f"""
                SELECT
                    {dimension_col}                                 AS dimension,
                    count()                                         AS page_views,
                    avg(load_time_ms)                               AS avg_load_time_ms,
                    quantile(0.75)(largest_contentful_paint_ms)     AS lcp_p75,
                    quantile(0.75)(first_input_delay_ms)            AS fid_p75,
                    quantile(0.75)(cumulative_layout_shift)         AS cls_p75,
                    sumIf(1, has_error = 1) / count()               AS error_rate
                FROM rum_page_views
                WHERE tenant_id = %(tenant_id)s
                  AND timestamp >= %(start)s
                  AND timestamp < %(end)s
                GROUP BY {dimension_col}
                ORDER BY page_views DESC
                LIMIT 20
            """
            rows = await self._query_all(ch, query, params)
            for row in rows:
                results.append(
                    DevicePerformance(
                        dimension=row["dimension"],
                        dimension_type=dimension_type,
                        page_views=row["page_views"],
                        avg_load_time_ms=row["avg_load_time_ms"],
                        lcp_p75=row["lcp_p75"],
                        fid_p75=row["fid_p75"],
                        cls_p75=row["cls_p75"],
                        error_rate=row["error_rate"],
                    )
                )
        return results

    # ── Query Helpers ───────────────────────────────────────────────────

    @staticmethod
    async def _query_one(ch, query: str, params: dict) -> dict:
        if ch is None:
            raise RuntimeError("ClickHouse client is not configured")
        result = await ch.fetchrow(query, params)
        if result is None:
            raise ValueError("Query returned no results")
        return dict(result)

    @staticmethod
    async def _query_all(ch, query: str, params: dict) -> list[dict]:
        if ch is None:
            raise RuntimeError("ClickHouse client is not configured")
        rows = await ch.fetch(query, params)
        return [dict(row) for row in rows]
