# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RayOlly is an enterprise-grade, AI-native observability platform (logs, metrics, traces, events) with **AI Agents-as-a-Service** as the core differentiator. Competes with Splunk, Datadog, Dynatrace, and New Relic. Uses OpenObserve as an architectural reference.

## Development Commands

```bash
# First-time setup
make setup          # Full dev environment setup (prereqs, deps, docker, DB)

# Infrastructure
make dev            # Start all services (ClickHouse, NATS, Redis, MinIO, Postgres)
make down           # Stop services
make init-db        # Run ClickHouse migrations (all .sql files in migrations/clickhouse/)
make migrate        # Run PostgreSQL Alembic migrations
make clean          # Stop and remove all volumes
make logs           # Tail service logs

# Backend (Python 3.12+ / FastAPI)
make api            # Run API server locally (uvicorn on :8080 with --reload)
make test           # Run all tests
make test-unit      # Run unit tests only
make test-cov       # Run tests with coverage report (terminal + HTML)
make lint           # ruff check + mypy
make format         # ruff format

# Run a single test file
cd backend && python -m pytest tests/unit/test_anomaly_detector.py -v

# Run a single test by name
cd backend && python -m pytest tests/ -k "test_zscore_anomaly" -v

# Frontend (Next.js 15 / React 19)
make web            # Next.js dev server on :3000 (turbopack)
make web-lint       # ESLint
make web-types      # TypeScript type check
make web-build      # Production build
```

## Architecture

```
Clients (OTEL SDKs, RayOlly Collector)
  │
  ▼
Ingestion Gateway (FastAPI + gRPC on :8080)
  │ Protocols: OTLP, Prometheus RemoteWrite, Splunk HEC, ES Bulk, Loki, JSON
  │ Pipeline: validate → enrich → PII redact → transform → route
  ▼
NATS JetStream (subjects: rayolly.ingest.{logs,metrics,traces}.{tenant_id})
  │
  ├──▶ ClickHouse (hot/warm storage, columnar)
  ├──▶ S3/MinIO (cold storage, Parquet via DuckDB)
  ├──▶ AI/ML Engine (anomaly scoring on ingest)
  └──▶ Alert Evaluator (real-time rule checking)
         │
         ▼
Query Engine ◄── Frontend (Next.js on :3000)
  │ SQL (RayQL) / PromQL / Full-text search
  │ Tier-aware federation (hot → warm → cold)
  ▼
AI Agent Orchestrator
  │ Anthropic tool-use loop, 12 built-in tools
  │ Agents: RCA, Query, Incident, Anomaly
  ▼
Integrations (ServiceNow, Twilio, Slack, PagerDuty, Jira, GitHub)
```

## Backend (`backend/rayolly/`)

**Entry point**: `api/app.py` — `create_app()` factory with lifespan managing NATS, Redis, ClickHouse connections. Clients stored on `app.state`.

**Configuration**: `core/config.py` — pydantic-settings with `RAYOLLY_` env prefix. Composed settings: Server, ClickHouse, NATS, Redis, S3, Auth, AI, Postgres.

**Middleware chain**: CORS → TenantMiddleware (extracts `tenant_id` from header/JWT/API key → `request.state.tenant_id`) → RequestLoggingMiddleware (structlog).

**Service modules** (each is a package under `services/`):

| Module | Key Classes | Purpose |
|--------|------------|---------|
| `ingestion/` | `IngestionPipeline`, `MessageRouter` | 5-stage processing, NATS publishing |
| `query/` | `QueryEngine`, `PromQLTranslator`, `QueryCache` | SQL/PromQL/search, tier federation |
| `storage/` | `StorageWriter` | NATS consumer → ClickHouse batch inserts |
| `ai/` | `AnomalyDetector`, `Forecaster`, `DrainParser` | Z-score/MAD/IQR/IsolationForest, Prophet, log patterns |
| `agents/` | `AgentRuntime`, `ToolRegistry`, `AgentMemoryStore` | Anthropic tool-use agentic loop (max 25 iterations) |
| `agents/observability` | `AgentObservabilityService` | Agent execution traces, costs, satisfaction tracking |
| `alerting/` | `AlertEvaluator`, `Notifier` | Rule evaluation loop, multi-channel dispatch |
| `apm/` | `ServiceMapBuilder`, `LatencyAnalyzer`, `ErrorTracker`, `SLOService` | Service topology, profiling, SLO burn rates |
| `infrastructure/` | `HostService`, `KubernetesService`, `CloudService`, `ContainerService` | Host maps, K8s (CrashLoopBackOff detection), cloud (AWS/GCP/Azure) |
| `rum/` | `RUMCollector`, `RUMAnalytics` | Core Web Vitals, session replay, page performance |
| `synthetics/` | `SyntheticMonitorService`, `SyntheticScheduler` | HTTP/SSL/DNS/TCP checks with timing breakdown |
| `logging/` | `LogExplorer`, `LiveTailService`, `LogViewService` | Search with facets, WebSocket live tail, saved views |
| `integrations/` | `IntegrationRegistry`, `ServiceNowIntegration`, `TwilioIntegration`, etc. | 7 enterprise integrations with pluggable framework |

**API routes** (13 route files under `api/routes/`): health, ingest, compat, query, logs, alerts, apm, infrastructure, rum, synthetics, agents, agent_observability, integrations.

**Models** (`models/`): Pydantic v2 — `telemetry.py` (OTEL-aligned LogRecord, MetricDataPoint, Span), `auth.py`, `query.py`, `alerts.py`, `agents.py`.

