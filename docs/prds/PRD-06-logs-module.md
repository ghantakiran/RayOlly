# PRD-06: Logs Module

**Product**: RayOlly — AI-Native Observability Platform
**Version**: 1.0
**Date**: 2026-03-19
**Status**: Draft
**Parent**: PRD-00 Platform Vision & Architecture
**Dependencies**: PRD-01 (Ingestion), PRD-02 (Storage), PRD-03 (Query Engine)

---

## 1. Executive Summary

The Logs Module is one of RayOlly's three core observability pillars. It provides enterprise-grade log management that competes directly with Splunk Enterprise, Datadog Log Management, and the ELK stack. Unlike competitors, RayOlly's logs are deeply integrated with AI agents for automatic pattern detection, anomaly identification, and natural language exploration.

**Key Differentiators**:
- 10x cost reduction vs Splunk through columnar storage and intelligent tiering
- AI-powered log pattern extraction and anomaly detection out-of-the-box
- Natural language log search ("show me all errors from the payment service in the last hour")
- Unified correlation with metrics and traces — no context switching
- No proprietary query language lock-in — standard SQL + compatibility layers

---

## 2. Goals & Non-Goals

### Goals
- Ingest, store, and search logs at petabyte scale with sub-second query response
- Provide full-text search with field-level filtering and aggregation
- Support all major log sources (applications, infrastructure, cloud, security)
- Enable AI-powered log analysis (patterns, anomalies, clustering)
- Deliver live tail with real-time streaming
- Offer compatibility with existing Splunk SPL and ELK queries (migration path)
- Support log-to-metrics derivation for cost-effective monitoring
- Enable compliance archival with configurable retention

### Non-Goals
- Replace dedicated SIEM solutions (security analytics is future scope)
- Build a proprietary log shipping agent (leverage OTEL Collector + Fluent Bit)
- Support unstructured binary log formats (images, videos)

---

## 3. Log Ingestion

### 3.1 Supported Sources

| Source Category | Specific Sources | Protocol |
|----------------|-----------------|----------|
| **Application Logs** | stdout/stderr, log files, frameworks (Log4j, Logback, Python logging, Winston) | OTLP, HTTP, File tail |
| **Infrastructure** | Syslog (RFC 5424/3164), journald, Windows Event Log | Syslog, OTLP |
| **Cloud Services** | AWS CloudWatch, CloudTrail, VPC Flow Logs; GCP Cloud Logging; Azure Monitor | Cloud API polling, webhook |
| **Containers** | Docker, Kubernetes pod logs, containerd | OTEL Collector, Fluent Bit |
| **Network** | Firewall logs, DNS logs, load balancer access logs | Syslog, HTTP |
| **Databases** | PostgreSQL, MySQL, MongoDB, Redis slow logs | File tail, OTLP |
| **Web Servers** | Nginx, Apache, Caddy access/error logs | File tail, Syslog |
| **Custom** | Any structured/semi-structured text | HTTP API, OTLP |

### 3.2 Log Processing Pipeline

```
Raw Log → Parsing → Enrichment → Classification → Storage
                                                      │
    ┌─────────────────────────────────────────────────┘
    │
    ▼
┌────────────────────────────────────────────────────┐
│                  Log Processing                     │
│                                                     │
│  1. RECEIVE: Accept via OTLP/HTTP/Syslog/File      │
│  2. PARSE: Extract fields (grok, regex, JSON, KV)  │
│  3. ENRICH: Add GeoIP, K8s metadata, hostname      │
│  4. CLASSIFY: Detect severity, categorize source    │
│  5. TRANSFORM: Rename fields, redact PII, filter   │
│  6. DERIVE: Generate metrics from log patterns      │
│  7. ROUTE: Send to appropriate storage tier          │
│  8. INDEX: Full-text index + columnar storage       │
│  9. ANALYZE: Feed to AI pattern detection           │
│                                                     │
└────────────────────────────────────────────────────┘
```

### 3.3 Log Parsing Engine

**Built-in Parsers**:

