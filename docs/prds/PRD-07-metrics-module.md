# PRD-07: Metrics & Infrastructure Monitoring

**Product**: RayOlly — AI-Native Observability Platform
**Version**: 1.0
**Date**: 2026-03-19
**Status**: Draft
**Parent**: PRD-00 Platform Vision & Architecture
**Dependencies**: PRD-01 (Ingestion), PRD-02 (Storage), PRD-03 (Query Engine)

---

## 1. Executive Summary

The Metrics Module provides enterprise-grade metrics collection, storage, querying, and visualization. It is designed to replace Prometheus + Grafana + Thanos stacks, Datadog Infrastructure Monitoring, and Dynatrace infrastructure monitoring. Metrics in RayOlly are deeply correlated with logs and traces, and continuously analyzed by AI agents for anomalies and forecasting.

**Key Differentiators**:
- PromQL-compatible query language — zero learning curve for Prometheus users
- 20:1 compression ratio with ClickHouse columnar storage (vs Prometheus TSDB's ~5:1)
- AI-powered anomaly detection on all metrics by default — no manual threshold configuration
- Unified correlation: click any metric anomaly to see related logs and traces
- Infrastructure topology auto-discovery with service dependency mapping

---

## 2. Goals & Non-Goals

### Goals
- Collect, store, and query metrics at 10M+ active time series per tenant
- Full PromQL compatibility for seamless Prometheus migration
- Infrastructure monitoring (hosts, containers, K8s, cloud resources)
- Custom metrics support (application, business, SLI/SLO)
- AI-powered anomaly detection and forecasting on all metrics
- Real-time dashboarding with sub-second refresh

### Non-Goals
- Replace specialized APM profiling (covered in PRD-08)
- Network packet-level monitoring (future scope)
- Synthetic monitoring / uptime checks (future scope)

---

## 3. Metric Types

### 3.1 OpenTelemetry Metric Types

| OTEL Type | Description | Storage Strategy |
|-----------|------------|-----------------|
| **Counter** | Monotonically increasing value | Store cumulative; derive rate at query time |
| **UpDownCounter** | Value that can increase or decrease | Store as gauge-like with delta encoding |
| **Histogram** | Distribution of values in buckets | Store bucket boundaries + counts; use DDSketch for compact storage |
| **ExponentialHistogram** | Histogram with exponential bucket sizes | Native OTEL support; more efficient than explicit histograms |
| **Gauge** | Point-in-time value | Store with DoubleDelta + Gorilla compression |
| **Summary** | Pre-computed quantiles | Store quantile values (legacy Prometheus support) |

### 3.2 Metric Data Model

```sql
-- ClickHouse metrics table (gauge/counter)
CREATE TABLE metrics.samples (
    tenant_id          UInt64,
    metric_name        LowCardinality(String),
    metric_type        Enum8('gauge' = 1, 'counter' = 2, 'histogram' = 3, 'summary' = 4),
    timestamp          DateTime64(3, 'UTC'),  -- Millisecond precision
    value              Float64,

    -- Labels (dimensions)
    labels             Map(LowCardinality(String), String),

    -- Common label shortcuts (denormalized for performance)
    label_service      LowCardinality(String),
    label_host         LowCardinality(String),
    label_namespace    LowCardinality(String),
    label_instance     LowCardinality(String),
    label_job          LowCardinality(String),

    -- Resource
    resource_attributes Map(String, String),

    INDEX idx_metric metric_name TYPE set(1000) GRANULARITY 1,
    INDEX idx_service label_service TYPE set(100) GRANULARITY 1
)
ENGINE = MergeTree()
PARTITION BY (tenant_id, toYYYYMMDD(timestamp))
ORDER BY (tenant_id, metric_name, label_service, label_host, timestamp)
TTL timestamp + INTERVAL 15 DAY TO VOLUME 'warm',
    timestamp + INTERVAL 90 DAY TO VOLUME 'cold'
SETTINGS index_granularity = 8192;

-- Pre-aggregated rollups for long-term retention
CREATE TABLE metrics.rollups_1h (
    tenant_id       UInt64,
    metric_name     LowCardinality(String),
    timestamp       DateTime,
    labels          Map(LowCardinality(String), String),
    min_value       Float64,
    max_value       Float64,
    avg_value       Float64,
    sum_value       Float64,
    count           UInt64,
    p50             Float64,
    p90             Float64,
    p99             Float64
)
ENGINE = AggregatingMergeTree()
PARTITION BY (tenant_id, toYYYYMM(timestamp))
ORDER BY (tenant_id, metric_name, timestamp);

-- Materialized view for automatic rollup
CREATE MATERIALIZED VIEW metrics.mv_rollup_1h TO metrics.rollups_1h AS
SELECT
    tenant_id,
    metric_name,
    toStartOfHour(timestamp) as timestamp,
    labels,
    min(value) as min_value,
    max(value) as max_value,
    avg(value) as avg_value,
    sum(value) as sum_value,
    count() as count,
    quantile(0.5)(value) as p50,
    quantile(0.9)(value) as p90,
    quantile(0.99)(value) as p99
FROM metrics.samples
GROUP BY tenant_id, metric_name, toStartOfHour(timestamp), labels;
```

---

## 4. Metric Collection

### 4.1 Collection Methods

| Method | Use Case | Protocol |
|--------|---------|----------|
| **OTLP** | Modern applications with OTEL SDK | gRPC / HTTP (primary) |
| **Prometheus Remote Write** | Existing Prometheus deployments | HTTP (protobuf) |
| **Prometheus Scrape** | RayOlly Collector scrapes /metrics endpoints | HTTP |
| **StatsD** | Legacy application metrics | UDP/TCP |
| **Datadog Agent** | Migration from Datadog | HTTP (DD API compat) |
| **CloudWatch** | AWS metrics | AWS API polling |
| **GCP Monitoring** | GCP metrics | GCP API polling |
| **Azure Monitor** | Azure metrics | Azure API polling |
| **Custom HTTP** | Business metrics, custom integrations | REST API |

### 4.2 Infrastructure Metrics (Auto-Collected)

**Host Metrics** (via RayOlly Collector / OTEL Collector):

| Category | Metrics |
|----------|---------|
| **CPU** | cpu.utilization, cpu.user, cpu.system, cpu.iowait, cpu.steal, per-core |
| **Memory** | memory.used, memory.free, memory.cached, memory.buffers, memory.swap |
| **Disk** | disk.read_bytes, disk.write_bytes, disk.iops, disk.utilization, per-mount |
| **Network** | network.bytes_in, network.bytes_out, network.packets, network.errors, per-interface |
| **Load** | system.load.1, system.load.5, system.load.15 |
| **Process** | process.count, process.cpu, process.memory, process.open_files |
| **Filesystem** | fs.usage, fs.inodes, fs.read_time, fs.write_time |

**Kubernetes Metrics** (via kube-state-metrics + cAdvisor):

| Category | Metrics |
|----------|---------|
| **Pod** | pod.cpu.usage, pod.memory.usage, pod.restart_count, pod.status |
| **Container** | container.cpu.limit, container.memory.limit, container.throttled |
| **Node** | node.allocatable, node.capacity, node.condition |
| **Deployment** | deployment.replicas, deployment.available, deployment.updated |
| **Service** | service.endpoint_count, service.ready |
| **PVC** | pvc.capacity, pvc.used, pvc.available |
| **HPA** | hpa.current_replicas, hpa.desired_replicas, hpa.cpu_utilization |

**Cloud Infrastructure** (via cloud integrations):

| Provider | Resource Types |
|----------|---------------|
| **AWS** | EC2, RDS, ELB/ALB, Lambda, S3, SQS, DynamoDB, ECS, EKS |
| **GCP** | GCE, Cloud SQL, Cloud Run, GKE, Pub/Sub, BigQuery |
| **Azure** | VMs, SQL, App Service, AKS, Event Hubs, Cosmos DB |

---

## 5. Query Language — PromQL Compatibility

### 5.1 PromQL Support

RayOlly supports full PromQL syntax for metrics querying:

```promql
# Instant queries
http_requests_total{service="payment-api", status=~"5.."}

# Range queries
rate(http_requests_total{service="payment-api"}[5m])

# Aggregations
sum by (service) (rate(http_requests_total[5m]))

# Histograms
histogram_quantile(0.99, sum by (le) (rate(http_request_duration_bucket[5m])))

# Subqueries
max_over_time(rate(http_requests_total[5m])[1h:5m])

# Alert-style queries
(rate(http_errors_total[5m]) / rate(http_requests_total[5m])) > 0.05

# Forecasting (RayOlly extension)
predict_linear(disk_usage_bytes[24h], 7 * 24 * 3600)
```

### 5.2 PromQL Extensions (RayOlly-Specific)

```promql
# AI anomaly score for any metric
anomaly_score(cpu_utilization{host="web-1"})

# Forecasted value
forecast(disk_usage_bytes{mount="/"}, "7d")

# Correlation between metrics
correlate(cpu_utilization, request_latency_p99, "1h")

# Top-K with automatic label selection
topk_by_value(10, rate(http_requests_total[5m]))

# Baseline comparison
compare_to_baseline(error_rate, "last_week")
```

### 5.3 SQL Metrics Queries (RayQL)

```sql
-- Metrics also queryable via SQL
SELECT
    toStartOfMinute(timestamp) as minute,
    labels['service'] as service,
    avg(value) as avg_cpu
FROM metrics.samples
WHERE metric_name = 'cpu_utilization'
  AND timestamp >= now() - INTERVAL 1 HOUR
GROUP BY minute, service
ORDER BY minute;

-- Join metrics with logs
SELECT
    m.timestamp,
    m.value as cpu_pct,
    l.body as log_message
FROM metrics.samples m
JOIN logs.log_entries l ON m.label_host = l.resource_host
    AND abs(toUnixTimestamp(m.timestamp) - toUnixTimestamp(l.timestamp)) < 60
WHERE m.metric_name = 'cpu_utilization'
  AND m.value > 90
  AND l.severity_number >= 17;
```

---

## 6. Infrastructure Monitoring UI

### 6.1 Host Map

Visual topology of all monitored hosts:

```
┌──────────────────────────────────────────────────────────┐
│ Host Map                    [CPU ▼] [Group by: AZ ▼]     │
│                                                          │
│  us-east-1a          us-east-1b          us-east-1c      │
│  ┌────┐ ┌────┐      ┌────┐ ┌────┐      ┌────┐          │
│  │ 🟢 │ │ 🟢 │      │ 🟡 │ │ 🟢 │      │ 🔴 │          │
│  │web1│ │web2│      │web3│ │web4│      │web5│          │
│  │23% │ │45% │      │78% │ │12% │      │95% │          │
│  └────┘ └────┘      └────┘ └────┘      └────┘          │
│  ┌────┐ ┌────┐      ┌────┐              ┌────┐          │
│  │ 🟢 │ │ 🟢 │      │ 🟢 │              │ 🟡 │          │
│  │db-1│ │db-2│      │db-3│              │db-4│          │
│  │34% │ │28% │      │41% │              │67% │          │
│  └────┘ └────┘      └────┘              └────┘          │
│                                                          │
│  Legend: 🟢 Healthy  🟡 Warning  🔴 Critical             │
│  Size = Memory | Color = CPU                             │
└──────────────────────────────────────────────────────────┘
```

### 6.2 Container/Kubernetes View

```
┌──────────────────────────────────────────────────────────┐
│ Kubernetes Cluster: prod-us-east                         │
│                                                          │
│ Namespaces:                                              │
│ ┌─────────────────────────────────────────────────────┐  │
│ │ production                          12 pods │ 3 svc │  │
│ │ ┌──────────┐ ┌──────────┐ ┌──────────┐            │  │
│ │ │ payment  │ │ gateway  │ │ user-svc │            │  │
│ │ │ 3/3 pods │ │ 2/2 pods │ │ 3/3 pods │            │  │
│ │ │ CPU: 45% │ │ CPU: 23% │ │ CPU: 67% │            │  │
│ │ │ Mem: 2.1G│ │ Mem: 512M│ │ Mem: 1.8G│            │  │
│ │ │ 🟢 OK    │ │ 🟢 OK    │ │ 🟡 WARN  │            │  │
│ │ └──────────┘ └──────────┘ └──────────┘            │  │
│ └─────────────────────────────────────────────────────┘  │
│                                                          │
│ Resource Usage:                                          │
│ CPU:  ████████░░ 78% allocated / 45% actual              │
│ Mem:  ██████░░░░ 62% allocated / 55% actual              │
│ Pods: ████████░░ 48/60 capacity                          │
└──────────────────────────────────────────────────────────┘
```

### 6.3 Service Detail Page

For each service/host, show:
- Overview metrics (CPU, memory, disk, network)
- Process list with resource consumption
- Related logs (from PRD-06)
- Related traces (from PRD-08)
- Active alerts
- AI anomaly indicators
- Deployment history timeline
- Configuration changes timeline

---

## 7. AI-Powered Metrics Analysis

### 7.1 Automatic Anomaly Detection

Every metric stream has automatic anomaly detection enabled by default:

```yaml
anomaly_detection:
  default_config:
    enabled: true
    sensitivity: medium  # low, medium, high
    methods:
      - type: statistical    # Z-score + MAD
        training_window: 14d
      - type: seasonal       # STL decomposition
        seasonality: [daily, weekly]
      - type: ml            # Isolation Forest (for complex patterns)
        retrain_interval: 24h
    alert_on_anomaly: true
    min_confidence: 0.8
    cool_down: 15m
```

### 7.2 Forecasting

```
┌──────────────────────────────────────────────────────────┐
│ Disk Usage Forecast — /data mount on db-primary          │
│                                                          │
│ 100%│                                          ▓▓▓▓▓▓▓  │
│     │                                     ░░░░░         │
│  80%│                                ░░░░░              │
│     │                           ░░░░░                    │
│  60%│               ████████████                         │
│     │          █████                                     │
│  40%│     █████                                          │
│     │ ████                                               │
│  20%│█                                                   │
│     └────────────────────────────────────────────────── │
│     Mar 5    Mar 12    Mar 19    Mar 26    Apr 2         │
│                        ↑ today                           │
│     ████ Actual   ░░░░ Forecast   ▓▓▓ >80% threshold    │
│                                                          │
│  ⚠️  AI Prediction: Disk will reach 80% in ~8 days      │
│     Recommendation: Expand volume or archive old data    │
└──────────────────────────────────────────────────────────┘
```

### 7.3 Metric Correlation

AI automatically discovers correlations between metrics:

```
┌──────────────────────────────────────────────────────────┐
│ Correlated Metrics for: api_latency_p99                  │
│                                                          │
│  Metric                    Correlation   Lag             │
│  ─────────────────────────────────────────────           │
│  db_connection_pool_usage    0.94        +2min  ⬆ lead  │
│  gc_pause_duration_ms        0.87        0      sync    │
│  memory_utilization          0.82        -1min  ⬇ lag   │
│  deployment_events           0.79        -5min  ⬇ lag   │
│  http_request_rate           0.71        +1min  ⬆ lead  │
│                                                          │
│  💡 AI Insight: API latency is most strongly driven by   │
│     database connection pool saturation, which precedes  │
│     latency spikes by ~2 minutes.                        │
└──────────────────────────────────────────────────────────┘
```

---

## 8. SLO Management

### 8.1 SLO Definition

```yaml
slos:
  - name: "Payment API Availability"
    description: "Payment API returns successful responses"
    sli:
      type: ratio
      good: 'sum(rate(http_requests_total{service="payment",status=~"2.."}[5m]))'
      total: 'sum(rate(http_requests_total{service="payment"}[5m]))'
    target: 99.95
    window: 30d  # Rolling window
    alert_policies:
      - burn_rate: 14.4   # 2% budget consumed in 1h
        window: 1h
        severity: critical
        notify: [pagerduty:payment-oncall]
      - burn_rate: 6
        window: 6h
        severity: warning
        notify: [slack:#payment-alerts]

  - name: "Search Latency P99"
    sli:
      type: threshold
      metric: 'histogram_quantile(0.99, sum by (le) (rate(search_duration_bucket[5m])))'
      threshold: 500  # ms
    target: 99.9
    window: 30d
```

### 8.2 SLO Dashboard

```
┌──────────────────────────────────────────────────────────┐
│ SLO Overview                                    March '26│
│                                                          │
│ Service          SLO Target   Current   Budget   Status  │
│ ──────────────────────────────────────────────────────── │
│ Payment API      99.95%       99.97%    67%      🟢      │
│ Search           99.90%       99.85%    -50%     🔴      │
│ User Auth        99.99%       99.99%    95%      🟢      │
│ Notifications    99.50%       99.62%    76%      🟢      │
│ Data Pipeline    99.90%       99.91%    10%      🟡      │
│                                                          │
│ Error Budget Burn Rate:                                  │
│ Search ███████████████████░ 150% of budget consumed      │
│   ⚠️ SLO breach projected in 4.2 hours at current rate  │
│   🤖 SLO Guardian Agent investigating...                 │
└──────────────────────────────────────────────────────────┘
```

---

## 9. Prometheus Compatibility

### 9.1 API Compatibility

RayOlly implements the Prometheus HTTP API for drop-in Grafana compatibility:

| Endpoint | Status | Notes |
|----------|--------|-------|
| `GET /api/v1/query` | Full | Instant query |
| `GET /api/v1/query_range` | Full | Range query |
| `GET /api/v1/series` | Full | Series metadata |
| `GET /api/v1/labels` | Full | Label names |
| `GET /api/v1/label/<name>/values` | Full | Label values |
| `POST /api/v1/write` | Full | Remote write |
| `GET /api/v1/metadata` | Full | Metric metadata |
| `GET /api/v1/alerts` | Full | Active alerts |
| `GET /api/v1/rules` | Full | Alerting/recording rules |

### 9.2 Migration from Prometheus

1. **Phase 1**: Add RayOlly as a Prometheus remote write target (dual-write)
2. **Phase 2**: Point Grafana dashboards to RayOlly's Prometheus-compatible API
3. **Phase 3**: Migrate alerting rules to RayOlly (import Prometheus rules YAML)
4. **Phase 4**: Decommission Prometheus + Thanos

```yaml
# prometheus.yml addition for remote write
remote_write:
  - url: https://rayolly.example.com/api/v1/prometheus/write
    headers:
      Authorization: "Bearer <ingest-token>"
      X-RayOlly-Tenant: "my-org"
    queue_config:
      max_samples_per_send: 5000
      batch_send_deadline: 5s
```

---

## 10. Custom Metrics API

```
POST /api/v1/metrics/ingest
Content-Type: application/json
Authorization: Bearer <token>

{
  "metrics": [
    {
      "name": "order.total_value",
      "type": "gauge",
      "value": 149.99,
      "timestamp": "2026-03-19T10:23:45Z",
      "labels": {
        "currency": "USD",
        "region": "us-east",
        "payment_method": "credit_card"
      }
    },
    {
      "name": "order.count",
      "type": "counter",
      "value": 1,
      "labels": {
        "region": "us-east",
        "status": "completed"
      }
    }
  ]
}
```

---

## 11. Performance Requirements

| Metric | Target |
|--------|--------|
| Active time series per tenant | 10M+ |
| Ingestion rate | 5M samples/sec per node |
| Query latency (instant, last 1h) | p50 < 100ms, p99 < 1s |
| Query latency (range, last 24h) | p50 < 500ms, p99 < 5s |
| Query latency (range, last 30d) | p50 < 2s, p99 < 15s |
| Dashboard refresh rate | 10s minimum |
| Compression ratio | 20:1 (vs raw samples) |
| Rollup accuracy | < 0.1% deviation from raw |
| High cardinality support | 1M unique label combinations |

---

## 12. Success Metrics

| Metric | Target (GA) | Target (12mo) |
|--------|------------|---------------|
| Prometheus migration time | < 1 day | < 2 hours |
| Anomaly detection accuracy | 85% | 95% |
| Forecast accuracy (7-day) | 80% within 10% error | 90% |
| SLO breach prediction accuracy | 70% | 85% |
| Storage cost vs Datadog | 60% lower | 75% lower |
| Query PromQL compatibility | 95% of PromQL functions | 99% |

---

## 13. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| High cardinality explosion | Cardinality limits + alerts; auto-drop low-value labels |
| PromQL edge cases | Comprehensive test suite against Prometheus compliance tests |
| Cloud integration auth complexity | OAuth2 + role-based cloud integration; setup wizards |
| Metric naming conflicts | Namespace isolation per tenant; naming conventions enforcement |

---

*End of PRD-07: Metrics & Infrastructure Monitoring*
