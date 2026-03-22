"""OTLP gRPC server for high-throughput telemetry ingestion.

Listens on port 4317 (standard OTLP gRPC port).
Accepts ExportLogsServiceRequest, ExportMetricsServiceRequest, ExportTraceServiceRequest.
Converts to internal models and feeds into the ingestion pipeline.
"""
from __future__ import annotations

import asyncio
from concurrent import futures
from typing import Any

import grpc
import structlog
from opentelemetry.proto.collector.logs.v1 import logs_service_pb2, logs_service_pb2_grpc
from opentelemetry.proto.collector.metrics.v1 import metrics_service_pb2, metrics_service_pb2_grpc
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2, trace_service_pb2_grpc

from rayolly.services.ingestion.models import (
    LogRecord,
    MetricDataPoint,
    MetricType,
    SeverityLevel,
    Span,
)
from rayolly.services.ingestion.pipeline import IngestionPipeline

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_value(val: Any) -> str | int | float | bool:
    """Extract a Python value from an OTLP AnyValue proto."""
    if val.HasField("string_value"):
        return val.string_value
    if val.HasField("int_value"):
        return val.int_value
    if val.HasField("double_value"):
        return val.double_value
    if val.HasField("bool_value"):
        return val.bool_value
    if val.HasField("bytes_value"):
        return val.bytes_value.hex()
    if val.HasField("array_value"):
        return [_extract_value(v) for v in val.array_value.values]
    if val.HasField("kvlist_value"):
        return {kv.key: _extract_value(kv.value) for kv in val.kvlist_value.values}
    return str(val)


def _tenant_from_metadata(context: grpc.aio.ServicerContext) -> str:
    """Extract the tenant ID from gRPC invocation metadata."""
    metadata = dict(context.invocation_metadata())
    return metadata.get("x-rayolly-tenant", metadata.get("tenant_id", "default"))


# Severity number ranges defined by the OpenTelemetry specification.
_SEVERITY_MAP: dict[int, str] = {
    1: "TRACE", 2: "TRACE", 3: "TRACE", 4: "TRACE",
    5: "DEBUG", 6: "DEBUG", 7: "DEBUG", 8: "DEBUG",
    9: "INFO", 10: "INFO", 11: "INFO", 12: "INFO",
    13: "WARN", 14: "WARN", 15: "WARN", 16: "WARN",
    17: "ERROR", 18: "ERROR", 19: "ERROR", 20: "ERROR",
    21: "FATAL", 22: "FATAL", 23: "FATAL", 24: "FATAL",
}

_KIND_MAP: dict[int, str] = {
    0: "INTERNAL",
    1: "INTERNAL",
    2: "SERVER",
    3: "CLIENT",
    4: "PRODUCER",
    5: "CONSUMER",
}

_STATUS_MAP: dict[int, str] = {
    0: "UNSET",
    1: "OK",
    2: "ERROR",
}


# ---------------------------------------------------------------------------
# gRPC Servicers
# ---------------------------------------------------------------------------

class LogsServicer(logs_service_pb2_grpc.LogsServiceServicer):
    """Handles OTLP ExportLogsServiceRequest."""

    def __init__(self, pipeline: IngestionPipeline) -> None:
        self.pipeline = pipeline

    async def Export(
        self,
        request: logs_service_pb2.ExportLogsServiceRequest,
        context: grpc.aio.ServicerContext,
    ) -> logs_service_pb2.ExportLogsServiceResponse:
        tenant_id = _tenant_from_metadata(context)

        logs: list[LogRecord] = []
        for resource_logs in request.resource_logs:
            resource_attrs = {
                kv.key: _extract_value(kv.value)
                for kv in resource_logs.resource.attributes
            }
            for scope_logs in resource_logs.scope_logs:
                for lr in scope_logs.log_records:
                    body = (
                        lr.body.string_value
                        if lr.body.HasField("string_value")
                        else str(lr.body)
                    )
                    severity = _SEVERITY_MAP.get(lr.severity_number, "INFO")
                    attrs = {
                        kv.key: _extract_value(kv.value) for kv in lr.attributes
                    }

                    logs.append(
                        LogRecord(
                            timestamp=lr.time_unix_nano,
                            body=body,
                            severity=SeverityLevel(severity),
                            attributes=attrs,
                            resource_attributes=resource_attrs,
                            trace_id=lr.trace_id.hex() if lr.trace_id else None,
                            span_id=lr.span_id.hex() if lr.span_id else None,
                        )
                    )

        result = await self.pipeline.process_logs(tenant_id, logs)
        logger.info(
            "grpc.logs_received",
            count=len(logs),
            accepted=result.accepted,
            rejected=result.rejected,
            tenant=tenant_id,
        )

        return logs_service_pb2.ExportLogsServiceResponse(
            partial_success=logs_service_pb2.ExportLogsPartialSuccess(
                rejected_log_records=result.rejected,
            )
        )


