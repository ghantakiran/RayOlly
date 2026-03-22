# PRD-08: Distributed Tracing & Application Performance Monitoring (APM)

**Product**: RayOlly — AI-Native Observability Platform
**Version**: 1.0
**Date**: 2026-03-19
**Status**: Draft
**Parent**: PRD-00 Platform Vision & Architecture
**Dependencies**: PRD-01 (Ingestion), PRD-02 (Storage), PRD-03 (Query Engine), PRD-06 (Logs), PRD-07 (Metrics)

---

## 1. Executive Summary

The Distributed Tracing & APM module is the third observability pillar in RayOlly, providing end-to-end request tracing, service dependency mapping, latency analysis, error tracking, and code-level profiling. It is designed to directly compete with **Dynatrace PurePath**, **Datadog APM**, **Splunk APM**, **New Relic APM**, and open-source solutions like **Jaeger** and **Grafana Tempo**.

Unlike legacy APM tools that require proprietary agents and opaque auto-instrumentation, RayOlly APM is **fully OpenTelemetry-native**, ingesting OTLP spans natively while also accepting Jaeger and Zipkin formats for zero-friction migration. Unlike Jaeger/Tempo that provide tracing without deep APM intelligence, RayOlly combines distributed tracing with AI-powered root cause analysis, continuous profiling, and automatic service topology discovery.

**Key Differentiators**:

| Capability | Datadog APM | Dynatrace PurePath | Jaeger / Tempo | **RayOlly APM** |
|---|---|---|---|---|
| OpenTelemetry native | Partial | Partial | Full | **Full** |
| Proprietary agent required | Yes | Yes (OneAgent) | No | **No** |
| Auto-instrumentation | Agent-based | OneAgent | Manual | **OTEL + AI-enhanced** |
| Tail-based sampling | Yes | Yes | No (head only) | **Yes, AI-driven** |
| Service map / topology | Yes | SmartScape | Basic | **Auto-discovered + AI** |
| Profiling integration | Separate product | Built-in | No | **Built-in, trace-correlated** |
| AI root cause analysis | Limited | Davis AI | No | **Full AI agent** |
| Log/metric correlation | Yes (separate billing) | Yes | No | **Unified, no extra cost** |
| Cost per span (at scale) | ~$1.70/M spans | License-based | Free (self-hosted) | **$0.50/M spans** |

**North Star Metric**: Mean time from trace collection to actionable root cause identification < 30 seconds for P1 incidents.

---

## 2. Goals & Non-Goals

### 2.1 Goals

- Ingest, store, and query **1 billion+ spans/day per tenant** with sub-second search
- Full OpenTelemetry OTLP/gRPC and OTLP/HTTP ingestion with Jaeger and Zipkin compatibility
- Automatic service topology discovery with real-time health indicators
- Trace search with < 500ms p95 latency for filtered queries across 7-day windows
- Latency decomposition showing which service/operation contributes most to total request time
- Error tracking with automatic classification, grouping, and regression detection
- Database and external call monitoring with query-level performance analytics
- Continuous profiling (CPU, memory, allocation) correlated to individual traces
- Tail-based sampling with configurable rules guaranteeing capture of error/slow traces
- AI-powered root cause identification, anomaly detection, and deployment impact analysis
- Seamless correlation: trace -> logs, trace -> metrics, trace -> profiles in a single click
- Migration tooling for Jaeger, Zipkin, Datadog, and Dynatrace environments

### 2.2 Non-Goals

- Synthetic monitoring / uptime checks (future PRD)
- Browser/mobile RUM (Real User Monitoring) — planned for PRD-12
- Network-level packet capture or flow monitoring
- Replace specialized database performance tools (e.g., pganalyze, Percona)
- Code-level debugging or step-through execution
- Log ingestion and storage (covered in PRD-06)

---

## 3. Trace Data Model

### 3.1 OpenTelemetry Span Model

RayOlly adopts the OpenTelemetry span specification as its canonical data model. Every span contains:

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Span Structure                                │
│                                                                      │
│  trace_id        : 128-bit globally unique trace identifier          │
│  span_id         : 64-bit unique span identifier                     │
│  parent_span_id  : 64-bit parent span (empty for root spans)        │
│  trace_state     : W3C trace state propagation header                │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ Identity                                                      │   │
│  │  service.name       : "order-service"                         │   │
│  │  span.name          : "POST /api/v1/orders"                   │   │
│  │  span.kind          : SERVER | CLIENT | PRODUCER | CONSUMER   │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ Timing                                                        │   │
│  │  start_time         : 2026-03-19T14:22:01.123456789Z          │   │
│  │  end_time           : 2026-03-19T14:22:01.456789012Z          │   │
│  │  duration_ns        : 333332223                                │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ Status                                                        │   │
│  │  status_code        : OK | ERROR | UNSET                      │   │
│  │  status_message     : "Internal Server Error"                 │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ Attributes (key-value pairs)                                  │   │
│  │  http.method         : "POST"                                 │   │
│  │  http.url            : "/api/v1/orders"                       │   │
│  │  http.status_code    : 500                                    │   │
│  │  db.system           : "postgresql"                           │   │
│  │  db.statement        : "INSERT INTO orders ..."               │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ Events (timestamped annotations)                              │   │
│  │  { time: T1, name: "exception", attributes: {                 │   │
│  │      exception.type: "NullPointerException",                  │   │
│  │      exception.message: "...",                                │   │
│  │      exception.stacktrace: "..."                              │   │
│  │  }}                                                           │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ Links (causal relationships to other spans)                   │   │
│  │  [{ trace_id: "...", span_id: "...", attributes: {...} }]     │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ Resource Attributes (process/host metadata)                   │   │
│  │  service.namespace   : "production"                           │   │
│  │  service.version     : "2.4.1"                                │   │
│  │  deployment.env      : "prod-us-east-1"                       │   │
│  │  host.name           : "ip-10-0-1-42"                         │   │
│  │  k8s.pod.name        : "order-service-7b4d9f-x2k4q"          │   │
│  │  k8s.namespace.name  : "commerce"                             │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 Trace / Span / Parent Relationships

A **trace** is a tree of spans representing a single end-to-end request:

```
Trace: abc123def456...
│
├── [Root Span] API Gateway — POST /api/v1/orders (350ms)
│   ├── [Child] order-service — processOrder (300ms)
│   │   ├── [Child] order-service — validatePayment (50ms)
│   │   │   └── [Child] payment-service — POST /validate (45ms)
│   │   │       └── [Child] payment-service — Stripe API call (30ms)
│   │   ├── [Child] order-service — INSERT orders (20ms)
│   │   │   └── [Child] PostgreSQL — INSERT INTO orders... (18ms)
│   │   └── [Child] order-service — publishEvent (10ms)
│   │       └── [Child] Kafka — produce order.created (8ms)
│   └── [Child] API Gateway — response serialization (5ms)
```

### 3.3 Span Kind Semantics

| Span Kind | Description | Example |
|-----------|------------|---------|
| `SERVER` | Handles an incoming request | HTTP handler, gRPC server method |
| `CLIENT` | Makes an outgoing request | HTTP client call, DB query |
| `PRODUCER` | Sends a message asynchronously | Kafka produce, SQS send |
| `CONSUMER` | Receives a message asynchronously | Kafka consume, SQS receive |
| `INTERNAL` | Internal operation, no remote call | Business logic, in-memory cache |

---

## 4. Trace Collection

### 4.1 Ingestion Protocols

| Protocol | Endpoint | Format | Priority |
|----------|---------|--------|----------|
| **OTLP/gRPC** | `grpc://ingest.rayolly.io:4317` | Protobuf | Primary |
| **OTLP/HTTP** | `https://ingest.rayolly.io/v1/traces` | Protobuf or JSON | Primary |
| **Jaeger Thrift** | `https://ingest.rayolly.io/api/traces` (Jaeger collector) | Thrift | Migration compat |
| **Jaeger gRPC** | `grpc://ingest.rayolly.io:14250` | Protobuf | Migration compat |
| **Zipkin v2** | `https://ingest.rayolly.io/api/v2/spans` | JSON | Migration compat |
| **Datadog APM** | `https://ingest.rayolly.io/v0.4/traces` | MessagePack | Migration compat |

### 4.2 Auto-Instrumentation Support

RayOlly provides zero-code auto-instrumentation via OpenTelemetry distributions:

