-- ============================================================
-- RayOlly ClickHouse Schema v1
-- Enterprise AI-native observability platform
-- ============================================================

-- ── Databases ───────────────────────────────────────────────
CREATE DATABASE IF NOT EXISTS logs;
CREATE DATABASE IF NOT EXISTS metrics;
CREATE DATABASE IF NOT EXISTS traces;
CREATE DATABASE IF NOT EXISTS events;
CREATE DATABASE IF NOT EXISTS system_audit;

-- ============================================================
-- LOGS
-- ============================================================

CREATE TABLE IF NOT EXISTS logs.log_entries
(
    tenant_id       LowCardinality(String)          CODEC(ZSTD(1)),
    log_id          UUID                             DEFAULT generateUUIDv4(),
    timestamp       DateTime64(9, 'UTC')             CODEC(DoubleDelta, LZ4),
    observed_ts     DateTime64(9, 'UTC')             CODEC(DoubleDelta, LZ4),
    severity        LowCardinality(String)           CODEC(ZSTD(1)),
    severity_number UInt8                            CODEC(T64, LZ4),
    service         LowCardinality(String)           CODEC(ZSTD(1)),
    service_version LowCardinality(String)           CODEC(ZSTD(1)),
    environment     LowCardinality(String)           CODEC(ZSTD(1)),
    host            LowCardinality(String)           CODEC(ZSTD(1)),
    body            String                           CODEC(ZSTD(3)),
    attributes      Map(String, String)              CODEC(ZSTD(3)),
    resource_attrs  Map(String, String)              CODEC(ZSTD(3)),
    trace_id        FixedString(32)                  CODEC(ZSTD(1)),
    span_id         FixedString(16)                  CODEC(ZSTD(1)),
    trace_flags     UInt8                            CODEC(T64, LZ4),

    -- Indexes
    INDEX idx_body body TYPE tokenbf_v1(30720, 2, 0) GRANULARITY 1,
    INDEX idx_body_ngrm body TYPE ngrambf_v1(3, 1024, 2, 0) GRANULARITY 1,
    INDEX idx_severity severity TYPE set(16) GRANULARITY 4,
    INDEX idx_service service TYPE set(256) GRANULARITY 4,
    INDEX idx_trace_id trace_id TYPE bloom_filter(0.01) GRANULARITY 1,
    INDEX idx_attrs_keys mapKeys(attributes) TYPE bloom_filter(0.01) GRANULARITY 1,
    INDEX idx_attrs_values mapValues(attributes) TYPE bloom_filter(0.01) GRANULARITY 1
)
ENGINE = MergeTree()
PARTITION BY (tenant_id, toYYYYMMDD(timestamp))
ORDER BY (tenant_id, service, severity, timestamp, log_id)
TTL toDateTime(timestamp) + INTERVAL 30 DAY DELETE,
    toDateTime(timestamp) + INTERVAL 7 DAY TO VOLUME 'cold'
SETTINGS
    index_granularity = 8192,
    ttl_only_drop_parts = 1,


-- ============================================================
-- METRICS
-- ============================================================

CREATE TABLE IF NOT EXISTS metrics.samples
(
    tenant_id       LowCardinality(String)           CODEC(ZSTD(1)),
    metric_name     LowCardinality(String)           CODEC(ZSTD(1)),
    metric_type     Enum8('gauge' = 0, 'counter' = 1, 'histogram' = 2, 'summary' = 3, 'exponential_histogram' = 4) CODEC(T64, LZ4),
    timestamp       DateTime64(3, 'UTC')             CODEC(DoubleDelta, LZ4),
    value           Float64                          CODEC(Gorilla, LZ4),
    service         LowCardinality(String)           CODEC(ZSTD(1)),
    environment     LowCardinality(String)           CODEC(ZSTD(1)),
    host            LowCardinality(String)           CODEC(ZSTD(1)),
    unit            LowCardinality(String)           CODEC(ZSTD(1)),
    labels          Map(String, String)              CODEC(ZSTD(3)),
    exemplar_trace_id FixedString(32)                CODEC(ZSTD(1)),
    exemplar_span_id  FixedString(16)                CODEC(ZSTD(1)),
    exemplar_value    Float64                        CODEC(Gorilla, LZ4),

    INDEX idx_metric_name metric_name TYPE set(1024) GRANULARITY 4,
    INDEX idx_service service TYPE set(256) GRANULARITY 4,
    INDEX idx_labels_keys mapKeys(labels) TYPE bloom_filter(0.01) GRANULARITY 1,
    INDEX idx_labels_values mapValues(labels) TYPE bloom_filter(0.01) GRANULARITY 1
)
ENGINE = MergeTree()
PARTITION BY (tenant_id, toYYYYMMDD(timestamp))
ORDER BY (tenant_id, metric_name, service, timestamp)
TTL toDateTime(timestamp) + INTERVAL 90 DAY DELETE,
    toDateTime(timestamp) + INTERVAL 14 DAY TO VOLUME 'cold'
SETTINGS
    index_granularity = 8192,
    ttl_only_drop_parts = 1,


