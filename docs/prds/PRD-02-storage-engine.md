# PRD-02: Storage Engine & Data Lifecycle

**Product**: RayOlly — AI-Native Observability Platform
**Module**: Storage Engine & Data Lifecycle Management
**Version**: 1.0
**Date**: 2026-03-19
**Status**: Draft
**Author**: Platform Architecture Team
**Priority**: P0 — Critical (Foundation)
**Dependencies**: None (foundational module)
**Depends On This**: PRD-03 (Query Engine), PRD-04 (AI/ML Engine), PRD-06 (Logs), PRD-07 (Metrics), PRD-08 (Traces)
**Stakeholders**: Engineering, SRE, Data Platform, Security, Finance

---

## 1. Overview

### 1.1 Purpose

This PRD defines the storage engine that underpins the entire RayOlly observability platform. The storage engine provides a unified persistence layer for all four observability pillars — logs, metrics, traces, and events — with intelligent data lifecycle management that delivers 10x cost efficiency over incumbent solutions like Splunk and Datadog.

### 1.2 Scope

The storage engine encompasses:

- **Hot tier**: ClickHouse cluster for real-time ingest and sub-second queries on recent data
- **Warm tier**: ClickHouse cold volumes on cost-optimized disks for aging but still queryable data
- **Cold tier**: S3/MinIO object storage with Apache Parquet files and Iceberg metadata for long-term retention
- **Data lifecycle management**: Automated tiering, compaction, TTL enforcement, and compliance holds
- **Multi-tenant data isolation**: Shared infrastructure with per-tenant logical isolation and resource controls
- **Self-monitoring**: The storage engine monitors its own health and performance

### 1.3 Reference Architecture

This PRD implements the Storage Layer described in PRD-00 (Platform Vision & Architecture), Section 5.1. It receives data from the Stream Processor (PRD-01) and serves the Query Engine (PRD-03).

```
Stream Processor (PRD-01)
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│                 STORAGE ENGINE (This PRD)                │
│                                                          │
│  ┌────────────┐   ┌─────────────┐   ┌───────────────┐  │
│  │  HOT TIER  │──▶│  WARM TIER  │──▶│   COLD TIER   │  │
│  │ ClickHouse │   │  ClickHouse │   │  S3/MinIO     │  │
│  │  (NVMe)    │   │  (EBS gp3)  │   │  (Parquet)    │  │
│  │  0-3 days  │   │  3-30 days  │   │  30+ days     │  │
│  └────────────┘   └─────────────┘   └───────────────┘  │
│         │                │                   │           │
│         └────────────────┼───────────────────┘           │
│                          ▼                               │
│              Unified Query Interface                     │
│                    (PRD-03)                               │
└─────────────────────────────────────────────────────────┘
```

---

## 2. Goals & Non-Goals

### 2.1 Goals

| ID | Goal | Measurement |
|----|------|-------------|
| G1 | Unified storage for all observability data types | Single schema handles logs, metrics, traces, events |
| G2 | 10x storage cost reduction vs Splunk/Datadog | < $0.50/GB/month hot, < $0.05/GB/month cold |
| G3 | Sub-second query latency on hot data | p50 < 500ms, p99 < 2s for common queries |
| G4 | Handle 1M+ rows/sec sustained ingest per shard | Measured at ClickHouse insert level |
| G5 | Automatic data tiering without query disruption | Same SQL across all tiers, transparent to callers |
| G6 | Multi-tenant isolation without per-tenant infrastructure | Shared tables with enforced tenant_id filtering |
| G7 | Compliance-ready retention and deletion | GDPR right-to-erasure, legal hold, configurable retention |
| G8 | 11-nines durability on cold storage | Matching S3 durability guarantees |
| G9 | Horizontal scalability to 100+ nodes | Linear throughput scaling with shard addition |
| G10 | Self-hosted and SaaS deployment parity | Identical storage engine in both models |

### 2.2 Non-Goals

| ID | Non-Goal | Rationale |
|----|----------|-----------|
| NG1 | Real-time streaming analytics (sub-100ms) | Not a streaming engine; NATS handles real-time |
| NG2 | ACID transactional guarantees | Observability data is append-mostly; eventual consistency is acceptable |
| NG3 | Graph database capabilities | Trace relationships use span parent pointers, not a graph DB |
| NG4 | Full-text search (primary) | Tantivy handles full-text; ClickHouse provides secondary token-level search |
| NG5 | Custom storage engine development | We leverage ClickHouse, not build a new database |
| NG6 | Real-time join across hot and cold in < 1s | Cross-tier joins are best-effort; cold tier queries are slower by design |
| NG7 | Per-tenant dedicated ClickHouse clusters | Shared infrastructure with logical isolation; dedicated clusters are a future enterprise add-on |

---

## 3. Storage Architecture

### 3.1 Three-Tier Architecture

The RayOlly storage engine uses a three-tier architecture designed to balance query performance against storage cost. Data flows from hot to warm to cold based on configurable policies.

```
                        Data Flow: Ingest → Hot → Warm → Cold → Archive/Delete

 ┌─────────────────────────────────────────────────────────────────────────────────┐
 │                          RayOlly Storage Engine                                 │
 │                                                                                 │
 │  INGEST                                                                         │
 │    │                                                                            │
 │    ▼                                                                            │
 │  ┌────────────────────────────────────────┐                                     │
 │  │           HOT TIER (0-3 days)          │  Performance: ★★★★★                 │
 │  │                                        │  Cost:        $$$$                   │
 │  │  ┌──────────────────────────────────┐  │                                     │
 │  │  │        ClickHouse Cluster        │  │  Storage: NVMe SSD                  │
 │  │  │                                  │  │  Compression: LZ4 (fast)            │
 │  │  │  Shard 1    Shard 2    Shard N   │  │  Replication: 2x                    │
 │  │  │  ┌──────┐  ┌──────┐  ┌──────┐   │  │  Capacity: ~10TB per shard          │
 │  │  │  │ R1   │  │ R1   │  │ R1   │   │  │                                     │
 │  │  │  │ R2   │  │ R2   │  │ R2   │   │  │  Write: 1M rows/sec/shard           │
 │  │  │  └──────┘  └──────┘  └──────┘   │  │  Read:  p50 < 200ms                 │
 │  │  └──────────────────────────────────┘  │                                     │
 │  └─────────────────┬──────────────────────┘                                     │
 │                    │  Tiering Policy: age > 3d OR disk_usage > 80%              │
 │                    ▼                                                             │
 │  ┌────────────────────────────────────────┐                                     │
 │  │          WARM TIER (3-30 days)         │  Performance: ★★★☆☆                 │
 │  │                                        │  Cost:        $$                     │
 │  │  ┌──────────────────────────────────┐  │                                     │
 │  │  │    ClickHouse (Cold Volumes)     │  │  Storage: EBS gp3 / HDD            │
 │  │  │                                  │  │  Compression: ZSTD (high ratio)     │
 │  │  │  Same table engine, different    │  │  Replication: 2x                    │
 │  │  │  storage policy. Parts moved     │  │  Capacity: ~50TB per shard          │
 │  │  │  via ALTER TABLE MOVE PARTITION  │  │                                     │
 │  │  └──────────────────────────────────┘  │  Read:  p50 < 2s                    │
 │  └─────────────────┬──────────────────────┘                                     │
 │                    │  Tiering Policy: age > 30d OR access_count < 10/day        │
 │                    ▼                                                             │
 │  ┌────────────────────────────────────────┐                                     │
 │  │          COLD TIER (30+ days)          │  Performance: ★☆☆☆☆                 │
 │  │                                        │  Cost:        $                      │
 │  │  ┌──────────────────────────────────┐  │                                     │
 │  │  │     S3 / MinIO Object Storage    │  │  Storage: Object Storage             │
 │  │  │                                  │  │  Format:  Apache Parquet             │
 │  │  │  Parquet files organized by:     │  │  Catalog: Apache Iceberg             │
 │  │  │  /tenant/data_type/YYYY/MM/DD/HH│  │  Compression: ZSTD level 9           │
 │  │  │                                  │  │  Query: DuckDB engine                │
 │  │  │  Iceberg metadata catalog for    │  │                                     │
 │  │  │  schema evolution & time travel  │  │  Read:  p50 < 10s                   │
 │  │  └──────────────────────────────────┘  │                                     │
 │  └────────────────────────────────────────┘                                     │
 │                                                                                 │
 │  ┌────────────────────────────────────────────────────────────────────────────┐ │
 │  │                     Lifecycle Manager (Daemon)                             │ │
 │  │                                                                            │ │
 │  │  ┌─────────┐  ┌───────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐  │ │
 │  │  │ Tiering │  │ Compaction│  │   TTL    │  │Compliance│  │  GDPR     │  │ │
 │  │  │ Engine  │  │ Manager   │  │ Enforcer │  │  Hold    │  │  Erasure  │  │ │
 │  │  └─────────┘  └───────────┘  └──────────┘  └──────────┘  └───────────┘  │ │
 │  └────────────────────────────────────────────────────────────────────────────┘ │
 │                                                                                 │
 └─────────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Storage-Compute Separation

RayOlly separates storage concerns from compute concerns to enable independent scaling:

| Concern | Component | Scales By |
|---------|-----------|-----------|
| Write compute | ClickHouse ingest nodes | Adding shard replicas |
| Read compute | ClickHouse query nodes + DuckDB workers | Adding read replicas / DuckDB pool |
| Hot storage | NVMe volumes attached to ClickHouse | Adding shards |
| Warm storage | EBS gp3 volumes (detachable) | Volume size increase |
| Cold storage | S3/MinIO buckets | Unlimited (object storage) |
| Metadata | ClickHouse Keeper / Iceberg catalog | Keeper quorum size |

In self-hosted deployments, compute and storage may be co-located on the same nodes. In the SaaS deployment, storage volumes are network-attached, allowing true separation.

### 3.3 Data Flow — Ingest to Storage

```
  NATS JetStream (from PRD-01)
          │
          │  Batch consumer (1000 rows or 1s, whichever first)
          ▼
  ┌───────────────────────────────┐
  │     Storage Writer Service     │
  │                                │
  │  1. Deserialize protobuf/JSON │
  │  2. Map to internal schema    │
  │  3. Partition by data_type    │
  │  4. Assign tenant_id          │
  │  5. Batch by partition key    │
  └───────────┬───────────────────┘
              │
              │  Native ClickHouse protocol (TCP 9000)
              │  Async insert with deduplication token
              ▼
  ┌───────────────────────────────┐
  │   ClickHouse (Distributed)    │
  │                                │
  │  Distributed table routes to  │
  │  correct shard via:           │
  │    cityHash64(tenant_id)      │
  └───────────────────────────────┘
```

---

## 4. Hot Tier — ClickHouse

### 4.1 Cluster Topology

The ClickHouse cluster uses a replicated-shard topology. Each shard consists of two replicas for high availability. Shards are added horizontally to increase write throughput and storage capacity.

```
                    ClickHouse Cluster: "rayolly_cluster"
  ┌─────────────────────────────────────────────────────────────┐
  │                                                              │
  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
  │  │   Shard 01   │  │   Shard 02   │  │   Shard N    │      │
  │  │              │  │              │  │              │      │
  │  │ ┌──────────┐ │  │ ┌──────────┐ │  │ ┌──────────┐ │      │
  │  │ │Replica 1 │ │  │ │Replica 1 │ │  │ │Replica 1 │ │      │
  │  │ │ (chi-01a)│ │  │ │ (chi-02a)│ │  │ │ (chi-Na) │ │      │
  │  │ └──────────┘ │  │ └──────────┘ │  │ └──────────┘ │      │
  │  │ ┌──────────┐ │  │ ┌──────────┐ │  │ ┌──────────┐ │      │
  │  │ │Replica 2 │ │  │ │Replica 2 │ │  │ │Replica 2 │ │      │
  │  │ │ (chi-01b)│ │  │ │ (chi-02b)│ │  │ │ (chi-Nb) │ │      │
  │  │ └──────────┘ │  │ └──────────┘ │  │ └──────────┘ │      │
  │  └──────────────┘  └──────────────┘  └──────────────┘      │
  │                                                              │
  │  ┌──────────────────────────────────────┐                   │
  │  │       ClickHouse Keeper Quorum       │                   │
  │  │  ┌──────┐  ┌──────┐  ┌──────┐       │                   │
  │  │  │ KP-1 │  │ KP-2 │  │ KP-3 │       │                   │
  │  │  └──────┘  └──────┘  └──────┘       │                   │
  │  └──────────────────────────────────────┘                   │
  │                                                              │
  └─────────────────────────────────────────────────────────────┘
```

### 4.2 Database and Schema Organization

```sql
-- Database per data type for clear namespace separation
CREATE DATABASE IF NOT EXISTS rayolly_logs ON CLUSTER rayolly_cluster;
CREATE DATABASE IF NOT EXISTS rayolly_metrics ON CLUSTER rayolly_cluster;
CREATE DATABASE IF NOT EXISTS rayolly_traces ON CLUSTER rayolly_cluster;
CREATE DATABASE IF NOT EXISTS rayolly_events ON CLUSTER rayolly_cluster;
CREATE DATABASE IF NOT EXISTS rayolly_meta ON CLUSTER rayolly_cluster;
```

### 4.3 Table Design: Logs

```sql
-- Local table on each shard (ReplicatedMergeTree)
CREATE TABLE rayolly_logs.logs_local ON CLUSTER rayolly_cluster
(
    -- Primary identification
    `tenant_id`         LowCardinality(String)   CODEC(ZSTD(1)),
    `log_id`            UUID                     DEFAULT generateUUIDv4(),

    -- Timestamp (primary sort dimension)
    `timestamp`         DateTime64(9, 'UTC')     CODEC(DoubleDelta, ZSTD(1)),
    `observed_timestamp` DateTime64(9, 'UTC')    CODEC(DoubleDelta, ZSTD(1)),

    -- OpenTelemetry fields
    `trace_id`          String                   CODEC(ZSTD(1)),
    `span_id`           String                   CODEC(ZSTD(1)),
    `trace_flags`       UInt8                    CODEC(T64, ZSTD(1)),

    -- Severity (OTEL severity number 1-24)
    `severity_number`   UInt8                    CODEC(T64, ZSTD(1)),
    `severity_text`     LowCardinality(String)   CODEC(ZSTD(1)),

    -- Body
    `body`              String                   CODEC(ZSTD(3)),

    -- Resource attributes (service info)
    `resource_schema_url`   String               CODEC(ZSTD(1)),
    `resource_attributes`   Map(LowCardinality(String), String) CODEC(ZSTD(1)),
    `service_name`      LowCardinality(String)   CODEC(ZSTD(1)),
    `service_namespace` LowCardinality(String)   CODEC(ZSTD(1)),
    `service_version`   LowCardinality(String)   CODEC(ZSTD(1)),

    -- Scope (instrumentation scope)
    `scope_name`        LowCardinality(String)   CODEC(ZSTD(1)),
    `scope_version`     LowCardinality(String)   CODEC(ZSTD(1)),

    -- Log attributes (arbitrary key-value pairs)
    `attributes`        Map(LowCardinality(String), String) CODEC(ZSTD(1)),

    -- Derived / enriched fields
    `source`            LowCardinality(String)   CODEC(ZSTD(1)),
    `host_name`         LowCardinality(String)   CODEC(ZSTD(1)),
    `host_ip`           IPv4                     CODEC(ZSTD(1)),
    `k8s_namespace`     LowCardinality(String)   CODEC(ZSTD(1)),
    `k8s_pod_name`      LowCardinality(String)   CODEC(ZSTD(1)),
    `k8s_container_name` LowCardinality(String)  CODEC(ZSTD(1)),

    -- Ingestion metadata
    `ingested_at`       DateTime64(3, 'UTC')     DEFAULT now64(3) CODEC(DoubleDelta, ZSTD(1)),

    -- Projection for materialized columns
    `_date`             Date                     MATERIALIZED toDate(timestamp),
    `_hour`             UInt8                    MATERIALIZED toHour(timestamp)
)
ENGINE = ReplicatedMergeTree(
    '/clickhouse/tables/{shard}/rayolly_logs/logs_local',
    '{replica}'
)
PARTITION BY (tenant_id, toYYYYMMDD(timestamp))
ORDER BY (tenant_id, service_name, severity_number, timestamp)
TTL timestamp + INTERVAL 3 DAY TO VOLUME 'warm',
    timestamp + INTERVAL 30 DAY DELETE
