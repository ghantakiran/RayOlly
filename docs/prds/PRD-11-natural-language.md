# PRD-11: Natural Language Interface & AI Assistant

**Product**: RayOlly — AI-Native Observability Platform
**Version**: 1.0
**Date**: 2026-03-19
**Status**: Draft
**Parent**: PRD-00 Platform Vision & Architecture
**Dependencies**: PRD-03 (Query Engine), PRD-06 (Logs), PRD-07 (Metrics), PRD-08 (Traces), PRD-10 (AI Agents)

---

## 1. Executive Summary

The Natural Language Interface (NLI) is the primary way non-SRE users interact with RayOlly's observability data. Rather than requiring engineers, product managers, and executives to learn RayQL, SQL, or PromQL, the NLI translates plain English questions into precise queries, executes them, and returns results as human-readable explanations with auto-suggested visualizations.

This is not a bolt-on chatbot. The NLI is a deeply integrated AI assistant that understands the user's tenant context — their services, metrics, log streams, recent incidents, deployments, and team structure. It supports multi-turn conversational debugging, proactive insights, and guided troubleshooting workflows that reduce MTTR by an estimated 60%.

**Key Differentiators vs. Competitors**:
- **Datadog Bits AI**: Limited to predefined queries; no true multi-turn conversation
- **Splunk AI Assistant**: SPL-focused; requires understanding Splunk concepts
- **New Relic NRQL copilot**: Single-turn only; no investigation context
- **RayOlly NLI**: Full multi-turn conversations with context carry-over, proactive insights, multi-modal responses, and guided investigation workflows

**Target Users**:

| User Persona | Primary Use Cases |
|---|---|
| **Backend Developer** | Debug service errors, understand latency spikes, correlate logs with traces |
| **Frontend Developer** | Check API error rates, investigate slow endpoints |
| **Engineering Manager** | Service health summaries, deployment impact, weekly reports |
| **Product Manager** | Feature usage metrics, error rates by feature area |
| **SRE** | Rapid incident triage, complex cross-service correlation |
| **Executive** | Platform reliability summaries, cost dashboards |

---

## 2. Goals & Non-Goals

### Goals

- Provide a natural language query interface that converts English to RayQL/SQL/PromQL with >90% accuracy on common query patterns
- Support multi-turn conversational debugging with context carry-over across 20+ turns
- Deliver context-aware responses that leverage the tenant's service catalog, recent incidents, and deployment history
- Auto-suggest visualizations for every query result
- Enable AI-guided troubleshooting with step-by-step investigation workflows
- Surface proactive insights without requiring user queries
- Integrate into every platform surface: web UI, Slack, API, CLI
- Maintain sub-5-second response times for simple queries
- Support investigation thread sharing and resumption
- Generate weekly AI reports per team/service

### Non-Goals

- Replace RayQL/SQL for power users who prefer writing queries directly
- Build a general-purpose AI chatbot (scoped to observability domain only)
- Provide real-time streaming responses for live tail (use existing live tail UI)
- Support natural language in non-English languages (Phase 1 is English only)
- Allow the NLI to take automated remediation actions (read-only in Phase 1)
- Fine-tune or host custom LLMs (use Claude API as primary engine)

---

## 3. Natural Language Query Engine

### 3.1 Overview

The NL Query Engine is the core translation layer that converts free-form English into executable queries. It operates across all three observability pillars (logs, metrics, traces) and supports hybrid queries that span multiple data sources.

```
┌─────────────────────────────────────────────────────────────────┐
│                    NL Query Engine                               │
│                                                                 │
│  ┌──────────┐   ┌──────────────┐   ┌──────────────────────┐   │
│  │  User NL  │──▶│    Intent    │──▶│   Query Plan         │   │
│  │  Input    │   │  Classifier  │   │   Generator          │   │
│  └──────────┘   └──────────────┘   └──────┬───────────────┘   │
│                                            │                    │
│                  ┌─────────────────────────▼──────────────┐    │
│                  │        Query Compiler                   │    │
│                  │                                         │    │
│                  │  ┌─────────┐ ┌────────┐ ┌───────────┐ │    │
│                  │  │  RayQL  │ │ PromQL │ │  Search   │ │    │
│                  │  │  / SQL  │ │        │ │  Query    │ │    │
│                  │  └────┬────┘ └───┬────┘ └─────┬─────┘ │    │
│                  └───────┼──────────┼────────────┼────────┘    │
│                          │          │            │              │
│                  ┌───────▼──────────▼────────────▼────────┐    │
│                  │         Query Executor                  │    │
│                  └──────────────────┬─────────────────────┘    │
│                                     │                          │
│                  ┌──────────────────▼─────────────────────┐    │
│                  │    Result Interpreter & Formatter       │    │
│                  │  (NL Explanation + Viz Suggestion)      │    │
│                  └────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Context-Aware Query Resolution

The query engine is not a generic NL-to-SQL translator. It understands the tenant's specific environment:

| Context Source | What It Provides | Example Impact |
|---|---|---|
| **Service Catalog** | All service names, owners, dependencies | Resolves "the payment service" to `service.name = "payment-api-v2"` |
| **Metric Registry** | Available metrics, their labels, units | Knows `http_request_duration_seconds` is a histogram |
| **Log Stream Index** | Available log sources, fields, formats | Knows `checkout-service` logs have a `transaction_id` field |
| **Trace Schema** | Span names, attributes, service graph | Understands "the database call in checkout" means the `db.query` span |
| **Recent Incidents** | Active and recent resolved incidents | When user says "the issue", maps to the current active incident |
| **Deployment History** | Recent deploys per service | Allows "since the last deploy" to resolve to a timestamp |
| **User History** | Past queries and investigations by this user | Learns user's typical services and preferred time ranges |

### 3.3 Multi-Turn Conversation Support

The NLI maintains conversation state across turns, allowing iterative query refinement:

**Example Multi-Turn Session**:

```
User: Show me error rates for all services
  → SELECT service, count(*) as errors
    FROM logs
    WHERE severity = 'ERROR' AND timestamp > now() - interval '1 hour'
    GROUP BY service ORDER BY errors DESC

User: Now filter to just the checkout service
  → SELECT count(*) as errors
    FROM logs
    WHERE severity = 'ERROR'
      AND service = 'checkout-api'
      AND timestamp > now() - interval '1 hour'

User: Go back 24 hours instead
  → SELECT count(*) as errors
    FROM logs
    WHERE severity = 'ERROR'
      AND service = 'checkout-api'
      AND timestamp > now() - interval '24 hours'

User: Break it down by hour
  → SELECT date_trunc('hour', timestamp) as hour, count(*) as errors
    FROM logs
    WHERE severity = 'ERROR'
      AND service = 'checkout-api'
      AND timestamp > now() - interval '24 hours'
    GROUP BY hour ORDER BY hour

User: Was there a deployment around the spike?
  → SELECT deployed_at, version, deployer, service
    FROM deployments
    WHERE service = 'checkout-api'
      AND deployed_at BETWEEN '2026-03-18T14:00:00Z' AND '2026-03-18T16:00:00Z'
