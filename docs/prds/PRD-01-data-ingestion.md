# PRD-01: Data Ingestion & OpenTelemetry Pipeline

**Product**: RayOlly — AI-Native Observability Platform
**Version**: 1.0
**Date**: 2026-03-19
**Status**: Draft
**Parent**: PRD-00 Platform Vision & Architecture
**Dependencies**: None (foundational component)

---

## 1. Executive Summary

The Data Ingestion Pipeline is RayOlly's front door — every byte of observability data enters through this layer. It is designed to be **OpenTelemetry-native first**, while supporting every major ingestion protocol for frictionless migration from existing tools. The pipeline handles parsing, enrichment, transformation, routing, and delivery to the storage engine at enterprise scale.

**Design Principles**:
- OTLP is the primary protocol; all others are adapters
- Schema-on-read: accept any shape, validate later
- At-least-once delivery with exactly-once semantics for metrics
- Stateless horizontal scaling behind load balancers
- AI-integrated: feed data to ML pipeline for real-time scoring during ingestion

---

## 2. Goals & Non-Goals

### Goals
1. Support OTLP (gRPC + HTTP) as the primary ingestion protocol
2. Provide compatibility endpoints for Prometheus, Fluentd, Syslog, Splunk HEC, Datadog, Elasticsearch Bulk API
3. Achieve 1M+ events/sec per ingestion node with linear horizontal scaling
4. End-to-end ingestion latency < 5 seconds (receipt to queryable)
5. Zero data loss with at-least-once delivery guarantees
6. Support schema validation, data enrichment, PII redaction, and field extraction at wire speed
7. Provide a lightweight RayOlly Collector agent for host-level telemetry collection
8. Enable seamless migration from Datadog, Splunk, ELK, and Prometheus
9. Multi-tenant with per-tenant rate limiting and quotas
10. Self-monitoring with comprehensive ingestion metrics

### Non-Goals
- Building a proprietary SDK (leverage OpenTelemetry SDKs)
- Real-time stream processing beyond enrichment (that's the AI/ML engine's job)
- Long-term data storage (that's the Storage Engine's job — PRD-02)
- Query execution (that's the Query Engine's job — PRD-03)

---

## 3. Protocol Support

### 3.1 Protocol Matrix

| Protocol | Format | Transport | Port | Priority | Use Case |
|----------|--------|-----------|------|----------|----------|
| **OTLP** | Protobuf | gRPC | 4317 | P0 | Primary — modern OTEL-instrumented apps |
| **OTLP** | Protobuf/JSON | HTTP | 4318 | P0 | Primary — environments without gRPC |
| **Prometheus Remote Write** | Protobuf (snappy) | HTTP | 8080 | P0 | Prometheus migration path |
| **HTTP JSON** | JSON | HTTP | 8080 | P0 | Custom events, simple integration |
| **Elasticsearch Bulk** | NDJSON | HTTP | 8080 | P1 | ELK migration path |
| **Splunk HEC** | JSON | HTTP | 8088 | P1 | Splunk migration path |
| **Syslog** | RFC 5424/3164 | TCP/UDP | 514/1514 | P1 | Network devices, legacy infrastructure |
| **Fluentd Forward** | MessagePack | TCP | 24224 | P1 | Existing Fluentd/Fluent Bit pipelines |
| **Loki Push** | Protobuf/JSON | HTTP | 3100 | P1 | Grafana Loki migration |
| **Datadog API** | JSON | HTTP | 8080 | P2 | Datadog migration path |
| **StatsD** | Text | UDP | 8125 | P2 | Legacy application metrics |
| **Kafka Consumer** | Various | Kafka | — | P2 | Existing Kafka telemetry pipelines |
| **Zipkin** | JSON/Thrift | HTTP | 9411 | P2 | Zipkin migration |
| **Jaeger** | Thrift/Protobuf | gRPC/HTTP | 14268 | P2 | Jaeger migration |

### 3.2 OTLP Ingestion (Primary Path)

