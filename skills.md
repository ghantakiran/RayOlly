# RayOlly — Skills & Capabilities Matrix

Platform capabilities with gap analysis. Status: **Active** (working), **Partial** (stubbed/incomplete), **Planned** (not started), **Gap** (missing and needed to compete).

---

## Data Collection

| Skill | Status | Gap Analysis |
|-------|--------|-------------|
| OTLP HTTP ingestion | Active | — |
| OTLP gRPC ingestion | **Gap** | Needed for high-throughput OTEL Collector. Deps installed, not wired. |
| Prometheus Remote Write | Partial | Proto parsing stubbed. Need compiled protos. |
| Splunk HEC compat | Active | — |
| Elasticsearch Bulk compat | Active | — |
| Loki Push compat | Active | — |
| JSON API ingestion | Active | — |
| Datadog API compat | **Gap** | Key migration path. Datadog has largest market share. |
| StatsD ingestion | **Gap** | Legacy apps still use StatsD heavily. |
| Kafka consumer | **Gap** | Many enterprises have telemetry in Kafka already. |
| GeoIP enrichment | Active | — |
| K8s metadata enrichment | Partial | Stubbed. Needs real K8s API integration. |
| PII detection (regex) | Active | — |
| PII detection (AI-based) | **Gap** | Would catch PII that regex misses (names, addresses). |
| Grok pattern library | **Gap** | Splunk has 200+ patterns. Critical for log parsing. |
| Adaptive sampling | **Gap** | Needed to control costs at high volume. |
| Backpressure handling | **Gap** | No queue depth monitoring or 429 responses yet. |

## Query & Analytics

