# PRD-14: API Platform & Integration Ecosystem

**Product**: RayOlly — AI-Native Observability Platform
**Version**: 1.0
**Date**: 2026-03-19
**Status**: Draft
**Parent**: PRD-00 Platform Vision & Architecture
**Dependencies**: PRD-01 (Ingestion), PRD-02 (Storage), PRD-03 (Query Engine), PRD-06 (Logs), PRD-07 (Metrics), PRD-08 (Traces), PRD-10 (Alerts), PRD-11 (Natural Language), PRD-12 (AI Agents)

---

## 1. Executive Summary

The API Platform & Integration Ecosystem is the programmatic surface area of RayOlly, enabling every capability in the platform to be accessed, automated, and extended through well-defined APIs, SDKs, CLI tools, and third-party integrations. This PRD defines four complementary API protocols (REST, GraphQL, gRPC, WebSocket), client libraries in four languages, a full-featured CLI, a Terraform provider, webhook infrastructure, and an integration marketplace covering 50+ third-party systems.

**Key Differentiators**:
- Four API protocols optimized for different use cases — REST for simplicity, GraphQL for flexible frontend queries, gRPC for high-throughput ingestion, WebSocket for real-time streaming
- First-class AI Agent APIs — invoke, configure, and monitor autonomous agents programmatically
- Infrastructure-as-Code with a native Terraform provider for all platform resources
- SDK libraries that are idiomatic to each language, not thin HTTP wrappers
- Integration marketplace with both native and community-contributed connectors
- OpenAPI 3.1 spec auto-generated and always in sync with implementation

---

## 2. Goals & Non-Goals

### Goals
- Expose 100% of platform functionality through at least one API protocol
- Provide a REST API as the primary integration surface with comprehensive OpenAPI 3.1 documentation
- Offer GraphQL for flexible, frontend-optimized querying with real-time subscriptions
- Support gRPC for high-throughput ingestion (1M+ events/sec per connection) and internal service-to-service calls
- Deliver WebSocket APIs for live tail, dashboard streaming, and interactive agent sessions
- Ship SDKs for Python, JavaScript/TypeScript, Go, and Java with idiomatic design and async support
- Build a full-featured CLI (`rayolly-cli`) for terminal-native workflows
- Provide a Terraform provider for infrastructure-as-code management of all RayOlly resources
- Support outgoing and incoming webhooks with HMAC signing and at-least-once delivery
- Integrate natively with 50+ third-party tools across incident management, CI/CD, cloud, and infrastructure
- Maintain backward compatibility with a minimum 12-month deprecation window
- Achieve p99 API latency under 200ms for read endpoints and under 100ms for write acknowledgments

### Non-Goals
- Build a no-code integration builder in v1 (future scope — v2 with visual workflow editor)
- Support SOAP or XML-RPC protocols
- Replace existing third-party APIs (e.g., we integrate with PagerDuty, not replace it)
- Build mobile-specific SDKs (mobile apps use the TypeScript SDK)
- Provide an on-premise API gateway (customers use their own or our cloud endpoints)

---

## 3. REST API (v1)

### 3.1 API Design Principles

| Principle | Implementation |
|-----------|---------------|
| **RESTful resources** | Nouns for endpoints, HTTP verbs for actions, proper status codes |
| **Consistent naming** | `snake_case` for JSON fields, `/kebab-case/` for URL paths, plural nouns for collections |
| **Envelope response** | All responses wrapped in `{ "data": ..., "meta": ..., "errors": ... }` |
| **Cursor pagination** | Cursor-based pagination for large datasets; offset pagination for small, bounded sets |
| **Filtering** | Query parameter filters: `?filter[severity]=error&filter[service]=payment` |
| **Sorting** | `?sort=-timestamp,+severity` (prefix `-` for descending) |
| **Field selection** | `?fields=id,timestamp,message` to reduce payload size |
| **Idempotency** | `Idempotency-Key` header for all mutating operations |
| **Request IDs** | Every response includes `X-Request-Id` for tracing |
| **HATEOAS** | Links to related resources in `_links` field |

### 3.2 API Versioning Strategy

- URL-based versioning: `/api/v1/`, `/api/v2/`
- Version specified in URL path, not headers (simplicity over purity)
- Each major version is a full API surface; no partial versions
- Experimental endpoints prefixed with `/api/v1/preview/` — no stability guarantee
- Sunset header (`Sunset: Sat, 01 Mar 2028 00:00:00 GMT`) on deprecated endpoints
- `API-Version` response header indicates the version that served the request

### 3.3 Authentication

**Bearer Token (JWT)**:
```
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```
- Issued via OAuth 2.0 / OIDC flow
- Short-lived (1 hour), refreshable
- Contains tenant ID, user ID, roles, scopes
- Used by interactive clients (web app, CLI after login)

**API Key**:
```
X-API-Key: ro_live_k1_a3b8f9c2d1e4f5a6b7c8d9e0f1a2b3c4
```
- Prefixed with `ro_live_` (production) or `ro_test_` (sandbox)
- Scoped to specific permissions (read-only, write, admin)
- Tied to a service account, not a user
- Rotatable without downtime (two active keys per service account)
- Used by programmatic clients (SDKs, CI/CD, Terraform)

**Service-to-service (mTLS)**:
- Certificate-based auth for internal gRPC communication
- Not exposed to external consumers

### 3.4 Rate Limiting

| Tier | Requests/min | Burst | Ingestion Events/sec | Concurrent Connections |
|------|-------------|-------|---------------------|----------------------|
| **Free** | 60 | 10 | 1,000 | 5 |
| **Pro** | 600 | 100 | 50,000 | 50 |
| **Enterprise** | 6,000 | 1,000 | 500,000 | 500 |
| **Dedicated** | Custom | Custom | Custom | Custom |

Rate limit headers on every response:
```
X-RateLimit-Limit: 600
X-RateLimit-Remaining: 542
X-RateLimit-Reset: 1711843200
X-RateLimit-Policy: per-key
Retry-After: 30
```

Rate limiting is applied per API key or per bearer token. Tenant-level aggregate limits apply as a safety ceiling. Ingestion endpoints have separate rate limits from query endpoints.

### 3.5 Error Response Format

All errors follow RFC 7807 (Problem Details for HTTP APIs):

```json
{
  "type": "https://api.rayolly.com/errors/rate-limit-exceeded",
  "title": "Rate Limit Exceeded",
  "status": 429,
  "detail": "You have exceeded the rate limit of 600 requests per minute. Retry after 30 seconds.",
  "instance": "/api/v1/logs/search",
  "request_id": "req_a1b2c3d4e5f6",
  "errors": [
    {
      "code": "RATE_LIMIT_EXCEEDED",
      "message": "Per-key rate limit exceeded",
      "field": null
    }
  ],
  "meta": {
    "retry_after": 30,
    "limit": 600,
    "remaining": 0
  }
}
```

Standard error codes:

| HTTP Status | Code | Meaning |
|------------|------|---------|
| 400 | `INVALID_REQUEST` | Malformed request body or parameters |
| 401 | `UNAUTHORIZED` | Missing or invalid authentication |
| 403 | `FORBIDDEN` | Authenticated but insufficient permissions |
| 404 | `NOT_FOUND` | Resource does not exist |
| 409 | `CONFLICT` | Resource version conflict (optimistic locking) |
| 422 | `VALIDATION_ERROR` | Semantic validation failure |
| 429 | `RATE_LIMIT_EXCEEDED` | Rate limit exceeded |
| 500 | `INTERNAL_ERROR` | Server-side error |
| 503 | `SERVICE_UNAVAILABLE` | Temporary overload or maintenance |

### 3.6 Endpoint Inventory