| Language | Mechanism | Frameworks Covered |
|----------|----------|-------------------|
| **Java** | OTEL Java Agent (javaagent JAR) | Spring Boot, Micronaut, Quarkus, JDBC, Hibernate, Kafka, gRPC, Netty |
| **Python** | OTEL Python auto-instrumentation | Django, Flask, FastAPI, SQLAlchemy, psycopg2, requests, aiohttp, Celery |
| **Go** | OTEL Go instrumentation libraries | net/http, gRPC, database/sql, Gin, Echo, Fiber |
| **Node.js** | OTEL Node.js auto-instrumentation | Express, Fastify, NestJS, pg, mysql2, Redis, GraphQL |
| **.NET** | OTEL .NET auto-instrumentation | ASP.NET Core, Entity Framework, HttpClient, gRPC, SQL Client |
| **Rust** | `tracing` crate + OTEL exporter | Actix-web, Axum, Tonic, sqlx, reqwest |

### 4.3 RayOlly OTEL Collector Distribution

RayOlly ships a custom OpenTelemetry Collector distribution (`rayolly-collector`) with:

- **Receivers**: OTLP, Jaeger, Zipkin, Datadog, Prometheus (for metric correlation)
- **Processors**: Batch, tail-sampling, attribute enrichment, K8s metadata, span-to-metric
- **Exporters**: RayOlly OTLP (optimized), debug
- **Extensions**: Health check, pprof, zpages, bearer token auth

```yaml
# rayolly-collector-config.yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: "0.0.0.0:4317"
      http:
        endpoint: "0.0.0.0:4318"
  jaeger:
    protocols:
      thrift_http:
        endpoint: "0.0.0.0:14268"
      grpc:
        endpoint: "0.0.0.0:14250"
  zipkin:
    endpoint: "0.0.0.0:9411"

processors:
  batch:
    timeout: 5s
    send_batch_size: 8192
  tail_sampling:
    decision_wait: 10s
    policies:
      - name: error-traces
        type: status_code
        status_code: { status_codes: [ERROR] }
      - name: slow-traces
        type: latency
        latency: { threshold_ms: 2000 }
      - name: probabilistic-baseline
        type: probabilistic
        probabilistic: { sampling_percentage: 10 }
  k8sattributes:
    extract:
      metadata:
        - k8s.pod.name
        - k8s.namespace.name
        - k8s.deployment.name
        - k8s.node.name

exporters:
  rayolly:
    endpoint: "grpc://ingest.rayolly.io:4317"
    headers:
      Authorization: "Bearer ${RAYOLLY_API_KEY}"
    compression: zstd
    retry_on_failure:
      enabled: true
      max_elapsed_time: 300s

service:
  pipelines:
    traces:
      receivers: [otlp, jaeger, zipkin]
      processors: [k8sattributes, tail_sampling, batch]
      exporters: [rayolly]
```

---

## 5. Service Map & Topology

### 5.1 Overview

RayOlly auto-discovers service dependencies by analyzing span relationships (client/server pairs, producer/consumer pairs) and constructs a real-time service topology graph comparable to Dynatrace SmartScape. No manual configuration is required.

### 5.2 Dependency Detection

| Dependency Type | Detection Method | Attributes Used |
|----------------|-----------------|-----------------|
| **HTTP** | Client span -> Server span matching | `http.url`, `http.host`, `server.address` |
| **gRPC** | Client span -> Server span matching | `rpc.system`, `rpc.service`, `rpc.method` |
| **Database** | Client spans with `db.*` attributes | `db.system`, `db.name`, `db.connection_string` |
| **Message Queue** | Producer -> Consumer span links | `messaging.system`, `messaging.destination` |
| **Cache** | Client spans with cache attributes | `db.system` = redis/memcached |
| **External API** | Client spans to unknown services | `http.url` domain not in service registry |

### 5.3 Service Map Data Model

```sql
-- Materialized view for service edges (updated every 60s)
CREATE MATERIALIZED VIEW traces.service_edges_mv
ENGINE = AggregatingMergeTree()
ORDER BY (tenant_id, time_bucket, source_service, target_service, edge_type)
AS SELECT
    tenant_id,
    toStartOfMinute(timestamp) AS time_bucket,
    source_service,
    target_service,
    edge_type,                          -- 'http', 'grpc', 'database', 'messaging', 'cache'
    countState()                  AS request_count,
    avgState(duration_ms)         AS avg_latency_ms,
    quantileState(0.99)(duration_ms) AS p99_latency_ms,
    sumState(is_error)            AS error_count
FROM traces.service_edges_raw
GROUP BY tenant_id, time_bucket, source_service, target_service, edge_type;
```

### 5.4 Health Indicators Per Service

Each node on the service map displays:

| Indicator | Calculation | Thresholds |
|-----------|------------|------------|
| **Request rate** | Requests/sec over window | Informational |
| **Error rate** | Errors / total requests * 100 | Green < 1%, Yellow < 5%, Red >= 5% |
| **P99 latency** | 99th percentile response time | Green < SLO, Yellow < 2x SLO, Red >= 2x SLO |
| **Saturation** | CPU/memory utilization (from metrics) | Green < 70%, Yellow < 85%, Red >= 85% |
| **Change indicator** | Deployment detected in last 30 min | Blue dot overlay |

### 5.5 Service Map UI (ASCII Art Mockup)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  SERVICE MAP                          Time: Last 15 min    Environment: prod    │
│  ─────────────────────────────────────────────────────────────────────────────  │
│                                                                                 │
│                           ┌─────────────┐                                       │
│                           │   NGINX     │                                       │
│               ┌──────────▶│  Ingress    │◀──────────┐                           │
│               │           │ 1.2k rps    │           │                           │
│               │           │ ● 0.1% err  │           │                           │
│               │           └──────┬──────┘           │                           │
│               │                  │                   │                           │
│               │        ┌─────────┼─────────┐         │                           │
│               │        ▼         ▼         ▼         │                           │
│          ┌────┴─────┐ ┌──────────┐ ┌──────────┐     │                           │
│          │  Web     │ │  Order   │ │  User    │     │                           │
│          │  App     │ │  Service │ │  Service │     │                           │
│          │ 800 rps  │ │ 350 rps  │ │ 200 rps  │     │                           │
│          │ ● 0.2%   │ │ ◉ 4.8%  │ │ ● 0.1%   │     │                           │
│          │ 45ms p99 │ │ 320ms   │ │ 25ms p99 │     │                           │
│          └────┬─────┘ └───┬──┬──┘ └─────┬────┘     │                           │
│               │           │  │          │           │                           │
│               │     ┌─────┘  └────┐     │           │                           │
│               │     ▼             ▼     │           │                           │
│               │ ┌──────────┐ ┌────┴─────┐           │                           │
│               │ │ Payment  │ │ Inventory│           │                           │
│               │ │ Service  │ │ Service  │           │                           │
│               │ │ 150 rps  │ │ 100 rps  │           │                           │
│               │ │ ● 0.3%   │ │ ● 0.0%   │           │                           │
│               │ └────┬─────┘ └─────┬────┘           │                           │
│               │      │             │                 │                           │
│        ┌──────┴──┐ ┌─┴───────┐ ┌──┴────────┐ ┌─────┴────┐                     │
│        │ Redis   │ │ Stripe  │ │PostgreSQL │ │  Kafka   │                     │
│        │ Cache   │ │ (ext)   │ │  Primary  │ │ Cluster  │                     │
│        │ 2.1k    │ │ 150 rps │ │ 800 qps   │ │ 500 msg/s│                     │
│        │ 0.8ms   │ │ 180ms   │ │ 12ms avg  │ │ 3ms avg  │                     │
│        └─────────┘ └─────────┘ └───────────┘ └──────────┘                     │
│                                                                                 │
│  Legend: ● Healthy  ◉ Degraded  ◈ Critical  ▲ Deployment detected              │
│  ─────────────────────────────────────────────────────────────────────────────  │
│  [Auto-Layout] [Group by Namespace] [Filter by Service] [Time Range ▾]         │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 5.6 Traffic Flow Visualization

The service map supports animated traffic flow:
- **Line thickness** proportional to request volume between services
- **Line color** reflects error rate (green -> yellow -> red gradient)
- **Animation speed** reflects average latency (faster animation = lower latency)
- **Dotted lines** for asynchronous messaging (Kafka, RabbitMQ, SQS)
- **Solid lines** for synchronous calls (HTTP, gRPC)

---

## 6. Trace Search & Exploration

### 6.1 Search Capabilities

Traces are searchable by any combination of the following:

