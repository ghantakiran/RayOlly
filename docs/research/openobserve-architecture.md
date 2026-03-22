# OpenObserve (O2) — Comprehensive Technical Reference

**Repo**: https://github.com/openobserve/openobserve
**Version**: 0.80.0
**License**: AGPL-3.0 (open source); separate commercial Enterprise License
**Stars**: ~18,200 | **Language**: Rust (backend) + TypeScript/Vue (frontend)

---

## 1. Architecture

OpenObserve is a **monolithic single-binary** observability platform written in Rust. Stateless, cloud-native design.

**Core source modules** (`src/`):

| Module | Responsibility |
|--------|---------------|
| `handler/http` | Axum-based HTTP API handlers (REST + ingestion) |
| `handler/grpc` | gRPC handlers (Arrow Flight for distributed query, OTLP) |
| `service/` | Business logic: logs, metrics, traces, search, alerts, pipelines, PromQL |
| `infra/` | Storage backends, DB (sqlite/postgres/nats), caching, scheduler |
| `ingester/` | Dedicated ingester binary for HA mode |
| `service/search/datafusion/` | Query engine on Apache DataFusion with custom optimizers |
| `service/tantivy/` | Full-text inverted index using Tantivy (Puffin format) |

**Data flow**:
1. Data arrives via HTTP/gRPC (OTLP, Bulk, JSON, Loki, HEC, Prometheus remote write)
2. Pipelines process/enrich/transform at ingest time
3. Written to WAL, then flushed to in-memory tables
4. Compacted into Parquet files → pushed to object storage (S3/MinIO/GCS/Azure Blob)
5. Metadata in SQLite (single-node) or PostgreSQL + NATS (HA mode)
6. Queries fan out via Arrow Flight, execute via DataFusion on Parquet

---

## 2. Features

| Feature | Status |
|---------|--------|
| Logs | Full-text search, SQL queries, bulk/JSON/OTLP/Loki/HEC ingestion |
| Metrics | Prometheus remote write, OTLP metrics, SQL + PromQL query |
| Traces | OTEL native, flamegraphs, Gantt charts, service graphs |
| RUM | Real User Monitoring, session replay, error tracking |
| Dashboards | 19+ chart types (ECharts), drag-and-drop builder |
| Alerts | Threshold-based, anomaly detection, deduplication, grouping |
| Pipelines | Ingest-time processing: enrichment, redaction, normalization |
| Functions | VRL / JavaScript-based ingest and query-time functions |
| AI/Chat | AI-powered query assistance |
| MCP | Model Context Protocol endpoint (for AI agent integration) |

---

## 3. Storage

**Primary format**: Apache Parquet (columnar) — key to "140x lower storage cost" claim.

**Backends**:
- S3-compatible object storage (AWS S3, MinIO, GCS, Azure Blob)
- Local filesystem
- WAL for durability

**Metadata**: SQLite (single-node) / PostgreSQL (HA) / NATS JetStream KV (coordination)

**Indexing**: Tantivy full-text (Puffin format), bloom filters (trace_id), time-based partitioning

---

## 4. Ingestion Protocols

| Protocol | Support |
|----------|---------|
| OTLP (gRPC + HTTP) | Full (primary) |
| Elasticsearch Bulk API | Full |
| JSON (native) | Full |
| Grafana Loki push API | Full |
| Splunk HEC | Full |
| Prometheus Remote Write | Full |
| Kinesis Firehose | Supported |
| GCP Pub/Sub | Supported |
| Fluentd/Fluent Bit | Via JSON or OTLP |

---

## 5. Query Engine

Built on **Apache DataFusion** with custom optimizers, UDFs, distributed plans.

- SQL for logs and traces
- PromQL for metrics (full implementation)
- Full-text search via Tantivy
- Distributed execution via Arrow Flight
- Around-search (context), multi-stream search, async search jobs

---

## 6. Frontend

- Vue 3 + TypeScript + Quasar Framework
- Vite build, ECharts + echarts-gl, Leaflet (maps)
- Monaco Editor for SQL editing
- Vue Flow for pipeline DAG editor
- GridStack for dashboard layout
- RRWeb Player for session replay

---

## 7. Deployment

- **Single binary** — default mode (HTTP + gRPC + all services embedded)
- **Docker** — official images at public.ecr.aws
- **Kubernetes** — StatefulSets, Helm charts
- **HA mode** — separated ingester/querier/compactor/alerter/router nodes
- **Super Cluster (Enterprise)** — multi-region federation

---

## 8. Multi-Tenancy

- Organizations as primary tenant boundary
- All API paths org-scoped
- RBAC via OpenFGA-style fine-grained authorization (Enterprise)
- Service accounts with assume-role
- Rate limiting per tenant
- Storage partitioned by org ID

---

## 9. Key Gaps vs. Splunk/Datadog/Dynatrace

1. No APM agent (relies on OTEL SDKs)
2. No synthetic monitoring
3. No native infrastructure monitoring agent
4. No SIEM/security analytics
5. Limited ML/AI capabilities vs Davis AI or Watchdog
6. Enterprise features behind paywall (SSO, RBAC, audit, federation)
7. No mobile app monitoring
8. Smaller integration ecosystem
9. No built-in log parsing library (vs Splunkbase TAs)
10. No network monitoring

**Strengths over competitors**:
- 140x lower storage cost (Parquet + S3)
- Single binary deployment (2-minute setup)
- No vendor lock-in (AGPL, OTEL-native, SQL/PromQL)
- Self-hosted with full data control
- Rust performance

---

## RayOlly Architectural Lessons from OpenObserve

| OpenObserve Choice | RayOlly Decision | Rationale |
|-------------------|------------------|-----------|
| Rust backend | Python + Rust hot paths | Faster development velocity; Rust via PyO3 for critical paths |
| Vue 3 + Quasar | React 19 + Next.js 15 | Larger ecosystem, better SSR, more enterprise-grade |
| Parquet on S3 | ClickHouse (hot) + Parquet/S3 (cold) | ClickHouse adds fast query tier missing in O2 |
| DataFusion query | ClickHouse SQL + DuckDB federation | ClickHouse is more mature for OLAP workloads |
| Tantivy search | Tantivy (same) | Proven, fast, no JVM |
| NATS coordination | NATS JetStream (same) | Proven, lightweight |
| No AI agents | AI Agents-as-a-Service (core) | Primary differentiator |
| Basic anomaly detection | Full ML/AI engine | Compete with Davis AI, Watchdog |
| AGPL license | Open core (Apache 2.0 core + commercial) | More enterprise-friendly than AGPL |
