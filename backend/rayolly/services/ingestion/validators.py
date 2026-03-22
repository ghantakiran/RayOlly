from __future__ import annotations

import time

from rayolly.services.ingestion.models import (
    LogRecord,
    MetricDataPoint,
    Span,
    ValidationResult,
)

MAX_MESSAGE_SIZE_BYTES = 1_048_576  # 1 MB
MAX_ATTRIBUTE_COUNT = 128
MAX_FUTURE_DRIFT_NS = 5 * 60 * 1_000_000_000  # 5 minutes
MAX_AGE_NS = 7 * 24 * 60 * 60 * 1_000_000_000  # 7 days


def _now_ns() -> int:
    return int(time.time() * 1_000_000_000)


def _check_timestamp(ts: int, errors: list[str]) -> None:
    now = _now_ns()
    if ts > now + MAX_FUTURE_DRIFT_NS:
        errors.append(f"Timestamp {ts} is too far in the future")
    if ts < now - MAX_AGE_NS:
        errors.append(f"Timestamp {ts} is older than 7 days")


def _check_attributes(attrs: dict, label: str, errors: list[str]) -> None:
    if len(attrs) > MAX_ATTRIBUTE_COUNT:
        errors.append(f"{label} count {len(attrs)} exceeds maximum {MAX_ATTRIBUTE_COUNT}")


def validate_log(record: LogRecord) -> ValidationResult:
    errors: list[str] = []

    if not record.body:
        errors.append("Log body is empty")

    _check_timestamp(record.timestamp, errors)
    _check_attributes(record.attributes, "attributes", errors)
    _check_attributes(record.resource_attributes, "resource_attributes", errors)

    serialized_size = len(record.body.encode("utf-8"))
    if serialized_size > MAX_MESSAGE_SIZE_BYTES:
        errors.append(f"Log body size {serialized_size} exceeds {MAX_MESSAGE_SIZE_BYTES} bytes")

    return ValidationResult(valid=len(errors) == 0, errors=errors)


def validate_metric(dp: MetricDataPoint) -> ValidationResult:
    errors: list[str] = []

    if not dp.name:
        errors.append("Metric name is required")

    _check_timestamp(dp.timestamp, errors)
    _check_attributes(dp.labels, "labels", errors)

    return ValidationResult(valid=len(errors) == 0, errors=errors)


def validate_span(span: Span) -> ValidationResult:
    errors: list[str] = []

    if not span.trace_id:
        errors.append("trace_id is required")
    if not span.span_id:
        errors.append("span_id is required")
    if not span.name:
        errors.append("Span name is required")

    _check_timestamp(span.start_time, errors)

    if span.end_time < span.start_time:
        errors.append("end_time cannot be before start_time")

    _check_attributes(span.attributes, "attributes", errors)
    _check_attributes(span.resource_attributes, "resource_attributes", errors)

    return ValidationResult(valid=len(errors) == 0, errors=errors)
