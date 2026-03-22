# RayOlly — Development Task Plan

## Legend
- [x] Complete
- [~] Partial / stubbed (needs finishing)
- [ ] Not started
- Priority: P0 (ship-blocking), P1 (core quality), P2 (feature), P3 (nice-to-have)

---

## SPRINT 0: Critical Fixes (Do First)

> These are bugs, security issues, and broken builds that must be fixed before any feature work.

### P0 — Security
- [x] Fix SQL injection in QueryEngine._inject_tenant() — validate tenant_id format
- [x] Fix SQL injection in _build_search_sql() — sanitize search terms
- [ ] Fix SQL injection in PromQLTranslator — sanitize label values and metric names
- [ ] Fix SQL injection in LogExplorer — parameterize all ClickHouse queries
- [ ] Audit all services/ for string-interpolated SQL and fix with parameterized queries
- [ ] Remove hardcoded credentials from docker configs (use env vars or secrets)

### P0 — Build Fixes
- [x] Fix Makefile api target: `rayolly.main:app` → `rayolly.api.app:app`
- [ ] Fix broken import in `api/routes/apm.py`: `rayolly.core.deps` → `rayolly.core.dependencies`
- [ ] Fix broken import in `api/routes/agents.py`: `agents.builtin.*` — add agents/ to PYTHONPATH or restructure
- [ ] Verify all 13 route modules import and register without errors
- [ ] Add `conftest.py` to tests/ with fixtures for ClickHouse mock, NATS mock, Redis mock

### P0 — Auth & Tenant Isolation
- [ ] Implement API key lookup in TenantMiddleware (PostgreSQL query)
- [ ] Implement JWT token validation (verify signature, expiry, claims)
- [ ] Add tenant_id validation to ALL service methods (not just query engine)
- [ ] Add integration test: verify cross-tenant data access is impossible

---

## SPRINT 1: Foundation Quality (Weeks 1-3)

> Make the existing code actually work end-to-end. No new features until this is solid.

### P0 — PostgreSQL Metadata Store
- [ ] Create Alembic migration infrastructure (`alembic init`, alembic.ini)
- [ ] Migration 001: users, organizations, teams, api_keys tables
- [ ] Migration 002: alert_rules, notification_channels, on_call_schedules tables
- [ ] Migration 003: saved_queries, query_history tables
- [ ] Migration 004: integration_instances, integration_configs tables
- [ ] Migration 005: agent_definitions (custom), agent_configs tables
- [ ] Migration 006: dashboards, dashboard_widgets tables
- [ ] Migration 007: slo_definitions, slo_history tables
- [ ] SQLAlchemy async models for all metadata tables
- [ ] Repository pattern for each entity (UserRepository, AlertRuleRepository, etc.)

### P0 — Test Suite
- [ ] `tests/conftest.py` — shared fixtures (mock ClickHouse, mock NATS, mock Redis, test tenant)
- [ ] `tests/unit/test_anomaly_detector.py` — all 4 methods + ensemble
- [ ] `tests/unit/test_forecaster.py` — linear + breach prediction
- [ ] `tests/unit/test_drain_parser.py` — pattern extraction, similarity, new patterns
- [ ] `tests/unit/test_pii_detector.py` — all patterns, edge cases, redaction
- [ ] `tests/unit/test_validators.py` — timestamp range, field limits, size limits
- [ ] `tests/unit/test_promql_translator.py` — rate, sum, histogram_quantile, selectors
- [ ] `tests/unit/test_query_engine.py` — tenant injection, caching, tier routing
- [ ] `tests/unit/test_enrichment.py` — GeoIP, hostname enrichment
- [ ] `tests/unit/test_ingestion_pipeline.py` — full pipeline (validate→enrich→PII→route)
- [ ] `tests/unit/test_service_map.py` — topology building, health classification
- [ ] `tests/unit/test_latency_analyzer.py` — percentiles, breakdown, comparison
- [ ] `tests/unit/test_error_tracker.py` — fingerprinting, classification, regression
- [ ] `tests/unit/test_slo_service.py` — burn rates, breach prediction
- [ ] `tests/unit/test_alert_evaluator.py` — condition checking, fire/resolve lifecycle
- [ ] `tests/unit/test_notifier.py` — each channel type
- [ ] `tests/unit/test_agent_runtime.py` — tool-use loop, iteration limit, timeout
- [ ] `tests/unit/test_integration_registry.py` — register, create instance, test connection
- [ ] `tests/integration/test_clickhouse_writer.py` — batch inserts, flush triggers
- [ ] `tests/integration/test_nats_routing.py` — publish/subscribe, backpressure
- [ ] `tests/integration/test_ingest_to_query.py` — ingest data → query it back
- [ ] Target: 80% code coverage on services/

