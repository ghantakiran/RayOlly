# PRD-05: AI Agents-as-a-Service Platform

**Product**: RayOlly — AI-Native Observability Platform
**Version**: 1.0
**Date**: 2026-03-19
**Status**: Draft
**Author**: Platform Architecture Team
**Priority**: P0 — Core Differentiator
**Stakeholders**: Engineering, Product, SRE, Security, AI/ML, Executive Leadership

---

## Table of Contents

1. [Overview](#1-overview)
2. [Vision](#2-vision)
3. [Goals & Non-Goals](#3-goals--non-goals)
4. [Agent Architecture](#4-agent-architecture)
5. [Built-in Agents](#5-built-in-agents-ship-with-platform)
6. [Agent SDK](#6-agent-sdk-for-custom-agents)
7. [Agent Marketplace](#7-agent-marketplace)
8. [Agent Orchestration](#8-agent-orchestration)
9. [Agent Memory & Knowledge](#9-agent-memory--knowledge)
10. [Agent Security & Governance](#10-agent-security--governance)
11. [Agent Observability](#11-agent-observability-observing-the-observers)
12. [LLM Integration](#12-llm-integration)
13. [Human-Agent Interaction](#13-human-agent-interaction)
14. [Multi-Tenancy](#14-multi-tenancy)
15. [Technology Stack](#15-technology-stack)
16. [Performance Requirements](#16-performance-requirements)
17. [Example Agent Workflows](#17-example-agent-workflows)
18. [Success Metrics](#18-success-metrics)
19. [Dependencies and Risks](#19-dependencies-and-risks)

---

## 1. Overview

### 1.1 Why This PRD Matters

This document defines the **single most important capability** in the RayOlly platform. AI Agents-as-a-Service is not a feature — it is the architectural foundation that separates RayOlly from every competing observability product on the market.

Every competitor — Datadog, Splunk, Dynatrace, New Relic — has converged on the same model: **dashboards with bolted-on ML**. They offer anomaly detection that generates alerts, natural language interfaces that translate questions into queries, and copilots that summarize log streams. These are incremental improvements to fundamentally passive tools. The operator still carries the cognitive load. The operator still gets paged at 3 AM. The operator still spends hours correlating across services.

RayOlly rejects this model entirely.

**RayOlly ships autonomous AI agents that detect, diagnose, and resolve observability issues — with or without human involvement.** These agents are not chatbots. They are not copilots. They are autonomous actors with tools, memory, judgment, and the ability to take action in production environments under governed constraints.

### 1.2 Competitive Landscape

| Capability | Datadog | Splunk | Dynatrace | New Relic | **RayOlly** |
|---|---|---|---|---|---|
| Anomaly detection | ML-based alerts | MLTK add-on | Davis AI | Applied Intelligence | **Agent-driven investigation** |
| Natural language | Bits AI (chat) | SPL Assistant | DQL natural lang | NRQL Grok | **Query Agent with context** |
| Root cause analysis | Manual correlation | Manual correlation | Davis topology | Lookout | **Autonomous RCA Agent** |
| Incident management | Integration-based | SOAR playbooks | Problem cards | Incident Intelligence | **Incident Commander Agent** |
| Auto-remediation | None | SOAR limited | Limited | None | **Runbook Execution Agent** |
| Custom automation | Monitors + webhooks | Playbooks | Extensions | Workflows | **Agent SDK + Marketplace** |
| Agent marketplace | None | Splunkbase (apps) | Hub (extensions) | Instant Observability | **Full Agent Marketplace** |
| Autonomous operation | None | None | None | None | **Multi-agent collaboration** |

### 1.3 What "Agents-as-a-Service" Means

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    THE OBSERVABILITY EVOLUTION                               │
│                                                                             │
│   Gen 1: Dashboards          "Here's your data — you figure it out"        │
│   Gen 2: Alerts              "Something looks wrong — go check"            │
│   Gen 3: ML Anomaly          "This metric is unusual — maybe investigate"  │
│   Gen 4: Copilots            "I can help you query if you ask me"          │
│   Gen 5: RayOlly Agents      "I detected the issue, found the root cause, │
│                                ran the runbook, and here's the postmortem"  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

RayOlly agents are **Gen 5** — fully autonomous actors that operate within governed boundaries. They combine:

- **Perception**: Real-time awareness of logs, metrics, traces, and events
- **Reasoning**: LLM-powered analysis with chain-of-thought investigation
- **Memory**: Learned patterns from past incidents, team preferences, and system topology
- **Tools**: Ability to query data, run commands, create alerts, send notifications, and execute runbooks
- **Collaboration**: Multi-agent workflows where specialized agents coordinate on complex problems
- **Governance**: Human-in-the-loop checkpoints, permission models, and audit trails

---

## 2. Vision

### 2.1 North Star

> **"Every organization has a team of AI SREs that never sleep, never miss an anomaly, and resolve issues before humans even notice."**

The AI Agents platform transforms observability from a reactive, human-dependent activity into a proactive, agent-driven operation. When an anomaly occurs at 3 AM:

- **Today (competitors)**: PagerDuty alert → Engineer wakes up → Opens 4 dashboards → Spends 45 minutes correlating → Identifies root cause → Runs manual remediation → Writes postmortem next day
- **RayOlly**: Anomaly detected → RCA Agent investigates automatically → Incident Commander creates timeline → Runbook Agent executes remediation → Engineer wakes up to a resolved incident with a complete postmortem

### 2.2 Agent Design Philosophy

Agents are **not chatbots**. This distinction is critical:

| Property | Chatbot / Copilot | RayOlly Agent |
|---|---|---|
| Activation | User-initiated | Autonomous (event-driven, scheduled, or on-demand) |
| Scope | Single question/answer | Multi-step investigation with branching logic |
| Memory | Stateless or session-only | Persistent long-term memory per tenant |
| Tools | Query translation only | Full toolkit: query, alert, execute, notify, delegate |
| Collaboration | None | Multi-agent workflows with delegation |
| Judgment | Predefined responses | Reasoning engine with confidence scoring |
| Actions | Read-only | Read + write (with governance) |
| Learning | None | Improves from feedback and outcomes |

### 2.3 Architectural Inspiration

The RayOlly agent system draws from proven AI agent architectures:

- **Claude Agent SDK**: Tool-use patterns, structured outputs, multi-turn reasoning
- **LangGraph**: Stateful, graph-based agent workflows with checkpoints
- **ReAct pattern**: Reasoning + Acting in an interleaved loop
- **Plan-and-Execute**: Complex investigations broken into plannable sub-tasks
- **Multi-Agent Debate**: Critical findings validated by independent agent analysis

### 2.4 Design Principles

1. **Agents are first-class citizens** — not an afterthought bolted onto dashboards
2. **Autonomy with guardrails** — agents act independently within governed boundaries
3. **Transparency always** — every agent decision is explainable and auditable
4. **Graceful degradation** — agents fall back to simpler methods when LLMs are unavailable
5. **Cost-aware execution** — agents optimize for value delivered per token spent
6. **Tenant isolation is sacred** — agents never cross tenant boundaries
7. **Human override is instant** — any agent action can be stopped or reversed immediately

---

## 3. Goals & Non-Goals

### 3.1 Goals

| ID | Goal | Success Criteria | Priority |
|----|------|-----------------|----------|
| G1 | Ship 8 production-ready built-in agents at launch | All 8 agents passing integration tests with >90% accuracy on benchmark scenarios | P0 |
| G2 | Reduce MTTR by 80% for incidents handled by agents | Measured across 100+ incidents in beta tenants | P0 |
| G3 | Agent SDK enables custom agent development in <1 day | Developer survey: 80% can build and deploy a custom agent within 8 hours | P0 |
| G4 | Agent Marketplace launches with 20+ community agents | Marketplace live with verified agents across 5+ categories | P1 |
| G5 | 95% of agent actions produce correct results | Measured by human review of agent decisions in production | P0 |
| G6 | Agent platform handles 1000+ concurrent agent executions per cluster | Load test validated at 1000 concurrent agents | P1 |
| G7 | Zero data leakage between tenants in multi-tenant agent execution | Security audit and penetration testing pass | P0 |
| G8 | Agent observability provides full visibility into agent behavior | Agent traces, metrics, and cost tracking operational | P0 |
| G9 | Enterprise customers can run agents without external LLM calls | Local model support validated for all built-in agents | P1 |
| G10 | Agent actions have full audit trail for compliance | SOC 2 audit requirements satisfied | P0 |

### 3.2 Non-Goals

| ID | Non-Goal | Rationale |
|----|----------|-----------|
| NG1 | General-purpose AI assistant (answering non-observability questions) | Agents are domain-specific; general chat is not our value proposition |
| NG2 | Replacing human judgment for business-critical production changes | Agents recommend and execute runbooks, but humans approve destructive actions |
| NG3 | Training custom foundation models | We integrate with best-in-class LLMs, not train our own |
| NG4 | Real-time voice interaction with agents | Text-based interaction is the initial modality |
| NG5 | Agent-to-agent communication across tenants | Strict tenant isolation; agents never share cross-tenant context |
| NG6 | Supporting non-Python agent development | Python-first SDK; other languages may come in v2 |
| NG7 | Autonomous infrastructure provisioning | Agents observe and remediate, they don't provision new infrastructure |

---

## 4. Agent Architecture

### 4.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         RayOlly AI Agent Platform                           │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                        INTERACTION LAYER                             │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐    │   │
│  │  │ Chat UI  │  │ Slack/   │  │ REST API │  │ Event Triggers   │    │   │
│  │  │          │  │ Teams    │  │          │  │ (anomaly, alert) │    │   │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────────┬─────────┘    │   │
│  └───────┼──────────────┼──────────────┼────────────────┼──────────────┘   │
│          │              │              │                │                    │
│  ┌───────▼──────────────▼──────────────▼────────────────▼──────────────┐   │
│  │                     AGENT GATEWAY                                    │   │
│  │  ┌─────────────┐ ┌──────────────┐ ┌──────────────┐ ┌────────────┐  │   │
│  │  │ Auth &      │ │ Rate         │ │ Request      │ │ Tenant     │  │   │
│  │  │ AuthZ       │ │ Limiter      │ │ Router       │ │ Resolver   │  │   │
│  │  └─────────────┘ └──────────────┘ └──────────────┘ └────────────┘  │   │
│  └────────────────────────────┬────────────────────────────────────────┘   │
│                               │                                             │
│  ┌────────────────────────────▼────────────────────────────────────────┐   │
│  │                    ORCHESTRATION LAYER                               │   │
│  │                                                                      │   │
│  │  ┌───────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │   │
│  │  │ Agent         │  │ Workflow     │  │ Priority & Resource      │  │   │
│  │  │ Scheduler     │  │ Engine       │  │ Manager                  │  │   │
│  │  └───────┬───────┘  └──────┬───────┘  └──────────┬───────────────┘  │   │
│  │          │                 │                      │                   │   │
│  │  ┌───────▼─────────────────▼──────────────────────▼───────────────┐  │   │
│  │  │                    AGENT TASK QUEUE                             │  │   │
│  │  │              (NATS JetStream — ordered, durable)               │  │   │
│  │  └────────────────────────────┬───────────────────────────────────┘  │   │
│  └───────────────────────────────┼──────────────────────────────────────┘   │
│                                  │                                           │
│  ┌───────────────────────────────▼──────────────────────────────────────┐   │
│  │                      AGENT RUNTIME LAYER                             │   │
│  │                                                                      │   │
│  │  ┌───────────────────────────────────────────────────────────────┐   │   │
│  │  │  Agent Execution Sandbox (Container per execution)            │   │   │
│  │  │                                                               │   │   │
│  │  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │   │   │
│  │  │  │ Reasoning │  │ Tool     │  │ Memory   │  │ Output   │    │   │   │
│  │  │  │ Engine   │  │ Executor │  │ Manager  │  │ Handler  │    │   │   │
│  │  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │   │   │
│  │  │                                                               │   │   │
│  │  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │   │   │
│  │  │  │ Planning │  │ State    │  │ Checkpoint│  │ Security │    │   │   │
│  │  │  │ Module   │  │ Machine  │  │ Manager  │  │ Monitor  │    │   │   │
│  │  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │   │   │
│  │  └───────────────────────────────────────────────────────────────┘   │   │
│  │                                                                      │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐            │   │
│  │  │ RCA      │  │ Incident │  │ Query    │  │ Anomaly  │   ...      │   │
│  │  │ Agent    │  │ Cmdr     │  │ Agent    │  │ Invstgtr │            │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘            │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                  │                                           │
│  ┌───────────────────────────────▼──────────────────────────────────────┐   │
│  │                        TOOL LAYER                                    │   │
│  │                                                                      │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │   │
│  │  │ Data     │  │ Alert    │  │ Runbook  │  │ Notifi-  │           │   │
│  │  │ Query    │  │ Manager  │  │ Executor │  │ cation   │           │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘           │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │   │
│  │  │ K8s API  │  │ Cloud    │  │ CI/CD    │  │ Incident │           │   │
│  │  │ Client   │  │ Provider │  │ Pipeline │  │ Manager  │           │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘           │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                  │                                           │
│  ┌───────────────────────────────▼──────────────────────────────────────┐   │
│  │                       DATA & MEMORY LAYER                            │   │
│  │                                                                      │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐   │   │
│  │  │ RayOlly      │  │ Knowledge    │  │ Agent State Store        │   │   │
│  │  │ Data Lake    │  │ Store        │  │ (PostgreSQL)             │   │   │
│  │  │ (logs,       │  │ (pgvector)   │  │                          │   │   │
│  │  │  metrics,    │  │              │  │ Session Memory           │   │   │
│  │  │  traces)     │  │              │  │ (Redis)                  │   │   │
│  │  └──────────────┘  └──────────────┘  └──────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                  │                                           │
│  ┌───────────────────────────────▼──────────────────────────────────────┐   │
│  │                         LLM LAYER                                    │   │
│  │                                                                      │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐   │   │
│  │  │ Claude API   │  │ Local Models │  │ Prompt Manager           │   │   │
│  │  │ (Primary)    │  │ (vLLM)       │  │ + Cache                  │   │   │
│  │  └──────────────┘  └──────────────┘  └──────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Agent Runtime Environment

Each agent executes within an isolated runtime that provides:

**Execution Container**
- Lightweight container (gVisor sandbox) per agent execution
- CPU/memory limits enforced per tenant configuration
- Network policies restrict access to approved endpoints only
- Filesystem is ephemeral — no persistent local state
- Container destroyed after execution completes or timeout

**Runtime Components**

```
┌─────────────────────────────────────────────────────────────┐
│                  Agent Execution Container                    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                  Agent Process                       │    │
│  │                                                      │    │
│  │  ┌────────────┐    ┌─────────────────────────────┐  │    │
│  │  │  Agent     │    │  Reasoning Loop              │  │    │
│  │  │  Config    │───▶│                              │  │    │
│  │  │  (YAML)   │    │  1. Perceive (read context)  │  │    │
│  │  └────────────┘    │  2. Think   (LLM reasoning) │  │    │
│  │                     │  3. Plan    (choose action)  │  │    │
│  │  ┌────────────┐    │  4. Act     (execute tool)   │  │    │
│  │  │  Agent     │    │  5. Observe (check result)   │  │    │
│  │  │  Code      │───▶│  6. Repeat or Conclude       │  │    │
│  │  │  (Python)  │    │                              │  │    │
│  │  └────────────┘    └───────────┬─────────────────┘  │    │
│  │                                │                      │    │
│  │  ┌────────────┐  ┌────────────▼────────────┐        │    │
│  │  │  Tool      │  │  State Machine          │        │    │
│  │  │  Registry  │  │  (tracks agent phase)   │        │    │
│  │  └────────────┘  └─────────────────────────┘        │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐               │
│  │ Memory    │  │ Tool      │  │ Security  │               │
│  │ Sidecar   │  │ Proxy     │  │ Monitor   │               │
│  └───────────┘  └───────────┘  └───────────┘               │
└─────────────────────────────────────────────────────────────┘
```

### 4.3 Agent Lifecycle

```
                    ┌───────────┐
                    │  CREATED  │  Agent definition registered
                    └─────┬─────┘
                          │
                    ┌─────▼─────┐
                    │ VALIDATED │  Config, tools, permissions verified
                    └─────┬─────┘
                          │
                    ┌─────▼─────┐
                    │ DEPLOYED  │  Agent available for execution
                    └─────┬─────┘
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ TRIGGERED│ │ SCHEDULED│ │ INVOKED  │
        │ (event)  │ │ (cron)   │ │ (manual) │
        └────┬─────┘ └────┬─────┘ └────┬─────┘
             │             │             │
             └─────────────┼─────────────┘
                           │
                    ┌──────▼──────┐
                    │  QUEUED     │  In task queue, awaiting resources
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  RUNNING    │  Agent executing in sandbox
                    └──────┬──────┘
                           │
              ┌────────────┼────────────────┐
              ▼            ▼                ▼
        ┌──────────┐ ┌──────────────┐ ┌──────────┐
        │COMPLETED │ │ WAITING_     │ │ FAILED   │
        │          │ │ APPROVAL     │ │          │
        └──────────┘ └──────┬───────┘ └──────────┘
                            │
                     ┌──────▼──────┐
                     │  APPROVED / │
                     │  REJECTED   │
                     └──────┬──────┘
                            │
                     ┌──────▼──────┐
                     │  COMPLETED  │
                     └─────────────┘
```

**Lifecycle States**

| State | Description | Duration |
|---|---|---|
| `CREATED` | Agent definition registered in system | Until validation |
| `VALIDATED` | Configuration and permissions verified | Instant |
| `DEPLOYED` | Agent active and ready for execution | Indefinite |
| `TRIGGERED` | Event fired that matches agent trigger | Instant |
| `QUEUED` | Waiting for execution resources | < 5s target |
| `RUNNING` | Actively executing in sandbox | Up to configured timeout |
| `WAITING_APPROVAL` | Blocked on human approval for action | Up to approval timeout |
| `COMPLETED` | Execution finished successfully | Terminal |
| `FAILED` | Execution failed with error | Terminal |
| `RETIRED` | Agent deactivated, no longer triggerable | Terminal |

### 4.4 Agent Execution Model

Agents support three execution modes:

**Event-Driven**
```yaml
trigger:
  type: event
  source: anomaly_detector
  conditions:
    - field: severity
      operator: gte
      value: high
    - field: service
      operator: in
      value: ["api-gateway", "payment-service", "auth-service"]
  debounce: 60s  # Don't re-trigger within 60s for same anomaly
```

**Scheduled**
```yaml
trigger:
  type: schedule
  cron: "0 9 * * 1"  # Every Monday at 9 AM
  timezone: "America/New_York"
```

**On-Demand**
```yaml
trigger:
  type: on_demand
  channels:
    - chat
    - api
    - slack_command
```

### 4.5 Tool System

Agents interact with the platform and external systems through a typed tool interface. Every tool invocation is logged, permission-checked, and rate-limited.

**Core Tool Categories**

```
┌─────────────────────────────────────────────────────────────────┐
│                     AGENT TOOL REGISTRY                         │
│                                                                 │
│  DATA TOOLS              ACTION TOOLS           COMMS TOOLS     │
│  ┌─────────────────┐     ┌─────────────────┐    ┌────────────┐ │
│  │ query_logs      │     │ create_alert    │    │ send_slack │ │
│  │ query_metrics   │     │ update_alert    │    │ send_teams │ │
│  │ query_traces    │     │ create_incident │    │ send_email │ │
│  │ run_rayql       │     │ update_incident │    │ page_user  │ │
│  │ get_service_map │     │ execute_runbook │    │ post_note  │ │
│  │ get_topology    │     │ scale_service   │    └────────────┘ │
│  │ get_deployments │     │ restart_pod     │                    │
│  │ get_change_log  │     │ rollback_deploy │    AGENT TOOLS     │
│  └─────────────────┘     └─────────────────┘    ┌────────────┐ │
│                                                  │ delegate   │ │
│  KNOWLEDGE TOOLS         INFRA TOOLS             │ spawn_sub  │ │
│  ┌─────────────────┐     ┌─────────────────┐    │ wait_for   │ │
│  │ search_kb       │     │ k8s_get         │    │ report     │ │
│  │ read_runbook    │     │ k8s_describe    │    └────────────┘ │
│  │ get_past_rca    │     │ aws_describe    │                    │
│  │ get_slo_config  │     │ gcp_describe    │                    │
│  │ get_team_info   │     │ azure_describe  │                    │
│  └─────────────────┘     └─────────────────┘                    │
└─────────────────────────────────────────────────────────────────┘
```

**Tool Definition Interface**

```python
from rayolly.agents.tools import Tool, ToolResult, ToolPermission

class QueryLogsTool(Tool):
    """Query the RayOlly log store."""

    name = "query_logs"
    description = "Search and retrieve log entries matching specified criteria"
    permission = ToolPermission.READ_DATA

    class Input(Tool.InputSchema):
        query: str          # RayQL query or natural language
        time_range: str     # e.g., "last 1h", "2026-03-19T00:00:00Z/2026-03-19T01:00:00Z"
        limit: int = 100   # Max results
        service: str | None = None  # Filter to specific service
        severity: str | None = None # Filter to severity level

    class Output(Tool.OutputSchema):
        logs: list[dict]    # Matching log entries
        total_count: int    # Total matches (before limit)
        query_time_ms: int  # Query execution time
        rayql_used: str     # The actual RayQL executed

    async def execute(self, input: Input, context: AgentContext) -> ToolResult:
        # Enforce tenant scoping — agent can ONLY see its tenant's data
        scoped_query = self._apply_tenant_scope(input.query, context.tenant_id)

        result = await context.data_client.query_logs(
            query=scoped_query,
            time_range=input.time_range,
            limit=input.limit,
        )

        return ToolResult(
            success=True,
            output=self.Output(
                logs=result.entries,
                total_count=result.total,
                query_time_ms=result.duration_ms,
                rayql_used=scoped_query,
            ),
        )
```

**Tool Permission Levels**

| Level | Description | Examples | Approval Required |
|---|---|---|---|
| `READ_DATA` | Read observability data | query_logs, query_metrics, get_traces | No |
| `READ_CONFIG` | Read system configuration | get_slo_config, get_alert_rules | No |
| `WRITE_CONFIG` | Modify configuration | create_alert, update_slo | Per-tenant setting |
| `WRITE_INCIDENT` | Create/update incidents | create_incident, update_timeline | No |
| `SEND_NOTIFICATION` | Send external notifications | send_slack, page_user | Per-tenant setting |
| `EXECUTE_RUNBOOK` | Execute operational runbooks | execute_runbook, restart_pod | Yes (default) |
| `INFRASTRUCTURE` | Modify infrastructure state | scale_service, rollback_deploy | Yes (always) |

### 4.6 Memory System

```
┌─────────────────────────────────────────────────────────────────┐
│                     AGENT MEMORY ARCHITECTURE                    │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ WORKING MEMORY (per execution)                           │   │
│  │ Redis — TTL: execution lifetime                          │   │
│  │                                                          │   │
│  │ • Current investigation context                          │   │
│  │ • Tool call history for this execution                   │   │
│  │ • Intermediate findings and hypotheses                   │   │
│  │ • Conversation history (if interactive session)          │   │
│  └────────────────────────┬─────────────────────────────────┘   │
│                           │                                      │
│  ┌────────────────────────▼─────────────────────────────────┐   │
│  │ EPISODIC MEMORY (per tenant)                             │   │
│  │ PostgreSQL — TTL: configurable (default 90 days)         │   │
│  │                                                          │   │
│  │ • Past investigation summaries                           │   │
│  │ • Resolved incidents and root causes                     │   │
│  │ • Agent decisions and their outcomes                     │   │
│  │ • User feedback on agent actions                         │   │
│  └────────────────────────┬─────────────────────────────────┘   │
│                           │                                      │
│  ┌────────────────────────▼─────────────────────────────────┐   │
│  │ SEMANTIC MEMORY (per tenant)                             │   │
│  │ PostgreSQL + pgvector — persistent                       │   │
│  │                                                          │   │
│  │ • Service topology and dependencies (knowledge graph)    │   │
│  │ • Team ownership and escalation paths                    │   │
│  │ • Runbook library (embedded for retrieval)               │   │
│  │ • Architecture documentation (embedded)                  │   │
│  │ • Common failure patterns and resolutions                │   │
│  │ • SLO definitions and thresholds                         │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 4.7 Planning and Reasoning Engine

The reasoning engine implements a **ReAct + Plan-and-Execute hybrid** approach:

```
┌─────────────────────────────────────────────────────┐
│              REASONING LOOP                          │
│                                                     │
│  ┌──────────┐                                       │
│  │  INPUT   │  Trigger event, user query, or        │
│  │          │  scheduled task                        │
│  └────┬─────┘                                       │
│       │                                             │
│  ┌────▼─────┐                                       │
│  │  PLAN    │  Break problem into sub-tasks          │
│  │          │  Identify tools and data needed        │
│  └────┬─────┘                                       │
│       │                                             │
│  ┌────▼─────────────────────────────────────────┐   │
│  │  EXECUTE LOOP (per sub-task)                 │   │
│  │                                               │   │
│  │  ┌─────────┐   ┌─────────┐   ┌─────────┐    │   │
│  │  │ REASON  │──▶│  ACT    │──▶│ OBSERVE │──┐ │   │
│  │  │ (think) │   │ (tool)  │   │ (result)│  │ │   │
│  │  └─────────┘   └─────────┘   └─────────┘  │ │   │
│  │       ▲                                    │ │   │
│  │       └────────────────────────────────────┘ │   │
│  │                                               │   │
│  │  Loop until sub-task resolved or max          │   │
│  │  iterations reached                           │   │
│  └────┬─────────────────────────────────────────┘   │
│       │                                             │
│  ┌────▼─────┐                                       │
│  │ SYNTHESIZE│  Combine findings from all sub-tasks │
│  │           │  Generate confidence scores           │
│  └────┬──────┘                                       │
│       │                                             │
│  ┌────▼─────┐                                       │
│  │  OUTPUT  │  Structured report, actions taken,     │
│  │          │  recommendations                       │
│  └──────────┘                                       │
└─────────────────────────────────────────────────────┘
```

**Reasoning Constraints**

| Parameter | Default | Configurable |
|---|---|---|
| Max reasoning iterations per sub-task | 10 | Yes |
| Max total tool calls per execution | 50 | Yes |
| Max LLM tokens per execution | 100,000 | Yes (per tenant) |
| Max execution wall time | 10 minutes | Yes |
| Confidence threshold for autonomous action | 0.85 | Yes |
| Max concurrent sub-tasks | 5 | Yes |

### 4.8 Multi-Agent Collaboration

Agents can delegate tasks to other agents, enabling complex multi-step workflows:

```
┌──────────────────────────────────────────────────────────────────┐
│              MULTI-AGENT COLLABORATION MODEL                      │
│                                                                  │
│  ┌────────────────────┐                                          │
│  │  Incident Commander│  (Orchestrating Agent)                   │
│  │  Agent             │                                          │
│  └──────┬─────────────┘                                          │
│         │                                                        │
│         ├──── delegate("rca_agent", {anomaly_id: "xyz"})         │
│         │     ┌──────────────┐                                   │
│         │     │  RCA Agent   │──▶ Returns: RCA report            │
│         │     └──────────────┘                                   │
│         │                                                        │
│         ├──── delegate("slo_guardian", {service: "api-gw"})      │
│         │     ┌──────────────┐                                   │
│         │     │ SLO Guardian │──▶ Returns: SLO impact assessment │
│         │     └──────────────┘                                   │
│         │                                                        │
│         ├──── delegate("runbook_agent", {runbook: "rollback"})   │
│         │     ┌──────────────┐                                   │
│         │     │ Runbook Agent│──▶ Returns: Execution result      │
│         │     └──────────────┘   (may require human approval)    │
│         │                                                        │
│         └──── synthesize_and_report()                            │
│               Final incident report with timeline                │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**Delegation Protocol**

```python
class DelegationRequest:
    target_agent: str          # Agent type to invoke
    task: str                  # Natural language task description
    context: dict              # Shared context from parent agent
    priority: Priority         # CRITICAL, HIGH, NORMAL, LOW
    timeout: timedelta         # Max wait time for result
    required_confidence: float # Min confidence for accepting result

class DelegationResult:
    status: str                # "completed", "failed", "timeout"
    result: dict               # Structured output from child agent
    confidence: float          # Agent's confidence in result
    reasoning_trace: list[str] # Summary of reasoning steps
    tools_used: list[str]      # Tools invoked during execution
    token_usage: TokenUsage    # LLM tokens consumed
```

### 4.9 Human-in-the-Loop Checkpoints

Certain actions require human approval before proceeding:

```
Agent decides to execute action
        │
        ▼
┌───────────────────┐
│ Check permission  │
│ level of action   │
└───────┬───────────┘
        │
        ├── READ_DATA, READ_CONFIG ──────────▶ Execute immediately
        │
        ├── WRITE_CONFIG, SEND_NOTIFICATION ─▶ Check tenant policy
        │   │                                   │
        │   ├── auto_approve = true ───────────▶ Execute immediately
        │   └── auto_approve = false ──────────▶ Queue for approval
        │
        └── EXECUTE_RUNBOOK, INFRASTRUCTURE ──▶ Always queue for approval
                                                │
                                        ┌───────▼───────────┐
                                        │  APPROVAL QUEUE   │
                                        │                   │
                                        │  Notify via:      │
                                        │  - Slack/Teams    │
                                        │  - Email          │
                                        │  - Dashboard UI   │
                                        │  - PagerDuty      │
                                        └───────┬───────────┘
                                                │
                                        ┌───────▼───────────┐
                                        │  Human reviews:   │
                                        │  - Action details │
                                        │  - Agent reasoning│
                                        │  - Risk assessment│
                                        │  - Affected scope │
                                        └───────┬───────────┘
                                                │
                                    ┌───────────┼───────────┐
                                    ▼                       ▼
                             ┌──────────┐           ┌──────────┐
                             │ APPROVED │           │ REJECTED │
                             │ Execute  │           │ Log +    │
                             │ action   │           │ feedback │
                             └──────────┘           └──────────┘
```

### 4.10 Agent Sandboxing and Security

```
┌─────────────────────────────────────────────────────────────────┐
│                  AGENT SECURITY MODEL                            │
│                                                                 │
│  LAYER 1: NETWORK ISOLATION                                     │
│  • Container runs in isolated network namespace                 │
│  • Egress restricted to: RayOlly APIs, approved LLM endpoints  │
│  • No direct internet access                                    │
│  • No access to host filesystem                                 │
│                                                                 │
│  LAYER 2: DATA SCOPING                                          │
│  • All data queries auto-scoped to tenant                       │
│  • Agent identity token includes tenant_id claim                │
│  • Tool proxy validates tenant scope on every call              │
│  • Cross-tenant data access = immediate kill + alert            │
│                                                                 │
│  LAYER 3: RESOURCE LIMITS                                       │
│  • CPU: 2 cores max per agent execution                         │
│  • Memory: 4 GB max per agent execution                         │
│  • Execution time: configurable timeout (default 10 min)        │
│  • LLM tokens: budget per execution, per hour, per day          │
│  • Tool calls: max 50 per execution (default)                   │
│                                                                 │
│  LAYER 4: ACTION GOVERNANCE                                     │
│  • Permission levels enforced per tool                          │
│  • Destructive actions require human approval                   │
│  • All actions logged to immutable audit trail                  │
│  • Kill switch: any agent can be stopped immediately            │
│  • Runaway detection: auto-kill if token/time budget exceeded   │
│                                                                 │
│  LAYER 5: PROMPT SECURITY                                       │
│  • System prompts are immutable (not modifiable by user input)  │
│  • Input sanitization on all user-provided context              │
│  • Output validation before action execution                    │
│  • Prompt injection detection layer                             │
│  • No arbitrary code execution from LLM output                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. Built-in Agents (Ship with Platform)

### 5.1 RCA Agent (Root Cause Analysis)

**Purpose**: Autonomously investigates anomalies and alerts to determine root cause, correlating across logs, metrics, traces, and deployment history.

**Trigger**: Anomaly detection event with severity >= `high`, or manual invocation.

**Agent Configuration**

```yaml
agent:
  name: rca_agent
  version: "1.0.0"
  type: built_in
  description: "Investigates anomalies to determine root cause"

  triggers:
    - type: event
      source: anomaly_detector
      conditions:
        - field: severity
          operator: gte
          value: high
      debounce: 120s
    - type: on_demand
      channels: [chat, api, slack]

  tools:
    - query_logs
    - query_metrics
    - query_traces
    - get_service_map
    - get_deployments
    - get_change_log
    - search_kb
    - get_past_rca
    - delegate

  memory:
    working: true
    episodic: true
    semantic: true

  limits:
    max_iterations: 15
    max_tool_calls: 40
    max_tokens: 80000
    timeout: 300s

  output:
    format: rca_report
    notify: [incident_channel, on_call_team]
```

**Investigation Flow**

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    RCA AGENT INVESTIGATION FLOW                         │
│                                                                         │
│  INPUT: Anomaly event (service=api-gateway, type=latency_spike,        │
│         severity=high, detected_at=2026-03-19T14:23:00Z)               │
│                                                                         │
│  STEP 1: SCOPE THE PROBLEM                                              │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ • query_metrics(service=api-gateway, metric=p99_latency,        │   │
│  │                  time_range="last 2h")                          │   │
│  │ • query_metrics(service=api-gateway, metric=error_rate,         │   │
│  │                  time_range="last 2h")                          │   │
│  │ • query_metrics(service=api-gateway, metric=request_rate,       │   │
│  │                  time_range="last 2h")                          │   │
│  │                                                                  │   │
│  │ Finding: p99 latency jumped from 120ms to 2400ms at 14:15 UTC   │   │
│  │ Error rate increased from 0.1% to 8.3%                          │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  STEP 2: IDENTIFY BLAST RADIUS                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ • get_service_map(root=api-gateway, depth=2)                    │   │
│  │ • query_metrics(services=[downstream_services],                 │   │
│  │                  metric=error_rate, time_range="last 2h")       │   │
│  │                                                                  │   │
│  │ Finding: Downstream services payment-svc and user-svc also      │   │
│  │ affected. Upstream web-frontend showing increased errors.        │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  STEP 3: CHECK FOR RECENT CHANGES                                       │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ • get_deployments(time_range="last 6h")                         │   │
│  │ • get_change_log(time_range="last 6h")                          │   │
│  │                                                                  │   │
│  │ Finding: Deployment of api-gateway v2.14.3 at 14:12 UTC         │   │
│  │ (3 minutes before anomaly onset)                                │   │
│  │ Change: "Add new caching layer for user profile lookups"        │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  STEP 4: DEEP DIVE INTO EVIDENCE                                        │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ • query_logs(service=api-gateway, severity=error,               │   │
│  │              time_range="14:12-14:25")                          │   │
│  │ • query_traces(service=api-gateway, min_duration=1000ms,        │   │
│  │                time_range="14:15-14:25", limit=20)              │   │
│  │                                                                  │   │
│  │ Finding: Logs show "Redis connection pool exhausted" errors      │   │
│  │ starting at 14:14. Traces show new cache_lookup span taking     │   │
│  │ 2000ms+ with Redis timeout exceptions.                          │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  STEP 5: CHECK PAST INCIDENTS                                           │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ • get_past_rca(tags=["redis", "connection_pool", "api-gateway"])│   │
│  │ • search_kb(query="redis connection pool exhaustion")           │   │
│  │                                                                  │   │
│  │ Finding: Similar incident on 2026-02-03. Root cause was Redis   │   │
│  │ maxclients limit. Resolution: increased pool size in config.    │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  STEP 6: BUILD CAUSALITY CHAIN & CONFIDENCE                             │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                                                                  │   │
│  │ ROOT CAUSE (confidence: 0.92):                                  │   │
│  │   Deployment v2.14.3 introduced a new caching layer that        │   │
│  │   creates Redis connections per-request instead of using the    │   │
│  │   connection pool. This exhausted the Redis connection limit    │   │
│  │   within 2 minutes of deployment under production traffic.      │   │
│  │                                                                  │   │
│  │ CAUSALITY CHAIN:                                                │   │
│  │   Deploy v2.14.3 (14:12)                                       │   │
│  │     → New cache layer creates per-request Redis connections     │   │
│  │     → Redis connection pool exhausted (14:14)                   │   │
│  │     → Cache lookups timeout at 2000ms (14:14)                   │   │
│  │     → api-gateway p99 latency spikes to 2400ms (14:15)         │   │
│  │     → Upstream web-frontend requests timeout (14:16)            │   │
│  │     → Error rate reaches 8.3% (14:17)                          │   │
│  │                                                                  │   │
│  │ RECOMMENDATION:                                                  │   │
│  │   1. Rollback api-gateway to v2.14.2 (immediate)               │   │
│  │   2. Fix connection pooling in caching code (follow-up)         │   │
│  │   3. Add connection pool utilization alert (preventive)         │   │
│  │                                                                  │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Output Schema**

```json
{
  "rca_report": {
    "id": "rca-20260319-142300-api-gateway",
    "anomaly_id": "anom-xyz-123",
    "timestamp": "2026-03-19T14:28:45Z",
    "investigation_duration_seconds": 345,
    "root_cause": {
      "summary": "Deployment v2.14.3 introduced per-request Redis connections, exhausting the connection pool",
      "confidence": 0.92,
      "category": "deployment_regression",
      "causality_chain": [
        {"event": "Deploy v2.14.3", "time": "14:12:00Z", "confidence": 1.0},
        {"event": "Redis connection pool exhausted", "time": "14:14:00Z", "confidence": 0.95},
        {"event": "Cache lookup timeouts", "time": "14:14:30Z", "confidence": 0.93},
        {"event": "p99 latency spike", "time": "14:15:00Z", "confidence": 0.98},
        {"event": "Cascading errors to dependents", "time": "14:16:00Z", "confidence": 0.90}
      ]
    },
    "affected_services": ["api-gateway", "web-frontend", "payment-svc", "user-svc"],
    "user_impact": {
      "estimated_affected_users": 12400,
      "error_rate_peak": 0.083,
      "duration_minutes": 13
    },
    "evidence": [
      {"type": "deployment", "detail": "v2.14.3 deployed at 14:12", "source": "deploy_log"},
      {"type": "log", "detail": "Redis connection pool exhausted (427 occurrences)", "source": "api-gateway logs"},
      {"type": "trace", "detail": "cache_lookup span avg 2100ms with timeout", "source": "trace_store"},
      {"type": "historical", "detail": "Similar incident 2026-02-03, same root cause pattern", "source": "past_rca"}
    ],
    "recommendations": [
      {"action": "rollback", "target": "api-gateway", "to_version": "v2.14.2", "urgency": "immediate", "requires_approval": true},
      {"action": "code_fix", "detail": "Use connection pool in new caching layer", "urgency": "follow_up"},
      {"action": "create_alert", "detail": "Redis connection pool utilization > 80%", "urgency": "preventive"}
    ],
    "tools_used": ["query_metrics", "get_service_map", "get_deployments", "query_logs", "query_traces", "get_past_rca", "search_kb"],
    "llm_tokens_used": 34500,
    "reasoning_steps": 12
  }
}
```

### 5.2 Incident Commander Agent

**Purpose**: Manages the full incident lifecycle — from detection through resolution to postmortem. Coordinates other agents, maintains the timeline, manages communications, and tracks SLA impact.

**Trigger**: Incident creation (manual or auto-created by RCA Agent), or anomaly escalation.

**Agent Configuration**

```yaml
agent:
  name: incident_commander
  version: "1.0.0"
  type: built_in
  description: "Manages incident lifecycle and coordinates response"

  triggers:
    - type: event
      source: incident_manager
      conditions:
        - field: action
          operator: eq
          value: created
    - type: event
      source: rca_agent
      conditions:
        - field: severity
          operator: gte
          value: high
        - field: confidence
          operator: gte
          value: 0.8

  tools:
    - create_incident
    - update_incident
    - query_logs
    - query_metrics
    - get_slo_config
    - send_slack
    - send_teams
    - page_user
    - delegate
    - get_team_info
    - search_kb

  limits:
    max_iterations: 30
    max_tool_calls: 100
    max_tokens: 150000
    timeout: 3600s  # Incidents can be long-running

  output:
    format: incident_report
```

**Capabilities**

| Capability | Description |
|---|---|
| Incident creation | Auto-creates incidents from high-confidence RCA findings |
| Timeline management | Maintains chronological event timeline with evidence |
| Agent coordination | Delegates to RCA, SLO Guardian, Runbook agents |
| Communication | Sends updates via Slack, Teams, PagerDuty at configurable intervals |
| Escalation | Auto-escalates based on severity, duration, and SLO impact |
| Status tracking | Tracks incident through: Detected → Investigating → Identified → Mitigating → Resolved |
| SLA monitoring | Tracks time-to-acknowledge, time-to-mitigate against SLA targets |
| Postmortem generation | Produces structured postmortem draft with timeline, root cause, and action items |
| Stakeholder updates | Generates executive summaries at configurable intervals |

**Postmortem Template (Auto-Generated)**

```markdown
# Incident Postmortem: INC-2026-0319-001

## Summary
API Gateway latency spike caused by Redis connection pool exhaustion following
deployment of v2.14.3. Duration: 13 minutes. User impact: ~12,400 users affected.

## Timeline
| Time (UTC) | Event | Source |
|---|---|---|
| 14:12:00 | api-gateway v2.14.3 deployed | Deploy pipeline |
| 14:14:00 | Redis connection pool exhausted errors begin | RCA Agent |
| 14:15:00 | p99 latency anomaly detected (120ms → 2400ms) | Anomaly Detector |
| 14:15:30 | RCA Agent investigation initiated | Agent Platform |
| 14:20:45 | Root cause identified: per-request Redis connections | RCA Agent |
| 14:21:00 | Incident INC-2026-0319-001 created (SEV1) | Incident Commander |
| 14:21:15 | On-call engineer @jsmith paged | Incident Commander |
| 14:22:00 | Rollback to v2.14.2 requested (awaiting approval) | Runbook Agent |
| 14:23:30 | Rollback approved by @jsmith | Human approval |
| 14:24:00 | Rollback initiated | Runbook Agent |
| 14:25:30 | api-gateway v2.14.2 deployed | Deploy pipeline |
| 14:27:00 | p99 latency returned to baseline (130ms) | Metrics |
| 14:28:00 | Error rate returned to baseline (0.1%) | Metrics |
| 14:28:30 | Incident resolved | Incident Commander |

## Root Cause
[Auto-populated from RCA Agent report]

## Impact
- **Duration**: 13 minutes (14:15 - 14:28 UTC)
- **Users affected**: ~12,400
- **Error budget consumed**: 2.1% of monthly budget
- **SLO status**: Within budget (remaining: 97.1%)
- **Revenue impact**: Estimated $0 (no transactions failed, only latency)

## Action Items
- [ ] Fix connection pooling in caching layer (owner: @dev-team, due: 2026-03-22)
- [ ] Add Redis connection pool utilization alert (owner: @sre-team, due: 2026-03-20)
- [ ] Add connection pool integration test (owner: @dev-team, due: 2026-03-22)
- [ ] Review deployment canary thresholds (owner: @platform-team, due: 2026-03-26)
```

### 5.3 Query Agent (Natural Language to Data)

**Purpose**: Converts natural language questions into RayQL queries, executes them, and presents results with context. Supports iterative refinement and visualization suggestions.

**Trigger**: On-demand via chat interface, Slack, or API.

**Agent Configuration**

```yaml
agent:
  name: query_agent
  version: "1.0.0"
  type: built_in
  description: "Natural language to data query interface"

  triggers:
    - type: on_demand
      channels: [chat, api, slack, teams]

  tools:
    - run_rayql
    - query_logs
    - query_metrics
    - query_traces
    - get_service_map
    - get_topology

  memory:
    working: true
    semantic: true  # Knows tenant's schema and services

  limits:
    max_iterations: 5
    max_tool_calls: 10
    max_tokens: 30000
    timeout: 30s
```

**Interaction Examples**

```
USER: "Show me error rates for the payment service over the last week"

AGENT REASONING:
  1. User wants error_rate metric for payment-svc
  2. Time range: last 7 days
  3. Check semantic memory for service name → "payment-service" (canonical)
  4. Generate RayQL query

AGENT ACTION: run_rayql("""
  SELECT
    time_bucket('1h', timestamp) AS hour,
    count(*) FILTER (WHERE status_code >= 500) AS errors,
    count(*) AS total,
    round(count(*) FILTER (WHERE status_code >= 500)::decimal / count(*) * 100, 2) AS error_rate
  FROM logs
  WHERE service = 'payment-service'
    AND timestamp > now() - INTERVAL '7 days'
  GROUP BY hour
  ORDER BY hour
""")

AGENT RESPONSE:
  "Here's the error rate for payment-service over the last 7 days:

   [Line chart showing hourly error rate]

   Key observations:
   • Average error rate: 0.23%
   • Peak: 4.7% on March 15 between 2-3 PM UTC (correlates with deploy v3.2.1)
   • Current: 0.18% (within normal range)

   The RayQL query used:
   SELECT time_bucket('1h', timestamp) AS hour, ...

   Would you like me to:
   • Break this down by endpoint?
   • Compare with the previous week?
   • Investigate the March 15 spike?"
```

```
USER: "Break it down by endpoint"

AGENT REASONING:
  1. Refinement of previous query
  2. Add endpoint dimension to GROUP BY
  3. Use working memory for context

AGENT ACTION: run_rayql("""
  SELECT
    time_bucket('1h', timestamp) AS hour,
    attributes->>'http.route' AS endpoint,
    round(count(*) FILTER (WHERE status_code >= 500)::decimal / count(*) * 100, 2) AS error_rate
  FROM logs
  WHERE service = 'payment-service'
    AND timestamp > now() - INTERVAL '7 days'
  GROUP BY hour, endpoint
  HAVING count(*) > 10
  ORDER BY hour, error_rate DESC
""")

AGENT RESPONSE:
  "Error rates by endpoint for payment-service:

   [Heatmap: endpoint × time → error_rate]

   Top error-producing endpoints:
   1. POST /api/v2/payments/process — avg 0.8% error rate
   2. POST /api/v2/payments/refund — avg 0.5% error rate
   3. GET /api/v2/payments/status — avg 0.02% error rate

   The /process endpoint accounts for 68% of all errors.
   Want me to investigate the /process endpoint errors specifically?"
```

### 5.4 Anomaly Investigator Agent

**Purpose**: Deep-dives into detected anomalies to determine whether they are actionable or noise. Collects evidence, assesses user impact, and recommends action.

**Trigger**: Anomaly detection event (all severities).

**Agent Configuration**

```yaml
agent:
  name: anomaly_investigator
  version: "1.0.0"
  type: built_in
  description: "Deep-dive investigation of detected anomalies"

  triggers:
    - type: event
      source: anomaly_detector
      debounce: 30s

  tools:
    - query_logs
    - query_metrics
    - query_traces
    - get_service_map
    - get_deployments
    - get_change_log
    - search_kb
    - delegate

  limits:
    max_iterations: 8
    max_tool_calls: 25
    max_tokens: 40000
    timeout: 120s
```

**Decision Matrix**

| Finding | Action | Confidence Threshold |
|---|---|---|
| Anomaly correlates with deployment + errors increasing | Escalate to RCA Agent | 0.7 |
| Anomaly is periodic/expected (e.g., batch jobs) | Suppress with explanation | 0.8 |
| Anomaly is transient, already self-resolved | Log and suppress | 0.7 |
| Anomaly shows user impact but cause unclear | Create alert + escalate | 0.6 |
| Anomaly is in non-production environment | Log only | 0.9 |

**Learning from Feedback**

```
┌─────────────────────────────────────────────────────────┐
│              ANOMALY INVESTIGATOR LEARNING LOOP          │
│                                                         │
│  Anomaly detected                                       │
│       │                                                 │
│       ▼                                                 │
│  Agent investigates → produces recommendation           │
│       │                                                 │
│       ▼                                                 │
│  Human reviews → provides feedback                      │
│       │                                                 │
│       ├── 👍 Correct action → store as positive example │
│       │                                                 │
│       ├── 👎 Wrong action → store with correction       │
│       │                                                 │
│       └── Adjusted → store with modified parameters     │
│                                                         │
│  Episodic memory updated:                               │
│  {                                                      │
│    anomaly_type: "latency_spike",                       │
│    service: "batch-processor",                          │
│    time_pattern: "daily_3am",                           │
│    correct_action: "suppress",                          │
│    reason: "expected daily batch job"                   │
│  }                                                      │
│                                                         │
│  Next occurrence: Agent checks episodic memory first    │
│  → "I've seen this pattern before, it's the daily      │
│     batch job. Suppressing."                            │
└─────────────────────────────────────────────────────────┘
```

### 5.5 Auto-Instrumentation Agent

**Purpose**: Discovers uninstrumented or under-instrumented services, suggests improvements, generates OpenTelemetry SDK configuration, and validates coverage.

**Trigger**: Scheduled (weekly scan) or on-demand.

**Agent Configuration**

```yaml
agent:
  name: auto_instrumentation
  version: "1.0.0"
  type: built_in
  description: "Discovers and improves service instrumentation"

  triggers:
    - type: schedule
      cron: "0 6 * * 1"  # Monday 6 AM
    - type: on_demand
      channels: [chat, api]

  tools:
    - get_service_map
    - get_topology
    - query_metrics
    - query_traces
    - search_kb
    - post_note

  limits:
    max_iterations: 20
    max_tool_calls: 40
    max_tokens: 60000
    timeout: 600s
```

**Capabilities**

| Capability | Implementation |
|---|---|
| Service discovery | Analyze trace data to find services with incomplete spans |
| Gap detection | Identify services visible in infrastructure but missing from traces |
| Coverage scoring | Score each service: 0-100 based on metric, trace, and log coverage |
| Config generation | Generate OTEL SDK config for detected language/framework |
| Health validation | Validate that instrumentation is producing expected telemetry |

**Output Example**

```json
{
  "instrumentation_report": {
    "scan_date": "2026-03-19",
    "total_services": 47,
    "fully_instrumented": 38,
    "partially_instrumented": 6,
    "not_instrumented": 3,
    "coverage_score": 83,
    "gaps": [
      {
        "service": "notification-worker",
        "issue": "No traces emitted, only logs",
        "language": "python",
        "framework": "celery",
        "recommendation": "Add opentelemetry-instrumentation-celery package",
        "generated_config": "# See attached otel-config.yaml",
        "impact": "Cannot trace async notification flows end-to-end"
      },
      {
        "service": "legacy-auth",
        "issue": "No telemetry of any kind detected",
        "language": "java",
        "framework": "spring-boot",
        "recommendation": "Add OTEL Java agent with auto-instrumentation",
        "generated_config": "# See attached otel-java-agent.properties",
        "impact": "Authentication failures are invisible to the platform"
      }
    ]
  }
}
```

### 5.6 Capacity Planning Agent

**Purpose**: Forecasts resource needs, identifies waste, recommends scaling actions, and generates capacity reports.

**Trigger**: Scheduled (weekly report) or on-demand.

**Agent Configuration**

```yaml
agent:
  name: capacity_planner
  version: "1.0.0"
  type: built_in
  description: "Resource forecasting and capacity optimization"

  triggers:
    - type: schedule
      cron: "0 8 * * 1"  # Monday 8 AM
    - type: on_demand
      channels: [chat, api]

  tools:
    - query_metrics
    - get_topology
    - get_service_map
    - search_kb
    - k8s_get
    - aws_describe
    - post_note

  limits:
    max_iterations: 25
    max_tool_calls: 50
    max_tokens: 80000
    timeout: 600s
```

**Report Sections**

| Section | Content |
|---|---|
| Resource utilization | CPU, memory, disk, network by service/cluster |
| Growth forecast | Projected resource needs at 30/60/90 days |
| Waste identification | Over-provisioned services, idle resources |
| Cost analysis | Current spend, projected spend, optimization opportunities |
| Scaling recommendations | Right-sizing, HPA adjustments, node pool changes |
| Risk assessment | Services approaching limits, single points of failure |

### 5.7 Runbook Execution Agent

**Purpose**: Stores, manages, and executes operational runbooks with parameterization, safety checks, rollback capability, and full audit trails.

**Trigger**: Delegated from other agents (RCA, Incident Commander) or on-demand.

**Agent Configuration**

```yaml
agent:
  name: runbook_executor
  version: "1.0.0"
  type: built_in
  description: "Safe execution of operational runbooks"

  triggers:
    - type: on_demand
      channels: [chat, api, slack, delegation]

  tools:
    - read_runbook
    - execute_runbook
    - k8s_get
    - k8s_describe
    - restart_pod
    - scale_service
    - rollback_deploy
    - query_metrics
    - query_logs

  approval:
    required_for: [execute_runbook, restart_pod, scale_service, rollback_deploy]
    approvers: [on_call_engineer, sre_team_lead]
    timeout: 300s  # 5 min approval timeout

  limits:
    max_iterations: 20
    max_tool_calls: 30
    max_tokens: 50000
    timeout: 600s
```

**Runbook Definition Format**

```yaml
runbook:
  name: rollback_deployment
  version: "1.2.0"
  description: "Rollback a Kubernetes deployment to previous version"
  category: deployment
  risk_level: medium
  requires_approval: true

  parameters:
    - name: service_name
      type: string
      required: true
      description: "Name of the service to rollback"
    - name: target_version
      type: string
      required: false
      description: "Specific version to rollback to (default: previous)"
    - name: namespace
      type: string
      required: false
      default: "production"

  pre_checks:
    - name: verify_service_exists
      tool: k8s_get
      args:
        resource: deployment
        name: "{{service_name}}"
        namespace: "{{namespace}}"
      expect: exists

    - name: verify_previous_version
      tool: k8s_describe
      args:
        resource: deployment
        name: "{{service_name}}"
        namespace: "{{namespace}}"
      extract: previous_revision

  steps:
    - name: capture_current_state
      tool: k8s_describe
      args:
        resource: deployment
        name: "{{service_name}}"
        namespace: "{{namespace}}"
      save_as: pre_rollback_state

    - name: execute_rollback
      tool: rollback_deploy
      args:
        deployment: "{{service_name}}"
        namespace: "{{namespace}}"
        to_revision: "{{target_version | default('previous')}}"
      timeout: 120s

    - name: wait_for_ready
      tool: k8s_get
      args:
        resource: deployment
        name: "{{service_name}}"
        namespace: "{{namespace}}"
      wait_condition: "available"
      timeout: 180s

  post_checks:
    - name: verify_health
      tool: query_metrics
      args:
        service: "{{service_name}}"
        metric: error_rate
        time_range: "last 5m"
      expect:
        operator: lt
        value: 0.05

  rollback:
    - name: undo_rollback
      tool: rollback_deploy
      args:
        deployment: "{{service_name}}"
        namespace: "{{namespace}}"
        to_revision: "{{pre_rollback_state.revision}}"
```

**Execution Flow**

```
Runbook invoked (by agent or human)
        │
        ▼
┌───────────────────┐
│ Parse parameters  │
│ Validate inputs   │
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│ Run pre-checks    │──── FAIL ──▶ Abort with explanation
└───────┬───────────┘
        │ PASS
        ▼
┌───────────────────┐
│ Request approval  │──── TIMEOUT/REJECT ──▶ Abort
└───────┬───────────┘
        │ APPROVED
        ▼
┌───────────────────┐
│ Execute steps     │──── FAIL ──▶ Execute rollback steps
│ (sequentially)    │
└───────┬───────────┘
        │ SUCCESS
        ▼
┌───────────────────┐
│ Run post-checks   │──── FAIL ──▶ Execute rollback steps
└───────┬───────────┘
        │ PASS
        ▼
┌───────────────────┐
│ Report success    │
│ Log audit trail   │
└───────────────────┘
```

### 5.8 SLO Guardian Agent

**Purpose**: Monitors SLO burn rates, predicts breaches, recommends interventions, and generates compliance reports.

**Trigger**: Continuous (runs on schedule with frequent checks), plus event-driven on SLO threshold crossings.

**Agent Configuration**

```yaml
agent:
  name: slo_guardian
  version: "1.0.0"
  type: built_in
  description: "SLO monitoring, prediction, and protection"

  triggers:
    - type: schedule
      cron: "*/15 * * * *"  # Every 15 minutes
    - type: event
      source: slo_monitor
      conditions:
        - field: burn_rate
          operator: gte
          value: 2.0  # 2x normal burn rate

  tools:
    - query_metrics
    - get_slo_config
    - send_slack
    - page_user
    - delegate
    - post_note

  limits:
    max_iterations: 10
    max_tool_calls: 20
    max_tokens: 30000
    timeout: 120s
```

**SLO Monitoring Logic**

```
Every 15 minutes:
  For each configured SLO:
    │
    ├── Calculate current burn rate
    │     burn_rate = (errors_in_window / total_in_window) / (1 - slo_target)
    │
    ├── Calculate remaining error budget
    │     budget_remaining = 1 - (total_errors_this_period / allowed_errors)
    │
    ├── Forecast: Will SLO breach before period ends?
    │     projected_budget = budget_remaining - (burn_rate × remaining_time)
    │
    └── Decision:
          │
          ├── burn_rate < 1.0  → Healthy, no action
          │
          ├── 1.0 ≤ burn_rate < 2.0 → Warning: slow burn
          │     → Post to SLO dashboard
          │     → Slack notification to team
          │
          ├── 2.0 ≤ burn_rate < 5.0 → Alert: fast burn
          │     → Page on-call engineer
          │     → Delegate investigation to Anomaly Investigator
          │
          └── burn_rate ≥ 5.0 → Critical: very fast burn
                → Page SRE team lead
                → Delegate to Incident Commander
                → Recommend traffic shedding or rollback
```

**SLO Report Output**

```
┌─────────────────────────────────────────────────────────────────┐
│                    WEEKLY SLO REPORT                             │
│                    Period: Mar 12-19, 2026                       │
│                                                                 │
│  SERVICE              SLO TARGET   CURRENT   BUDGET   STATUS    │
│  ─────────────────────────────────────────────────────────────── │
│  api-gateway          99.95%       99.93%    62.1%    ⚠ WARN   │
│  payment-service      99.99%       99.99%    91.2%    ✓ OK      │
│  user-service         99.9%        99.97%    97.0%    ✓ OK      │
│  search-service       99.5%        99.8%     98.5%    ✓ OK      │
│  notification-worker  99.0%        99.6%     94.0%    ✓ OK      │
│                                                                 │
│  INCIDENTS THIS PERIOD:                                         │
│  • INC-2026-0315-002: api-gateway latency (consumed 35% budget)│
│  • INC-2026-0319-001: api-gateway Redis (consumed 2.1% budget) │
│                                                                 │
│  FORECAST:                                                      │
│  api-gateway is on track to breach SLO by March 28 if current  │
│  burn rate continues. Recommend investigation into recurring    │
│  latency issues.                                                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. Agent SDK (for Custom Agents)

### 6.1 Overview

The RayOlly Agent SDK enables customers and partners to build custom agents that run on the RayOlly platform. The SDK provides a Python-first development experience with full access to the agent runtime, tools, memory, and orchestration capabilities.

### 6.2 SDK Installation

```bash
pip install rayolly-agent-sdk
```

### 6.3 Agent Definition Format

Every custom agent consists of two components:

1. **Agent manifest** (`agent.yaml`) — declares metadata, triggers, tools, and limits
2. **Agent logic** (`agent.py`) — implements the agent's reasoning and behavior

**Minimal Agent Example**

`agent.yaml`:
```yaml
agent:
  name: custom_error_monitor
  version: "1.0.0"
  description: "Monitors specific error patterns and alerts the team"
  author: "platform-team@acme.com"

  triggers:
    - type: schedule
      cron: "*/5 * * * *"

  tools:
    - query_logs
    - send_slack

  permissions:
    - READ_DATA
    - SEND_NOTIFICATION

  limits:
    max_iterations: 5
    max_tool_calls: 10
    max_tokens: 15000
    timeout: 60s
```

`agent.py`:
```python
from rayolly.agents import Agent, AgentContext, AgentResult
from rayolly.agents.tools import query_logs, send_slack


class CustomErrorMonitor(Agent):
    """Monitors for specific error patterns every 5 minutes."""

    async def run(self, context: AgentContext) -> AgentResult:
        # Step 1: Check for the error pattern
        logs = await self.use_tool(
            query_logs,
            query='level:error AND message:"database connection timeout"',
            time_range="last 5m",
            limit=50,
        )

        if logs.total_count == 0:
            return AgentResult(
                status="completed",
                summary="No database timeout errors in last 5 minutes",
                actions_taken=[],
            )

        # Step 2: Assess severity
        if logs.total_count > 10:
            severity = "critical"
            message = f"🚨 {logs.total_count} database timeout errors in last 5 minutes!"
        elif logs.total_count > 3:
            severity = "warning"
            message = f"⚠️ {logs.total_count} database timeout errors in last 5 minutes"
        else:
            severity = "info"
            message = f"ℹ️ {logs.total_count} database timeout errors in last 5 minutes"

        # Step 3: Notify if concerning
        if severity in ("critical", "warning"):
            affected_services = set(log["service"] for log in logs.logs)
            await self.use_tool(
                send_slack,
                channel="#sre-alerts",
                message=f"{message}\nAffected services: {', '.join(affected_services)}",
            )

        return AgentResult(
            status="completed",
            summary=f"Found {logs.total_count} database timeout errors ({severity})",
            actions_taken=["slack_notification"] if severity != "info" else [],
            data={"error_count": logs.total_count, "severity": severity},
        )
```

### 6.4 Advanced Agent Example — Reasoning Agent

```python
from rayolly.agents import ReasoningAgent, AgentContext, AgentResult, Think, Act, Observe
from rayolly.agents.memory import EpisodicMemory, SemanticMemory
from rayolly.agents.tools import query_logs, query_metrics, get_service_map, send_slack


class DeploymentHealthChecker(ReasoningAgent):
    """
    Monitors deployments and verifies health post-deploy.
    Uses ReAct reasoning loop for investigation.
    """

    async def run(self, context: AgentContext) -> AgentResult:
        deployment = context.trigger_event["deployment"]
        service = deployment["service"]
        version = deployment["version"]

        # Check episodic memory for past deployment issues
        past_issues = await self.memory.episodic.search(
            query=f"deployment issues for {service}",
            limit=5,
        )

        # Build investigation plan
        plan = await self.plan(
            goal=f"Verify health of {service} deployment {version}",
            context={
                "service": service,
                "version": version,
                "deployed_at": deployment["timestamp"],
                "past_issues": past_issues,
            },
        )

        # Execute plan with reasoning loop
        findings = []
        for step in plan.steps:
            # Think: What should I check?
            thought = await self.think(
                f"Executing step: {step.description}. "
                f"Previous findings: {findings}"
            )

            # Act: Execute the appropriate tool
            result = await self.act(step, context)

            # Observe: Analyze the result
            observation = await self.observe(result, thought)
            findings.append(observation)

            # Early termination if critical issue found
            if observation.severity == "critical":
                await self.use_tool(
                    send_slack,
                    channel="#deploy-alerts",
                    message=(
                        f"Critical issue detected after {service} {version} deploy:\n"
                        f"{observation.summary}\n"
                        f"Recommend immediate rollback."
                    ),
                )
                break

        # Synthesize findings
        return await self.synthesize(findings, context)
```

### 6.5 Tool Definition API

Custom agents can define their own tools:

```python
from rayolly.agents.tools import Tool, ToolResult, ToolPermission


class CheckJiraTicket(Tool):
    """Check the status of a Jira ticket."""

    name = "check_jira"
    description = "Retrieve status and details of a Jira ticket"
    permission = ToolPermission.READ_CONFIG  # Requires external API access

    class Input(Tool.InputSchema):
        ticket_id: str

    class Output(Tool.OutputSchema):
        status: str
        assignee: str
        summary: str
        priority: str

    async def execute(self, input: Input, context: AgentContext) -> ToolResult:
        # Use tenant's configured Jira integration
        jira_client = await context.get_integration("jira")
        ticket = await jira_client.get_issue(input.ticket_id)

        return ToolResult(
            success=True,
            output=self.Output(
                status=ticket.status,
                assignee=ticket.assignee.display_name,
                summary=ticket.summary,
                priority=ticket.priority.name,
            ),
        )
```

### 6.6 Memory API

```python
from rayolly.agents.memory import Memory, EpisodicMemory, SemanticMemory

class MyAgent(Agent):
    async def run(self, context: AgentContext) -> AgentResult:
        # WORKING MEMORY — automatic, scoped to this execution
        self.memory.working.set("current_hypothesis", "Redis connection issue")
        hypothesis = self.memory.working.get("current_hypothesis")

        # EPISODIC MEMORY — past experiences
        similar_incidents = await self.memory.episodic.search(
            query="Redis connection pool exhaustion",
            time_range="last 90d",
            limit=5,
        )

        # Save to episodic memory for future reference
        await self.memory.episodic.save(
            event_type="investigation",
            summary="Redis connection pool issue caused by new cache layer",
            tags=["redis", "connection_pool", "deployment_regression"],
            outcome="resolved_by_rollback",
        )

        # SEMANTIC MEMORY — knowledge base
        runbooks = await self.memory.semantic.search(
            query="Redis troubleshooting",
            category="runbook",
            limit=3,
        )

        service_info = await self.memory.semantic.get_entity(
            entity_type="service",
            name="api-gateway",
        )
        # Returns: {name, team, dependencies, slos, recent_deploys, ...}
```

### 6.7 Inter-Agent Communication API

```python
from rayolly.agents import Agent, AgentContext
from rayolly.agents.delegation import delegate, DelegationRequest


class MyOrchestrator(Agent):
    async def run(self, context: AgentContext) -> AgentResult:
        # Delegate to the RCA agent
        rca_result = await self.delegate(
            target_agent="rca_agent",
            task="Investigate the latency spike on api-gateway starting at 14:15 UTC",
            context={
                "anomaly_id": context.trigger_event["anomaly_id"],
                "service": "api-gateway",
            },
            timeout=timedelta(minutes=5),
            required_confidence=0.7,
        )

        if rca_result.confidence >= 0.8:
            # High confidence — proceed with remediation
            runbook_result = await self.delegate(
                target_agent="runbook_executor",
                task=f"Execute rollback for {rca_result.result['service']}",
                context=rca_result.result,
                timeout=timedelta(minutes=10),
            )

        # Can also spawn sub-agents for parallel work
        async with self.parallel() as pool:
            pool.delegate("slo_guardian", task="Check SLO impact for api-gateway")
            pool.delegate("anomaly_investigator", task="Check for related anomalies")
            results = await pool.gather()
```

### 6.8 Testing Framework

```python
from rayolly.agents.testing import AgentTestCase, MockToolkit, MockMemory


class TestCustomErrorMonitor(AgentTestCase):
    agent_class = CustomErrorMonitor

    async def test_no_errors_found(self):
        """Agent should report clean status when no errors exist."""
        self.mock_tool(
            "query_logs",
            response={"logs": [], "total_count": 0, "query_time_ms": 12},
        )

        result = await self.run_agent()

        assert result.status == "completed"
        assert "No database timeout errors" in result.summary
        self.assert_tool_not_called("send_slack")

    async def test_critical_errors_trigger_notification(self):
        """Agent should send Slack alert when >10 errors found."""
        self.mock_tool(
            "query_logs",
            response={
                "logs": [{"service": "user-svc", "message": "timeout"}] * 15,
                "total_count": 15,
                "query_time_ms": 23,
            },
        )
        self.mock_tool("send_slack", response={"ok": True})

        result = await self.run_agent()

        assert result.status == "completed"
        assert result.data["severity"] == "critical"
        self.assert_tool_called("send_slack", channel="#sre-alerts")

    async def test_respects_token_budget(self):
        """Agent should not exceed configured token limits."""
        result = await self.run_agent()
        assert result.token_usage.total < self.agent_config.limits.max_tokens
```

### 6.9 Deployment Pipeline

```bash
# Validate agent definition
rayolly agent validate ./my-agent/

# Run tests locally
rayolly agent test ./my-agent/

# Package the agent
rayolly agent package ./my-agent/ --output my-agent-1.0.0.tar.gz

# Deploy to RayOlly (requires API key)
rayolly agent deploy ./my-agent/ --tenant acme-corp --environment production

# Check deployment status
rayolly agent status custom_error_monitor --tenant acme-corp

# Rollback to previous version
rayolly agent rollback custom_error_monitor --tenant acme-corp --to-version 0.9.0
```

### 6.10 Versioning and Rollback

| Operation | Command | Description |
|---|---|---|
| List versions | `rayolly agent versions <name>` | Show all deployed versions |
| Deploy specific version | `rayolly agent deploy --version 1.2.0` | Deploy a specific version |
| Rollback | `rayolly agent rollback <name> --to-version <v>` | Revert to previous version |
| Canary deploy | `rayolly agent deploy --canary 10%` | Route 10% of triggers to new version |
| Promote canary | `rayolly agent promote <name>` | Promote canary to 100% |

---

## 7. Agent Marketplace

### 7.1 Overview

The Agent Marketplace is where the RayOlly ecosystem grows beyond the platform team. Community developers, partners, and customers publish agents that extend the platform for specific use cases, verticals, and integrations.

### 7.2 Marketplace Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    AGENT MARKETPLACE                             │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    CATALOG SERVICE                        │   │
│  │  • Agent listings with metadata                          │   │
│  │  • Search and filtering                                  │   │
│  │  • Ratings and reviews                                   │   │
│  │  • Version history                                       │   │
│  └──────────────────────────┬───────────────────────────────┘   │
│                              │                                   │
│  ┌──────────────┐  ┌────────▼──────┐  ┌──────────────────────┐ │
│  │ SUBMISSION   │  │ REGISTRY      │  │ INSTALLATION         │ │
│  │ PIPELINE     │  │ (Agent Store) │  │ SERVICE              │ │
│  │              │  │               │  │                      │ │
│  │ • Upload     │  │ • Packages    │  │ • Deploy to tenant   │ │
│  │ • Review     │  │ • Signatures  │  │ • Configure          │ │
│  │ • Security   │  │ • Manifests   │  │ • Dependency check   │ │
│  │   scan       │  │               │  │ • Health verify      │ │
│  │ • Certify    │  │               │  │                      │ │
│  └──────────────┘  └───────────────┘  └──────────────────────┘ │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   BILLING & REVENUE                       │   │
│  │  • Free agents (community)                               │   │
│  │  • Paid agents (per tenant/month)                        │   │
│  │  • Revenue sharing (70/30 creator/platform)              │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 7.3 Agent Categories

| Category | Description | Examples |
|---|---|---|
| **Monitoring** | Enhanced monitoring capabilities | Custom metric monitors, log pattern detectors |
| **Security** | Security-focused agents | Vulnerability scanners, compliance checkers, threat detectors |
| **Compliance** | Regulatory compliance | HIPAA audit agent, SOC 2 evidence collector, PCI-DSS validator |
| **Cost** | Cloud cost optimization | AWS cost advisor, spot instance optimizer, unused resource finder |
| **Database** | Database operations | Slow query analyzer, schema drift detector, backup monitor |
| **Kubernetes** | K8s-specific operations | Pod health monitor, resource quota advisor, RBAC auditor |
| **CI/CD** | Deployment pipeline | Deploy verifier, canary analyzer, rollback advisor |
| **Communication** | Notification and reporting | Custom report generator, executive briefing agent |
| **Integration** | Third-party integrations | Jira sync agent, ServiceNow bridge, PagerDuty enricher |

### 7.4 Verification and Certification

**Tiers**

| Tier | Badge | Requirements |
|---|---|---|
| Community | None | Passes automated security scan, basic validation |
| Verified | ✓ Verified | Community + manual code review, functionality testing |
| Certified | ★ Certified | Verified + performance benchmarks, SLA guarantees, official support |
| Built-in | ⚡ Official | Developed and maintained by RayOlly team |

**Certification Process**

```
Submit agent
     │
     ▼
┌──────────────────┐
│ Automated checks │
│ • Security scan  │
│ • Dependency     │
│   audit          │
│ • Test coverage  │
│   ≥ 80%         │
│ • Manifest valid │
└──────┬───────────┘
       │ PASS
       ▼
┌──────────────────┐
│ Manual review    │
│ • Code quality   │
│ • Security       │
│ • Performance    │
│ • Documentation  │
└──────┬───────────┘
       │ APPROVED
       ▼
┌──────────────────┐
│ Benchmark tests  │
│ • Load testing   │
│ • Token usage    │
│ • Error handling │
└──────┬───────────┘
       │ PASS
       ▼
  Published ★
```

### 7.5 Revenue Sharing Model

| Revenue Component | Creator Share | Platform Share |
|---|---|---|
| Paid agent subscription | 70% | 30% |
| Support add-on | 50% | 50% |
| Enterprise license | 60% | 40% |

Minimum payout: $100/month. Payments via Stripe Connect.

### 7.6 Installation and Configuration UI

```
┌─────────────────────────────────────────────────────────────────┐
│  MARKETPLACE > AWS Cost Optimizer Agent     ★ Certified         │
│                                                                 │
│  ┌───────────────────────────────────────────────────────┐      │
│  │  Analyzes AWS resource usage and recommends cost      │      │
│  │  optimizations. Generates weekly reports with         │      │
│  │  estimated savings.                                   │      │
│  │                                                       │      │
│  │  Author: CloudOps Solutions                           │      │
│  │  Version: 2.3.1  |  Downloads: 1,247  |  ⭐ 4.8/5   │      │
│  └───────────────────────────────────────────────────────┘      │
│                                                                 │
│  CONFIGURATION                                                  │
│  ┌───────────────────────────────────────────────────────┐      │
│  │  AWS Account IDs:  [___________________________]     │      │
│  │  Regions:          [☑ us-east-1] [☑ us-west-2]      │      │
│  │  Report Schedule:  [Weekly ▼]  Day: [Monday ▼]      │      │
│  │  Slack Channel:    [#cloud-costs____________]        │      │
│  │  Min Savings:      [$100_______] /month              │      │
│  └───────────────────────────────────────────────────────┘      │
│                                                                 │
│  PERMISSIONS REQUIRED                                           │
│  ☑ READ_DATA (metrics)                                         │
│  ☑ READ_CONFIG (AWS describe)                                  │
│  ☑ SEND_NOTIFICATION (Slack reports)                           │
│                                                                 │
│  DEPENDENCIES                                                   │
│  ☑ AWS Integration (configured)                                │
│  ☑ Slack Integration (configured)                              │
│                                                                 │
│  [ Install Agent ]  [ View Source ]  [ Documentation ]          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 8. Agent Orchestration

### 8.1 Event-Driven Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                 AGENT ORCHESTRATION ENGINE                        │
│                                                                 │
│  EVENT SOURCES              EVENT BUS (NATS)                    │
│  ┌─────────────┐           ┌────────────────────────────────┐   │
│  │ Anomaly     │──publish──▶│ subjects:                     │   │
│  │ Detector    │           │ • agents.trigger.anomaly       │   │
│  ├─────────────┤           │ • agents.trigger.incident      │   │
│  │ Alert       │──publish──▶│ • agents.trigger.deploy       │   │
│  │ Manager     │           │ • agents.trigger.schedule      │   │
│  ├─────────────┤           │ • agents.trigger.user_request  │   │
│  │ Deploy      │──publish──▶│ • agents.trigger.delegation   │   │
│  │ Pipeline    │           │ • agents.result.*              │   │
│  ├─────────────┤           │ • agents.approval.*            │   │
│  │ Scheduler   │──publish──▶│                               │   │
│  ├─────────────┤           └──────────┬─────────────────────┘   │
│  │ User        │──publish──▶          │                         │
│  │ Request     │                      │                         │
│  └─────────────┘                      │                         │
│                                       ▼                         │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                   TRIGGER MATCHER                          │ │
│  │                                                            │ │
│  │  For each event:                                           │ │
│  │  1. Match against all registered agent trigger conditions  │ │
│  │  2. Check debounce (don't re-trigger too soon)            │ │
│  │  3. Check tenant limits (concurrent agent cap)            │ │
│  │  4. Enqueue matched agents to task queue                  │ │
│  │                                                            │ │
│  └──────────────────────────┬─────────────────────────────────┘ │
│                              │                                   │
│  ┌──────────────────────────▼─────────────────────────────────┐ │
│  │                    TASK QUEUE                               │ │
│  │  NATS JetStream — durable, ordered per priority            │ │
│  │                                                            │ │
│  │  Priority levels:                                          │ │
│  │  P0 (CRITICAL) — Incident response, human requests         │ │
│  │  P1 (HIGH)     — High-severity anomaly investigation       │ │
│  │  P2 (NORMAL)   — Scheduled tasks, routine checks           │ │
│  │  P3 (LOW)      — Background analysis, reporting            │ │
│  └──────────────────────────┬─────────────────────────────────┘ │
│                              │                                   │
│  ┌──────────────────────────▼─────────────────────────────────┐ │
│  │                 RESOURCE MANAGER                            │ │
│  │                                                            │ │
│  │  • Tracks concurrent agents per tenant                     │ │
│  │  • Enforces limits (default: 10 concurrent per tenant)     │ │
│  │  • Manages LLM token budgets                               │ │
│  │  • Allocates sandbox containers from pool                  │ │
│  │  • Preempts low-priority agents if critical agent needs    │ │
│  │    resources                                               │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### 8.2 Multi-Agent Workflow Example

```
┌─────────────────────────────────────────────────────────────────────────┐
│            WORKFLOW: Production Incident Response                        │
│                                                                         │
│  EVENT: anomaly.severity=critical, service=payment-service              │
│                                                                         │
│  ┌────────────────┐                                                     │
│  │    Anomaly      │                                                    │
│  │  Investigator   │  Quick assessment: Is this real?                   │
│  └───────┬────────┘                                                     │
│          │ Result: actionable=true, confidence=0.88                     │
│          ▼                                                              │
│  ┌────────────────┐                                                     │
│  │  RCA Agent      │  Full root cause investigation                     │
│  └───────┬────────┘                                                     │
│          │ Result: root_cause identified, confidence=0.91               │
│          ▼                                                              │
│  ┌────────────────┐                                                     │
│  │   Incident      │  Creates incident, manages lifecycle               │
│  │  Commander      │                                                    │
│  └───────┬────────┘                                                     │
│          │                                                              │
│     ┌────┼─────────────┐                                                │
│     │    │             │                                                │
│     ▼    ▼             ▼                                                │
│  ┌─────┐ ┌──────┐ ┌──────────┐                                        │
│  │ SLO │ │Notify│ │ Runbook  │                                        │
│  │Guard│ │(Slack│ │ Executor │ ◄── Requires human approval             │
│  │     │ │PgDty)│ │          │                                        │
│  └──┬──┘ └──┬───┘ └────┬─────┘                                        │
│     │       │          │                                                │
│     └───────┼──────────┘                                                │
│             ▼                                                           │
│  ┌────────────────┐                                                     │
│  │   Incident      │  Compiles results, generates postmortem            │
│  │  Commander      │                                                    │
│  │  (final report) │                                                    │
│  └────────────────┘                                                     │
│                                                                         │
│  TOTAL TIME: ~3 minutes (vs 45+ minutes manual)                        │
│  TOKENS USED: ~120,000 across all agents                               │
│  TOOLS INVOKED: 47 total                                               │
│  HUMAN INVOLVEMENT: 1 approval (rollback)                              │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 8.3 Concurrent Execution Limits

| Tenant Tier | Concurrent Agents | Monthly Token Budget | Agent Types Available |
|---|---|---|---|
| Free | 2 | 500K tokens | Query Agent, basic Anomaly Investigator |
| Team | 5 | 5M tokens | All built-in agents |
| Business | 10 | 25M tokens | All built-in + marketplace + custom |
| Enterprise | 25 | 100M tokens | All + priority execution + dedicated resources |
| Dedicated | Unlimited | Unlimited | All + custom SLA + local models |

### 8.4 Queue Management

```python
# Agent task priority calculation
def calculate_priority(task: AgentTask) -> int:
    base_priority = task.priority.value  # P0=0, P1=1, P2=2, P3=3

    # Boost priority for active incidents
    if task.context.get("incident_active"):
        base_priority = min(base_priority, 0)  # Always P0

    # Boost for human-initiated requests (low latency expected)
    if task.trigger_type == "on_demand":
        base_priority = min(base_priority, 1)  # At least P1

    # De-prioritize if tenant is at token budget limit
    if task.tenant.token_usage_percent > 90:
        base_priority = max(base_priority, 2)  # At most P2

    return base_priority
```

---

## 9. Agent Memory & Knowledge

### 9.1 Memory Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                   MEMORY & KNOWLEDGE SYSTEM                      │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ WORKING MEMORY                        Store: Redis      │    │
│  │ Scope: Single execution               TTL: Execution    │    │
│  │                                                         │    │
│  │ • Investigation scratchpad                              │    │
│  │ • Current hypotheses and their status                   │    │
│  │ • Tool call results (to avoid redundant calls)          │    │
│  │ • Conversation context (for interactive sessions)       │    │
│  │ • Intermediate calculations and comparisons             │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ EPISODIC MEMORY                       Store: PostgreSQL │    │
│  │ Scope: Per tenant                     TTL: 90d default  │    │
│  │                                                         │    │
│  │ Records:                                                │    │
│  │ ┌─────────────────────────────────────────────────┐     │    │
│  │ │ {                                               │     │    │
│  │ │   "id": "ep-20260319-001",                      │     │    │
│  │ │   "timestamp": "2026-03-19T14:28:00Z",          │     │    │
│  │ │   "agent": "rca_agent",                         │     │    │
│  │ │   "event_type": "investigation",                │     │    │
│  │ │   "summary": "Redis pool exhaustion from...",   │     │    │
│  │ │   "tags": ["redis", "connection_pool"],         │     │    │
│  │ │   "outcome": "resolved_by_rollback",            │     │    │
│  │ │   "confidence": 0.92,                           │     │    │
│  │ │   "human_feedback": "correct",                  │     │    │
│  │ │   "embedding": [0.123, -0.456, ...]             │     │    │
│  │ │ }                                               │     │    │
│  │ └─────────────────────────────────────────────────┘     │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ SEMANTIC MEMORY (Knowledge Graph)     Store: PostgreSQL │    │
│  │ Scope: Per tenant                     + pgvector        │    │
│  │                                       TTL: Persistent   │    │
│  │                                                         │    │
│  │  ENTITIES:                                              │    │
│  │  ┌──────────┐    ┌──────────┐    ┌──────────┐         │    │
│  │  │ Services │───▶│ Teams    │───▶│ People   │         │    │
│  │  └────┬─────┘    └──────────┘    └──────────┘         │    │
│  │       │                                                │    │
│  │  ┌────▼─────┐    ┌──────────┐    ┌──────────┐         │    │
│  │  │Dependen- │    │ SLOs     │    │ Runbooks │         │    │
│  │  │cies     │    └──────────┘    └──────────┘         │    │
│  │  └──────────┘                                         │    │
│  │                                                         │    │
│  │  DOCUMENTS (embedded for retrieval):                    │    │
│  │  • Architecture documentation                           │    │
│  │  • Operational runbooks                                 │    │
│  │  • Past postmortems                                     │    │
│  │  • Team preferences and escalation paths                │    │
│  │  • Common failure patterns                              │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### 9.2 Knowledge Graph Schema

```sql
-- Core entity tables
CREATE TABLE knowledge_services (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    name TEXT NOT NULL,
    display_name TEXT,
    language TEXT,          -- python, java, go, etc.
    framework TEXT,         -- fastapi, spring-boot, etc.
    repository_url TEXT,
    team_id UUID REFERENCES knowledge_teams(id),
    tier TEXT,              -- critical, standard, best-effort
    created_at TIMESTAMPTZ DEFAULT now(),
    metadata JSONB,
    embedding vector(1536), -- For semantic search
    UNIQUE(tenant_id, name)
);

CREATE TABLE knowledge_dependencies (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    source_service_id UUID REFERENCES knowledge_services(id),
    target_service_id UUID REFERENCES knowledge_services(id),
    dependency_type TEXT,   -- sync, async, database, cache, queue
    protocol TEXT,          -- http, grpc, amqp, redis, postgres
    criticality TEXT,       -- critical, degraded, optional
    discovered_at TIMESTAMPTZ DEFAULT now(),
    last_seen_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE knowledge_teams (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    name TEXT NOT NULL,
    slack_channel TEXT,
    pagerduty_service_id TEXT,
    escalation_policy JSONB,
    working_hours JSONB,    -- {timezone, start, end, days}
    UNIQUE(tenant_id, name)
);

CREATE TABLE knowledge_documents (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    category TEXT NOT NULL,  -- runbook, architecture, postmortem, sop
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    tags TEXT[],
    embedding vector(1536),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Episodic memory
CREATE TABLE agent_episodes (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    agent_type TEXT NOT NULL,
    event_type TEXT NOT NULL,
    summary TEXT NOT NULL,
    details JSONB,
    tags TEXT[],
    outcome TEXT,
    confidence FLOAT,
    human_feedback TEXT,     -- correct, incorrect, partially_correct
    feedback_detail TEXT,
    embedding vector(1536),
    created_at TIMESTAMPTZ DEFAULT now(),
    expires_at TIMESTAMPTZ
);

-- Indexes for efficient retrieval
CREATE INDEX idx_episodes_tenant_agent ON agent_episodes(tenant_id, agent_type);
CREATE INDEX idx_episodes_tags ON agent_episodes USING gin(tags);
CREATE INDEX idx_episodes_embedding ON agent_episodes USING ivfflat(embedding vector_cosine_ops);
CREATE INDEX idx_documents_embedding ON knowledge_documents USING ivfflat(embedding vector_cosine_ops);
CREATE INDEX idx_services_embedding ON knowledge_services USING ivfflat(embedding vector_cosine_ops);
```

### 9.3 Memory Retrieval Strategy

When an agent needs context, the memory system uses a hybrid retrieval approach:

```
Query: "Redis connection pool issues on api-gateway"
        │
        ├── Exact match (tags, service name)
        │   → Episodes tagged "redis" + "api-gateway"
        │
        ├── Semantic search (embedding similarity)
        │   → Top-5 episodes by cosine similarity to query embedding
        │
        ├── Temporal relevance (recency boost)
        │   → Recent episodes weighted higher
        │
        └── Outcome weighting (successful resolutions preferred)
            → Episodes with positive human feedback weighted higher

Final ranking = 0.3 × exact_match + 0.4 × semantic_score
              + 0.2 × recency_score + 0.1 × outcome_score
```

---

## 10. Agent Security & Governance

### 10.1 Permission Model

```
┌─────────────────────────────────────────────────────────────────┐
│                    AGENT PERMISSION MODEL                        │
│                                                                 │
│  LEVEL 1: AGENT TYPE PERMISSIONS (set by platform)              │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Agent Type      │ Allowed Permission Levels              │   │
│  │─────────────────┼────────────────────────────────────────│   │
│  │ query_agent     │ READ_DATA, READ_CONFIG                 │   │
│  │ rca_agent       │ READ_DATA, READ_CONFIG, WRITE_INCIDENT│   │
│  │ incident_cmdr   │ READ_DATA, READ_CONFIG, WRITE_INCIDENT│   │
│  │                 │ SEND_NOTIFICATION, delegate            │   │
│  │ runbook_exec    │ READ_DATA, EXECUTE_RUNBOOK,           │   │
│  │                 │ INFRASTRUCTURE                         │   │
│  │ custom_agent    │ As declared in manifest (reviewed)     │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  LEVEL 2: TENANT POLICY (set by tenant admin)                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ • Which agents are enabled for this tenant               │   │
│  │ • Which permissions require human approval               │   │
│  │ • Approved scope (services, namespaces, environments)    │   │
│  │ • Token budgets and rate limits                          │   │
│  │ • Notification channels and escalation paths             │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  LEVEL 3: EXECUTION CONTEXT (enforced at runtime)               │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ • Data queries auto-scoped to tenant                     │   │
│  │ • Agent identity token (short-lived, scoped)             │   │
│  │ • Tool proxy validates every call                        │   │
│  │ • Container network policy enforced                      │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 10.2 Approval Workflows

```yaml
# Tenant approval policy configuration
approval_policy:
  # Actions that always require approval
  always_require_approval:
    - INFRASTRUCTURE
    - EXECUTE_RUNBOOK

  # Actions that require approval for production only
  production_approval:
    - WRITE_CONFIG
    - scale_service
    - restart_pod

  # Actions auto-approved
  auto_approve:
    - READ_DATA
    - READ_CONFIG
    - WRITE_INCIDENT
    - SEND_NOTIFICATION  # Can be changed to require approval

  # Approval settings
  approval_channels:
    - type: slack
      channel: "#agent-approvals"
    - type: pagerduty
      service: "agent-approvals"

  approval_timeout: 300s  # 5 minutes
  approval_escalation:
    - after: 120s
      notify: sre_team_lead
    - after: 240s
      notify: engineering_manager

  # Who can approve
  approvers:
    - role: on_call_engineer
    - role: sre_team_lead
    - role: tenant_admin
```

### 10.3 Audit Logging

Every agent action is recorded in an immutable audit log:

```json
{
  "audit_event": {
    "id": "audit-20260319-142300-001",
    "timestamp": "2026-03-19T14:23:00.123Z",
    "tenant_id": "tenant-acme-001",
    "agent_type": "rca_agent",
    "execution_id": "exec-abc-123",
    "action": "tool_call",
    "tool": "query_logs",
    "tool_input": {
      "query": "level:error AND service:api-gateway",
      "time_range": "last 2h",
      "limit": 100
    },
    "tool_output_summary": "Returned 427 log entries",
    "duration_ms": 234,
    "token_usage": {"input": 1200, "output": 3400},
    "data_accessed": {
      "type": "logs",
      "service_filter": "api-gateway",
      "time_range": "2026-03-19T12:23:00Z/2026-03-19T14:23:00Z",
      "record_count": 427
    }
  }
}
```

### 10.4 Kill Switch

```
┌─────────────────────────────────────────────────────────────────┐
│                    AGENT KILL SWITCH                             │
│                                                                 │
│  TRIGGER CONDITIONS (any triggers immediate kill):              │
│                                                                 │
│  1. Manual kill: Admin clicks "Stop Agent" in UI                │
│  2. Token budget exceeded: Agent used >110% of token limit      │
│  3. Time budget exceeded: Agent running >120% of timeout        │
│  4. Error loop detected: Same tool failing 5+ times             │
│  5. Anomalous behavior: Unusual tool call patterns detected     │
│  6. Tenant-wide kill: Admin disables all agents for tenant      │
│                                                                 │
│  KILL PROCEDURE:                                                │
│  1. Send SIGTERM to agent process                               │
│  2. Wait 5 seconds for graceful shutdown                        │
│  3. Send SIGKILL if still running                               │
│  4. Destroy sandbox container                                   │
│  5. Release all held resources                                  │
│  6. Log kill event to audit trail                               │
│  7. Notify tenant admin                                         │
│  8. Mark execution as KILLED in state store                     │
│                                                                 │
│  Any pending approval requests are auto-cancelled.              │
│  Any delegated sub-agents are also killed.                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 10.5 Rate Limiting

| Resource | Per Execution | Per Tenant/Hour | Per Tenant/Day |
|---|---|---|---|
| LLM tokens | Configurable (default: 100K) | Configurable | Configurable |
| Tool calls | 50 | 500 | 5,000 |
| Notifications sent | 10 | 50 | 200 |
| Infrastructure actions | 5 | 20 | 50 |
| Data query volume | 10M rows | 100M rows | 1B rows |

---

## 11. Agent Observability (Observing the Observers)

### 11.1 Agent Execution Traces

Every agent execution produces a trace using OpenTelemetry, viewable in RayOlly itself:

```
Trace: exec-abc-123 (RCA Agent)
│
├── [0ms] agent.start
│   ├── agent_type: rca_agent
│   ├── trigger: anomaly_event
│   └── tenant: acme-corp
│
├── [50ms] agent.plan
│   ├── goal: "Investigate latency spike on api-gateway"
│   ├── planned_steps: 6
│   └── tokens_used: 2,100
│
├── [120ms] tool.query_metrics
│   ├── duration: 234ms
│   ├── rows_returned: 120
│   └── finding: "p99 latency spike at 14:15"
│
├── [400ms] tool.get_service_map
│   ├── duration: 89ms
│   └── services_found: 4
│
├── [550ms] tool.get_deployments
│   ├── duration: 45ms
│   └── deployments_found: 1
│
├── [700ms] agent.reason (LLM call)
│   ├── duration: 1,200ms
│   ├── model: claude-sonnet-4-20250514
│   ├── tokens_input: 8,400
│   ├── tokens_output: 1,200
│   └── hypothesis: "Deployment caused Redis pool exhaustion"
│
├── [2000ms] tool.query_logs
│   ├── duration: 456ms
│   ├── rows_returned: 427
│   └── finding: "Redis connection pool exhausted errors"
│
├── [2500ms] tool.query_traces
│   ├── duration: 312ms
│   └── finding: "cache_lookup span 2000ms+ with timeout"
│
├── [3000ms] tool.get_past_rca
│   ├── duration: 123ms
│   └── similar_incidents: 1
│
├── [3200ms] agent.reason (LLM call — final synthesis)
│   ├── duration: 2,100ms
│   ├── model: claude-sonnet-4-20250514
│   ├── tokens_input: 22,000
│   ├── tokens_output: 3,400
│   └── confidence: 0.92
│
└── [5400ms] agent.complete
    ├── status: completed
    ├── total_duration: 5,400ms
    ├── total_tokens: 34,500
    ├── total_tool_calls: 7
    └── estimated_cost: $0.043
```

### 11.2 Agent Performance Metrics

| Metric | Description | Aggregation |
|---|---|---|
| `agent.execution.duration` | Total execution time | p50, p95, p99 by agent type |
| `agent.execution.count` | Number of executions | Sum by agent type, status |
| `agent.execution.success_rate` | Successful / total | Rate by agent type |
| `agent.llm.tokens_used` | LLM tokens consumed | Sum by agent type, model |
| `agent.llm.latency` | LLM API call latency | p50, p95, p99 by model |
| `agent.tool.calls` | Tool invocations | Count by tool name, agent type |
| `agent.tool.latency` | Tool execution time | p50, p95, p99 by tool name |
| `agent.tool.error_rate` | Tool call failures | Rate by tool name |
| `agent.queue.depth` | Tasks waiting in queue | Gauge by priority |
| `agent.queue.wait_time` | Time in queue before execution | p50, p95, p99 |
| `agent.approval.wait_time` | Time waiting for human approval | p50, p95, p99 |
| `agent.delegation.count` | Inter-agent delegations | Count by source → target |
| `agent.memory.retrieval_latency` | Memory lookup time | p50, p95 by memory type |
| `agent.cost.estimated` | Estimated cost per execution | Sum by agent type, tenant |

### 11.3 Agent Health Dashboard

```
┌─────────────────────────────────────────────────────────────────┐
│  AGENT HEALTH DASHBOARD                                         │
│                                                                 │
│  SYSTEM STATUS: ✓ All Systems Operational                       │
│                                                                 │
│  ACTIVE AGENTS          EXECUTIONS (24h)      LLM USAGE (24h)  │
│  ┌────────────────┐    ┌────────────────┐    ┌────────────────┐ │
│  │   Running: 7   │    │   Total: 342   │    │  Tokens: 4.2M  │ │
│  │   Queued:  3   │    │   Success: 328 │    │  Cost: $52.30  │ │
│  │   Waiting: 1   │    │   Failed:  14  │    │  Cache hit: 34%│ │
│  │   (approval)   │    │   Rate: 95.9%  │    │                │ │
│  └────────────────┘    └────────────────┘    └────────────────┘ │
│                                                                 │
│  AGENT TYPE BREAKDOWN                                           │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Agent            │ Runs │ Success │ Avg Time │ Avg Cost  │   │
│  │──────────────────┼──────┼─────────┼──────────┼──────────│   │
│  │ query_agent      │  187 │  98.4%  │    4.2s  │   $0.02  │   │
│  │ anomaly_invest.  │   89 │  94.4%  │   28.3s  │   $0.08  │   │
│  │ rca_agent        │   23 │  91.3%  │  142.0s  │   $0.43  │   │
│  │ slo_guardian     │   18 │ 100.0%  │   12.1s  │   $0.04  │   │
│  │ incident_cmdr    │    8 │  87.5%  │  245.0s  │   $1.20  │   │
│  │ capacity_planner │    4 │ 100.0%  │  180.0s  │   $0.85  │   │
│  │ runbook_exec     │    6 │  83.3%  │   90.0s  │   $0.35  │   │
│  │ auto_instrument  │    1 │ 100.0%  │  320.0s  │   $0.92  │   │
│  │ custom agents    │    6 │ 100.0%  │   15.0s  │   $0.05  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  RECENT FAILURES                                                │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ 14:45 rca_agent — LLM timeout (retried, succeeded)      │   │
│  │ 13:22 runbook_exec — Approval timeout (5m exceeded)      │   │
│  │ 11:07 anomaly_invest. — Max iterations reached           │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 11.4 Agent Cost Tracking

```sql
-- Agent cost tracking query
SELECT
    agent_type,
    date_trunc('day', started_at) AS day,
    count(*) AS executions,
    sum(llm_tokens_input + llm_tokens_output) AS total_tokens,
    sum(estimated_cost_usd) AS total_cost,
    avg(estimated_cost_usd) AS avg_cost_per_execution,
    avg(duration_seconds) AS avg_duration
FROM agent_executions
WHERE tenant_id = :tenant_id
  AND started_at > now() - INTERVAL '30 days'
GROUP BY agent_type, day
ORDER BY day DESC, total_cost DESC;
```

---

## 12. LLM Integration

### 12.1 Model Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      LLM INTEGRATION LAYER                      │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   MODEL ROUTER                            │   │
│  │                                                           │   │
│  │  Agent request ──▶ Select model based on:                 │   │
│  │                    • Agent type / task complexity          │   │
│  │                    • Tenant configuration                  │   │
│  │                    • Cost optimization preference          │   │
│  │                    • Availability / latency requirements   │   │
│  └──────────────────────────┬────────────────────────────────┘   │
│                              │                                   │
│         ┌────────────────────┼────────────────────┐              │
│         ▼                    ▼                    ▼              │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐        │
│  │ Claude API   │   │ Local Models │   │ Rule-Based   │        │
│  │ (Primary)    │   │ (vLLM)       │   │ Fallback     │        │
│  │              │   │              │   │              │        │
│  │ Models:      │   │ Models:      │   │ • Pattern    │        │
│  │ • Opus       │   │ • Llama 3.3  │   │   matching   │        │
│  │   (complex   │   │   70B        │   │ • Rule       │        │
│  │    RCA)      │   │ • Mistral    │   │   engine     │        │
│  │ • Sonnet     │   │   Large      │   │ • Heuristic  │        │
│  │   (standard) │   │ • Qwen 2.5   │   │   analysis   │        │
│  │ • Haiku      │   │   72B        │   │              │        │
│  │   (simple    │   │              │   │              │        │
│  │    queries)  │   │ For:         │   │ For:         │        │
│  │              │   │ • Air-gapped │   │ • LLM        │        │
│  │              │   │   deploys    │   │   unavailable│        │
│  │              │   │ • Data       │   │ • Budget     │        │
│  │              │   │   residency  │   │   exhausted  │        │
│  │              │   │ • Cost       │   │              │        │
│  │              │   │   sensitive  │   │              │        │
│  └──────────────┘   └──────────────┘   └──────────────┘        │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   PROMPT MANAGER                          │   │
│  │                                                           │   │
│  │  • Versioned prompt templates per agent type              │   │
│  │  • System prompts with agent role, tools, constraints     │   │
│  │  • Dynamic context injection (tenant info, service map)   │   │
│  │  • Few-shot examples from episodic memory                 │   │
│  │  • Prompt A/B testing framework                           │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                  RESPONSE CACHE                           │   │
│  │                                                           │   │
│  │  • Cache deterministic reasoning patterns                 │   │
│  │  • Key: hash(system_prompt + tool_results + query)        │   │
│  │  • TTL: 1 hour for factual, 5 min for time-sensitive      │   │
│  │  • Hit rate target: 20-40% for recurring patterns         │   │
│  │  • Estimated savings: 25% token cost reduction            │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 12.2 Model Selection Per Agent

| Agent Type | Default Model | Rationale | Fallback |
|---|---|---|---|
| RCA Agent | Claude Sonnet | Complex reasoning, multi-step analysis | Llama 3.3 70B |
| Incident Commander | Claude Sonnet | Coordination, synthesis, report generation | Llama 3.3 70B |
| Query Agent | Claude Haiku | Fast, high-volume, simpler translation | Mistral Large |
| Anomaly Investigator | Claude Sonnet | Pattern recognition, judgment calls | Llama 3.3 70B |
| Auto-Instrumentation | Claude Haiku | Template-based config generation | Rule-based |
| Capacity Planner | Claude Sonnet | Forecasting, complex analysis | Llama 3.3 70B |
| Runbook Executor | Claude Haiku | Parameter extraction, step execution | Rule-based |
| SLO Guardian | Claude Haiku | Calculations, threshold logic | Rule-based |

Tenants can override model selection per agent. Enterprise tier can use Claude Opus for all agents.

### 12.3 Token Budget Management

```python
class TokenBudgetManager:
    """Manages LLM token budgets per tenant and per execution."""

    async def check_budget(self, tenant_id: str, estimated_tokens: int) -> BudgetCheck:
        usage = await self.get_usage(tenant_id)

        return BudgetCheck(
            execution_remaining=usage.execution_limit - usage.execution_used,
            hourly_remaining=usage.hourly_limit - usage.hourly_used,
            daily_remaining=usage.daily_limit - usage.daily_used,
            monthly_remaining=usage.monthly_limit - usage.monthly_used,
            can_proceed=all([
                estimated_tokens <= usage.execution_limit - usage.execution_used,
                estimated_tokens <= usage.hourly_limit - usage.hourly_used,
                estimated_tokens <= usage.daily_limit - usage.daily_used,
                estimated_tokens <= usage.monthly_limit - usage.monthly_used,
            ]),
        )

    async def on_budget_exceeded(self, tenant_id: str, level: str):
        if level == "execution":
            # Kill current execution, try with cheaper model
            raise ExecutionBudgetExceeded()
        elif level == "hourly":
            # Queue remaining tasks, notify tenant admin
            await self.notify_admin(tenant_id, "Hourly token budget reached")
        elif level == "daily":
            # Switch all agents to rule-based fallback
            await self.enable_fallback_mode(tenant_id)
        elif level == "monthly":
            # Disable non-critical agents, alert tenant
            await self.disable_non_critical_agents(tenant_id)
```

### 12.4 Fallback Chain

```
LLM request
    │
    ▼
┌───────────────┐    SUCCESS
│ Claude API    │──────────────▶ Return result
└───────┬───────┘
        │ FAIL (timeout, rate limit, error)
        ▼
┌───────────────┐    SUCCESS
│ Local Model   │──────────────▶ Return result (may have lower quality)
│ (vLLM)        │
└───────┬───────┘
        │ FAIL (not available, error)
        ▼
┌───────────────┐    SUCCESS
│ Rule-Based    │──────────────▶ Return result (limited capability)
│ Engine        │
└───────┬───────┘
        │ FAIL (no matching rules)
        ▼
┌───────────────┐
│ Graceful      │  Log failure, notify admin,
│ Degradation   │  return "unable to complete" with partial results
└───────────────┘
```

---

## 13. Human-Agent Interaction

### 13.1 Chat Interface

The chat interface is the primary human-agent interaction surface within the RayOlly dashboard:

```
┌─────────────────────────────────────────────────────────────────┐
│  RAYOLLY > Agent Chat                              ⚙ Settings  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                                                          │   │
│  │  YOU: Why is the checkout page slow right now?           │   │
│  │                                                          │   │
│  │  ─────────────────────────────────────────────────────── │   │
│  │                                                          │   │
│  │  QUERY AGENT:                                            │   │
│  │  I looked at the checkout-service metrics for the last   │   │
│  │  hour. Here's what I found:                              │   │
│  │                                                          │   │
│  │  • p99 latency is currently 3.2s (normally ~400ms)      │   │
│  │  • The spike started at 15:42 UTC (18 minutes ago)      │   │
│  │  • Error rate is normal (0.12%)                         │   │
│  │  • Request rate is normal (no traffic spike)            │   │
│  │                                                          │   │
│  │  [📊 View latency chart]  [📋 View query used]          │   │
│  │                                                          │   │
│  │  This looks like a latency issue without errors.         │   │
│  │  Would you like me to:                                   │   │
│  │  • Investigate the root cause (start RCA Agent)         │   │
│  │  • Check if there were recent deployments               │   │
│  │  • Show slow traces from the last 20 minutes            │   │
│  │                                                          │   │
│  │  ─────────────────────────────────────────────────────── │   │
│  │                                                          │   │
│  │  YOU: Investigate the root cause                         │   │
│  │                                                          │   │
│  │  ─────────────────────────────────────────────────────── │   │
│  │                                                          │   │
│  │  RCA AGENT:                                              │   │
│  │  Starting investigation into checkout-service latency    │   │
│  │  spike...                                                │   │
│  │                                                          │   │
│  │  ⏳ Step 1/5: Analyzing latency distribution...         │   │
│  │  ✓ Step 2/5: Checking downstream dependencies...        │   │
│  │  ✓ Step 3/5: Reviewing recent deployments...            │   │
│  │  ⏳ Step 4/5: Examining slow traces...                  │   │
│  │                                                          │   │
│  │  [Show reasoning] [Stop investigation]                   │   │
│  │                                                          │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Ask a question or give an instruction...         [Send] │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 13.2 Contextual Agent Suggestions

When users are viewing dashboards, agents proactively offer relevant insights:

```
┌─────────────────────────────────────────────────────────────────┐
│  DASHBOARD: api-gateway                                         │
│                                                                 │
│  [Latency chart showing spike]                                  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  💡 AGENT INSIGHT                                        │   │
│  │                                                          │   │
│  │  I noticed this latency spike correlates with deploy     │   │
│  │  v2.14.3 (18 minutes ago). Similar pattern to incident   │   │
│  │  INC-2026-0203 (Redis connection pool exhaustion).       │   │
│  │                                                          │   │
│  │  [Investigate]  [Dismiss]  [Not helpful]                 │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 13.3 Notification Integration

| Platform | Integration Type | Capabilities |
|---|---|---|
| **Slack** | Bot + slash commands | `/rayolly ask <question>`, `/rayolly investigate <service>`, interactive approval buttons |
| **Microsoft Teams** | Bot + adaptive cards | Chat with agents, approval workflows, rich incident cards |
| **PagerDuty** | Event API + webhook | Auto-create incidents, enrich with RCA, auto-resolve |
| **Email** | SMTP integration | Scheduled reports, incident summaries, SLO alerts |
| **Webhook** | Custom HTTP endpoints | Generic integration for any system |

### 13.4 Feedback Mechanism

```python
# Feedback API
class AgentFeedback:
    execution_id: str          # Which agent execution
    rating: Literal["positive", "negative", "partial"]
    feedback_text: str | None  # Optional detailed feedback
    corrections: dict | None   # What the correct answer should have been

# Example feedback stored
{
    "execution_id": "exec-abc-123",
    "agent_type": "rca_agent",
    "rating": "positive",
    "feedback_text": "Root cause was correct, but missed that the
                      Redis config was also wrong in staging",
    "corrections": {
        "additional_root_cause": "Redis maxclients set to 100 in staging config"
    },
    "created_by": "jsmith@acme.com",
    "created_at": "2026-03-19T15:30:00Z"
}
```

Feedback is stored in episodic memory and used to improve future agent performance.

### 13.5 Agent Transparency

Every agent decision is explainable. Users can click "Show reasoning" to see:

```
┌──────────────────────────────────────────────────────────────┐
│  REASONING TRACE: RCA Agent (exec-abc-123)                   │
│                                                              │
│  STEP 1: I queried p99 latency for api-gateway over the     │
│  last 2 hours. The data shows a clear spike from 120ms to   │
│  2400ms beginning at 14:15 UTC.                             │
│                                                              │
│  STEP 2: I checked the service dependency map. api-gateway   │
│  depends on: user-service (HTTP), payment-service (gRPC),   │
│  redis-cache (Redis), postgres-primary (PostgreSQL).         │
│                                                              │
│  STEP 3: I looked for recent deployments. Found api-gateway  │
│  v2.14.3 deployed at 14:12 UTC — 3 minutes before the       │
│  anomaly. This is a strong temporal correlation.             │
│                                                              │
│  STEP 4: I searched error logs. Found 427 instances of       │
│  "Redis connection pool exhausted" starting at 14:14 UTC.   │
│  This confirms the Redis connection is the bottleneck.       │
│                                                              │
│  STEP 5: I examined slow traces. The new "cache_lookup"      │
│  span (not present in v2.14.2) is taking 2000ms+ and        │
│  consistently fails with timeout.                            │
│                                                              │
│  STEP 6: I checked past incidents. Found a similar incident  │
│  on 2026-02-03 with the same Redis pool exhaustion pattern. │
│  That incident was resolved by increasing pool size.         │
│                                                              │
│  CONCLUSION: With 0.92 confidence, the root cause is the     │
│  new caching layer in v2.14.3 creating per-request Redis    │
│  connections instead of using the connection pool.           │
│                                                              │
│  [View raw LLM inputs/outputs]  [View tool call details]    │
└──────────────────────────────────────────────────────────────┘
```

---

## 14. Multi-Tenancy

### 14.1 Tenant Isolation Model

```
┌─────────────────────────────────────────────────────────────────┐
│                 MULTI-TENANT AGENT ISOLATION                     │
│                                                                 │
│  ┌──────────────────┐  ┌──────────────────┐                    │
│  │ TENANT A         │  │ TENANT B         │                    │
│  │ (Acme Corp)      │  │ (Globex Inc)     │                    │
│  │                  │  │                  │                    │
│  │ ┌──────────────┐ │  │ ┌──────────────┐ │                    │
│  │ │ Agent Config │ │  │ │ Agent Config │ │  Separate configs  │
│  │ │ • Enabled    │ │  │ │ • Enabled    │ │                    │
│  │ │   agents     │ │  │ │   agents     │ │                    │
│  │ │ • Policies   │ │  │ │ • Policies   │ │                    │
│  │ │ • Budgets    │ │  │ │ • Budgets    │ │                    │
│  │ └──────────────┘ │  │ └──────────────┘ │                    │
│  │                  │  │                  │                    │
│  │ ┌──────────────┐ │  │ ┌──────────────┐ │                    │
│  │ │ Knowledge    │ │  │ │ Knowledge    │ │  Separate          │
│  │ │ Base         │ │  │ │ Base         │ │  knowledge stores  │
│  │ │ (services,   │ │  │ │ (services,   │ │                    │
│  │ │  teams,      │ │  │ │  teams,      │ │                    │
│  │ │  runbooks)   │ │  │ │  runbooks)   │ │                    │
│  │ └──────────────┘ │  │ └──────────────┘ │                    │
│  │                  │  │                  │                    │
│  │ ┌──────────────┐ │  │ ┌──────────────┐ │                    │
│  │ │ Episodic     │ │  │ │ Episodic     │ │  Separate          │
│  │ │ Memory       │ │  │ │ Memory       │ │  memory stores     │
│  │ │ (past        │ │  │ │ (past        │ │                    │
│  │ │  incidents)  │ │  │ │  incidents)  │ │                    │
│  │ └──────────────┘ │  │ └──────────────┘ │                    │
│  │                  │  │                  │                    │
│  │ ┌──────────────┐ │  │ ┌──────────────┐ │                    │
│  │ │ Execution    │ │  │ │ Execution    │ │  Separate          │
│  │ │ Sandboxes    │ │  │ │ Sandboxes    │ │  containers        │
│  │ │ (isolated)   │ │  │ │ (isolated)   │ │                    │
│  │ └──────────────┘ │  │ └──────────────┘ │                    │
│  │                  │  │                  │                    │
│  └──────────────────┘  └──────────────────┘                    │
│                                                                 │
│  SHARED (platform-level, no tenant data mixing):               │
│  • Agent runtime binaries                                       │
│  • LLM API connection pools                                    │
│  • Marketplace catalog                                          │
│  • Platform monitoring                                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 14.2 Per-Tenant Configuration

```yaml
# Tenant agent configuration
tenant:
  id: tenant-acme-001
  name: "Acme Corp"

  agents:
    enabled:
      - rca_agent
      - incident_commander
      - query_agent
      - anomaly_investigator
      - slo_guardian
      - runbook_executor
    disabled:
      - auto_instrumentation  # Not needed — using auto-instrumentation operator
      - capacity_planner      # Will enable in Q2

    custom_agents:
      - custom_error_monitor
      - aws_cost_optimizer

  policies:
    auto_approve_notifications: true
    auto_approve_config_writes: false
    require_approval_for_runbooks: true
    require_approval_for_infrastructure: true

  budgets:
    concurrent_agents: 10
    monthly_token_limit: 25000000  # 25M tokens
    daily_token_limit: 1500000     # 1.5M tokens
    hourly_token_limit: 200000     # 200K tokens

  llm:
    preferred_provider: "claude"  # claude, local, auto
    preferred_model_tier: "standard"  # economy, standard, premium
    allow_external_llm: true  # If false, only local models

  notifications:
    default_slack_channel: "#sre-alerts"
    incident_channel: "#incidents"
    agent_approval_channel: "#agent-approvals"
    pagerduty_service: "P1234567"
```

### 14.3 Resource Isolation

| Resource | Isolation Mechanism |
|---|---|
| Data access | Row-level security with `tenant_id` on all queries |
| Agent execution | Separate container per execution, no shared state |
| Memory stores | Partitioned by `tenant_id`, indexed separately |
| LLM calls | Separate API keys (optional), budget tracking per tenant |
| Network | Network policies prevent cross-tenant container communication |
| Audit logs | Partitioned by tenant, separate access controls |
| Encryption | Per-tenant encryption keys for knowledge base (Enterprise) |

---

## 15. Technology Stack

### 15.1 Core Components

| Component | Technology | Rationale |
|---|---|---|
| **Agent Runtime** | Python 3.12+ async (asyncio) | LLM SDK ecosystem, AI/ML library support, async for concurrent tool calls |
| **Agent Framework** | Custom orchestrator + Claude Agent SDK patterns | Production control, not locked to single framework |
| **LLM (Primary)** | Claude API (Anthropic) | Best reasoning for complex RCA, structured tool use, long context |
| **LLM (Local)** | vLLM serving Llama 3.3 / Mistral Large | Air-gapped deployments, data residency, cost optimization |
| **Memory (Knowledge)** | PostgreSQL 16 + pgvector | Hybrid relational + vector search, mature ecosystem |
| **Memory (Session)** | Redis 7+ (or Valkey) | Sub-ms working memory, session state, caching |
| **Message Bus** | NATS JetStream | High-throughput event-driven triggers, durable queues, simple ops |
| **Execution Sandbox** | gVisor containers (runsc) | Lightweight isolation with strong security boundaries |
| **Container Orchestration** | Kubernetes | Agent container lifecycle management, resource limits |
| **API Gateway** | Custom (Go) | Auth, rate limiting, tenant routing, WebSocket for chat |
| **Prompt Management** | Custom service | Versioned prompts, A/B testing, template rendering |
| **Agent Packaging** | OCI container images | Standard packaging, versioning, registry support |

### 15.2 Infrastructure Requirements

| Component | Minimum (Dev) | Production (per cluster) |
|---|---|---|
| Agent Orchestrator | 2 CPU, 4 GB RAM | 4 CPU, 16 GB RAM (3 replicas) |
| Agent Worker Pool | 4 CPU, 8 GB RAM | 16 CPU, 64 GB RAM (auto-scaling) |
| PostgreSQL (knowledge) | 2 CPU, 4 GB RAM, 50 GB SSD | 8 CPU, 32 GB RAM, 500 GB NVMe |
| Redis (session) | 1 CPU, 2 GB RAM | 4 CPU, 16 GB RAM (cluster mode) |
| NATS | 1 CPU, 1 GB RAM | 2 CPU, 8 GB RAM (3-node cluster) |
| vLLM (local models) | 1x A100 40GB | 2-4x A100 80GB (model dependent) |

---

## 16. Performance Requirements

### 16.1 Latency Targets

| Operation | Target | P99 | Notes |
|---|---|---|---|
| Agent trigger → queued | < 500ms | < 1s | Event bus to queue |
| Queue → execution start | < 5s | < 15s | Container allocation |
| Query Agent response | < 10s | < 30s | Simple NL → query → result |
| Anomaly Investigator | < 60s | < 120s | Quick assessment |
| RCA Agent investigation | < 3min | < 5min | Full root cause analysis |
| Incident Commander setup | < 30s | < 60s | Incident creation + first notification |
| Runbook execution | < 2min | < 5min | Depends on runbook complexity |
| SLO check cycle | < 30s | < 60s | Per-SLO evaluation |
| Memory retrieval (episodic) | < 200ms | < 500ms | Vector similarity search |
| Memory retrieval (semantic) | < 100ms | < 300ms | Entity lookup |
| Tool call (data query) | < 2s | < 5s | Depends on query complexity |
| Human approval response | N/A | Timeout: 5min | Human dependent |

### 16.2 Throughput Targets

| Metric | Target |
|---|---|
| Concurrent agent executions per cluster | 1,000 |
| Agent executions per hour per cluster | 10,000 |
| Events processed per second (trigger matching) | 50,000 |
| LLM requests per second per cluster | 200 |
| Tool calls per second per cluster | 5,000 |

### 16.3 Availability Targets

| Component | Target | Recovery Time |
|---|---|---|
| Agent Orchestration Service | 99.9% | < 30s (auto-restart) |
| Agent Execution Runtime | 99.9% | < 10s (new container) |
| LLM Integration (with fallback) | 99.95% | < 5s (failover to local/rule-based) |
| Memory Services | 99.9% | < 30s (replica failover) |
| Event Bus | 99.99% | < 5s (NATS cluster failover) |

---

## 17. Example Agent Workflows

### 17.1 Scenario: Production API Latency Spike

**Context**: Friday evening, 6:47 PM. The on-call engineer is at dinner. The payment-service API starts responding slowly.

```
TIME     EVENT
──────── ─────────────────────────────────────────────────────────────

18:47:00 ANOMALY DETECTOR: Latency anomaly detected
         service=payment-service, p99=4200ms (baseline: 250ms)
         severity=CRITICAL

18:47:01 TRIGGER MATCHER: Matches anomaly_investigator trigger
         → Queued with priority P1

18:47:02 ANOMALY INVESTIGATOR: Execution started
         → Queries metrics: Confirms latency spike across all endpoints
         → Queries error rate: 12% (baseline: 0.1%)
         → Checks deployments: payment-service v4.1.0 deployed at 18:40
         → Assessment: ACTIONABLE (confidence: 0.91)
         → Escalates to RCA Agent

18:47:35 RCA AGENT: Execution started (delegated from Anomaly Investigator)
         → Queries slow traces: All slow traces show new "fraud-check" span
         → Queries logs: "External fraud API timeout" errors (340 in 7 min)
         → Checks change log: v4.1.0 added synchronous fraud check API call
         → Searches knowledge base: Fraud API has 500ms SLA, currently 8s+
         → Checks past incidents: No similar incidents found
         → Root cause: New fraud check API call in v4.1.0 is synchronous
           and the external fraud API is degraded, blocking all payment
           requests. (Confidence: 0.94)

18:49:12 INCIDENT COMMANDER: Triggered by high-confidence RCA
         → Creates incident INC-2026-0319-003 (SEV1)
         → Posts to #incidents Slack channel with summary
         → Pages on-call engineer via PagerDuty

18:49:30 SLO GUARDIAN: Delegated by Incident Commander
         → payment-service SLO: 99.99% availability
         → Current burn rate: 47x normal
         → Projected SLO breach in: 2.1 hours
         → Error budget consumed this incident: 0.8% so far

18:49:45 INCIDENT COMMANDER: Delegates remediation assessment
         → RCA Agent recommends: Rollback to v4.0.9 (removes fraud check)
         → Alternative: Make fraud check async (code change required)
         → Recommends rollback as immediate action

18:50:00 RUNBOOK EXECUTOR: Triggered by Incident Commander
         → Selects runbook: rollback_deployment
         → Parameters: {service: payment-service, target: v4.0.9}
         → Pre-checks pass
         → REQUESTS HUMAN APPROVAL

18:50:05 NOTIFICATION: Slack message to #agent-approvals
         "🔴 APPROVAL REQUIRED: Rollback payment-service to v4.0.9
          Reason: Synchronous fraud check API causing 4.2s latency
          Confidence: 94%
          [Approve] [Reject] [Show details]"

18:51:30 ON-CALL ENGINEER: Approves via Slack button (from phone at dinner)

18:51:31 RUNBOOK EXECUTOR: Approval received
         → Executes rollback: kubectl rollout undo deployment/payment-service
         → Waits for rollout: 45 seconds
         → Post-check: Error rate dropping...

18:52:30 MONITORING: payment-service metrics normalizing
         → p99 latency: 280ms (recovered)
         → Error rate: 0.15% (recovered)

18:52:45 INCIDENT COMMANDER: Detects recovery
         → Updates incident status: MITIGATED
         → Posts recovery notification to #incidents
         → Generates postmortem draft
         → Creates follow-up Jira tickets:
           1. Make fraud check async (priority: HIGH)
           2. Add circuit breaker for external API calls (priority: HIGH)
           3. Add external API latency monitoring (priority: MEDIUM)

18:53:00 INCIDENT COMMANDER: Closes incident
         Total duration: 6 minutes
         Human involvement: 1 approval (90 seconds)
         LLM tokens used: 89,000 across all agents
         Estimated agent cost: $1.12

         WITHOUT AGENTS: ~45 minutes minimum
         (Engineer called, opens laptop, investigates manually,
          identifies cause, runs rollback, monitors recovery)
```

### 17.2 Scenario: Gradual Memory Leak Detection

**Context**: Tuesday morning. No one has noticed anything, but the capacity-planning agent's weekly scan finds something.

```
TIME     EVENT
──────── ─────────────────────────────────────────────────────────────

09:00:00 CAPACITY PLANNER: Scheduled weekly scan starts

09:02:30 CAPACITY PLANNER: Anomaly in memory usage trend
         → search-service memory usage: growing 2.1% daily for 12 days
         → No corresponding increase in request rate
         → Current: 78% of pod memory limit
         → Projected OOM: 8 days at current rate

09:03:00 CAPACITY PLANNER: Deep analysis
         → Checks deployment history: search-service v2.8.0 deployed 14 days ago
         → Memory growth started ~2 days after deploy (matches cache warm-up)
         → No similar pattern in other services
         → Searches knowledge base: v2.8.0 changelog mentions "new in-memory
           search index cache"

09:04:00 CAPACITY PLANNER: Generates report
         → Finding: Likely memory leak in search-service v2.8.0's new
           in-memory cache (not bounded, growing linearly)
         → Recommendation: Investigate cache eviction policy
         → Urgency: Medium (8 days before OOM kill)
         → Posts finding to #sre-weekly-report

09:04:30 NOTIFICATION: Slack message to #sre-weekly-report
         "📊 Capacity Planning: search-service memory leak detected
          Memory growing 2.1%/day since v2.8.0 deploy.
          Projected OOM in 8 days.
          Likely cause: Unbounded in-memory search cache.
          [View full report] [Investigate now] [Ignore]"
```

### 17.3 Scenario: Natural Language Data Exploration

**Context**: Wednesday afternoon. VP of Engineering wants to understand system reliability for a board presentation.

```
VP: "How reliable have our customer-facing services been this quarter?"

QUERY AGENT:
  I've analyzed the SLO data for all customer-facing services (tier: critical)
  for Q1 2026 (Jan 1 - Mar 19):

  SERVICE              SLO TARGET   ACHIEVED   ERROR BUDGET
  ─────────────────────────────────────────────────────────
  api-gateway          99.95%       99.91%     ⚠ 62.1% remaining
  payment-service      99.99%       99.98%     ✓ 78.4% remaining
  user-service         99.9%        99.97%     ✓ 97.0% remaining
  search-service       99.5%        99.82%     ✓ 96.4% remaining
  checkout-service     99.95%       99.96%     ✓ 88.2% remaining

  Overall platform availability: 99.94%

  Key incidents this quarter:
  • 3 SEV1 incidents (avg resolution: 12 minutes)
  • 8 SEV2 incidents (avg resolution: 34 minutes)
  • api-gateway consumed most error budget (2 incidents)

  Would you like me to:
  • Generate a board-ready reliability report?
  • Compare with last quarter?
  • Drill into the api-gateway incidents?

VP: "Compare with last quarter and generate a board-ready report"

QUERY AGENT:
  Q4 2025 vs Q1 2026 comparison:

  METRIC                    Q4 2025    Q1 2026    CHANGE
  ─────────────────────────────────────────────────────
  Platform availability     99.87%     99.94%     +0.07%
  SEV1 incidents            7          3          -57%
  Avg MTTR (SEV1)          47 min     12 min     -74%
  Avg MTTR (SEV2)          82 min     34 min     -59%
  SLO breaches             2          0          -100%
  Error budget consumed    avg 71%    avg 34%    -52%

  Note: MTTR improvement correlates with AI Agent deployment in
  January 2026. Agents handled 68% of incident investigation
  autonomously.

  [📄 Download board report (PDF)]
  [📊 View interactive dashboard]
```

### 17.4 Scenario: New Deployment with Auto-Verification

**Context**: Thursday at 2 PM. A developer deploys user-service v5.0.0, a major version with database schema changes.

```
TIME     EVENT
──────── ─────────────────────────────────────────────────────────────

14:00:00 DEPLOY PIPELINE: user-service v5.0.0 deployed to production
         → Event published to agents.trigger.deploy

14:00:01 ANOMALY INVESTIGATOR: Watching for post-deploy anomalies
         → Baseline captured: error_rate=0.08%, p99=180ms

14:00:01 SLO GUARDIAN: Monitoring user-service SLO burn rate

14:05:00 ANOMALY INVESTIGATOR: 5-minute check
         → error_rate: 0.09% (within normal variance)
         → p99 latency: 195ms (within normal variance)
         → No anomaly detected

14:15:00 ANOMALY INVESTIGATOR: 15-minute check
         → error_rate: 0.10% (still normal)
         → p99 latency: 210ms (slight increase, within bounds)
         → New: database query latency for "user_profiles" table up 40%
         → Assessment: Monitoring — the db query increase may indicate
           schema migration impact but not yet at anomaly threshold

14:30:00 ANOMALY INVESTIGATOR: 30-minute check
         → error_rate: 0.11% (still normal)
         → p99 latency: 240ms (trending up but within SLO)
         → Database query latency: still elevated but stable
         → Assessment: Likely expected behavior from schema change
         → Logs note for future reference in episodic memory

14:30:30 NOTIFICATION: Slack message to #deployments
         "✅ user-service v5.0.0 — 30-minute post-deploy check passed
          All metrics within SLO bounds.
          Note: DB query latency for user_profiles table is 40% higher
          than pre-deploy baseline. This appears stable and may be
          expected from the schema changes. Worth monitoring.
          [View details]"
```

---

## 18. Success Metrics

### 18.1 Core KPIs

| Metric | Baseline (without agents) | Target (with agents) | Measurement |
|---|---|---|---|
| Mean Time to Detect (MTTD) | 15 minutes | < 2 minutes | From anomaly start to detection |
| Mean Time to Investigate | 30 minutes | < 3 minutes | From detection to root cause |
| Mean Time to Resolve (MTTR) | 60 minutes | < 10 minutes | From detection to resolution |
| Incidents requiring human wake-up | 100% | < 30% | Auto-resolved vs human-escalated |
| RCA accuracy | N/A (manual) | > 90% | Verified by human review |
| False positive rate (anomaly) | 40% (rule-based) | < 15% | Agent-classified noise |
| SLO breach prediction accuracy | N/A | > 85% | Predicted vs actual breaches |
| Time to first value (new agent) | N/A | < 8 hours | SDK → deployed → working agent |

### 18.2 Adoption Metrics

| Metric | 3-Month Target | 6-Month Target | 12-Month Target |
|---|---|---|---|
| Tenants with agents enabled | 50% | 80% | 95% |
| Agent executions per day (platform) | 5,000 | 25,000 | 100,000 |
| Custom agents deployed | 50 | 200 | 1,000 |
| Marketplace agents published | 20 | 75 | 250 |
| Agent chat interactions per day | 1,000 | 10,000 | 50,000 |
| Positive agent feedback rate | 70% | 80% | 90% |

### 18.3 Business Metrics

| Metric | Target | Impact |
|---|---|---|
| Agent platform as primary purchase driver | 40% of new enterprise deals | Revenue attribution |
| Net Promoter Score lift | +15 points vs pre-agent baseline | Customer satisfaction |
| Expansion revenue from agent marketplace | $1M ARR in year 1 | Ecosystem revenue |
| Competitive win rate vs Datadog (agent feature) | 60% when agents are evaluated | Market position |
| Customer operational cost reduction | 40% reduction in SRE toil hours | Customer value |

---

## 19. Dependencies and Risks

### 19.1 Dependencies

| Dependency | Type | Mitigation |
|---|---|---|
| Claude API availability and latency | External service | Local model fallback, response caching, rule-based fallback |
| Claude API pricing stability | Business | Multi-model support, token budget management, negotiate volume pricing |
| RayOlly data platform (logs, metrics, traces) | Internal (PRD-01, PRD-02, PRD-03) | Agent platform can launch incrementally as data features ship |
| Anomaly detection engine | Internal (PRD-04) | Agents can also be triggered manually or on schedule |
| Kubernetes infrastructure | Infrastructure | Support non-K8s deployment for agent runtime |
| Customer willingness to trust autonomous agents | Market | Start with read-only agents, progressive trust building, transparency |

### 19.2 Risks

| Risk | Severity | Likelihood | Mitigation |
|---|---|---|---|
| **LLM hallucination leading to wrong RCA** | High | Medium | Confidence scoring, human review for critical actions, multi-agent validation, feedback loop |
| **LLM cost explosion with high agent usage** | High | Medium | Token budgets, model tiering, caching, local model fallback |
| **Agent takes destructive action incorrectly** | Critical | Low | Approval workflows, permission model, sandbox isolation, kill switch, no auto-approve for infrastructure |
| **Cross-tenant data leakage via agent** | Critical | Low | Row-level security, separate containers, tenant-scoped tokens, penetration testing, security audit |
| **Prompt injection via log data** | High | Medium | Input sanitization, separate system/user prompt boundaries, output validation, no code execution from LLM output |
| **Agent latency too high for incident response** | Medium | Medium | Model optimization, caching, parallel tool calls, pre-computation |
| **User distrust of autonomous systems** | Medium | High | Transparency (show reasoning), progressive autonomy levels, easy override, measurable results |
| **SDK adoption too complex** | Medium | Medium | Excellent documentation, templates, examples, CLI tooling, support |
| **Marketplace quality control** | Medium | Medium | Certification tiers, automated testing, security scanning, reviews |
| **Regulatory compliance concerns** | High | Medium | Audit trails, data residency support (local models), SOC 2 compliance, GDPR data handling |

### 19.3 Open Questions

| ID | Question | Owner | Due Date |
|----|----------|-------|----------|
| OQ-1 | Should agents be able to create PRs for code fixes? | Product + Engineering | 2026-04-15 |
| OQ-2 | What is the pricing model for agent tokens (bundled vs usage-based)? | Product + Finance | 2026-04-01 |
| OQ-3 | Should we support agent-to-agent communication across tenants for MSP use cases? | Architecture | 2026-05-01 |
| OQ-4 | What compliance certifications are required before agents can execute runbooks? | Security + Legal | 2026-04-15 |
| OQ-5 | Should marketplace agents run in the platform's LLM context or bring their own? | Architecture | 2026-04-01 |
| OQ-6 | What is the SLA for agent response time that we commit to in enterprise contracts? | Product + SRE | 2026-04-15 |

---

## Appendix A: Glossary

| Term | Definition |
|---|---|
| Agent | An autonomous AI-powered actor that perceives, reasons, and acts within the RayOlly platform |
| Agent Execution | A single invocation of an agent, from trigger to completion |
| Delegation | When one agent invokes another agent to perform a sub-task |
| Episodic Memory | Agent's learned experiences from past investigations and outcomes |
| Kill Switch | Mechanism to immediately terminate a running agent |
| Reasoning Loop | The iterative think-act-observe cycle that agents use to investigate |
| RCA | Root Cause Analysis — determining the fundamental cause of an incident |
| Runbook | A predefined sequence of operational steps to diagnose or remediate an issue |
| Sandbox | An isolated execution environment for agent code |
| Semantic Memory | Structured knowledge about the tenant's services, teams, and infrastructure |
| SLO | Service Level Objective — a target reliability metric |
| Tool | A capability that an agent can invoke (query data, send notification, etc.) |
| Working Memory | Temporary state during a single agent execution |

## Appendix B: API Reference Summary

### Agent Management API

```
POST   /api/v1/agents                    Create/register an agent
GET    /api/v1/agents                    List agents for tenant
GET    /api/v1/agents/{id}               Get agent details
PUT    /api/v1/agents/{id}               Update agent configuration
DELETE /api/v1/agents/{id}               Delete/retire agent
POST   /api/v1/agents/{id}/deploy        Deploy agent version
POST   /api/v1/agents/{id}/invoke        Manually invoke agent
POST   /api/v1/agents/{id}/stop          Stop running agent (kill switch)
GET    /api/v1/agents/{id}/executions    List agent executions
GET    /api/v1/agents/{id}/metrics       Get agent performance metrics
```

### Agent Execution API

```
GET    /api/v1/executions/{id}           Get execution details
GET    /api/v1/executions/{id}/trace     Get execution trace
GET    /api/v1/executions/{id}/logs      Get execution logs
POST   /api/v1/executions/{id}/feedback  Submit feedback on execution
```

### Agent Chat API

```
POST   /api/v1/chat/sessions             Create chat session
POST   /api/v1/chat/sessions/{id}/messages  Send message to agent
GET    /api/v1/chat/sessions/{id}/messages  Get chat history
DELETE /api/v1/chat/sessions/{id}         End chat session
```

### Approval API

```
GET    /api/v1/approvals                  List pending approvals
POST   /api/v1/approvals/{id}/approve     Approve agent action
POST   /api/v1/approvals/{id}/reject      Reject agent action
```

### Marketplace API

```
GET    /api/v1/marketplace/agents         Browse marketplace agents
GET    /api/v1/marketplace/agents/{id}    Get marketplace agent details
POST   /api/v1/marketplace/agents/{id}/install  Install agent
POST   /api/v1/marketplace/submit         Submit agent to marketplace
```

---

*PRD-05: AI Agents-as-a-Service Platform — RayOlly's core differentiator. This document defines the architecture, capabilities, and vision for the most ambitious feature in the RayOlly platform. Agents transform observability from a reactive, human-dependent activity into a proactive, AI-driven operation.*

*Version 1.0 | 2026-03-19 | Platform Architecture Team*