| Filter | Operators | Example |
|--------|-----------|---------|
| **Service** | `=`, `!=`, `in` | `service.name = "order-service"` |
| **Operation** | `=`, `!=`, `~` (regex) | `span.name ~ "POST /api/.*"` |
| **Duration** | `>`, `<`, `>=`, `<=`, `between` | `duration > 2s` |
| **Status** | `=` | `status = ERROR` |
| **HTTP status** | `=`, `>`, `<` | `http.status_code >= 500` |
| **Tag/Attribute** | `=`, `!=`, `exists`, `~` | `user.id = "u-12345"` |
| **Trace ID** | `=` | `trace_id = "abc123..."` |
| **Time range** | `between` | `timestamp between now-1h and now` |
| **Min spans** | `>=` | `span_count >= 50` |
| **Has error** | boolean | `has_error = true` |

### 6.2 Trace Timeline Visualization (Waterfall View)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  TRACE DETAIL: abc123def456789                          Duration: 352ms      │
│  Service: order-service  |  Operation: POST /api/v1/orders  |  Status: ERROR│
│  ──────────────────────────────────────────────────────────────────────────  │
│                                                                              │
│  Time:  0ms    50ms   100ms   150ms   200ms   250ms   300ms   350ms         │
│         │       │       │       │       │       │       │       │            │
│                                                                              │
│  API Gateway                                                                 │
│  POST /api/v1/orders                                                         │
│  ██████████████████████████████████████████████████████████████████  352ms   │
│                                                                              │
│    order-service                                                             │
│    processOrder                                                              │
│    ·██████████████████████████████████████████████████████████████  305ms   │
│                                                                              │
│      order-service                                                           │
│      validatePayment                                                         │
│      ·███████████████                                               52ms    │
│                                                                              │
│        payment-service                                                       │
│        POST /validate                                                        │
│        ··█████████████                                              47ms    │
│                                                                              │
│          payment-service                                                     │
│          Stripe API call                                                     │
│          ···████████                                                32ms    │
│                                                                              │
│      order-service                                                           │
│      INSERT orders                                                           │
│               ·████                                                 22ms    │
│                                                                              │
│        PostgreSQL                                                            │
│        INSERT INTO orders...                                                 │
│               ··███                                                 18ms    │
│                                                                              │
│      order-service                                                           │
│      checkInventory                               ← ERROR                    │
│                    ·█████████████████████████████████████████████   195ms ❌│
│                                                                              │
│        inventory-service                                                     │
│        GET /api/v1/stock                          ← 500                      │
│                    ··████████████████████████████████████████████   190ms ❌│
│                                                                              │
│          PostgreSQL                                                          │
│          SELECT stock FROM inventory...           ← TIMEOUT                  │
│                    ···██████████████████████████████████████████    185ms ❌│
│                                                                              │
│  ──────────────────────────────────────────────────────────────────────────  │
│  [Span Details]  [Logs (12)]  [Related Metrics]  [Profiles]  [Compare]      │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 6.3 Span Detail View

Clicking on any span shows:

- **Attributes**: All key-value pairs (HTTP headers, DB queries, custom tags)
- **Events**: Exception events with full stack traces
- **Resource**: Host, pod, deployment, service version metadata
- **Logs**: All logs emitted during this span's execution (correlated by trace_id + span_id)
- **Linked spans**: Causal links to other traces (e.g., async follow-up operations)
- **Process info**: PID, runtime version, SDK version

### 6.4 Trace Comparison (Before/After Deployment)

Users can select two traces of the same operation and compare them side-by-side:

- **Duration diff** per span (which spans got slower/faster)
- **New spans** added or removed
- **Attribute diff** (e.g., service version changed)
- **Error diff** (new errors introduced)

---

## 7. Latency Analysis

### 7.1 Latency Breakdown by Service

```
┌──────────────────────────────────────────────────────────────────────────┐
│  LATENCY ANALYSIS — POST /api/v1/orders                                  │
│  Time Range: Last 1 hour          Environment: prod-us-east-1            │
│  ──────────────────────────────────────────────────────────────────────  │
│                                                                          │
│  Overall Latency:  P50: 120ms   P90: 280ms   P95: 350ms   P99: 890ms   │
│                                                                          │
│  Breakdown by Service:                                                   │
│                                                                          │
│  Service              P50     P90     P99     % of Total (P50)           │
│  ─────────────────────────────────────────────────────────────           │
│  order-service        35ms    80ms    180ms   ████████████░░ 29%        │
│  inventory-service    25ms    60ms    350ms   ████████░░░░░░ 21%        │
│  payment-service      30ms    55ms    120ms   ██████████░░░░ 25%        │
│  PostgreSQL           20ms    45ms    200ms   ██████░░░░░░░░ 17%        │
│  Redis                 2ms     5ms     15ms   █░░░░░░░░░░░░░  2%        │
│  Kafka                 3ms     8ms     25ms   █░░░░░░░░░░░░░  3%        │
│  Network/other         5ms    27ms     -      ██░░░░░░░░░░░░  4%        │
│                                                                          │
│  ──────────────────────────────────────────────────────────────────────  │
│  Latency Histogram (P99 distribution):                                   │
│                                                                          │
│     ▂▃▅██▇▅▃▂▁                                 ▁▂▁                      │
│  ───┼──┼──┼──┼──┼──┼──┼──┼──┼──┼──┼──┼──┼──┼──┼───                    │
│   50 100 150 200 250 300 350 400 500 600 700 800 900  ms                │
│                                                                          │
│  [Time Series]  [Heatmap]  [Compare Period]  [Alert on Regression]      │
└──────────────────────────────────────────────────────────────────────────┘
```

### 7.2 Latency Heatmap

A 2D heatmap (time on x-axis, latency buckets on y-axis, color = request count) enables visual identification of latency mode shifts, bimodal distributions, and timeout cliffs.

### 7.3 Slow Trace Identification

RayOlly automatically identifies and indexes slow traces:

- **Absolute threshold**: Any trace exceeding a configured duration (default: 2s)
- **Relative threshold**: Traces exceeding 3x the P50 for that operation
- **Timeout traces**: Traces where a span duration equals a known timeout value (e.g., 30s, 60s)
- **Degradation detection**: Operations whose P99 has increased > 20% vs previous period

### 7.4 Latency Decomposition Query

```sql
-- Which service contributes most to P99 latency for a given endpoint?
SELECT
    service_name,
    quantile(0.50)(duration_ms) AS p50,
    quantile(0.90)(duration_ms) AS p90,
    quantile(0.99)(duration_ms) AS p99,
    avg(duration_ms) AS avg_ms,
    count() AS span_count,
    round(sum(duration_ms) / (SELECT sum(duration_ms) FROM traces.spans
        WHERE tenant_id = 1 AND root_service = 'api-gateway'
        AND root_operation = 'POST /api/v1/orders'
        AND timestamp >= now() - INTERVAL 1 HOUR) * 100, 1) AS pct_of_total
FROM traces.spans
WHERE
    tenant_id = 1
    AND root_service = 'api-gateway'
    AND root_operation = 'POST /api/v1/orders'
    AND timestamp >= now() - INTERVAL 1 HOUR
GROUP BY service_name
ORDER BY p99 DESC;
```

---

## 8. Error Tracking

### 8.1 Error Rate by Service/Operation

RayOlly computes error rates at multiple granularities:

- **Service-level**: Total error rate across all operations
- **Operation-level**: Error rate per endpoint/method
- **Downstream-level**: Error rate caused by a specific downstream dependency

### 8.2 Error Classification and Grouping

Errors are automatically classified and grouped:

| Classification | Method | Example |
|----------------|--------|---------|
| **Exception type** | `exception.type` attribute | `NullPointerException`, `ConnectionTimeout` |
| **HTTP status** | `http.status_code` | 500, 502, 503, 504 |
| **gRPC status** | `rpc.grpc.status_code` | UNAVAILABLE, DEADLINE_EXCEEDED |
| **Database error** | `db.error` or exception during DB span | Deadlock, timeout, constraint violation |
| **Custom** | User-defined error tags | Business logic errors |

Grouping uses a fingerprinting algorithm:
1. Normalize the stack trace (remove line numbers, memory addresses, generated class names)
2. Hash the normalized exception type + top 5 stack frames + service + operation
3. Group by fingerprint, track first seen / last seen / occurrence count

### 8.3 Stack Trace Collection

Stack traces are captured from OpenTelemetry span events with `name = "exception"`:

```json
{
  "name": "exception",
  "timestamp": "2026-03-19T14:22:01.456Z",
  "attributes": {
    "exception.type": "java.sql.SQLTransientConnectionException",
    "exception.message": "HikariPool-1 - Connection is not available, request timed out after 30000ms",
    "exception.stacktrace": "java.sql.SQLTransientConnectionException: HikariPool-1 ...\n\tat com.zaxxer.hikari.pool.HikariPool.createTimeoutException(HikariPool.java:696)\n\tat com.zaxxer.hikari.pool.HikariPool.getConnection(HikariPool.java:197)\n\tat com.example.orders.repository.OrderRepository.save(OrderRepository.java:42)\n\tat com.example.orders.service.OrderService.processOrder(OrderService.java:78)\n..."
  }
}
```

### 8.4 Error Trending and Regression Detection

- **Baseline error rate** per operation computed using a 7-day rolling window
- **Regression alert** when error rate exceeds baseline by > 2 standard deviations
- **New error detection** when a previously unseen error fingerprint appears
- **Error spike detection** using the same anomaly detection engine as metrics (PRD-07)
- **Deployment correlation**: Errors that first appear within 30 minutes of a deployment are flagged with the deployment version

### 8.5 Error Summary Table (ClickHouse)

```sql
-- Materialized view for error groups
CREATE MATERIALIZED VIEW traces.error_groups_mv
ENGINE = AggregatingMergeTree()
ORDER BY (tenant_id, error_fingerprint)
AS SELECT
    tenant_id,
    cityHash64(
        concat(service_name, ':', operation_name, ':',
               exception_type, ':', normalized_stack_top5)
    ) AS error_fingerprint,
    any(service_name)        AS service_name,
    any(operation_name)      AS operation_name,
    any(exception_type)      AS exception_type,
    any(exception_message)   AS sample_message,
    any(exception_stacktrace) AS sample_stacktrace,
    min(timestamp)           AS first_seen,
    max(timestamp)           AS last_seen,
    countState()             AS occurrence_count,
    uniqState(trace_id)      AS affected_traces
FROM traces.span_errors
GROUP BY tenant_id, error_fingerprint;
```

---

## 9. Database & External Call Monitoring

### 9.1 SQL Query Tracking

For every database span, RayOlly captures:

| Field | Source | Example |
|-------|--------|---------|
| `db.system` | Span attribute | `postgresql`, `mysql`, `mssql` |
| `db.name` | Span attribute | `orders_db` |
| `db.statement` | Span attribute | `SELECT * FROM orders WHERE user_id = $1` |
| `db.operation` | Parsed from statement | `SELECT`, `INSERT`, `UPDATE`, `DELETE` |
| Duration | Span timing | 18ms |
| Rows affected | Span attribute (if available) | 1 |

#### Query Normalization

Raw SQL is normalized to group identical query patterns:

```
-- Raw:    SELECT * FROM orders WHERE user_id = 12345 AND status = 'pending'
-- Normal: SELECT * FROM orders WHERE user_id = ? AND status = ?
```

#### Explain Plan Collection

For queries exceeding a configurable threshold (default: 100ms), RayOlly can request an explain plan:

```json
{
  "query_normalized": "SELECT * FROM orders WHERE user_id = ? AND created_at > ?",
  "avg_duration_ms": 250,
  "explain_plan": {
    "plan": "Seq Scan on orders (cost=0.00..35420.00 rows=1 width=512)",
    "recommendation": "Missing index on (user_id, created_at). Suggested: CREATE INDEX idx_orders_user_created ON orders(user_id, created_at);"
  }
}
```

### 9.2 NoSQL & Cache Call Tracking

| System | Attributes Captured | Analytics |
|--------|-------------------|-----------|
| **Redis** | Command, key pattern, response size | Top commands by latency, cache hit/miss ratio |
| **MongoDB** | Collection, operation, filter pattern | Slow queries, collection hotspots |
| **Elasticsearch** | Index, query type, result count | Slow searches, heavy aggregations |
| **DynamoDB** | Table, operation, consumed capacity | Throttled requests, hot partitions |

### 9.3 External HTTP Call Monitoring

All outbound HTTP client spans are tracked:

- **Endpoint**: Grouped by host + path pattern
- **Latency**: P50/P90/P99 per external endpoint
- **Error rate**: 4xx/5xx rates per external service
- **Throughput**: Requests per second to each external service
- **Circuit breaker detection**: Identify patterns suggesting circuit breaker trips

### 9.4 gRPC Call Monitoring

- Method-level latency and error rate
- Streaming call duration and message count
- Deadline exceeded tracking
- Metadata/header size monitoring

### 9.5 Query Performance Analytics (SQL)

```sql
-- Top 10 slowest normalized queries in the last hour
SELECT
    db_system,
    db_name,
    normalized_statement,
    count()                          AS call_count,
    avg(duration_ms)                 AS avg_ms,
    quantile(0.99)(duration_ms)      AS p99_ms,
    max(duration_ms)                 AS max_ms,
    sum(duration_ms)                 AS total_time_ms
FROM traces.spans
WHERE
    tenant_id = 1
    AND span_kind = 'CLIENT'
    AND db_system != ''
    AND timestamp >= now() - INTERVAL 1 HOUR
GROUP BY db_system, db_name, normalized_statement
ORDER BY p99_ms DESC
LIMIT 10;
```

---

## 10. Profiling Integration

### 10.1 Continuous Profiling

RayOlly integrates continuous profiling (comparable to Datadog Continuous Profiler and Pyroscope):

| Profile Type | Description | Overhead | Languages |
|-------------|------------|---------|-----------|
| **CPU** | On-CPU time per function | < 1% | Java, Go, Python, Node.js, .NET, Rust |
| **Wall clock** | Total elapsed time per function | < 1% | Java, Go, Python, Node.js |
| **Allocation** | Heap allocation rate per call site | < 2% | Java, Go, .NET |
| **Heap live** | Current heap memory per allocation site | < 1% | Java, Go, .NET |
| **Lock contention** | Time spent waiting on locks | < 1% | Java, Go |
| **Goroutine** | Goroutine count and creation rate | < 1% | Go |
| **Exception** | Exception creation rate per call site | < 1% | Java, .NET |

### 10.2 Profile-to-Trace Correlation

Each profiling sample can be correlated to an active span:

```
Trace: POST /api/v1/orders (320ms)
  └── order-service.processOrder (280ms)
        │
        ├── Profile: CPU (280ms sampled)
        │   ├── OrderService.processOrder()        12ms (4.3%)
        │   ├── PaymentClient.validate()           45ms (16.1%)
        │   ├── JsonSerializer.serialize()          28ms (10.0%)  ← hotspot
        │   ├── HikariPool.getConnection()          85ms (30.4%)  ← hotspot
        │   ├── PreparedStatement.execute()          62ms (22.1%)
        │   └── KafkaProducer.send()                18ms (6.4%)
        │
        └── Profile: Allocation (during span)
            ├── JsonSerializer.serialize()          48MB  ← hotspot
            ├── ArrayList.grow()                    12MB
            └── ByteBuffer.allocate()                8MB
```

### 10.3 Code Hotspot Identification

RayOlly's AI engine identifies code hotspots by:

1. Aggregating profiling data per operation over time
2. Detecting functions that consistently consume disproportionate resources
3. Correlating hotspots with latency regressions after deployments
4. Generating actionable recommendations (e.g., "JsonSerializer.serialize() accounts for 10% of CPU in processOrder; consider switching to a streaming serializer")

### 10.4 Flame Graph Visualization

Flame graphs are rendered interactively in the UI:

- **Standard flame graph**: Call stack depth on y-axis, time/samples on x-axis
- **Icicle graph**: Inverted flame graph (roots at top)
- **Differential flame graph**: Compares two time periods, highlights regressions in red
- **Sandwich view**: Shows both callers and callees for a selected function
- Supports zoom, search, and filtering by package/namespace

---

## 11. Tail-Based Sampling

### 11.1 Head-Based vs Tail-Based Sampling

| Aspect | Head-Based | Tail-Based |
|--------|-----------|-----------|
| **Decision point** | At trace start | After trace completes |
| **Knows trace outcome** | No | Yes |
| **Error capture guarantee** | No — may drop error traces | Yes — always keeps error traces |
| **Slow trace capture** | No — may drop slow traces | Yes — always keeps slow traces |
| **Implementation complexity** | Simple (per-span decision) | Complex (requires buffering) |
| **Resource cost** | Low | Medium (buffer memory) |
| **RayOlly approach** | Fallback only | **Primary strategy** |