SETTINGS
    index_granularity = 8192,
    ttl_only_drop_parts = 1,
    storage_policy = 'tiered',
    merge_with_ttl_timeout = 3600,
    min_bytes_for_wide_part = 10485760;

-- Skip indexes for fast filtering
ALTER TABLE rayolly_logs.logs_local
    ADD INDEX idx_body body TYPE tokenbf_v1(30720, 3, 0) GRANULARITY 1,
    ADD INDEX idx_trace_id trace_id TYPE bloom_filter(0.01) GRANULARITY 1,
    ADD INDEX idx_service_name service_name TYPE set(100) GRANULARITY 4,
    ADD INDEX idx_severity severity_number TYPE minmax GRANULARITY 1,
    ADD INDEX idx_host_name host_name TYPE set(1000) GRANULARITY 4,
    ADD INDEX idx_k8s_namespace k8s_namespace TYPE set(100) GRANULARITY 4;

-- Distributed table for cross-shard queries
CREATE TABLE rayolly_logs.logs ON CLUSTER rayolly_cluster AS rayolly_logs.logs_local
ENGINE = Distributed(
    'rayolly_cluster',
    'rayolly_logs',
    'logs_local',
    cityHash64(tenant_id)
);
```

### 4.4 Table Design: Metrics

```sql
CREATE TABLE rayolly_metrics.metrics_local ON CLUSTER rayolly_cluster
(
    -- Primary identification
    `tenant_id`         LowCardinality(String)   CODEC(ZSTD(1)),
    `metric_id`         UUID                     DEFAULT generateUUIDv4(),

    -- Timestamp
    `timestamp`         DateTime64(3, 'UTC')     CODEC(DoubleDelta, ZSTD(1)),

    -- Metric identity
    `metric_name`       LowCardinality(String)   CODEC(ZSTD(1)),
    `metric_description` String                  CODEC(ZSTD(1)),
    `metric_unit`       LowCardinality(String)   CODEC(ZSTD(1)),

    -- Metric type: 1=Gauge, 2=Sum, 3=Histogram, 4=ExponentialHistogram, 5=Summary
    `metric_type`       Enum8(
                            'gauge' = 1,
                            'sum' = 2,
                            'histogram' = 3,
                            'exponential_histogram' = 4,
                            'summary' = 5
                        )                        CODEC(ZSTD(1)),

    -- Value fields (only one populated per row based on metric_type)
    `value_float`       Float64                  CODEC(Gorilla, ZSTD(1)),
    `value_int`         Int64                    CODEC(DoubleDelta, ZSTD(1)),

    -- Sum-specific fields
    `is_monotonic`      Bool                     CODEC(ZSTD(1)),
    `aggregation_temporality` Enum8(
                            'unspecified' = 0,
                            'delta' = 1,
                            'cumulative' = 2
                        )                        CODEC(ZSTD(1)),

    -- Histogram fields
    `histogram_count`       UInt64               CODEC(DoubleDelta, ZSTD(1)),
    `histogram_sum`         Float64              CODEC(Gorilla, ZSTD(1)),
    `histogram_min`         Float64              CODEC(Gorilla, ZSTD(1)),
    `histogram_max`         Float64              CODEC(Gorilla, ZSTD(1)),
    `histogram_bucket_counts` Array(UInt64)      CODEC(ZSTD(1)),
    `histogram_explicit_bounds` Array(Float64)   CODEC(ZSTD(1)),

    -- Labels / attributes
    `labels`            Map(LowCardinality(String), String) CODEC(ZSTD(1)),

    -- Resource attributes
    `resource_attributes`   Map(LowCardinality(String), String) CODEC(ZSTD(1)),
    `service_name`      LowCardinality(String)   CODEC(ZSTD(1)),
    `service_namespace` LowCardinality(String)   CODEC(ZSTD(1)),
    `host_name`         LowCardinality(String)   CODEC(ZSTD(1)),

    -- Scope
    `scope_name`        LowCardinality(String)   CODEC(ZSTD(1)),
    `scope_version`     LowCardinality(String)   CODEC(ZSTD(1)),

    -- Ingestion metadata
    `ingested_at`       DateTime64(3, 'UTC')     DEFAULT now64(3) CODEC(DoubleDelta, ZSTD(1)),

    -- Projections
    `_date`             Date                     MATERIALIZED toDate(timestamp)
)
ENGINE = ReplicatedMergeTree(
    '/clickhouse/tables/{shard}/rayolly_metrics/metrics_local',
    '{replica}'
)
PARTITION BY (tenant_id, toYYYYMMDD(timestamp))
ORDER BY (tenant_id, metric_name, service_name, host_name, timestamp)
TTL timestamp + INTERVAL 3 DAY TO VOLUME 'warm',
    timestamp + INTERVAL 90 DAY DELETE
SETTINGS
    index_granularity = 8192,
    ttl_only_drop_parts = 1,
    storage_policy = 'tiered';

-- Skip indexes
ALTER TABLE rayolly_metrics.metrics_local
    ADD INDEX idx_metric_name metric_name TYPE set(500) GRANULARITY 4,
    ADD INDEX idx_service_name service_name TYPE set(100) GRANULARITY 4,
    ADD INDEX idx_host_name host_name TYPE set(1000) GRANULARITY 4;

-- Distributed table
CREATE TABLE rayolly_metrics.metrics ON CLUSTER rayolly_cluster
AS rayolly_metrics.metrics_local
ENGINE = Distributed(
    'rayolly_cluster',
    'rayolly_metrics',
    'metrics_local',
    cityHash64(tenant_id)
);
```

### 4.5 Table Design: Traces (Spans)

```sql
CREATE TABLE rayolly_traces.spans_local ON CLUSTER rayolly_cluster
(
    -- Primary identification
    `tenant_id`         LowCardinality(String)   CODEC(ZSTD(1)),

    -- Trace context
    `trace_id`          FixedString(32)          CODEC(ZSTD(1)),
    `span_id`           FixedString(16)          CODEC(ZSTD(1)),
    `parent_span_id`    FixedString(16)          CODEC(ZSTD(1)),
    `trace_state`       String                   CODEC(ZSTD(1)),

    -- Span identity
    `span_name`         LowCardinality(String)   CODEC(ZSTD(1)),
    `span_kind`         Enum8(
                            'UNSPECIFIED' = 0,
                            'INTERNAL' = 1,
                            'SERVER' = 2,
                            'CLIENT' = 3,
                            'PRODUCER' = 4,
                            'CONSUMER' = 5
                        )                        CODEC(ZSTD(1)),

    -- Timing
    `start_time`        DateTime64(9, 'UTC')     CODEC(DoubleDelta, ZSTD(1)),
    `end_time`          DateTime64(9, 'UTC')     CODEC(DoubleDelta, ZSTD(1)),
    `duration_ns`       UInt64                   CODEC(DoubleDelta, ZSTD(1)),

    -- Status
    `status_code`       Enum8(
                            'UNSET' = 0,
                            'OK' = 1,
                            'ERROR' = 2
                        )                        CODEC(ZSTD(1)),
    `status_message`    String                   CODEC(ZSTD(1)),

    -- Attributes
    `attributes`        Map(LowCardinality(String), String) CODEC(ZSTD(1)),

    -- Resource attributes
    `resource_attributes`   Map(LowCardinality(String), String) CODEC(ZSTD(1)),
    `service_name`      LowCardinality(String)   CODEC(ZSTD(1)),
    `service_namespace` LowCardinality(String)   CODEC(ZSTD(1)),
    `service_version`   LowCardinality(String)   CODEC(ZSTD(1)),

    -- Scope
    `scope_name`        LowCardinality(String)   CODEC(ZSTD(1)),
    `scope_version`     LowCardinality(String)   CODEC(ZSTD(1)),

    -- Span events (exceptions, logs within span)
    `events.timestamp`      Array(DateTime64(9, 'UTC'))  CODEC(ZSTD(1)),
    `events.name`           Array(LowCardinality(String)) CODEC(ZSTD(1)),
    `events.attributes`     Array(Map(LowCardinality(String), String)) CODEC(ZSTD(1)),

    -- Span links (cross-trace references)
    `links.trace_id`        Array(FixedString(32)) CODEC(ZSTD(1)),
    `links.span_id`         Array(FixedString(16)) CODEC(ZSTD(1)),
    `links.trace_state`     Array(String)          CODEC(ZSTD(1)),
    `links.attributes`      Array(Map(LowCardinality(String), String)) CODEC(ZSTD(1)),

    -- Derived / enriched
    `has_error`         Bool                     MATERIALIZED status_code = 'ERROR',
    `host_name`         LowCardinality(String)   CODEC(ZSTD(1)),

    -- Ingestion metadata
    `ingested_at`       DateTime64(3, 'UTC')     DEFAULT now64(3) CODEC(DoubleDelta, ZSTD(1)),

    -- Projections
    `_date`             Date                     MATERIALIZED toDate(start_time)
)
ENGINE = ReplicatedMergeTree(
    '/clickhouse/tables/{shard}/rayolly_traces/spans_local',
    '{replica}'
)
PARTITION BY (tenant_id, toYYYYMMDD(start_time))
ORDER BY (tenant_id, service_name, span_name, start_time)
TTL start_time + INTERVAL 3 DAY TO VOLUME 'warm',
    start_time + INTERVAL 14 DAY DELETE
SETTINGS
    index_granularity = 8192,
    ttl_only_drop_parts = 1,
    storage_policy = 'tiered';

-- Skip indexes
ALTER TABLE rayolly_traces.spans_local
    ADD INDEX idx_trace_id trace_id TYPE bloom_filter(0.001) GRANULARITY 1,
    ADD INDEX idx_service_name service_name TYPE set(100) GRANULARITY 4,
    ADD INDEX idx_span_name span_name TYPE set(500) GRANULARITY 4,
    ADD INDEX idx_status_code status_code TYPE set(3) GRANULARITY 4,
    ADD INDEX idx_duration duration_ns TYPE minmax GRANULARITY 1;

-- Distributed table
CREATE TABLE rayolly_traces.spans ON CLUSTER rayolly_cluster
AS rayolly_traces.spans_local
ENGINE = Distributed(
    'rayolly_cluster',
    'rayolly_traces',
    'spans_local',
    cityHash64(tenant_id)
);
```

### 4.6 Table Design: Events

```sql
CREATE TABLE rayolly_events.events_local ON CLUSTER rayolly_cluster
(
    -- Primary identification
    `tenant_id`         LowCardinality(String)   CODEC(ZSTD(1)),
    `event_id`          UUID                     DEFAULT generateUUIDv4(),

    -- Timestamp
    `timestamp`         DateTime64(3, 'UTC')     CODEC(DoubleDelta, ZSTD(1)),

    -- Event classification
    `event_type`        LowCardinality(String)   CODEC(ZSTD(1)),
        -- deployment, scaling, config_change, alert, incident, custom
    `event_source`      LowCardinality(String)   CODEC(ZSTD(1)),
        -- kubernetes, ci_cd, terraform, manual, agent
    `event_severity`    Enum8(
                            'info' = 1,
                            'warning' = 2,
                            'error' = 3,
                            'critical' = 4
                        )                        CODEC(ZSTD(1)),

    -- Event content
    `title`             String                   CODEC(ZSTD(1)),
    `body`              String                   CODEC(ZSTD(3)),

    -- Context
    `service_name`      LowCardinality(String)   CODEC(ZSTD(1)),
    `environment`       LowCardinality(String)   CODEC(ZSTD(1)),
    `host_name`         LowCardinality(String)   CODEC(ZSTD(1)),

    -- Attributes (arbitrary key-value)
    `attributes`        Map(LowCardinality(String), String) CODEC(ZSTD(1)),

    -- Correlation
    `trace_id`          String                   CODEC(ZSTD(1)),
    `related_event_ids` Array(UUID)              CODEC(ZSTD(1)),

    -- Tags for filtering
    `tags`              Array(LowCardinality(String)) CODEC(ZSTD(1)),

    -- Ingestion metadata
    `ingested_at`       DateTime64(3, 'UTC')     DEFAULT now64(3) CODEC(DoubleDelta, ZSTD(1)),

    -- Projections
    `_date`             Date                     MATERIALIZED toDate(timestamp)
)
ENGINE = ReplicatedMergeTree(
    '/clickhouse/tables/{shard}/rayolly_events/events_local',
    '{replica}'
)
PARTITION BY (tenant_id, toYYYYMMDD(timestamp))
ORDER BY (tenant_id, event_type, service_name, timestamp)
TTL timestamp + INTERVAL 3 DAY TO VOLUME 'warm',
    timestamp + INTERVAL 90 DAY DELETE
SETTINGS
    index_granularity = 8192,
    ttl_only_drop_parts = 1,
    storage_policy = 'tiered';

-- Skip indexes
ALTER TABLE rayolly_events.events_local
    ADD INDEX idx_event_type event_type TYPE set(50) GRANULARITY 4,
    ADD INDEX idx_service_name service_name TYPE set(100) GRANULARITY 4,
    ADD INDEX idx_title title TYPE tokenbf_v1(10240, 3, 0) GRANULARITY 1,
    ADD INDEX idx_tags tags TYPE bloom_filter(0.01) GRANULARITY 1;

-- Distributed table
CREATE TABLE rayolly_events.events ON CLUSTER rayolly_cluster
AS rayolly_events.events_local
ENGINE = Distributed(
    'rayolly_cluster',
    'rayolly_events',
    'events_local',
    cityHash64(tenant_id)
);
```

### 4.7 Materialized Views for Common Aggregations

```sql
-- Materialized view: Log volume by service (per-minute rollup)
CREATE MATERIALIZED VIEW rayolly_logs.logs_volume_per_minute_mv
ON CLUSTER rayolly_cluster
TO rayolly_logs.logs_volume_per_minute
AS SELECT
    tenant_id,
    service_name,
    severity_number,
    toStartOfMinute(timestamp) AS minute,
    count()                     AS log_count,
    sum(length(body))           AS total_bytes
FROM rayolly_logs.logs_local
GROUP BY tenant_id, service_name, severity_number, minute;

CREATE TABLE rayolly_logs.logs_volume_per_minute ON CLUSTER rayolly_cluster
(
    `tenant_id`         LowCardinality(String),
    `service_name`      LowCardinality(String),
    `severity_number`   UInt8,
    `minute`            DateTime,
    `log_count`         AggregateFunction(count, UInt64),
    `total_bytes`       AggregateFunction(sum, UInt64)
)
ENGINE = ReplicatedAggregatingMergeTree(
    '/clickhouse/tables/{shard}/rayolly_logs/logs_volume_per_minute',
    '{replica}'
)
PARTITION BY (tenant_id, toYYYYMMDD(minute))
ORDER BY (tenant_id, service_name, severity_number, minute)
TTL minute + INTERVAL 90 DAY DELETE;

-- Materialized view: Metric rollups (5-minute aggregation)
CREATE MATERIALIZED VIEW rayolly_metrics.metrics_5min_rollup_mv
ON CLUSTER rayolly_cluster
TO rayolly_metrics.metrics_5min_rollup
AS SELECT
    tenant_id,
    metric_name,
    service_name,
    host_name,
    toStartOfFiveMinutes(timestamp)  AS interval_start,
    avg(value_float)                  AS avg_value,
    min(value_float)                  AS min_value,
    max(value_float)                  AS max_value,
    count()                           AS sample_count,
    quantileState(0.5)(value_float)   AS p50_state,
    quantileState(0.95)(value_float)  AS p95_state,
    quantileState(0.99)(value_float)  AS p99_state
FROM rayolly_metrics.metrics_local
WHERE metric_type IN ('gauge', 'sum')
GROUP BY tenant_id, metric_name, service_name, host_name, interval_start;