## Frontend (`frontend/src/`)

Next.js 15 App Router with React 19, TypeScript, Tailwind CSS v4, dark theme.

**13 pages**: Dashboard, Logs, Metrics, Traces, APM (service map), Infrastructure (host map, K8s, cloud, containers), RUM (Core Web Vitals), Synthetics (monitors, uptime), DEM (Apdex, funnels, session replay), AI Agents, Agent Observability, Alerts, Integrations (marketplace).

**Key components**: `Sidebar` (sectioned nav: Observability, Digital Experience, Intelligence, Platform), `TimeRangePicker`, `QueryEditor` (Monaco), `ChartWidget` (ECharts).

**State**: Zustand store (`stores/app.ts`) for timeRange, selectedService, sidebarCollapsed, theme.

**API proxy**: `next.config.ts` rewrites `/api/*` → `http://localhost:8080/api/*`.

## AI Agent System (`agents/builtin/`)

4 built-in agents defined with system prompts, tool lists, and triggers:
- **RCA Agent** — 10-step investigation methodology triggered by alerts/anomalies
- **Query Agent** — NL-to-SQL with schema awareness
- **Incident Commander** — lifecycle management, postmortem generation
- **Anomaly Investigator** — classifies ACTIONABLE vs NOISE vs NEEDS_MONITORING

Runtime (`services/agents/runtime.py`) implements the Anthropic messages API tool-use loop. 12 tools in `services/agents/tools.py` (query logs/metrics/traces, get service map, create alerts, send notifications, etc.).

## Infrastructure

**Docker Compose**: 7 services — rayolly-api (:8080), clickhouse (:8123/:9000), nats (:4222), redis (:6379), minio (:9002/:9001), postgres (:5432), rayolly-web (:3000).

**ClickHouse schemas**: `backend/migrations/clickhouse/` — `001_initial_schema.sql` (logs, metrics, traces, events, audit_log tables with codecs and TTL tiering), `002_agent_observability.sql` (agent_executions, agent_steps, agent_feedback).

**ClickHouse configs**: `infra/docker/clickhouse-config.xml`, `clickhouse-users.xml` (4 users: default, rayolly, rayolly_ingest, rayolly_reader).

## Critical Patterns

- **Tenant isolation**: Every ClickHouse query gets automatic `tenant_id` injection via `QueryEngine._inject_tenant()`. TenantMiddleware extracts tenant from `X-RayOlly-Tenant` header, API key lookup, or JWT.
- **ClickHouse partitioning**: All tables use `PARTITION BY (tenant_id, toYYYYMMDD(timestamp))`.
- **NATS subjects**: `rayolly.ingest.{signal}.{tenant_id}` for telemetry, `rayolly.alerts.events` for alert events.
- **Ingestion pipeline**: 5 stages — validate → enrich (GeoIP, K8s) → transform → PII detect → route to NATS.
- **Agent loop**: max 25 tool-use iterations, 5-minute timeout, tracks input/output tokens and cost.
- **Integration framework**: `BaseIntegration` abstract class with `test_connection()`, `sync()`, `execute_action()`. Register new integrations in `IntegrationRegistry`.

## Known Issues & Technical Debt

See `tasks.md` for full prioritized plan. Key items:

**Critical (fix before feature work):**
- Import error in `api/routes/apm.py` — references `rayolly.core.deps` (should be `rayolly.core.dependencies`)
- Import error in `api/routes/agents.py` — `agents.builtin.*` path resolution
- API key tenant resolution not implemented (TenantMiddleware line 47)
- Several services still use string interpolation for SQL (being migrated to parameterized)

**High (Sprint 1):**
- No test suite (0% coverage, target 80%)
- PostgreSQL metadata store not implemented (alerts, queries, incidents all in-memory)
- Agent executions stored in-memory dict (lost on restart)

**Tracked in:** `tasks.md` (prioritized backlog), `memory.md` (decisions & patterns), `skills.md` (capability gap matrix)

## Development Best Practices

**Before writing any service code**, check:
1. Does it accept `tenant_id` and use it in all queries?
2. Are ClickHouse queries parameterized (no f-string interpolation for user input)?
3. Is there a corresponding unit test?
4. Is the route registered in `api/app.py`?

**Commit format** (enforced by git hook): `type(scope): description`
- Types: feat, fix, refactor, docs, test, chore, perf, ci
- Scopes: ingestion, query, agents, apm, infra, rum, synthetics, alerts, integrations, frontend, storage, ai, logging, auth, core

**SQL safety**: Validate all dynamic values with `re.match(r'^[a-zA-Z0-9_-]+$', value)` before using in SQL. See `QueryEngine._inject_tenant()` for the pattern.

## Project Documentation Map

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Development guidance for Claude Code (this file) |
| `README.md` | Project overview, quick start, architecture |
| `tasks.md` | Prioritized development backlog with gap analysis |
| `memory.md` | Architecture decisions, patterns, technical debt, sprint history |
| `skills.md` | Full capability matrix with gap analysis per module |
| `docs/prds/` | 15 Product Requirements Documents (27K lines) |
| `docs/research/` | Competitive analysis, OpenObserve reference |

## PRD Documents

15 PRDs in `docs/prds/` (PRD-00 through PRD-14) covering full platform specs. PRD-05 (AI Agents-as-a-Service) is the most critical — the primary competitive differentiator. Research in `docs/research/` (competitive analysis, OpenObserve reference).