### 11.2 Decision Criteria

RayOlly's tail-based sampler evaluates completed traces against an ordered policy chain:

```yaml
sampling_policies:
  # Always keep: error traces
  - name: errors
    type: status_code
    status_codes: [ERROR]
    sample_rate: 1.0              # 100% of error traces

  # Always keep: slow traces (> 2x P99 for that operation)
    - name: slow-dynamic
    type: latency_percentile
    percentile: 99
    multiplier: 2.0
    sample_rate: 1.0

  # Always keep: traces with specific tags
  - name: vip-customers
    type: attribute
    key: "customer.tier"
    values: ["enterprise", "vip"]
    sample_rate: 1.0

  # High sampling: new deployments (first 30 min)
  - name: new-deployments
    type: attribute
    key: "service.version.age_minutes"
    numeric_range: { max: 30 }
    sample_rate: 0.5              # 50% of traces from new deployments

  # Baseline: probabilistic sampling for healthy traces
  - name: baseline
    type: probabilistic
    sample_rate: 0.05             # 5% of normal traces
```

### 11.3 Sampling Architecture

```
                   ┌──────────────────┐
                   │  Application     │
                   │  (OTEL SDK)      │
                   └────────┬─────────┘
                            │ All spans sent (no head sampling)
                            ▼
                   ┌──────────────────┐
                   │  RayOlly         │
                   │  Collector       │
                   │  (Edge)          │
                   └────────┬─────────┘
                            │ Buffered spans (10s window)
                            ▼
                   ┌──────────────────┐
                   │  Tail Sampling   │
                   │  Decision Engine │
                   │                  │
                   │  - Wait for root │
                   │  - Evaluate      │
                   │    policies      │
                   │  - Keep / Drop   │
                   └───┬──────────┬───┘
                       │          │
                  Keep │          │ Drop
                       ▼          ▼
              ┌──────────┐  ┌──────────┐
              │ RayOlly  │  │ Metrics  │
              │ Storage  │  │ Only     │
              │ (full    │  │ (span    │
              │  spans)  │  │  counts, │
              └──────────┘  │  RED)    │
                            └──────────┘
```

### 11.4 Guaranteed Capture

Even dropped traces contribute to aggregate metrics (RED: Rate, Errors, Duration) via the span-to-metrics processor, ensuring that sampling does not affect accuracy of service map health indicators, latency percentiles, or error rate calculations.

---

## 12. AI-Powered APM

### 12.1 Automatic Root Cause Identification

When an incident or anomaly is detected, the AI agent analyzes traces to identify root cause:

**Process:**
1. Collect all traces for the affected operation within the anomaly window
2. Compare error/slow traces against baseline healthy traces
3. Identify the deepest span where behavior diverges (the "blame span")
4. Correlate with deployment events, infrastructure metrics, and config changes
5. Generate a natural language explanation

**Example Output:**
```
Root Cause Analysis — POST /api/v1/orders latency spike

Summary: P99 latency increased from 320ms to 2.1s starting at 14:15 UTC.

Root Cause: inventory-service database connection pool exhaustion.
  - Blame span: PostgreSQL SELECT on inventory.stock table
  - Span P99 went from 18ms to 1.8s at 14:15
  - HikariCP connection pool maxed at 10 connections
  - Concurrent query count increased 4x after deploy v2.4.1
  - Deploy v2.4.1 removed query result caching in InventoryRepository

Recommendation:
  1. Revert inventory-service to v2.4.0 (immediate)
  2. Restore cache in InventoryRepository.getStock() (fix-forward)
  3. Increase HikariCP pool size from 10 to 25 (mitigation)

Confidence: 94%
Evidence: 847 traces analyzed, 812 show same blame span pattern.
```

### 12.2 Latency Anomaly Detection Per Endpoint

- Each operation's latency distribution is modeled with a rolling baseline
- Anomalies are detected when the distribution shifts (mean shift, variance increase, new mode)
- Multi-dimensional anomaly detection: detects anomalies in a single environment, region, or customer segment

### 12.3 Deployment Impact Analysis

When a new service version is detected:

1. Compare pre/post deployment latency distributions (Kolmogorov-Smirnov test)
2. Compare error rates and error types
3. Identify new code paths (new spans not seen before)
4. Track rollback rate and time-to-rollback
5. Generate a deployment impact score (0-100)

### 12.4 Trace Pattern Analysis

The AI engine identifies recurring patterns:

- **N+1 query patterns**: Detect repeated identical DB spans within a single trace
- **Retry storms**: Detect excessive retry spans to the same downstream
- **Synchronous fan-out anti-patterns**: Detect sequential calls that could be parallelized
- **Timeout cascade**: Detect when one timeout causes a chain of upstream timeouts

---

## 13. Correlation with Logs & Metrics

### 13.1 Trace-to-Log Correlation

Every log line emitted during a span's execution carries `trace_id` and `span_id` via OpenTelemetry context propagation.

**User flow**: Click a span in the trace timeline -> See all logs for that span in a side panel.

```sql
-- Retrieve logs for a specific trace
SELECT
    timestamp,
    severity_text,
    body,
    span_id,
    resource_attributes['service.name'] AS service
FROM logs.entries
WHERE
    tenant_id = 1
    AND trace_id = 'abc123def456789...'
ORDER BY timestamp ASC;
```

### 13.2 Trace-to-Metric Correlation

Spans automatically generate RED metrics (Rate, Errors, Duration):

```sql
-- Auto-generated span metrics
SELECT
    service_name,
    operation_name,
    toStartOfMinute(timestamp) AS minute,
    count()                                AS request_rate,
    countIf(status_code = 'ERROR')         AS error_count,
    quantile(0.50)(duration_ms)            AS p50_ms,
    quantile(0.99)(duration_ms)            AS p99_ms
FROM traces.spans
WHERE
    tenant_id = 1
    AND span_kind IN ('SERVER', 'CONSUMER')
    AND timestamp >= now() - INTERVAL 1 HOUR
GROUP BY service_name, operation_name, minute
ORDER BY minute DESC;
```

### 13.3 Unified Timeline View

A single timeline shows all signals for a given time range:

```
14:15:00  ▲ Metric anomaly: order-service P99 latency spike (320ms → 2.1s)
14:15:12  ■ Trace: POST /api/v1/orders — 2.3s (ERROR) — trace_id: abc123...
14:15:12  ● Log: [ERROR] HikariPool-1 — Connection not available, timeout 30s
14:15:15  ▲ Metric anomaly: inventory-service DB connection pool at 100%
14:15:30  ★ Deployment: inventory-service v2.4.1 detected (started 14:10)
14:16:00  ◆ AI Alert: Root cause identified — DB connection pool exhaustion
14:16:05  ● Log: [WARN] inventory-service — 47 queries queued for connection
```

---

## 14. Frontend Components

### 14.1 Trace Explorer UI Mockup

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  TRACE EXPLORER                                              RayOlly APM        │
│  ──────────────────────────────────────────────────────────────────────────────  │
│                                                                                  │
│  ┌─ Filters ──────────────────────────────────────────────────────────────────┐ │
│  │ Service: [order-service ▾]  Operation: [All ▾]   Status: [All ▾]          │ │
│  │ Duration: [> 500ms      ]   Tags: [customer.tier=enterprise           ]   │ │
│  │ Time Range: [Last 1 hour ▾]                       [🔍 Search Traces]      │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
│  Results: 1,247 traces found                                 Sort: [Duration ▾] │
│  ──────────────────────────────────────────────────────────────────────────────  │
│                                                                                  │
│  │ Status │ Trace ID     │ Root Service   │ Root Operation        │ Dur   │Spans│
│  │────────│──────────────│────────────────│───────────────────────│───────│─────│
│  │  ❌    │ abc123de...  │ api-gateway    │ POST /api/v1/orders   │ 2.3s  │  24 │
│  │  ❌    │ def456ab...  │ api-gateway    │ POST /api/v1/orders   │ 2.1s  │  22 │
│  │  ❌    │ 789xyz12...  │ api-gateway    │ POST /api/v1/orders   │ 1.9s  │  28 │
│  │  ⚠️    │ aaa111bb...  │ api-gateway    │ POST /api/v1/orders   │ 890ms │  18 │
│  │  ✅    │ bbb222cc...  │ api-gateway    │ GET /api/v1/orders    │ 520ms │  12 │
│  │  ✅    │ ccc333dd...  │ api-gateway    │ POST /api/v1/orders   │ 510ms │  15 │
│  │  ...   │              │                │                       │       │     │
│  │────────│──────────────│────────────────│───────────────────────│───────│─────│
│  │                                                                              │
│  │  Latency Distribution (this query):                                          │
│  │     ▁▂▃▅██▇▅▃▂▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▂▅▃▁                                │
│  │  ───┼────┼────┼────┼────┼────┼────┼────┼────┼───                            │
│  │    100  200  400  600  800  1.0s 1.5s 2.0s 2.5s                             │
│  │                                                                              │
│  └──────────────────────────────────────────────────────────────────────────────┘
│                                                                                  │
│  [Export CSV]  [Create Alert Rule]  [Open in AI Chat]  [Compare Traces]         │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### 14.2 Service Map UI Mockup

