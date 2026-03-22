"""RUM (Real User Monitoring) data collection and processing.

Collects page views, user actions, resource timings, JS errors,
and session replay events from browser agents. Data is validated,
enriched with GeoIP, and published to NATS for downstream processing.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class DeviceType(str, Enum):
    DESKTOP = "desktop"
    MOBILE = "mobile"
    TABLET = "tablet"


class ConnectionType(str, Enum):
    WIFI = "wifi"
    FOUR_G = "4g"
    THREE_G = "3g"
    TWO_G = "2g"
    SLOW_2G = "slow-2g"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


class ActionType(str, Enum):
    CLICK = "click"
    SCROLL = "scroll"
    INPUT = "input"
    NAVIGATION = "navigation"
    CUSTOM = "custom"


class ResourceType(str, Enum):
    SCRIPT = "script"
    STYLESHEET = "stylesheet"
    IMAGE = "image"
    FONT = "font"
    XHR = "xhr"
    FETCH = "fetch"
    DOCUMENT = "document"
    OTHER = "other"


class ReplayEventType(str, Enum):
    DOM_MUTATION = "dom_mutation"
    MOUSE_MOVE = "mouse_move"
    SCROLL = "scroll"
    INPUT = "input"
    RESIZE = "resize"


@dataclass
class PageView:
    session_id: str
    user_id: str | None
    page_url: str
    referrer: str | None
    timestamp: datetime
    load_time_ms: float
    dom_ready_ms: float
    first_contentful_paint_ms: float
    largest_contentful_paint_ms: float
    first_input_delay_ms: float
    cumulative_layout_shift: float
    time_to_interactive_ms: float
    browser: str
    os: str
    device_type: DeviceType
    country: str | None = None
    city: str | None = None
    connection_type: ConnectionType = ConnectionType.UNKNOWN
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class UserAction:
    session_id: str
    action_type: ActionType
    target_element: str
    timestamp: datetime
    duration_ms: float
    error: str | None = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class ResourceTiming:
    session_id: str
    page_url: str
    resource_url: str
    resource_type: ResourceType
    duration_ms: float
    transfer_size_bytes: int
    timestamp: datetime
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class JSError:
    session_id: str
    page_url: str
    message: str
    stack_trace: str
    filename: str
    line: int
    column: int
    timestamp: datetime
    user_agent: str
    user_id: str | None = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class SessionReplayEvent:
    session_id: str
    event_type: ReplayEventType
    timestamp: datetime
    data: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


class RUMCollector:
    """Collects, validates, enriches, and publishes RUM data.

    Integrates with:
    - GeoIP for location enrichment
    - NATS for event streaming
    - S3 for session replay storage
    """

    NATS_SUBJECT_PAGE_VIEW = "rum.page_view"
    NATS_SUBJECT_ACTION = "rum.action"
    NATS_SUBJECT_RESOURCE = "rum.resource"
    NATS_SUBJECT_ERROR = "rum.error"

    def __init__(self, nats_client=None, s3_client=None, geoip_reader=None):
        self._nats = nats_client
        self._s3 = s3_client
        self._geoip = geoip_reader

    async def process_page_view(self, tenant_id: str, page_view: PageView) -> PageView:
        """Validate, enrich with GeoIP, and publish page view to NATS."""
        self._validate_page_view(page_view)
        page_view = await self._enrich_geoip(page_view)

        payload = self._serialize_event(tenant_id, "page_view", asdict(page_view))
        await self._publish(self.NATS_SUBJECT_PAGE_VIEW, tenant_id, payload)

        logger.debug(
            "Processed page view: session=%s url=%s lcp=%.0fms",
            page_view.session_id,
            page_view.page_url,
            page_view.largest_contentful_paint_ms,
        )
        return page_view

    async def process_action(self, tenant_id: str, action: UserAction) -> UserAction:
        """Validate and publish user action to NATS."""
        self._validate_action(action)

        payload = self._serialize_event(tenant_id, "action", asdict(action))
        await self._publish(self.NATS_SUBJECT_ACTION, tenant_id, payload)

        logger.debug(
            "Processed action: session=%s type=%s target=%s",
            action.session_id,
            action.action_type,
            action.target_element,
        )
        return action

    async def process_resource(self, tenant_id: str, resource: ResourceTiming) -> ResourceTiming:
        """Validate and publish resource timing to NATS."""
        self._validate_resource(resource)

        payload = self._serialize_event(tenant_id, "resource", asdict(resource))
        await self._publish(self.NATS_SUBJECT_RESOURCE, tenant_id, payload)

        logger.debug(
            "Processed resource: session=%s url=%s type=%s duration=%.0fms",
            resource.session_id,
            resource.resource_url,
            resource.resource_type,
            resource.duration_ms,
        )
        return resource

    async def process_js_error(self, tenant_id: str, error: JSError) -> JSError:
        """Validate and publish JS error to NATS."""
        self._validate_js_error(error)

        payload = self._serialize_event(tenant_id, "js_error", asdict(error))
        await self._publish(self.NATS_SUBJECT_ERROR, tenant_id, payload)

        logger.debug(
            "Processed JS error: session=%s message=%s file=%s:%d",
            error.session_id,
            error.message[:80],
            error.filename,
            error.line,
        )
        return error

    async def process_session_replay(
        self, tenant_id: str, events: list[SessionReplayEvent]
    ) -> str:
        """Store session replay events in S3, returning the object key.

        Events are batched and stored as newline-delimited JSON in S3,
        organized by tenant, session, and timestamp for efficient retrieval.
        """
        if not events:
            raise ValueError("Session replay events list must not be empty")

        session_id = events[0].session_id
        min_ts = min(e.timestamp for e in events)
        date_prefix = min_ts.strftime("%Y/%m/%d")

        s3_key = (
            f"session-replay/{tenant_id}/{date_prefix}/{session_id}/"
            f"{min_ts.isoformat()}-{len(events)}.ndjson"
        )

        ndjson_lines = []
        for event in events:
            record = asdict(event)
            record["timestamp"] = event.timestamp.isoformat()
            ndjson_lines.append(json.dumps(record, default=str))

        body = "\n".join(ndjson_lines)

        if self._s3 is not None:
            await self._s3.put_object(
                Bucket="rayolly-session-replay",
                Key=s3_key,
                Body=body.encode("utf-8"),
                ContentType="application/x-ndjson",
                Metadata={
                    "tenant_id": tenant_id,
                    "session_id": session_id,
                    "event_count": str(len(events)),
                },
            )

        logger.info(
            "Stored %d session replay events: tenant=%s session=%s key=%s",
            len(events),
            tenant_id,
            session_id,
            s3_key,
        )
        return s3_key

    # ── Validation ──────────────────────────────────────────────────────

    @staticmethod
    def _validate_page_view(pv: PageView) -> None:
        if not pv.session_id:
            raise ValueError("session_id is required")
        if not pv.page_url:
            raise ValueError("page_url is required")
        if pv.load_time_ms < 0:
            raise ValueError("load_time_ms must be non-negative")
        if pv.largest_contentful_paint_ms < 0:
            raise ValueError("largest_contentful_paint_ms must be non-negative")
        if pv.cumulative_layout_shift < 0:
            raise ValueError("cumulative_layout_shift must be non-negative")

    @staticmethod
    def _validate_action(action: UserAction) -> None:
        if not action.session_id:
            raise ValueError("session_id is required")
        if not action.target_element:
            raise ValueError("target_element is required")
        if action.duration_ms < 0:
            raise ValueError("duration_ms must be non-negative")

    @staticmethod
    def _validate_resource(resource: ResourceTiming) -> None:
        if not resource.session_id:
            raise ValueError("session_id is required")
        if not resource.resource_url:
            raise ValueError("resource_url is required")
        if resource.duration_ms < 0:
            raise ValueError("duration_ms must be non-negative")
        if resource.transfer_size_bytes < 0:
            raise ValueError("transfer_size_bytes must be non-negative")

    @staticmethod
    def _validate_js_error(error: JSError) -> None:
        if not error.session_id:
            raise ValueError("session_id is required")
        if not error.message:
            raise ValueError("error message is required")

    # ── Enrichment ──────────────────────────────────────────────────────

    async def _enrich_geoip(self, page_view: PageView) -> PageView:
        """Enrich page view with GeoIP data if reader is available."""
        if self._geoip is None:
            return page_view
        try:
            # GeoIP lookup is synchronous in maxminddb; wrap if needed
            ip = getattr(page_view, "_client_ip", None)
            if ip:
                geo = self._geoip.get(ip)
                if geo:
                    page_view.country = geo.get("country", {}).get("iso_code")
                    page_view.city = (
                        geo.get("city", {}).get("names", {}).get("en")
                    )
        except Exception:
            logger.warning("GeoIP enrichment failed for session %s", page_view.session_id)
        return page_view

    # ── Publishing ──────────────────────────────────────────────────────

    @staticmethod
    def _serialize_event(tenant_id: str, event_type: str, data: dict) -> bytes:
        envelope = {
            "tenant_id": tenant_id,
            "event_type": event_type,
            "data": data,
        }
        return json.dumps(envelope, default=str).encode("utf-8")

    async def _publish(self, subject: str, tenant_id: str, payload: bytes) -> None:
        full_subject = f"{subject}.{tenant_id}"
        if self._nats is not None:
            await self._nats.publish(full_subject, payload)
        else:
            logger.warning("NATS client not configured; dropping message on %s", full_subject)