#### 3.6.1 Logs API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/logs/search` | Search logs with query, filters, time range |
| `POST` | `/api/v1/logs/ingest` | Ingest log events (batch) |
| `GET` | `/api/v1/logs/{log_id}` | Get a single log event by ID |
| `POST` | `/api/v1/logs/aggregate` | Run aggregation queries on logs |
| `GET` | `/api/v1/logs/streams` | List saved log streams |
| `POST` | `/api/v1/logs/streams` | Create a saved log stream |
| `GET` | `/api/v1/logs/streams/{stream_id}` | Get a saved log stream |
| `PUT` | `/api/v1/logs/streams/{stream_id}` | Update a saved log stream |
| `DELETE` | `/api/v1/logs/streams/{stream_id}` | Delete a saved log stream |
| `GET` | `/api/v1/logs/patterns` | Get auto-detected log patterns |
| `GET` | `/api/v1/logs/patterns/{pattern_id}` | Get a specific pattern with examples |
| `POST` | `/api/v1/logs/export` | Trigger an async log export job |
| `GET` | `/api/v1/logs/fields` | List available log fields with cardinality |

**Example — Search Logs**:
```bash
curl -X POST https://api.rayolly.com/api/v1/logs/search \
  -H "Authorization: Bearer $RAYOLLY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "level:error AND service:payment-api",
    "time_range": {
      "from": "2026-03-19T00:00:00Z",
      "to": "2026-03-19T12:00:00Z"
    },
    "filters": {
      "severity": ["error", "critical"],
      "environment": ["production"]
    },
    "sort": [{ "field": "timestamp", "order": "desc" }],
    "limit": 50,
    "cursor": null
  }'
```

Response:
```json
{
  "data": {
    "logs": [
      {
        "id": "log_01HV3X9K2M4N5P6Q7R8S9T0U",
        "timestamp": "2026-03-19T11:45:23.456Z",
        "severity": "error",
        "service": "payment-api",
        "message": "Payment processing timeout after 30s for order_id=ORD-98765",
        "attributes": {
          "order_id": "ORD-98765",
          "customer_id": "cust_12345",
          "payment_provider": "stripe",
          "latency_ms": 30012
        },
        "trace_id": "abc123def456",
        "span_id": "span_789"
      }
    ],
    "cursor": "eyJsYXN0X2lkIjoibG9nXzAxSFYz..."
  },
  "meta": {
    "total_matched": 1247,
    "returned": 50,
    "query_time_ms": 42,
    "scanned_bytes": "2.3 GB"
  }
}
```

**Example — Ingest Logs**:
```bash
curl -X POST https://api.rayolly.com/api/v1/logs/ingest \
  -H "X-API-Key: ro_live_k1_a3b8f9c2d1e4f5a6b7c8d9e0f1a2b3c4" \
  -H "Content-Type: application/json" \
  -d '{
    "logs": [
      {
        "timestamp": "2026-03-19T11:50:00Z",
        "severity": "info",
        "service": "order-service",
        "message": "Order ORD-11111 created successfully",
        "attributes": {
          "order_id": "ORD-11111",
          "amount_cents": 4999,
          "currency": "USD"
        }
      },
      {
        "timestamp": "2026-03-19T11:50:01Z",
        "severity": "warn",
        "service": "order-service",
        "message": "Inventory check slow: 2.3s for SKU-555",
        "attributes": {
          "sku": "SKU-555",
          "latency_ms": 2300
        }
      }
    ]
  }'
```

#### 3.6.2 Metrics API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/metrics/query` | Query metrics with PromQL or RayQL |
| `POST` | `/api/v1/metrics/ingest` | Ingest metric data points (batch) |
| `GET` | `/api/v1/metrics/metadata` | List all metric names with metadata |
| `GET` | `/api/v1/metrics/metadata/{metric_name}` | Get metadata for a specific metric |
| `GET` | `/api/v1/metrics/labels` | List all label names |
| `GET` | `/api/v1/metrics/labels/{label_name}/values` | List values for a label |
| `POST` | `/api/v1/metrics/aggregate` | Run aggregation on metrics |
| `GET` | `/api/v1/metrics/slos` | List SLO definitions |
| `POST` | `/api/v1/metrics/slos` | Create an SLO |
| `GET` | `/api/v1/metrics/slos/{slo_id}` | Get SLO details with current status |
| `PUT` | `/api/v1/metrics/slos/{slo_id}` | Update an SLO |
| `DELETE` | `/api/v1/metrics/slos/{slo_id}` | Delete an SLO |

**Example — Query Metrics**:
```bash
curl -X POST https://api.rayolly.com/api/v1/metrics/query \
  -H "Authorization: Bearer $RAYOLLY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "rate(http_requests_total{service=\"api-gateway\", status=~\"5..\"}[5m])",
    "time_range": {
      "from": "2026-03-19T10:00:00Z",
      "to": "2026-03-19T12:00:00Z"
    },
    "step": "60s"
  }'
```

#### 3.6.3 Traces API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/traces/search` | Search traces by filters |
| `GET` | `/api/v1/traces/{trace_id}` | Get a full trace by ID |
| `GET` | `/api/v1/traces/{trace_id}/spans` | Get all spans for a trace |
| `GET` | `/api/v1/traces/{trace_id}/spans/{span_id}` | Get a specific span |
| `POST` | `/api/v1/traces/ingest` | Ingest trace spans (batch) |
| `GET` | `/api/v1/traces/service-map` | Get the service dependency map |
| `POST` | `/api/v1/traces/analytics` | Run trace analytics (latency distributions, error rates) |
| `GET` | `/api/v1/traces/services` | List discovered services |
| `GET` | `/api/v1/traces/services/{service_name}/operations` | List operations for a service |

**Example — Get Trace by ID**:
```bash
curl -X GET https://api.rayolly.com/api/v1/traces/abc123def456 \
  -H "Authorization: Bearer $RAYOLLY_TOKEN"
```

Response:
```json
{
  "data": {
    "trace_id": "abc123def456",
    "root_service": "api-gateway",
    "root_operation": "POST /api/orders",
    "duration_ms": 342,
    "span_count": 12,
    "error": true,
    "services": ["api-gateway", "order-service", "payment-api", "inventory-service"],
    "spans": [
      {
        "span_id": "span_001",
        "parent_span_id": null,
        "service": "api-gateway",
        "operation": "POST /api/orders",
        "start_time": "2026-03-19T11:45:23.100Z",
        "duration_ms": 342,
        "status": "error",
        "attributes": {
          "http.method": "POST",
          "http.status_code": 500,
          "http.url": "/api/orders"
        }
      }
    ]
  }
}
```

#### 3.6.4 Alerts API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/alerts/rules` | List alert rules |
| `POST` | `/api/v1/alerts/rules` | Create an alert rule |
| `GET` | `/api/v1/alerts/rules/{rule_id}` | Get an alert rule |
| `PUT` | `/api/v1/alerts/rules/{rule_id}` | Update an alert rule |
| `DELETE` | `/api/v1/alerts/rules/{rule_id}` | Delete an alert rule |
| `POST` | `/api/v1/alerts/rules/{rule_id}/test` | Test an alert rule against recent data |
| `GET` | `/api/v1/alerts/history` | List alert firing history |
| `GET` | `/api/v1/alerts/active` | List currently firing alerts |
| `GET` | `/api/v1/alerts/silences` | List silences |
| `POST` | `/api/v1/alerts/silences` | Create a silence |
| `DELETE` | `/api/v1/alerts/silences/{silence_id}` | Delete (expire) a silence |
| `GET` | `/api/v1/alerts/channels` | List notification channels |
| `POST` | `/api/v1/alerts/channels` | Create a notification channel |
| `PUT` | `/api/v1/alerts/channels/{channel_id}` | Update a notification channel |
| `POST` | `/api/v1/alerts/channels/{channel_id}/test` | Send a test notification |