CREATE TABLE rayolly_metrics.metrics_5min_rollup ON CLUSTER rayolly_cluster
(
    `tenant_id`         LowCardinality(String),
    `metric_name`       LowCardinality(String),
    `service_name`      LowCardinality(String),
    `host_name`         LowCardinality(String),
    `interval_start`    DateTime,
    `avg_value`         AggregateFunction(avg, Float64),
    `min_value`         AggregateFunction(min, Float64),
    `max_value`         AggregateFunction(max, Float64),
    `sample_count`      AggregateFunction(count, UInt64),
    `p50_state`         AggregateFunction(quantile(0.5), Float64),
    `p95_state`         AggregateFunction(quantile(0.95), Float64),
    `p99_state`         AggregateFunction(quantile(0.99), Float64)
)
ENGINE = ReplicatedAggregatingMergeTree(
    '/clickhouse/tables/{shard}/rayolly_metrics/metrics_5min_rollup',
    '{replica}'
)
PARTITION BY (tenant_id, toYYYYMMDD(interval_start))
ORDER BY (tenant_id, metric_name, service_name, host_name, interval_start)
TTL interval_start + INTERVAL 365 DAY DELETE;

-- Materialized view: Service latency from traces (per-minute)
CREATE MATERIALIZED VIEW rayolly_traces.service_latency_per_minute_mv
ON CLUSTER rayolly_cluster
TO rayolly_traces.service_latency_per_minute
AS SELECT
    tenant_id,
    service_name,
    span_name,
    span_kind,
    toStartOfMinute(start_time)      AS minute,
    count()                           AS request_count,
    countIf(status_code = 'ERROR')    AS error_count,
    avg(duration_ns)                  AS avg_duration_ns,
    max(duration_ns)                  AS max_duration_ns,
    quantileState(0.5)(duration_ns)   AS p50_state,
    quantileState(0.95)(duration_ns)  AS p95_state,
    quantileState(0.99)(duration_ns)  AS p99_state
FROM rayolly_traces.spans_local
WHERE span_kind IN ('SERVER', 'CONSUMER')
GROUP BY tenant_id, service_name, span_name, span_kind, minute;

CREATE TABLE rayolly_traces.service_latency_per_minute ON CLUSTER rayolly_cluster
(
    `tenant_id`         LowCardinality(String),
    `service_name`      LowCardinality(String),
    `span_name`         LowCardinality(String),
    `span_kind`         Enum8('UNSPECIFIED'=0,'INTERNAL'=1,'SERVER'=2,'CLIENT'=3,'PRODUCER'=4,'CONSUMER'=5),
    `minute`            DateTime,
    `request_count`     AggregateFunction(count, UInt64),
    `error_count`       AggregateFunction(count, UInt64),
    `avg_duration_ns`   AggregateFunction(avg, UInt64),
    `max_duration_ns`   AggregateFunction(max, UInt64),
    `p50_state`         AggregateFunction(quantile(0.5), UInt64),
    `p95_state`         AggregateFunction(quantile(0.95), UInt64),
    `p99_state`         AggregateFunction(quantile(0.99), UInt64)
)
ENGINE = ReplicatedAggregatingMergeTree(
    '/clickhouse/tables/{shard}/rayolly_traces/service_latency_per_minute',
    '{replica}'
)
PARTITION BY (tenant_id, toYYYYMMDD(minute))
ORDER BY (tenant_id, service_name, span_name, span_kind, minute)
TTL minute + INTERVAL 90 DAY DELETE;
```

### 4.8 MergeTree Engine Family Selection

| Table | Engine | Rationale |
|-------|--------|-----------|
| logs_local | ReplicatedMergeTree | Standard append-only workload; no deduplication needed (log_id is unique) |
| metrics_local | ReplicatedMergeTree | Raw metric samples; no dedup at storage level (dedup at ingest) |
| spans_local | ReplicatedMergeTree | Standard append-only spans |
| events_local | ReplicatedMergeTree | Low-volume event data |
| logs_volume_per_minute | ReplicatedAggregatingMergeTree | Pre-aggregated rollups; merges aggregate states on compaction |
| metrics_5min_rollup | ReplicatedAggregatingMergeTree | Pre-aggregated metric rollups with quantile states |
| service_latency_per_minute | ReplicatedAggregatingMergeTree | Pre-aggregated trace latency rollups |

For event-sourced data where late-arriving data may update existing rows, `ReplacingMergeTree` can be used with the `ingested_at` column as the version field. This is reserved for future use cases (e.g., span updates, event corrections).

### 4.9 Partition Strategy

All primary tables are partitioned by `(tenant_id, toYYYYMMDD(timestamp))`:

- **tenant_id as partition prefix**: Enables efficient `DROP PARTITION` for tenant offboarding, per-tenant TTL, and partition-level data isolation. ClickHouse prunes partitions when `tenant_id` appears in `WHERE`.
- **Day-level time partitioning**: Balances partition count against pruning efficiency. Hourly partitioning would create too many parts for high-cardinality tenants. Weekly partitioning would make TTL too coarse.

**Partition naming convention**: `{tenant_id}-{YYYYMMDD}` (e.g., `acme-corp-20260319`).

**Partition management rules**:
- Maximum active partitions per table: 10,000 (enforced by monitoring, not a hard limit)
- Partitions older than TTL are dropped, not deleted row-by-row
- `ttl_only_drop_parts = 1` ensures entire parts are dropped, avoiding expensive row-level deletes

### 4.10 Index Design

**Primary key** (ORDER BY clause — the primary index in ClickHouse):

| Table | ORDER BY | Rationale |
|-------|----------|-----------|
| logs | (tenant_id, service_name, severity_number, timestamp) | Tenants always filter by tenant; most queries filter by service then severity |
| metrics | (tenant_id, metric_name, service_name, host_name, timestamp) | Metric queries always specify metric name, often filtered by service/host |
| spans | (tenant_id, service_name, span_name, start_time) | Trace queries target a service and endpoint |
| events | (tenant_id, event_type, service_name, timestamp) | Events are browsed by type within a service |

**Skip indexes**:

| Index Type | Used For | Granularity |
|-----------|----------|-------------|
| `tokenbf_v1` | Full-text token search on `body`, `title` | 1 (every granule) |
| `bloom_filter` | High-cardinality exact match: `trace_id`, `tags` | 1 |
| `set` | Low-cardinality exact match: `service_name`, `host_name` | 4 |
| `minmax` | Range queries: `severity_number`, `duration_ns` | 1 |

### 4.11 Compression Codecs

| Column Type | Codec Chain | Expected Ratio | Notes |
|-------------|-------------|-----------------|-------|
| Timestamps (DateTime64) | DoubleDelta + ZSTD(1) | 50:1 to 100:1 | DoubleDelta exploits monotonic time |
| Metric values (Float64) | Gorilla + ZSTD(1) | 10:1 to 30:1 | Gorilla XOR for time-series floats |
| Counter integers | DoubleDelta + ZSTD(1) | 30:1 to 50:1 | Monotonically increasing counters |
| Low-cardinality strings | LowCardinality + ZSTD(1) | 50:1 to 200:1 | Dictionary encoding + compression |
| Log body (high entropy) | ZSTD(3) | 5:1 to 10:1 | Higher ZSTD level for bulky text |
| UUIDs | ZSTD(1) | 3:1 to 5:1 | Random data, limited compressibility |
| Map columns | ZSTD(1) | 10:1 to 20:1 | Key repetition aids compression |
| Boolean / Enum | ZSTD(1) | 100:1+ | Tiny values, highly compressible |
| IPv4 | ZSTD(1) | 10:1 to 20:1 | 4-byte fixed, good locality |

### 4.12 Replication and Sharding Strategy

**Sharding**: Data is distributed across shards using `cityHash64(tenant_id)`. This ensures all data for a single tenant lands on the same shard, enabling efficient local queries without cross-shard joins.

**Replication**: Each shard has 2 replicas (configurable). Replicas use ClickHouse's built-in `ReplicatedMergeTree` replication via ClickHouse Keeper, providing:
- Synchronous replication for writes (configurable: `insert_quorum = 2` for strong consistency, or `1` for performance)
- Automatic failover for reads
- No external replication tool needed

**Shard allocation policy**:
- New tenants are assigned to the shard with the lowest current data volume
- Large tenants (>1TB/day) may be assigned a dedicated shard
- Shard rebalancing is manual (planned: automated rebalancing in Phase 4)

### 4.13 Query Performance Optimization

**Configuration for query performance**:

```xml
<!-- /etc/clickhouse-server/users.d/rayolly_query_settings.xml -->
<clickhouse>
    <profiles>
        <default>
            <!-- Parallel query execution -->
            <max_threads>16</max_threads>
            <max_block_size>65536</max_block_size>

            <!-- Memory limits per query -->
            <max_memory_usage>10737418240</max_memory_usage> <!-- 10GB -->
            <max_memory_usage_for_user>21474836480</max_memory_usage_for_user> <!-- 20GB -->

            <!-- Query timeout -->
            <max_execution_time>300</max_execution_time> <!-- 5 min -->

            <!-- Distributed query settings -->
            <distributed_product_mode>global</distributed_product_mode>
            <prefer_localhost_replica>1</prefer_localhost_replica>

            <!-- Read optimization -->
            <use_uncompressed_cache>1</use_uncompressed_cache>
            <merge_tree_min_rows_for_concurrent_read>100000</merge_tree_min_rows_for_concurrent_read>

            <!-- Skip index usage -->
            <force_index_by_date>0</force_index_by_date>

            <!-- Output limits -->
            <max_result_rows>1000000</max_result_rows>
            <result_overflow_mode>throw</result_overflow_mode>
        </default>

        <!-- Profile for heavy analytical queries (AI/ML engine) -->
        <analytical>
            <max_memory_usage>32212254720</max_memory_usage> <!-- 30GB -->
            <max_execution_time>600</max_execution_time>
            <max_threads>32</max_threads>
        </analytical>

        <!-- Profile for real-time tail queries -->
        <realtime>
            <max_execution_time>30</max_execution_time>
            <max_memory_usage>1073741824</max_memory_usage> <!-- 1GB -->
            <max_threads>4</max_threads>
        </realtime>
    </profiles>
</clickhouse>
```

---

## 5. Warm Tier — ClickHouse Cold Storage

### 5.1 Storage Policy Configuration

ClickHouse supports multiple storage volumes within a single table via storage policies. Data is transparently moved between volumes based on TTL rules.

```xml
<!-- /etc/clickhouse-server/config.d/storage_policy.xml -->
<clickhouse>
    <storage_configuration>
        <disks>
            <hot>
                <type>local</type>
                <path>/data/clickhouse/hot/</path>
                <!-- NVMe SSD: 3,500 MB/s read, 3,000 MB/s write -->
            </hot>
            <warm>
                <type>local</type>
                <path>/data/clickhouse/warm/</path>
                <!-- EBS gp3 or SATA SSD: 500 MB/s read, 250 MB/s write -->
            </warm>
            <cold_s3>
                <type>s3</type>
                <endpoint>https://minio.rayolly.internal:9000/rayolly-cold/</endpoint>
                <access_key_id>AKIAIOSFODNN7EXAMPLE</access_key_id>
                <secret_access_key>wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY</secret_access_key>
                <metadata_path>/data/clickhouse/s3_metadata/</metadata_path>
                <cache_enabled>true</cache_enabled>
                <data_cache_enabled>true</data_cache_enabled>
                <cache_on_write_operations>false</cache_on_write_operations>
                <max_cache_size>107374182400</max_cache_size> <!-- 100GB local cache -->
            </cold_s3>
        </disks>
        <policies>
            <tiered>
                <volumes>
                    <hot_volume>
                        <disk>hot</disk>
                        <max_data_part_size_bytes>1073741824</max_data_part_size_bytes>
                    </hot_volume>
                    <warm_volume>
                        <disk>warm</disk>
                        <max_data_part_size_bytes>10737418240</max_data_part_size_bytes>
                    </warm_volume>
                    <cold_volume>
                        <disk>cold_s3</disk>
                    </cold_volume>
                </volumes>
                <move_factor>0.1</move_factor>
                <!-- Move data when hot volume is 90% full -->
            </tiered>
        </policies>
    </storage_configuration>
</clickhouse>
```

### 5.2 Tiering Policies

| Criteria | Hot → Warm | Warm → Cold (S3) | Notes |
|----------|------------|-------------------|-------|
| Age-based (default) | > 3 days | > 30 days | Configured via TTL in table DDL |
| Disk pressure | hot volume > 80% capacity | warm volume > 85% capacity | Controlled by `move_factor` |
| Access frequency | < 100 queries/day touching partition | < 10 queries/day | Tracked by lifecycle manager daemon |
| Manual override | Admin API: `POST /api/v1/storage/tier` | Same | For compliance or cost optimization |
| Per-tenant override | Tenant config: `hot_retention_days` | Tenant config: `warm_retention_days` | Enterprise feature; overrides defaults |

### 5.3 Query Transparency

Warm data is queried identically to hot data — same SQL, same table names. ClickHouse handles the volume mapping transparently. The only difference is latency: queries touching warm partitions incur higher I/O latency (~2-5x slower for sequential scans, ~1.5x for indexed lookups).

The query engine (PRD-03) should display a `data_tier` field in query metadata so users understand latency expectations:

```sql
-- System table to check which parts are on which volume
SELECT
    partition,
    disk_name,
    sum(rows) AS total_rows,
    formatReadableSize(sum(bytes_on_disk)) AS size
FROM system.parts
WHERE database = 'rayolly_logs' AND table = 'logs_local' AND active
GROUP BY partition, disk_name
ORDER BY partition;
```

### 5.4 Automatic Data Movement

Data movement is handled by ClickHouse's built-in TTL mechanism:

```sql
-- TTL rules defined in table DDL (shown in Section 4 tables)
-- Additional: manual partition movement for ad-hoc tiering
ALTER TABLE rayolly_logs.logs_local
    MOVE PARTITION ('acme-corp', '20260315')
    TO VOLUME 'warm_volume';

-- Move all partitions older than 3 days (run by lifecycle manager cron)
-- This is handled programmatically by the Lifecycle Manager service
```

### 5.5 Recompression on Warm

When data moves to warm tier, parts can be recompressed with ZSTD at a higher level to improve storage efficiency at the cost of slightly slower decompression:

```sql
-- Modify compression codec for warm data
ALTER TABLE rayolly_logs.logs_local
    MODIFY COLUMN body CODEC(ZSTD(6))
    -- Only affects new parts; existing parts retain original codec
    -- Use OPTIMIZE TABLE ... FINAL to recompress existing parts
;
```

In practice, the Lifecycle Manager triggers `OPTIMIZE TABLE ... FINAL` on warm partitions to consolidate and recompress parts.

---

## 6. Cold Tier — Object Storage (S3/MinIO)

### 6.1 Architecture

The cold tier serves as long-term, cost-effective storage for data older than 30 days (configurable). Data is exported from ClickHouse warm tier as Apache Parquet files and cataloged using Apache Iceberg for schema evolution and time-travel queries.

```
ClickHouse (Warm Tier)
        │
        │  Export via lifecycle manager
        │  (SELECT ... INTO OUTFILE FORMAT Parquet)
        ▼
┌──────────────────────────────────────────────────────────┐
│                 Cold Tier — Object Storage                │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐ │
│  │              S3 / MinIO Bucket                       │ │
│  │                                                      │ │
│  │  s3://rayolly-cold/                                  │ │
│  │    ├── iceberg/                                       │ │
│  │    │   ├── logs/metadata/                             │ │
│  │    │   ├── metrics/metadata/                          │ │
│  │    │   ├── traces/metadata/                           │ │
│  │    │   └── events/metadata/                           │ │
│  │    └── data/                                          │ │
│  │        ├── logs/                                      │ │
│  │        │   ├── tenant=acme-corp/                      │ │
│  │        │   │   ├── date=2026-02-15/                   │ │
│  │        │   │   │   ├── hour=00/                       │ │
│  │        │   │   │   │   ├── part-00000.parquet         │ │
│  │        │   │   │   │   ├── part-00001.parquet         │ │
│  │        │   │   │   │   └── ...                        │ │
│  │        │   │   │   ├── hour=01/                       │ │
│  │        │   │   │   └── ...                            │ │
│  │        │   │   └── date=2026-02-16/                   │ │
│  │        │   └── tenant=globex-inc/                     │ │
│  │        ├── metrics/                                   │ │
│  │        │   └── (same partitioning scheme)             │ │
│  │        ├── traces/                                    │ │
│  │        │   └── (same partitioning scheme)             │ │
│  │        └── events/                                    │ │
│  │            └── (same partitioning scheme)             │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐ │
│  │         Apache Iceberg Catalog (REST)                │ │
│  │                                                      │ │
│  │  - Schema evolution tracking                         │ │
│  │  - Partition pruning metadata                        │ │
│  │  - Snapshot history (time travel)                    │ │
│  │  - Manifest files for file-level stats               │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐ │
│  │         DuckDB Query Engine (Embedded)               │ │
│  │                                                      │ │
│  │  - Query-in-place on Parquet files                   │ │
│  │  - Predicate pushdown to Parquet row groups           │ │
│  │  - Iceberg-aware partition pruning                    │ │
│  │  - Results returned via Query Engine (PRD-03)         │ │
│  └─────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