```

### 3.4 Query Explanation

Every generated query can be explained in plain English:

```
User: explain this query
  → "This query counts error-level log entries from the checkout-api service
     over the last 24 hours, grouped by hour. It helps you see when errors
     spiked. The results are sorted chronologically so you can identify
     the exact window when errors increased."
```

### 3.5 Example Natural Language Queries (30+)

#### Log Queries

| # | Natural Language | Generated Query |
|---|---|---|
| 1 | "Show me all errors from the payment service in the last hour" | `SELECT * FROM logs WHERE service = 'payment-api' AND severity = 'ERROR' AND timestamp > now() - interval '1 hour' ORDER BY timestamp DESC LIMIT 100` |
| 2 | "How many 500 errors did we have today?" | `SELECT count(*) FROM logs WHERE status_code = 500 AND timestamp > today()` |
| 3 | "Show me logs with 'timeout' from any database service" | `SELECT * FROM logs WHERE message ILIKE '%timeout%' AND service IN (SELECT name FROM services WHERE category = 'database') AND timestamp > now() - interval '1 hour' LIMIT 100` |
| 4 | "What are the most common error messages this week?" | `SELECT message_pattern, count(*) as occurrences FROM log_patterns WHERE severity = 'ERROR' AND timestamp > now() - interval '7 days' GROUP BY message_pattern ORDER BY occurrences DESC LIMIT 20` |
| 5 | "Show me the logs right before the checkout service crashed" | `SELECT * FROM logs WHERE service = 'checkout-api' AND timestamp BETWEEN (SELECT crashed_at - interval '5 minutes' FROM incidents WHERE service = 'checkout-api' ORDER BY created_at DESC LIMIT 1) AND (SELECT crashed_at FROM incidents WHERE service = 'checkout-api' ORDER BY created_at DESC LIMIT 1) ORDER BY timestamp` |
| 6 | "Any OOM kills in the last 24 hours?" | `SELECT * FROM logs WHERE (message ILIKE '%OOMKilled%' OR message ILIKE '%out of memory%') AND timestamp > now() - interval '24 hours'` |
| 7 | "Show me all log entries for request ID abc-123" | `SELECT * FROM logs WHERE trace_id = 'abc-123' OR message LIKE '%abc-123%' ORDER BY timestamp` |
| 8 | "Compare error volume between this week and last week" | `SELECT date_trunc('day', timestamp) as day, count(*) as errors, CASE WHEN timestamp > now() - interval '7 days' THEN 'this_week' ELSE 'last_week' END as period FROM logs WHERE severity = 'ERROR' AND timestamp > now() - interval '14 days' GROUP BY day, period ORDER BY day` |
| 9 | "What new error types appeared after the last deploy?" | `SELECT DISTINCT message_pattern FROM log_patterns WHERE severity = 'ERROR' AND timestamp > (SELECT MAX(deployed_at) FROM deployments WHERE service = 'checkout-api') AND message_pattern NOT IN (SELECT DISTINCT message_pattern FROM log_patterns WHERE severity = 'ERROR' AND timestamp < (SELECT MAX(deployed_at) FROM deployments WHERE service = 'checkout-api'))` |
| 10 | "Show me slow database query logs over 5 seconds" | `SELECT * FROM logs WHERE service IN (SELECT name FROM services WHERE category = 'database') AND duration_ms > 5000 AND timestamp > now() - interval '1 hour' ORDER BY duration_ms DESC` |

#### Metric Queries

| # | Natural Language | Generated Query |
|---|---|---|
| 11 | "What's the p99 latency for the API gateway?" | `histogram_quantile(0.99, rate(http_request_duration_seconds_bucket{service="api-gateway"}[5m]))` |
| 12 | "Show me CPU usage across all nodes" | `avg by (node) (rate(node_cpu_seconds_total{mode!="idle"}[5m])) * 100` |
| 13 | "Is memory usage trending up on the payment service?" | `predict_linear(container_memory_usage_bytes{service="payment-api"}[1h], 3600)` |
| 14 | "Compare latency before and after the deploy" | `http_request_duration_seconds{service="checkout-api", quantile="0.95"} offset 1h` vs `http_request_duration_seconds{service="checkout-api", quantile="0.95"}` |
| 15 | "What's our current request rate?" | `sum(rate(http_requests_total[5m]))` |
| 16 | "Which service has the highest error rate right now?" | `topk(5, sum by (service) (rate(http_requests_total{status=~"5.."}[5m])) / sum by (service) (rate(http_requests_total[5m])))` |
| 17 | "Show me disk usage for the Kafka cluster" | `avg by (instance) (node_filesystem_avail_bytes{job="kafka-nodes"} / node_filesystem_size_bytes{job="kafka-nodes"}) * 100` |
| 18 | "How does today's traffic compare to last Tuesday?" | `sum(rate(http_requests_total[5m])) vs sum(rate(http_requests_total[5m] offset 7d))` |
| 19 | "Alert me if API latency exceeds 500ms" | Creates alert rule: `avg(rate(http_request_duration_seconds_sum{service="api-gateway"}[5m]) / rate(http_request_duration_seconds_count{service="api-gateway"}[5m])) > 0.5` |
| 20 | "Show me the pod autoscaling events for checkout" | `kube_hpa_status_current_replicas{hpa="checkout-api"} vs kube_hpa_spec_max_replicas{hpa="checkout-api"}` |

#### Trace Queries

| # | Natural Language | Generated Query |
|---|---|---|
| 21 | "Show me the slowest traces for checkout in the last hour" | `SELECT trace_id, duration_ms, root_service, root_operation FROM traces WHERE service = 'checkout-api' AND timestamp > now() - interval '1 hour' ORDER BY duration_ms DESC LIMIT 20` |
| 22 | "What's the typical trace path for a purchase?" | `SELECT span_name, service, avg(duration_ms) FROM spans WHERE root_operation = 'POST /api/purchase' GROUP BY span_name, service ORDER BY avg_start_offset` |
| 23 | "Find traces where the database took more than 2 seconds" | `SELECT DISTINCT trace_id FROM spans WHERE db.system IS NOT NULL AND duration_ms > 2000 AND timestamp > now() - interval '1 hour'` |
| 24 | "How many services does a typical checkout request touch?" | `SELECT avg(service_count) FROM (SELECT trace_id, count(DISTINCT service) as service_count FROM spans WHERE root_operation = 'POST /api/checkout' AND timestamp > now() - interval '1 hour' GROUP BY trace_id)` |
| 25 | "Show me traces with errors in the payment downstream" | `SELECT trace_id, duration_ms FROM traces WHERE trace_id IN (SELECT trace_id FROM spans WHERE service = 'payment-api' AND status_code = 'ERROR') AND timestamp > now() - interval '1 hour'` |

#### Cross-Pillar / Complex Queries

| # | Natural Language | Generated Query Type |
|---|---|---|
| 26 | "Why is checkout slow right now?" | Hybrid: metrics (latency) + traces (slow spans) + logs (errors) + deployments |
| 27 | "What changed in the last hour that could cause this?" | Hybrid: deployments + config changes + anomaly events |
| 28 | "Are any services degraded?" | Metrics: SLO burn rates across all services |
| 29 | "Give me a health summary for the platform team's services" | Hybrid: metrics + incidents + SLO status filtered by team ownership |
| 30 | "What's the blast radius if the Redis cluster goes down?" | Service dependency graph query |
| 31 | "Show me everything related to this trace ID" | Hybrid: trace waterfall + correlated logs + metric context at trace timestamp |
| 32 | "Which team owns the service with the most errors?" | Hybrid: logs (error count by service) + service catalog (ownership) |
| 33 | "Summarize what happened during last night's incident" | Hybrid: incident timeline + logs + metrics + traces + deployment history |

---

## 4. AI Assistant (Chat Interface)

### 4.1 Conversational Debugging

The AI Assistant goes beyond query translation. It conducts interactive investigations, asks clarifying questions, and synthesizes information from multiple data sources.

**Example Conversation — Investigating a Latency Spike**:

```
┌─────────────────────────────────────────────────────────────┐
│ RayOlly AI Assistant                                    ─ □ x│
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ You: Why is checkout slow right now?                        │
│                                                             │
│ AI: I can see checkout-api p95 latency is currently         │
│ 2.3s, which is 4x higher than the 24h baseline of          │
│ 580ms. Let me investigate...                                │
│                                                             │
│ I checked three areas:                                      │
│                                                             │
│ 1. **Traces**: The slowdown is concentrated in the          │
│    `db.query` span — avg 1.8s vs normal 200ms              │
│                                                             │
│ 2. **Metrics**: PostgreSQL connection pool utilization      │
│    is at 95% (normally 40%). Active connections: 47/50      │
│                                                             │
│ 3. **Logs**: I see 230 "connection pool exhausted"          │
│    warnings in the last 15 minutes                          │
│                                                             │
│ 📊 [Latency Chart]  [DB Pool Chart]  [Error Log Table]     │
│                                                             │
│ **Likely cause**: The PostgreSQL connection pool is          │
│ saturated. This started 18 minutes ago, which correlates    │
│ with a deploy of `checkout-api v2.14.3` at 14:32 UTC.      │
│                                                             │
│ Would you like me to:                                       │
│ • Compare the new deploy's DB query patterns vs previous?   │
│ • Check if other services sharing this DB are affected?     │
│ • Look at the specific queries causing pool exhaustion?     │
│                                                             │
│ You: Check the specific queries                             │
│                                                             │
│ AI: Found 3 query patterns consuming the pool:              │
│                                                             │
│ | Query Pattern          | Avg Duration | Count/min |       │
│ |------------------------|-------------|-----------|         │
│ | SELECT * FROM orders   | 3.2s        | 45        |        │
│ |   WHERE user_id = ?    |             |           |         │
│ |   (missing index)      |             |           |         │
│ | SELECT * FROM products | 890ms       | 120       |        │
│ |   JOIN inventory...    |             |           |         │
│ | INSERT INTO audit_log  | 450ms       | 200       |        │
│                                                             │
│ The `orders` query is new in v2.14.3 and is missing an      │
│ index on `user_id`. This single query type is consuming     │
│ 60% of the connection pool.                                 │
│                                                             │
│ **Recommendation**: Add an index on `orders.user_id` or     │
│ roll back to v2.14.2.                                       │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ Ask RayOlly anything...                              [Send] │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Guided Investigation

