# PRD-03: Query Engine & Search

**Product**: RayOlly — AI-Native Observability Platform
**Version**: 1.0
**Date**: 2026-03-19
**Status**: Draft
**Parent**: PRD-00 Platform Vision & Architecture
**Dependencies**: PRD-02 (Storage Engine)

---

## 1. Executive Summary

The Query Engine is the brain of RayOlly's data access layer — a unified interface that lets users search, analyze, and explore logs, metrics, and traces using a single query language. It supports **SQL** (primary), **PromQL** (metrics compatibility), **full-text search** (logs), and **natural language** (via AI agents). The engine federates across hot (ClickHouse), warm, and cold (S3/Parquet via DuckDB) storage tiers transparently.

**Key Differentiators**:
- SQL-first with observability-specific extensions (RayQL)
- PromQL-compatible for zero-friction Prometheus migration
- Full-text search via Tantivy (Rust) — no JVM overhead
- Cross-tier federated queries (hot + warm + cold in single query)
- AI-powered query generation from natural language
- Sub-second query performance on billion-row datasets

---

## 2. Goals & Non-Goals

### Goals
1. Provide a unified SQL-based query language (RayQL) for all data types
2. Full PromQL compatibility for Prometheus/Grafana integration
3. Sub-second full-text search across petabytes of logs via Tantivy
4. Transparent federation across hot/warm/cold storage tiers
5. Query result caching for dashboard performance
6. Saved queries, parameterized queries, and scheduled queries
7. Query editor with autocomplete, syntax highlighting, and explain plans
8. Grafana data source compatibility
9. Support 50 concurrent queries per tenant with resource isolation

### Non-Goals
- Replacing ClickHouse's native query optimizer (we leverage it)
- Building a general-purpose data warehouse
- Real-time streaming queries (live tail is handled by NATS WebSocket — PRD-06)

---

## 3. Query Language — RayQL

### 3.1 Design Philosophy

RayQL is **SQL:2016 compatible** with observability-specific extensions. Users familiar with SQL need zero learning curve. Extensions provide observability functions (rate, histogram, anomaly scoring) that would be verbose in standard SQL.

### 3.2 Core SQL Queries

```sql
-- Basic log search
SELECT timestamp, resource_service, severity_text, body
FROM logs
WHERE timestamp >= now() - INTERVAL 1 HOUR
  AND severity_text = 'ERROR'
ORDER BY timestamp DESC
LIMIT 100;

-- Aggregated log analytics
SELECT
    toStartOfMinute(timestamp) AS minute,
    resource_service AS service,
    count() AS error_count,
    uniq(resource_host) AS affected_hosts
FROM logs
WHERE timestamp >= now() - INTERVAL 6 HOUR
  AND severity_number >= 17
GROUP BY minute, service
ORDER BY minute DESC;

-- Metric query with rate calculation
SELECT
    toStartOfMinute(timestamp) AS minute,
    labels['service'] AS service,
    sumRate(value, timestamp, 300) AS requests_per_second
FROM metrics
WHERE metric_name = 'http_requests_total'
  AND timestamp >= now() - INTERVAL 1 HOUR
GROUP BY minute, service
ORDER BY minute;

-- Trace latency analysis
SELECT
    resource_service AS service,
    operation_name,
    count() AS trace_count,
    quantile(0.5)(duration_ns / 1e6) AS p50_ms,
    quantile(0.9)(duration_ns / 1e6) AS p90_ms,
    quantile(0.99)(duration_ns / 1e6) AS p99_ms,
    avg(duration_ns / 1e6) AS avg_ms
FROM traces
WHERE timestamp >= now() - INTERVAL 1 HOUR
  AND parent_span_id = ''  -- Root spans only
GROUP BY service, operation_name
ORDER BY p99_ms DESC
LIMIT 20;

-- Cross-signal correlation: find logs for slow traces
SELECT l.timestamp, l.resource_service, l.body, t.duration_ns / 1e6 AS trace_ms
FROM logs l
JOIN traces t ON l.trace_id = t.trace_id
WHERE t.duration_ns > 5000000000  -- > 5s
  AND t.timestamp >= now() - INTERVAL 1 HOUR
  AND l.severity_number >= 13
ORDER BY t.duration_ns DESC
LIMIT 50;
```