| Format | Parser | Auto-Detected |
|--------|--------|---------------|
| JSON | Native JSON parser | Yes |
| Key-Value | KV parser (`key=value` format) | Yes |
| CSV/TSV | Delimited parser | With header detection |
| Apache/Nginx | Combined Log Format grok pattern | Yes |
| Syslog | RFC 5424 / RFC 3164 parser | Yes |
| Windows Event | XML parser | Yes |
| Custom | Grok patterns (Logstash compatible) | User-defined |
| Regex | Named capture groups | User-defined |
| XML | Nested XML parser | Semi-auto |

**Grok Pattern Library**:
```
# Built-in patterns (200+ patterns, Logstash compatible)
NGINX_ACCESS: %{IPORHOST:remote_addr} - %{USER:remote_user} \[%{HTTPDATE:time_local}\] "%{WORD:method} %{URIPATHPARAM:request} HTTP/%{NUMBER:http_version}" %{INT:status} %{INT:body_bytes_sent} "%{DATA:http_referer}" "%{DATA:http_user_agent}"

# Custom pattern support
CUSTOM_APP: \[%{TIMESTAMP_ISO8601:timestamp}\] \[%{LOGLEVEL:level}\] \[%{DATA:service}\] %{GREEDYDATA:message}
```

**AI-Assisted Parsing**:
- Automatic format detection for unknown log formats
- AI suggests grok patterns for unstructured logs
- Pattern validation with sample log lines
- One-click parser creation from log samples

---

## 4. Log Data Model

### 4.1 Internal Schema

```sql
-- ClickHouse table for logs
CREATE TABLE logs.log_entries (
    -- Core fields
    timestamp          DateTime64(9, 'UTC'),  -- Nanosecond precision
    observed_timestamp DateTime64(9, 'UTC'),  -- When collected
    tenant_id          UInt64,
    org_id             UInt64,
    stream             LowCardinality(String), -- e.g., 'nginx-access', 'app-errors'

    -- OpenTelemetry fields
    trace_id           FixedString(32),        -- Links to traces
    span_id            FixedString(16),         -- Links to spans
    severity_number    UInt8,                   -- OTEL severity (1-24)
    severity_text      LowCardinality(String),  -- DEBUG, INFO, WARN, ERROR, FATAL

    -- Content
    body               String,                  -- Full log message
    body_tokens        String,                  -- Tokenized for search

    -- Resource attributes (who generated it)
    resource_service    LowCardinality(String),
    resource_host       LowCardinality(String),
    resource_namespace  LowCardinality(String),  -- K8s namespace
    resource_pod        LowCardinality(String),  -- K8s pod
    resource_container  LowCardinality(String),  -- Container name
    resource_cloud      LowCardinality(String),  -- aws, gcp, azure
    resource_region     LowCardinality(String),
    resource_attributes Map(String, String),      -- Additional resource attrs

    -- Log attributes (parsed fields)
    attributes          Map(String, String),      -- Extracted fields

    -- Derived fields
    pattern_hash        UInt64,                   -- Log pattern fingerprint
    pattern_signature   String,                   -- Human-readable pattern

    -- Indexing
    INDEX idx_body body TYPE tokenbf_v1(10240, 3, 0) GRANULARITY 4,
    INDEX idx_trace trace_id TYPE bloom_filter(0.01) GRANULARITY 1,
    INDEX idx_severity severity_text TYPE set(10) GRANULARITY 1,
    INDEX idx_service resource_service TYPE set(100) GRANULARITY 1
)
ENGINE = MergeTree()
PARTITION BY (tenant_id, toYYYYMMDD(timestamp))
ORDER BY (tenant_id, resource_service, severity_number, timestamp)
TTL timestamp + INTERVAL 30 DAY TO VOLUME 'warm',
    timestamp + INTERVAL 90 DAY TO VOLUME 'cold'
SETTINGS index_granularity = 8192,
         min_bytes_for_wide_part = 10485760;
```

### 4.2 Severity Levels

| OTEL Severity | Number Range | RayOlly Label | Color |
|---------------|-------------|---------------|-------|
| TRACE | 1-4 | TRACE | Gray |
| DEBUG | 5-8 | DEBUG | Blue |
| INFO | 9-12 | INFO | Green |
| WARN | 13-16 | WARN | Yellow |
| ERROR | 17-20 | ERROR | Red |
| FATAL | 21-24 | FATAL | Purple |

---

## 5. Log Search & Exploration

### 5.1 Search Interface

