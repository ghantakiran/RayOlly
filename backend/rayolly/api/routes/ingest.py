from __future__ import annotations

import time
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from rayolly.services.ingestion.models import (
    LogRecord,
    MetricDataPoint,
    MetricType,
    SeverityLevel,
    Span,
)
from rayolly.services.ingestion.pipeline import IngestionPipeline

logger = structlog.get_logger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class LogIngestRequest(BaseModel):
    stream: str = "default"
    logs: list[LogRecord]


class MetricIngestRequest(BaseModel):
    metrics: list[MetricDataPoint]


class EventIngestRequest(BaseModel):
    event_type: str = "generic"
    events: list[dict[str, Any]]


class IngestResponse(BaseModel):
    accepted: int
    rejected: int
    processing_time_ms: float
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Dependencies — tenant comes from TenantMiddleware via request.state
# ---------------------------------------------------------------------------

_pipeline_instances: dict[str, IngestionPipeline] = {}  # keyed by id(nats_client)
_rate_limit_state: dict[str, tuple[float, int]] = {}
_RATE_LIMIT_WINDOW = 60.0
_RATE_LIMIT_MAX = 1000


def get_tenant_id(request: Request) -> str:
    """Get tenant_id from middleware (X-RayOlly-Tenant header)."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant identification required")
    return tenant_id


def check_rate_limit(request: Request) -> str:
    """Rate limit per tenant using sliding window."""
    tenant_id = get_tenant_id(request)
    now = time.monotonic()
    window_start, count = _rate_limit_state.get(tenant_id, (now, 0))

    if now - window_start > _RATE_LIMIT_WINDOW:
        _rate_limit_state[tenant_id] = (now, 1)
        return tenant_id

    if count >= _RATE_LIMIT_MAX:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    _rate_limit_state[tenant_id] = (window_start, count + 1)
    return tenant_id


async def get_pipeline(request: Request) -> IngestionPipeline:
    """Get or create the ingestion pipeline with NATS + ClickHouse."""
    nats = getattr(request.app.state, "nats", None)
    ch = getattr(request.app.state, "clickhouse", None)
    key = f"{id(nats)}_{id(ch)}"
    if key not in _pipeline_instances:
        _pipeline_instances[key] = IngestionPipeline(
            nats_client=nats,
            clickhouse_client=ch,
        )
    return _pipeline_instances[key]


# ---------------------------------------------------------------------------
# JSON ingestion endpoints
# ---------------------------------------------------------------------------

@router.post("/api/v1/logs/ingest", response_model=IngestResponse, status_code=status.HTTP_200_OK)
async def ingest_logs(
    body: LogIngestRequest,
    request: Request,
    pipeline: IngestionPipeline = Depends(get_pipeline),
) -> IngestResponse:
    tenant_id = check_rate_limit(request)
    for log in body.logs:
        log.stream = body.stream

    result = await pipeline.process_logs(tenant_id, body.logs)
    return IngestResponse(
        accepted=result.accepted,
        rejected=result.rejected,
        processing_time_ms=result.processing_time_ms,
        errors=result.errors,
    )


@router.post("/api/v1/metrics/ingest", response_model=IngestResponse, status_code=status.HTTP_200_OK)
async def ingest_metrics(
    body: MetricIngestRequest,
    request: Request,
    pipeline: IngestionPipeline = Depends(get_pipeline),
) -> IngestResponse:
    tenant_id = check_rate_limit(request)
    result = await pipeline.process_metrics(tenant_id, body.metrics)
    return IngestResponse(
        accepted=result.accepted,
        rejected=result.rejected,
        processing_time_ms=result.processing_time_ms,
        errors=result.errors,
    )


@router.post("/api/v1/events/ingest", response_model=IngestResponse, status_code=status.HTTP_200_OK)
async def ingest_events(
    body: EventIngestRequest,
    request: Request,
    pipeline: IngestionPipeline = Depends(get_pipeline),
) -> IngestResponse:
    tenant_id = check_rate_limit(request)
    now_ns = int(time.time() * 1_000_000_000)
    logs = [
        LogRecord(
            timestamp=event.get("timestamp", now_ns),
            body=str(event.get("body", event.get("message", ""))),
            severity=SeverityLevel(event.get("severity", "INFO")),
            attributes={
                **{k: v for k, v in event.items() if k not in ("timestamp", "body", "message", "severity")},
                "event_type": body.event_type,
            },
        )
        for event in body.events
    ]
    result = await pipeline.process_logs(tenant_id, logs)
    return IngestResponse(
        accepted=result.accepted,
        rejected=result.rejected,
        processing_time_ms=result.processing_time_ms,
        errors=result.errors,
    )


# ---------------------------------------------------------------------------
# OTLP HTTP endpoints
# ---------------------------------------------------------------------------

async def _read_body(request: Request) -> bytes:
    return await request.body()


@router.post("/v1/logs")
async def otlp_logs(
    request: Request,
    pipeline: IngestionPipeline = Depends(get_pipeline),
) -> Response:
    tenant_id = check_rate_limit(request)
    """OTLP HTTP log ingestion (protobuf or JSON).

    Parses the ExportLogsServiceRequest and converts to internal LogRecord format.
    """
    content_type = request.headers.get("content-type", "")
    raw = await _read_body(request)

    try:
        if "application/x-protobuf" in content_type:
            from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
                ExportLogsServiceRequest,
            )

            pb_request = ExportLogsServiceRequest()
            pb_request.ParseFromString(raw)
            logs = _convert_otlp_logs(pb_request)
        else:
            import orjson

            data = orjson.loads(raw)
            logs = _convert_otlp_logs_json(data)

        result = await pipeline.process_logs(tenant_id, logs)
        return Response(
            content=b"",
            status_code=status.HTTP_200_OK if result.accepted > 0 else status.HTTP_400_BAD_REQUEST,
        )
    except Exception:
        logger.error("otlp.logs_parse_failed", exc_info=True)
        return Response(content=b"", status_code=status.HTTP_400_BAD_REQUEST)


@router.post("/v1/metrics")
async def otlp_metrics(
    request: Request,
    pipeline: IngestionPipeline = Depends(get_pipeline),
) -> Response:
    tenant_id = check_rate_limit(request)
    content_type = request.headers.get("content-type", "")
    raw = await _read_body(request)

    try:
        if "application/x-protobuf" in content_type:
            from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
                ExportMetricsServiceRequest,
            )

            pb_request = ExportMetricsServiceRequest()
            pb_request.ParseFromString(raw)
            metrics = _convert_otlp_metrics(pb_request)
        else:
            import orjson

            data = orjson.loads(raw)
            metrics = _convert_otlp_metrics_json(data)

        result = await pipeline.process_metrics(tenant_id, metrics)
        return Response(
            content=b"",
            status_code=status.HTTP_200_OK if result.accepted > 0 else status.HTTP_400_BAD_REQUEST,
        )
    except Exception:
        logger.error("otlp.metrics_parse_failed", exc_info=True)
        return Response(content=b"", status_code=status.HTTP_400_BAD_REQUEST)


@router.post("/v1/traces")
async def otlp_traces(
    request: Request,
    pipeline: IngestionPipeline = Depends(get_pipeline),
) -> Response:
    tenant_id = check_rate_limit(request)
    content_type = request.headers.get("content-type", "")
    raw = await _read_body(request)

    try:
        if "application/x-protobuf" in content_type:
            from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
                ExportTraceServiceRequest,
            )

            pb_request = ExportTraceServiceRequest()
            pb_request.ParseFromString(raw)
            spans = _convert_otlp_traces(pb_request)
        else:
            import orjson

            data = orjson.loads(raw)
            spans = _convert_otlp_traces_json(data)

        result = await pipeline.process_traces(tenant_id, spans)
        return Response(
            content=b"",
            status_code=status.HTTP_200_OK if result.accepted > 0 else status.HTTP_400_BAD_REQUEST,
        )
    except Exception:
        logger.error("otlp.traces_parse_failed", exc_info=True)
        return Response(content=b"", status_code=status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# OTLP protobuf converters
# ---------------------------------------------------------------------------

def _extract_resource_attrs(resource: Any) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    for kv in resource.attributes:
        attrs[kv.key] = _otlp_anyvalue(kv.value)
    return attrs


def _otlp_anyvalue(val: Any) -> Any:
    if val.HasField("string_value"):
        return val.string_value
    if val.HasField("int_value"):
        return val.int_value
    if val.HasField("double_value"):
        return val.double_value
    if val.HasField("bool_value"):
        return val.bool_value
    return str(val)


def _convert_otlp_logs(pb_request: Any) -> list[LogRecord]:
    logs: list[LogRecord] = []
    for resource_logs in pb_request.resource_logs:
        resource_attrs = _extract_resource_attrs(resource_logs.resource)
        for scope_logs in resource_logs.scope_logs:
            for log_record in scope_logs.log_records:
                attrs: dict[str, Any] = {}
                for kv in log_record.attributes:
                    attrs[kv.key] = _otlp_anyvalue(kv.value)

                body = log_record.body.string_value if log_record.body.HasField("string_value") else str(log_record.body)
                severity_map = {1: "TRACE", 5: "DEBUG", 9: "INFO", 13: "WARN", 17: "ERROR", 21: "FATAL"}
                severity = severity_map.get(log_record.severity_number, "INFO")

                logs.append(LogRecord(
                    timestamp=log_record.time_unix_nano,
                    body=body,
                    severity=SeverityLevel(severity),
                    attributes=attrs,
                    resource_attributes=resource_attrs,
                    trace_id=log_record.trace_id.hex() if log_record.trace_id else None,
                    span_id=log_record.span_id.hex() if log_record.span_id else None,
                ))
    return logs


def _convert_otlp_metrics(pb_request: Any) -> list[MetricDataPoint]:
    metrics: list[MetricDataPoint] = []
    for resource_metrics in pb_request.resource_metrics:
        resource_attrs = _extract_resource_attrs(resource_metrics.resource)
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                if metric.HasField("gauge"):
                    for dp in metric.gauge.data_points:
                        metrics.append(_metric_dp_from_pb(metric.name, "gauge", dp, resource_attrs))
                elif metric.HasField("sum"):
                    for dp in metric.sum.data_points:
                        metrics.append(_metric_dp_from_pb(metric.name, "counter", dp, resource_attrs))
                elif metric.HasField("histogram"):
                    for dp in metric.histogram.data_points:
                        metrics.append(MetricDataPoint(
                            name=metric.name,
                            type=MetricType.HISTOGRAM,
                            value=dp.sum if dp.sum else 0.0,
                            timestamp=dp.time_unix_nano,
                            labels={kv.key: str(_otlp_anyvalue(kv.value)) for kv in dp.attributes},
                            resource_attributes=resource_attrs,
                        ))
    return metrics


def _metric_dp_from_pb(name: str, mtype: str, dp: Any, resource_attrs: dict[str, Any]) -> MetricDataPoint:
    value = dp.as_double if dp.HasField("as_double") else float(dp.as_int)
    labels = {kv.key: str(_otlp_anyvalue(kv.value)) for kv in dp.attributes}
    return MetricDataPoint(
        name=name,
        type=MetricType(mtype),
        value=value,
        timestamp=dp.time_unix_nano,
        labels=labels,
        resource_attributes=resource_attrs,
    )


def _convert_otlp_traces(pb_request: Any) -> list[Span]:
    spans: list[Span] = []
    kind_map = {0: "INTERNAL", 1: "INTERNAL", 2: "SERVER", 3: "CLIENT", 4: "PRODUCER", 5: "CONSUMER"}
    status_map = {0: "UNSET", 1: "OK", 2: "ERROR"}

    for resource_spans in pb_request.resource_spans:
        resource_attrs = _extract_resource_attrs(resource_spans.resource)
        for scope_spans in resource_spans.scope_spans:
            for pb_span in scope_spans.spans:
                attrs: dict[str, Any] = {}
                for kv in pb_span.attributes:
                    attrs[kv.key] = _otlp_anyvalue(kv.value)

                events = []
                for event in pb_span.events:
                    event_attrs = {kv.key: _otlp_anyvalue(kv.value) for kv in event.attributes}
                    events.append({
                        "name": event.name,
                        "timestamp": event.time_unix_nano,
                        "attributes": event_attrs,
                    })

                spans.append(Span(
                    trace_id=pb_span.trace_id.hex(),
                    span_id=pb_span.span_id.hex(),
                    parent_span_id=pb_span.parent_span_id.hex() if pb_span.parent_span_id else None,
                    name=pb_span.name,
                    kind=kind_map.get(pb_span.kind, "INTERNAL"),
                    start_time=pb_span.start_time_unix_nano,
                    end_time=pb_span.end_time_unix_nano,
                    attributes=attrs,
                    resource_attributes=resource_attrs,
                    status_code=status_map.get(pb_span.status.code, "UNSET"),
                    status_message=pb_span.status.message,
                    events=events,
                ))
    return spans


# ---------------------------------------------------------------------------
# OTLP JSON converters
# ---------------------------------------------------------------------------

def _extract_json_attrs(attributes: list[dict[str, Any]] | None) -> dict[str, Any]:
    if not attributes:
        return {}
    result: dict[str, Any] = {}
    for kv in attributes:
        val = kv.get("value", {})
        result[kv["key"]] = (
            val.get("stringValue")
            or val.get("intValue")
            or val.get("doubleValue")
            or val.get("boolValue")
            or str(val)
        )
    return result


def _convert_otlp_logs_json(data: dict[str, Any]) -> list[LogRecord]:
    logs: list[LogRecord] = []
    severity_map = {"1": "TRACE", "5": "DEBUG", "9": "INFO", "13": "WARN", "17": "ERROR", "21": "FATAL"}

    for rl in data.get("resourceLogs", []):
        resource_attrs = _extract_json_attrs(rl.get("resource", {}).get("attributes"))
        for sl in rl.get("scopeLogs", []):
            for lr in sl.get("logRecords", []):
                body_obj = lr.get("body", {})
                body = body_obj.get("stringValue", str(body_obj))
                sev_num = str(lr.get("severityNumber", "9"))
                severity = severity_map.get(sev_num, "INFO")
                attrs = _extract_json_attrs(lr.get("attributes"))

                logs.append(LogRecord(
                    timestamp=int(lr.get("timeUnixNano", 0)),
                    body=body,
                    severity=SeverityLevel(severity),
                    attributes=attrs,
                    resource_attributes=resource_attrs,
                    trace_id=lr.get("traceId"),
                    span_id=lr.get("spanId"),
                ))
    return logs


def _convert_otlp_metrics_json(data: dict[str, Any]) -> list[MetricDataPoint]:
    metrics: list[MetricDataPoint] = []
    for rm in data.get("resourceMetrics", []):
        resource_attrs = _extract_json_attrs(rm.get("resource", {}).get("attributes"))
        for sm in rm.get("scopeMetrics", []):
            for m in sm.get("metrics", []):
                name = m.get("name", "")
                for field_name, mtype in [("gauge", "gauge"), ("sum", "counter"), ("histogram", "histogram")]:
                    field_data = m.get(field_name)
                    if not field_data:
                        continue
                    for dp in field_data.get("dataPoints", []):
                        value = dp.get("asDouble", dp.get("asInt", 0.0))
                        labels = _extract_json_attrs(dp.get("attributes"))
                        metrics.append(MetricDataPoint(
                            name=name,
                            type=MetricType(mtype),
                            value=float(value),
                            timestamp=int(dp.get("timeUnixNano", 0)),
                            labels={k: str(v) for k, v in labels.items()},
                            resource_attributes=resource_attrs,
                        ))
    return metrics


def _convert_otlp_traces_json(data: dict[str, Any]) -> list[Span]:
    spans: list[Span] = []
    kind_map = {"0": "INTERNAL", "1": "INTERNAL", "2": "SERVER", "3": "CLIENT", "4": "PRODUCER", "5": "CONSUMER"}
    status_map = {"0": "UNSET", "1": "OK", "2": "ERROR"}

    for rs in data.get("resourceSpans", []):
        resource_attrs = _extract_json_attrs(rs.get("resource", {}).get("attributes"))
        for ss in rs.get("scopeSpans", []):
            for s in ss.get("spans", []):
                attrs = _extract_json_attrs(s.get("attributes"))
                events = []
                for event in s.get("events", []):
                    event_attrs = _extract_json_attrs(event.get("attributes"))
                    events.append({
                        "name": event.get("name", ""),
                        "timestamp": int(event.get("timeUnixNano", 0)),
                        "attributes": event_attrs,
                    })

                spans.append(Span(
                    trace_id=s.get("traceId", ""),
                    span_id=s.get("spanId", ""),
                    parent_span_id=s.get("parentSpanId"),
                    name=s.get("name", ""),
                    kind=kind_map.get(str(s.get("kind", 0)), "INTERNAL"),
                    start_time=int(s.get("startTimeUnixNano", 0)),
                    end_time=int(s.get("endTimeUnixNano", 0)),
                    attributes=attrs,
                    resource_attributes=resource_attrs,
                    status_code=status_map.get(str(s.get("status", {}).get("code", 0)), "UNSET"),
                    status_message=s.get("status", {}).get("message", ""),
                    events=events,
                ))
    return spans