When the user's question is ambiguous, the AI asks clarifying questions before executing:

```
User: Something is wrong with our APIs
AI: I can help investigate. To narrow things down:
    1. Are you seeing errors, latency issues, or both?
    2. Is this affecting all APIs or specific services?
    3. When did you first notice the issue?

    Meanwhile, here's what I see across your API services right now:
    • api-gateway: ✅ Normal (p95: 120ms, error rate: 0.1%)
    • checkout-api: ⚠️ Elevated errors (error rate: 4.2%, up from 0.3%)
    • user-api: ✅ Normal (p95: 45ms, error rate: 0.05%)
    • inventory-api: ⚠️ High latency (p95: 890ms, up from 200ms)

    Should I dig into checkout-api and inventory-api?
```

### 4.3 Multi-Modal Responses

Every AI response can contain a mix of:

| Response Element | Description |
|---|---|
| **Text** | Natural language explanation and analysis |
| **Inline Charts** | Time-series, bar charts, heatmaps rendered inline |
| **Tables** | Structured data results with sortable columns |
| **Trace Waterfall** | Embedded trace visualization |
| **Service Map** | Dependency graph highlighting affected services |
| **Links** | Deep links to dashboards, log views, trace details |
| **Code Blocks** | Generated queries shown for transparency |
| **Action Buttons** | "Add to Dashboard", "Create Alert", "Share", "Copy Query" |

### 4.4 Investigation History

All conversations are persisted and searchable:

- **Resume**: Pick up any past investigation where you left off
- **Search**: Full-text search across all investigation threads
- **Bookmark**: Mark important investigations for future reference
- **Auto-tag**: AI automatically tags investigations by service, issue type, and severity

### 4.5 Shareable Investigation Threads

Any investigation can be shared with teammates:

```
POST /api/v1/investigations/{id}/share
{
  "share_with": ["team:platform", "user:jane@example.com"],
  "permissions": "read",
  "include_context": true
}
```

Shared threads include the full conversation, all generated queries, results, and visualizations. Recipients can fork a shared thread to continue their own investigation branch.

---

## 5. Context Engine

### 5.1 Architecture

The Context Engine assembles a rich context window for every LLM call, ensuring responses are specific to the user's environment rather than generic.

```
┌──────────────────────────────────────────────────────────────────┐
│                        Context Engine                             │
│                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐     │
│  │   Service     │  │  Incident    │  │  Deployment        │     │
│  │   Catalog     │  │  History     │  │  History           │     │
│  │              │  │              │  │                    │     │
│  │ - Names      │  │ - Active     │  │ - Last 7 days     │     │
│  │ - Owners     │  │ - Recent     │  │ - Per service     │     │
│  │ - Deps       │  │ - Patterns   │  │ - Changelogs      │     │
│  └──────┬───────┘  └──────┬───────┘  └────────┬───────────┘     │
│         │                  │                    │                  │
│  ┌──────▼──────────────────▼────────────────────▼───────────┐    │
│  │                Context Assembler                          │    │
│  │  Selects relevant context per query (token-budget aware)  │    │
│  └──────────────────────┬───────────────────────────────────┘    │
│                          │                                        │
│  ┌──────────────┐  ┌────▼─────────┐  ┌────────────────────┐     │
│  │   User       │  │   Merged     │  │  Schema            │     │
│  │   Profile    │  │   Context    │──▶│  Awareness         │     │
│  │              │  │   Window     │  │                    │     │
│  │ - Role       │  └──────────────┘  │ - Metric names    │     │
│  │ - Team       │                     │ - Log fields      │     │
│  │ - History    │                     │ - Trace attrs     │     │
│  └──────────────┘                     └────────────────────┘     │
└──────────────────────────────────────────────────────────────────┘
```