**Example — Create Alert Rule**:
```bash
curl -X POST https://api.rayolly.com/api/v1/alerts/rules \
  -H "Authorization: Bearer $RAYOLLY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "High Error Rate - Payment API",
    "description": "Fires when payment-api 5xx rate exceeds 5% for 5 minutes",
    "type": "metric",
    "condition": {
      "query": "rate(http_requests_total{service=\"payment-api\", status=~\"5..\"}[5m]) / rate(http_requests_total{service=\"payment-api\"}[5m]) * 100",
      "operator": "greater_than",
      "threshold": 5,
      "for_duration": "5m"
    },
    "severity": "critical",
    "labels": { "team": "payments", "environment": "production" },
    "notification_channels": ["channel_slack_payments", "channel_pagerduty_p1"],
    "runbook_url": "https://wiki.internal/runbooks/payment-high-error-rate"
  }'
```

#### 3.6.5 Dashboards API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/dashboards` | List dashboards |
| `POST` | `/api/v1/dashboards` | Create a dashboard |
| `GET` | `/api/v1/dashboards/{dashboard_id}` | Get a dashboard with widgets |
| `PUT` | `/api/v1/dashboards/{dashboard_id}` | Update a dashboard |
| `DELETE` | `/api/v1/dashboards/{dashboard_id}` | Delete a dashboard |
| `POST` | `/api/v1/dashboards/{dashboard_id}/clone` | Clone a dashboard |
| `GET` | `/api/v1/dashboards/{dashboard_id}/widgets` | List widgets |
| `POST` | `/api/v1/dashboards/{dashboard_id}/widgets` | Add a widget |
| `PUT` | `/api/v1/dashboards/{dashboard_id}/widgets/{widget_id}` | Update a widget |
| `DELETE` | `/api/v1/dashboards/{dashboard_id}/widgets/{widget_id}` | Remove a widget |
| `POST` | `/api/v1/dashboards/{dashboard_id}/share` | Generate a share link |
| `GET` | `/api/v1/dashboards/templates` | List dashboard templates |

#### 3.6.6 Users & Teams API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/users` | List users in the organization |
| `GET` | `/api/v1/users/{user_id}` | Get user details |
| `PUT` | `/api/v1/users/{user_id}` | Update user settings |
| `DELETE` | `/api/v1/users/{user_id}` | Deactivate a user |
| `GET` | `/api/v1/users/{user_id}/api-keys` | List user's API keys |
| `POST` | `/api/v1/users/{user_id}/api-keys` | Create an API key |
| `DELETE` | `/api/v1/users/{user_id}/api-keys/{key_id}` | Revoke an API key |
| `GET` | `/api/v1/teams` | List teams |
| `POST` | `/api/v1/teams` | Create a team |
| `GET` | `/api/v1/teams/{team_id}` | Get team details |
| `PUT` | `/api/v1/teams/{team_id}` | Update a team |
| `DELETE` | `/api/v1/teams/{team_id}` | Delete a team |
| `POST` | `/api/v1/teams/{team_id}/members` | Add members to a team |
| `DELETE` | `/api/v1/teams/{team_id}/members/{user_id}` | Remove a member from a team |
| `GET` | `/api/v1/roles` | List available roles |

#### 3.6.7 AI Agents API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/agents` | List available AI agents |
| `GET` | `/api/v1/agents/{agent_id}` | Get agent details and capabilities |
| `POST` | `/api/v1/agents/{agent_id}/invoke` | Invoke an agent with a task |
| `GET` | `/api/v1/agents/{agent_id}/runs` | List agent run history |
| `GET` | `/api/v1/agents/{agent_id}/runs/{run_id}` | Get a specific agent run (status, output, trace) |
| `POST` | `/api/v1/agents/{agent_id}/runs/{run_id}/cancel` | Cancel a running agent invocation |
| `GET` | `/api/v1/agents/{agent_id}/config` | Get agent configuration |
| `PUT` | `/api/v1/agents/{agent_id}/config` | Update agent configuration |
| `GET` | `/api/v1/agents/marketplace` | List agents in the marketplace |
| `POST` | `/api/v1/agents/custom` | Register a custom agent |

**Example — Invoke AI Agent**:
```bash
curl -X POST https://api.rayolly.com/api/v1/agents/rca-agent/invoke \
  -H "Authorization: Bearer $RAYOLLY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "task": "Investigate the root cause of increased latency on order-service",
    "context": {
      "service": "order-service",
      "time_range": {
        "from": "2026-03-19T10:00:00Z",
        "to": "2026-03-19T12:00:00Z"
      },
      "symptoms": ["p99 latency > 2s", "error rate spike to 8%"]
    },
    "params": {
      "depth": "deep",
      "include_recommendations": true,
      "max_duration_seconds": 120
    }
  }'
```

Response:
```json
{
  "data": {
    "run_id": "run_01HV4A2B3C4D5E6F7G8H",
    "agent_id": "rca-agent",
    "status": "running",
    "started_at": "2026-03-19T12:01:00Z",
    "estimated_completion": "2026-03-19T12:03:00Z",
    "stream_url": "wss://api.rayolly.com/ws/agents/runs/run_01HV4A2B3C4D5E6F7G8H"
  }
}
```

#### 3.6.8 Admin API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/admin/org` | Get organization settings |
| `PUT` | `/api/v1/admin/org` | Update organization settings |
| `GET` | `/api/v1/admin/quotas` | Get current usage and quotas |
| `PUT` | `/api/v1/admin/quotas` | Update quota configuration |
| `GET` | `/api/v1/admin/audit-log` | Query the audit log |
| `GET` | `/api/v1/admin/api-keys` | List all API keys in the org |
| `POST` | `/api/v1/admin/api-keys/{key_id}/revoke` | Revoke any API key |
| `GET` | `/api/v1/admin/usage` | Get usage statistics (ingestion, queries, storage) |
| `GET` | `/api/v1/admin/data-retention` | Get retention policies |
| `PUT` | `/api/v1/admin/data-retention` | Update retention policies |
| `POST` | `/api/v1/admin/sso` | Configure SSO (SAML/OIDC) |
| `GET` | `/api/v1/admin/integrations` | List configured integrations |

### 3.7 OpenAPI 3.1 Spec Approach

- OpenAPI 3.1 spec is the single source of truth for the REST API
- Generated from code annotations using `fastapi` (Python) or `openapi-generator` tooling
- Published at `https://api.rayolly.com/openapi.json` and `https://api.rayolly.com/openapi.yaml`
- CI pipeline validates that every deployed endpoint is documented in the spec
- Breaking change detection runs on every PR via `openapi-diff`
- Spec includes `x-codegen` extensions for SDK generation
- Webhook event schemas are included in the spec under the `webhooks` section

---

## 4. GraphQL API

### 4.1 Use Cases

- **Flexible frontend queries**: Fetch exactly the fields needed for each UI view, reducing over-fetching
- **Cross-domain joins**: Single query that fetches logs, related traces, and associated metrics
- **Custom integrations**: Third-party tools that need tailored data shapes
- **Mobile/bandwidth-sensitive clients**: Minimize payload size

### 4.2 Schema Design Approach

- Schema follows a domain-driven design matching the REST resource model
- Relay-style pagination with `Connection`, `Edge`, and `PageInfo` types
- Interface types for common patterns (`Timestamped`, `Ownable`, `Searchable`)
- Input types for mutations mirror REST request bodies
- Custom scalars: `DateTime`, `Duration`, `JSON`, `Cursor`
- Schema stitching to compose domain subgraphs (logs, metrics, traces, agents)

### 4.3 Example Queries

**Cross-domain query — Logs with correlated traces and metrics**:
```graphql
query InvestigateService($service: String!, $timeRange: TimeRangeInput!) {
  logs(
    filter: { service: $service, severity: [ERROR, CRITICAL] }
    timeRange: $timeRange
    first: 20
  ) {
    edges {
      node {
        id
        timestamp
        severity
        message
        traceId
        trace {
          duration_ms
          error
          rootService
          spans(first: 5) {
            edges {
              node {
                service
                operation
                duration_ms
                status
              }
            }
          }
        }
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
    totalCount
  }

  metrics(
    query: "rate(http_requests_total{service=$service}[5m])"
    timeRange: $timeRange
    step: "60s"
  ) {
    series {
      labels
      datapoints {
        timestamp
        value
      }
    }
  }
}
```

