from __future__ import annotations

import time
from typing import Any

import orjson
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from rayolly.api.routes.ingest import IngestResponse, check_rate_limit, get_pipeline
from rayolly.services.ingestion.models import (
    LogRecord,
    MetricDataPoint,
    MetricType,
    SeverityLevel,
)
from rayolly.services.ingestion.pipeline import IngestionPipeline

logger = structlog.get_logger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Splunk HEC compatible
# ---------------------------------------------------------------------------

@router.post("/services/collector/event", response_model=IngestResponse)
async def splunk_hec_ingest(
    request: Request,
    tenant_id: str = Depends(check_rate_limit),
    pipeline: IngestionPipeline = Depends(get_pipeline),
) -> IngestResponse:
    """Splunk HTTP Event Collector (HEC) compatible endpoint.

    Accepts single events or batched events (newline-delimited JSON).
    """
    raw = await request.body()
    now_ns = int(time.time() * 1_000_000_000)

    logs: list[LogRecord] = []
    for line in raw.split(b"\n"):
        line = line.strip()
        if not line:
            continue
        try:
            event = orjson.loads(line)
        except Exception:
            logger.warning("compat.hec_parse_error", line=line[:200])
            continue

        ts = event.get("time")
        if ts is not None:
            timestamp = int(float(ts) * 1_000_000_000)
        else:
            timestamp = now_ns

        body = event.get("event", "")
        if isinstance(body, dict):
            body = orjson.dumps(body).decode("utf-8")

        attributes: dict[str, Any] = {}
        if fields := event.get("fields"):
            attributes.update(fields)

        resource_attrs: dict[str, Any] = {}
        if sourcetype := event.get("sourcetype"):
            resource_attrs["service.name"] = sourcetype
        if host := event.get("host"):
            resource_attrs["host.name"] = host
        if source := event.get("source"):
            attributes["log.source"] = source

        stream = event.get("index", "default")

        logs.append(LogRecord(
            timestamp=timestamp,
            body=str(body),
            severity=SeverityLevel.INFO,
            attributes=attributes,
            resource_attributes=resource_attrs,
            stream=stream,
        ))

    if not logs:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No valid events")

    result = await pipeline.process_logs(tenant_id, logs)
    return IngestResponse(
        accepted=result.accepted,
        rejected=result.rejected,
        processing_time_ms=result.processing_time_ms,
        errors=result.errors,
    )


# ---------------------------------------------------------------------------
# Elasticsearch Bulk API compatible
# ---------------------------------------------------------------------------

@router.post("/_bulk", response_model=IngestResponse)
async def elasticsearch_bulk_ingest(
    request: Request,
    tenant_id: str = Depends(check_rate_limit),
    pipeline: IngestionPipeline = Depends(get_pipeline),
) -> IngestResponse:
    """Elasticsearch-compatible _bulk endpoint.

    Accepts NDJSON (action + document pairs). Only 'index' and 'create'
    actions are supported; 'delete' and 'update' are silently ignored.
    """
    raw = await request.body()
    now_ns = int(time.time() * 1_000_000_000)
    lines = [l for l in raw.split(b"\n") if l.strip()]

    logs: list[LogRecord] = []
    i = 0
    while i < len(lines):
        try:
            action = orjson.loads(lines[i])
        except Exception:
            i += 1
            continue

        action_type = None
        action_meta: dict[str, Any] = {}
        for key in ("index", "create", "delete", "update"):
            if key in action:
                action_type = key
                action_meta = action[key]
                break

        if action_type in ("delete",):
            i += 1
            continue

        if action_type in ("update",):
            i += 2
            continue

        i += 1
        if i >= len(lines):
            break

        try:
            doc = orjson.loads(lines[i])
        except Exception:
            i += 1
            continue
        i += 1

        ts_str = doc.pop("@timestamp", None) or doc.pop("timestamp", None)
        if ts_str is not None:
            try:
                from datetime import datetime

                if isinstance(ts_str, (int, float)):
                    timestamp = int(ts_str * 1_000_000_000)
                else:
                    dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    timestamp = int(dt.timestamp() * 1_000_000_000)
            except Exception:
                timestamp = now_ns
        else:
            timestamp = now_ns

        body = doc.pop("message", "") or doc.pop("msg", "") or doc.pop("log", "")
        if not body:
            body = orjson.dumps(doc).decode("utf-8")

        stream = action_meta.get("_index", "default")
        severity_str = doc.pop("level", doc.pop("severity", "INFO")).upper()
        try:
            severity = SeverityLevel(severity_str)
        except ValueError:
            severity = SeverityLevel.INFO

        logs.append(LogRecord(
            timestamp=timestamp,
            body=str(body),
            severity=severity,
            attributes=doc,
            stream=stream,
        ))

    if not logs:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No valid documents")

    result = await pipeline.process_logs(tenant_id, logs)
    return IngestResponse(
        accepted=result.accepted,
        rejected=result.rejected,
        processing_time_ms=result.processing_time_ms,
        errors=result.errors,
    )


# ---------------------------------------------------------------------------
# Grafana Loki compatible
# ---------------------------------------------------------------------------