```
┌─────────────────────────────────────────────────────┐
│              OTLP Ingestion Handler                  │
│                                                      │
│  gRPC Server (port 4317)                            │
│  ├── LogsService/Export                              │
│  ├── MetricsService/Export                           │
│  └── TracesService/Export                            │
│                                                      │
│  HTTP Server (port 4318)                            │
│  ├── POST /v1/logs                                   │
│  ├── POST /v1/metrics                                │
│  └── POST /v1/traces                                 │
│                                                      │
│  Authentication: Bearer token / API key              │
│  Compression: gzip, zstd, snappy                     │
│  TLS: Required (TLS 1.3)                            │
│  Max payload: 10MB (configurable)                    │
│  Batch support: Native OTLP batching                 │
└─────────────────────────────────────────────────────┘
```

**OTLP gRPC Configuration**:
```python
# FastAPI + grpcio server
from opentelemetry.proto.collector.logs.v1 import logs_service_pb2_grpc
from opentelemetry.proto.collector.metrics.v1 import metrics_service_pb2_grpc
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2_grpc

class LogsServicer(logs_service_pb2_grpc.LogsServiceServicer):
    async def Export(self, request, context):
        tenant_id = extract_tenant(context)
        await rate_limiter.check(tenant_id)
        resource_logs = request.resource_logs
        await pipeline.process_logs(tenant_id, resource_logs)
        return ExportLogsServiceResponse(
            partial_success=ExportLogsPartialSuccess(rejected_log_records=0)
        )
```

### 3.3 Compatibility Endpoints

**Prometheus Remote Write**:
```
POST /api/v1/prometheus/write
Content-Type: application/x-protobuf
Content-Encoding: snappy
X-RayOlly-Tenant: <tenant-id>
Authorization: Bearer <token>

# Accepts standard Prometheus remote write protobuf format
# Converts to OTEL metric data model internally
```

**Splunk HEC**:
```
POST /services/collector/event
Authorization: Splunk <hec-token>
Content-Type: application/json

{"event": "Payment processed", "sourcetype": "payment-api", "index": "main", "time": 1711000000}

# Maps Splunk fields to OTEL log model:
# event → body, sourcetype → resource.service.name, index → stream, time → timestamp
```

**Elasticsearch Bulk API**:
```
POST /_bulk
Content-Type: application/x-ndjson

{"index": {"_index": "app-logs"}}
{"@timestamp": "2026-03-19T10:00:00Z", "message": "Request completed", "level": "info"}

# Maps ES fields to OTEL: @timestamp → timestamp, message → body, _index → stream
```

---

## 4. RayOlly Collector Agent

### 4.1 Overview

The RayOlly Collector is a lightweight, OTEL Collector-based distribution that ships with pre-configured receivers, processors, and the RayOlly exporter.

### 4.2 Capabilities

| Capability | Description |
|-----------|------------|
| **Host metrics** | CPU, memory, disk, network, load, filesystem, process |
| **Log file tailing** | Tail log files with configurable paths, multiline support |
| **Container metrics** | Docker/containerd stats, container lifecycle events |
| **K8s metadata enrichment** | Pod name, namespace, deployment, labels, annotations |
| **Process monitoring** | Top processes by CPU/memory, process lifecycle |
| **Service auto-discovery** | Detect running services (nginx, postgres, redis, etc.) |
| **OTLP receiver** | Accept OTEL data from application SDKs |
| **Prometheus scraper** | Scrape /metrics endpoints from local services |
| **JMX receiver** | Java application metrics (optional) |
| **Central configuration** | Pull config from RayOlly API on startup, hot-reload |

### 4.3 Resource Footprint

| Resource | Target | Maximum |
|----------|--------|---------|
| CPU | < 0.5% of host | < 2% |
| Memory | < 50MB | < 150MB |
| Disk I/O | < 1MB/s | < 5MB/s |
| Network | < 100KB/s (compressed) | < 1MB/s |
| Binary size | < 50MB | — |

### 4.4 Collector Configuration