See Section 5.5 for the full service map ASCII art mockup.

Additional UI elements:
- **Zoom & pan**: Mouse wheel zoom, click-drag to pan
- **Node click**: Opens service detail side panel (latency, errors, deployments, dependencies)
- **Edge click**: Shows traffic detail between two services (rate, latency, errors)
- **Time scrubber**: Drag slider to replay topology state over time
- **Comparison mode**: Side-by-side topology at two different time points
- **Grouping**: Auto-group by namespace, team ownership, or environment

### 14.3 Flame Graph Visualization

The flame graph component supports:

- **Zoom**: Click to zoom into a subtree; breadcrumb to navigate back
- **Search**: Highlight all frames matching a search term
- **Color schemes**: By package, by self time %, by allocation size
- **Differential mode**: Red = slower, blue = faster vs baseline
- **Timeline integration**: Flame graph for a specific trace span vs aggregated flame graph for an operation

---

## 15. API Endpoints

### 15.1 Trace Search

```
POST /api/v1/traces/search
```

**Request:**
```json
{
  "query": {
    "service_name": "order-service",
    "operation_name": "POST /api/v1/orders",
    "min_duration_ms": 500,
    "status": "ERROR",
    "attributes": {
      "customer.tier": "enterprise"
    },
    "time_range": {
      "start": "2026-03-19T13:00:00Z",
      "end": "2026-03-19T14:00:00Z"
    }
  },
  "sort": { "field": "duration", "order": "desc" },
  "limit": 50,
  "offset": 0
}
```

**Response:**
```json
{
  "traces": [
    {
      "trace_id": "abc123def456789012345678",
      "root_service": "api-gateway",
      "root_operation": "POST /api/v1/orders",
      "start_time": "2026-03-19T13:22:01.123Z",
      "duration_ms": 2312,
      "span_count": 24,
      "service_count": 5,
      "status": "ERROR",
      "error_types": ["SQLTransientConnectionException"]
    }
  ],
  "total_count": 1247,
  "query_duration_ms": 42
}
```

### 15.2 Trace by ID

```
GET /api/v1/traces/{trace_id}
```

**Response:**
```json
{
  "trace_id": "abc123def456789012345678",
  "spans": [
    {
      "span_id": "span001",
      "parent_span_id": "",
      "service_name": "api-gateway",
      "operation_name": "POST /api/v1/orders",
      "span_kind": "SERVER",
      "start_time": "2026-03-19T13:22:01.123Z",
      "end_time": "2026-03-19T13:22:03.435Z",
      "duration_ms": 2312,
      "status_code": "ERROR",
      "attributes": {
        "http.method": "POST",
        "http.url": "/api/v1/orders",
        "http.status_code": 500
      },
      "events": [],
      "resource": {
        "service.name": "api-gateway",
        "service.version": "1.8.2",
        "k8s.pod.name": "api-gw-7b4d9f-x2k4q"
      }
    }
  ],
  "span_count": 24,
  "duration_ms": 2312
}
```

### 15.3 Service Map

```
GET /api/v1/services/map?env=prod&time_range=15m
```

**Response:**
```json
{
  "nodes": [
    {
      "service_name": "order-service",
      "service_type": "service",
      "request_rate": 350.2,
      "error_rate": 0.048,
      "p99_latency_ms": 320,
      "instances": 5,
      "latest_version": "2.4.1",
      "health": "degraded"
    }
  ],
  "edges": [
    {
      "source": "order-service",
      "target": "payment-service",
      "edge_type": "http",
      "request_rate": 150.0,
      "error_rate": 0.003,
      "avg_latency_ms": 45
    }
  ]
}
```

### 15.4 Service Detail

```
GET /api/v1/services/{service_name}?time_range=1h
```

### 15.5 Operation Latency

```
GET /api/v1/services/{service_name}/operations/{operation}/latency?time_range=1h&percentiles=50,90,99
```

### 15.6 Error Groups

```
GET /api/v1/services/{service_name}/errors?time_range=24h&sort=count
```

### 15.7 Trace Comparison

```
POST /api/v1/traces/compare
```

**Request:**
```json
{
  "baseline_trace_id": "trace_before_deploy_abc123",
  "comparison_trace_id": "trace_after_deploy_def456"
}
```

### 15.8 Profile Data

```
GET /api/v1/profiles?service={name}&type=cpu&time_range=15m
GET /api/v1/profiles/trace/{trace_id}/span/{span_id}
```

### 15.9 Sampling Rules (CRUD)

```
GET    /api/v1/sampling/rules
POST   /api/v1/sampling/rules
PUT    /api/v1/sampling/rules/{rule_id}
DELETE /api/v1/sampling/rules/{rule_id}
```

---

## 16. Performance Requirements

### 16.1 Ingestion

| Metric | Target |
|--------|--------|
| Span ingestion throughput | >= 500K spans/second per collector node |
| Ingestion latency (collector to storage) | < 5 seconds P99 |
| Protocol support | OTLP gRPC, OTLP HTTP, Jaeger, Zipkin simultaneously |
| Backpressure handling | Graceful degradation; no data loss on transient overload |
| Max span size | 64 KB (attributes + events + links) |
| Max spans per trace | 10,000 (configurable per tenant, hard limit 100,000) |
| Max events per span | 128 |
| Max attributes per span | 128 keys |

### 16.2 Query Performance

| Query Type | Target (P95) | Dataset |
|------------|-------------|---------|
| Trace by ID | < 100ms | Any retention period |
| Trace search (filtered) | < 500ms | 7-day window |
| Trace search (full scan) | < 3s | 7-day window |
| Service map generation | < 200ms | Real-time (last 15m) |
| Latency percentile query | < 300ms | 1-hour window |
| Error group listing | < 200ms | 24-hour window |
| Profile flame graph | < 500ms | 15-minute window |

### 16.3 Storage

| Metric | Target |
|--------|--------|
| Average span size (compressed) | ~200 bytes |
| Storage per 1B spans/day | ~200 GB/day compressed |
| Hot retention | 7 days (SSD-backed ClickHouse) |
| Warm retention | 30 days (HDD-backed ClickHouse) |
| Cold retention | 365 days (S3/GCS object storage, Parquet) |
| Compression ratio | >= 10:1 (raw to compressed) |

### 16.4 Reliability

| Metric | Target |
|--------|--------|
| Data durability | 99.999% (replicated + S3 backup) |
| Ingestion availability | 99.95% uptime |
| Query availability | 99.9% uptime |
| Recovery time (single node failure) | < 30 seconds (via replication) |

---

## 17. Storage Schema (ClickHouse)

### 17.1 Primary Spans Table