### 3.3 RayQL Extensions

```sql
-- rate() — calculate per-second rate from counter metrics
SELECT rate(value, timestamp, '5m') AS rps
FROM metrics WHERE metric_name = 'http_requests_total';

-- anomaly_score() — AI-computed anomaly confidence
SELECT timestamp, value, anomaly_score(value, '7d') AS score
FROM metrics WHERE metric_name = 'api_latency_p99';

-- forecast() — predict future metric values
SELECT forecast(value, timestamp, '7d') AS predicted_value
FROM metrics WHERE metric_name = 'disk_usage_bytes';

-- topk() — top K by value
SELECT topk(10, resource_service, count()) AS top_services
FROM logs WHERE severity_text = 'ERROR';

-- histogram_quantile() — compute quantile from histogram buckets
SELECT histogram_quantile(0.99, metric_name, value, labels['le'])
FROM metrics WHERE metric_name = 'http_request_duration_bucket';

-- compare_baseline() — compare current value to historical baseline
SELECT timestamp, value,
       compare_baseline(value, '1w') AS vs_last_week,
       compare_baseline(value, '1d') AS vs_yesterday
FROM metrics WHERE metric_name = 'error_rate';

-- extract_fields() — dynamic field extraction from log body
SELECT extract_fields(body, 'kv') AS parsed_fields
FROM logs WHERE stream = 'app-logs';
```

### 3.4 Pipe Syntax (Splunk SPL-Inspired)

For log exploration, RayQL supports an optional pipe syntax:

```
-- Pipe syntax for interactive log exploration
source=nginx-access
| where status >= 500
| extract pattern='%{IP:client_ip} %{WORD:method} %{URIPATH:path}'
| stats count() AS errors, dc(client_ip) AS unique_clients BY path
| sort -errors
| head 20

-- This compiles to equivalent SQL:
SELECT
    extractPath(body) AS path,
    count() AS errors,
    uniq(extractIP(body)) AS unique_clients
FROM logs
WHERE stream = 'nginx-access'
  AND toInt32OrNull(attributes['status']) >= 500
GROUP BY path
ORDER BY errors DESC
LIMIT 20;
```

---

## 4. PromQL Compatibility

### 4.1 Full PromQL Support

RayOlly implements the Prometheus HTTP API for drop-in Grafana integration:

```promql
-- Instant vectors
http_requests_total{service="api", status=~"5.."}

-- Range vectors and rate
rate(http_requests_total{service="api"}[5m])

-- Aggregations
sum by (service) (rate(http_requests_total[5m]))
avg without (instance) (node_cpu_utilization)

-- Histogram quantiles
histogram_quantile(0.99, sum by (le) (rate(http_duration_bucket[5m])))

-- Subqueries
max_over_time(rate(http_requests_total[5m])[1h:5m])

-- Binary operations
rate(http_errors_total[5m]) / rate(http_requests_total[5m]) * 100

-- Recording rule expressions
sum by (service) (rate(http_requests_total{status=~"5.."}[5m]))
  / sum by (service) (rate(http_requests_total[5m]))

-- Supported functions
abs, absent, ceil, changes, clamp, clamp_max, clamp_min,
day_of_month, day_of_week, days_in_month, delta, deriv,
exp, floor, histogram_quantile, holt_winters, hour,
idelta, increase, irate, label_join, label_replace,
ln, log2, log10, minute, month, predict_linear,
rate, resets, round, scalar, sgn, sort, sort_desc,
sqrt, time, timestamp, vector, year,
avg_over_time, min_over_time, max_over_time,
sum_over_time, count_over_time, quantile_over_time,
stddev_over_time, stdvar_over_time, last_over_time,
present_over_time, absent_over_time
```

### 4.2 Prometheus API Endpoints

```
GET  /api/v1/query              # Instant query
GET  /api/v1/query_range        # Range query
GET  /api/v1/series             # Find series by label matchers
GET  /api/v1/labels             # Get all label names
GET  /api/v1/label/{name}/values # Get label values
POST /api/v1/write              # Remote write (ingestion)
GET  /api/v1/metadata           # Metric metadata
GET  /api/v1/alerts             # Active alerts
GET  /api/v1/rules              # Alerting and recording rules
GET  /api/v1/targets            # Scrape targets
```