```yaml
# rayolly-collector.yaml
receivers:
  hostmetrics:
    collection_interval: 15s
    scrapers:
      cpu: { metrics: [system.cpu.utilization] }
      memory: {}
      disk: {}
      network: {}
      filesystem: {}
      load: {}
      process:
        include: { match_type: regexp, names: [".*"] }

  filelog:
    include:
      - /var/log/syslog
      - /var/log/auth.log
      - /app/logs/*.log
    multiline:
      line_start_pattern: '^\d{4}-\d{2}-\d{2}'
    operators:
      - type: regex_parser
        regex: '^(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.\d+Z)\s+\[(?P<severity>\w+)\]\s+(?P<body>.*)'

  otlp:
    protocols:
      grpc: { endpoint: 0.0.0.0:4317 }
      http: { endpoint: 0.0.0.0:4318 }

  prometheus:
    config:
      scrape_configs:
        - job_name: local-services
          scrape_interval: 30s
          static_configs:
            - targets: ['localhost:9090', 'localhost:9100']

processors:
  batch:
    send_batch_size: 5000
    timeout: 5s
  memory_limiter:
    limit_mib: 128
    spike_limit_mib: 32
  resourcedetection:
    detectors: [env, system, docker, ec2, gcp, azure]
  k8sattributes:
    auth_type: serviceAccount
    extract:
      metadata: [k8s.pod.name, k8s.namespace.name, k8s.deployment.name]
      labels: [app, version, team]

exporters:
  otlp/rayolly:
    endpoint: ingest.rayolly.example.com:4317
    headers:
      Authorization: "Bearer ${RAYOLLY_INGEST_TOKEN}"
      X-RayOlly-Tenant: "${RAYOLLY_TENANT_ID}"
    compression: zstd
    retry_on_failure:
      enabled: true
      max_elapsed_time: 300s
    sending_queue:
      enabled: true
      num_consumers: 10
      queue_size: 5000

service:
  pipelines:
    logs:
      receivers: [filelog, otlp]
      processors: [memory_limiter, batch, resourcedetection, k8sattributes]
      exporters: [otlp/rayolly]
    metrics:
      receivers: [hostmetrics, otlp, prometheus]
      processors: [memory_limiter, batch, resourcedetection]
      exporters: [otlp/rayolly]
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch, resourcedetection, k8sattributes]
      exporters: [otlp/rayolly]
```

### 4.5 Installation

```bash
# Linux (one-liner)
curl -sSL https://install.rayolly.io/collector | bash -s -- \
  --token "$RAYOLLY_INGEST_TOKEN" \
  --tenant "$RAYOLLY_TENANT_ID" \
  --endpoint "ingest.rayolly.example.com:4317"

# Docker
docker run -d --name rayolly-collector \
  -v /var/log:/var/log:ro \
  -v /proc:/host/proc:ro \
  -e RAYOLLY_INGEST_TOKEN="..." \
  -e RAYOLLY_TENANT_ID="..." \
  rayolly/collector:latest

# Kubernetes DaemonSet
helm install rayolly-collector rayolly/collector \
  --set token="..." \
  --set tenant="..." \
  --set endpoint="ingest.rayolly.example.com:4317"
```

---

## 5. Ingestion Pipeline Architecture

### 5.1 Pipeline Flow

```
                    ┌──────────────────────────────┐
                    │      Load Balancer (L4)       │
                    │  (HAProxy / AWS NLB / K8s)    │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │     Ingestion Gateway         │
                    │                               │
                    │  1. TLS Termination           │
                    │  2. Authentication             │
                    │  3. Tenant Identification      │
                    │  4. Rate Limiting              │
                    │  5. Protocol Detection          │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │     Protocol Adapter Layer     │
                    │                               │
                    │  OTLP → Internal Model         │
                    │  Prom RW → Internal Model      │
                    │  HEC → Internal Model          │
                    │  Syslog → Internal Model       │
                    │  ES Bulk → Internal Model      │
                    │  (All converge to OTEL model)  │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │     Processing Pipeline        │
                    │                               │
                    │  Stage 1: Schema Validation    │
                    │  Stage 2: Field Extraction     │
                    │  Stage 3: Enrichment           │
                    │  Stage 4: Transformation       │
                    │  Stage 5: PII Detection        │
                    │  Stage 6: Sampling             │
                    │  Stage 7: Routing              │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │     NATS JetStream             │
                    │                               │
                    │  Subjects:                     │
                    │  rayolly.ingest.logs.{tenant}  │
                    │  rayolly.ingest.metrics.{tenant}│
                    │  rayolly.ingest.traces.{tenant}│
                    │  rayolly.dlq.{tenant}          │
                    └──────────────┬───────────────┘
                                   │
                         ┌─────────┼─────────┐
                         ▼         ▼         ▼
                    ┌─────────┐ ┌─────┐ ┌────────┐
                    │ClickHouse│ │ AI  │ │ Alert  │
                    │ Writer   │ │ ML  │ │ Eval   │
                    │          │ │Score│ │        │
                    └─────────┘ └─────┘ └────────┘
```