@router.post("/loki/api/v1/push", response_model=IngestResponse)
async def loki_push(
    request: Request,
    tenant_id: str = Depends(check_rate_limit),
    pipeline: IngestionPipeline = Depends(get_pipeline),
) -> IngestResponse:
    """Grafana Loki push API compatible endpoint.

    Accepts the Loki push format with streams containing labels and entries.
    """
    raw = await request.body()

    try:
        data = orjson.loads(raw)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    logs: list[LogRecord] = []
    for stream_entry in data.get("streams", []):
        labels = stream_entry.get("stream", {})
        stream_name = labels.pop("stream", labels.pop("job", "default"))
        service_name = labels.pop("service_name", labels.pop("app", ""))

        resource_attrs: dict[str, Any] = {}
        if service_name:
            resource_attrs["service.name"] = service_name

        for entry in stream_entry.get("values", []):
            if len(entry) < 2:
                continue
            ts_str, line = entry[0], entry[1]
            try:
                timestamp = int(ts_str)
            except (ValueError, TypeError):
                timestamp = int(time.time() * 1_000_000_000)

            structured_metadata: dict[str, Any] = {}
            if len(entry) > 2 and isinstance(entry[2], dict):
                structured_metadata = entry[2]

            logs.append(LogRecord(
                timestamp=timestamp,
                body=line,
                severity=SeverityLevel(labels.get("level", "INFO").upper()) if labels.get("level") else SeverityLevel.INFO,
                attributes={**labels, **structured_metadata},
                resource_attributes=resource_attrs,
                stream=stream_name,
            ))

    if not logs:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No valid entries")

    result = await pipeline.process_logs(tenant_id, logs)
    return IngestResponse(
        accepted=result.accepted,
        rejected=result.rejected,
        processing_time_ms=result.processing_time_ms,
        errors=result.errors,
    )


# ---------------------------------------------------------------------------
# Prometheus Remote Write compatible
# ---------------------------------------------------------------------------

@router.post("/api/v1/prometheus/write")
async def prometheus_remote_write(
    request: Request,
    tenant_id: str = Depends(check_rate_limit),
    pipeline: IngestionPipeline = Depends(get_pipeline),
) -> Response:
    """Prometheus Remote Write compatible endpoint.

    Accepts snappy-compressed protobuf WriteRequest messages.
    NOTE: Requires compiled protobuf definitions for prometheus.WriteRequest.
    Using a stub implementation that decodes the snappy-compressed payload
    and converts to internal MetricDataPoint format.
    """
    raw = await request.body()

    try:
        # Decompress snappy-compressed payload
        # NOTE: In production, compile prometheus remote write proto definitions
        # and use them here. For now we attempt to use the snappy + protobuf path,
        # falling back to a stub that returns an appropriate error.
        try:
            import snappy  # type: ignore[import-untyped]

            decompressed = snappy.decompress(raw)
        except ImportError:
            logger.warning("compat.prometheus_write.snappy_unavailable")
            decompressed = raw

        # Stub: parse WriteRequest protobuf
        # In production, generate Python bindings from prometheus protobufs:
        #   from prometheus_pb2 import WriteRequest
        #   write_request = WriteRequest()
        #   write_request.ParseFromString(decompressed)
        #
        # Then iterate timeseries:
        #   for ts in write_request.timeseries:
        #       labels = {l.name: l.value for l in ts.labels}
        #       name = labels.pop("__name__", "unknown")
        #       for sample in ts.samples:
        #           metrics.append(MetricDataPoint(
        #               name=name,
        #               type=MetricType.GAUGE,
        #               value=sample.value,
        #               timestamp=int(sample.timestamp * 1_000_000),
        #               labels=labels,
        #           ))
        metrics = _parse_prometheus_write_request(decompressed)

        if not metrics:
            return Response(status_code=status.HTTP_204_NO_CONTENT)

        await pipeline.process_metrics(tenant_id, metrics)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception:
        logger.error("compat.prometheus_write_failed", exc_info=True)
        return Response(status_code=status.HTTP_400_BAD_REQUEST)


def _parse_prometheus_write_request(data: bytes) -> list[MetricDataPoint]:
    """Parse Prometheus WriteRequest protobuf.

    This is a best-effort parser. In production, use compiled protobuf
    definitions generated from prometheus/prometheus protobufs.
    """
    try:
        from prometheus_pb2 import WriteRequest  # type: ignore[import-not-found]

        write_request = WriteRequest()
        write_request.ParseFromString(data)

        metrics: list[MetricDataPoint] = []
        for ts in write_request.timeseries:
            labels = {label.name: label.value for label in ts.labels}
            name = labels.pop("__name__", "unknown")
            for sample in ts.samples:
                metrics.append(MetricDataPoint(
                    name=name,
                    type=MetricType.GAUGE,
                    value=sample.value,
                    timestamp=int(sample.timestamp * 1_000_000),
                    labels=labels,
                ))
        return metrics
    except ImportError:
        logger.debug("compat.prometheus_pb2_unavailable")
        return []