```sql
CREATE TABLE traces.spans (
    -- Identity
    tenant_id            UInt64,
    trace_id             FixedString(32),   -- 128-bit hex-encoded
    span_id              FixedString(16),   -- 64-bit hex-encoded
    parent_span_id       FixedString(16),   -- Empty string for root spans
    trace_state          String DEFAULT '',

    -- Span metadata
    service_name         LowCardinality(String),
    operation_name       LowCardinality(String),
    span_kind            Enum8(
                           'UNSPECIFIED' = 0,
                           'INTERNAL' = 1,
                           'SERVER' = 2,
                           'CLIENT' = 3,
                           'PRODUCER' = 4,
                           'CONSUMER' = 5
                         ),

    -- Timing
    timestamp            DateTime64(9, 'UTC'),  -- Nanosecond precision
    duration_ns          UInt64,
    duration_ms          Float64 MATERIALIZED duration_ns / 1000000.0,

    -- Status
    status_code          Enum8('UNSET' = 0, 'OK' = 1, 'ERROR' = 2),
    status_message       String DEFAULT '',

    -- Attributes (flexible key-value)
    attributes           Map(LowCardinality(String), String),

    -- Common attributes denormalized for fast filtering
    http_method          LowCardinality(String) DEFAULT '',
    http_url             String DEFAULT '',
    http_status_code     UInt16 DEFAULT 0,
    db_system            LowCardinality(String) DEFAULT '',
    db_name              LowCardinality(String) DEFAULT '',
    db_statement         String DEFAULT '',
    normalized_db_statement String DEFAULT '',
    rpc_system           LowCardinality(String) DEFAULT '',
    rpc_service          LowCardinality(String) DEFAULT '',
    rpc_method           LowCardinality(String) DEFAULT '',
    messaging_system     LowCardinality(String) DEFAULT '',
    messaging_destination LowCardinality(String) DEFAULT '',

    -- Exception info (denormalized from events for fast error queries)
    has_error            UInt8 DEFAULT 0,
    exception_type       LowCardinality(String) DEFAULT '',
    exception_message    String DEFAULT '',
    exception_stacktrace String DEFAULT '',

    -- Events (array of structs)
    event_names          Array(String),
    event_timestamps     Array(DateTime64(9, 'UTC')),
    event_attributes     Array(Map(String, String)),

    -- Links
    link_trace_ids       Array(FixedString(32)),
    link_span_ids        Array(FixedString(16)),

    -- Resource attributes
    service_namespace    LowCardinality(String) DEFAULT '',
    service_version      LowCardinality(String) DEFAULT '',
    deployment_environment LowCardinality(String) DEFAULT '',
    host_name            LowCardinality(String) DEFAULT '',
    k8s_pod_name         String DEFAULT '',
    k8s_namespace        LowCardinality(String) DEFAULT '',
    k8s_deployment       LowCardinality(String) DEFAULT '',
    resource_attributes  Map(String, String),

    -- Root span info (denormalized for trace-level queries)
    root_service         LowCardinality(String) DEFAULT '',
    root_operation       LowCardinality(String) DEFAULT '',
    root_duration_ns     UInt64 DEFAULT 0,

    -- Sampling
    sampling_rate        Float32 DEFAULT 1.0,

    -- Projection columns
    INDEX idx_trace_id trace_id TYPE bloom_filter(0.01) GRANULARITY 1,
    INDEX idx_service service_name TYPE set(500) GRANULARITY 1,
    INDEX idx_operation operation_name TYPE set(5000) GRANULARITY 4,
    INDEX idx_status status_code TYPE set(3) GRANULARITY 1,
    INDEX idx_http_status http_status_code TYPE set(100) GRANULARITY 4,
    INDEX idx_has_error has_error TYPE set(2) GRANULARITY 1,
    INDEX idx_duration duration_ms TYPE minmax GRANULARITY 4,
    INDEX idx_exception_type exception_type TYPE set(500) GRANULARITY 4,
    INDEX idx_db_system db_system TYPE set(20) GRANULARITY 4
)
ENGINE = MergeTree()
PARTITION BY (tenant_id, toYYYYMMDD(timestamp))
ORDER BY (tenant_id, service_name, timestamp, trace_id, span_id)
TTL toDateTime(timestamp) + INTERVAL 7 DAY TO VOLUME 'warm',
    toDateTime(timestamp) + INTERVAL 30 DAY TO VOLUME 'cold',
    toDateTime(timestamp) + INTERVAL 365 DAY DELETE
SETTINGS
    index_granularity = 8192,
    storage_policy = 'tiered';
```

### 17.2 Trace Index Table (for fast trace-level queries)

```sql
CREATE TABLE traces.trace_index (
    tenant_id            UInt64,
    trace_id             FixedString(32),
    root_service         LowCardinality(String),
    root_operation       LowCardinality(String),
    start_time           DateTime64(9, 'UTC'),
    duration_ns          UInt64,
    duration_ms          Float64 MATERIALIZED duration_ns / 1000000.0,
    span_count           UInt32,
    service_count        UInt8,
    has_error            UInt8,
    error_types          Array(LowCardinality(String)),
    services             Array(LowCardinality(String)),
    http_status_codes    Array(UInt16),

    INDEX idx_trace_id trace_id TYPE bloom_filter(0.001) GRANULARITY 1,
    INDEX idx_root_service root_service TYPE set(500) GRANULARITY 1,
    INDEX idx_root_operation root_operation TYPE set(5000) GRANULARITY 4,
    INDEX idx_has_error has_error TYPE set(2) GRANULARITY 1,
    INDEX idx_duration duration_ms TYPE minmax GRANULARITY 4
)
ENGINE = MergeTree()
PARTITION BY (tenant_id, toYYYYMMDD(start_time))
ORDER BY (tenant_id, root_service, start_time, trace_id)
TTL toDateTime(start_time) + INTERVAL 30 DAY TO VOLUME 'cold',
    toDateTime(start_time) + INTERVAL 365 DAY DELETE
SETTINGS
    index_granularity = 8192,
    storage_policy = 'tiered';
```

### 17.3 Service Edges Table (for service map)

```sql
CREATE TABLE traces.service_edges_raw (
    tenant_id            UInt64,
    timestamp            DateTime64(3, 'UTC'),
    source_service       LowCardinality(String),
    target_service       LowCardinality(String),
    edge_type            LowCardinality(String),  -- 'http', 'grpc', 'database', 'messaging', 'cache'
    duration_ms          Float64,
    is_error             UInt8,
    trace_id             FixedString(32),
    source_operation     LowCardinality(String),
    target_operation     LowCardinality(String)
)
ENGINE = MergeTree()
PARTITION BY (tenant_id, toYYYYMMDD(timestamp))
ORDER BY (tenant_id, source_service, target_service, timestamp)
TTL toDateTime(timestamp) + INTERVAL 7 DAY DELETE
SETTINGS index_granularity = 8192;
```

### 17.4 Error Groups Table

```sql
CREATE TABLE traces.error_groups (
    tenant_id            UInt64,
    error_fingerprint    UInt64,
    service_name         LowCardinality(String),
    operation_name       LowCardinality(String),
    exception_type       LowCardinality(String),
    sample_message       String,
    sample_stacktrace    String,
    sample_trace_id      FixedString(32),
    first_seen           DateTime64(3, 'UTC'),
    last_seen            DateTime64(3, 'UTC'),
    occurrence_count     UInt64,
    affected_trace_count UInt64,
    status               Enum8('active' = 1, 'resolved' = 2, 'ignored' = 3),
    assigned_to          String DEFAULT '',
    notes                String DEFAULT ''
)
ENGINE = ReplacingMergeTree(last_seen)
ORDER BY (tenant_id, error_fingerprint)
SETTINGS index_granularity = 8192;
```

### 17.5 Profiling Data Table

```sql
CREATE TABLE traces.profiles (
    tenant_id            UInt64,
    service_name         LowCardinality(String),
    profile_type         Enum8('cpu' = 1, 'wall' = 2, 'alloc_objects' = 3,
                                'alloc_space' = 4, 'heap_live' = 5,
                                'lock_contention' = 6, 'goroutine' = 7),
    timestamp            DateTime64(3, 'UTC'),
    duration_ns          UInt64,
    sample_count         UInt32,

    -- Collapsed stack traces (flamegraph-ready)
    stack_traces         Array(String),      -- e.g., ["main;foo;bar", "main;foo;baz"]
    stack_values         Array(UInt64),       -- sample count per stack

    -- Correlation
    trace_id             FixedString(32) DEFAULT '',
    span_id              FixedString(16) DEFAULT '',

    -- Resource
    host_name            LowCardinality(String),
    k8s_pod_name         String DEFAULT '',
    service_version      LowCardinality(String) DEFAULT ''
)
ENGINE = MergeTree()
PARTITION BY (tenant_id, toYYYYMMDD(timestamp))
ORDER BY (tenant_id, service_name, profile_type, timestamp)
TTL toDateTime(timestamp) + INTERVAL 7 DAY TO VOLUME 'warm',
    toDateTime(timestamp) + INTERVAL 30 DAY DELETE
SETTINGS index_granularity = 8192;
```

---

## 18. Migration Paths

### 18.1 From Jaeger

