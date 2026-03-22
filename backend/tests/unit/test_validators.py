"""Tests for rayolly.services.ingestion.validators."""

from __future__ import annotations

import time

from rayolly.services.ingestion.models import LogRecord, MetricDataPoint, Span
from rayolly.services.ingestion.validators import (
    MAX_ATTRIBUTE_COUNT,
    MAX_MESSAGE_SIZE_BYTES,
    validate_log,
    validate_metric,
    validate_span,
)


def _now_ns() -> int:
    return int(time.time() * 1_000_000_000)


# -----------------------------------------------------------------------
# Log validation
# -----------------------------------------------------------------------

class TestValidateLog:
    def test_valid_log_passes(self) -> None:
        record = LogRecord(timestamp=_now_ns(), body="Hello world")
        result = validate_log(record)
        assert result.valid is True
        assert result.errors == []

    def test_future_timestamp_rejected(self) -> None:
        future_ns = _now_ns() + 10 * 60 * 1_000_000_000  # 10 min in future
        record = LogRecord(timestamp=future_ns, body="future log")
        result = validate_log(record)
        assert result.valid is False
        assert any("future" in e.lower() for e in result.errors)

    def test_old_timestamp_rejected(self) -> None:
        old_ns = _now_ns() - 8 * 24 * 60 * 60 * 1_000_000_000  # 8 days ago
        record = LogRecord(timestamp=old_ns, body="ancient log")
        result = validate_log(record)
        assert result.valid is False
        assert any("older" in e.lower() or "7 days" in e.lower() for e in result.errors)

    def test_missing_body_rejected(self) -> None:
        record = LogRecord(timestamp=_now_ns(), body="")
        result = validate_log(record)
        assert result.valid is False
        assert any("empty" in e.lower() for e in result.errors)

    def test_empty_body_rejected(self) -> None:
        record = LogRecord(timestamp=_now_ns(), body="")
        result = validate_log(record)
        assert result.valid is False

    def test_oversized_body_rejected(self) -> None:
        huge_body = "x" * (MAX_MESSAGE_SIZE_BYTES + 1)
        record = LogRecord(timestamp=_now_ns(), body=huge_body)
        result = validate_log(record)
        assert result.valid is False
        assert any("size" in e.lower() or "exceeds" in e.lower() for e in result.errors)

    def test_too_many_attributes_rejected(self) -> None:
        attrs = {f"key_{i}": f"value_{i}" for i in range(MAX_ATTRIBUTE_COUNT + 1)}
        record = LogRecord(timestamp=_now_ns(), body="log", attributes=attrs)
        result = validate_log(record)
        assert result.valid is False
        assert any("exceeds" in e.lower() for e in result.errors)


# -----------------------------------------------------------------------
# Metric validation
# -----------------------------------------------------------------------

class TestValidateMetric:
    def test_valid_metric_passes(self) -> None:
        dp = MetricDataPoint(name="cpu_usage", value=0.85, timestamp=_now_ns())
        result = validate_metric(dp)
        assert result.valid is True


# -----------------------------------------------------------------------
# Span validation
# -----------------------------------------------------------------------

class TestValidateSpan:
    def test_valid_span_passes(self) -> None:
        ts = _now_ns()
        span = Span(
            trace_id="abcdef1234567890abcdef1234567890",
            span_id="1234567890abcdef",
            name="GET /api",
            start_time=ts,
            end_time=ts + 50_000_000,
        )
        result = validate_span(span)
        assert result.valid is True
