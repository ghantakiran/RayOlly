# PRD-00: RayOlly Platform Vision & Architecture

**Product**: RayOlly — AI-Native Observability Platform
**Version**: 1.0
**Date**: 2026-03-19
**Status**: Draft
**Author**: Platform Architecture Team
**Stakeholders**: Engineering, Product, SRE, Security, Executive Leadership

---

## 1. Executive Summary

RayOlly is an enterprise-grade, AI-native observability platform that unifies logs, metrics, traces, and events into a single, intelligent system. Unlike legacy platforms that bolt AI features onto existing architectures, RayOlly is built from the ground up with **AI Agents-as-a-Service** at its core — autonomous intelligent agents that detect, diagnose, and resolve issues before they impact users.

RayOlly competes directly with Splunk, Datadog, Dynatrace, and New Relic by offering:
- **10x cost efficiency** through intelligent data tiering and columnar storage
- **AI-first architecture** with autonomous agents, not just dashboards with ML alerts
- **Full OpenTelemetry native** support — no proprietary lock-in
- **Both SaaS and self-hosted** deployment with identical feature parity
- **Open-core model** — core platform is open source, enterprise features are commercial

---

## 2. Problem Statement

### 2.1 Market Problems

| Problem | Impact | Current Solutions' Gaps |
|---------|--------|----------------------|
| Observability cost explosion | Enterprises spend $500K-$50M/yr on observability | Datadog/Splunk charge per GB ingested — costs scale linearly |
| Tool sprawl | Avg enterprise uses 4-7 monitoring tools | Each vendor excels in one pillar, weak in others |
| Alert fatigue | 70% of alerts are noise | Rule-based alerting creates cascading false positives |
| Slow MTTR | Avg MTTR is 4+ hours for P1 incidents | Manual correlation across logs/metrics/traces |
| Talent shortage | Not enough SREs to cover 24/7 operations | Tools require deep expertise to configure and operate |
| Vendor lock-in | Proprietary agents and query languages | Migration costs are prohibitive |
| Data silos | Logs, metrics, traces in separate systems | No unified correlation or context switching |

### 2.2 Why Now

1. **OpenTelemetry maturity** — OTEL is now the industry standard, reducing agent lock-in
2. **LLM capabilities** — Foundation models enable natural language querying and autonomous agents
3. **Columnar storage advances** — ClickHouse, Arrow, Parquet make 10x cost reduction feasible
4. **Agent AI frameworks** — LangGraph, Claude Agent SDK enable production-grade autonomous agents
5. **Enterprise AI readiness** — Organizations are ready to deploy AI agents for infrastructure operations

---

## 3. Product Vision

> **"Every engineer has an AI SRE team that never sleeps, never misses an anomaly, and explains everything in plain English."**

### 3.1 Vision Pillars