| Aspect | Migration Path |
|--------|---------------|
| **Data format** | Jaeger uses OTEL-compatible spans; no transformation needed |
| **Collector** | Replace Jaeger Collector with RayOlly Collector (Jaeger receiver built-in) |
| **Agent** | Replace Jaeger Agent with OTEL SDK or RayOlly Collector in sidecar mode |
| **Storage** | Export from Cassandra/Elasticsearch via `jaeger-query` API; import via OTLP |
| **UI** | Jaeger UI trace links redirect to RayOlly trace explorer |
| **Query API** | RayOlly provides a Jaeger-compatible `/api/traces` endpoint for transition |
| **Timeline** | 1-2 weeks for infrastructure, 2-4 weeks for full migration |

### 18.2 From Zipkin

| Aspect | Migration Path |
|--------|---------------|
| **Data format** | Zipkin v2 JSON -> OTEL span mapping (well-defined) |
| **Collector** | RayOlly Collector includes Zipkin receiver on port 9411 |
| **Instrumentation** | Replace Zipkin tracers with OTEL SDKs (Brave -> OTEL bridge available) |
| **Storage** | Export from Cassandra/Elasticsearch/MySQL via Zipkin API; import via RayOlly |
| **Timeline** | 1-2 weeks for infrastructure, 2-4 weeks for instrumentation migration |

### 18.3 From Datadog APM

| Aspect | Migration Path |
|--------|---------------|
| **Data format** | Datadog trace format -> OTEL span mapping via RayOlly Collector |
| **Agent** | Dual-ship: configure dd-agent to forward to both Datadog and RayOlly Collector |
| **Instrumentation** | Replace `dd-trace-*` libraries with OTEL SDKs (gradual, per-service) |
| **Service map** | Auto-rebuilt from ingested traces within minutes |
| **Dashboards** | Dashboard migration tool maps Datadog APM widgets to RayOlly equivalents |
| **Monitors** | Alert rule migration tool converts Datadog APM monitors to RayOlly alerts |
| **Timeline** | 2-4 weeks dual-ship, 4-8 weeks full migration |

### 18.4 From Dynatrace

| Aspect | Migration Path |
|--------|---------------|
| **Data format** | Dynatrace PurePath -> OTEL span mapping (requires transformation) |
| **Agent** | Replace OneAgent with OTEL SDK + RayOlly Collector (per-service rollout) |
| **SmartScape** | RayOlly service map auto-discovers same topology from OTEL spans |
| **Davis AI** | RayOlly AI agent provides comparable root cause analysis |
| **Entity model** | Dynatrace entity IDs mapped to OTEL resource attributes |
| **Timeline** | 4-8 weeks (OneAgent removal requires careful per-host rollout) |

### 18.5 Migration Tooling

RayOlly provides:

- **`rayolly migrate jaeger`** — CLI tool to export Jaeger traces and import to RayOlly
- **`rayolly migrate zipkin`** — CLI tool for Zipkin migration
- **`rayolly migrate datadog`** — Converts Datadog dashboards, monitors, and service catalog
- **Dual-write collector config** — Send traces to both old and new system during transition
- **Validation report** — Compares trace counts, service maps, and error rates between old and new

---

## 19. Success Metrics

### 19.1 Product Metrics

| Metric | Target (6 months post-launch) | Measurement |
|--------|-------------------------------|-------------|
| Traces ingested | 50B+ spans/day across all tenants | Ingestion pipeline counter |
| Trace search P95 latency | < 500ms | API server metrics |
| Service map load time | < 200ms | Frontend performance |
| AI root cause accuracy | > 85% (validated by user feedback) | Thumbs up/down on AI analysis |
| Trace-to-log correlation usage | > 60% of trace views click into logs | Frontend analytics |
| Migration completions | 50+ enterprise customers migrated | CRM tracking |

### 19.2 Business Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| APM module adoption | 80% of RayOlly customers enable APM | Feature flag tracking |
| Customer MTTR reduction | 40% reduction vs prior tool | Customer surveys |
| Competitive win rate vs Datadog APM | > 30% in head-to-head evaluations | Sales CRM |
| Net revenue retention (APM users) | > 130% | Finance reporting |
| Cost savings vs competitor | > 60% at equivalent scale | TCO calculator |

### 19.3 Engineering Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Span ingestion reliability | 99.95% uptime | Uptime monitoring |
| Data loss rate | < 0.001% | Ingestion vs storage reconciliation |
| P99 query latency (trace search) | < 1s | API metrics |
| ClickHouse compression ratio | > 10:1 | Storage monitoring |
| Collector CPU overhead | < 2% of host CPU | Agent benchmarks |

---

## 20. Risks & Mitigations

### 20.1 Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **ClickHouse cannot handle trace query patterns at scale** | Medium | High | Trace index table for fast lookups; bloom filters on trace_id; benchmark at 2x projected volume before launch |
| **Tail-based sampling loses traces during collector restarts** | Medium | Medium | WAL (Write-Ahead Log) for in-flight traces; replicated collector pairs; graceful drain on shutdown |
| **Service map becomes unreadable with 500+ services** | High | Medium | Auto-grouping by namespace; zoom/filter controls; focus mode showing N-hop neighborhood of selected service |
| **Profiling overhead unacceptable for latency-sensitive services** | Low | High | All profiling is opt-in per service; async profiling (JFR-based) with < 1% overhead; kill-switch via remote config |
| **OTEL SDK instrumentation gaps in certain frameworks** | Medium | Medium | Maintain a curated instrumentation registry; contribute upstream; provide manual instrumentation guides |
| **High cardinality span attributes explode storage** | High | High | Attribute value cardinality limits (configurable); automatic high-cardinality detection and alerting; attribute allowlist/blocklist per tenant |

### 20.2 Product Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **Users expect Datadog-parity on day 1** | High | High | Clearly scoped GA feature set; migration guide highlights feature mapping; rapid iteration on top-requested gaps |
| **AI root cause analysis produces incorrect results** | Medium | High | Confidence scores on all AI outputs; "show evidence" button; human feedback loop for continuous improvement; conservative alerting thresholds |
| **Migration friction prevents adoption** | Medium | High | Dual-write support; Jaeger/Zipkin/Datadog compatible endpoints; dedicated migration engineering team; free migration assistance for enterprise customers |
| **Open-source alternatives (Jaeger + Grafana) are "good enough"** | Medium | Medium | Differentiate on AI capabilities, profiling integration, and service map intelligence that OSS tools lack; publish competitive benchmarks |

### 20.3 Operational Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **Noisy neighbor in multi-tenant ClickHouse** | Medium | High | Per-tenant resource quotas; query timeout enforcement; tenant isolation via separate partitions; workload management |
| **Span ingestion spikes during incidents (when you need APM most)** | High | High | Auto-scaling collector fleet; adaptive sampling that increases during spikes; priority queue for error traces; capacity headroom at 3x baseline |
| **Cold storage query performance degrades** | Medium | Medium | Columnar Parquet format in S3 for efficient scanning; pre-computed aggregates for cold data; clear UX indication of "searching cold storage — may be slower" |

---

## Appendix A: Glossary

| Term | Definition |
|------|-----------|
| **Span** | A single unit of work within a trace (e.g., one HTTP handler, one DB query) |
| **Trace** | A collection of spans representing an end-to-end request |
| **Root span** | The first span in a trace (no parent) |
| **Trace ID** | 128-bit globally unique identifier for a trace |
| **Span ID** | 64-bit unique identifier for a span within a trace |
| **RED metrics** | Rate, Errors, Duration — the three golden signals derived from spans |
| **Tail-based sampling** | Sampling decision made after a trace completes, enabling intelligent selection |
| **Flame graph** | Visualization of profiling data showing call stacks and resource consumption |
| **Service map** | Graph visualization of service dependencies discovered from trace data |
| **PurePath** | Dynatrace's proprietary distributed tracing technology |
| **SmartScape** | Dynatrace's proprietary topology and dependency mapping feature |

## Appendix B: Related PRDs

| PRD | Relationship |
|-----|-------------|
| PRD-00: Platform Vision | Parent architecture and vision |
| PRD-01: Data Ingestion Pipeline | Shared ingestion infrastructure for OTLP traces |
| PRD-02: Storage Engine | ClickHouse storage layer, tiering policies |
| PRD-03: Query Engine | Trace search query compilation and execution |
| PRD-06: Logs Module | Trace-to-log correlation via trace_id/span_id |
| PRD-07: Metrics Module | Span-derived RED metrics; metric-to-trace drill-down |
| PRD-09: Alerting & Incidents (planned) | APM-driven alerts and incident creation |
| PRD-12: Real User Monitoring (planned) | Browser/mobile trace correlation |

---

*PRD-08 v1.0 | RayOlly Distributed Tracing & APM | Draft | 2026-03-19*