### P1 — Wire Up Stubs
- [ ] Alert rules: persist to PostgreSQL, load in evaluator loop
- [ ] Saved queries: persist to PostgreSQL, CRUD operations
- [ ] Query history: track per-user/tenant, store in PostgreSQL
- [ ] Agent executions: persist to ClickHouse (agent_executions table), not in-memory dict
- [ ] Incident lifecycle: persist to PostgreSQL with timeline events
- [ ] Email notifications: implement via SMTP or AWS SES
- [ ] Postmortem generation: wire Incident Agent with Claude API

### P1 — CI/CD Pipeline
- [ ] GitHub Actions: lint (ruff + mypy) on every PR
- [ ] GitHub Actions: test suite on every PR
- [ ] GitHub Actions: frontend lint + type-check on every PR
- [ ] GitHub Actions: Docker build test on every PR
- [ ] GitHub Actions: security scanning (trivy, detect-secrets) on every PR
- [ ] Branch protection: require passing CI before merge

---

## SPRINT 2: AI/Agent Observability — First of Its Kind (Weeks 4-7)

> This is THE differentiator. Make it world-class.

### P0 — Agent Execution Engine
- [ ] SSE streaming for agent responses (real-time token streaming to UI)
- [ ] Agent execution persistence to ClickHouse (replace in-memory dict)
- [ ] Agent step-level tracing (each tool call as a trace span with timing)
- [ ] Agent cost attribution per tenant (daily/weekly/monthly rollups)
- [ ] Agent token budget enforcement per tenant (configurable limits)

### P0 — Agent Observability Dashboard (make it the best)
- [ ] Execution waterfall view (like a trace — show each step, tool call, LLM call)
- [ ] Real-time execution monitoring (watch agent think in real-time)
- [ ] Agent comparison view (compare RCA agent accuracy over time)
- [ ] Cost forecasting (predict monthly agent costs at current usage)
- [ ] Agent A/B testing framework (test new prompts against old)
- [ ] Hallucination detection (validate agent tool call results against actual data)
- [ ] Agent SLOs (success rate, latency, cost per investigation)

### P1 — Advanced Agent Capabilities
- [ ] Agent-to-agent delegation (Incident → triggers RCA → triggers Notification)
- [ ] Agent memory evolution (long-term learning from past investigations per tenant)
- [ ] Custom agent builder UI (drag-and-drop tools, edit system prompt, test)
- [ ] Agent marketplace backend (publish, install, rate, revenue share)
- [ ] Agent versioning (A/B test prompt versions, rollback)
- [ ] Multi-model support (route simple queries to Haiku, complex RCA to Opus)
- [ ] Local model fallback (vLLM with Llama/Mistral for air-gapped deployments)

### P1 — New Built-in Agents
- [ ] Capacity Planning Agent (forecast resource exhaustion, recommend scaling)
- [ ] SLO Guardian Agent (monitor burn rates, predict breaches, recommend interventions)
- [ ] Runbook Executor Agent (execute remediation steps with human approval)
- [ ] Cost Optimization Agent (identify over-provisioned resources, unused indexes)
- [ ] Security Agent (detect suspicious patterns in logs, auth anomalies)
- [ ] Change Correlation Agent (link deployments to incidents automatically)

### P2 — Agent Intelligence
- [ ] Agent knowledge graph (services, teams, dependencies, runbooks per tenant)
- [ ] Automated incident pattern library (learn from past incidents)
- [ ] Agent confidence calibration (track prediction accuracy over time)
- [ ] Cross-tenant anonymized learning (improve models from aggregate patterns)

---

## SPRINT 3: Production-Grade Observability (Weeks 8-12)

### P0 — Storage & Performance
- [ ] S3/MinIO Parquet cold tier writer (compact ClickHouse data to Parquet)
- [ ] DuckDB cold tier query engine (query Parquet files in place)
- [ ] Data lifecycle manager (enforce TTL, tiering policies per tenant)
- [ ] ClickHouse cluster mode (2 shards, 2 replicas minimum)
- [ ] Query performance benchmarks (target: p99 < 2s for 1TB, < 5s for 100TB)
- [ ] Ingestion load test (target: 1M events/sec per node)

### P0 — OTLP gRPC Server
- [ ] Compile OpenTelemetry proto definitions
- [ ] Implement LogsService/Export gRPC handler
- [ ] Implement MetricsService/Export gRPC handler
- [ ] Implement TraceService/Export gRPC handler
- [ ] Test with official OTEL Collector exporter

### P1 — Full PromQL Compatibility
- [ ] Replace regex-based PromQL parser with proper AST parser
- [ ] Implement all PromQL functions (see PRD-03 for full list)
- [ ] Pass Prometheus compliance test suite
- [ ] Grafana data source plugin (native RayOlly, not just Prometheus compat)