**Mutation — Create alert rule**:
```graphql
mutation CreateAlertRule($input: CreateAlertRuleInput!) {
  createAlertRule(input: $input) {
    rule {
      id
      name
      severity
      condition {
        query
        operator
        threshold
      }
      notificationChannels {
        id
        type
        name
      }
    }
  }
}
```

### 4.4 Subscriptions for Real-Time Data

```graphql
subscription LiveLogTail($filter: LogFilterInput!) {
  logStream(filter: $filter) {
    id
    timestamp
    severity
    service
    message
    attributes
  }
}

subscription AlertFeed($severity: [AlertSeverity!]) {
  alertFired(severity: $severity) {
    id
    ruleName
    severity
    firedAt
    service
    message
  }
}

subscription AgentRunProgress($runId: ID!) {
  agentRunUpdates(runId: $runId) {
    status
    progress
    currentStep
    intermediateFindings {
      type
      summary
    }
  }
}
```

### 4.5 GraphQL Endpoint

- Single endpoint: `POST /api/v1/graphql`
- Introspection enabled in development; disabled in production (accessible via docs)
- Query complexity analysis with a max cost of 1000 per query
- Depth limiting: max query depth of 10
- Persisted queries supported for production performance

---

## 5. gRPC API

### 5.1 Use Cases

- **High-throughput ingestion**: Log, metric, and trace ingestion at 1M+ events/sec
- **Service-to-service**: Internal RayOlly microservice communication
- **OTEL Collector export**: Native OTLP/gRPC support
- **Low-latency queries**: Binary protocol reduces serialization overhead
- **Bi-directional streaming**: Live tail, agent interaction

### 5.2 Proto Definitions

```protobuf
syntax = "proto3";

package rayolly.ingest.v1;

import "google/protobuf/timestamp.proto";

service IngestService {
  // Unary - single batch ingest
  rpc IngestLogs(IngestLogsRequest) returns (IngestLogsResponse);
  rpc IngestMetrics(IngestMetricsRequest) returns (IngestMetricsResponse);
  rpc IngestTraces(IngestTracesRequest) returns (IngestTracesResponse);

  // Client streaming - continuous ingestion
  rpc StreamLogs(stream LogEvent) returns (IngestLogsResponse);
  rpc StreamMetrics(stream MetricDatapoint) returns (IngestMetricsResponse);
  rpc StreamTraces(stream TraceSpan) returns (IngestTracesResponse);
}

message LogEvent {
  google.protobuf.Timestamp timestamp = 1;
  string severity = 2;
  string service = 3;
  string message = 4;
  map<string, string> attributes = 5;
  string trace_id = 6;
  string span_id = 7;
}

message IngestLogsRequest {
  repeated LogEvent logs = 1;
  string idempotency_key = 2;
}

message IngestLogsResponse {
  int64 accepted = 1;
  int64 rejected = 2;
  repeated IngestError errors = 3;
}

message IngestError {
  int32 index = 1;
  string code = 2;
  string message = 3;
}
```

```protobuf
syntax = "proto3";

package rayolly.query.v1;

service QueryService {
  // Unary query
  rpc SearchLogs(SearchLogsRequest) returns (SearchLogsResponse);
  rpc QueryMetrics(QueryMetricsRequest) returns (QueryMetricsResponse);
  rpc SearchTraces(SearchTracesRequest) returns (SearchTracesResponse);

  // Server streaming - live tail
  rpc TailLogs(TailLogsRequest) returns (stream LogEvent);
  rpc TailMetrics(TailMetricsRequest) returns (stream MetricDatapoint);
}

service AgentService {
  // Invoke agent with bidirectional streaming for interactive sessions
  rpc InvokeAgent(stream AgentMessage) returns (stream AgentMessage);
  rpc GetAgentRun(GetAgentRunRequest) returns (AgentRunResponse);
}
```

### 5.3 Streaming RPCs

- **Client streaming** for ingestion: clients send a continuous stream of events; server responds with an acknowledgment summary when the stream closes or at periodic intervals
- **Server streaming** for live tail: client sends a filter; server pushes matching events in real time
- **Bidirectional streaming** for agent interaction: client sends prompts/context; agent streams back findings, questions, and results

gRPC endpoint: `grpc://ingest.rayolly.com:443` (with TLS)

---

## 6. WebSocket API

### 6.1 Connection Management

- Endpoint: `wss://api.rayolly.com/ws`
- Authentication via `?token=` query parameter or first message
- Heartbeat: server sends `ping` every 30s; client must respond with `pong` within 10s
- Auto-reconnect with exponential backoff (client SDKs handle this)
- Maximum connection duration: 24 hours (reconnect required)
- Per-connection message rate limit: 100 messages/sec inbound

### 6.2 Live Tail Streaming

```json
// Subscribe to live log tail
{
  "type": "subscribe",
  "channel": "logs.tail",
  "params": {
    "filter": {
      "service": "payment-api",
      "severity": ["error", "warn"]
    }
  },
  "id": "sub_001"
}

// Server sends matching logs
{
  "type": "event",
  "channel": "logs.tail",
  "id": "sub_001",
  "data": {
    "id": "log_01HV3X9K2M4N5P6Q7R8S9T0U",
    "timestamp": "2026-03-19T11:45:23.456Z",
    "severity": "error",
    "service": "payment-api",
    "message": "Payment processing timeout"
  }
}
```

### 6.3 Dashboard Real-Time Updates

```json
// Subscribe to dashboard widget updates
{
  "type": "subscribe",
  "channel": "dashboard.widgets",
  "params": {
    "dashboard_id": "dash_abc123",
    "widget_ids": ["widget_1", "widget_2"],
    "refresh_interval_ms": 5000
  },
  "id": "sub_002"
}
```

### 6.4 Agent Interaction Streaming

```json
// Subscribe to agent run progress
{
  "type": "subscribe",
  "channel": "agent.run",
  "params": {
    "run_id": "run_01HV4A2B3C4D5E6F7G8H"
  },
  "id": "sub_003"
}

// Agent streams back progress
{
  "type": "event",
  "channel": "agent.run",
  "id": "sub_003",
  "data": {
    "status": "investigating",
    "step": 3,
    "total_steps": 7,
    "current_action": "Analyzing correlated traces for order-service",
    "findings": [
      {
        "type": "anomaly",
        "summary": "Database connection pool exhaustion detected at 10:42 UTC"
      }
    ]
  }
}
```

---

## 7. SDK Libraries

### 7.1 SDK Design Principles

| Principle | Detail |
|-----------|--------|
| **Idiomatic** | Each SDK follows the conventions and patterns of its language ecosystem |
| **Async-first** | All SDKs support async operations; sync wrappers provided for convenience |
| **Type-safe** | Full type annotations/generics in all languages |
| **Auto-retry** | Automatic retry with exponential backoff for transient failures (429, 503) |
| **Configurable** | Timeouts, retry policies, base URL, custom HTTP clients all configurable |
| **Observable** | SDKs emit their own metrics and traces for debugging |
| **Paginated** | Auto-paginating iterators for list endpoints |
| **Streaming** | Native support for WebSocket and gRPC streaming |

### 7.2 Python SDK

```bash
pip install rayolly
```

