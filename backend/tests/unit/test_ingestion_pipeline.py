"""Tests for rayolly.services.ingestion.pipeline — IngestionPipeline."""

from __future__ import annotations

import sys
import time
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import pytest

# Ensure the nats package is importable even when not installed.
# The router module imports nats at the top level; we stub it so the test
# can import the pipeline module without needing the real nats library.
if "nats" not in sys.modules:
    _nats_stub = ModuleType("nats")
    _nats_js_stub = ModuleType("nats.js")
    _nats_aio_stub = ModuleType("nats.aio")
    _nats_aio_client_stub = ModuleType("nats.aio.client")
    _nats_aio_client_stub.Client = MagicMock  # type: ignore[attr-defined]
    _nats_js_stub.JetStreamContext = MagicMock  # type: ignore[attr-defined]
    sys.modules["nats"] = _nats_stub
    sys.modules["nats.js"] = _nats_js_stub
    sys.modules["nats.aio"] = _nats_aio_stub
    sys.modules["nats.aio.client"] = _nats_aio_client_stub

from rayolly.services.ingestion.enrichment import Enricher
from rayolly.services.ingestion.models import LogRecord, MetricDataPoint, Span
from rayolly.services.ingestion.pii import PIIDetector
from rayolly.services.ingestion.pipeline import IngestionPipeline
from rayolly.services.ingestion.router import MessageRouter


def _now_ns() -> int:
    return int(time.time() * 1_000_000_000)


@pytest.fixture
def mock_router() -> AsyncMock:
    router = AsyncMock(spec=MessageRouter)
    router.route_logs = AsyncMock(return_value=1)
    router.route_metrics = AsyncMock(return_value=1)
    router.route_traces = AsyncMock(return_value=1)
    router.route_dlq = AsyncMock(return_value=0)
    return router


@pytest.fixture
def mock_enricher() -> AsyncMock:
    enricher = AsyncMock(spec=Enricher)
    enricher.enrich = AsyncMock()
    return enricher


@pytest.fixture
def pipeline(mock_router: AsyncMock, mock_enricher: AsyncMock) -> IngestionPipeline:
    return IngestionPipeline(
        router=mock_router,
        enricher=mock_enricher,
        pii_detector=PIIDetector(),
    )


def _valid_log(body: str = "Normal log message") -> LogRecord:
    return LogRecord(timestamp=_now_ns(), body=body)


def _valid_metric() -> MetricDataPoint:
    return MetricDataPoint(name="cpu", value=0.5, timestamp=_now_ns())


def _valid_span() -> Span:
    ts = _now_ns()
    return Span(
        trace_id="abcdef1234567890abcdef1234567890",
        span_id="1234567890abcdef",
        name="GET /api",
        start_time=ts,
        end_time=ts + 50_000_000,
    )


# -----------------------------------------------------------------------
# Logs
# -----------------------------------------------------------------------

class TestProcessLogs:
    @pytest.mark.asyncio
    async def test_process_logs_success(
        self, pipeline: IngestionPipeline, mock_router: AsyncMock
    ) -> None:
        result = await pipeline.process_logs("t1", [_valid_log()])
        assert result.accepted == 1
        assert result.rejected == 0
        mock_router.route_logs.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_process_logs_with_pii_redaction(
        self, mock_router: AsyncMock, mock_enricher: AsyncMock
    ) -> None:
        pii_pipeline = IngestionPipeline(
            router=mock_router,
            enricher=mock_enricher,
            pii_detector=PIIDetector(),
        )
        log = _valid_log(body="User email alice@example.com logged in")
        result = await pii_pipeline.process_logs("t1", [log])
        assert result.accepted == 1
        # The PII should have been redacted before routing
        assert "alice@example.com" not in log.body
        assert "[EMAIL]" in log.body

    @pytest.mark.asyncio
    async def test_process_logs_validation_failure(
        self, pipeline: IngestionPipeline, mock_router: AsyncMock
    ) -> None:
        bad_log = LogRecord(timestamp=_now_ns(), body="")  # empty body
        result = await pipeline.process_logs("t1", [bad_log])
        assert result.rejected == 1
        assert result.accepted == 0
        mock_router.route_logs.assert_not_awaited()


# -----------------------------------------------------------------------
# Metrics
# -----------------------------------------------------------------------

class TestProcessMetrics:
    @pytest.mark.asyncio
    async def test_process_metrics_success(
        self, pipeline: IngestionPipeline, mock_router: AsyncMock
    ) -> None:
        result = await pipeline.process_metrics("t1", [_valid_metric()])
        assert result.accepted == 1
        mock_router.route_metrics.assert_awaited_once()


# -----------------------------------------------------------------------
# Traces
# -----------------------------------------------------------------------

class TestProcessTraces:
    @pytest.mark.asyncio
    async def test_process_traces_success(
        self, pipeline: IngestionPipeline, mock_router: AsyncMock
    ) -> None:
        result = await pipeline.process_traces("t1", [_valid_span()])
        assert result.accepted == 1
        mock_router.route_traces.assert_awaited_once()


# -----------------------------------------------------------------------
# Routing & error handling
# -----------------------------------------------------------------------

class TestRouting:
    @pytest.mark.asyncio
    async def test_pipeline_routes_to_nats(
        self, pipeline: IngestionPipeline, mock_router: AsyncMock
    ) -> None:
        await pipeline.process_logs("t1", [_valid_log()])
        mock_router.route_logs.assert_awaited_once()
        call_args = mock_router.route_logs.call_args
        assert call_args[0][0] == "t1"

    @pytest.mark.asyncio
    async def test_pipeline_handles_enrichment_error_gracefully(
        self, mock_router: AsyncMock
    ) -> None:
        bad_enricher = AsyncMock(spec=Enricher)
        bad_enricher.enrich = AsyncMock(side_effect=RuntimeError("enrichment boom"))

        pipeline = IngestionPipeline(
            router=mock_router,
            enricher=bad_enricher,
            pii_detector=PIIDetector(),
        )
        result = await pipeline.process_logs("t1", [_valid_log()])
        # The log should be rejected due to processing error, not crash the pipeline
        assert result.accepted == 0
        assert pipeline.metrics.errors == 1