### 4.3 PromQL → SQL Translation

Internally, PromQL queries are translated to optimized ClickHouse SQL:

```promql
sum by (service) (rate(http_requests_total{status=~"5.."}[5m]))
```
Translates to:
```sql
SELECT
    labels['service'] AS service,
    sum(
        (last_value - first_value) / (last_ts - first_ts)
    ) AS value
FROM (
    SELECT
        labels['service'],
        first_value(value) OVER w AS first_value,
        last_value(value) OVER w AS last_value,
        first_value(timestamp) OVER w AS first_ts,
        last_value(timestamp) OVER w AS last_ts
    FROM metrics
    WHERE metric_name = 'http_requests_total'
      AND match(labels['status'], '^5..$')
      AND timestamp >= now() - INTERVAL 5 MINUTE
    WINDOW w AS (PARTITION BY labels ORDER BY timestamp)
)
GROUP BY service;
```

---

## 5. Full-Text Search Engine

### 5.1 Tantivy Integration

RayOlly uses **Tantivy** (Rust-based search engine library) for full-text search, accessed from Python via PyO3 bindings.

```
┌────────────────────────────────────────────┐
│           Full-Text Search Architecture     │
│                                             │
│  Query: "connection timeout database"       │
│           │                                 │
│  ┌────────▼─────────┐                      │
│  │  Query Parser     │                      │
│  │  (AND/OR/NOT,     │                      │
│  │   field scoped,   │                      │
│  │   wildcards,      │                      │
│  │   phrase, fuzzy)  │                      │
│  └────────┬─────────┘                      │
│           │                                 │
│  ┌────────▼─────────┐                      │
│  │ Tantivy Search    │  ← Rust via PyO3    │
│  │  - Inverted Index │                      │
│  │  - BM25 scoring   │                      │
│  │  - Term/Phrase    │                      │
│  │  - Regex match    │                      │
│  └────────┬─────────┘                      │
│           │ Matching doc IDs               │
│  ┌────────▼─────────┐                      │
│  │ ClickHouse Fetch  │  ← Get full records │
│  │  by row IDs       │                      │
│  └────────┬─────────┘                      │
│           │                                 │
│  ┌────────▼─────────┐                      │
│  │  Result Assembly  │                      │
│  │  + Highlighting   │                      │
│  └──────────────────┘                      │
└────────────────────────────────────────────┘
```

### 5.2 Search Query Syntax

```
# Simple terms (AND by default)
connection timeout database

# Explicit boolean
connection AND (timeout OR refused) NOT test

# Field-scoped search
service:payment-api AND body:"connection timeout"

# Wildcards
service:payment-* AND body:timeout*

# Regex
body:/connection.*timeout.*\d+ms/

# Phrase search (exact sequence)
"connection timeout after 30 seconds"

# Fuzzy search
body:timout~2  # Levenshtein distance 2

# Range queries
attributes.status_code:[500 TO 599]
attributes.latency_ms:>1000

# Proximity search
"timeout database"~5  # Terms within 5 words
```

### 5.3 Tokenization

| Tokenizer | Use Case | Description |
|-----------|---------|-------------|
| **Standard** | Default for body field | Unicode-aware word tokenization, lowercase |
| **Whitespace** | Log fields | Split on whitespace only |
| **Keyword** | Exact match fields | No tokenization (service name, hostname) |
| **Path** | File paths | Split on `/`, `.`, `\` |
| **Camel** | Code identifiers | Split camelCase and snake_case |
| **NGram** | Substring search | Character n-grams (2-4) for contains queries |

### 5.4 Index Configuration

```yaml
# Per-stream full-text index configuration
search_index:
  default:
    indexed_fields:
      - field: body
        tokenizer: standard
        stored: false  # Not stored in index, fetch from ClickHouse
      - field: resource_service
        tokenizer: keyword
      - field: severity_text
        tokenizer: keyword
    bloom_filter_fields:
      - trace_id
      - span_id
    commit_interval: 5s
    merge_policy:
      min_merge_size: 8MB
      max_merge_size: 5GB
```

---

## 6. Query Processing Pipeline

### 6.1 Execution Flow

```
┌───────────────┐
│  Query Input   │  (SQL, PromQL, Search, NL)
└───────┬───────┘
        │