### 6.2 Parquet File Format Design

**File layout**:
- Row group size: 128MB (uncompressed target), producing ~30-50MB compressed files
- Target file size on disk: 128MB - 256MB per Parquet file
- Page size: 1MB (default Parquet data page)
- Dictionary encoding: enabled for all string columns with cardinality < 10,000

**Parquet schema** (logs example):

```
message rayolly_log {
  required binary tenant_id (STRING);
  required int64  timestamp (TIMESTAMP(NANOS, true));
  optional int64  observed_timestamp (TIMESTAMP(NANOS, true));
  optional binary trace_id (STRING);
  optional binary span_id (STRING);
  required int32  severity_number (INT(8, false));
  optional binary severity_text (STRING);
  required binary body (STRING);
  optional binary service_name (STRING);
  optional binary service_namespace (STRING);
  optional binary service_version (STRING);
  optional binary host_name (STRING);
  optional binary host_ip (STRING);
  optional binary k8s_namespace (STRING);
  optional binary k8s_pod_name (STRING);
  optional binary source (STRING);
  optional group  resource_attributes (MAP) {
    repeated group key_value {
      required binary key (STRING);
      optional binary value (STRING);
    }
  }
  optional group  attributes (MAP) {
    repeated group key_value {
      required binary key (STRING);
      optional binary value (STRING);
    }
  }
  required int64  ingested_at (TIMESTAMP(MILLIS, true));
}
```

### 6.3 Partitioning Scheme

```
s3://rayolly-cold/data/{data_type}/tenant={tenant_id}/date={YYYY-MM-DD}/hour={HH}/

Examples:
  s3://rayolly-cold/data/logs/tenant=acme-corp/date=2026-02-15/hour=00/part-00000.parquet
  s3://rayolly-cold/data/metrics/tenant=globex-inc/date=2026-02-15/hour=12/part-00000.parquet
  s3://rayolly-cold/data/traces/tenant=acme-corp/date=2026-02-15/hour=06/part-00000.parquet
```

**Partition key hierarchy**: `data_type → tenant_id → date → hour`

This hierarchy enables:
- Tenant-level data isolation (important for GDPR erasure)
- Efficient date-range pruning (most cold queries are time-bounded)
- Hour-level granularity for targeted queries without scanning full days

### 6.4 File Sizing Strategy

| Scenario | Target File Size | Row Count (approx) | Rationale |
|----------|-----------------|--------------------:|-----------|
| High-volume tenant (>1GB/hr logs) | 256MB | ~2-5M rows | Maximize sequential read throughput |
| Medium-volume tenant | 128MB | ~1-2M rows | Balance between file count and size |
| Low-volume tenant (<10MB/hr) | 64MB (minimum) | ~100K-500K rows | Avoid too many small files |

The cold tier export job batches data to meet these targets. If an hour's data for a tenant is smaller than 64MB, adjacent hours are merged into a single file spanning multiple hours (the `hour` partition key in the file path uses the first hour in the range).

### 6.5 Metadata Catalog — Apache Iceberg

Iceberg provides:
- **Schema evolution**: Add/remove/rename columns without rewriting files
- **Partition evolution**: Change partitioning without rewriting data
- **Time travel**: Query data as of a specific snapshot for audit
- **Manifest-level statistics**: Column min/max/null_count per file for predicate pushdown

```python
# Iceberg table registration (PyIceberg)
from pyiceberg.catalog import load_catalog

catalog = load_catalog("rayolly", **{
    "type": "rest",
    "uri": "http://iceberg-catalog.rayolly.internal:8181",
    "s3.endpoint": "https://minio.rayolly.internal:9000",
    "s3.access-key-id": "AKIAIOSFODNN7EXAMPLE",
    "s3.secret-access-key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
})

# Table creation for logs cold storage
from pyiceberg.schema import Schema
from pyiceberg.types import (
    StringType, TimestamptzType, IntegerType, BinaryType, MapType,
    NestedField, LongType
)
from pyiceberg.partitioning import PartitionSpec, PartitionField
from pyiceberg.transforms import IdentityTransform, DayTransform, HourTransform

logs_schema = Schema(
    NestedField(1, "tenant_id", StringType(), required=True),
    NestedField(2, "timestamp", TimestamptzType(), required=True),
    NestedField(3, "severity_number", IntegerType(), required=True),
    NestedField(4, "severity_text", StringType()),
    NestedField(5, "body", StringType(), required=True),
    NestedField(6, "service_name", StringType()),
    NestedField(7, "host_name", StringType()),
    NestedField(8, "trace_id", StringType()),
    NestedField(9, "span_id", StringType()),
    NestedField(10, "source", StringType()),
    NestedField(11, "resource_attributes", MapType(12, StringType(), 13, StringType())),
    NestedField(14, "attributes", MapType(15, StringType(), 16, StringType())),
    NestedField(17, "ingested_at", TimestamptzType(), required=True),
)

logs_partition_spec = PartitionSpec(
    PartitionField(source_id=1, field_id=1000, transform=IdentityTransform(), name="tenant_id"),
    PartitionField(source_id=2, field_id=1001, transform=DayTransform(), name="date"),
    PartitionField(source_id=2, field_id=1002, transform=HourTransform(), name="hour"),
)

catalog.create_table(
    identifier="rayolly.logs_cold",
    schema=logs_schema,
    partition_spec=logs_partition_spec,
    location="s3://rayolly-cold/data/logs/",
)
```

### 6.6 Query-in-Place via DuckDB

Cold tier data is queried using DuckDB, which provides excellent Parquet read performance and Iceberg integration:

```sql
-- DuckDB query on cold data (executed by Query Engine, PRD-03)
INSTALL iceberg;
LOAD iceberg;

SELECT
    service_name,
    severity_text,
    count(*) AS log_count
FROM iceberg_scan('s3://rayolly-cold/data/logs/', allow_moved_paths = true)
WHERE tenant_id = 'acme-corp'
  AND timestamp >= '2026-01-01'::TIMESTAMP
  AND timestamp < '2026-02-01'::TIMESTAMP
  AND severity_number >= 17  -- ERROR and above
GROUP BY service_name, severity_text
ORDER BY log_count DESC;
```

DuckDB pushes predicates down to Parquet row groups and leverages Iceberg manifest statistics to skip irrelevant files entirely.

### 6.7 Lifecycle Policies

```yaml
# lifecycle_policies.yaml — cold tier lifecycle configuration
cold_tier:
  s3:
    bucket: rayolly-cold

    # S3 lifecycle rules
    lifecycle_rules:
      - id: transition-to-glacier
        prefix: data/
        transitions:
          - days: 365          # After 1 year in S3 Standard
            storage_class: GLACIER_IR  # Glacier Instant Retrieval
          - days: 730          # After 2 years
            storage_class: DEEP_ARCHIVE
        expiration:
          days: 2555           # 7 years max (configurable per tenant)
        noncurrent_version_expiration:
          days: 30

      - id: delete-temp-files
        prefix: tmp/
        expiration:
          days: 1

    # MinIO lifecycle (for self-hosted)
    minio_lifecycle_rules:
      - id: expire-old-data
        prefix: data/
        expiration:
          days: 2555
        status: Enabled
```

---

## 7. Data Lifecycle Management

### 7.1 Lifecycle Manager Architecture

The Lifecycle Manager is a standalone service that orchestrates data movement, compaction, TTL enforcement, compliance holds, and GDPR erasure.

```
┌─────────────────────────────────────────────────────────────┐
│                    Lifecycle Manager Service                  │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Scheduler   │  │  Policy DB   │  │  Audit Log   │      │
│  │  (Cron-based) │  │ (PostgreSQL) │  │  (append-only)│      │
│  └──────┬───────┘  └──────────────┘  └──────────────┘      │
│         │                                                    │
│  ┌──────▼──────────────────────────────────────────────┐    │
│  │                    Job Executor                       │    │
│  │                                                      │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ │    │
│  │  │ Tiering  │ │Compaction│ │   TTL    │ │  GDPR  │ │    │
│  │  │  Job     │ │   Job    │ │   Job    │ │ Erasure│ │    │
│  │  └──────────┘ └──────────┘ └──────────┘ └────────┘ │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐            │    │
│  │  │Compliance│ │  Export  │ │ Recompr. │            │    │
│  │  │  Hold    │ │ to Cold  │ │   Job    │            │    │
│  │  └──────────┘ └──────────┘ └──────────┘            │    │
│  └──────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 Retention Policies

Retention policies are configurable at multiple levels, with the most specific policy winning:

```yaml
# retention_policies.yaml
defaults:
  logs:
    hot_days: 3
    warm_days: 30
    cold_days: 365
    total_max_days: 2555   # 7 years

  metrics:
    hot_days: 3
    warm_days: 90
    cold_days: 730
    total_max_days: 2555
    # Rollup retention: 5-min rollups kept for 2 years,
    # 1-hour rollups kept for 7 years
    rollup_retention:
      5min: 730
      1hour: 2555

  traces:
    hot_days: 3
    warm_days: 14
    cold_days: 90
    total_max_days: 365

  events:
    hot_days: 3
    warm_days: 90
    cold_days: 730
    total_max_days: 2555

# Per-tenant overrides
tenants:
  acme-corp:
    logs:
      hot_days: 7          # Premium tier: 7 days hot
      warm_days: 60
      cold_days: 1825      # 5 years for compliance
    compliance:
      legal_hold: false
      regulatory_retention: SOX  # 7-year retention on all data

  startup-xyz:
    logs:
      hot_days: 1          # Free tier: 1 day hot
      warm_days: 7
      cold_days: 30
      total_max_days: 30

# Per-stream overrides (within a tenant)
streams:
  acme-corp:
    "service=payment-api":
      logs:
        hot_days: 14        # Critical service: extended hot retention
        cold_days: 2555
    "severity>=ERROR":
      logs:
        hot_days: 7          # All errors kept hot longer
        cold_days: 1825
```

### 7.3 Automatic Tiering Rules Engine

The tiering engine evaluates rules every 15 minutes:

```python
# Pseudocode for tiering evaluation
class TieringEngine:
    def evaluate(self):
        for partition in self.get_hot_partitions():
            tenant_policy = self.get_policy(partition.tenant_id, partition.data_type)

            # Rule 1: Age-based tiering
            if partition.age_days > tenant_policy.hot_days:
                self.schedule_move(partition, tier='warm')
                continue

            # Rule 2: Disk pressure tiering
            if self.hot_disk_usage_pct() > 80:
                oldest = self.get_oldest_hot_partitions(count=10)
                for p in oldest:
                    self.schedule_move(p, tier='warm')

            # Rule 3: Access-frequency tiering
            if partition.queries_last_24h < 10 and partition.age_days > 1:
                self.schedule_move(partition, tier='warm')

        for partition in self.get_warm_partitions():
            tenant_policy = self.get_policy(partition.tenant_id, partition.data_type)

            # Check compliance hold before cold tiering
            if self.has_compliance_hold(partition.tenant_id):
                continue  # Do not move to cold; warm is still directly queryable

            if partition.age_days > tenant_policy.hot_days + tenant_policy.warm_days:
                self.schedule_export_to_cold(partition)
```

### 7.4 Data Compaction and Optimization

ClickHouse performs background merges automatically. The Lifecycle Manager triggers additional optimization:

```sql
-- Force compaction of old partitions (reduce part count)
OPTIMIZE TABLE rayolly_logs.logs_local
    PARTITION ('acme-corp', '20260315')
    FINAL;

-- Compact all partitions older than 7 days (run nightly)
-- Executed programmatically by Lifecycle Manager
-- Targets: reduce parts per partition to < 5
```

**Compaction schedule**:
| Action | Frequency | Target |
|--------|-----------|--------|
| ClickHouse background merge | Continuous | Automatic |
| Forced `OPTIMIZE FINAL` on warm partitions | Daily (02:00 UTC) | Parts per partition < 5 |
| Parquet file compaction (cold tier) | Weekly | Merge small files to 128-256MB target |
| Iceberg metadata compaction | Daily | Expire old snapshots, compact manifests |

### 7.5 TTL Management

TTL enforcement in ClickHouse is part-level (not row-level). The setting `ttl_only_drop_parts = 1` ensures ClickHouse only drops entire parts where all rows have expired, avoiding expensive row-level deletion.

```sql
-- View current TTL status for a table
SELECT
    database,
    table,
    name AS part_name,
    partition,
    rows,
    formatReadableSize(bytes_on_disk) AS size,
    delete_ttl_info_min,
    delete_ttl_info_max,
    move_ttl_info.expression AS move_ttl_expr,
    move_ttl_info.min AS move_ttl_min,
    move_ttl_info.max AS move_ttl_max
FROM system.parts
WHERE database = 'rayolly_logs'
  AND table = 'logs_local'
  AND active
ORDER BY partition;
```

### 7.6 Compliance Holds

Compliance holds prevent data from being tiered to cold storage or deleted, regardless of TTL policies. This supports legal hold and regulatory retention requirements.

```sql
-- Compliance hold tracking table
CREATE TABLE rayolly_meta.compliance_holds ON CLUSTER rayolly_cluster
(
    `hold_id`           UUID DEFAULT generateUUIDv4(),
    `tenant_id`         LowCardinality(String),
    `hold_type`         Enum8('legal_hold' = 1, 'regulatory' = 2, 'litigation' = 3),
    `hold_reason`       String,
    `data_types`        Array(LowCardinality(String)),  -- ['logs', 'events']
    `start_time`        DateTime64(3, 'UTC'),
    `end_time`          Nullable(DateTime64(3, 'UTC')),  -- NULL = indefinite
    `created_by`        String,
    `created_at`        DateTime64(3, 'UTC') DEFAULT now64(3),
    `released_at`       Nullable(DateTime64(3, 'UTC')),
    `released_by`       Nullable(String)
)
ENGINE = ReplicatedMergeTree(
    '/clickhouse/tables/{shard}/rayolly_meta/compliance_holds',
    '{replica}'
)
ORDER BY (tenant_id, hold_type, created_at);
```

### 7.7 GDPR Right-to-Erasure

GDPR Article 17 requires the ability to delete all personal data for a specific data subject. In RayOlly, this translates to deleting all data associated with a tenant (or specific identifiers within a tenant).

**Erasure process**:

1. **Hot tier (ClickHouse)**: Use `ALTER TABLE DELETE WHERE tenant_id = 'target'` — lightweight delete via mutation. Parts are rewritten in the background.
2. **Warm tier (ClickHouse)**: Same mutation mechanism.
3. **Cold tier (S3/Parquet)**: Iceberg supports row-level deletes via positional delete files. For full tenant erasure, delete all files under the tenant partition prefix.
4. **Audit**: All erasure operations are logged in the compliance audit table with timestamps.

```sql
-- GDPR erasure for a specific tenant (executed by Lifecycle Manager)
-- Step 1: Mark hold on new ingestion
-- Step 2: Delete from hot/warm
ALTER TABLE rayolly_logs.logs_local DELETE WHERE tenant_id = 'target-tenant';
ALTER TABLE rayolly_metrics.metrics_local DELETE WHERE tenant_id = 'target-tenant';
ALTER TABLE rayolly_traces.spans_local DELETE WHERE tenant_id = 'target-tenant';
ALTER TABLE rayolly_events.events_local DELETE WHERE tenant_id = 'target-tenant';