### 5.2 Processing Stages

**Stage 1: Schema Validation**
- Validate timestamp format and range (reject future dates > 5min, past dates > 7d)
- Validate required fields (timestamp, body/value, resource)
- Type coercion for known fields
- Reject oversized payloads (> 1MB per record)

**Stage 2: Field Extraction**
```yaml
# Parsing pipeline configuration
parsers:
  - name: json-auto
    type: json
    auto_detect: true
    flatten_depth: 3

  - name: nginx-access
    type: grok
    match: stream=nginx-access
    pattern: '%{NGINX_ACCESS}'
    timestamp_field: time_local
    timestamp_format: "02/Jan/2006:15:04:05 -0700"

  - name: kv-extract
    type: key_value
    delimiter: "="
    pair_delimiter: " "
    fields: [body]
```

**Stage 3: Enrichment**
```yaml
enrichment:
  geoip:
    enabled: true
    database: /data/maxmind/GeoLite2-City.mmdb
    source_fields: [attributes.client_ip, attributes.remote_addr]
    target_prefix: geo

  kubernetes:
    enabled: true
    api_server: https://kubernetes.default.svc
    metadata:
      - pod_name → resource.k8s.pod.name
      - namespace → resource.k8s.namespace.name
      - deployment → resource.k8s.deployment.name
      - labels → resource.k8s.labels.*
      - annotations → resource.k8s.annotations.*
      - node_name → resource.k8s.node.name

  hostname_resolution:
    enabled: true
    cache_ttl: 300s

  service_catalog:
    enabled: true
    # Enrich with team owner, tier, runbook URL from service catalog
```

**Stage 4: Transformation**
```yaml
transforms:
  - name: rename-fields
    type: rename
    mappings:
      msg: body
      lvl: severity_text
      ts: timestamp

  - name: drop-debug
    type: filter
    condition: "severity_text == 'DEBUG' AND resource_service != 'payment-api'"
    action: drop

  - name: sample-verbose
    type: sample
    condition: "severity_text == 'INFO' AND stream == 'access-logs'"
    rate: 0.1  # Keep 10% of matching logs
```

**Stage 5: PII Detection & Redaction**
```yaml
pii_redaction:
  enabled: true
  detectors:
    - type: regex
      name: credit_card
      pattern: '\b(?:\d{4}[-\s]?){3}\d{4}\b'
      replacement: "[REDACTED_CC]"
    - type: regex
      name: ssn
      pattern: '\b\d{3}-\d{2}-\d{4}\b'
      replacement: "[REDACTED_SSN]"
    - type: regex
      name: email
      pattern: '\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
      replacement: "[REDACTED_EMAIL]"
    - type: ai
      name: ai_pii_detector
      enabled: false  # Enable for AI-powered PII detection (higher accuracy, higher cost)
      model: pii-detector-v1
      confidence_threshold: 0.9
  apply_to: [body, attributes.*]
  audit_log: true  # Log what was redacted for compliance
```

**Stage 6: Sampling**
```yaml
sampling:
  # Head-based sampling for logs
  logs:
    default_rate: 1.0  # Keep all by default
    rules:
      - condition: "severity_number >= 13"  # WARN and above
        rate: 1.0  # Always keep
      - condition: "stream == 'access-logs' AND attributes['status_code'] < 400"
        rate: 0.1  # 10% of successful access logs

  # Tail-based sampling for traces (decision made after trace completes)
  traces:
    strategy: tail_based
    decision_wait: 30s
    policies:
      - name: errors
        type: status_code
        status_code: ERROR
        rate: 1.0
      - name: slow
        type: latency
        threshold_ms: 2000
        rate: 1.0
      - name: default
        type: probabilistic
        rate: 0.1

  # Metrics are never sampled (always keep all)
  metrics:
    default_rate: 1.0
```

