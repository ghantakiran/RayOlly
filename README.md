# RayOlly

**AI-Native Observability Platform**

RayOlly unifies logs, metrics, traces, and events into a single platform with **autonomous AI agents** that detect, diagnose, and resolve issues before they impact users. Built for enterprise scale, open at its core.

```
┌─────────────────────────────────────────────────────────────┐
│  Logs  │  Metrics  │  Traces  │  RUM  │  Synthetics        │
├─────────────────────────────────────────────────────────────┤
│                  Unified Data Lake                           │
│           ClickHouse (hot) + S3/Parquet (cold)              │
├─────────────────────────────────────────────────────────────┤
│          AI/ML Engine · Anomaly · Forecast · Patterns       │
├─────────────────────────────────────────────────────────────┤
│       AI Agents-as-a-Service (RCA · Incident · Query)       │
├─────────────────────────────────────────────────────────────┤
│  Dashboards · NL Chat · Alerts · API · Integrations · CLI   │
└─────────────────────────────────────────────────────────────┘
```

## Why RayOlly?

| vs Competition | RayOlly Advantage |
|---------------|-------------------|
| **Datadog** | 10x lower cost, no per-GB bill shock, self-hosted option |
| **Splunk** | Modern UI, AI agents (not just dashboards), OTEL-native |
| **Dynatrace** | Open core, custom agent creation, transparent AI |
| **New Relic** | Autonomous agents, richer APM, enterprise integrations |
| **All** | AI Agents-as-a-Service — no competitor has this |

## Platform Modules

| Module | Description |
|--------|-------------|
| **Logging** | Full-text search, live tail (WebSocket), log patterns, log-to-metrics |
| **Metrics** | PromQL compatible, anomaly detection, forecasting, SLO management |
| **Tracing & APM** | Service maps, latency analysis, error tracking, continuous profiling |
| **Infrastructure** | Hosts, Kubernetes, containers, cloud (AWS/GCP/Azure) |
| **RUM** | Core Web Vitals, page performance, JS errors, session replay |
| **Synthetic Monitoring** | HTTP/SSL/DNS/TCP checks, uptime tracking, status pages |
| **Digital Experience** | Apdex scoring, user journey funnels, frontend-backend correlation |
| **AI Agents** | Autonomous RCA, incident management, NL queries, anomaly investigation |
| **Agent Observability** | Monitor AI agents: costs, performance, satisfaction, tool usage |
| **Alerting** | AI-powered noise reduction, multi-channel notifications, incident lifecycle |
| **Integrations** | ServiceNow, Twilio, Slack, PagerDuty, Jira, GitHub, webhooks |

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.12+
- Node.js 22+

### Start the Platform

```bash
# Clone and start infrastructure
git clone https://github.com/ghantakiran/RayOlly.git
cd RayOlly

# Full dev environment setup (prereqs, deps, docker, DB)
make setup

# Or step-by-step:
make dev        # Start all services (ClickHouse, NATS, Redis, MinIO, Postgres)
make init-db    # Initialize database schemas
make api        # Start the backend API on :8080

# In another terminal — start the frontend
make web        # Next.js dev server on :3000
```