-- Hourly rollups (AggregatingMergeTree)
CREATE TABLE IF NOT EXISTS metrics.rollups_1h
(
    tenant_id       LowCardinality(String)           CODEC(ZSTD(1)),
    metric_name     LowCardinality(String)           CODEC(ZSTD(1)),
    service         LowCardinality(String)           CODEC(ZSTD(1)),
    environment     LowCardinality(String)           CODEC(ZSTD(1)),
    labels          Map(String, String)              CODEC(ZSTD(3)),
    hour            DateTime                         CODEC(DoubleDelta, LZ4),
    min_val         SimpleAggregateFunction(min, Float64)  CODEC(Gorilla, LZ4),
    max_val         SimpleAggregateFunction(max, Float64)  CODEC(Gorilla, LZ4),
    sum_val         SimpleAggregateFunction(sum, Float64)  CODEC(Gorilla, LZ4),
    count_val       SimpleAggregateFunction(sum, UInt64)   CODEC(T64, LZ4),
    avg_state       AggregateFunction(avg, Float64)        CODEC(ZSTD(1)),
    p50_state       AggregateFunction(quantile(0.50), Float64) CODEC(ZSTD(1)),
    p95_state       AggregateFunction(quantile(0.95), Float64) CODEC(ZSTD(1)),
    p99_state       AggregateFunction(quantile(0.99), Float64) CODEC(ZSTD(1))
)
ENGINE = AggregatingMergeTree()
PARTITION BY (tenant_id, toYYYYMM(hour))
ORDER BY (tenant_id, metric_name, service, environment, hour)
TTL hour + INTERVAL 365 DAY DELETE
SETTINGS
    index_granularity = 8192;


-- Materialized view: raw samples -> hourly rollups
CREATE MATERIALIZED VIEW IF NOT EXISTS metrics.mv_rollup_1h
TO metrics.rollups_1h
AS
SELECT
    tenant_id,
    metric_name,
    service,
    environment,
    labels,
    toStartOfHour(timestamp) AS hour,
    min(value) AS min_val,
    max(value) AS max_val,
    sum(value) AS sum_val,
    count() AS count_val,
    avgState(value) AS avg_state,
    quantileState(0.50)(value) AS p50_state,
    quantileState(0.95)(value) AS p95_state,
    quantileState(0.99)(value) AS p99_state
FROM metrics.samples
GROUP BY
    tenant_id,
    metric_name,
    service,
    environment,
    labels,
    hour;


-- ============================================================
-- TRACES
-- ============================================================

CREATE TABLE IF NOT EXISTS traces.spans
(
    tenant_id         LowCardinality(String)          CODEC(ZSTD(1)),
    trace_id          FixedString(32)                  CODEC(ZSTD(1)),
    span_id           FixedString(16)                  CODEC(ZSTD(1)),
    parent_span_id    FixedString(16)                  CODEC(ZSTD(1)),
    trace_state       String                           CODEC(ZSTD(1)),
    span_name         LowCardinality(String)           CODEC(ZSTD(1)),
    span_kind         Enum8('UNSPECIFIED' = 0, 'INTERNAL' = 1, 'SERVER' = 2, 'CLIENT' = 3, 'PRODUCER' = 4, 'CONSUMER' = 5) CODEC(T64, LZ4),
    service           LowCardinality(String)           CODEC(ZSTD(1)),
    service_version   LowCardinality(String)           CODEC(ZSTD(1)),
    environment       LowCardinality(String)           CODEC(ZSTD(1)),
    start_time        DateTime64(9, 'UTC')             CODEC(DoubleDelta, LZ4),
    end_time          DateTime64(9, 'UTC')             CODEC(DoubleDelta, LZ4),
    duration_ns       UInt64                           CODEC(T64, LZ4),
    status_code       Enum8('UNSET' = 0, 'OK' = 1, 'ERROR' = 2) CODEC(T64, LZ4),
    status_message    String                           CODEC(LZ4HC(5)),
    attributes        Map(String, String)              CODEC(ZSTD(3)),
    resource_attrs    Map(String, String)              CODEC(ZSTD(3)),
    events            Nested(
                          name      String,
                          timestamp DateTime64(9, 'UTC'),
                          attrs     Map(String, String)
                      )                                CODEC(ZSTD(3)),
    links             Nested(
                          trace_id  FixedString(32),
                          span_id   FixedString(16),
                          attrs     Map(String, String)
                      )                                CODEC(ZSTD(3)),

    INDEX idx_trace_id trace_id TYPE bloom_filter(0.001) GRANULARITY 1,
    INDEX idx_service service TYPE set(256) GRANULARITY 4,
    INDEX idx_span_name span_name TYPE set(1024) GRANULARITY 4,
    INDEX idx_status_code status_code TYPE set(8) GRANULARITY 4,
    INDEX idx_duration duration_ns TYPE minmax GRANULARITY 4,
    INDEX idx_attrs_keys mapKeys(attributes) TYPE bloom_filter(0.01) GRANULARITY 1,
    INDEX idx_attrs_values mapValues(attributes) TYPE bloom_filter(0.01) GRANULARITY 1
)
ENGINE = MergeTree()
PARTITION BY (tenant_id, toYYYYMMDD(start_time))
ORDER BY (tenant_id, service, span_name, start_time, trace_id)
TTL toDateTime(start_time) + INTERVAL 30 DAY DELETE,
    toDateTime(start_time) + INTERVAL 7 DAY TO VOLUME 'cold'