class MetricsServicer(metrics_service_pb2_grpc.MetricsServiceServicer):
    """Handles OTLP ExportMetricsServiceRequest."""

    def __init__(self, pipeline: IngestionPipeline) -> None:
        self.pipeline = pipeline

    async def Export(
        self,
        request: metrics_service_pb2.ExportMetricsServiceRequest,
        context: grpc.aio.ServicerContext,
    ) -> metrics_service_pb2.ExportMetricsServiceResponse:
        tenant_id = _tenant_from_metadata(context)

        metrics: list[MetricDataPoint] = []
        for resource_metrics in request.resource_metrics:
            resource_attrs = {
                kv.key: _extract_value(kv.value)
                for kv in resource_metrics.resource.attributes
            }
            for scope_metrics in resource_metrics.scope_metrics:
                for metric in scope_metrics.metrics:
                    data_points: list[Any] = []
                    mtype = "gauge"

                    if metric.HasField("gauge"):
                        data_points = metric.gauge.data_points
                        mtype = "gauge"
                    elif metric.HasField("sum"):
                        data_points = metric.sum.data_points
                        mtype = "counter"
                    elif metric.HasField("histogram"):
                        data_points = metric.histogram.data_points
                        mtype = "histogram"
                    elif metric.HasField("summary"):
                        data_points = metric.summary.data_points
                        mtype = "summary"

                    for dp in data_points:
                        value: float
                        if hasattr(dp, "as_double") and dp.HasField("as_double"):
                            value = dp.as_double
                        elif hasattr(dp, "as_int"):
                            value = float(dp.as_int)
                        else:
                            value = 0.0

                        labels = {
                            kv.key: _extract_value(kv.value)
                            for kv in dp.attributes
                        }

                        metrics.append(
                            MetricDataPoint(
                                name=metric.name,
                                type=MetricType(mtype),
                                value=value,
                                timestamp=dp.time_unix_nano,
                                labels={k: str(v) for k, v in labels.items()},
                                resource_attributes=resource_attrs,
                                unit=metric.unit,
                                description=metric.description,
                            )
                        )

        result = await self.pipeline.process_metrics(tenant_id, metrics)
        logger.info(
            "grpc.metrics_received",
            count=len(metrics),
            accepted=result.accepted,
            rejected=result.rejected,
            tenant=tenant_id,
        )

        return metrics_service_pb2.ExportMetricsServiceResponse(
            partial_success=metrics_service_pb2.ExportMetricsPartialSuccess(
                rejected_data_points=result.rejected,
            )
        )


class TraceServicer(trace_service_pb2_grpc.TraceServiceServicer):
    """Handles OTLP ExportTraceServiceRequest."""

    def __init__(self, pipeline: IngestionPipeline) -> None:
        self.pipeline = pipeline

    async def Export(
        self,
        request: trace_service_pb2.ExportTraceServiceRequest,
        context: grpc.aio.ServicerContext,
    ) -> trace_service_pb2.ExportTraceServiceResponse:
        tenant_id = _tenant_from_metadata(context)

        spans: list[Span] = []
        for resource_spans in request.resource_spans:
            resource_attrs = {
                kv.key: _extract_value(kv.value)
                for kv in resource_spans.resource.attributes
            }
            for scope_spans in resource_spans.scope_spans:
                for s in scope_spans.spans:
                    attrs = {
                        kv.key: _extract_value(kv.value) for kv in s.attributes
                    }

                    events = []
                    for event in s.events:
                        events.append({
                            "name": event.name,
                            "timestamp": event.time_unix_nano,
                            "attributes": {
                                kv.key: _extract_value(kv.value)
                                for kv in event.attributes
                            },
                        })

                    links = []
                    for link in s.links:
                        links.append({
                            "trace_id": link.trace_id.hex(),
                            "span_id": link.span_id.hex(),
                            "attributes": {
                                kv.key: _extract_value(kv.value)
                                for kv in link.attributes
                            },
                        })

                    spans.append(
                        Span(
                            trace_id=s.trace_id.hex(),
                            span_id=s.span_id.hex(),
                            parent_span_id=(
                                s.parent_span_id.hex() if s.parent_span_id else None
                            ),
                            name=s.name,
                            kind=_KIND_MAP.get(s.kind, "INTERNAL"),
                            start_time=s.start_time_unix_nano,
                            end_time=s.end_time_unix_nano,
                            attributes=attrs,
                            resource_attributes=resource_attrs,
                            status_code=_STATUS_MAP.get(s.status.code, "UNSET"),
                            status_message=s.status.message,
                            events=events,
                            links=links,
                        )
                    )

        result = await self.pipeline.process_traces(tenant_id, spans)
        logger.info(
            "grpc.traces_received",
            count=len(spans),
            accepted=result.accepted,
            rejected=result.rejected,
            tenant=tenant_id,
        )

        return trace_service_pb2.ExportTraceServiceResponse(
            partial_success=trace_service_pb2.ExportTracePartialSuccess(
                rejected_spans=result.rejected,
            )
        )


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------

async def serve(pipeline: IngestionPipeline, port: int = 4317) -> None:
    """Start the OTLP gRPC server and block until termination."""
    server = grpc.aio.server(
        futures.ThreadPoolExecutor(max_workers=10),
        options=[
            ("grpc.max_receive_message_length", 16 * 1024 * 1024),  # 16 MB
            ("grpc.max_send_message_length", 16 * 1024 * 1024),
            ("grpc.keepalive_time_ms", 30_000),
            ("grpc.keepalive_timeout_ms", 10_000),
        ],
    )

    logs_service_pb2_grpc.add_LogsServiceServicer_to_server(
        LogsServicer(pipeline), server,
    )
    metrics_service_pb2_grpc.add_MetricsServiceServicer_to_server(
        MetricsServicer(pipeline), server,
    )
    trace_service_pb2_grpc.add_TraceServiceServicer_to_server(
        TraceServicer(pipeline), server,
    )

    server.add_insecure_port(f"[::]:{port}")
    await server.start()
    logger.info("grpc_server_started", port=port)

    try:
        await server.wait_for_termination()
    except asyncio.CancelledError:
        await server.stop(grace=5)
        logger.info("grpc_server_stopped")