### P1 — Full-Text Search (Tantivy)
- [ ] Tantivy Rust bindings via PyO3 (tantivy-py)
- [ ] Index management (create, update, compact, delete per stream)
- [ ] Query syntax: AND, OR, NOT, wildcards, phrase, fuzzy, proximity
- [ ] Highlighting in results
- [ ] Benchmark: sub-second search across 1B log lines

### P1 — Advanced Ingestion
- [ ] Prometheus Remote Write with compiled protobuf
- [ ] Tail-based sampling (collect spans, make decision after trace completes)
- [ ] Adaptive sampling (auto-adjust rate based on queue depth)
- [ ] Kubernetes metadata enrichment (real K8s API integration)
- [ ] Grok pattern library (100+ patterns for common log formats)
- [ ] Rust hot-path parser via PyO3 (10x parsing throughput)

### P2 — RUM JavaScript SDK
- [ ] Browser SDK: auto-capture page views, Web Vitals, JS errors, resource timing
- [ ] Session replay recording (DOM mutations, mouse, scroll, input)
- [ ] Auto-inject trace context for frontend-to-backend correlation
- [ ] NPM package: `@rayolly/browser-sdk`
- [ ] CDN-hosted script tag option

### P2 — Synthetic Monitoring Production
- [ ] Multi-location check infrastructure (at least 5 global locations)
- [ ] Browser-based synthetic tests (Playwright runner)
- [ ] Public status page hosting (custom domain support)
- [ ] SSL certificate monitoring with renewal alerts

---

## SPRINT 4: Enterprise & Scale (Weeks 13-18)

### P0 — Authentication & Authorization
- [ ] JWT auth with refresh tokens
- [ ] SSO: SAML 2.0 (Okta, Azure AD, OneLogin)
- [ ] SSO: OIDC (Google, GitHub, Auth0, Keycloak)
- [ ] SCIM 2.0 user/group provisioning
- [ ] RBAC: built-in roles (Owner, Admin, Editor, Viewer)
- [ ] RBAC: custom roles with permission matrix
- [ ] Field-level access control (hide sensitive fields)
- [ ] API key management (create, rotate, revoke, scope, expiry)
- [ ] Audit logging (all admin actions to ClickHouse)

### P0 — Multi-Tenancy Production
- [ ] Per-tenant resource quotas (ingestion rate, storage, query concurrency)
- [ ] Per-tenant rate limiting (Redis token bucket)
- [ ] Noisy neighbor prevention (ClickHouse query weight limits)
- [ ] Tenant onboarding automation (create org, first user, API key, sample data)

### P1 — Kubernetes Deployment
- [ ] Helm chart with values for small/medium/large deployments
- [ ] Kubernetes Operator (CRD for RayOlly clusters)
- [ ] HPA per component (ingester, querier, agent-runtime)
- [ ] PodDisruptionBudgets, anti-affinity, topology spread
- [ ] Multi-AZ deployment (minimum 3 AZs)
- [ ] Health checks, readiness probes, graceful shutdown

### P1 — Frontend Completions
- [ ] Dashboard builder (drag-and-drop grid, 15+ widget types)
- [ ] Dashboard templates (K8s, AWS, Node.js, Python, Java)
- [ ] Settings pages (org, team, user, API key management)
- [ ] Onboarding wizard (install collector, send first data, see results)
- [ ] Command palette (Cmd+K) with global search
- [ ] Keyboard shortcuts throughout
- [ ] Real API integration (replace all mock data)
- [ ] WebSocket live updates for dashboards

### P2 — Advanced Features
- [ ] Terraform provider (dashboards, alerts, SLOs, integrations)
- [ ] GraphQL API for frontend flexibility
- [ ] CLI tool (`rayolly query`, `rayolly tail`, `rayolly agent invoke`)
- [ ] Python/TypeScript/Go SDK libraries
- [ ] Webhook incoming (custom event ingestion)
- [ ] Scheduled reports (PDF/PNG via headless Chrome)

### P3 — Compliance
- [ ] SOC 2 Type II controls and evidence collection
- [ ] HIPAA BAA support (PHI handling)
- [ ] GDPR: data processing records, right to erasure
- [ ] FedRAMP readiness assessment

---

## Metrics to Track

| Metric | Current | Sprint 1 Target | Sprint 4 Target |
|--------|---------|-----------------|-----------------|
| Test coverage | 0% | 80% | 90% |
| SQL injection vectors | ~15 | 0 | 0 |
| Stubbed endpoints | ~12 | 3 | 0 |
| PostgreSQL-backed entities | 0 | 7 | All |
| PromQL function coverage | ~30% | 60% | 99% |
| Agent types | 4 | 6 | 10 |
| Integration count | 7 | 10 | 20 |
| Frontend pages with real data | 0 | 5 | 13 |