┌───────▼───────┐
│  Query Router  │  Determine query type → handler
└───────┬───────┘
        │
┌───────▼───────────────────────────────────────┐
│  Query Planner                                 │
│                                                │
│  1. Parse → AST                                │
│  2. Validate (syntax, permissions, tenant)      │
│  3. Analyze (identify tables, time range, etc.) │
│  4. Optimize (predicate pushdown, column prune) │
│  5. Plan (single-node vs distributed)           │
│  6. Tier routing (hot vs warm vs cold)          │
└───────┬───────────────────────────────────────┘
        │
┌───────▼───────────────────────────────────────┐
│  Query Executor                                │
│                                                │
│  Hot tier:  → ClickHouse SQL (native client)   │
│  Warm tier: → ClickHouse SQL (same, slower)    │
│  Cold tier: → DuckDB on S3 Parquet             │
│  Search:    → Tantivy → ClickHouse fetch       │
│  Mixed:     → Fan-out to all relevant tiers,   │
│               merge results                     │
└───────┬───────────────────────────────────────┘
        │
┌───────▼───────┐
│  Result Cache  │  Redis (TTL based on query type)
└───────┬───────┘
        │
┌───────▼───────────────────────────────────────┐
│  Result Formatter                              │
│  JSON │ CSV │ Parquet │ Arrow │ Prometheus     │
└───────────────────────────────────────────────┘
```

### 6.2 Query Optimization

| Optimization | Description | Impact |
|-------------|------------|--------|
| **Time range partitioning** | Prune ClickHouse partitions by time range | 10-100x faster |
| **Tenant injection** | Auto-inject `tenant_id = X` filter | Security + performance |
| **Predicate pushdown** | Push WHERE clauses to storage layer | Reduce data read |
| **Column pruning** | Only read columns referenced in SELECT/WHERE | Reduce I/O |
| **Materialized view routing** | Route to pre-aggregated materialized views | 10-100x faster for aggregations |
| **Bloom filter pre-filtering** | Use bloom filters for trace_id lookups | Skip partitions |
| **Result caching** | Cache frequent queries (dashboards) in Redis | Sub-millisecond repeat queries |
| **Approximate queries** | Use HyperLogLog for cardinality, t-digest for quantiles | Faster + less memory |
| **Parallel execution** | Fan out to ClickHouse shards in parallel | Linear speedup |
| **Query deduplication** | Collapse identical concurrent queries | Reduce load |

### 6.3 Tier-Aware Federation

```python
class FederatedQueryPlanner:
    """Routes query to appropriate storage tiers based on time range."""

    async def plan(self, query: ParsedQuery) -> FederatedPlan:
        time_range = query.time_range
        plans = []

        # Hot tier: data from last N days (configurable per tenant)
        hot_cutoff = now() - timedelta(days=tenant.hot_retention_days)
        if time_range.end > hot_cutoff:
            plans.append(ClickHousePlan(
                time_range=TimeRange(max(time_range.start, hot_cutoff), time_range.end),
                tier="hot"
            ))

        # Warm tier: data from hot_cutoff to warm_cutoff
        warm_cutoff = now() - timedelta(days=tenant.warm_retention_days)
        if time_range.start < hot_cutoff and time_range.end > warm_cutoff:
            plans.append(ClickHousePlan(
                time_range=TimeRange(max(time_range.start, warm_cutoff), min(time_range.end, hot_cutoff)),
                tier="warm"
            ))

        # Cold tier: anything older than warm_cutoff
        if time_range.start < warm_cutoff:
            plans.append(DuckDBPlan(
                time_range=TimeRange(time_range.start, min(time_range.end, warm_cutoff)),
                s3_prefix=f"s3://{bucket}/{tenant.id}/",
                format="parquet"
            ))

        return FederatedPlan(sub_plans=plans, merge_strategy=query.merge_strategy)