SETTINGS
    index_granularity = 8192,
    ttl_only_drop_parts = 1,


-- Service dependency graph edges (SummingMergeTree)
CREATE TABLE IF NOT EXISTS traces.service_edges
(
    tenant_id       LowCardinality(String)           CODEC(ZSTD(1)),
    date            Date                              CODEC(DoubleDelta, LZ4),
    source_service  LowCardinality(String)           CODEC(ZSTD(1)),
    dest_service    LowCardinality(String)           CODEC(ZSTD(1)),
    source_env      LowCardinality(String)           CODEC(ZSTD(1)),
    dest_env        LowCardinality(String)           CODEC(ZSTD(1)),
    protocol        LowCardinality(String)           CODEC(ZSTD(1)),
    call_count      UInt64                           CODEC(T64, LZ4),
    error_count     UInt64                           CODEC(T64, LZ4),
    total_duration_ns UInt64                         CODEC(T64, LZ4),
    p50_duration_ns UInt64                           CODEC(T64, LZ4),
    p99_duration_ns UInt64                           CODEC(T64, LZ4)
)
ENGINE = SummingMergeTree((call_count, error_count, total_duration_ns))
PARTITION BY (tenant_id, toYYYYMM(date))
ORDER BY (tenant_id, date, source_service, dest_service, protocol)
TTL date + INTERVAL 90 DAY DELETE
SETTINGS
    index_granularity = 8192;


-- ============================================================
-- EVENTS
-- ============================================================

CREATE TABLE IF NOT EXISTS events.events
(
    tenant_id       LowCardinality(String)           CODEC(ZSTD(1)),
    event_id        UUID                             DEFAULT generateUUIDv4(),
    timestamp       DateTime64(6, 'UTC')             CODEC(DoubleDelta, LZ4),
    event_type      LowCardinality(String)           CODEC(ZSTD(1)),
    source          LowCardinality(String)           CODEC(ZSTD(1)),
    service         LowCardinality(String)           CODEC(ZSTD(1)),
    environment     LowCardinality(String)           CODEC(ZSTD(1)),
    severity        LowCardinality(String)           CODEC(ZSTD(1)),
    title           String                           CODEC(LZ4HC(5)),
    body            String                           CODEC(ZSTD(3)),
    attributes      Map(String, String)              CODEC(ZSTD(3)),
    tags            Array(LowCardinality(String))    CODEC(ZSTD(1)),
    trace_id        FixedString(32)                  CODEC(ZSTD(1)),
    related_ids     Array(String)                    CODEC(ZSTD(1)),

    INDEX idx_event_type event_type TYPE set(128) GRANULARITY 4,
    INDEX idx_service service TYPE set(256) GRANULARITY 4,
    INDEX idx_title title TYPE tokenbf_v1(10240, 2, 0) GRANULARITY 1,
    INDEX idx_tags tags TYPE bloom_filter(0.01) GRANULARITY 1
)
ENGINE = MergeTree()
PARTITION BY (tenant_id, toYYYYMMDD(timestamp))
ORDER BY (tenant_id, event_type, service, timestamp)
TTL toDateTime(timestamp) + INTERVAL 90 DAY DELETE
SETTINGS
    index_granularity = 8192;


-- ============================================================
-- AUDIT LOG
-- ============================================================

CREATE TABLE IF NOT EXISTS system_audit.audit_log
(
    tenant_id       LowCardinality(String)           CODEC(ZSTD(1)),
    event_id        UUID                             DEFAULT generateUUIDv4(),
    timestamp       DateTime64(6, 'UTC')             CODEC(DoubleDelta, LZ4),
    actor_id        String                           CODEC(ZSTD(1)),
    actor_type      LowCardinality(String)           CODEC(ZSTD(1)),
    action          LowCardinality(String)           CODEC(ZSTD(1)),
    resource_type   LowCardinality(String)           CODEC(ZSTD(1)),
    resource_id     String                           CODEC(ZSTD(1)),
    description     String                           CODEC(LZ4HC(5)),
    old_value       String                           CODEC(ZSTD(3)),
    new_value       String                           CODEC(ZSTD(3)),
    ip_address      IPv6                             CODEC(ZSTD(1)),
    user_agent      String                           CODEC(LZ4HC(5)),
    metadata        Map(String, String)              CODEC(ZSTD(3)),

    INDEX idx_actor actor_id TYPE bloom_filter(0.01) GRANULARITY 1,
    INDEX idx_action action TYPE set(128) GRANULARITY 4,
    INDEX idx_resource resource_type TYPE set(64) GRANULARITY 4
)
ENGINE = MergeTree()
PARTITION BY (tenant_id, toYYYYMM(timestamp))
ORDER BY (tenant_id, timestamp, actor_id)
TTL toDateTime(timestamp) + INTERVAL 365 DAY DELETE
SETTINGS
    index_granularity = 8192;