```python
import asyncio
from rayolly import RayOllyClient
from rayolly.models import LogSearchRequest, TimeRange, AlertRule

# Initialize client
client = RayOllyClient(
    api_key="ro_live_k1_a3b8f9c2d1e4f5a6b7c8d9e0f1a2b3c4",
    base_url="https://api.rayolly.com",  # optional, defaults to cloud
)

# Search logs
async def search_errors():
    results = await client.logs.search(
        query="level:error AND service:payment-api",
        time_range=TimeRange(from_="2026-03-19T00:00:00Z", to="2026-03-19T12:00:00Z"),
        severity=["error", "critical"],
        limit=50,
    )
    for log in results.logs:
        print(f"[{log.timestamp}] {log.severity}: {log.message}")

    # Auto-paginate through all results
    async for log in client.logs.search_iter(query="level:error", limit=1000):
        process(log)

# Ingest logs
async def ingest_example():
    response = await client.logs.ingest([
        {"severity": "info", "service": "my-app", "message": "Request processed"},
        {"severity": "error", "service": "my-app", "message": "Database timeout"},
    ])
    print(f"Accepted: {response.accepted}, Rejected: {response.rejected}")

# Invoke AI agent
async def investigate():
    run = await client.agents.invoke(
        agent_id="rca-agent",
        task="Why is order-service slow?",
        context={"service": "order-service"},
    )

    # Stream agent progress
    async for update in client.agents.stream(run.run_id):
        print(f"[{update.status}] {update.current_action}")
        if update.status == "completed":
            print(f"Root cause: {update.result.root_cause}")

# Live tail
async def tail_logs():
    async for log in client.logs.tail(service="payment-api", severity=["error"]):
        print(f"{log.timestamp} | {log.message}")

asyncio.run(search_errors())
```

### 7.3 JavaScript/TypeScript SDK

```bash
npm install @rayolly/sdk
```

```typescript
import { RayOllyClient } from "@rayolly/sdk";

const client = new RayOllyClient({
  apiKey: process.env.RAYOLLY_API_KEY!,
});

// Search logs
const results = await client.logs.search({
  query: 'level:error AND service:payment-api',
  timeRange: { from: '2026-03-19T00:00:00Z', to: '2026-03-19T12:00:00Z' },
  severity: ['error', 'critical'],
  limit: 50,
});

for (const log of results.logs) {
  console.log(`[${log.timestamp}] ${log.severity}: ${log.message}`);
}

// Auto-paginating async iterator
for await (const log of client.logs.searchIter({ query: 'level:error' })) {
  console.log(log.message);
}

// Create alert rule
const rule = await client.alerts.rules.create({
  name: 'High Error Rate',
  type: 'metric',
  condition: {
    query: 'rate(http_errors_total{service="api"}[5m])',
    operator: 'greater_than',
    threshold: 5,
    forDuration: '5m',
  },
  severity: 'critical',
  notificationChannels: ['channel_slack_oncall'],
});

// Live tail with WebSocket
const stream = client.logs.tail({ service: 'payment-api' });
stream.on('log', (log) => console.log(log.message));
stream.on('error', (err) => console.error(err));
```

### 7.4 Go SDK

```bash
go get github.com/rayolly/rayolly-go
```

```go
package main

import (
    "context"
    "fmt"
    "log"
    "time"

    "github.com/rayolly/rayolly-go"
    "github.com/rayolly/rayolly-go/types"
)

func main() {
    client, err := rayolly.NewClient(
        rayolly.WithAPIKey("ro_live_k1_a3b8f9c2d1e4f5a6b7c8d9e0f1a2b3c4"),
    )
    if err != nil {
        log.Fatal(err)
    }

    ctx := context.Background()

    // Search logs
    results, err := client.Logs.Search(ctx, &types.LogSearchRequest{
        Query: "level:error AND service:payment-api",
        TimeRange: types.TimeRange{
            From: time.Now().Add(-12 * time.Hour),
            To:   time.Now(),
        },
        Limit: 50,
    })
    if err != nil {
        log.Fatal(err)
    }

    for _, entry := range results.Logs {
        fmt.Printf("[%s] %s: %s\n", entry.Timestamp, entry.Severity, entry.Message)
    }

    // Ingest metrics via gRPC (high throughput)
    stream, err := client.Metrics.IngestStream(ctx)
    if err != nil {
        log.Fatal(err)
    }
    for i := 0; i < 10000; i++ {
        stream.Send(&types.MetricDatapoint{
            Name:      "custom_requests_total",
            Value:     float64(i),
            Timestamp: time.Now(),
            Labels:    map[string]string{"service": "my-app"},
        })
    }
    resp, err := stream.CloseAndRecv()
    fmt.Printf("Ingested: %d accepted, %d rejected\n", resp.Accepted, resp.Rejected)
}
```

### 7.5 Java SDK

```xml
<dependency>
    <groupId>com.rayolly</groupId>
    <artifactId>rayolly-sdk</artifactId>
    <version>1.0.0</version>
</dependency>
```

```java
import com.rayolly.RayOllyClient;
import com.rayolly.models.*;
import java.time.Instant;
import java.util.List;
import java.util.concurrent.CompletableFuture;

public class Example {
    public static void main(String[] args) {
        RayOllyClient client = RayOllyClient.builder()
            .apiKey("ro_live_k1_a3b8f9c2d1e4f5a6b7c8d9e0f1a2b3c4")
            .build();

        // Async search
        CompletableFuture<LogSearchResponse> future = client.logs().searchAsync(
            LogSearchRequest.builder()
                .query("level:error AND service:payment-api")
                .timeRange(TimeRange.of(
                    Instant.now().minusSeconds(43200),
                    Instant.now()
                ))
                .severity(List.of("error", "critical"))
                .limit(50)
                .build()
        );

        future.thenAccept(results -> {
            results.getLogs().forEach(log ->
                System.out.printf("[%s] %s: %s%n",
                    log.getTimestamp(), log.getSeverity(), log.getMessage())
            );
        }).join();

        // Sync convenience
        LogSearchResponse results = client.logs().search(
            LogSearchRequest.builder()
                .query("level:error")
                .limit(10)
                .build()
        );
    }
}
```

---

## 8. CLI Tool (rayolly-cli)

### 8.1 Installation

```bash
# macOS
brew install rayolly/tap/rayolly-cli

# Linux
curl -sSL https://get.rayolly.com/cli | bash

# Windows
winget install RayOlly.CLI

# Docker
docker run --rm -it rayolly/cli:latest

# Go install
go install github.com/rayolly/cli/cmd/rayolly@latest
```

### 8.2 Authentication

```bash
# Interactive login (opens browser for OAuth flow)
rayolly auth login

# API key authentication
rayolly auth login --api-key ro_live_k1_a3b8f9c2d1e4f5a6b7c8d9e0f1a2b3c4

# Set default organization and environment
rayolly config set org my-company
rayolly config set environment production

# Check authentication status
rayolly auth status
```

### 8.3 Key Commands

```bash
# --- Logs ---
# Search logs
rayolly logs search "level:error AND service:payment-api" --from 1h --limit 50

# Live tail
rayolly logs tail --service payment-api --severity error,warn

# Aggregate
rayolly logs aggregate "count() by service, severity" --from 24h

# --- Metrics ---
# Query metrics
rayolly metrics query 'rate(http_requests_total{service="api"}[5m])' --from 6h --step 1m

# List metrics
rayolly metrics list --filter "http_*"

# --- Traces ---
# Search traces
rayolly traces search --service order-service --min-duration 1s --from 1h

# Get trace detail
rayolly traces get abc123def456

# Service map
rayolly traces service-map --format dot | dot -Tpng -o service-map.png

# --- Alerts ---
# List firing alerts
rayolly alerts list --status firing

# Create alert from YAML
rayolly alerts create -f alert-rule.yaml

# Silence an alert
rayolly alerts silence "service=payment-api" --duration 2h --reason "deploying fix"

# --- Dashboards ---
# List dashboards
rayolly dashboards list

# Export dashboard as JSON
rayolly dashboards export dash_abc123 -o dashboard.json

# Import dashboard
rayolly dashboards import -f dashboard.json

# --- AI Agents ---
# List agents
rayolly agents list

# Invoke agent interactively
rayolly agents invoke rca-agent --task "Why is order-service slow?" --interactive

# View agent run
rayolly agents runs get run_01HV4A2B3C4D5E6F7G8H

# --- Admin ---
# View usage
rayolly admin usage --from 30d

# Audit log
rayolly admin audit-log --actor user@company.com --from 7d
```

### 8.4 Shell Completion

```bash
# Bash
rayolly completion bash > /etc/bash_completion.d/rayolly

# Zsh
rayolly completion zsh > "${fpath[1]}/_rayolly"

# Fish
rayolly completion fish > ~/.config/fish/completions/rayolly.fish

# PowerShell
rayolly completion powershell > rayolly.ps1
```