| Skill | Status | Gap Analysis |
|-------|--------|-------------|
| SQL (RayQL) | Active | Works but uses string interpolation. Need parameterized queries throughout. |
| PromQL | Partial | Regex-based parser. ~30% function coverage. Need AST parser for Grafana compat. |
| Full-text search (ClickHouse) | Active | hasToken-based. Adequate but not as fast as Tantivy. |
| Full-text search (Tantivy) | **Gap** | Specified in PRD-03. Needed for sub-second search at petabyte scale. |
| Query caching (Redis) | Active | — |
| Tier federation (hot/warm/cold) | Active | Planner exists but cold tier (DuckDB) not implemented. |
| Prometheus API compat | Active | /query, /query_range, /labels, /label/*/values |
| Grafana data source | **Gap** | Native plugin would accelerate adoption. |
| Saved queries | Partial | API exists, not persisted (in-memory only). |
| Scheduled queries | **Gap** | Needed for SLO tracking, report generation. |
| Query explain plan | Partial | Returns plan info but no execution statistics. |
| JDBC/ODBC driver | **Gap** | Enables BI tools (Tableau, Metabase, Superset). |

## AI/ML Engine

| Skill | Status | Gap Analysis |
|-------|--------|-------------|
| Z-score anomaly detection | Active | — |
| MAD anomaly detection | Active | — |
| IQR anomaly detection | Active | — |
| Isolation Forest | Active | — |
| Ensemble anomaly detection | Active | Majority voting across methods. |
| Linear forecasting | Active | — |
| Prophet forecasting | Active | — |
| Resource exhaustion prediction | Active | — |
| Log pattern mining (Drain) | Active | — |
| Real-time scoring on ingest | **Gap** | Anomaly detection runs on-demand, not streaming. |
| Per-tenant model training | **Gap** | Models are stateless. Need training pipeline. |
| Model registry | **Gap** | No versioning, A/B testing, or rollback for models. |
| Metric correlation engine | **Gap** | Auto-discover related metrics (like Datadog Watchdog). |
| LSTM/Autoencoder anomalies | **Gap** | For complex temporal patterns Isolation Forest misses. |
| Change point detection | **Gap** | Detect regime changes (not just outliers). |
| Causal inference (Granger) | **Gap** | Determine causality, not just correlation. |

## AI Agents — First of Its Kind

| Skill | Status | Gap Analysis |
|-------|--------|-------------|
| Agent runtime (Anthropic loop) | Active | 25 max iterations, 5-min timeout. |
| RCA Agent | Active | 10-step investigation methodology. |
| Query Agent (NL→SQL) | Active | Schema-aware, iterative refinement. |
| Incident Commander | Active | Lifecycle management, postmortem draft. |
| Anomaly Investigator | Active | Classifies actionable vs noise. |
| 12 built-in tools | Active | Query logs/metrics/traces, service map, alerts, notifications. |
| Short-term memory (Redis) | Active | Per-execution, 1h TTL. |
| Long-term memory (PostgreSQL) | Active | Persistent per-tenant knowledge. |
| Agent execution persistence | **Gap** | Currently in-memory dict. Lost on restart. Must move to ClickHouse. |
| SSE streaming responses | **Gap** | Agents respond after full completion. Need real-time streaming. |
| Agent-to-agent delegation | **Gap** | Critical for incident workflows (Incident→RCA→Notification chain). |
| Custom agent builder UI | **Gap** | Drag-and-drop tools, edit prompt, test. Key for marketplace. |
| Agent marketplace | **Gap** | Publish, install, rate, revenue share. Primary business model differentiator. |
| Multi-model routing | **Gap** | Haiku for simple queries, Opus for complex RCA. Save costs. |
| Local model fallback | **Gap** | vLLM for air-gapped deployments. Enterprise requirement. |
| Agent versioning | **Gap** | A/B test prompt versions. Essential for iterating agent quality. |
| Capacity Planning Agent | **Gap** | Forecast exhaustion, recommend scaling. |
| SLO Guardian Agent | **Gap** | Monitor burn rates, predict breaches. |
| Runbook Executor Agent | **Gap** | Execute remediation with human approval. |
| Cost Optimization Agent | **Gap** | Identify waste in cloud/K8s resources. |
| Security Agent | **Gap** | Detect suspicious patterns, auth anomalies. |

## Agent Observability — Unique Differentiator

| Skill | Status | Gap Analysis |
|-------|--------|-------------|
| Execution recording | Active | Records steps, tools, tokens, cost. |
| Cost tracking per agent | Active | By agent type, tenant, model. |
| Tool usage statistics | Active | Invocations, latency, error rates. |
| User satisfaction (thumbs) | Active | Feedback collection and trending. |
| Issue detection | Active | High failure rate, slow agents, cost spikes. |
| ClickHouse tables | Active | agent_executions, agent_steps, agent_feedback. |
| Observability dashboard | Active | Cards, tables, charts with mock data. |
| **Execution waterfall** | **Gap** | Show agent steps like a distributed trace. This is the killer feature. |
| **Real-time monitoring** | **Gap** | Watch agent investigate live via SSE. |
| **Accuracy tracking** | **Gap** | Compare agent conclusions with human-verified answers. |
| **Hallucination detection** | **Gap** | Validate agent claims against actual data. |
| **Cost forecasting** | **Gap** | Predict monthly agent costs, alert on overspend. |
| **Agent A/B testing** | **Gap** | Test new prompts against existing. Measure quality. |
| **Agent SLOs** | **Gap** | success_rate > 90%, p95_latency < 30s, cost < $0.50. |
| **Cross-agent traces** | **Gap** | When agents delegate, show the full chain. |
| **Agent drift detection** | **Gap** | Alert when agent behavior changes (token usage, tool patterns). |

## Observability Modules

### Logging
| Skill | Status | Gap |
|-------|--------|-----|
| Full-text search with facets | Active | — |
| Log volume histogram | Active | — |
| Live tail (WebSocket) | Active | — |
| Saved views | Active | Not persisted. |
| Log-to-metrics | Active | — |
| Log patterns (Drain) | Active | — |
| Log archive (S3 Parquet) | **Gap** | Needed for compliance retention. |
| Log pipeline config UI | **Gap** | — |

### APM
| Skill | Status | Gap |
|-------|--------|-----|
| Service dependency map | Active | — |
| Latency analysis (percentiles) | Active | — |
| Error fingerprinting | Active | — |
| Continuous profiling | Active | — |
| SLO management | Active | — |
| Database query tracking | **Gap** | SQL explain plans, slow query analysis. |
| Code-level visibility | **Gap** | Method-level profiling. Dynatrace has this. |

### Infrastructure
| Skill | Status | Gap |
|-------|--------|-----|
| Host monitoring | Active | — |
| Kubernetes monitoring | Active | CrashLoopBackOff, OOM detection. |
| Cloud monitoring (AWS/GCP/Azure) | Active | — |
| Container monitoring | Active | — |
| Network monitoring | **Gap** | Datadog NPM equivalent. |
| Process monitoring | **Gap** | Top processes by resource. |
| eBPF-based monitoring | **Gap** | Like Pixie/New Relic. Zero-config K8s observability. |

### RUM
| Skill | Status | Gap |
|-------|--------|-----|
| Core Web Vitals | Active | — |
| Page performance | Active | — |
| JS error tracking | Active | — |
| Session replay collection | Active | — |
| Browser SDK | **Gap** | Must build `@rayolly/browser-sdk`. |
| Session replay player | **Gap** | Need rrweb integration. |
| Mobile SDKs | **Gap** | iOS/Android. |

### Synthetics
| Skill | Status | Gap |
|-------|--------|-----|
| HTTP/SSL/DNS/TCP checks | Active | — |
| Assertion engine | Active | — |
| Monitor scheduling | Active | — |
| Multi-location execution | **Gap** | Need distributed check infrastructure. |
| Browser tests (Playwright) | **Gap** | For complex user flows. |
| Public status page | **Gap** | Custom domain support. |

## Integrations

| Integration | Status | Gap |
|-------------|--------|-----|
| ServiceNow | Active | — |
| Twilio (SMS/voice) | Active | Ack webhook not implemented. |
| Slack (Block Kit) | Active | — |
| PagerDuty | Active | — |
| Jira | Active | — |
| GitHub | Active | — |
| Generic Webhook | Active | — |
| OpsGenie | **Gap** | Common in enterprises. |
| Microsoft Teams (full) | **Gap** | Adaptive Cards, not just webhook. |
| AWS CloudWatch | **Gap** | Import AWS metrics. |
| GCP Cloud Monitoring | **Gap** | Import GCP metrics. |
| Azure Monitor | **Gap** | Import Azure metrics. |
| Terraform provider | **Gap** | Infrastructure-as-code for dashboards, alerts. |
| Datadog (import) | **Gap** | Migration tool to import dashboards/monitors. |
| Prometheus (federation) | **Gap** | Federated query from existing Prometheus. |

## Platform & Enterprise

| Skill | Status | Gap |
|-------|--------|-----|
| Multi-tenant isolation | Active | Tenant middleware + query injection. |
| Structured logging | Active | structlog with JSON. |
| Health checks | Active | /healthz, /readyz. |
| OpenAPI docs | Active | Auto-generated by FastAPI. |
| Docker Compose dev env | Active | — |
| Git hooks (pre-commit, commit-msg, pre-push) | Active | — |
| JWT authentication | **Gap** | Critical for production. |
| RBAC enforcement | **Gap** | Roles exist in models, not enforced. |
| SSO (SAML/OIDC) | **Gap** | Enterprise requirement. |
| API key management | **Gap** | Create, rotate, revoke. |
| Audit logging | **Gap** | Table exists, not written to. |
| Rate limiting | **Gap** | Redis token bucket defined, not enforced. |
| Kubernetes Helm chart | **Gap** | Required for production deployment. |
| Test suite | **Gap** | 0% coverage. Target 80%. |
| CI/CD pipeline | **Gap** | No GitHub Actions. |

---

## Gap Priority Matrix

| Priority | Count | Examples |
|----------|-------|---------|
| **P0 (ship-blocking)** | 8 | SQL injection fix, auth, test suite, broken imports, OTLP gRPC |
| **P1 (core quality)** | 14 | PostgreSQL store, PromQL parser, Tantivy search, agent persistence |
| **P2 (feature gaps)** | 18 | Agent marketplace, RUM SDK, browser tests, network monitoring |
| **P3 (nice-to-have)** | 12 | eBPF, Terraform provider, JDBC driver, mobile SDKs |

**Total gaps identified: 52** — see tasks.md for the full prioritized plan.