**Stage 7: Routing**
```yaml
routing:
  rules:
    - match: "signal_type == 'logs'"
      destination: "nats://rayolly.ingest.logs.{tenant_id}"
    - match: "signal_type == 'metrics'"
      destination: "nats://rayolly.ingest.metrics.{tenant_id}"
    - match: "signal_type == 'traces'"
      destination: "nats://rayolly.ingest.traces.{tenant_id}"
    - match: "parse_error == true"
      destination: "nats://rayolly.dlq.{tenant_id}"
```

---

## 6. Schema Management

### 6.1 Strategy: Schema-on-Read with Soft Validation

RayOlly follows a **schema-on-read** approach:
- Accept any valid JSON/OTLP payload without strict schema enforcement
- Dynamically detect new fields and their types
- Apply schema validation only for known fields (timestamps, severity, etc.)
- Store raw data; apply structure at query time

### 6.2 Dynamic Field Detection

```python
class SchemaDetector:
    """Detects field types from incoming data and maintains schema registry."""

    TYPE_PRIORITY = {
        'bool': 1,
        'int64': 2,
        'float64': 3,
        'string': 4,  # Fallback — always compatible
    }

    async def detect_and_register(self, tenant_id: str, stream: str, record: dict):
        for field_name, value in flatten(record):
            detected_type = self.infer_type(value)
            existing_type = await self.schema_registry.get(tenant_id, stream, field_name)

            if existing_type is None:
                await self.schema_registry.register(tenant_id, stream, field_name, detected_type)
            elif existing_type != detected_type:
                # Type conflict resolution: widen to string
                if self.TYPE_PRIORITY[detected_type] > self.TYPE_PRIORITY[existing_type]:
                    await self.schema_registry.update(tenant_id, stream, field_name, 'string')
                    await self.emit_warning(f"Type conflict for {field_name}: {existing_type} vs {detected_type}")
```

### 6.3 OTEL → Internal Model Mapping

| OTEL Log Field | Internal Field | ClickHouse Column |
|----------------|---------------|-------------------|
| `timeUnixNano` | `timestamp` | `DateTime64(9, 'UTC')` |
| `observedTimeUnixNano` | `observed_timestamp` | `DateTime64(9, 'UTC')` |
| `severityNumber` | `severity_number` | `UInt8` |
| `severityText` | `severity_text` | `LowCardinality(String)` |
| `body.stringValue` | `body` | `String` |
| `resource.attributes` | `resource_*` | Denormalized + `Map(String, String)` |
| `attributes` | `attributes` | `Map(String, String)` |
| `traceId` | `trace_id` | `FixedString(32)` |
| `spanId` | `span_id` | `FixedString(16)` |

---

## 7. Backpressure & Flow Control

### 7.1 Strategy

```
Client → Gateway → NATS → Writers
  ↑                  │
  │    Backpressure   │
  └──────────────────┘

When NATS queue depth exceeds threshold:
1. Gateway returns HTTP 429 (Too Many Requests) with Retry-After header
2. gRPC returns RESOURCE_EXHAUSTED status
3. Client SDK / Collector retries with exponential backoff
4. If queue continues to grow, enable adaptive sampling (reduce ingestion rate)
5. Dead letter queue for data that cannot be processed
```

### 7.2 Configuration

```yaml
backpressure:
  nats_queue_depth_warning: 100000    # Start logging warnings
  nats_queue_depth_critical: 500000   # Start returning 429
  nats_queue_depth_emergency: 1000000 # Enable adaptive sampling
  adaptive_sampling_rate: 0.5         # Keep 50% when in emergency mode
  retry_after_seconds: 30
  client_retry:
    initial_interval: 1s
    max_interval: 60s
    multiplier: 2
    max_elapsed_time: 300s
```

---

## 8. High Availability

### 8.1 Architecture