### 8.5 Output Formats

```bash
# Table (default, human-readable)
rayolly logs search "level:error" --format table

# JSON (for piping to jq)
rayolly logs search "level:error" --format json | jq '.data.logs[].message'

# YAML
rayolly alerts rules list --format yaml

# CSV
rayolly metrics query 'http_requests_total' --format csv > metrics.csv

# Compact (one line per result, for grep/awk)
rayolly logs tail --format compact
```

---

## 9. Terraform Provider

### 9.1 Provider Configuration

```hcl
terraform {
  required_providers {
    rayolly = {
      source  = "rayolly/rayolly"
      version = "~> 1.0"
    }
  }
}

provider "rayolly" {
  api_key     = var.rayolly_api_key  # or RAYOLLY_API_KEY env var
  base_url    = "https://api.rayolly.com"
  environment = "production"
}
```

### 9.2 Resources

#### Dashboards
```hcl
resource "rayolly_dashboard" "service_overview" {
  name        = "Payment Service Overview"
  description = "Key metrics and logs for the payment service"
  team_id     = rayolly_team.payments.id

  tags = ["payment", "production", "critical"]

  variable {
    name          = "environment"
    type          = "custom"
    default_value = "production"
    options       = ["production", "staging", "development"]
  }

  widget {
    title    = "Error Rate"
    type     = "timeseries"
    position = { x = 0, y = 0, w = 6, h = 4 }

    query {
      type       = "metric"
      expression = "rate(http_requests_total{service=\"payment-api\", status=~\"5..\"}[5m])"
    }
  }

  widget {
    title    = "Recent Errors"
    type     = "log_table"
    position = { x = 6, y = 0, w = 6, h = 4 }

    query {
      type       = "log"
      expression = "service:payment-api AND level:error"
    }
  }
}
```

#### Alert Rules
```hcl
resource "rayolly_alert_rule" "payment_errors" {
  name        = "Payment API High Error Rate"
  description = "Fires when payment-api 5xx rate exceeds 5% for 5 minutes"
  severity    = "critical"
  team_id     = rayolly_team.payments.id

  condition {
    type         = "metric"
    query        = "rate(http_requests_total{service=\"payment-api\", status=~\"5..\"}[5m]) / rate(http_requests_total{service=\"payment-api\"}[5m]) * 100"
    operator     = "greater_than"
    threshold    = 5
    for_duration = "5m"
  }

  labels = {
    team        = "payments"
    environment = "production"
  }

  notification_channel_ids = [
    rayolly_notification_channel.slack_payments.id,
    rayolly_notification_channel.pagerduty_p1.id,
  ]

  runbook_url = "https://wiki.internal/runbooks/payment-high-error-rate"
}
```

#### Teams and Notification Channels
```hcl
resource "rayolly_team" "payments" {
  name        = "Payments Team"
  description = "Owns all payment-related services"

  member {
    user_id = "user_alice"
    role    = "admin"
  }

  member {
    user_id = "user_bob"
    role    = "member"
  }

  service_ownership = ["payment-api", "payment-worker", "payment-gateway"]
}

resource "rayolly_notification_channel" "slack_payments" {
  name = "Slack - Payments Alerts"
  type = "slack"

  config = {
    webhook_url = var.slack_webhook_url
    channel     = "#payments-alerts"
    mention     = "@payments-oncall"
  }
}

resource "rayolly_notification_channel" "pagerduty_p1" {
  name = "PagerDuty - P1 Escalation"
  type = "pagerduty"

  config = {
    integration_key = var.pagerduty_integration_key
    severity        = "critical"
  }
}
```

#### SLOs
```hcl
resource "rayolly_slo" "payment_availability" {
  name        = "Payment API Availability"
  description = "99.95% availability target for payment processing"
  team_id     = rayolly_team.payments.id

  sli {
    type         = "availability"
    good_query   = "sum(rate(http_requests_total{service=\"payment-api\", status!~\"5..\"}[5m]))"
    total_query  = "sum(rate(http_requests_total{service=\"payment-api\"}[5m]))"
  }

  target          = 99.95
  window          = "30d"
  burn_rate_alerts = true
}
```

#### Agent Configuration
```hcl
resource "rayolly_agent_config" "rca_agent" {
  agent_id = "rca-agent"

  config = {
    max_investigation_depth = "deep"
    auto_invoke_on_p1       = true
    allowed_services        = ["payment-api", "order-service", "inventory-service"]
    max_duration_seconds    = 300
    notify_channel          = rayolly_notification_channel.slack_payments.id
  }
}
```

### 9.3 Data Sources

```hcl
data "rayolly_services" "all" {
  environment = "production"
}

data "rayolly_metric_metadata" "http_requests" {
  metric_name = "http_requests_total"
}

output "discovered_services" {
  value = data.rayolly_services.all.services[*].name
}
```

### 9.4 State Management

- Terraform state tracks all RayOlly resource IDs and configurations
- Import existing resources: `terraform import rayolly_dashboard.existing dash_abc123`
- Drift detection: `terraform plan` shows any manual changes made outside Terraform
- Resource dependencies are automatically resolved (e.g., team must exist before dashboard referencing it)

---

## 10. Webhooks

### 10.1 Outgoing Webhooks

Outgoing webhooks deliver platform events to external HTTP endpoints.

**Supported Events**:

| Event Type | Trigger |
|-----------|---------|
| `alert.fired` | Alert rule condition met |
| `alert.resolved` | Alert condition cleared |
| `alert.acknowledged` | Alert acknowledged by user |
| `incident.created` | Incident opened (manually or by alert) |
| `incident.updated` | Incident status or severity changed |
| `incident.resolved` | Incident resolved |
| `agent.run.started` | AI agent invocation started |
| `agent.run.completed` | AI agent run completed with findings |
| `agent.run.failed` | AI agent run failed |
| `slo.budget.warning` | SLO error budget below 20% |
| `slo.budget.exhausted` | SLO error budget exhausted |
| `export.completed` | Data export job finished |
| `user.login` | User login event (audit) |

**Payload Example — `alert.fired`**:
```json
{
  "id": "evt_01HV5X9K2M4N5P6Q",
  "type": "alert.fired",
  "timestamp": "2026-03-19T11:45:23Z",
  "data": {
    "alert_id": "alert_abc123",
    "rule_id": "rule_def456",
    "rule_name": "Payment API High Error Rate",
    "severity": "critical",
    "condition": {
      "query": "rate(http_errors[5m]) > 5%",
      "current_value": 8.3,
      "threshold": 5
    },
    "labels": {
      "service": "payment-api",
      "environment": "production",
      "team": "payments"
    },
    "fired_at": "2026-03-19T11:45:00Z",
    "dashboard_url": "https://app.rayolly.com/alerts/alert_abc123",
    "runbook_url": "https://wiki.internal/runbooks/payment-high-error-rate"
  },
  "org_id": "org_123",
  "webhook_id": "wh_789"
}
```

### 10.2 Incoming Webhooks

Incoming webhooks allow external systems to push events into RayOlly.

```bash
# Each incoming webhook gets a unique URL
POST https://ingest.rayolly.com/webhooks/in/whi_a1b2c3d4e5f6

# Generic event ingestion
curl -X POST https://ingest.rayolly.com/webhooks/in/whi_a1b2c3d4e5f6 \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "deployment",
    "service": "payment-api",
    "version": "2.3.1",
    "environment": "production",
    "deployed_by": "github-actions",
    "commit_sha": "abc123"
  }'
```

Incoming webhooks support configurable field mapping and transformation rules to normalize events from different sources.

### 10.3 Webhook Security

| Mechanism | Details |
|-----------|---------|
| **HMAC signing** | Every outgoing webhook includes `X-RayOlly-Signature-256` header with HMAC-SHA256 of the payload using a shared secret |
| **Timestamp validation** | `X-RayOlly-Timestamp` header; reject if older than 5 minutes to prevent replay attacks |
| **IP allowlisting** | Published list of egress IPs; customers can restrict inbound to these IPs |
| **mTLS** | Optional mutual TLS for enterprise customers |
| **Secret rotation** | Rotate webhook signing secrets without downtime (two active secrets during rotation window) |