-- Step 3: Delete from all materialized views
ALTER TABLE rayolly_logs.logs_volume_per_minute DELETE WHERE tenant_id = 'target-tenant';
ALTER TABLE rayolly_metrics.metrics_5min_rollup DELETE WHERE tenant_id = 'target-tenant';
ALTER TABLE rayolly_traces.service_latency_per_minute DELETE WHERE tenant_id = 'target-tenant';
```

```python
# Cold tier erasure (S3/Parquet)
import boto3

s3 = boto3.client('s3', endpoint_url='https://minio.rayolly.internal:9000')

def erase_tenant_cold_data(tenant_id: str, bucket: str = 'rayolly-cold'):
    """Delete all cold-tier data for a tenant (GDPR erasure)."""
    for data_type in ['logs', 'metrics', 'traces', 'events']:
        prefix = f"data/{data_type}/tenant={tenant_id}/"
        paginator = s3.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=bucket, Prefix=prefix)

        delete_objects = []
        for page in pages:
            for obj in page.get('Contents', []):
                delete_objects.append({'Key': obj['Key']})
                if len(delete_objects) == 1000:
                    s3.delete_objects(
                        Bucket=bucket,
                        Delete={'Objects': delete_objects}
                    )
                    delete_objects = []

        if delete_objects:
            s3.delete_objects(
                Bucket=bucket,
                Delete={'Objects': delete_objects}
            )

    # Update Iceberg catalog to remove tenant snapshots
    # (handled via PyIceberg API)
```

---

## 8. Data Model

### 8.1 Internal Data Model — Logs

| Field | Type | Required | Source | Description |
|-------|------|----------|--------|-------------|
| `tenant_id` | String (LowCardinality) | Yes | Ingestion gateway | Tenant identifier, injected at ingest |
| `log_id` | UUID | Yes | Auto-generated | Unique log record ID |
| `timestamp` | DateTime64(9) | Yes | OTEL `TimeUnixNano` | Event occurrence time (nanosecond precision) |
| `observed_timestamp` | DateTime64(9) | No | OTEL `ObservedTimestamp` | Time log was collected |
| `trace_id` | String | No | OTEL `TraceId` | Hex-encoded W3C trace ID |
| `span_id` | String | No | OTEL `SpanId` | Hex-encoded span ID |
| `severity_number` | UInt8 | Yes | OTEL `SeverityNumber` | 1-24 per OTEL spec |
| `severity_text` | String (LowCardinality) | No | OTEL `SeverityText` | TRACE, DEBUG, INFO, WARN, ERROR, FATAL |
| `body` | String | Yes | OTEL `Body` | Log message body |
| `service_name` | String (LowCardinality) | No | `resource.service.name` | Extracted from resource attributes |
| `service_namespace` | String (LowCardinality) | No | `resource.service.namespace` | Extracted from resource attributes |
| `service_version` | String (LowCardinality) | No | `resource.service.version` | Extracted from resource attributes |
| `host_name` | String (LowCardinality) | No | `resource.host.name` | Extracted from resource attributes |
| `host_ip` | IPv4 | No | `resource.host.ip` | Extracted and cast |
| `k8s_namespace` | String (LowCardinality) | No | `resource.k8s.namespace.name` | Kubernetes metadata |
| `k8s_pod_name` | String (LowCardinality) | No | `resource.k8s.pod.name` | Kubernetes metadata |
| `k8s_container_name` | String (LowCardinality) | No | `resource.k8s.container.name` | Kubernetes metadata |
| `source` | String (LowCardinality) | No | Enrichment pipeline | Data source (otel, syslog, filebeat, etc.) |
| `resource_attributes` | Map(String, String) | No | OTEL `Resource.attributes` | Full resource attributes map |
| `attributes` | Map(String, String) | No | OTEL `LogRecord.attributes` | Log-specific attributes |
| `ingested_at` | DateTime64(3) | Yes | Server time at ingest | When RayOlly received the record |

### 8.2 Internal Data Model — Metrics

| Field | Type | Required | Source | Description |
|-------|------|----------|--------|-------------|
| `tenant_id` | String (LowCardinality) | Yes | Ingestion gateway | Tenant identifier |
| `timestamp` | DateTime64(3) | Yes | OTEL data point timestamp | Metric observation time |
| `metric_name` | String (LowCardinality) | Yes | OTEL `Name` | Metric name (e.g., `http.server.duration`) |
| `metric_description` | String | No | OTEL `Description` | Human-readable description |
| `metric_unit` | String (LowCardinality) | No | OTEL `Unit` | Unit (e.g., `ms`, `By`, `1`) |
| `metric_type` | Enum8 | Yes | OTEL metric type | gauge, sum, histogram, exp_histogram, summary |
| `value_float` | Float64 | Conditional | OTEL data point | Gauge/Sum float value |
| `value_int` | Int64 | Conditional | OTEL data point | Gauge/Sum integer value |
| `is_monotonic` | Bool | Conditional | OTEL Sum | Monotonic counter flag |
| `aggregation_temporality` | Enum8 | Conditional | OTEL Sum/Histogram | delta or cumulative |
| `histogram_count` | UInt64 | Conditional | OTEL Histogram | Total count |
| `histogram_sum` | Float64 | Conditional | OTEL Histogram | Sum of observations |
| `histogram_min` | Float64 | Conditional | OTEL Histogram | Minimum observed value |
| `histogram_max` | Float64 | Conditional | OTEL Histogram | Maximum observed value |
| `histogram_bucket_counts` | Array(UInt64) | Conditional | OTEL Histogram | Bucket counts |
| `histogram_explicit_bounds` | Array(Float64) | Conditional | OTEL Histogram | Bucket boundaries |
| `labels` | Map(String, String) | No | OTEL `Attributes` | Metric attributes/labels |
| `resource_attributes` | Map(String, String) | No | OTEL `Resource` | Resource attributes |
| `service_name` | String (LowCardinality) | No | `resource.service.name` | Extracted |
| `host_name` | String (LowCardinality) | No | `resource.host.name` | Extracted |

### 8.3 Internal Data Model — Traces (Spans)

| Field | Type | Required | Source | Description |
|-------|------|----------|--------|-------------|
| `tenant_id` | String (LowCardinality) | Yes | Ingestion gateway | Tenant identifier |
| `trace_id` | FixedString(32) | Yes | OTEL `TraceId` | 128-bit trace ID (hex) |
| `span_id` | FixedString(16) | Yes | OTEL `SpanId` | 64-bit span ID (hex) |
| `parent_span_id` | FixedString(16) | No | OTEL `ParentSpanId` | Parent span (empty for root) |
| `trace_state` | String | No | OTEL `TraceState` | W3C trace state |
| `span_name` | String (LowCardinality) | Yes | OTEL `Name` | Operation name |
| `span_kind` | Enum8 | Yes | OTEL `Kind` | INTERNAL, SERVER, CLIENT, PRODUCER, CONSUMER |
| `start_time` | DateTime64(9) | Yes | OTEL `StartTimeUnixNano` | Span start (nanoseconds) |
| `end_time` | DateTime64(9) | Yes | OTEL `EndTimeUnixNano` | Span end (nanoseconds) |
| `duration_ns` | UInt64 | Yes | Derived | end_time - start_time |
| `status_code` | Enum8 | Yes | OTEL `Status.Code` | UNSET, OK, ERROR |
| `status_message` | String | No | OTEL `Status.Message` | Error message |
| `attributes` | Map(String, String) | No | OTEL `Attributes` | Span attributes |
| `resource_attributes` | Map(String, String) | No | OTEL `Resource` | Resource attributes |
| `service_name` | String (LowCardinality) | No | `resource.service.name` | Extracted |
| `events.*` | Nested arrays | No | OTEL `Events` | Span events (exceptions, annotations) |
| `links.*` | Nested arrays | No | OTEL `Links` | Cross-trace links |

### 8.4 OTEL Semantic Conventions Mapping

RayOlly promotes frequently-queried OTEL semantic convention attributes to top-level columns for query performance:

| OTEL Semantic Convention | RayOlly Column | Rationale |
|--------------------------|----------------|-----------|
| `service.name` | `service_name` | Most common filter; part of ORDER BY |
| `service.namespace` | `service_namespace` | Common grouping dimension |
| `service.version` | `service_version` | Deployment correlation |
| `host.name` | `host_name` | Infrastructure grouping |
| `host.ip` | `host_ip` | IPv4 native type for efficiency |
| `k8s.namespace.name` | `k8s_namespace` | Kubernetes-native filtering |
| `k8s.pod.name` | `k8s_pod_name` | Pod-level debugging |
| `k8s.container.name` | `k8s_container_name` | Container-level filtering |

All other OTEL attributes remain in the `resource_attributes` or `attributes` Map columns and are queryable via ClickHouse Map functions:

```sql
-- Querying promoted attribute
SELECT * FROM rayolly_logs.logs
WHERE tenant_id = 'acme-corp' AND service_name = 'payment-api';

-- Querying non-promoted attribute from Map
SELECT * FROM rayolly_logs.logs
WHERE tenant_id = 'acme-corp'
  AND attributes['http.method'] = 'POST'
  AND attributes['http.status_code'] = '500';
```

### 8.5 Field Naming Conventions

| Convention | Rule | Example |
|-----------|------|---------|
| Column names | snake_case | `service_name`, `trace_id` |
| OTEL attribute keys | Dot-notation (OTEL standard) | `http.method`, `rpc.grpc.status_code` |
| Map keys | Dot-notation, matching OTEL | `attributes['http.url']` |
| Internal metadata | Prefixed with underscore | `_date`, `_hour` |
| Derived columns | MATERIALIZED, clear name | `has_error`, `duration_ns` |

### 8.6 Data Type System

| RayOlly Type | ClickHouse Type | Parquet Type | Description |
|-------------|----------------|-------------|-------------|
| string | String | BYTE_ARRAY (UTF8) | Variable-length UTF-8 string |
| string_lc | LowCardinality(String) | BYTE_ARRAY + DICT | Low-cardinality string (dictionary encoded) |
| int64 | Int64 | INT64 | 64-bit signed integer |
| uint64 | UInt64 | INT64 (UINT_64) | 64-bit unsigned integer |
| float64 | Float64 | DOUBLE | 64-bit IEEE 754 float |
| bool | Bool (UInt8) | BOOLEAN | True/False |
| timestamp_ns | DateTime64(9, 'UTC') | TIMESTAMP(NANOS, true) | Nanosecond-precision UTC timestamp |
| timestamp_ms | DateTime64(3, 'UTC') | TIMESTAMP(MILLIS, true) | Millisecond-precision UTC timestamp |
| date | Date | DATE | Calendar date |
| ipv4 | IPv4 | INT32 (custom) | IPv4 address |
| uuid | UUID | FIXED_LEN_BYTE_ARRAY(16) | UUID v4 |
| array(T) | Array(T) | LIST | Typed array |
| map(K, V) | Map(K, V) | MAP | Key-value map |
| enum8 | Enum8 | INT32 (ENUM) | Enumerated type (up to 128 values) |
| fixed_string(N) | FixedString(N) | FIXED_LEN_BYTE_ARRAY(N) | Fixed-length binary |

---

## 9. Compression & Efficiency

### 9.1 Target Compression Ratios

| Data Type | Raw Size (per 1M records) | Compressed Hot (LZ4/ZSTD) | Compressed Cold (ZSTD-9) | Ratio (Hot) | Ratio (Cold) |
|-----------|--------------------------|---------------------------|--------------------------|-------------|--------------|
| Logs | ~2.5 GB | ~250 MB | ~150 MB | 10:1 | 17:1 |
| Metrics | ~400 MB | ~20 MB | ~12 MB | 20:1 | 33:1 |
| Traces (spans) | ~1.5 GB | ~120 MB | ~75 MB | 12:1 | 20:1 |
| Events | ~500 MB | ~40 MB | ~25 MB | 12:1 | 20:1 |

### 9.2 Codec Selection Per Column Type

| Column Category | Columns | Primary Codec | Secondary Codec | Why |
|----------------|---------|---------------|-----------------|-----|
| Timestamps | timestamp, start_time, end_time, ingested_at | DoubleDelta | ZSTD(1) | Timestamps are monotonically increasing; DoubleDelta encodes diffs of diffs near zero |
| Metric values | value_float, histogram_sum/min/max | Gorilla | ZSTD(1) | Gorilla XOR encoding optimized for slowly-changing float time-series |
| Counters | duration_ns, histogram_count, rows | DoubleDelta | ZSTD(1) | Counters are monotonic or slowly changing |
| Low-cardinality strings | service_name, severity_text, metric_name | LowCardinality | ZSTD(1) | ClickHouse dictionary encoding + column compression |
| High-cardinality strings | body, status_message | — | ZSTD(3) | No specialized codec; higher ZSTD level for better ratio |
| Fixed-size IDs | trace_id, span_id | — | ZSTD(1) | Random data, limited optimization possible |
| Maps | attributes, resource_attributes, labels | — | ZSTD(1) | Key repetition provides good ZSTD ratio |
| Booleans/Enums | is_monotonic, status_code, span_kind | — | ZSTD(1) | Tiny values, extremely compressible |
| IP addresses | host_ip | — | ZSTD(1) | 4-byte fixed, locality helps |
| Arrays | histogram_bucket_counts, events.* | — | ZSTD(1) | Mixed content, general compression |

### 9.3 Dictionary Encoding

ClickHouse's `LowCardinality` type provides automatic dictionary encoding for columns with fewer than ~10,000 distinct values. Columns using LowCardinality:

- `tenant_id` (typically < 10,000 tenants)
- `service_name` (typically < 1,000 per tenant)
- `service_namespace`, `service_version`
- `host_name` (typically < 10,000 per tenant)
- `severity_text` (6 values)
- `metric_name` (typically < 5,000 per tenant)
- `metric_unit` (< 50 distinct values)
- `event_type`, `event_source`
- `k8s_namespace`, `k8s_pod_name`, `k8s_container_name`
- `source`, `scope_name`, `scope_version`

### 9.4 Delta Encoding for Timestamps

DoubleDelta encoding exploits the fact that observability timestamps are nearly monotonic:

```
Raw timestamps:     1710841200000000000  1710841200001000000  1710841200002000000
First delta:                            1000000              1000000
Second delta:                                                0

DoubleDelta stores: [base, 1000000, 0, 0, 0, ...]  → near-zero entropy
```

For timestamps arriving out of order (within a partition), ClickHouse sorts data during merges, restoring monotonicity and improving DoubleDelta efficiency on compacted parts.

### 9.5 Expected Storage Costs

| Tier | Storage Medium | Cost per GB/month | 1TB Ingested/day Cost | 10TB Ingested/day Cost |
|------|---------------|-------------------|-----------------------|------------------------|
| Hot (3 days) | NVMe SSD | $0.50 | ~$45/mo (3d × 100GB compressed) | ~$450/mo |
| Warm (27 days) | EBS gp3 / HDD | $0.10 | ~$200/mo (27d × 75GB compressed) | ~$2,000/mo |
| Cold (335 days) | S3 Standard | $0.023 | ~$550/mo (335d × 70GB compressed) | ~$5,500/mo |
| Archive (1+ year) | S3 Glacier IR | $0.004 | ~$100/mo per year | ~$1,000/mo per year |

**Total estimated cost for 1TB/day ingestion with 1-year retention: ~$900/month**

Compare with:
- Splunk: ~$2,500/GB/year × 365TB = $912,500/year ($76,000/month)
- Datadog: ~$0.10/GB ingested + $0.05/GB scanned = variable but ~$15,000/month

RayOlly achieves approximately **15-80x cost reduction** depending on the incumbent.

---

## 10. Replication & Durability

### 10.1 ClickHouse Keeper Configuration

ClickHouse Keeper replaces ZooKeeper for coordination. It provides consensus for replication, distributed DDL, and leader election.

```xml
<!-- /etc/clickhouse-keeper/keeper_config.xml -->
<clickhouse>
    <keeper_server>
        <tcp_port>9181</tcp_port>
        <server_id>1</server_id>

        <coordination_settings>
            <operation_timeout_ms>10000</operation_timeout_ms>
            <session_timeout_ms>30000</session_timeout_ms>
            <raft_logs_level>warning</raft_logs_level>
            <force_sync>true</force_sync>
            <snapshot_distance>100000</snapshot_distance>
            <snapshots_to_keep>3</snapshots_to_keep>
        </coordination_settings>

        <raft_configuration>
            <server>
                <id>1</id>
                <hostname>keeper-01.rayolly.internal</hostname>
                <port>9234</port>
            </server>
            <server>
                <id>2</id>
                <hostname>keeper-02.rayolly.internal</hostname>
                <port>9234</port>
            </server>
            <server>
                <id>3</id>
                <hostname>keeper-03.rayolly.internal</hostname>
                <port>9234</port>
            </server>
        </raft_configuration>
    </keeper_server>
