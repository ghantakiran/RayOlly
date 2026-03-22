-- ============================================================
-- RayOlly ClickHouse Schema v2 — Agent Observability
-- Unique differentiator: observability for AI agents themselves
-- ============================================================

CREATE DATABASE IF NOT EXISTS agents;

-- ============================================================
-- AGENT EXECUTIONS
-- Primary fact table for every agent invocation.
-- ============================================================

CREATE TABLE IF NOT EXISTS agents.agent_executions
(
    execution_id    String                           CODEC(ZSTD(1)),
    agent_type      LowCardinality(String)           CODEC(ZSTD(1)),
    tenant_id       LowCardinality(String)           CODEC(ZSTD(1)),
    status          LowCardinality(String)           CODEC(ZSTD(1)),       -- running, completed, failed, cancelled
    started_at      DateTime64(3, 'UTC')             CODEC(DoubleDelta, LZ4),
    completed_at    DateTime64(3, 'UTC')             CODEC(DoubleDelta, LZ4),
    duration_ms     UInt32                           CODEC(T64, LZ4),
    input_tokens    UInt32                           CODEC(T64, LZ4),
    output_tokens   UInt32                           CODEC(T64, LZ4),
    total_tokens    UInt32                           CODEC(T64, LZ4),
    cost_usd        Float64                          CODEC(Gorilla, LZ4),
    model           LowCardinality(String)           CODEC(ZSTD(1)),
    tool_calls_count UInt16                          CODEC(T64, LZ4),
    error_message   String                           CODEC(ZSTD(3)),
    steps_count     UInt16                           CODEC(T64, LZ4),

    -- Indexes for common query patterns
    INDEX idx_agent_type agent_type    TYPE set(32)              GRANULARITY 4,
    INDEX idx_status     status        TYPE set(8)               GRANULARITY 4,
    INDEX idx_model      model         TYPE set(16)              GRANULARITY 4,
    INDEX idx_error_msg  error_message TYPE tokenbf_v1(10240, 2, 0) GRANULARITY 1
)
ENGINE = MergeTree()
PARTITION BY (tenant_id, toYYYYMMDD(started_at))
ORDER BY (tenant_id, agent_type, started_at, execution_id)
TTL toDateTime(started_at) + INTERVAL 90 DAY DELETE,
    toDateTime(started_at) + INTERVAL 14 DAY TO VOLUME 'cold'
SETTINGS
    index_granularity = 8192,
    ttl_only_drop_parts = 1,


-- ============================================================
-- AGENT STEPS
-- Individual steps within an execution (thinking, tool calls, etc.)
-- ============================================================

CREATE TABLE IF NOT EXISTS agents.agent_steps
(
    execution_id    String                           CODEC(ZSTD(1)),
    step_number     UInt16                           CODEC(T64, LZ4),
    step_type       LowCardinality(String)           CODEC(ZSTD(1)),       -- thinking, tool_call, tool_result, response
    timestamp       DateTime64(3, 'UTC')             CODEC(DoubleDelta, LZ4),
    duration_ms     UInt32                           CODEC(T64, LZ4),
    tool_name       LowCardinality(String)           CODEC(ZSTD(1)),
    tokens_used     UInt32                           CODEC(T64, LZ4),
    content_preview String                           CODEC(ZSTD(3)),

    INDEX idx_step_type step_type TYPE set(8)        GRANULARITY 4,
    INDEX idx_tool_name tool_name TYPE set(128)      GRANULARITY 4,
    INDEX idx_content   content_preview TYPE tokenbf_v1(10240, 2, 0) GRANULARITY 1
)
ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (execution_id, step_number)
TTL toDateTime(timestamp) + INTERVAL 90 DAY DELETE,
    toDateTime(timestamp) + INTERVAL 14 DAY TO VOLUME 'cold'
SETTINGS
    index_granularity = 8192,
    ttl_only_drop_parts = 1,


-- ============================================================
-- AGENT FEEDBACK
-- User ratings (thumbs up/down) for agent executions
-- ============================================================

CREATE TABLE IF NOT EXISTS agents.agent_feedback
(
    execution_id    String                           CODEC(ZSTD(1)),
    tenant_id       LowCardinality(String)           CODEC(ZSTD(1)),
    user_id         String                           CODEC(ZSTD(1)),
    rating          LowCardinality(String)           CODEC(ZSTD(1)),       -- thumbs_up, thumbs_down
    comment         String                           CODEC(ZSTD(3)),
    timestamp       DateTime64(3, 'UTC')             CODEC(DoubleDelta, LZ4),

    INDEX idx_rating rating TYPE set(4) GRANULARITY 4
)
ENGINE = MergeTree()
PARTITION BY (tenant_id, toYYYYMM(timestamp))
ORDER BY (tenant_id, timestamp, execution_id)
TTL toDateTime(timestamp) + INTERVAL 365 DAY DELETE
SETTINGS
    index_granularity = 8192;


-- ============================================================
-- MATERIALIZED VIEWS — hourly agent metrics rollup
-- ============================================================

CREATE TABLE IF NOT EXISTS agents.agent_metrics_hourly
(
    tenant_id         LowCardinality(String)                                CODEC(ZSTD(1)),
    agent_type        LowCardinality(String)                                CODEC(ZSTD(1)),
    hour              DateTime                                              CODEC(DoubleDelta, LZ4),
    total_executions  SimpleAggregateFunction(sum, UInt64)                  CODEC(T64, LZ4),
    successful        SimpleAggregateFunction(sum, UInt64)                  CODEC(T64, LZ4),
    failed            SimpleAggregateFunction(sum, UInt64)                  CODEC(T64, LZ4),
    cancelled         SimpleAggregateFunction(sum, UInt64)                  CODEC(T64, LZ4),
    total_tokens      SimpleAggregateFunction(sum, UInt64)                  CODEC(T64, LZ4),
    total_cost        SimpleAggregateFunction(sum, Float64)                 CODEC(Gorilla, LZ4),
    total_tool_calls  SimpleAggregateFunction(sum, UInt64)                  CODEC(T64, LZ4),
    avg_duration_state AggregateFunction(avg, UInt32)                       CODEC(ZSTD(1)),
    p50_duration_state AggregateFunction(quantile(0.50), UInt32)            CODEC(ZSTD(1)),
    p95_duration_state AggregateFunction(quantile(0.95), UInt32)            CODEC(ZSTD(1))
)
ENGINE = AggregatingMergeTree()
PARTITION BY (tenant_id, toYYYYMM(hour))
ORDER BY (tenant_id, agent_type, hour)
TTL hour + INTERVAL 365 DAY DELETE
SETTINGS
    index_granularity = 8192;


CREATE MATERIALIZED VIEW IF NOT EXISTS agents.mv_agent_metrics_hourly
TO agents.agent_metrics_hourly
AS
SELECT
    tenant_id,
    agent_type,
    toStartOfHour(started_at)                    AS hour,
    count()                                      AS total_executions,
    countIf(status = 'completed')                AS successful,
    countIf(status = 'failed')                   AS failed,
    countIf(status = 'cancelled')                AS cancelled,
    sum(total_tokens)                            AS total_tokens,
    sum(cost_usd)                                AS total_cost,
    sum(tool_calls_count)                        AS total_tool_calls,
    avgState(duration_ms)                        AS avg_duration_state,
    quantileState(0.50)(duration_ms)             AS p50_duration_state,
    quantileState(0.95)(duration_ms)             AS p95_duration_state
FROM agents.agent_executions
GROUP BY
    tenant_id,
    agent_type,
    hour;