```
┌─────────────────────────────────────────┐
│        Load Balancer (L4, multi-AZ)     │
└────┬────────────┬────────────┬──────────┘
     │            │            │
┌────▼────┐ ┌────▼────┐ ┌────▼────┐
│Ingester │ │Ingester │ │Ingester │   Stateless pods
│  AZ-1a  │ │  AZ-1b  │ │  AZ-1c  │   Min 3 replicas
└────┬────┘ └────┬────┘ └────┬────┘
     │            │            │
┌────▼────────────▼────────────▼──────┐
│         NATS JetStream Cluster       │
│     (3 nodes, cross-AZ replicated)   │
└─────────────────────────────────────┘
```

- **Stateless ingesters**: Any node can handle any request; no session affinity needed
- **NATS JetStream**: Provides durable message delivery with at-least-once guarantees
- **Health checks**: `/healthz` (liveness), `/readyz` (readiness) endpoints
- **Graceful shutdown**: Drain in-flight requests before terminating (30s grace period)
- **Rolling updates**: Zero-downtime deployment via Kubernetes rolling update strategy

### 8.2 Delivery Guarantees

| Signal | Guarantee | Mechanism |
|--------|-----------|-----------|
| Logs | At-least-once | NATS JetStream acknowledgment |
| Metrics | Effectively exactly-once | Dedup by metric name + labels + timestamp in ClickHouse ReplacingMergeTree |
| Traces | At-least-once | NATS JetStream + span dedup by span_id |

---

## 9. Multi-Tenancy

### 9.1 Tenant Identification

```python
async def identify_tenant(request) -> str:
    """Extract tenant ID from request, in priority order."""
    # 1. Explicit header
    tenant = request.headers.get("X-RayOlly-Tenant")
    if tenant:
        return tenant

    # 2. From API key lookup
    api_key = extract_api_key(request)
    if api_key:
        return await api_key_service.get_tenant(api_key)

    # 3. From JWT claims
    token = extract_bearer_token(request)
    if token:
        claims = verify_jwt(token)
        return claims.get("tenant_id")

    raise AuthenticationError("Unable to identify tenant")
```

### 9.2 Per-Tenant Rate Limits

| Tier | Ingestion Rate | Daily Volume | Streams | Fields/Stream |
|------|---------------|--------------|---------|---------------|
| Free | 1K events/sec | 1 GB/day | 10 | 100 |
| Pro | 50K events/sec | 100 GB/day | 100 | 500 |
| Enterprise | 1M events/sec | Unlimited | Unlimited | 1,000 |
| Custom | Configurable | Configurable | Configurable | Configurable |

### 9.3 Rate Limiting Implementation

```python
class TenantRateLimiter:
    """Token bucket rate limiter backed by Redis."""

    async def check(self, tenant_id: str, event_count: int) -> bool:
        key = f"ratelimit:{tenant_id}"
        quota = await self.get_quota(tenant_id)

        # Redis token bucket via Lua script (atomic)
        allowed = await self.redis.eval(
            TOKEN_BUCKET_SCRIPT,
            keys=[key],
            args=[quota.rate, quota.burst, event_count, time.time()]
        )
        if not allowed:
            await self.metrics.increment("ingestion.rate_limited", tags={"tenant": tenant_id})
            raise RateLimitExceeded(
                retry_after=self.calculate_retry_after(tenant_id)
            )
```

---

## 10. Security

### 10.1 Transport Security

| Layer | Protection |
|-------|-----------|
| TLS termination | TLS 1.3 with strong cipher suites at load balancer |
| Internal transport | mTLS between ingestion nodes and NATS |
| Compression | zstd/gzip for payload compression |
| Payload validation | Max size 10MB, max fields 500, max nested depth 10 |

### 10.2 Authentication Methods

| Method | Use Case | Header |
|--------|---------|--------|
| API Key | Programmatic ingestion | `Authorization: Bearer <key>` or `X-RayOlly-API-Key: <key>` |
| Ingest Token | Collector agents | `Authorization: Bearer <ingest-token>` |
| Splunk HEC Token | Splunk migration | `Authorization: Splunk <hec-token>` |
| mTLS Client Cert | High-security environments | Client certificate |

### 10.3 IP Allowlisting

```yaml
# Per-tenant IP allowlist
security:
  ip_allowlist:
    enabled: true
    lists:
      - tenant_id: "acme-corp"
        cidrs:
          - "10.0.0.0/8"
          - "172.16.0.0/12"
          - "203.0.113.0/24"
```