```
┌─────────────────────────────────────────────────────────────────────┐
│                        RayOlly Platform                             │
│                                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │   Logs   │  │ Metrics  │  │  Traces  │  │  Events  │  PILLARS  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘           │
│       │              │              │              │                 │
│  ┌────▼──────────────▼──────────────▼──────────────▼─────┐         │
│  │              Unified Data Lake                         │         │
│  │         (Columnar + Object Storage)                    │         │
│  └────────────────────┬──────────────────────────────────┘         │
│                       │                                             │
│  ┌────────────────────▼──────────────────────────────────┐         │
│  │               AI/ML Engine                             │         │
│  │  Anomaly Detection │ Forecasting │ Pattern Mining      │         │
│  └────────────────────┬──────────────────────────────────┘         │
│                       │                                             │
│  ┌────────────────────▼──────────────────────────────────┐         │
│  │          AI Agents-as-a-Service (CORE)                 │  ◄──── │
│  │  RCA Agent │ Incident Agent │ Query Agent │ Custom     │  DIFF  │
│  └────────────────────┬──────────────────────────────────┘         │
│                       │                                             │
│  ┌────────────────────▼──────────────────────────────────┐         │
│  │           Unified Experience Layer                     │         │
│  │  Dashboards │ NL Chat │ Alerts │ API │ CLI             │         │
│  └───────────────────────────────────────────────────────┘         │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 Core Differentiators vs Competition

| Capability | RayOlly | Datadog | Splunk | Dynatrace | New Relic |
|-----------|---------|---------|--------|-----------|-----------|
| AI Agents (autonomous) | Core architecture | Limited (Bits AI) | Limited (AI Assistant) | Davis AI (rule-based) | Limited (NRAI) |
| Custom agent creation | Yes — Agent SDK | No | No | No | No |
| OpenTelemetry native | Full native | Partial (proprietary agent preferred) | Partial | Partial (OneAgent) | Good |
| Self-hosted option | Full feature parity | No | Yes (expensive) | Managed only | No |
| Cost model | Per-node flat rate | Per GB (expensive) | Per GB (very expensive) | Per host | Per GB |
| Natural language queries | Full conversational AI | Basic | Basic SPL assist | Limited | Basic |
| Open source core | Yes | No | No | No | No |
| Agent-as-a-Service marketplace | Yes | No | No | No | No |
| Unified storage | Single columnar lake | Separate per product | Separate indexes | Separate | Separate NRDB |

---

## 4. Target Users & Personas

### 4.1 Primary Personas

**P1: Site Reliability Engineer (SRE)**
- Needs: Rapid incident triage, automated root cause analysis, SLO tracking
- Pain: Alert fatigue, manual correlation, 3am pages for non-issues
- RayOlly value: AI agents handle first-response, auto-correlate signals, reduce noise by 90%

**P2: Platform Engineer**
- Needs: Infrastructure monitoring, capacity planning, deployment observability
- Pain: Tool sprawl, inconsistent instrumentation, costly scaling
- RayOlly value: Unified platform, auto-instrumentation agents, predictive capacity planning

**P3: Application Developer**
- Needs: Debug production issues, trace requests, understand dependencies
- Pain: Can't navigate complex observability tools, context-switching between tools
- RayOlly value: Natural language queries ("why is checkout slow?"), AI-guided debugging

**P4: Engineering Manager / VP Eng**
- Needs: System health overview, SLA compliance, cost optimization, team productivity
- Pain: No single pane of glass, observability costs out of control
- RayOlly value: Executive dashboards, AI-generated reports, 10x cost savings

**P5: DevOps / Cloud Architect**
- Needs: Cloud infrastructure monitoring, Kubernetes observability, multi-cloud visibility
- Pain: Each cloud has different monitoring, K8s observability is complex
- RayOlly value: Unified multi-cloud view, K8s-native monitoring, auto-discovery

**P6: Security / Compliance Officer**
- Needs: Audit logging, compliance reporting, security event monitoring
- Pain: Separate SIEM tools, compliance data spread across systems
- RayOlly value: Built-in compliance, unified audit trail, security analytics

---

## 5. High-Level Architecture

### 5.1 System Architecture

```
                            ┌─────────────────────────────┐
                            │     Client Applications      │
                            │  (OTEL SDK / RayOlly Agent)  │
                            └──────────┬──────────────────┘
                                       │
                    ┌──────────────────▼──────────────────┐
                    │        Ingestion Gateway             │
                    │  ┌─────┐ ┌─────┐ ┌─────┐ ┌──────┐  │
                    │  │OTLP │ │HTTP │ │gRPC │ │Syslog│  │
                    │  └──┬──┘ └──┬──┘ └──┬──┘ └──┬───┘  │
                    │     └───────┴───────┴───────┘       │
                    │              │                        │
                    │     ┌───────▼────────┐               │
                    │     │  Schema Engine  │               │
                    │     │  (Validate,     │               │
                    │     │   Enrich,       │               │
                    │     │   Transform)    │               │
                    │     └───────┬────────┘               │
                    └─────────────┼────────────────────────┘
                                  │
                    ┌─────────────▼────────────────────────┐
                    │        Stream Processor               │
                    │     (NATS JetStream / Kafka)          │
                    │  ┌────────┐ ┌────────┐ ┌──────────┐ │
                    │  │ Route  │ │Enrich  │ │ AI Pre-  │ │
                    │  │        │ │        │ │ Process  │ │
                    │  └────┬───┘ └───┬────┘ └────┬─────┘ │
                    └───────┼─────────┼───────────┼────────┘
                            │         │           │
              ┌─────────────▼─────────▼───────────▼──────────┐
              │              Storage Layer                     │
              │  ┌──────────────┐  ┌────────────────────┐    │
              │  │  ClickHouse   │  │  Object Storage    │    │
              │  │  (Hot/Warm)   │  │  (S3/MinIO - Cold) │    │
              │  │  - Logs Index │  │  - Parquet files   │    │
              │  │  - Metrics    │  │  - Long-term       │    │
              │  │  - Traces     │  │  - Compliance      │    │
              │  └──────┬───────┘  └────────┬───────────┘    │
              │         └────────┬───────────┘                │
              └──────────────────┼─────────────────────────────┘
                                 │
              ┌──────────────────▼─────────────────────────────┐
              │              Query Engine                        │
              │  ┌──────────┐ ┌───────────┐ ┌───────────────┐ │
              │  │ SQL Layer│ │ Full-Text │ │ Federation    │ │
              │  │          │ │ Search    │ │ (Cross-store) │ │
              │  └──────────┘ └───────────┘ └───────────────┘ │
              └──────────────────┬─────────────────────────────┘
                                 │
              ┌──────────────────▼─────────────────────────────┐
              │              AI/ML Engine                        │
              │  ┌───────────┐ ┌───────────┐ ┌──────────────┐ │
              │  │ Anomaly   │ │ Forecast  │ │ Pattern      │ │
              │  │ Detection │ │ Engine    │ │ Mining       │ │
              │  └───────────┘ └───────────┘ └──────────────┘ │
              └──────────────────┬─────────────────────────────┘
                                 │
              ┌──────────────────▼─────────────────────────────┐
              │         AI Agent Orchestrator                    │
              │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ │
              │  │  RCA   │ │Incident│ │ Query  │ │ Custom │ │
              │  │ Agent  │ │ Agent  │ │ Agent  │ │ Agents │ │
              │  └────────┘ └────────┘ └────────┘ └────────┘ │
              │  ┌──────────────────────────────────────────┐ │
              │  │          Agent Marketplace                │ │
              │  └──────────────────────────────────────────┘ │
              └──────────────────┬─────────────────────────────┘
                                 │
              ┌──────────────────▼─────────────────────────────┐
              │           Experience Layer                       │
              │  ┌──────────┐ ┌─────────┐ ┌──────┐ ┌───────┐ │
              │  │Dashboard │ │ NL Chat │ │ API  │ │  CLI  │ │
              │  │ (React)  │ │ (AI)    │ │(REST)│ │       │ │
              │  └──────────┘ └─────────┘ └──────┘ └───────┘ │
              └────────────────────────────────────────────────┘