</clickhouse>
```

### 10.2 Replication Factor

| Deployment | Replication Factor | Insert Quorum | Notes |
|-----------|-------------------|---------------|-------|
| Development | 1 | 1 | Single node, no HA |
| Staging | 2 | 1 | Two replicas, async replication |
| Production (default) | 2 | 2 | Synchronous writes to both replicas |
| Production (high durability) | 3 | 2 | Three replicas, quorum of 2 |

```xml
<!-- Per-table replication settings -->
<clickhouse>
    <merge_tree>
        <replicated_deduplication_window>100</replicated_deduplication_window>
        <replicated_deduplication_window_seconds>604800</replicated_deduplication_window_seconds>
    </merge_tree>

    <profiles>
        <default>
            <insert_quorum>2</insert_quorum>
            <insert_quorum_parallel>1</insert_quorum_parallel>
            <insert_quorum_timeout>60000</insert_quorum_timeout>
            <select_sequential_consistency>0</select_sequential_consistency>
        </default>
    </profiles>
</clickhouse>
```

### 10.3 Cross-AZ Replication

In cloud deployments, replicas within a shard are placed in different availability zones:

```
         ┌──────────────────────────────────────────────┐
         │              AWS Region: us-east-1            │
         │                                               │
         │  AZ-a                    AZ-b                 │
         │  ┌──────────────┐       ┌──────────────┐     │
         │  │  Shard 1     │       │  Shard 1     │     │
         │  │  Replica A   │◄─────►│  Replica B   │     │
         │  │  (chi-01a)   │ sync  │  (chi-01b)   │     │
         │  └──────────────┘       └──────────────┘     │
         │  ┌──────────────┐       ┌──────────────┐     │
         │  │  Shard 2     │       │  Shard 2     │     │
         │  │  Replica A   │◄─────►│  Replica B   │     │
         │  │  (chi-02a)   │ sync  │  (chi-02b)   │     │
         │  └──────────────┘       └──────────────┘     │
         │                                               │
         │  AZ-c (Keeper quorum)                         │
         │  ┌──────────────┐                             │
         │  │  Keeper-3    │                             │
         │  └──────────────┘                             │
         │  (Keeper-1 in AZ-a, Keeper-2 in AZ-b)        │
         └──────────────────────────────────────────────┘
```

### 10.4 Backup Strategy

| Backup Type | Frequency | Retention | Method | Target |
|-------------|-----------|-----------|--------|--------|
| Full backup | Weekly (Sunday 03:00 UTC) | 4 weeks | `BACKUP TABLE ... TO S3` | s3://rayolly-backups/full/ |
| Incremental backup | Daily (03:00 UTC) | 7 days | `BACKUP TABLE ... TO S3` (incremental) | s3://rayolly-backups/incremental/ |
| Keeper snapshots | Every 100K operations | 3 snapshots | Built-in Keeper snapshotting | Local + S3 |
| Iceberg metadata | Per commit | 30 days | Iceberg snapshot retention | In-place (S3) |

```sql
-- Full backup example
BACKUP DATABASE rayolly_logs, rayolly_metrics, rayolly_traces, rayolly_events
TO S3('https://s3.amazonaws.com/rayolly-backups/full/2026-03-19/', 'AKID', 'SECRET')
SETTINGS
    base_backup = S3('https://s3.amazonaws.com/rayolly-backups/full/2026-03-12/', 'AKID', 'SECRET');

-- Incremental backup
BACKUP DATABASE rayolly_logs
TO S3('https://s3.amazonaws.com/rayolly-backups/incremental/2026-03-19/', 'AKID', 'SECRET')
SETTINGS
    base_backup = S3('https://s3.amazonaws.com/rayolly-backups/incremental/2026-03-18/', 'AKID', 'SECRET');
```

### 10.5 Point-in-Time Recovery

ClickHouse does not natively support point-in-time recovery at the row level. RayOlly achieves PITR through:

1. **Backup-based recovery**: Restore from the most recent backup before the target time.
2. **Replay from NATS JetStream**: NATS retains messages for a configurable period (default 72 hours). After restoring from backup, replay messages from NATS starting at the backup timestamp.
3. **Cold tier time travel**: Iceberg snapshots allow querying cold data as of any previous snapshot.

**Recovery time targets**:
- RPO (Recovery Point Objective): < 1 minute (NATS retention)
- RTO (Recovery Time Objective): < 15 minutes (backup restore + replay)

### 10.6 Disaster Recovery Plan

| Scenario | RTO | RPO | Recovery Procedure |
|----------|-----|-----|-------------------|
| Single node failure | 0 (automatic) | 0 | Replica takes over reads; writes continue to surviving replica |
| Single AZ failure | < 5 min | 0 | Replicas in surviving AZ serve all traffic |
| Full region failure | < 4 hours | < 1 hour | Restore from S3 backups in DR region; cold data is in S3 (cross-region replicated) |
| Data corruption (logical) | < 30 min | Depends on detection time | Restore from last good backup; replay from NATS |
| Accidental deletion (table) | < 15 min | 0 | Restore from backup (data preserved in S3 cold tier) |

---

## 11. Multi-Tenancy

### 11.1 Tenant Isolation Strategy

RayOlly uses **shared tables with mandatory `tenant_id` filtering** (the "shared-everything" model). This provides cost efficiency while maintaining logical isolation.

**Why shared tables instead of per-tenant databases**:
- Per-tenant databases do not scale past ~1,000 tenants (too many tables for ClickHouse metadata)
- Shared tables with `tenant_id` in the partition key enable efficient per-tenant operations
- ClickHouse partition pruning eliminates cross-tenant data scanning

**Isolation guarantees**:
- Every query MUST include `WHERE tenant_id = ?` — enforced at the API gateway level
- The Storage Writer Service always injects `tenant_id` before insert
- ClickHouse users are configured with row-level security policies (see below)

### 11.2 Row-Level Security

```sql
-- Create per-tenant ClickHouse users with row policies
CREATE USER IF NOT EXISTS tenant_acme
    IDENTIFIED WITH sha256_hash BY 'hash_here'
    DEFAULT DATABASE rayolly_logs
    SETTINGS max_memory_usage = 5368709120;  -- 5GB per query

-- Row-level security policy
CREATE ROW POLICY IF NOT EXISTS tenant_acme_policy
    ON rayolly_logs.logs
    FOR SELECT
    USING tenant_id = 'acme-corp'
    TO tenant_acme;

CREATE ROW POLICY IF NOT EXISTS tenant_acme_metrics_policy
    ON rayolly_metrics.metrics
    FOR SELECT
    USING tenant_id = 'acme-corp'
    TO tenant_acme;

-- Repeat for traces and events tables
```

In practice, the Query Engine (PRD-03) uses a service account with full access and injects `tenant_id` filters at the query planning stage. Row policies serve as a defense-in-depth measure.

### 11.3 Resource Quotas Per Tenant

```sql
-- Quota definitions
CREATE QUOTA IF NOT EXISTS tenant_free_tier
    FOR INTERVAL 1 HOUR MAX
        queries = 1000,
        result_rows = 10000000,
        read_rows = 100000000,
        execution_time = 300
    FOR INTERVAL 1 DAY MAX
        queries = 10000,
        result_rows = 100000000,
        read_rows = 1000000000,
        execution_time = 3600
    TO tenant_free;

CREATE QUOTA IF NOT EXISTS tenant_pro_tier
    FOR INTERVAL 1 HOUR MAX
        queries = 10000,
        result_rows = 100000000,
        read_rows = 1000000000,
        execution_time = 3600
    FOR INTERVAL 1 DAY MAX
        queries = 100000,
        result_rows = 1000000000,
        read_rows = 10000000000,
        execution_time = 36000
    TO tenant_pro;

CREATE QUOTA IF NOT EXISTS tenant_enterprise_tier
    FOR INTERVAL 1 HOUR MAX
        queries = 100000,
        result_rows = 1000000000,
        read_rows = 10000000000,
        execution_time = 36000
    -- No daily limit
    TO tenant_enterprise;
```

### 11.4 Noisy Neighbor Prevention

| Mechanism | Implementation | Description |
|-----------|---------------|-------------|
| Query memory limit | `max_memory_usage` per ClickHouse user | Prevents single tenant from consuming all memory |
| Query time limit | `max_execution_time` per profile | Kills long-running queries |
| Concurrent query limit | `max_concurrent_queries_for_user` | Limits parallel queries per tenant |
| Read row limit | Quota `read_rows` per interval | Prevents scanning entire cluster |
| Write rate limit | Ingestion gateway token bucket | Limits ingest rate per tenant (PRD-01) |
| Priority scheduling | ClickHouse `priority` setting per user | Lower priority for free-tier tenants |

```xml
<!-- Noisy neighbor settings per profile -->
<clickhouse>
    <profiles>
        <tenant_free>
            <max_memory_usage>2147483648</max_memory_usage>    <!-- 2GB -->
            <max_execution_time>30</max_execution_time>
            <max_concurrent_queries_for_user>5</max_concurrent_queries_for_user>
            <priority>10</priority>  <!-- Lower priority -->
        </tenant_free>
        <tenant_pro>
            <max_memory_usage>10737418240</max_memory_usage>   <!-- 10GB -->
            <max_execution_time>120</max_execution_time>
            <max_concurrent_queries_for_user>20</max_concurrent_queries_for_user>
            <priority>5</priority>
        </tenant_pro>
        <tenant_enterprise>
            <max_memory_usage>32212254720</max_memory_usage>   <!-- 30GB -->
            <max_execution_time>600</max_execution_time>
            <max_concurrent_queries_for_user>50</max_concurrent_queries_for_user>
            <priority>1</priority>   <!-- Highest priority -->
        </tenant_enterprise>
    </profiles>
</clickhouse>
```

### 11.5 Tenant Data Segregation for Compliance

For tenants requiring physical data segregation (e.g., government, healthcare):

1. **Partition-level isolation**: Since `tenant_id` is part of the partition key, a tenant's data is stored in dedicated partition directories on disk. While this is logical separation (same ClickHouse instance), it enables:
   - Per-partition encryption (future: ClickHouse disk-level encryption per partition)
   - Per-partition backup and restore
   - Fast `DROP PARTITION` for tenant offboarding

2. **Dedicated shard option** (Enterprise tier): A tenant can be assigned to a dedicated shard where no other tenants' data exists. The `cityHash64(tenant_id)` sharding key routes all data to that shard.

3. **Data residency**: For EU data residency (GDPR), tenants are assigned to shards in EU regions. The shard assignment is stored in the tenant configuration and enforced at the ingestion gateway.

---

## 12. Performance Targets

### 12.1 Write Performance

| Metric | Target | Measurement Point |
|--------|--------|-------------------|
| Insert throughput (per shard) | 1,000,000 rows/sec | ClickHouse native protocol, batched inserts of 10K-100K rows |
| Insert throughput (per cluster, 10 shards) | 10,000,000 rows/sec | Distributed table insert |
| Insert latency (batch) | < 100ms for 10K row batch | Measured at Storage Writer Service |
| Insert-to-queryable lag | < 2 seconds | Time from insert to appearance in SELECT |
| Async insert buffer | 1 second or 100K rows (whichever first) | ClickHouse async_insert setting |

### 12.2 Read Performance

| Query Pattern | Data Size | p50 Latency | p99 Latency | Notes |
|--------------|-----------|-------------|-------------|-------|
| Point query (trace_id lookup) | Any | < 50ms | < 200ms | Bloom filter index |
| Time-range scan (1 hour, 1 service) | Hot | < 200ms | < 1s | Partition + primary key pruning |
| Time-range scan (1 day, 1 service) | Hot | < 500ms | < 2s | Multiple partitions |
| Time-range scan (7 days, all services) | Hot + Warm | < 2s | < 5s | Cross-volume |
| Aggregation (count by service, 1 day) | Hot | < 300ms | < 1s | Materialized view |
| Full-text search (token in body) | Hot (1 day) | < 1s | < 3s | tokenbf skip index |
| Cold tier scan (30 days, 1 service) | Cold | < 5s | < 15s | DuckDB + Parquet |
| Cold tier scan (90 days, aggregation) | Cold | < 10s | < 30s | DuckDB + Iceberg pruning |

### 12.3 Compression Targets

| Data Type | Target Compression Ratio (Hot) | Target Compression Ratio (Cold) |
|-----------|-------------------------------|--------------------------------|
| Logs | 10:1 | 17:1 |
| Metrics | 20:1 | 33:1 |
| Traces | 12:1 | 20:1 |
| Events | 12:1 | 20:1 |
| Materialized views (rollups) | 50:1+ | N/A (kept in ClickHouse) |

### 12.4 Storage Cost Targets

| Tier | Cost per GB/month | Target |
|------|-------------------|---------|
| Hot (NVMe) | < $0.50 | Includes replication overhead |
| Warm (EBS gp3) | < $0.10 | Includes replication overhead |
| Cold (S3 Standard) | < $0.025 | Single copy (S3 provides durability) |
| Archive (S3 Glacier IR) | < $0.005 | For data > 1 year old |

---

## 13. Scalability

### 13.1 Horizontal Scaling Strategy

```
       Current State                     After Scale-Out
  ┌───────────────────┐            ┌───────────────────────┐
  │  3 Shards × 2 Rep │            │  6 Shards × 2 Rep     │
  │                    │            │                        │
  │  S1: ████████ 80%  │   ──►     │  S1: ████     40%     │
  │  S2: ███████  70%  │            │  S2: ███      35%     │
  │  S3: █████    50%  │            │  S3: ██       25%     │
  │                    │            │  S4: ████     40%     │ ← new
  │                    │            │  S5: ███      35%     │ ← new
  │                    │            │  S6: ██       25%     │ ← new
  └───────────────────┘            └───────────────────────┘
```

**Adding a new shard**:

1. Deploy new ClickHouse nodes (2 replicas per shard)
2. Add shard definition to cluster config
3. Update Distributed table definitions (automatic via ON CLUSTER)
4. New data for newly assigned tenants routes to the new shard
5. Optionally rebalance existing tenants (manual process)

```xml
<!-- Updated cluster config after adding Shard 4 -->
<clickhouse>
    <remote_servers>
        <rayolly_cluster>
            <shard>
                <internal_replication>true</internal_replication>
                <replica>
                    <host>chi-01a.rayolly.internal</host>
                    <port>9000</port>
                </replica>
                <replica>
                    <host>chi-01b.rayolly.internal</host>
                    <port>9000</port>
                </replica>
            </shard>
            <shard>
                <internal_replication>true</internal_replication>
                <replica>
                    <host>chi-02a.rayolly.internal</host>
                    <port>9000</port>
                </replica>
                <replica>
                    <host>chi-02b.rayolly.internal</host>
                    <port>9000</port>
                </replica>
            </shard>
            <!-- ... additional shards ... -->
            <shard>
                <internal_replication>true</internal_replication>
                <replica>
                    <host>chi-04a.rayolly.internal</host>
                    <port>9000</port>
                </replica>
                <replica>
                    <host>chi-04b.rayolly.internal</host>
                    <port>9000</port>
                </replica>
            </shard>
        </rayolly_cluster>
    </remote_servers>