---

## 11. Monitoring & Self-Observability

### 11.1 Ingestion Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `rayolly_ingestion_events_total` | Counter | tenant, protocol, signal | Total events ingested |
| `rayolly_ingestion_bytes_total` | Counter | tenant, protocol, signal | Total bytes ingested |
| `rayolly_ingestion_latency_seconds` | Histogram | protocol, stage | Processing latency by stage |
| `rayolly_ingestion_errors_total` | Counter | tenant, protocol, error_type | Ingestion errors |
| `rayolly_ingestion_rate_limited_total` | Counter | tenant | Rate limit rejections |
| `rayolly_ingestion_queue_depth` | Gauge | subject | NATS queue depth |
| `rayolly_ingestion_active_connections` | Gauge | protocol | Active client connections |
| `rayolly_collector_agent_count` | Gauge | tenant, version | Connected collector agents |
| `rayolly_pii_redactions_total` | Counter | tenant, detector | PII fields redacted |
| `rayolly_dlq_messages_total` | Counter | tenant, reason | Dead letter queue entries |

### 11.2 Health Endpoints

```
GET /healthz          → 200 OK (liveness)
GET /readyz           → 200 OK (readiness — checks NATS connectivity)
GET /metrics          → Prometheus metrics endpoint
GET /api/v1/status    → Detailed ingestion pipeline status
```

---

## 12. API Specifications

### 12.1 Ingestion APIs

```
# OTLP gRPC (primary)
grpc://ingest.rayolly.io:4317
  - opentelemetry.proto.collector.logs.v1.LogsService/Export
  - opentelemetry.proto.collector.metrics.v1.MetricsService/Export
  - opentelemetry.proto.collector.trace.v1.TraceService/Export

# OTLP HTTP
POST /v1/logs
POST /v1/metrics
POST /v1/traces

# Custom JSON
POST /api/v1/logs/ingest
POST /api/v1/metrics/ingest
POST /api/v1/events/ingest

# Compatibility
POST /api/v1/prometheus/write          (Prometheus Remote Write)
POST /services/collector/event          (Splunk HEC)
POST /_bulk                             (Elasticsearch Bulk)
POST /loki/api/v1/push                  (Loki)
POST /api/v2/series                     (Datadog metrics compat)
POST /api/v2/logs                       (Datadog logs compat)
```

### 12.2 Pipeline Management API

```
# Pipeline configuration CRUD
GET    /api/v1/pipelines                     # List all pipelines
POST   /api/v1/pipelines                     # Create pipeline
GET    /api/v1/pipelines/{id}                # Get pipeline
PUT    /api/v1/pipelines/{id}                # Update pipeline
DELETE /api/v1/pipelines/{id}                # Delete pipeline
POST   /api/v1/pipelines/{id}/test           # Test pipeline with sample data

# Schema management
GET    /api/v1/schemas/{stream}              # Get stream schema
GET    /api/v1/schemas/{stream}/fields       # List detected fields
PUT    /api/v1/schemas/{stream}/fields/{name} # Override field type

# Agent management
GET    /api/v1/collectors                    # List connected collectors
GET    /api/v1/collectors/{id}               # Get collector status
PUT    /api/v1/collectors/{id}/config        # Push config to collector
POST   /api/v1/collectors/{id}/restart       # Restart collector
```

---

## 13. Migration Support

### 13.1 Migration Paths

| From | Strategy | Estimated Time |
|------|----------|---------------|
| **Datadog** | 1. Point Datadog Agent to also send to RayOlly (dual-write). 2. Replicate dashboards/alerts. 3. Cut over. | 1-4 weeks |
| **Splunk** | 1. Add RayOlly as HEC target. 2. Convert SPL saved searches to RayQL. 3. Migrate dashboards. 4. Cut over. | 2-6 weeks |
| **ELK** | 1. Add RayOlly output to Logstash/Fluent Bit. 2. Import Kibana dashboards. 3. Migrate alerts. 4. Cut over. | 1-3 weeks |
| **Prometheus** | 1. Add remote_write to RayOlly. 2. Verify PromQL compatibility. 3. Migrate Grafana dashboards. 4. Cut over. | 1-2 weeks |