### 5.2 Service Catalog Awareness

The Context Engine maintains a synchronized view of the tenant's service catalog:

```json
{
  "service": "checkout-api",
  "owner_team": "commerce",
  "tier": "critical",
  "language": "go",
  "dependencies": ["payment-api", "inventory-api", "user-api", "postgresql", "redis"],
  "dependents": ["web-frontend", "mobile-bff"],
  "slo_targets": {
    "availability": "99.95%",
    "latency_p99": "500ms"
  },
  "recent_deploys": [
    {"version": "v2.14.3", "deployed_at": "2026-03-19T14:32:00Z", "deployer": "ci-bot"}
  ],
  "oncall": "alice@example.com",
  "runbook_url": "https://wiki.internal/runbooks/checkout-api"
}
```

### 5.3 User Role Awareness

Responses are tailored to the user's role:

| Role | Response Style | Detail Level | Default Scope |
|---|---|---|---|
| **SRE** | Technical, concise, action-oriented | Full: raw queries, exact metrics, span details | All services |
| **Developer** | Technical, focused on code paths | Moderate: relevant logs, traces, queries | Own team's services |
| **Manager** | Summary-focused, trends and impacts | High-level: charts, counts, SLO status | Team's services |
| **Executive** | Business impact, dollar figures | Executive summary: uptime, cost, trends | All services (aggregated) |

### 5.4 Historical Query Patterns

The engine learns from each user's query history to improve suggestions:

- **Frequent services**: Pre-loads context for services the user queries most
- **Preferred time ranges**: Defaults to user's typical time window
- **Common patterns**: Suggests queries similar to the user's past activity
- **Query corrections**: Learns from cases where the user refined a generated query

---

## 6. Query Generation Pipeline

### 6.1 Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Query Generation Pipeline                         │
│                                                                     │
│  Step 1: NL Input                                                   │
│  "Show me errors from checkout in the last hour"                    │
│         │                                                           │
│         ▼                                                           │
│  Step 2: Intent Classification                                      │
│  ┌─────────────────────────────────────────────┐                   │
│  │ intent: "log_search"                        │                   │
│  │ entities:                                    │                   │
│  │   severity: "ERROR"                         │                   │
│  │   service: "checkout-api" (resolved)        │                   │
│  │   time_range: "1 hour" (relative)           │                   │
│  │ confidence: 0.96                            │                   │
│  └─────────────────────┬───────────────────────┘                   │
│                         │                                           │
│         ▼                                                           │
│  Step 3: Query Plan                                                 │
│  ┌─────────────────────────────────────────────┐                   │
│  │ data_source: "logs"                         │                   │
│  │ query_type: "search_with_filter"            │                   │
│  │ filters:                                     │                   │
│  │   - field: "severity", op: "=", val: "ERROR"│                   │
│  │   - field: "service", op: "=",              │                   │
│  │     val: "checkout-api"                     │                   │
│  │   - field: "timestamp", op: ">",           │                   │
│  │     val: "now() - 1h"                       │                   │
│  │ sort: timestamp DESC                        │                   │
│  │ limit: 100                                  │                   │
│  └─────────────────────┬───────────────────────┘                   │
│                         │                                           │
│         ▼                                                           │
│  Step 4: Query Compilation                                          │
│  ┌─────────────────────────────────────────────┐                   │
│  │ SELECT timestamp, severity, message,        │                   │
│  │        trace_id, span_id                    │                   │
│  │ FROM logs                                    │                   │
│  │ WHERE severity = 'ERROR'                    │                   │
│  │   AND service = 'checkout-api'              │                   │
│  │   AND timestamp > now() - interval '1 hour' │                   │
│  │ ORDER BY timestamp DESC                     │                   │
│  │ LIMIT 100                                   │                   │
│  └─────────────────────┬───────────────────────┘                   │
│                         │                                           │
│         ▼                                                           │
│  Step 5: Execution                                                  │
│  ┌─────────────────────────────────────────────┐                   │
│  │ Query routed to ClickHouse logs table       │                   │
│  │ Execution time: 120ms                       │                   │
│  │ Rows returned: 47                           │                   │
│  └─────────────────────┬───────────────────────┘                   │
│                         │                                           │
│         ▼                                                           │
│  Step 6: Result Interpretation                                      │
│  ┌─────────────────────────────────────────────┐                   │
│  │ NL: "Found 47 errors from checkout-api in   │                   │
│  │ the last hour. The most frequent error is    │                   │
│  │ 'connection pool exhausted' (31 occurrences).│                   │
│  │ Errors spiked at 14:35 UTC."                │                   │
│  │                                              │                   │
│  │ Suggested viz: time-series bar chart         │                   │
│  │ Suggested follow-up: "What happened at       │                   │
│  │ 14:35? Want me to check for deployments?"   │                   │
│  └─────────────────────────────────────────────┘                   │
└─────────────────────────────────────────────────────────────────────┘
```

### 6.2 Intent Classification

Supported intent categories:

| Intent Category | Sub-Intents | Example |
|---|---|---|
| **log_search** | search, count, pattern, compare, tail | "Show me errors from..." |
| **metric_query** | current_value, time_series, comparison, forecast | "What's the p99 latency..." |
| **trace_search** | find_traces, trace_detail, span_analysis | "Show me slow traces..." |
| **investigation** | root_cause, impact_analysis, correlation | "Why is X slow?" |
| **status** | health_check, slo_status, service_summary | "Is checkout healthy?" |
| **management** | create_alert, create_dashboard, share | "Alert me if..." |
| **explanation** | explain_query, explain_metric, explain_alert | "What does this query do?" |
| **meta** | help, capabilities, feedback | "What can you do?" |

### 6.3 Error Handling and Query Refinement

When query generation fails or returns unexpected results:

```
Pipeline Step          Error Type                  Recovery Action
─────────────         ──────────                  ───────────────
Intent Classification  Low confidence (<0.7)       Ask clarifying question
Entity Resolution      Unknown service name        Suggest closest matches
Query Compilation      Invalid syntax              Retry with simpler query
Execution              Timeout (>30s)              Add stricter time/limit bounds
Execution              No results                  Suggest broader query
Interpretation         Results don't match intent  Flag and ask user to confirm
```

**Example Error Recovery**:

```
User: Show me errors from the payroll service

AI: I don't see a service called "payroll" in your environment.
    Did you mean one of these?
    • payment-api (Commerce team)
    • payroll-processor (HR Platform team) — note: this service
      sends data to a different RayOlly tenant
    • payout-service (Finance team)