```

---

## 7. Query Caching

### 7.1 Cache Strategy

| Query Type | Cache TTL | Cache Key |
|-----------|-----------|-----------|
| Dashboard widget (relative time) | 10-60s | hash(query + time_bucket) |
| Dashboard widget (absolute time) | 24h | hash(query + time_range) |
| Saved search | 60s | hash(query + time_bucket) |
| Ad-hoc query | No cache | — |
| PromQL instant query | 15s | hash(query + step) |
| PromQL range query | Varies by range | hash(query + range + step) |
| Full-text search | 30s | hash(query + time_bucket + tenant) |

### 7.2 Cache Implementation

```python
class QueryCache:
    """Redis-backed query result cache with smart invalidation."""

    def __init__(self, redis: Redis):
        self.redis = redis

    async def get_or_execute(self, query: Query, executor: QueryExecutor) -> QueryResult:
        if not query.cacheable:
            return await executor.execute(query)

        cache_key = self.compute_key(query)
        cached = await self.redis.get(cache_key)
        if cached:
            self.metrics.cache_hits.inc()
            return deserialize(cached)

        self.metrics.cache_misses.inc()
        result = await executor.execute(query)
        await self.redis.setex(cache_key, query.cache_ttl, serialize(result))
        return result

    def compute_key(self, query: Query) -> str:
        # Normalize time range to bucket for relative time queries
        normalized_time = self.bucket_time(query.time_range, query.cache_ttl)
        return f"qcache:{query.tenant_id}:{hash(query.sql + str(normalized_time))}"
