# RayOlly — Project Memory

Persistent knowledge base for maintaining context across development sessions.

---

## Product Identity

- **Name**: RayOlly
- **Tagline**: "Every engineer has an AI SRE team that never sleeps"
- **Category**: Enterprise AI-native observability platform
- **Core differentiator**: AI Agents-as-a-Service + Agent Observability (first-of-its-kind)
- **License**: Open core (Apache 2.0 core, commercial enterprise features)
- **Pricing**: Per-node flat rate (avoids Datadog-style bill shock)

## Competitive Positioning

| Competitor | Their Weakness | RayOlly Advantage |
|-----------|---------------|-------------------|
| Datadog | Per-GB pricing, no self-hosted, vendor lock-in | 10x cheaper, self-hosted parity, OTEL-native |
| Splunk | Expensive, two-platform problem | Unified platform, modern AI agents, lower cost |
| Dynatrace | Davis AI is opaque, slow to ship | Transparent AI, custom agents, observable agents |
| New Relic | Less sophisticated AI/ML | Autonomous agents, agent marketplace, better DX |
| OpenObserve | No AI agents, basic anomaly detection | Full AI stack, enterprise integrations, APM |
| **All** | **No agent observability** | **RayOlly monitors its own AI agents — unique** |

## Architecture Decisions

### ADR-001: Python + Rust hot paths
Python 3.12+ with FastAPI for development velocity. Rust via PyO3 for grok parsing and Tantivy search. Trade-off: slower than pure Rust, but faster iteration and richer ML/AI ecosystem.

### ADR-002: ClickHouse + Parquet hybrid storage
ClickHouse for hot/warm (fast queries), Parquet on S3 for cold (cheap archival). OpenObserve uses Parquet-only which is slow for interactive queries.

### ADR-003: NATS JetStream over Kafka
Lighter weight, simpler ops, built-in persistence. Sufficient for our scale targets.

### ADR-004: React/Next.js over Vue
Larger ecosystem, better SSR, more enterprise-grade than OpenObserve's Vue/Quasar.

### ADR-005: Claude API as primary LLM
Best reasoning for complex RCA. Mitigate cost with caching, smart routing (Haiku for simple, Opus for complex), local model fallback.

### ADR-006: Shared tables with tenant_id
Simpler ops and better utilization than per-tenant databases. Row-level security via mandatory tenant_id injection in query engine.

### ADR-007: Agent Observability as core module
Not an afterthought. Dedicated ClickHouse tables, dedicated API, dedicated UI. Track every agent step, tool call, token, cost, and user satisfaction. This is what no competitor has.

## Critical Security Rules

1. **ALL ClickHouse queries** must validate tenant_id format (alphanumeric + hyphens + underscores only)
2. **NO string interpolation** for user-provided values in SQL — use parameterized queries or validate/sanitize
3. **Tenant_id injection** is mandatory in QueryEngine, LogExplorer, and every service that queries ClickHouse
4. **API keys** must be hashed (bcrypt) before storage; never log or return full keys
5. **PII detection** runs on all ingested data by default; opt-out requires explicit tenant config

## Known Technical Debt

### Critical (fix before any feature work)
1. ~~SQL injection in QueryEngine (string interpolation for tenant_id)~~ **FIXED**
2. ~~Makefile references wrong module path~~ **FIXED**
3. Import error in `api/routes/apm.py` — references `rayolly.core.deps` (should be `dependencies`)
4. Import error in `api/routes/agents.py` — `agents.builtin.*` path not on PYTHONPATH
5. API key tenant resolution always returns None (auth bypass)

### High (fix in Sprint 1)
6. Zero test files — need 80% coverage target
7. Alert evaluator can't load rules (no PostgreSQL store)
8. Agent executions stored in-memory dict (lost on restart)
9. All PostgreSQL-backed entities are stubs (alerts, queries, incidents, users)

### Medium (fix in Sprint 2)
10. PromQL parser is regex-based — needs proper AST
11. Email notification is a stub
12. Twilio escalation doesn't validate acknowledgment
13. Frontend uses mock data everywhere
14. No OTLP gRPC server (only HTTP)

## Key Patterns

### Tenant Isolation (MANDATORY)
```python
# Every service method that touches ClickHouse MUST:
# 1. Accept tenant_id parameter
# 2. Include tenant_id in WHERE clause
# 3. Validate tenant_id format before use in SQL

# In QueryEngine:
if not re.match(r'^[a-zA-Z0-9_-]+$', tenant_id):
    raise QueryExecutionError(f"Invalid tenant_id format")
```