```

---

## 7. Visualization Suggestions

### 7.1 Auto-Suggest Logic

The AI automatically recommends the best chart type based on the query result shape:

| Result Shape | Suggested Visualization | Rationale |
|---|---|---|
| Single numeric value | Stat panel (big number) | Immediate readability |
| Time-series (1 metric) | Line chart | Trend visibility |
| Time-series (2-5 metrics) | Multi-line chart | Comparison |
| Time-series (6+ metrics) | Stacked area chart or heatmap | Density view |
| Categorical counts | Bar chart (horizontal) | Easy label reading |
| Distribution | Histogram or box plot | Percentile visibility |
| Top-N ranking | Bar chart (sorted) | Rank comparison |
| Geographic data | Map overlay | Spatial patterns |
| Trace spans | Waterfall / Gantt chart | Temporal flow |
| Service dependencies | Directed graph | Relationship mapping |
| Log entries | Scrollable table | Detail inspection |
| Before/after comparison | Side-by-side panels | Change detection |

### 7.2 One-Click "Add to Dashboard"

Any visualization generated in the chat can be persisted:

```
User: Show me error rate by service over the last 24 hours

AI: [Renders stacked bar chart]

    Here's the error rate breakdown. checkout-api accounts for
    62% of all errors.

    [Add to Dashboard ▼]  [Copy Query]  [Share]  [Expand]
         │
         ├── Add to "Commerce Team" dashboard
         ├── Add to "Platform Overview" dashboard
         ├── Create new dashboard
         └── Add as widget to investigation
```

### 7.3 Inline Charts in Chat

Charts are rendered directly in the conversation thread using the platform's charting library (same renderer as dashboards). They are interactive: hoverable, zoomable, and clickable (clicking a data point opens the relevant detail view).

---

## 8. AI-Guided Troubleshooting

### 8.1 Step-by-Step Investigation Workflows

The AI follows structured investigation runbooks while maintaining natural conversation:

```
┌─────────────────────────────────────────────────────────────┐
│           AI-Guided Troubleshooting Workflow                 │
│                                                             │
│  ┌──────────────┐                                          │
│  │  Symptom     │  "Checkout is slow"                      │
│  │  Detection   │                                           │
│  └──────┬───────┘                                          │
│         │                                                   │
│         ▼                                                   │
│  ┌──────────────┐                                          │
│  │  Scope       │  Which services? Since when?             │
│  │  Definition  │  How severe? Who is affected?            │
│  └──────┬───────┘                                          │
│         │                                                   │
│         ▼                                                   │
│  ┌──────────────┐                                          │
│  │  Evidence    │  Metrics: latency, error rate, saturation│
│  │  Gathering   │  Logs: error patterns, warnings          │
│  │              │  Traces: slow spans, bottlenecks         │
│  └──────┬───────┘                                          │
│         │                                                   │
│         ▼                                                   │
│  ┌──────────────┐                                          │
│  │  Change      │  Recent deploys? Config changes?         │
│  │  Correlation │  Traffic pattern changes?                │
│  └──────┬───────┘                                          │
│         │                                                   │
│         ▼                                                   │
│  ┌──────────────┐                                          │
│  │  Hypothesis  │  Ranked list of probable causes          │
│  │  Generation  │  with supporting evidence                │
│  └──────┬───────┘                                          │
│         │                                                   │
│         ▼                                                   │
│  ┌──────────────┐                                          │
│  │  Similar     │  Match against historical incidents      │
│  │  Incident    │  for resolution guidance                 │
│  │  Matching    │                                          │
│  └──────┬───────┘                                          │
│         │                                                   │
│         ▼                                                   │
│  ┌──────────────┐                                          │
│  │  Suggested   │  Specific actions with links             │
│  │  Actions     │  to relevant dashboards/runbooks         │
│  └──────────────┘                                          │
└─────────────────────────────────────────────────────────────┘
```

### 8.2 Root Cause Hypothesis Generation

The AI generates ranked hypotheses with evidence scores:

```
AI: Based on my investigation, here are the most likely causes,
    ranked by evidence strength:

    1. [92% confidence] Missing database index on orders.user_id
       Evidence:
       • New query pattern in v2.14.3 doing full table scan
       • DB CPU at 89%, query duration 3.2s avg
       • Connection pool at 95% capacity
       • Issue started exactly when v2.14.3 was deployed

    2. [35% confidence] Increased traffic from marketing campaign
       Evidence:
       • Request rate is 1.4x normal for this time of day
       Contradicting:
       • Traffic increase alone doesn't explain DB saturation
       • Issue correlates with deploy, not with traffic ramp

    3. [15% confidence] Underlying infrastructure issue
       Evidence:
       • None found — all node metrics normal
       Contradicting:
       • Issue is service-specific, not infrastructure-wide
```

### 8.3 Similar Past Incident Matching

The AI searches the incident history for similar patterns:

```
AI: This looks similar to INC-2847 from 2026-02-03:
    • Same symptom: checkout-api latency spike
    • Same root cause category: missing database index
    • Resolution: Added index, latency returned to normal in 2 minutes
    • Resolved by: @bob from the commerce team

    Would you like me to pull up that incident's resolution steps?
```

---

## 9. Proactive Insights

### 9.1 "Things You Should Know"

The AI generates unsolicited insights when it detects notable patterns. These appear as non-intrusive cards in the UI.

| Insight Type | Example | Trigger |
|---|---|---|
| **Anomaly Summary** | "Error rate for user-api has been 3x normal for the last 30 minutes" | Statistical anomaly detected |
| **Deployment Impact** | "Since deploying payment-api v3.1.0 two hours ago, p99 latency improved 25%" | Post-deploy metric shift |
| **Trending Issue** | "Connection timeout errors have been increasing 15% daily for a week" | Trend detection |
| **Capacity Warning** | "At current growth rate, the Kafka cluster will hit disk limits in 12 days" | Forecast threshold crossing |
| **Cost Insight** | "The new debug logging in auth-service is generating 2TB/day extra. Estimated cost impact: $340/month" | Log volume anomaly |
| **SLO Risk** | "checkout-api has burned 40% of its monthly error budget in the first week" | SLO burn rate calculation |

### 9.2 Weekly AI-Generated Reports

Automated weekly digests per team:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Commerce Team — Weekly Observability Report
  Week of March 10–16, 2026
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Reliability
  ├── Availability: 99.97% (target: 99.95%) ✅
  ├── P99 Latency: 420ms (target: 500ms) ✅
  ├── Error Budget Remaining: 68% ✅
  └── Incidents: 2 (1 P2, 1 P3)

  Notable Events
  ├── checkout-api v2.14.2 deployed (Tue) — no issues
  ├── payment-api timeout spike (Wed, 15min) — auto-resolved
  └── inventory-api memory leak fix (Thu) — 30% memory reduction

  Trends
  ├── Request volume: +8% WoW (seasonal increase)
  ├── Error rate: -12% WoW (improved after Thu fix)
  └── Log volume: +45% WoW ⚠️ (investigate debug logging)

  AI Recommendations
  ├── Consider adding index on orders.created_at (slow query detected)
  ├── Review payment-api retry logic (3x retry storms observed)
  └── Archive audit_log entries older than 90 days (table growing 2GB/day)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 9.3 Trending Issues Notification

The AI identifies slow-burn issues that individual alerts miss:

- Gradual latency increases over days
- Slowly growing error rates
- Memory leaks
- Disk space consumption trends
- Certificate expiration approaching
- Dependency version security advisories

### 9.4 Cost Optimization Suggestions

```
AI: I identified 3 cost optimization opportunities:

    1. High-cardinality metric reduction — $1,200/mo savings
       The metric `http_request_duration_seconds` has label
       `request_id` with 2M unique values. Removing this label
       would reduce storage by 89%.

    2. Log level optimization — $800/mo savings
       auth-service is logging at DEBUG level in production.
       Switching to INFO would reduce log volume by 73%.

    3. Unused dashboards cleanup — indirect savings
       14 dashboards haven't been viewed in 90+ days. The queries
       backing them consume 8% of query capacity.