**Signature Verification (Python)**:
```python
import hmac
import hashlib

def verify_webhook(payload: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)
```

### 10.4 Retry Logic and Delivery Guarantees

- **At-least-once delivery**: webhooks may be delivered more than once; consumers must be idempotent
- **Retry schedule**: 1s, 10s, 1m, 5m, 30m, 1h, 6h (7 retries over ~7.5 hours)
- **Success criteria**: HTTP 2xx response within 30 seconds
- **Dead letter queue**: after all retries exhausted, event goes to DLQ; visible in admin UI
- **Manual retry**: replay individual events or entire time ranges from the admin UI
- **Webhook logs**: full request/response logs retained for 30 days

---

## 11. Integration Ecosystem

### 11.1 Native Integrations

#### Incident Management

| Integration | Capabilities |
|-------------|-------------|
| **Slack** | Alert notifications, interactive incident management, slash commands (`/rayolly query ...`), log/trace sharing, AI agent chat interface |
| **PagerDuty** | Alert → incident creation, severity mapping, auto-resolve, on-call lookup |
| **OpsGenie** | Alert routing, team escalation, bidirectional sync |
| **Microsoft Teams** | Alert cards, adaptive cards for incidents, bot for queries |
| **Jira** | Create tickets from alerts/incidents, bidirectional status sync, link traces to tickets |
| **ServiceNow** | Incident creation, CMDB enrichment, change correlation |

#### Source Control & CI/CD

| Integration | Capabilities |
|-------------|-------------|
| **GitHub** | Deploy event tracking, commit annotation, PR checks (SLO budget), Actions integration |
| **GitLab** | Deploy tracking, MR annotations, CI/CD pipeline integration |
| **GitHub Actions** | Reusable action for deploy markers, SLO gates, log assertions in CI |
| **GitLab CI** | Pipeline component for deploy markers and quality gates |
| **Jenkins** | Plugin for deploy events and build log forwarding |
| **ArgoCD** | Sync event tracking, rollback correlation, deployment annotations |

#### Monitoring & Observability

| Integration | Capabilities |
|-------------|-------------|
| **Prometheus** | Remote write receiver, PromQL compatibility, AlertManager bridge |
| **Grafana** | Data source plugin, dashboard import, annotation bridge |
| **CloudWatch** | Metric and log import, cross-account support |
| **Azure Monitor** | Metric and log import, diagnostic settings integration |
| **Datadog** | Migration tools, dual-write during transition |

#### Logging & Data

| Integration | Capabilities |
|-------------|-------------|
| **Fluentd** | Output plugin for RayOlly ingestion |
| **Fluent Bit** | Native output plugin (high performance, low memory) |
| **Logstash** | Output plugin for log forwarding |
| **Vector** | Sink for logs, metrics, and traces |
| **Kafka** | Consumer for ingestion, producer for export |

#### Cloud Platforms

| Integration | Capabilities |
|-------------|-------------|
| **AWS** | CloudWatch, CloudTrail, S3, Lambda, ECS/EKS, RDS, ALB/NLB logs |
| **GCP** | Cloud Logging, Cloud Monitoring, GKE, Cloud Run, Cloud SQL |
| **Azure** | Monitor, Log Analytics, AKS, App Service, SQL Database |

#### Infrastructure

| Integration | Capabilities |
|-------------|-------------|
| **Kubernetes** | Pod logs, cluster metrics, events, HPA correlation, admission webhooks |
| **Docker** | Container log driver, Docker Compose service discovery |
| **Terraform** | Provider (see Section 9), state drift detection |
| **Ansible** | Callback plugin for playbook execution events |

#### Databases

| Integration | Capabilities |
|-------------|-------------|
| **PostgreSQL** | Slow query logs, connection metrics, replication lag, pg_stat_statements |
| **MySQL** | Slow query log, performance schema metrics, replication monitoring |
| **MongoDB** | Profiler logs, operation metrics, replica set monitoring |
| **Redis** | Slowlog, memory metrics, keyspace notifications |
| **Elasticsearch** | Cluster health, index metrics, slow log forwarding |

### 11.2 Integration Marketplace Architecture

- Community and partner integrations published as versioned packages
- Each integration includes: connector code, default dashboards, alert templates, documentation
- Review process: automated security scan, manual review for certified integrations
- Versioning: semver, with automatic minor version updates (user opt-in for major)
- Installation via UI, CLI (`rayolly integrations install aws`), or Terraform

---

## 12. Data Export

### 12.1 Scheduled Exports

```bash
# Create a scheduled export via CLI
rayolly exports create \
  --name "daily-compliance-logs" \
  --query "source:audit-log" \
  --schedule "0 2 * * *" \
  --destination s3://my-bucket/rayolly-exports/ \
  --format parquet \
  --retention 365d
```

| Destination | Auth Method | Formats |
|-------------|-------------|---------|
| **Amazon S3** | IAM role (cross-account) or access key | JSON, CSV, Parquet, OTLP |
| **Google Cloud Storage** | Service account key or Workload Identity | JSON, CSV, Parquet, OTLP |
| **Azure Blob Storage** | Managed Identity or SAS token | JSON, CSV, Parquet, OTLP |
| **SFTP** | SSH key or password | JSON, CSV |

### 12.2 Streaming Export

| Destination | Protocol | Use Case |
|-------------|----------|----------|
| **Kafka** | Kafka producer | Real-time data lake ingestion |
| **Webhook** | HTTP POST | Custom processing pipelines |
| **Amazon Kinesis** | Kinesis producer | AWS data pipeline integration |
| **Google Pub/Sub** | gRPC publisher | GCP data pipeline integration |

### 12.3 Export Formats

| Format | Best For | Compression |
|--------|----------|-------------|
| **JSON** | General purpose, human readable | gzip, zstd |
| **CSV** | Spreadsheet import, simple analysis | gzip |
| **Parquet** | Analytics, data lake, cost-efficient storage | snappy, zstd |
| **OTLP** | OpenTelemetry-compatible systems | protobuf (native) |

### 12.4 Compliance Exports

- Preconfigured export templates for SOC 2, HIPAA, PCI-DSS, GDPR
- Immutable exports with SHA-256 checksums and chain-of-custody metadata
- Configurable PII redaction before export
- Legal hold: prevent deletion of data under legal hold even if retention policy expires
- Export audit trail: every export operation is logged in the audit log

---

## 13. Backward Compatibility

### 13.1 API Deprecation Policy

| Phase | Duration | Actions |
|-------|----------|---------|
| **Announcement** | Day 0 | Deprecation notice in changelog, API docs, and email to API key owners |
| **Warning** | 0-6 months | `Deprecation: true` and `Sunset` headers on deprecated endpoints; deprecation warnings in SDKs |
| **Migration** | 6-12 months | Migration guide published; both old and new endpoints active; usage dashboard shows deprecated endpoint calls |
| **Sunset** | 12+ months | Deprecated endpoints return `410 Gone` with migration link |

### 13.2 Version Sunset Schedule

| Version | Release | Deprecation | Sunset |
|---------|---------|-------------|--------|
| v1 | 2026-Q2 | TBD (minimum v3 release) | Minimum 12 months after deprecation |
| v2 | 2027 (planned) | TBD | TBD |

### 13.3 Migration Guides

- Per-version migration guide published at `https://docs.rayolly.com/api/migration/v1-to-v2`
- SDK auto-migration: SDKs log warnings for deprecated method calls with suggested replacements
- Automated migration tool: `rayolly-cli api migrate --from v1 --to v2 --dry-run` analyzes API key usage and generates a migration plan
- Compatibility shim: optional middleware that translates v1 requests to v2 (for customers needing extra migration time)

---

## 14. API Documentation

### 14.1 Interactive API Docs