The log explorer is the primary interface for investigating logs. It combines:
- Full-text search bar with autocomplete
- Field sidebar (filterable list of all extracted fields)
- Time range selector (absolute, relative, comparison)
- Log stream viewer (chronological log display)
- Field statistics panel (top values, cardinality, distribution)

### 5.2 Query Syntax

**Simple Search**:
```
error payment timeout
# Full-text search across all log bodies
```

**Field Filtering**:
```
service:payment-api AND status:error AND latency:>1000
# Field-scoped queries with operators
```

**RayQL (SQL-based)**:
```sql
SELECT timestamp, resource_service, body, attributes['status_code']
FROM logs
WHERE tenant_id = current_tenant()
  AND timestamp >= now() - INTERVAL 1 HOUR
  AND severity_text IN ('ERROR', 'FATAL')
  AND resource_service = 'payment-api'
  AND body ILIKE '%timeout%'
ORDER BY timestamp DESC
LIMIT 100
```

**Pipe Syntax (Splunk SPL inspired)**:
```
source=payment-api severity=ERROR
| where body CONTAINS 'timeout'
| stats count() as error_count BY resource_host
| sort -error_count
| head 10
```

**Natural Language** (via Query Agent):
```
"Show me all payment errors in the last hour grouped by host"
→ Auto-generates RayQL query
→ Shows results with explanation
```

### 5.3 Search Features

| Feature | Description |
|---------|------------|
| **Full-text search** | Tantivy-powered, sub-second across billions of logs |
| **Field filtering** | Click any field value to add as filter |
| **Negative filters** | Exclude field values with `-field:value` |
| **Regex search** | `body:/timeout.*connection/` |
| **Wildcard search** | `service:payment-*` |
| **Saved searches** | Save and share queries with team |
| **Search history** | Recent searches per user |
| **Surrounding logs** | View context lines around a log entry |
| **Log detail view** | Expand any log to see all parsed fields |
| **Copy & share** | Deep-linkable search URLs |
| **Export** | Export results as JSON, CSV, or Parquet |

### 5.4 Aggregations & Analytics

```sql
-- Log volume over time (histogram)
SELECT toStartOfMinute(timestamp) as minute,
       severity_text,
       count() as log_count
FROM logs
WHERE timestamp >= now() - INTERVAL 24 HOUR
GROUP BY minute, severity_text
ORDER BY minute

-- Top error messages
SELECT pattern_signature,
       count() as occurrences,
       min(timestamp) as first_seen,
       max(timestamp) as last_seen
FROM logs
WHERE severity_number >= 17
GROUP BY pattern_signature
ORDER BY occurrences DESC
LIMIT 20

-- Error rate by service
SELECT resource_service,
       countIf(severity_number >= 17) / count() * 100 as error_rate,
       count() as total_logs
FROM logs
WHERE timestamp >= now() - INTERVAL 1 HOUR
GROUP BY resource_service
HAVING error_rate > 1
ORDER BY error_rate DESC
```

---

## 6. Live Tail

### 6.1 Real-Time Log Streaming

Live tail provides a real-time view of incoming logs, similar to `tail -f` but across an entire distributed system.

**Architecture**:
```
Ingestion Pipeline → NATS JetStream → WebSocket Gateway → Browser

- Client subscribes via WebSocket with filter criteria
- Server-side filtering to reduce bandwidth
- Client-side rendering with virtual scrolling
- Pause/resume without losing position
- Highlight matching terms
```

**Features**:
- Filter by service, severity, keyword during live tail
- Color-coded severity levels
- Pause/play with buffer (keeps streaming, buffers for when resumed)
- Rate indicator (logs/second)
- Auto-scroll with smart pause (stops when user scrolls up)
- Multi-stream view (tail multiple services simultaneously)

**Performance**:
- Support 100K logs/sec display rate (with sampling at high volumes)
- WebSocket compression (permessage-deflate)
- Virtual DOM rendering (only render visible rows)
- Target: < 2 second delay from ingestion to display

---

## 7. Log Patterns & AI Analytics

### 7.1 Automatic Pattern Extraction

RayOlly automatically groups similar log lines into patterns using the Drain algorithm:

```
Raw logs:
  "Connection timeout to database host db-1.prod at port 5432 after 30s"
  "Connection timeout to database host db-2.prod at port 5432 after 30s"
  "Connection timeout to database host db-3.prod at port 5432 after 45s"

Extracted pattern:
  "Connection timeout to database host <*> at port <*> after <*>"

  Variables:
    $1: [db-1.prod, db-2.prod, db-3.prod]  → host
    $2: [5432]                                → port
    $3: [30s, 30s, 45s]                       → duration
```

**Pattern Features**:
| Feature | Description |
|---------|------------|
| Auto-clustering | Group logs by structural similarity |
| Pattern trending | Track pattern frequency over time |
| New pattern alerts | Detect never-before-seen log patterns |
| Pattern anomalies | Alert when pattern frequency deviates from baseline |
| Pattern comparison | Compare patterns across time ranges or environments |
| Variable analysis | Statistical analysis of pattern variables |

### 7.2 AI-Powered Log Analytics

| Capability | Description | AI Method |
|-----------|------------|-----------|
| **Anomaly detection** | Detect unusual log volume, new error types, sudden pattern shifts | Time-series analysis + LLM classification |
| **Log summarization** | "What happened in the last hour?" → AI-generated summary | LLM summarization |
| **Error clustering** | Group related errors across services | Embedding similarity + clustering |
| **Impact analysis** | "Which users are affected by this error?" | Trace correlation + AI reasoning |
| **Remediation suggestions** | Suggest fixes based on error patterns and knowledge base | RAG + LLM |

### 7.3 Log-to-Metrics

Derive metrics from log data to reduce storage costs while preserving insights:

```yaml
# Log-to-metrics rule configuration
rules:
  - name: http_error_rate
    source: stream=nginx-access
    type: counter
    filter: "attributes['status_code'] >= 400"
    dimensions:
      - resource_service
      - attributes['status_code']
      - attributes['method']
    description: "HTTP error count derived from access logs"

  - name: request_latency
    source: stream=nginx-access
    type: histogram
    value: "toFloat64(attributes['request_time'])"
    buckets: [0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10]
    dimensions:
      - resource_service
      - attributes['uri']
    description: "Request latency distribution from access logs"
```

Benefits:
- Keep granular logs for 7 days, derived metrics for 13 months
- 100x storage reduction for monitoring use cases
- Metrics queryable via PromQL compatibility layer
- No loss of aggregate visibility

---

## 8. Log Views & Saved Searches

### 8.1 Log Views

Pre-configured views for common investigation patterns:

| View | Description | Default Filters |
|------|------------|----------------|
| **All Logs** | Unfiltered log stream | None |
| **Errors & Warnings** | Only error-level and above | `severity >= WARN` |
| **By Service** | Grouped by service name | Grouped by `resource_service` |
| **Infrastructure** | System and infrastructure logs | `stream IN ('syslog', 'journald', 'kernel')` |
| **Security** | Auth and security events | `stream IN ('auth', 'audit', 'firewall')` |
| **Kubernetes** | K8s cluster events and pod logs | `resource_namespace != ''` |
| **Custom** | User-defined views | User-configured |

### 8.2 Saved Searches

```json
{
  "id": "ss_abc123",
  "name": "Payment Timeout Errors",
  "description": "Payment service timeout errors in production",
  "query": "resource_service:payment-api AND body:timeout AND severity:ERROR",
  "time_range": "relative:1h",
  "columns": ["timestamp", "resource_host", "body", "attributes.trace_id"],
  "sort": { "field": "timestamp", "order": "desc" },
  "sharing": "team",
  "alert_enabled": true,
  "alert_threshold": { "count": 10, "window": "5m" },
  "created_by": "user@example.com",
  "tags": ["payment", "production", "p1"]
}
```

---

## 9. Log Archival & Compliance

### 9.1 Retention Policies

```yaml
retention_policies:
  default:
    hot_tier: 7d        # ClickHouse, fast query
    warm_tier: 30d       # ClickHouse cold storage
    cold_tier: 365d      # S3/MinIO Parquet
    delete_after: 365d   # Permanent deletion

  compliance:
    hot_tier: 30d
    warm_tier: 90d
    cold_tier: 2555d     # 7 years for financial compliance
    delete_after: 2555d
    immutable: true      # Cannot be deleted until TTL

  security:
    hot_tier: 90d
    warm_tier: 365d
    cold_tier: 2555d
    delete_after: 2555d
```