```

---

## 10. Integration Points

### 10.1 Embedded Chat (Floating Button)

Present on every page. Context-aware based on the current view:

- On a dashboard: "Ask about the metrics on this dashboard"
- On a log view: "Ask about these log entries"
- On a trace view: "Ask about this trace"
- On an alert: "Ask about why this alert fired"

### 10.2 Slack Bot Integration

```
/rayolly ask Why is checkout slow?

@RayOlly show me error rates for payment-api

/rayolly investigate INC-3421

/rayolly report commerce-team weekly
```

The Slack bot supports:
- Threaded conversations (same multi-turn support as web UI)
- Inline chart images (rendered server-side, posted as Slack image blocks)
- Action buttons for common follow-ups
- Incident channel auto-join and context injection
- Scheduled reports to channels

### 10.3 API for Programmatic Access

```
POST /api/v1/nl/query
{
  "query": "Show me error rates for checkout in the last hour",
  "conversation_id": "conv-abc123",  // optional, for multi-turn
  "response_format": "json",         // json | markdown | chart_spec
  "max_results": 100,
  "timeout_ms": 10000
}

Response:
{
  "conversation_id": "conv-abc123",
  "intent": "log_search",
  "generated_query": {
    "type": "sql",
    "query": "SELECT ... FROM logs WHERE ...",
    "execution_time_ms": 145
  },
  "results": { ... },
  "explanation": "Found 47 errors from checkout-api...",
  "visualization": {
    "type": "time_series_bar",
    "spec": { ... }
  },
  "suggested_followups": [
    "What happened at the error spike?",
    "Compare with yesterday",
    "Check related traces"
  ]
}
```

### 10.4 CLI Tool Integration

```bash
# Interactive mode
$ rayolly chat
RayOlly> show me errors from checkout in the last hour
Found 47 errors. Top error: "connection pool exhausted" (31 occurrences).
RayOlly> break it down by hour
[ASCII chart rendered in terminal]

# Single query mode
$ rayolly ask "what's the p99 latency for api-gateway?"
Current p99 latency for api-gateway: 125ms (normal range: 80-150ms)

# Pipe-friendly mode
$ rayolly ask --format json "error count by service today" | jq '.results'
```

---

## 11. LLM Architecture

### 11.1 System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      LLM Architecture                                │
│                                                                     │
│  ┌──────────┐   ┌──────────────────────────────────────────────┐   │
│  │  User    │   │            NLI Service                        │   │
│  │  Request │──▶│                                               │   │
│  └──────────┘   │  ┌────────────┐   ┌──────────────────────┐  │   │
│                  │  │  Prompt    │   │   Context Engine      │  │   │
│                  │  │  Builder   │◀──│   (RAG Pipeline)      │  │   │
│                  │  └─────┬──────┘   │                       │  │   │
│                  │        │          │  ┌─────────────────┐  │  │   │
│                  │        │          │  │ Vector Store     │  │  │   │
│                  │        │          │  │ (Query Patterns) │  │  │   │
│                  │        │          │  └─────────────────┘  │  │   │
│                  │        │          │  ┌─────────────────┐  │  │   │
│                  │        │          │  │ Service Catalog  │  │  │   │
│                  │        │          │  │ Cache            │  │  │   │
│                  │        │          │  └─────────────────┘  │  │   │
│                  │        │          │  ┌─────────────────┐  │  │   │
│                  │        │          │  │ Schema Registry  │  │  │   │
│                  │        │          │  └─────────────────┘  │  │   │
│                  │        │          └──────────────────────┘  │   │
│                  │        ▼                                     │   │
│                  │  ┌────────────────────────────────────────┐ │   │
│                  │  │           LLM Router                    │ │   │
│                  │  │                                         │ │   │
│                  │  │  ┌─────────────┐  ┌────────────────┐  │ │   │
│                  │  │  │ Claude API  │  │  Local Model   │  │ │   │
│                  │  │  │ (Primary)   │  │  (Fallback)    │  │ │   │
│                  │  │  │             │  │  Llama 3 70B   │  │ │   │
│                  │  │  │ - Sonnet    │  │                │  │ │   │
│                  │  │  │   (queries) │  │  For air-gapped│  │ │   │
│                  │  │  │ - Opus      │  │  deployments   │  │ │   │
│                  │  │  │   (complex) │  │                │  │ │   │
│                  │  │  └─────────────┘  └────────────────┘  │ │   │
│                  │  └────────────────────────────────────────┘ │   │
│                  │                                              │   │
│                  │  ┌────────────────────────────────────────┐ │   │
│                  │  │       Response Cache (Redis)           │ │   │
│                  │  │  TTL: 5min for metrics, 1min for logs  │ │   │
│                  │  └────────────────────────────────────────┘ │   │
│                  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 11.2 Claude API as Primary Reasoning Engine

| Model | Use Case | Rationale |
|---|---|---|
| **Claude Sonnet** | Simple queries, intent classification, entity extraction | Fast (< 1s), cost-effective, sufficient for structured tasks |
| **Claude Opus** | Complex investigations, root cause analysis, multi-step reasoning | Superior reasoning for ambiguous, multi-source analysis |
| **Claude Haiku** | Query validation, result summarization, follow-up suggestions | Ultra-fast, minimal cost, good for auxiliary tasks |

### 11.3 Prompt Engineering Strategy

The system uses structured prompts with the following sections:

```
[SYSTEM PROMPT]
├── Role definition (observability expert)
├── Available data sources and schemas
├── Query syntax reference (RayQL, PromQL, SQL)
├── Output format specification
└── Safety guardrails

[CONTEXT INJECTION — via RAG]
├── Tenant service catalog (relevant subset)
├── Recent incidents (if applicable)
├── Recent deployments (if applicable)
├── User's query history (last 10)
└── Similar past queries and their validated SQL