- **Swagger UI** available at `https://api.rayolly.com/docs`
- **Redoc** available at `https://api.rayolly.com/redoc` (optimized for reading)
- Try-it-out functionality with authenticated requests (after login)
- Request/response examples for every endpoint
- Syntax-highlighted code samples in curl, Python, JS, Go, and Java

### 14.2 SDK Documentation

- Auto-generated from SDK source code docstrings
- Python: hosted on ReadTheDocs with Sphinx
- TypeScript: TypeDoc-generated, hosted on docs site
- Go: pkg.go.dev with complete examples
- Java: Javadoc with Maven Central integration

### 14.3 Code Examples & Tutorials

- Quick start guides per language (< 5 minutes to first API call)
- Use-case tutorials: "Set up alerting for a microservice", "Build a custom dashboard", "Automate incident response with AI agents"
- Runnable example repository: `github.com/rayolly/examples`
- Jupyter notebooks for data analysis workflows

### 14.4 Postman / Insomnia Collections

```bash
# Import Postman collection
curl -o rayolly-postman.json https://api.rayolly.com/postman-collection.json

# Import Insomnia collection
curl -o rayolly-insomnia.yaml https://api.rayolly.com/insomnia-collection.yaml
```

- Pre-configured environment variables for API key and base URL
- Request examples for every endpoint
- Pre-request scripts for authentication token refresh
- Test assertions for response validation
- Collection auto-generated from OpenAPI spec on every release

---

## 15. Performance Requirements

### 15.1 API Latency Targets

| Endpoint Category | p50 | p95 | p99 | Notes |
|------------------|-----|-----|-----|-------|
| **Log search** | 50ms | 150ms | 500ms | For queries scanning < 10GB |
| **Log ingest** | 5ms | 15ms | 50ms | Acknowledgment latency (async processing) |
| **Metric query** | 30ms | 100ms | 300ms | For queries with < 1M datapoints |
| **Metric ingest** | 3ms | 10ms | 30ms | Acknowledgment latency |
| **Trace lookup (by ID)** | 20ms | 50ms | 100ms | Single trace retrieval |
| **Trace search** | 100ms | 300ms | 800ms | Complex filter queries |
| **Alert rule CRUD** | 20ms | 50ms | 100ms | |
| **Dashboard CRUD** | 30ms | 80ms | 200ms | |
| **Agent invocation** | 100ms | 200ms | 500ms | Time to start (not complete) |
| **GraphQL query** | 50ms | 200ms | 600ms | Depends on query complexity |
| **Health check** | 2ms | 5ms | 10ms | `/api/v1/health` |

### 15.2 Rate Limits Per Tier

| Tier | API Calls/min | Ingestion Events/sec | Query Concurrency | WebSocket Connections | Export Jobs/day |
|------|--------------|---------------------|-------------------|-----------------------|----------------|
| **Free** | 60 | 1,000 | 2 | 5 | 1 |
| **Pro** | 600 | 50,000 | 10 | 50 | 10 |
| **Enterprise** | 6,000 | 500,000 | 100 | 500 | 100 |
| **Dedicated** | Custom | 5,000,000+ | 1,000+ | 5,000+ | Unlimited |

### 15.3 Concurrent Connection Limits

- REST API: 100 concurrent requests per API key (Pro), 1,000 (Enterprise)
- WebSocket: connection limits per tier (see above)
- gRPC: 50 concurrent streams per connection, 10 connections per client (configurable)
- GraphQL: 20 concurrent queries per connection

---

## 16. Success Metrics

### 16.1 Adoption Metrics

| Metric | Target (6 months) | Target (12 months) |
|--------|-------------------|---------------------|
| Monthly active API keys | 500 | 5,000 |
| SDK downloads (all languages) | 10,000/month | 100,000/month |
| CLI installations | 2,000 | 15,000 |
| Terraform provider downloads | 500 | 5,000 |
| Integration marketplace installs | 1,000 | 10,000 |
| Webhook configurations | 2,000 | 20,000 |

### 16.2 Quality Metrics

| Metric | Target |
|--------|--------|
| API availability | 99.99% |
| p99 latency within targets | 99% of the time |
| SDK bug report resolution | < 48 hours for critical, < 1 week for others |
| API documentation accuracy | 100% endpoints documented, verified by CI |
| Breaking change incidents | 0 (unintentional) |

### 16.3 Developer Experience Metrics

| Metric | Target |
|--------|--------|
| Time to first API call (new user) | < 5 minutes |
| NPS score from API consumers | > 50 |
| Support tickets related to API confusion | < 5% of total tickets |
| SDK code coverage | > 90% |

---

## 17. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **Breaking API changes slip through** | Medium | High | OpenAPI diff in CI, contract tests, canary deployments, mandatory review for API changes |
| **Rate limiting too aggressive for large customers** | Medium | Medium | Configurable limits per API key, burst allowances, dedicated tier with custom limits |
| **GraphQL query complexity abuse** | High | Medium | Query cost analysis, depth limiting, persisted queries for production, rate limiting per complexity unit |
| **WebSocket connection storms** | Medium | High | Connection rate limiting, graceful degradation, per-tenant connection pools, automatic shedding |
| **SDK version fragmentation** | Medium | Low | Automated SDK generation from OpenAPI spec, monthly release cadence, semantic versioning |
| **Webhook delivery failures** | Low | Medium | Retry with exponential backoff, dead letter queue, alerting on delivery failure rates, manual replay |
| **gRPC adoption barrier** | Medium | Low | REST API as primary interface, gRPC for advanced users only, comprehensive docs and examples |
| **Third-party integration breakage** | Medium | Medium | Integration health monitoring, automated testing against partner sandboxes, versioned integration packages |
| **API key leakage** | Medium | Critical | Key rotation without downtime, leaked key detection (GitHub secret scanning partnership), scope-limited keys, audit logging |
| **Multi-tenancy data leakage via API** | Low | Critical | Tenant ID in JWT claims enforced at data layer, automated pen testing, bug bounty program, query injection prevention |
| **Terraform provider state drift** | Medium | Medium | Drift detection in plan, import support for existing resources, state refresh on apply |
| **Documentation staleness** | High | Medium | Auto-generated docs from code, CI validation that every endpoint has docs, quarterly doc review sprints |

---

## Appendix A: API Quick Reference

### Base URLs

| Environment | REST | gRPC | WebSocket | GraphQL |
|-------------|------|------|-----------|---------|
| **Production** | `https://api.rayolly.com` | `grpc://ingest.rayolly.com:443` | `wss://api.rayolly.com/ws` | `https://api.rayolly.com/api/v1/graphql` |
| **EU Region** | `https://api.eu.rayolly.com` | `grpc://ingest.eu.rayolly.com:443` | `wss://api.eu.rayolly.com/ws` | `https://api.eu.rayolly.com/api/v1/graphql` |
| **Staging** | `https://api.staging.rayolly.com` | `grpc://ingest.staging.rayolly.com:443` | `wss://api.staging.rayolly.com/ws` | `https://api.staging.rayolly.com/api/v1/graphql` |
| **Self-hosted** | `https://{your-domain}/api` | `grpc://{your-domain}:9090` | `wss://{your-domain}/ws` | `https://{your-domain}/api/v1/graphql` |

### HTTP Status Code Summary

| Code | Meaning | Retry? |
|------|---------|--------|
| 200 | Success | No |
| 201 | Created | No |
| 202 | Accepted (async) | No |
| 204 | Deleted | No |
| 400 | Bad request | No (fix request) |
| 401 | Unauthorized | No (fix auth) |
| 403 | Forbidden | No (check permissions) |
| 404 | Not found | No |
| 409 | Conflict | Yes (re-fetch and retry) |
| 422 | Validation error | No (fix request) |
| 429 | Rate limited | Yes (after `Retry-After`) |
| 500 | Server error | Yes (with backoff) |
| 503 | Unavailable | Yes (with backoff) |

---

## Appendix B: Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0-draft | 2026-03-19 | Initial PRD |