Open [http://localhost:3000](http://localhost:3000) for the dashboard.
API available at [http://localhost:8080/docs](http://localhost:8080/docs) (Swagger UI).

### Send Test Data

```bash
# Send a log via OTLP HTTP
curl -X POST http://localhost:8080/v1/logs \
  -H "Content-Type: application/json" \
  -H "X-RayOlly-Tenant: demo" \
  -d '{"resourceLogs":[{"resource":{"attributes":[{"key":"service.name","value":{"stringValue":"payment-api"}}]},"scopeLogs":[{"logRecords":[{"timeUnixNano":"1711000000000000000","body":{"stringValue":"Payment processed successfully"},"severityNumber":9,"severityText":"INFO"}]}]}]}'

# Send a log via JSON API
curl -X POST http://localhost:8080/api/v1/logs/ingest \
  -H "Content-Type: application/json" \
  -H "X-RayOlly-Tenant: demo" \
  -d '{"stream":"app-logs","logs":[{"timestamp":"2026-03-19T10:00:00Z","body":"Order completed","severity":"INFO","attributes":{"order_id":"ord_123","amount":"49.99"}}]}'

# Query via PromQL-compatible API
curl "http://localhost:8080/api/v1/prometheus/query?query=http_requests_total" \
  -H "X-RayOlly-Tenant: demo"

# Invoke the RCA Agent
curl -X POST http://localhost:8080/api/v1/agents/invoke \
  -H "Content-Type: application/json" \
  -H "X-RayOlly-Tenant: demo" \
  -d '{"agent_type":"rca","input":{"alert":"High error rate on payment-api","severity":"critical"}}'
```

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12+, FastAPI, gRPC, uvloop |
| Frontend | Next.js 15, React 19, TypeScript, Tailwind CSS v4, ECharts, Monaco |
| Hot Storage | ClickHouse (columnar OLAP, 10-100x compression) |
| Cold Storage | Apache Parquet on S3/MinIO, queried via DuckDB |
| Streaming | NATS JetStream |
| Cache | Redis |
| AI/ML | scikit-learn, Prophet, ONNX Runtime, Anthropic Claude API |
| Deployment | Docker Compose (dev), Kubernetes + Helm (production) |

## Frontend Design System

The frontend uses a **mission-control dark theme** designed for SREs and developers who spend long hours in dashboards.

### Design Highlights

- **Glass Morphism** — Frosted glass cards with `backdrop-filter: blur()` and subtle borders
- **Aurora Effects** — Animated gradient sweeps and mesh backgrounds for depth
- **Severity-Aware Colors** — Consistent palette (emerald/amber/red/purple) across all states
- **Glow System** — Status dots, active nav items, and cards emit subtle colored glow
- **Micro-Animations** — Staggered list entry, card hover lift, shimmer loading skeletons
- **Tabular Numbers** — All metrics use `font-variant-numeric: tabular-nums` for alignment
- **JetBrains Mono** — Monospace font for logs, trace IDs, and code blocks

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Cmd+K` | Command palette |
| `G` then `D` | Go to Dashboard |
| `G` then `L` | Go to Logs |
| `G` then `M` | Go to Metrics |
| `G` then `T` | Go to Traces |
| `G` then `A` | Go to AI Agents |
| `G` then `I` | Go to Infrastructure |
| `G` then `R` | Go to Alerts |
| `G` then `S` | Go to Settings |
| `/` | Focus search (Logs page) |
| `?` | Show keyboard shortcuts |

### Component Library

Reusable components in `frontend/src/components/shared/`:

| Component | Description |
|-----------|-------------|
| `Badge` | Severity/status badges with 9 color variants |
| `Button` | Primary (gradient), secondary, ghost, danger, success |
| `Card` | Default, glass, elevated, interactive (hover glow ring) |
| `StatusDot` | Health indicators with colored glow shadows |
| `ProgressBar` | Default, gradient (color changes by value) |
| `MiniSparkline` | Inline sparkline for metric cards |
| `UptimeBar` | SRE uptime visualization (30-day bars) |
| `LiveIndicator` | Pulsing emerald "Live" badge |
| `Kbd` | Keyboard shortcut display |

## Project Structure

```
backend/                    Python backend (FastAPI)
  rayolly/
    api/                    FastAPI app, middleware, 13 route modules
    core/                   Config, logging, dependencies
    models/                 Pydantic v2 models (telemetry, auth, query, alerts, agents)
    services/               13 service modules (see table above)
  migrations/clickhouse/    ClickHouse DDL schemas
  tests/                    pytest (unit, integration, e2e)
frontend/                   Next.js 15 frontend
  src/app/                  16 pages (App Router)
  src/components/           Shared components (sidebar, charts, editor)
  src/lib/                  API client, utilities
  src/stores/               Zustand global state
agents/builtin/             4 AI agent definitions (RCA, Query, Incident, Anomaly)
docs/prds/                  15 Product Requirements Documents
docs/research/              Competitive analysis, OpenObserve reference
infra/                      Docker configs, Helm charts, Terraform
```

## Development

```bash
make help       # Show all available commands
make setup      # Full dev environment setup
make dev        # Start infrastructure services
make api        # Run API server (uvicorn on :8080)
make web        # Run frontend (Next.js on :3000)
make test       # Run all tests
make test-cov   # Tests with coverage report
make lint       # Lint (ruff + mypy)
make format     # Auto-format (ruff)
make web-build  # Production frontend build
make web-lint   # ESLint
make web-types  # TypeScript type check
```

See [CLAUDE.md](CLAUDE.md) for detailed architecture and development guidance.

## Ingestion Compatibility

RayOlly accepts data from any existing observability stack:

| Protocol | Endpoint | Migration From |
|----------|----------|---------------|
| OTLP gRPC | `:4317` | Any OTEL SDK |
| OTLP HTTP | `/v1/{logs,metrics,traces}` | Any OTEL SDK |
| Prometheus Remote Write | `/api/v1/prometheus/write` | Prometheus, Grafana Agent |
| Splunk HEC | `/services/collector/event` | Splunk |
| Elasticsearch Bulk | `/_bulk` | ELK, OpenSearch |
| Loki Push | `/loki/api/v1/push` | Grafana Loki |
| JSON API | `/api/v1/{logs,metrics}/ingest` | Custom |

## License

Apache 2.0 (core platform) — Enterprise features under commercial license.