### 13.2 Historical Data Import

```bash
# Import historical data from various sources
rayolly-cli import logs \
  --source splunk \
  --splunk-url https://splunk.example.com:8089 \
  --splunk-token "..." \
  --index main \
  --time-range "2026-01-01,2026-03-01" \
  --stream imported-splunk-logs

rayolly-cli import metrics \
  --source prometheus \
  --prometheus-url http://prometheus:9090 \
  --match '{__name__=~".+"}' \
  --time-range "2026-01-01,2026-03-01"
```

---

## 14. Performance Requirements

| Metric | Target | Stretch Goal |
|--------|--------|-------------|
| Ingestion throughput per node | 1M events/sec | 2M events/sec |
| Cluster throughput (10 nodes) | 10M events/sec | 20M events/sec |
| Processing latency (receipt to NATS) | < 50ms p99 | < 20ms p99 |
| End-to-end latency (receipt to queryable) | < 5s p99 | < 2s p99 |
| Protocol adapter overhead | < 5ms per event | < 2ms |
| Enrichment overhead | < 10ms per batch | < 5ms |
| Max concurrent connections | 10K per node | 50K per node |
| Max payload size | 10MB | 50MB |
| Compression ratio (wire) | 5:1 (zstd) | 10:1 |

---

## 15. Technical Design

### 15.1 Technology Stack

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| HTTP server | Python 3.12+ / FastAPI (uvicorn) | Async ASGI, excellent OpenAPI support |
| gRPC server | grpcio-tools + grpclib | OTLP native protocol support |
| Hot path parsing | Rust via PyO3 | 10-100x faster than pure Python for grok/regex |
| Message bus | NATS JetStream | Lightweight, persistent, built-in clustering |
| Rate limiter | Redis + Lua scripts | Atomic token bucket, shared state across nodes |
| Schema registry | PostgreSQL | ACID guarantees for schema evolution |
| GeoIP | MaxMind GeoLite2 | Industry standard, monthly updates |
| Container | Distroless Python base | Minimal attack surface |

### 15.2 FastAPI Ingestion Server

```python
from fastapi import FastAPI, Request, Depends
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: connect to NATS, Redis, load schemas
    await nats_client.connect()
    await redis_client.connect()
    await schema_registry.load()
    yield
    # Shutdown: drain connections
    await nats_client.drain()

app = FastAPI(title="RayOlly Ingestion API", lifespan=lifespan)

@app.post("/v1/logs")
async def ingest_otlp_logs(
    request: Request,
    tenant: str = Depends(identify_tenant),
    _: None = Depends(rate_limit),
):
    body = await request.body()
    export_request = ExportLogsServiceRequest()
    export_request.ParseFromString(body)

    processed = await pipeline.process_logs(tenant, export_request.resource_logs)
    await nats_client.publish(f"rayolly.ingest.logs.{tenant}", processed)

    return ExportLogsServiceResponse()
```

---

## 16. Success Metrics

| Metric | Target (GA) | Target (12mo) |
|--------|------------|---------------|
| Ingestion uptime | 99.95% | 99.99% |
| Data loss rate | < 0.01% | < 0.001% |
| Mean latency (receipt to queryable) | < 5s | < 2s |
| Protocol coverage | 8 protocols | 12 protocols |
| Collector agent deployments | 1,000 | 50,000 |
| Migration success rate | 90% | 98% |
| PII detection accuracy | 95% | 99% |

---

## 17. Dependencies & Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Python throughput limits | Medium | High | Rust extensions via PyO3 for hot paths; uvloop; multiple worker processes |
| NATS JetStream scaling | Low | High | NATS is proven at 10M+ msg/sec; horizontal scaling |
| Protocol compatibility gaps | High | Medium | Comprehensive integration tests against real Splunk/DD/ES payloads |
| High cardinality from dynamic fields | High | Medium | Field count limits; cardinality warnings; auto-drop above threshold |
| PII detection false positives | Medium | Medium | Configurable sensitivity; allowlists; audit trail for review |
| Collector agent deployment friction | Medium | Medium | One-liner install; auto-update; central config management |

---

*End of PRD-01: Data Ingestion & OpenTelemetry Pipeline*