### NATS Subject Convention
```
rayolly.ingest.{signal_type}.{tenant_id}    # logs, metrics, traces
rayolly.alerts.events                         # alert state changes
rayolly.agents.events                         # agent execution events
rayolly.dlq.{tenant_id}                      # dead letter queue
```

### ClickHouse Table Design
- Partition: `(tenant_id, toYYYYMMDD(timestamp))` always
- LowCardinality for categorical columns (service, severity, status)
- Codecs: DoubleDelta (timestamps), Gorilla (floats), ZSTD (maps/strings)
- Indexes: bloom_filter on trace_id, tokenbf on body, set on service/severity

### New Service Checklist
When creating a new backend service:
1. Create package under `services/{name}/`
2. Use dataclasses for data models (not Pydantic — that's for API models)
3. Accept `clickhouse_client` via constructor injection
4. Accept `tenant_id` as first parameter of all query methods
5. Use `structlog.get_logger(__name__)` for logging
6. All methods async
7. Add corresponding route file in `api/routes/`
8. Register router in `api/app.py` `create_app()`
9. Write unit tests in `tests/unit/test_{name}.py`

### New Agent Tool Checklist
1. Define class with `name`, `description`, `parameters` (JSON schema)
2. Implement `async execute(self, parameters, context) -> dict`
3. Register in `ToolRegistry` in `services/agents/tools.py`
4. Add to relevant agent definitions' tool lists
5. Add unit test in `tests/unit/test_agent_tools.py`

### New Integration Checklist
1. Extend `BaseIntegration` in `services/integrations/{name}.py`
2. Define `config_schema` (JSON schema for required credentials)
3. Implement `test_connection()`, `execute_action()`
4. Register in `IntegrationRegistry`
5. Add to frontend integrations page mock data
6. Add unit test with mocked HTTP calls

## Environment Variables
All prefixed `RAYOLLY_`. See `backend/.env.example` for complete list.

Key ones:
- `RAYOLLY_AI_ANTHROPIC_API_KEY` — Claude API key (required for agents)
- `RAYOLLY_AUTH_JWT_SECRET` — JWT signing key
- `RAYOLLY_CLICKHOUSE_{HOST,PORT,USER,PASSWORD}`
- `RAYOLLY_NATS_URL`, `RAYOLLY_REDIS_URL`, `RAYOLLY_POSTGRES_URL`

## Sprint History

### Sprint 1: Foundation — Complete
15 PRDs (27K lines), backend scaffold, ingestion pipeline, query engine, AI/ML, 4 agents, 7 frontend pages, Docker Compose.

### Sprint 2: Modules — Complete
APM, Infrastructure, RUM, Synthetics, DEM, Agent Observability, 7 integrations, enhanced logging. 13 frontend pages total.

### Sprint 3: Quality & Fixes — Current
Critical security fixes (SQL injection), build fixes (Makefile, imports), comprehensive task planning. Next: tests, PostgreSQL metadata, auth.

## AI Agent Observability — Vision

This is first-of-its-kind. No competitor monitors their own AI features this way.

**Current**: Execution recording, cost tracking, tool usage stats, satisfaction ratings, issue detection.

**Target state** (what makes it world-class):
- **Execution waterfall**: Visualize each agent step like a distributed trace (thinking → tool_call → tool_result → thinking → response). Show token count, latency, cost per step.
- **Real-time monitoring**: Watch an agent investigate in real-time via SSE streaming. See it query logs, check metrics, build hypotheses.
- **Accuracy tracking**: For RCA agent — compare agent's root cause conclusion with human-verified root cause. Track accuracy % over time.
- **Hallucination detection**: Validate that when an agent says "error rate is 5%", the actual error rate matches. Flag discrepancies.
- **Cost forecasting**: Based on current agent usage, predict monthly costs. Alert if trending over budget.
- **Agent A/B testing**: Test new system prompts or tool sets against existing versions. Measure quality, speed, cost.
- **Agent SLOs**: Define SLOs for agents themselves (success rate > 90%, p95 latency < 30s, cost per investigation < $0.50).
- **Cross-agent correlation**: When Incident Agent delegates to RCA Agent, show the full chain as a single investigation trace.