[USER MESSAGE]
├── Current user query
├── Conversation history (summarized if long)
└── Current page context (if applicable)
```

Prompt versioning is managed via Git. All prompts are A/B testable. Prompt performance is tracked via accuracy metrics on a golden test set of 500+ query pairs.

### 11.4 RAG (Retrieval Augmented Generation) for Context

The RAG pipeline enriches LLM prompts with tenant-specific knowledge:

| RAG Source | Embedding Model | Index Type | Refresh Rate |
|---|---|---|---|
| Service catalog | text-embedding-3-small | HNSW (pgvector) | Real-time (CDC) |
| Metric/log schemas | text-embedding-3-small | HNSW (pgvector) | Every 5 minutes |
| Past query patterns | text-embedding-3-small | HNSW (pgvector) | Every query |
| Runbook content | text-embedding-3-small | HNSW (pgvector) | Hourly |
| Incident postmortems | text-embedding-3-small | HNSW (pgvector) | On creation |

### 11.5 Token Budget Management

| Component | Max Tokens | Strategy |
|---|---|---|
| System prompt | 2,000 | Static, versioned |
| Context (RAG) | 6,000 | Dynamic selection by relevance score |
| Conversation history | 4,000 | Sliding window with summarization |
| User message | 500 | Truncation with warning |
| Reserved for response | 4,000 | Hard limit with streaming |
| **Total budget** | **16,500** | Fits within Sonnet/Opus context windows |

For long conversations (>20 turns), the system:
1. Summarizes older turns into a 500-token synopsis
2. Preserves the last 5 turns verbatim
3. Retains all extracted entities and query context
4. Keeps investigation state (hypotheses, evidence, findings)

### 11.6 Caching Strategies

| Cache Layer | TTL | Key | Hit Rate Target |
|---|---|---|---|
| **Query translation cache** | 1 hour | hash(intent + entities + schema_version) | 40% |
| **Result cache** | 1–5 min (configurable) | hash(generated_query + time_bucket) | 25% |
| **Context cache** | 5 min | hash(tenant_id + service_catalog_version) | 80% |
| **Embedding cache** | 24 hours | hash(text_content) | 90% |
| **Conversation cache** | 24 hours | conversation_id | 95% |

### 11.7 Local Model Fallback for Air-Gapped Deployments

For customers who cannot send data to external APIs:

- **Primary local model**: Llama 3 70B (quantized to 4-bit for GPU efficiency)
- **Deployment**: vLLM server on customer-provided GPU nodes (minimum 2x A100 40GB)
- **Capability tradeoffs**: Reduced accuracy on complex investigations (~75% vs ~92% for Claude Opus), same performance on simple queries (~88% vs ~91%)
- **Prompt compatibility**: Same prompt templates, but with additional few-shot examples to compensate for weaker reasoning

---

## 12. Security & Privacy

### 12.1 No PII in LLM Prompts

All data sent to the LLM is scrubbed:

| Data Type | Handling |
|---|---|
| **Service names** | Passed through (non-PII, needed for resolution) |
| **Metric names/values** | Passed through (non-PII) |
| **Log messages** | PII redacted before LLM prompt (emails, IPs, tokens replaced with placeholders) |
| **User names** | Replaced with role identifiers |
| **Trace content** | Attribute values scrubbed; structure preserved |
| **Query results** | Aggregated results preferred; raw rows PII-redacted |

### 12.2 Tenant Data Isolation

- Every LLM call includes the tenant ID for routing and isolation
- RAG indices are per-tenant (no cross-tenant data in vector store)
- Conversation history is tenant-scoped with row-level security
- LLM prompt logs are stored per-tenant and subject to data retention policies

### 12.3 Query Audit Logging

Every NLI interaction is logged:

```json
{
  "timestamp": "2026-03-19T14:35:22Z",
  "tenant_id": "tenant-abc",
  "user_id": "user-xyz",
  "conversation_id": "conv-123",
  "input": "show me errors from checkout",
  "intent_classified": "log_search",
  "generated_query": "SELECT ... FROM logs ...",
  "query_executed": true,
  "result_row_count": 47,
  "response_time_ms": 2340,
  "llm_model": "claude-sonnet",
  "llm_tokens_used": 3420,
  "pii_redactions_applied": 0,
  "user_feedback": null
}
```

### 12.4 Content Filtering

- **Input filtering**: Reject prompt injection attempts, off-topic queries, abusive content
- **Output filtering**: Ensure AI responses don't hallucinate sensitive data, leak cross-tenant information, or provide harmful operational advice
- **Guardrails**: AI cannot suggest destructive actions (drop tables, delete data, scale to zero)
- **Rate limiting**: Per-user and per-tenant limits on NLI queries (default: 100/hour per user, 5,000/hour per tenant)

---

## 13. Frontend Components

### 13.1 Chat Panel

```
┌──────────────────────────────────────────────────────────────────┐
│ ◉ RayOlly AI Assistant                    [History] [─] [□] [×] │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│ ┌──────────────────────────────────────────────────────────────┐ │
│ │ [Suggested]  Error rate summary  │  Deployment impact  │     │ │
│ │              Service health      │  Current incidents   │     │ │
│ └──────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌─ AI ───────────────────────────────────────────────────────┐  │
│  │ Good morning, Alice. Here's what you should know:          │  │
│  │                                                             │  │
│  │ • checkout-api error rate is 3x normal (since 14:32 UTC)  │  │
│  │ • All other services are within normal ranges              │  │
│  │                                                             │  │
│  │ Would you like me to investigate the checkout errors?       │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌─ You ──────────────────────────────────────────────────────┐  │
│  │ Yes, what's causing the checkout errors?                    │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌─ AI ───────────────────────────────────────────────────────┐  │
│  │ I found 47 errors in the last hour. Here's the breakdown:  │  │
│  │                                                             │  │
│  │  Errors by Type                                            │  │
│  │  ┌────────────────────────────────────────────┐            │  │
│  │  │ ████████████████████████████████  31  Pool │            │  │
│  │  │ ████████████                      12  Timeout           │  │
│  │  │ ████                               4  Other│            │  │
│  │  └────────────────────────────────────────────┘            │  │
│  │                                                             │  │
│  │  "connection pool exhausted" is the top error (66%).       │  │
│  │  This started at 14:32 UTC, correlating with deploy        │  │
│  │  v2.14.3.                                                  │  │
│  │                                                             │  │
│  │  [View Logs]  [View Traces]  [View Deploy Diff]           │  │
│  │                                                             │  │
│  │  Would you like me to investigate the root cause?          │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
├──────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────┐  [⏎]  │
│  │ Type a question or press / for commands...            │       │
│  └──────────────────────────────────────────────────────┘       │
│  [📎 Attach Context]  [🔍 Show Query]  [📊 Visualize]          │
└──────────────────────────────────────────────────────────────────┘
```

### 13.2 Query Suggestion Bar

Appears at the top of log, metric, and trace explorer views:

```
┌──────────────────────────────────────────────────────────────────┐
│ Ask AI:  ┌──────────────────────────────────────────────────┐    │
│          │ "Show me errors from checkout in the last hour"   │    │
│          └──────────────────────────────────────────────────┘    │
│                                                                  │
│ Suggestions: [Errors by service] [Latency trends] [Recent deploys] │
│              [Current incidents] [Slow traces]                    │
└──────────────────────────────────────────────────────────────────┘
```

### 13.3 Investigation Workspace

For complex investigations, the chat expands into a full workspace:

```
┌──────────────────────────────────────────────────────────────────┐
│ Investigation: checkout-api latency spike          [Share] [Save]│
├──────────────────────────┬───────────────────────────────────────┤
│                          │                                       │
│    Chat Thread           │    Evidence Board                     │
│                          │                                       │
│  AI: Found root cause... │  ┌─ Metrics ───────────────────────┐ │
│                          │  │ [Latency chart]                  │ │
│  You: Show me the query  │  │ [DB Pool utilization chart]      │ │
│                          │  └──────────────────────────────────┘ │
│  AI: Here's the slow     │                                       │
│      query pattern...    │  ┌─ Logs ──────────────────────────┐ │
│                          │  │ [Error log table — 47 entries]   │ │
│  You: Check similar      │  └──────────────────────────────────┘ │
│       incidents          │                                       │
│                          │  ┌─ Timeline ──────────────────────┐ │
│  AI: Found INC-2847...   │  │ 14:32 Deploy v2.14.3            │ │
│                          │  │ 14:35 Error spike begins         │ │
│                          │  │ 14:37 Pool exhaustion warnings   │ │
│                          │  │ 14:42 Alert fired                │ │
│                          │  └──────────────────────────────────┘ │
│                          │                                       │
│  [Type a question...]    │  ┌─ Hypotheses ────────────────────┐ │
│                          │  │ 1. Missing index (92%)           │ │
│                          │  │ 2. Traffic spike (35%)           │ │
│                          │  │ 3. Infra issue (15%)             │ │
│                          │  └──────────────────────────────────┘ │
└──────────────────────────┴───────────────────────────────────────┘
```

---

## 14. Performance Requirements

### 14.1 Response Time SLAs

| Operation | Target | P99 | Timeout |
|---|---|---|---|
| Intent classification | < 500ms | < 1s | 2s |
| Simple NL to query generation | < 2s | < 3s | 5s |
| Simple NL query to results | < 5s | < 8s | 15s |
| Complex investigation step | < 10s | < 15s | 30s |
| Multi-source investigation | < 15s | < 25s | 45s |
| Weekly report generation | < 60s | < 120s | 300s |
| Context loading (RAG) | < 200ms | < 500ms | 1s |
| Streaming first token | < 1s | < 2s | 3s |

### 14.2 Throughput

| Metric | Target |
|---|---|
| Concurrent conversations per tenant | 50 |
| NL queries per second (platform-wide) | 500 |
| LLM API calls per second | 200 |
| RAG vector searches per second | 1,000 |

### 14.3 Availability

- NLI service: 99.9% uptime
- Graceful degradation: if LLM API is down, fall back to basic query templates
- Read-only mode: if context engine is degraded, respond with reduced context

---

## 15. Success Metrics

### 15.1 Adoption Metrics

| Metric | Target (3 months) | Target (12 months) |
|---|---|---|
| DAU of NLI (% of total DAU) | 30% | 60% |
| NL queries per user per day | 3 | 8 |
| Investigation threads created per week | 50 per tenant | 200 per tenant |
| Slack bot queries per day | 100 per tenant | 500 per tenant |

### 15.2 Quality Metrics

| Metric | Target |
|---|---|
| Query generation accuracy (correct SQL/PromQL) | >90% |
| Intent classification accuracy | >95% |
| User satisfaction (thumbs up/down) | >80% positive |
| Query refinement rate (user had to correct) | <15% |
| Zero-result rate (query returns nothing useful) | <5% |
| Hallucination rate (AI states incorrect facts) | <1% |

### 15.3 Impact Metrics

| Metric | Target |
|---|---|
| MTTR reduction for P1 incidents | 40% reduction |
| Time to first insight (new investigation) | <30 seconds |
| Queries previously requiring SRE help now self-served | 70% |
| Weekly report manual effort replaced | 90% |

---

## 16. Risks & Mitigations

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| 1 | **LLM generates incorrect queries** leading to wrong conclusions | High | High | Query validation layer, show generated query to user, confidence scoring, "explain this query" option, golden test set CI |
| 2 | **LLM hallucination** — AI states facts not supported by data | Medium | Critical | Ground all responses in retrieved data, citation links to source data, factuality checking pass on responses |
| 3 | **Prompt injection** — malicious users manipulate AI behavior | Medium | High | Input sanitization, system prompt hardening, output filtering, red-team testing quarterly |
| 4 | **Cost overrun** from LLM API usage | Medium | Medium | Token budget management, aggressive caching (40%+ hit rate target), Haiku for simple tasks, rate limiting per tenant |
| 5 | **Latency** — LLM response times degrade user experience | Medium | High | Streaming responses, parallel context loading, cache warm-up, model routing (Haiku for fast tasks) |
| 6 | **Context staleness** — AI uses outdated service catalog or schema | Low | Medium | Real-time CDC sync for catalog, schema refresh every 5 min, timestamp on all context data |
| 7 | **PII leakage** — sensitive data sent to LLM provider | Low | Critical | PII redaction pipeline before all LLM calls, automated PII detection tests, data classification tags |
| 8 | **Cross-tenant data leak** — AI references wrong tenant's data | Low | Critical | Tenant ID in every query, per-tenant RAG indices, integration tests for isolation, audit logging |
| 9 | **Over-reliance on AI** — users trust AI blindly without verification | Medium | Medium | Always show source data and generated queries, confidence indicators, "verify this" prompts for low-confidence responses |
| 10 | **Air-gapped deployment quality gap** — local models significantly weaker | Medium | Medium | Extensive few-shot examples, query template library, hybrid mode (local for simple, flagged for complex), quality benchmarks per deployment mode |

---

## 17. Milestones & Phasing

### Phase 1 — Foundation (Weeks 1–8)
- NL-to-SQL/PromQL query engine for single-pillar queries
- Basic chat interface with single-turn support
- Context engine with service catalog and schema awareness
- Query explanation feature
- Claude Sonnet integration

### Phase 2 — Conversations (Weeks 9–14)
- Multi-turn conversation support with context carry-over
- Investigation history and resumption
- Auto-visualization suggestions
- Inline charts in chat responses
- Slack bot (basic query support)

### Phase 3 — Intelligence (Weeks 15–20)
- AI-guided troubleshooting workflows
- Root cause hypothesis generation
- Similar incident matching
- Cross-pillar hybrid queries
- Investigation workspace UI

### Phase 4 — Proactive (Weeks 21–26)
- Proactive insights ("Things you should know")
- Weekly AI-generated reports
- Cost optimization suggestions
- Shareable investigation threads
- CLI tool integration
- Local model fallback for air-gapped deployments

---

*PRD-11 | Natural Language Interface & AI Assistant | RayOlly Platform*