```

### 5.2 Technology Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **API Gateway** | Python 3.12+ / FastAPI | Async-first, ASGI, excellent OpenAPI support, type safety |
| **Stream Processing** | NATS JetStream | Lightweight, high-throughput, built-in persistence, simpler than Kafka |
| **Hot Storage** | ClickHouse | Best-in-class columnar OLAP, 10-100x compression, SQL native |
| **Warm/Cold Storage** | Apache Parquet on S3/MinIO | Cost-effective, open format, query-in-place with DuckDB |
| **Search Engine** | Tantivy (Rust) via Python bindings | Blazing fast full-text search, no JVM overhead (unlike OpenSearch) |
| **Cache** | Redis Cluster / DragonflyDB | Query cache, session state, real-time aggregations |
| **AI/ML Runtime** | Python + ONNX Runtime + vLLM | Unified inference, GPU-optimized, model-agnostic |
| **Agent Framework** | Claude Agent SDK + LangGraph | Production-grade agent orchestration, tool use, reasoning |
| **LLM Provider** | Claude API (primary) + local models | Best reasoning for RCA, with local fallback for air-gapped |
| **Frontend** | React 19 + Next.js 15 + TypeScript | Server components, streaming SSR, best ecosystem |
| **Visualization** | Apache ECharts + D3.js | High-performance, 100K+ data points, rich chart types |
| **Query Editor** | Monaco Editor | VS Code-grade editing, syntax highlighting, autocomplete |
| **Real-time** | WebSocket + Server-Sent Events | Live tail, streaming dashboards, agent status |
| **Container Orchestration** | Kubernetes (Helm + Operator) | Industry standard, auto-scaling, self-healing |
| **CI/CD** | GitHub Actions + ArgoCD | GitOps deployment, automated testing |
| **Observability (self)** | OpenTelemetry | Dogfooding — RayOlly monitors itself |

### 5.3 Design Principles

1. **AI-First, Not AI-Bolted** — Every feature is designed assuming AI agents will interact with it programmatically
2. **OpenTelemetry Native** — OTEL is the primary data model, not an afterthought adapter
3. **Storage-Compute Separation** — Scale storage and compute independently
4. **Schema-on-Read** — Accept any data shape, apply schema at query time for flexibility
5. **Multi-Tenant by Default** — Every component is tenant-aware from day one
6. **API-First** — Every UI action maps to a public API; the UI is just one client
7. **Progressive Complexity** — Simple for developers, powerful for SREs, enterprise-grade for platform teams
8. **Cost-Aware Architecture** — Intelligent tiering, sampling, and aggregation to control costs
9. **Open Core** — Core platform is open source; enterprise features (SSO, RBAC, agents marketplace) are commercial

---

## 6. Feature Breakdown by PRD

| PRD | Module | Priority | Dependencies |
|-----|--------|----------|-------------|
| PRD-01 | Data Ingestion & OTEL Pipeline | P0 — Critical | None |
| PRD-02 | Storage Engine & Data Lifecycle | P0 — Critical | None |
| PRD-03 | Query Engine & Search | P0 — Critical | PRD-02 |
| PRD-04 | AI/ML Engine Core | P0 — Critical | PRD-02, PRD-03 |
| PRD-05 | AI Agents-as-a-Service | P0 — Critical | PRD-04 |
| PRD-06 | Logs Module | P0 — Critical | PRD-01, PRD-02, PRD-03 |
| PRD-07 | Metrics & Infrastructure Monitoring | P0 — Critical | PRD-01, PRD-02, PRD-03 |
| PRD-08 | Distributed Tracing & APM | P1 — High | PRD-01, PRD-02, PRD-03 |
| PRD-09 | Alerting & Incident Management | P1 — High | PRD-04, PRD-05 |
| PRD-10 | Dashboards & Visualization Frontend | P0 — Critical | PRD-03 |
| PRD-11 | Natural Language Interface | P1 — High | PRD-03, PRD-05 |
| PRD-12 | Multi-Tenancy, RBAC & Security | P0 — Critical | None |
| PRD-13 | Deployment & Infrastructure | P0 — Critical | None |
| PRD-14 | API Platform & Integrations | P1 — High | PRD-03 |

---

## 7. Phased Delivery Roadmap

### Phase 1: Foundation (Months 1-4)
**Goal**: Core data pipeline working end-to-end

- [ ] PRD-01: OTEL ingestion pipeline (OTLP/gRPC, HTTP)
- [ ] PRD-02: ClickHouse storage with S3 tiering
- [ ] PRD-03: SQL query engine + basic full-text search
- [ ] PRD-12: Multi-tenancy foundation + basic RBAC
- [ ] PRD-13: Kubernetes deployment (Helm charts)
- [ ] PRD-10: Basic dashboard UI (React shell + chart widgets)

**Milestone**: Ingest logs/metrics via OTEL, query via SQL, view in basic dashboards

### Phase 2: Observability Pillars (Months 5-8)
**Goal**: Feature parity with open-source observability tools

- [ ] PRD-06: Full log management (search, live tail, patterns)
- [ ] PRD-07: Metrics module (PromQL compat, host maps, infra monitoring)
- [ ] PRD-08: Distributed tracing (service maps, flame graphs, latency analysis)
- [ ] PRD-09: Alerting engine (rule-based + threshold)
- [ ] PRD-14: REST API v1 + CLI tool

**Milestone**: Replace Grafana+Loki+Tempo stack for early adopters

### Phase 3: AI Intelligence (Months 9-12)
**Goal**: AI-powered features that differentiate from competition

- [ ] PRD-04: AI/ML engine (anomaly detection, forecasting, pattern mining)
- [ ] PRD-05: Agent orchestrator + built-in agents (RCA, Incident, Query)
- [ ] PRD-11: Natural language interface (conversational querying)
- [ ] PRD-09: AI-powered alerting (predictive, correlation, noise reduction)

**Milestone**: AI agents autonomously detect and diagnose incidents

### Phase 4: Enterprise & Scale (Months 13-18)
**Goal**: Enterprise-ready for Fortune 500 deployment

- [ ] PRD-12: SSO/SAML/OIDC, advanced RBAC, audit logging
- [ ] PRD-13: Multi-region, disaster recovery, SaaS infrastructure
- [ ] PRD-05: Agent marketplace + custom agent SDK
- [ ] PRD-14: Terraform provider, GraphQL API, SDK libraries
- [ ] Compliance certifications: SOC 2 Type II, HIPAA, GDPR

**Milestone**: Enterprise GA — ready to compete with Datadog/Splunk

---

## 8. Success Metrics

### 8.1 Product Metrics

| Metric | Target (GA) | Target (12mo post-GA) |
|--------|------------|----------------------|
| Ingestion throughput | 1M events/sec/node | 10M events/sec/cluster |
| Query latency (p99) | < 2s for 1TB dataset | < 5s for 100TB dataset |
| Storage cost vs Datadog | 70% lower | 80% lower |
| MTTR improvement | 50% reduction | 80% reduction with AI agents |
| Alert noise reduction | 60% fewer false positives | 90% with AI correlation |
| Agent autonomous resolution | 10% of P3/P4 incidents | 40% of P3/P4 incidents |
| NL query accuracy | 80% correct SQL generation | 95% correct SQL generation |

### 8.2 Business Metrics

| Metric | Year 1 | Year 2 | Year 3 |
|--------|--------|--------|--------|
| Open source GitHub stars | 5K | 25K | 50K |
| Self-hosted deployments | 500 | 5,000 | 20,000 |
| SaaS customers | 50 | 500 | 2,000 |
| Enterprise contracts | 5 | 50 | 200 |
| ARR | $1M | $15M | $75M |

---

## 9. Competitive Moats

1. **AI Agents-as-a-Service** — No competitor offers autonomous agents with a marketplace for custom agents. This is the primary differentiator.
2. **Open Core + Open Standards** — OTEL native + open source core eliminates lock-in fear, the #1 enterprise objection to Datadog.
3. **Cost Structure** — Columnar storage + intelligent tiering delivers 10x cost efficiency. Flat per-node pricing eliminates bill shock.
4. **Developer Experience** — Natural language queries + AI debugging assistant makes observability accessible to all engineers, not just SREs.
5. **Self-Hosted Parity** — Unlike Datadog (SaaS only) or Splunk (expensive self-hosted), RayOlly offers identical features in both models.

---

## 10. Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| ClickHouse scalability limits | Medium | High | Abstract storage layer; evaluate Apache Doris as fallback |
| LLM cost for agent operations | High | Medium | Local model support (Llama, Mistral); smart caching; prompt optimization |
| Open source community building | Medium | High | DevRel investment; integrations with popular tools; contributor program |
| Enterprise sales cycle length | High | Medium | Open source land-and-expand; free tier; POC program |
| AI agent reliability/hallucination | Medium | High | Human-in-the-loop for critical actions; confidence scoring; guardrails |
| Competitor response (Datadog AI) | High | Medium | First-mover on agent marketplace; deeper OTEL integration; cost advantage |

---

## 11. Non-Functional Requirements

| Requirement | Target |
|-------------|--------|
| Availability | 99.95% (SaaS), 99.9% (self-hosted) |
| Data durability | 99.999999999% (11 nines) |
| Ingestion latency | < 5s end-to-end (ingest to queryable) |
| Horizontal scalability | Linear scale to 100+ nodes |
| Data retention | Configurable: 1 day to 10 years |
| Compliance | SOC 2 Type II, HIPAA, GDPR, FedRAMP (roadmap) |
| Encryption | AES-256 at rest, TLS 1.3 in transit |
| Multi-region | Active-active with < 1s replication lag |
| Backup/Recovery | RPO < 1 min, RTO < 15 min |

---

## 12. Open Questions

1. **Pricing model details**: Flat per-node vs hybrid (base + usage)?
2. **Open source license**: Apache 2.0 vs AGPL vs BSL (Business Source License)?
3. **Initial cloud provider**: AWS-first or multi-cloud from day one?
4. **LLM strategy**: Claude-exclusive partnership or multi-model from start?
5. **Agent marketplace revenue model**: Revenue share with agent creators?
6. **Compliance priority order**: SOC 2 first, then HIPAA, then GDPR?

---

*This is the master PRD. All subsequent PRDs (01-14) reference this document for vision, architecture, and technology stack decisions.*