### 9.2 Compliance Features

| Feature | Description |
|---------|------------|
| **Immutable storage** | Write-once, read-many for compliance logs |
| **Legal hold** | Prevent deletion of logs under investigation |
| **GDPR erasure** | Selective deletion of PII fields (not entire logs) |
| **Audit trail** | Track who accessed what logs when |
| **Encryption** | AES-256 at rest, TLS 1.3 in transit |
| **Access controls** | Field-level and stream-level RBAC |
| **Export** | Compliance-ready export in standard formats |

---

## 10. Integration with Other Modules

### 10.1 Logs ↔ Traces
- Click any log with `trace_id` to jump to the distributed trace
- View all logs associated with a specific trace/span
- Correlated timeline view (logs + trace spans on same timeline)

### 10.2 Logs ↔ Metrics
- Log-derived metrics visible in metrics dashboards
- Click metric anomaly to see corresponding logs
- Log volume as a metric for alerting

### 10.3 Logs ↔ AI Agents
- Query Agent understands log data ("show me recent errors")
- RCA Agent investigates logs during root cause analysis
- Anomaly Agent monitors log patterns for unusual activity
- Incident Agent includes relevant logs in incident timeline

### 10.4 Logs ↔ Alerts
- Log-based alerting rules (threshold, pattern, absence)
- Alert preview (see matching logs before saving alert)
- Alert investigation links directly to filtered log view

---

## 11. Frontend Components

### 11.1 Log Explorer Page

```
┌─────────────────────────────────────────────────────────────┐
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ 🔍 Search: error payment timeout          [1h ▼] [🔄]  │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ ┌──────────┐  ┌──────────────────────────────────────────┐ │
│ │ Fields   │  │ Log Volume Chart (histogram)              │ │
│ │          │  │ ▁▂▃▅▇▅▃▂▁▁▂▃▅▇█▇▅▃▂▁                   │ │
│ │ service ▼│  └──────────────────────────────────────────┘ │
│ │ ├ api   3│                                               │
│ │ ├ web   2│  ┌──────────────────────────────────────────┐ │
│ │ └ db    1│  │ Timestamp          Service   Message      │ │
│ │          │  │ 10:23:45.123  ●ERR  payment  Timeout...   │ │
│ │ level   ▼│  │ 10:23:44.891  ●ERR  payment  Conn ref... │ │
│ │ ├ ERROR 5│  │ 10:23:44.567  ●WRN  gateway  Retry att.. │ │
│ │ ├ WARN  3│  │ 10:23:44.234  ●ERR  payment  Timeout...  │ │
│ │ └ INFO  1│  │ 10:23:43.998  ●INF  api      Request...  │ │
│ │          │  │ ...                                        │ │
│ │ host    ▼│  └──────────────────────────────────────────┘ │
│ │ ├ web-1 4│                                               │
│ │ └ web-2 2│  [◀ Prev] Page 1 of 234 [Next ▶] [Export ▼] │
│ └──────────┘                                               │
└─────────────────────────────────────────────────────────────┘
```

### 11.2 Log Detail Panel

When a log entry is expanded:

```
┌──────────────────────────────────────────────────────────┐
│ Log Detail                                          [✕]  │
│                                                          │
│ Timestamp: 2026-03-19T10:23:45.123456789Z               │
│ Service:   payment-api                                   │
│ Host:      web-1.prod.us-east-1                          │
│ Severity:  ERROR                                         │
│ Stream:    payment-api-errors                            │
│                                                          │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ Connection timeout to database host db-1.prod at     │ │
│ │ port 5432 after 30s. Transaction ID: txn_abc123.     │ │
│ │ Retries exhausted (3/3).                             │ │
│ └──────────────────────────────────────────────────────┘ │
│                                                          │
│ Parsed Fields:                                           │
│   db_host:       db-1.prod                               │
│   port:          5432                                    │
│   timeout:       30s                                     │
│   transaction_id: txn_abc123                             │
│   retry_count:   3                                       │
│   retry_max:     3                                       │
│                                                          │
│ Context:                                                 │
│   Trace ID:     abc123...def456  [View Trace →]          │
│   Span ID:      span_789                                 │
│   Pattern:      "Connection timeout to database..."      │
│   Pattern Freq: 47 occurrences in last hour (⬆ 340%)    │
│                                                          │
│ [View Surrounding Logs] [Copy JSON] [Create Alert]       │
│ [Ask AI: "Why is this happening?"]                       │
└──────────────────────────────────────────────────────────┘
```