```

---

## 8. Saved Queries & Views

### 8.1 Saved Query Model

```json
{
  "id": "sq_abc123",
  "name": "Payment Errors (Last Hour)",
  "description": "All payment service errors grouped by endpoint",
  "query": "SELECT toStartOfMinute(timestamp) AS minute, attributes['endpoint'] AS endpoint, count() AS errors FROM logs WHERE resource_service = 'payment-api' AND severity_text = 'ERROR' AND timestamp >= now() - INTERVAL 1 HOUR GROUP BY minute, endpoint ORDER BY minute",
  "query_type": "sql",
  "parameters": [
    { "name": "service", "type": "string", "default": "payment-api" },
    { "name": "lookback", "type": "interval", "default": "1 HOUR" }
  ],
  "schedule": null,
  "sharing": "team",
  "tags": ["payment", "production", "errors"],
  "created_by": "user@example.com",
  "created_at": "2026-03-19T10:00:00Z"
}
```

### 8.2 Scheduled Queries

```yaml
# Execute query on schedule, store results and/or trigger alerts
scheduled_queries:
  - name: hourly-error-summary
    query: |
      SELECT resource_service, count() AS errors
      FROM logs
      WHERE severity_number >= 17
        AND timestamp >= now() - INTERVAL 1 HOUR
      GROUP BY resource_service
      HAVING errors > 100
    schedule: "0 * * * *"  # Every hour
    actions:
      - type: store
        destination: metrics
        metric_name: hourly_error_count
        labels: [resource_service]
      - type: alert
        condition: "errors > 1000"
        channels: [slack:#alerts]
```

---

## 9. Query Editor (Frontend Component)

### 9.1 Monaco Editor Integration

```
┌──────────────────────────────────────────────────────────┐
│ Query Editor                                [Run ▶] [⚙]  │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ SELECT timestamp, resource_service, body             │ │
│ │ FROM logs█                                           │ │
│ │ WHERE timestamp >= now() - INTERVAL 1 HOUR           │ │
│ │   AND severity_text = 'ERROR'                        │ │
│ │ ORDER BY timestamp DESC                              │ │
│ │ LIMIT 100                                            │ │
│ └──────────────────────────────────────────────────────┘ │
│                                                          │
│ Autocomplete suggestions:          [SQL ▼] [PromQL] [NL]│
│ ┌──────────────────────┐                                 │
│ │ ▸ logs               │  Tables                         │
│ │ ▸ metrics            │                                 │
│ │ ▸ traces             │                                 │
│ │ ▸ log_patterns       │                                 │
│ └──────────────────────┘                                 │
│                                                          │
│ [History ▼] [Saved ▼] [Explain Plan] [Format Query]     │
└──────────────────────────────────────────────────────────┘
```

### 9.2 Autocomplete Features

| Feature | Description |
|---------|------------|
| **Table names** | All accessible tables (logs, metrics, traces, etc.) |
| **Column names** | Columns for selected table, including dynamic fields |
| **Functions** | SQL + RayQL extension functions with signatures |
| **Field values** | Top values for low-cardinality fields (service names, severity) |
| **Keywords** | SQL keywords with context-aware suggestions |
| **Snippets** | Common query templates (error rate, latency percentiles) |
| **History** | Recent queries from the same user |
| **AI suggestions** | Context-aware query completions via LLM |

### 9.3 Explain Plan Visualization

```
┌──────────────────────────────────────────────────────┐
│ Explain Plan                                         │
│                                                      │
│ ┌─ Limit 100                                    0ms  │
│ │  └─ Sort by timestamp DESC                    2ms  │
│ │     └─ Filter: severity = 'ERROR'            12ms  │
│ │        └─ ClickHouse Scan: logs              145ms  │
│ │           ├─ Partitions scanned: 1/30              │
│ │           ├─ Rows scanned: 1.2M / 150M             │
│ │           ├─ Bytes read: 48MB (compressed)         │
│ │           └─ Index: idx_severity (skip index)      │
│ │                                                    │
│ │  Total: 159ms | Rows: 100 | Bytes: 48MB           │
│ │  Tier: Hot (ClickHouse)                            │
│ └────────────────────────────────────────────────────│
└──────────────────────────────────────────────────────┘
```

---

## 10. Query API

### 10.1 REST Endpoints

```
# Execute SQL query
POST /api/v1/query
Content-Type: application/json
Authorization: Bearer <token>

{
  "query": "SELECT timestamp, body FROM logs WHERE severity_text = 'ERROR' LIMIT 10",
  "time_range": { "from": "2026-03-19T09:00:00Z", "to": "2026-03-19T10:00:00Z" },
  "format": "json",
  "timeout": 30
}

Response:
{
  "status": "ok",
  "took_ms": 145,
  "rows": 10,
  "total_rows": 24891,
  "columns": [
    { "name": "timestamp", "type": "DateTime64(9)" },
    { "name": "body", "type": "String" }
  ],
  "data": [
    { "timestamp": "2026-03-19T09:59:45.123Z", "body": "Connection timeout..." },
    ...
  ],
  "query_id": "q_abc123",
  "tier": "hot",
  "cached": false
}
```

```
# Execute PromQL query
GET /api/v1/prometheus/query?query=rate(http_requests_total[5m])&time=2026-03-19T10:00:00Z

GET /api/v1/prometheus/query_range?query=rate(http_requests_total[5m])&start=2026-03-19T09:00:00Z&end=2026-03-19T10:00:00Z&step=60s

# Full-text search
POST /api/v1/search
{
  "query": "connection timeout database",
  "stream": "payment-api",
  "time_range": { "from": "...", "to": "..." },
  "fields": ["timestamp", "resource_service", "body"],
  "highlight": true,
  "limit": 50
}

# Streaming query results via WebSocket
WS /api/v1/query/stream
→ { "query": "SELECT * FROM logs WHERE ...", "stream": true }
← { "type": "row", "data": { ... } }
← { "type": "row", "data": { ... } }
← { "type": "complete", "rows": 1000, "took_ms": 2345 }

# Query management
GET    /api/v1/queries/saved           # List saved queries
POST   /api/v1/queries/saved           # Save a query
GET    /api/v1/queries/history          # Recent query history
POST   /api/v1/queries/explain          # Get explain plan
DELETE /api/v1/queries/cancel/{id}      # Cancel running query
GET    /api/v1/queries/running          # List running queries
```

### 10.2 Export Formats

| Format | Content-Type | Use Case |
|--------|-------------|----------|
| JSON | application/json | Default API response |
| CSV | text/csv | Spreadsheet export |
| Parquet | application/x-parquet | Large dataset export |
| Arrow IPC | application/vnd.apache.arrow.stream | High-performance client |
| Prometheus | application/json | PromQL endpoint responses |

---

## 11. Multi-Tenancy in Queries

### 11.1 Automatic Tenant Injection

Every query is automatically rewritten to include tenant isolation:

```python
class TenantInjector:
    """Injects tenant_id filter into every query for data isolation."""

    def rewrite(self, query: ParsedQuery, tenant_id: int) -> ParsedQuery:
        # For every table reference, add tenant_id filter
        for table_ref in query.table_references:
            if table_ref.name in TENANT_SCOPED_TABLES:
                query.add_filter(f"{table_ref.alias}.tenant_id = {tenant_id}")

        # Prevent cross-tenant joins
        if query.has_joins:
            self.validate_no_cross_tenant_access(query, tenant_id)

        return query
```

### 11.2 Resource Isolation

| Resource | Per-Tenant Limit | Mechanism |
|----------|-----------------|-----------|
| Concurrent queries | 50 (configurable) | Semaphore per tenant |
| Query memory | 4GB per query | ClickHouse settings `max_memory_usage` |
| Query timeout | 300s (configurable) | Server-enforced timeout |
| Result size | 10M rows (configurable) | Limit enforcement |
| CPU priority | Weighted fair queuing | ClickHouse user-level weights |

---

## 12. Compatibility & Integration

### 12.1 Grafana Data Source

RayOlly ships a Grafana data source plugin:

```yaml
# Grafana provisioning
datasources:
  - name: RayOlly
    type: rayolly-datasource
    url: https://api.rayolly.example.com
    jsonData:
      tenant: my-org
    secureJsonData:
      apiKey: $RAYOLLY_API_KEY

  # Also works as Prometheus data source (PromQL API)
  - name: RayOlly-Prometheus
    type: prometheus
    url: https://api.rayolly.example.com/api/v1/prometheus
    jsonData:
      httpHeaderName1: Authorization
    secureJsonData:
      httpHeaderValue1: "Bearer $RAYOLLY_API_KEY"
```

### 12.2 JDBC/ODBC Drivers

```
# JDBC connection (via ClickHouse JDBC driver compatibility)
jdbc:clickhouse://api.rayolly.example.com:8443/default?ssl=true&user=<api-key>&password=<token>

# Use with any BI tool: Tableau, Metabase, Superset, DBeaver, etc.
```

---

## 13. Performance Requirements

| Metric | Target |
|--------|--------|
| Simple log search (last 1h, 1 filter) | p50 < 200ms, p99 < 2s |
| Complex aggregation (last 24h, group by) | p50 < 1s, p99 < 10s |
| Full-text search (last 1h) | p50 < 300ms, p99 < 3s |
| PromQL instant query | p50 < 100ms, p99 < 1s |
| PromQL range query (24h, 60s step) | p50 < 500ms, p99 < 5s |
| Cross-tier federated query (hot + cold) | p50 < 5s, p99 < 30s |
| Trace by ID | p50 < 100ms, p99 < 500ms |
| Max concurrent queries per tenant | 50 |
| Query cache hit ratio (dashboards) | > 80% |
| Max result set | 10M rows |

---

## 14. Technical Architecture

### 14.1 Technology Stack

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Query parser | sqlglot (Python) | SQL dialect translation, AST manipulation |
| PromQL parser | Custom Python parser | Full PromQL spec compliance |
| ClickHouse client | clickhouse-connect (Python) | Async, connection pooling, native protocol |
| DuckDB client | duckdb Python package | In-process OLAP for cold tier queries |
| Search engine | tantivy-py (Rust via PyO3) | Fast full-text search, no JVM |
| Query cache | Redis Cluster | Distributed caching, pub/sub for invalidation |
| Query editor | Monaco Editor (React) | VS Code-grade editing in browser |
| API server | FastAPI | Async, WebSocket, streaming responses |

---

## 15. Success Metrics

| Metric | Target (GA) | Target (12mo) |
|--------|------------|---------------|
| Query latency p99 (simple) | < 2s | < 1s |
| PromQL compatibility | 95% of functions | 99% |
| Search latency p99 | < 3s | < 1s |
| Cache hit ratio | 70% | 85% |
| Concurrent query capacity | 50/tenant | 200/tenant |
| Grafana compatibility | Full Prometheus API | + native plugin |
| NL-to-SQL accuracy | 75% | 92% |

---

## 16. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| PromQL edge cases breaking Grafana dashboards | Comprehensive test suite against Prometheus compliance tests; community bug reports pipeline |
| Cross-tier query latency for cold data | DuckDB parallelism; pre-warm frequently accessed cold data; query explain plan shows expected latency |
| SQL injection | Parameterized queries; AST-based rewriting (never string concatenation); sqlglot validation |
| Query of death (resource exhaustion) | Per-query memory limits; timeout enforcement; query complexity scoring; kill switch for runaway queries |
| Tantivy index size growing unbounded | Index lifecycle management; index per time partition; automatic cleanup |

---

*End of PRD-03: Query Engine & Search*