</clickhouse>
```

### 13.2 Shard Management and Rebalancing

**Shard assignment**: Tenants are assigned to shards via a lookup table, not purely by hash. This allows controlled assignment and rebalancing.

```sql
-- Shard assignment tracking
CREATE TABLE rayolly_meta.tenant_shard_assignment ON CLUSTER rayolly_cluster
(
    `tenant_id`     LowCardinality(String),
    `shard_id`      UInt16,
    `assigned_at`   DateTime64(3, 'UTC') DEFAULT now64(3),
    `assigned_by`   String,
    `reason`        String  -- 'initial', 'rebalance', 'dedicated', 'manual'
)
ENGINE = ReplicatedReplacingMergeTree(
    '/clickhouse/tables/{shard}/rayolly_meta/tenant_shard_assignment',
    '{replica}',
    assigned_at
)
ORDER BY tenant_id;
```

**Rebalancing process** (manual, scheduled for automation in Phase 4):

1. Identify imbalanced shards (>30% deviation from mean)
2. Select tenants to move (smallest tenants first, to minimize disruption)
3. Export tenant data from source shard via `SELECT ... INTO OUTFILE`
4. Import into target shard via `INSERT INTO ... SELECT FROM file(...)`
5. Update shard assignment table
6. Drop source data after verification

### 13.3 Capacity Planning Guidelines

| Cluster Size | Shards | Replicas/Shard | Total Nodes | Ingest Capacity | Storage (Hot, 3d) | Recommended For |
|-------------|--------|----------------|-------------|-----------------|-------------------|-----------------|
| Small | 2 | 2 | 4 | 2M rows/sec | 2 TB | Startups, < 100GB/day |
| Medium | 4 | 2 | 8 | 4M rows/sec | 8 TB | Mid-market, 100GB-1TB/day |
| Large | 8 | 2 | 16 | 8M rows/sec | 30 TB | Enterprise, 1-5TB/day |
| X-Large | 16 | 2 | 32 | 16M rows/sec | 100 TB | Large enterprise, 5-20TB/day |
| Massive | 32+ | 3 | 96+ | 32M+ rows/sec | 300+ TB | Hyperscale, 20TB+/day |

**Node sizing recommendation** (per ClickHouse node):
- CPU: 16-32 vCPUs (compute-optimized instances)
- RAM: 64-128 GB (at least 2x the expected working set)
- Hot storage: 2-4 TB NVMe SSD per node
- Warm storage: 10-20 TB EBS gp3 per node
- Network: 10 Gbps minimum, 25 Gbps recommended

### 13.4 Auto-Scaling Triggers and Policies

| Metric | Threshold | Action | Cooldown |
|--------|-----------|--------|----------|
| Disk usage (hot volume) | > 75% | Alert; at 85% trigger warm tiering acceleration | 1 hour |
| Disk usage (warm volume) | > 80% | Alert; at 90% trigger cold export acceleration | 1 hour |
| CPU utilization (sustained) | > 70% for 15 min | Scale up node size or add read replicas | 30 min |
| Insert queue depth | > 100K pending batches | Alert; at 500K add ingest workers | 15 min |
| Query latency (p99) | > 5s for 10 min | Add read replicas; review slow queries | 30 min |
| Memory pressure | > 85% RSS for 10 min | Alert; kill low-priority queries; scale up RAM | 15 min |
| Replication lag | > 60 seconds | Alert; at 300s investigate network/disk | 5 min |

**Note**: ClickHouse does not support transparent auto-scaling of shards. Auto-scaling in RayOlly means:
- Vertical scaling: node size changes (Kubernetes pod resource limits)
- Read replica scaling: adding/removing read replicas within a shard
- Shard addition: manual, planned operation (not automated in Phase 1-2)

---

## 14. Monitoring (Self-Monitoring)

### 14.1 Storage Utilization Metrics

| Metric Name | Type | Source | Description |
|-------------|------|--------|-------------|
| `rayolly.storage.disk_usage_bytes` | Gauge | system.disks | Bytes used per disk/volume |
| `rayolly.storage.disk_free_bytes` | Gauge | system.disks | Free bytes per disk/volume |
| `rayolly.storage.disk_usage_pct` | Gauge | Derived | Disk usage percentage |
| `rayolly.storage.parts_count` | Gauge | system.parts | Active parts count per table |
| `rayolly.storage.rows_count` | Gauge | system.parts | Total rows per table |
| `rayolly.storage.compressed_bytes` | Gauge | system.columns | Compressed size per table/column |
| `rayolly.storage.uncompressed_bytes` | Gauge | system.columns | Uncompressed size per table/column |
| `rayolly.storage.compression_ratio` | Gauge | Derived | Compression ratio per table |
| `rayolly.storage.partitions_count` | Gauge | system.parts | Active partitions per table |
| `rayolly.cold.objects_count` | Gauge | S3 list | Object count in cold storage |
| `rayolly.cold.total_bytes` | Gauge | S3 list | Total bytes in cold storage |

### 14.2 Query Performance Metrics

| Metric Name | Type | Source | Description |
|-------------|------|--------|-------------|
| `rayolly.query.duration_ms` | Histogram | system.query_log | Query execution time |
| `rayolly.query.rows_read` | Histogram | system.query_log | Rows read per query |
| `rayolly.query.bytes_read` | Histogram | system.query_log | Bytes read per query |
| `rayolly.query.memory_usage` | Histogram | system.query_log | Peak memory per query |
| `rayolly.query.count` | Counter | system.query_log | Total queries executed |
| `rayolly.query.errors` | Counter | system.query_log | Failed queries |
| `rayolly.query.slow_count` | Counter | Derived | Queries exceeding p99 target |

### 14.3 Ingestion and Compaction Metrics

| Metric Name | Type | Source | Description |
|-------------|------|--------|-------------|
| `rayolly.ingest.rows_per_sec` | Gauge | system.metrics | Current insert rate |
| `rayolly.ingest.bytes_per_sec` | Gauge | system.metrics | Current insert bytes/sec |
| `rayolly.ingest.async_insert_queue` | Gauge | system.async_inserts | Pending async inserts |
| `rayolly.merge.active_count` | Gauge | system.merges | Currently running merges |
| `rayolly.merge.rows_per_sec` | Gauge | system.merges | Merge throughput |
| `rayolly.merge.duration_ms` | Histogram | system.part_log | Merge duration |
| `rayolly.mutation.active_count` | Gauge | system.mutations | Active mutations (deletes) |

### 14.4 Replication Lag Monitoring

```sql
-- Query to check replication lag across all tables
SELECT
    database,
    table,
    replica_name,
    is_leader,
    total_replicas,
    active_replicas,
    queue_size,
    inserts_in_queue,
    merges_in_queue,
    log_pointer,
    last_queue_update,
    absolute_delay AS replication_lag_seconds
FROM system.replicas
WHERE absolute_delay > 10  -- Alert threshold: 10 seconds
ORDER BY absolute_delay DESC;
```

### 14.5 Alerting Rules

```yaml
# alerts.yaml — storage engine alerts
groups:
  - name: rayolly_storage
    rules:
      - alert: HighDiskUsage
        expr: rayolly_storage_disk_usage_pct > 80
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Disk usage above 80% on {{ $labels.host }}"

      - alert: CriticalDiskUsage
        expr: rayolly_storage_disk_usage_pct > 90
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Disk usage above 90% on {{ $labels.host }} — data loss risk"

      - alert: ReplicationLag
        expr: rayolly_replication_lag_seconds > 60
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Replication lag > 60s on {{ $labels.table }}"

      - alert: HighQueryLatency
        expr: histogram_quantile(0.99, rayolly_query_duration_ms) > 5000
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Query p99 latency exceeds 5s"

      - alert: InsertQueueBacklog
        expr: rayolly_ingest_async_insert_queue > 100000
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Async insert queue backlog > 100K"

      - alert: TooManyParts
        expr: rayolly_storage_parts_count > 3000
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "Too many active parts on {{ $labels.table }} — merge backlog"

      - alert: KeeperSessionExpired
        expr: increase(rayolly_keeper_session_expired_total[5m]) > 0
        labels:
          severity: critical
        annotations:
          summary: "ClickHouse Keeper session expired — replication disrupted"
```

---

## 15. Migration & Compatibility

### 15.1 Data Import from Existing ClickHouse

For organizations migrating from a self-managed ClickHouse deployment:

```bash
#!/bin/bash
# migrate_from_clickhouse.sh — migrate data from external ClickHouse

SOURCE_HOST="old-clickhouse.example.com"
SOURCE_DB="logs"
SOURCE_TABLE="application_logs"
TARGET_TABLE="rayolly_logs.logs"
TENANT_ID="migrated-tenant"

# Step 1: Export schema mapping
clickhouse-client --host "$SOURCE_HOST" \
  --query "DESCRIBE TABLE ${SOURCE_DB}.${SOURCE_TABLE}" \
  > /tmp/source_schema.tsv

# Step 2: Export data in batches (by day partition)
for DATE in $(seq -f "%04g%02g%02g" 20260101 20260319); do
  clickhouse-client --host "$SOURCE_HOST" \
    --query "SELECT
      '${TENANT_ID}' AS tenant_id,
      timestamp,
      timestamp AS observed_timestamp,
      '' AS trace_id,
      '' AS span_id,
      0 AS trace_flags,
      multiIf(level='ERROR',17, level='WARN',13, level='INFO',9, level='DEBUG',5, 1) AS severity_number,
      level AS severity_text,
      message AS body,
      service AS service_name,
      '' AS service_namespace,
      '' AS service_version,
      map() AS resource_attributes,
      '' AS scope_name,
      '' AS scope_version,
      mapFromArrays(
        arrayFilter(x -> x != '', [if(host != '', 'host', '')]),
        arrayFilter(x -> x != '', [host])
      ) AS attributes,
      source,
      hostname AS host_name,
      toIPv4OrDefault(host_ip) AS host_ip,
      '' AS k8s_namespace,
      '' AS k8s_pod_name,
      '' AS k8s_container_name,
      now64(3) AS ingested_at
    FROM ${SOURCE_DB}.${SOURCE_TABLE}
    WHERE toYYYYMMDD(timestamp) = ${DATE}
    FORMAT Native" | \
  clickhouse-client --host "clickhouse.rayolly.internal" \
    --query "INSERT INTO ${TARGET_TABLE} FORMAT Native"
done
```

### 15.2 Data Import from Elasticsearch/OpenSearch

```python
# migrate_from_elasticsearch.py
"""
Migrate data from Elasticsearch/OpenSearch to RayOlly ClickHouse.
Uses scroll API for large datasets.
"""

from elasticsearch import Elasticsearch
from clickhouse_driver import Client
import json
from datetime import datetime

ES_HOST = "https://elasticsearch.example.com:9200"
CH_HOST = "clickhouse.rayolly.internal"
TENANT_ID = "migrated-tenant"
ES_INDEX = "application-logs-*"
BATCH_SIZE = 10_000

es = Elasticsearch([ES_HOST])
ch = Client(host=CH_HOST, database='rayolly_logs')

# Scroll through ES index
scroll = es.search(
    index=ES_INDEX,
    scroll='5m',
    size=BATCH_SIZE,
    body={
        "query": {"match_all": {}},
        "sort": [{"@timestamp": "asc"}]
    }
)

scroll_id = scroll['_scroll_id']
total = scroll['hits']['total']['value']
processed = 0

while True:
    hits = scroll['hits']['hits']
    if not hits:
        break

    batch = []
    for hit in hits:
        src = hit['_source']
        row = {
            'tenant_id': TENANT_ID,
            'timestamp': src.get('@timestamp', datetime.utcnow().isoformat()),
            'severity_number': _map_severity(src.get('level', 'INFO')),
            'severity_text': src.get('level', 'INFO'),
            'body': src.get('message', json.dumps(src)),
            'service_name': src.get('service', src.get('application', '')),
            'host_name': src.get('hostname', src.get('host', {}).get('name', '')),
            'source': 'elasticsearch_migration',
            'resource_attributes': {},
            'attributes': {k: str(v) for k, v in src.items()
                          if k not in ('@timestamp', 'message', 'level', 'service', 'hostname')},
        }
        batch.append(row)

    ch.execute(
        'INSERT INTO logs_local (tenant_id, timestamp, severity_number, severity_text, '
        'body, service_name, host_name, source, resource_attributes, attributes) VALUES',
        batch
    )

    processed += len(hits)
    print(f"Migrated {processed}/{total} documents")

    scroll = es.scroll(scroll_id=scroll_id, scroll='5m')

def _map_severity(level: str) -> int:
    mapping = {
        'TRACE': 1, 'DEBUG': 5, 'INFO': 9,
        'WARN': 13, 'WARNING': 13, 'ERROR': 17, 'FATAL': 21, 'CRITICAL': 21
    }
    return mapping.get(level.upper(), 9)
```

### 15.3 Data Import from Splunk Indexes

```bash
#!/bin/bash
# migrate_from_splunk.sh — export from Splunk via REST API, import to RayOlly

SPLUNK_HOST="https://splunk.example.com:8089"
SPLUNK_TOKEN="your-bearer-token"
SPLUNK_INDEX="main"
TENANT_ID="migrated-tenant"

# Step 1: Export from Splunk as JSON (using Splunk REST API)
curl -k -H "Authorization: Bearer ${SPLUNK_TOKEN}" \
  "${SPLUNK_HOST}/services/search/jobs/export" \
  -d search="search index=${SPLUNK_INDEX} earliest=-30d latest=now" \
  -d output_mode=json \
  -d count=0 \
  > /tmp/splunk_export.json

# Step 2: Transform Splunk JSON to RayOlly format
python3 - <<'PYEOF'
import json
import sys

with open('/tmp/splunk_export.json') as f, open('/tmp/rayolly_import.jsonl', 'w') as out:
    for line in f:
        if not line.strip():
            continue
        try:
            event = json.loads(line)
            result = event.get('result', {})
            row = {
                "tenant_id": "migrated-tenant",
                "timestamp": result.get("_time", ""),
                "severity_text": result.get("severity", result.get("log_level", "INFO")),
                "body": result.get("_raw", ""),
                "service_name": result.get("source", result.get("sourcetype", "")),
                "host_name": result.get("host", ""),
                "source": "splunk_migration",
                "attributes": {k: v for k, v in result.items()
                              if k not in ("_time", "_raw", "host", "source", "sourcetype", "severity")}
            }
            out.write(json.dumps(row) + '\n')
        except json.JSONDecodeError:
            continue
PYEOF

# Step 3: Import to ClickHouse
clickhouse-client --host "clickhouse.rayolly.internal" \
  --query "INSERT INTO rayolly_logs.logs FORMAT JSONEachRow" \
  < /tmp/rayolly_import.jsonl
```

### 15.4 Format Conversion Tools

RayOlly ships with a `rayolly-migrate` CLI tool supporting:

| Source Format | Target | Status |
|--------------|--------|--------|
| ClickHouse (remote) | RayOlly ClickHouse | Phase 1 |
| Elasticsearch / OpenSearch | RayOlly ClickHouse | Phase 1 |
| Splunk (REST export) | RayOlly ClickHouse | Phase 2 |
| Loki (LogQL export) | RayOlly ClickHouse | Phase 2 |
| Prometheus TSDB | RayOlly ClickHouse | Phase 2 |
| Jaeger (gRPC export) | RayOlly ClickHouse | Phase 2 |
| Generic CSV/JSON/Parquet | RayOlly ClickHouse | Phase 1 |

---

## 16. Technical Design Details

### 16.1 ClickHouse Cluster Topology — Full Configuration

```xml
<!-- /etc/clickhouse-server/config.d/cluster.xml -->
<clickhouse>
    <remote_servers>
        <rayolly_cluster>
            <!-- Shard 1 -->
            <shard>
                <weight>1</weight>
                <internal_replication>true</internal_replication>
                <replica>
                    <host>chi-01a.rayolly.internal</host>
                    <port>9000</port>
                    <secure>1</secure>
                </replica>
                <replica>
                    <host>chi-01b.rayolly.internal</host>
                    <port>9000</port>
                    <secure>1</secure>
                </replica>
            </shard>
            <!-- Shard 2 -->
            <shard>
                <weight>1</weight>
                <internal_replication>true</internal_replication>
                <replica>
                    <host>chi-02a.rayolly.internal</host>
                    <port>9000</port>
                    <secure>1</secure>
                </replica>
                <replica>
                    <host>chi-02b.rayolly.internal</host>
                    <port>9000</port>
                    <secure>1</secure>
                </replica>
            </shard>
            <!-- Shard 3 -->
            <shard>
                <weight>1</weight>
                <internal_replication>true</internal_replication>
                <replica>
                    <host>chi-03a.rayolly.internal</host>
                    <port>9000</port>
                    <secure>1</secure>
                </replica>
                <replica>
                    <host>chi-03b.rayolly.internal</host>
                    <port>9000</port>
                    <secure>1</secure>
                </replica>
            </shard>
        </rayolly_cluster>
    </remote_servers>

    <!-- ClickHouse Keeper reference -->
    <zookeeper>
        <node>
            <host>keeper-01.rayolly.internal</host>
            <port>9181</port>
        </node>
        <node>
            <host>keeper-02.rayolly.internal</host>
            <port>9181</port>
        </node>
        <node>
            <host>keeper-03.rayolly.internal</host>
            <port>9181</port>
        </node>
        <session_timeout_ms>30000</session_timeout_ms>
        <operation_timeout_ms>10000</operation_timeout_ms>
    </zookeeper>

    <!-- Macros for ReplicatedMergeTree path templates -->
    <macros>
        <shard>01</shard>          <!-- Set per node: 01, 02, 03 -->
        <replica>chi-01a</replica> <!-- Set per node -->
        <cluster>rayolly_cluster</cluster>
    </macros>