---

## 12. API Endpoints

### 12.1 Log Search API

```
POST /api/v1/logs/search
Content-Type: application/json
Authorization: Bearer <token>

{
  "query": "service:payment-api AND severity:ERROR",
  "time_range": {
    "from": "2026-03-19T09:00:00Z",
    "to": "2026-03-19T10:00:00Z"
  },
  "fields": ["timestamp", "resource_service", "body", "severity_text"],
  "sort": { "field": "timestamp", "order": "desc" },
  "limit": 100,
  "offset": 0
}

Response: {
  "hits": 247,
  "took_ms": 145,
  "logs": [
    {
      "timestamp": "2026-03-19T10:23:45.123Z",
      "resource_service": "payment-api",
      "body": "Connection timeout to database...",
      "severity_text": "ERROR"
    }
    // ...
  ],
  "aggregations": {
    "severity_distribution": { "ERROR": 198, "WARN": 49 },
    "top_services": { "payment-api": 150, "gateway": 97 }
  }
}
```

### 12.2 Log Ingestion API

```
POST /api/v1/logs/ingest
Content-Type: application/json
Authorization: Bearer <ingest-token>

{
  "stream": "my-app",
  "logs": [
    {
      "timestamp": "2026-03-19T10:23:45.123Z",
      "body": "User login successful",
      "severity": "INFO",
      "attributes": {
        "user_id": "usr_123",
        "ip": "1.2.3.4",
        "method": "oauth2"
      }
    }
  ]
}
```

### 12.3 Live Tail WebSocket

```
WS /api/v1/logs/tail
→ { "action": "subscribe", "filter": "service:payment-api AND severity:>=ERROR" }
← { "type": "log", "data": { "timestamp": "...", "body": "...", ... } }
← { "type": "log", "data": { ... } }
→ { "action": "pause" }
→ { "action": "resume" }
→ { "action": "unsubscribe" }
```

---

## 13. Performance Requirements

| Metric | Target |
|--------|--------|
| Ingestion throughput | 1M logs/sec per node |
| Search latency (simple) | p50 < 200ms, p99 < 2s |
| Search latency (complex agg) | p50 < 1s, p99 < 10s |
| Live tail latency | < 2s end-to-end |
| Pattern extraction | < 5min for new pattern detection |
| Storage efficiency | 10:1 compression ratio |
| Full-text index overhead | < 15% of raw log size |
| Concurrent searches per tenant | 50 |
| Max log message size | 1MB |
| Max fields per log | 500 |

---

## 14. Migration Paths

### 14.1 From Splunk
- SPL → RayQL query translator
- Splunk HEC (HTTP Event Collector) compatible endpoint
- Splunk saved search import
- Dashboard conversion tool
- Dual-write during migration

### 14.2 From ELK/OpenSearch
- Elasticsearch Query DSL compatible endpoint (subset)
- Index pattern → stream mapping
- Kibana dashboard import (basic)
- Logstash output plugin for RayOlly

### 14.3 From Datadog
- Datadog Log API compatible endpoint
- Log pipeline conversion
- Dashboard import tool

---

## 15. Success Metrics

| Metric | Target (GA) | Target (12mo) |
|--------|------------|---------------|
| Log search latency p99 | < 2s | < 1s |
| Storage cost per GB | 70% less than Splunk | 80% less |
| Pattern detection accuracy | 85% | 95% |
| Log-to-trace correlation | 90% of logs with trace context | 98% |
| User adoption | 80% daily active log users | 95% |
| NL query accuracy for logs | 75% | 90% |

---

## 16. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Full-text search performance at scale | Tantivy + skip indexes + bloom filters; partition pruning |
| High cardinality fields | Cardinality limits per field; dictionary encoding |
| Log volume spikes | Adaptive sampling; rate limiting; backpressure |
| Parser maintenance burden | AI-assisted parser creation; community parser library |
| SPL compatibility completeness | Prioritize top 80% of SPL commands; document gaps |

---

*End of PRD-06: Logs Module*