</clickhouse>
```

### 16.2 MinIO Deployment Configuration

```yaml
# minio-deployment.yaml (Kubernetes)
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: minio
  namespace: rayolly-storage
spec:
  serviceName: minio
  replicas: 4  # Distributed mode: 4 nodes minimum
  selector:
    matchLabels:
      app: minio
  template:
    metadata:
      labels:
        app: minio
    spec:
      containers:
        - name: minio
          image: minio/minio:RELEASE.2026-03-01T00-00-00Z
          args:
            - server
            - http://minio-{0...3}.minio.rayolly-storage.svc.cluster.local/data
            - --console-address
            - ":9001"
          env:
            - name: MINIO_ROOT_USER
              valueFrom:
                secretKeyRef:
                  name: minio-credentials
                  key: root-user
            - name: MINIO_ROOT_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: minio-credentials
                  key: root-password
            - name: MINIO_STORAGE_CLASS_STANDARD
              value: "EC:2"  # Erasure coding: 2 parity drives
            - name: MINIO_PROMETHEUS_AUTH_TYPE
              value: "public"
          ports:
            - containerPort: 9000
              name: api
            - containerPort: 9001
              name: console
          volumeMounts:
            - name: data
              mountPath: /data
          resources:
            requests:
              cpu: "2"
              memory: "8Gi"
            limits:
              cpu: "4"
              memory: "16Gi"
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes: ["ReadWriteOnce"]
        storageClassName: gp3-storage
        resources:
          requests:
            storage: 2Ti  # 2TB per MinIO node
---
# MinIO bucket creation job
apiVersion: batch/v1
kind: Job
metadata:
  name: minio-bucket-setup
  namespace: rayolly-storage
spec:
  template:
    spec:
      containers:
        - name: mc
          image: minio/mc:latest
          command:
            - /bin/sh
            - -c
            - |
              mc alias set rayolly http://minio.rayolly-storage.svc.cluster.local:9000 $MINIO_ROOT_USER $MINIO_ROOT_PASSWORD
              mc mb rayolly/rayolly-cold --ignore-existing
              mc mb rayolly/rayolly-backups --ignore-existing
              mc ilm rule add rayolly/rayolly-cold --prefix "data/" --expire-days 2555
              mc ilm rule add rayolly/rayolly-backups --prefix "full/" --expire-days 28
              mc ilm rule add rayolly/rayolly-backups --prefix "incremental/" --expire-days 7
          envFrom:
            - secretRef:
                name: minio-credentials
      restartPolicy: OnFailure
```

### 16.3 Data Pipeline — Ingestion to Storage

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Data Pipeline (End-to-End)                        │
│                                                                          │
│   ┌──────────┐     ┌─────────────┐     ┌────────────────┐              │
│   │  OTEL    │────▶│  Ingestion  │────▶│     NATS       │              │
│   │ Collector│     │   Gateway   │     │   JetStream    │              │
│   │          │     │  (PRD-01)   │     │                │              │
│   └──────────┘     │             │     │  Subjects:     │              │
│                    │ - Auth      │     │  rayolly.logs  │              │
│                    │ - Validate  │     │  rayolly.metrics│             │
│                    │ - Route     │     │  rayolly.traces│              │
│                    └─────────────┘     │  rayolly.events│              │
│                                        └───────┬────────┘              │
│                                                │                        │
│                                     ┌──────────▼──────────┐            │
│                                     │  Storage Writer     │            │
│                                     │  Service            │            │
│                                     │                     │            │
│                                     │  - NATS consumer    │            │
│                                     │  - Batch assembler  │            │
│                                     │    (1K rows / 1s)   │            │
│                                     │  - Schema mapper    │            │
│                                     │  - ClickHouse       │            │
│                                     │    native client    │            │
│                                     │  - Retry w/ backoff │            │
│                                     │  - Dedup tokens     │            │
│                                     └──────────┬──────────┘            │
│                                                │                        │
│                              ┌─────────────────┼───────────────┐       │
│                              │                 │               │       │
│                     ┌────────▼───┐    ┌────────▼───┐  ┌───────▼────┐  │
│                     │ ClickHouse │    │ ClickHouse │  │ ClickHouse │  │
│                     │  Shard 1   │    │  Shard 2   │  │  Shard N   │  │
│                     │ (hot/warm) │    │ (hot/warm) │  │ (hot/warm) │  │
│                     └──────┬─────┘    └──────┬─────┘  └──────┬─────┘  │
│                            │                 │               │         │
│                            └─────────┬───────┘───────────────┘         │
│                                      │                                  │
│                            ┌─────────▼─────────┐                       │
│                            │  Lifecycle Manager │                       │
│                            │                    │                       │
│                            │  Warm → Cold export│                       │
│                            │  (Parquet writer)  │                       │
│                            └─────────┬──────────┘                       │
│                                      │                                  │
│                            ┌─────────▼─────────┐                       │
│                            │   S3 / MinIO      │                       │
│                            │  (Cold Storage)   │                       │
│                            │  + Iceberg Catalog│                       │
│                            └───────────────────┘                       │
└─────────────────────────────────────────────────────────────────────────┘
```

### 16.4 Component Interaction Diagram

```
  ┌─────────────────────────────────────────────────────────────────┐
  │                    Component Interactions                        │
  │                                                                  │
  │  Storage Writer ──TCP:9000──▶ ClickHouse (insert)               │
  │  Query Engine ───TCP:9000──▶ ClickHouse (select)                │
  │  Query Engine ───DuckDB────▶ S3/MinIO (cold queries)            │
  │  Lifecycle Mgr ──TCP:9000──▶ ClickHouse (DDL, OPTIMIZE)        │
  │  Lifecycle Mgr ──S3 API────▶ S3/MinIO (export, delete)         │
  │  Lifecycle Mgr ──REST──────▶ Iceberg Catalog (metadata)        │
  │  ClickHouse ─────Raft──────▶ ClickHouse Keeper (consensus)     │
  │  ClickHouse ─────S3 API────▶ S3/MinIO (warm volume, backups)   │
  │  Monitoring ─────TCP:9000──▶ ClickHouse (system tables)        │
  │  Monitoring ─────HTTP──────▶ MinIO (metrics endpoint)           │
  │                                                                  │
  │  Ports:                                                          │
  │    9000 — ClickHouse native TCP                                  │
  │    8123 — ClickHouse HTTP                                        │
  │    9181 — ClickHouse Keeper client                               │
  │    9234 — ClickHouse Keeper Raft                                 │
  │    9363 — ClickHouse Prometheus metrics                          │
  │    9000 — MinIO S3 API                                           │
  │    9001 — MinIO Console                                          │
  │    8181 — Iceberg REST Catalog                                   │
  └─────────────────────────────────────────────────────────────────┘
```

---

## 17. Success Metrics

### 17.1 Phase 1 (Foundation) Success Criteria

| Metric | Target | Validation Method |
|--------|--------|-------------------|
| ClickHouse cluster operational | 3 shards, 2 replicas each | Cluster health check |
| Ingest throughput | > 500K rows/sec sustained | Load test with synthetic data |
| Query latency (hot, simple) | p99 < 2s | Benchmark suite |
| Compression ratio (logs) | > 8:1 | `system.columns` measurement |
| Tiering (hot → warm) | Automatic, no data loss | Integration test |
| Multi-tenant isolation | No cross-tenant data leaks | Security audit |
| Backup/restore | Full and incremental working | DR drill |
| Self-monitoring | All metrics exposed, alerts firing | Monitoring dashboard |

### 17.2 Phase 2 (Maturity) Success Criteria

| Metric | Target | Validation Method |
|--------|--------|-------------------|
| Ingest throughput | > 2M rows/sec sustained | Production measurement |
| Query latency (hot, complex) | p99 < 5s | Production p99 |
| Cold tier query | p99 < 30s for 90-day scan | Production measurement |
| Storage cost | < $1.00/GB/month blended | Finance reporting |
| Uptime | > 99.95% | SLA monitoring |
| Data loss incidents | 0 | Incident tracking |
| Successful tenant migrations | > 10 tenants migrated from other platforms | Customer success tracking |

### 17.3 Long-Term (12 months post-GA) Targets

| Metric | Target |
|--------|--------|
| Ingest throughput (cluster) | 10M+ rows/sec |
| Active tenants | 500+ |
| Total data under management | 1 PB+ |
| Storage cost | < $0.50/GB/month blended |
| Query latency (hot) | p50 < 200ms, p99 < 1s |
| Uptime | > 99.99% |
| Zero data loss incidents | 0 for 12 consecutive months |

---

## 18. Dependencies and Risks

### 18.1 Dependencies

| Dependency | Type | Owner | Impact if Delayed |
|-----------|------|-------|-------------------|
| ClickHouse 24.x+ | External software | ClickHouse Inc. | Use current stable; no blocker |
| ClickHouse Keeper | External software | ClickHouse Inc. | Fallback: ZooKeeper |
| MinIO | External software | MinIO Inc. | Fallback: AWS S3 directly |
| Apache Parquet libraries | External library | Apache | Well-established; low risk |
| Apache Iceberg (PyIceberg) | External library | Apache | Fallback: custom manifest catalog |
| DuckDB | External software | DuckDB Foundation | Fallback: ClickHouse S3 table function |
| NATS JetStream (PRD-01) | Internal module | RayOlly team | Storage cannot receive data without ingest pipeline |
| Kubernetes (PRD-13) | Infrastructure | Platform team | Storage can run bare-metal; K8s is for orchestration |
| Network infrastructure | Infrastructure | Infra team | 10Gbps+ between nodes required |
| NVMe SSD provisioning | Infrastructure | Infra team | Hot tier performance depends on NVMe |

### 18.2 Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| ClickHouse scaling limits (>50 shards) | Low | High | Abstract storage interface; evaluate Apache Doris or StarRocks as alternatives |
| ClickHouse Keeper instability under load | Low | High | Deploy 5-node Keeper quorum; fallback to ZooKeeper |
| Parquet/Iceberg schema evolution breaks backward compat | Medium | Medium | Pin library versions; test schema changes in staging; Iceberg handles evolution natively |
| S3 costs higher than projected (request costs) | Medium | Low | MinIO for self-hosted; batch S3 operations; use S3 Express One Zone for hot-ish cold data |
| Tenant data leak via misconfigured row policy | Low | Critical | Defense-in-depth: API gateway filter + ClickHouse row policy + audit logging; regular security testing |
| NVMe disk failure causing data loss | Medium | Medium | Replication factor 2 across AZs; no single point of failure |
| ClickHouse version upgrade breaks compatibility | Low | Medium | Pin major version; test upgrades in staging; maintain rollback plan |
| Cold tier query performance unacceptable for users | Medium | Medium | Pre-compute materialized views that survive tiering; cache frequent cold queries in Redis |
| GDPR erasure takes too long for large tenants | Medium | Medium | Partition-level drops are fast; row-level mutations are slow — design for partition drops |
| Noisy neighbor causes outage for other tenants | Medium | High | Resource quotas, priority scheduling, circuit breakers at query engine level |
| Backup corruption discovered during DR drill | Low | Critical | Regular DR drills (monthly); verify backup integrity with checksums; test restore process |
| Migration tools produce incorrect data mapping | Medium | Medium | Validation step after migration; row count + checksum comparison; sample-based correctness audit |

### 18.3 Open Questions

| # | Question | Decision Needed By | Owner |
|---|----------|-------------------|-------|
| 1 | Should we support ClickHouse Cloud (managed) as an alternative to self-managed? | Phase 2 | Architecture |
| 2 | What is the maximum number of tenants per shard before performance degrades? | Phase 1 (load test) | Storage team |
| 3 | Should rollup materialized views be managed by the storage engine or the query engine? | Phase 1 | Architecture |
| 4 | Iceberg REST catalog vs Hive Metastore vs Nessie catalog? | Phase 1 | Data platform |
| 5 | Should we support customer-managed encryption keys (CMEK) at the storage level? | Phase 2 | Security |
| 6 | DuckDB embedded vs DuckDB server for cold tier queries? | Phase 1 | Query engine team |
| 7 | How to handle schema changes in ClickHouse tables without downtime? | Phase 1 | Storage team |
| 8 | Should the warm tier use ClickHouse S3-backed tables instead of local cold volumes? | Phase 2 | Architecture |

---

## Appendix A: Glossary

| Term | Definition |
|------|-----------|
| Part | A ClickHouse data file containing sorted, compressed data for a portion of a partition |
| Partition | A logical grouping of parts by partition key (tenant_id + date) |
| Granule | The minimum unit of data ClickHouse reads (8,192 rows by default) |
| MergeTree | ClickHouse table engine family optimized for append-heavy analytical workloads |
| Skip index | Secondary index in ClickHouse that allows skipping granules during scans |
| TTL | Time-to-live: automatic data movement or deletion based on timestamp age |
| Shard | A horizontal partition of data across multiple ClickHouse nodes |
| Replica | A copy of a shard for high availability and read scaling |
| ClickHouse Keeper | Consensus system for ClickHouse replication (replaces ZooKeeper) |
| Parquet | Columnar file format for efficient analytical queries |
| Iceberg | Table format providing ACID transactions, schema evolution, and time travel on data lakes |
| DuckDB | Embedded analytical SQL engine optimized for Parquet/CSV scanning |
| Gorilla codec | Compression for float time-series using XOR of consecutive values |
| DoubleDelta codec | Compression for monotonically increasing integers (timestamps, counters) |
| LowCardinality | ClickHouse optimization that stores low-cardinality strings as dictionary-encoded integers |

## Appendix B: Reference Configuration — Minimum Viable Deployment

For development and small self-hosted deployments:

```yaml
# docker-compose.storage.yaml
version: "3.8"
services:
  clickhouse-01:
    image: clickhouse/clickhouse-server:24.12
    hostname: clickhouse-01
    ports:
      - "8123:8123"   # HTTP
      - "9000:9000"   # Native TCP
      - "9363:9363"   # Prometheus
    volumes:
      - ch_data_01:/var/lib/clickhouse
      - ./config/clickhouse:/etc/clickhouse-server/config.d
      - ./config/clickhouse/users:/etc/clickhouse-server/users.d
    environment:
      CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT: 1
    ulimits:
      nofile:
        soft: 262144
        hard: 262144
    deploy:
      resources:
        limits:
          cpus: "8"
          memory: 32G

  clickhouse-keeper-01:
    image: clickhouse/clickhouse-keeper:24.12
    hostname: clickhouse-keeper-01
    ports:
      - "9181:9181"
    volumes:
      - keeper_data_01:/var/lib/clickhouse-keeper
      - ./config/keeper:/etc/clickhouse-keeper

  minio:
    image: minio/minio:latest
    hostname: minio
    ports:
      - "9002:9000"   # S3 API (avoid port conflict with ClickHouse)
      - "9001:9001"   # Console
    volumes:
      - minio_data:/data
    environment:
      MINIO_ROOT_USER: rayolly
      MINIO_ROOT_PASSWORD: rayolly-secret-change-me
    command: server /data --console-address ":9001"

volumes:
  ch_data_01:
  keeper_data_01:
  minio_data:
```

---

*PRD-02 v1.0 | Storage Engine & Data Lifecycle | RayOlly Platform*
*Last updated: 2026-03-19*
*Next review: 2026-04-02*
