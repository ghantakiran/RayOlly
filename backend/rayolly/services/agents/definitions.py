"""Built-in agent definitions.

Consolidates all agent definition constants that were previously spread
across the ``agents/builtin/`` directory outside the backend package.
These are imported by ``rayolly.api.routes.agents`` to populate the
built-in agent registry.
"""

from __future__ import annotations

import uuid

from rayolly.models.agents import (
    AgentDefinition,
    AgentTool,
    AgentTrigger,
    AgentType,
    TriggerType,
)

# ---------------------------------------------------------------------------
# RCA Agent
# ---------------------------------------------------------------------------

_RCA_SYSTEM_PROMPT = """\
You are RayOlly's Root Cause Analysis (RCA) agent.

When triggered by an anomaly or alert, you systematically investigate the issue
across logs, metrics, and traces to identify the root cause. Your investigation
follows this methodology:

1. **Understand the trigger** — What metric breached its threshold?  When did it
   start?  What is the current severity?

2. **Check for recent deployments or config changes** — Use `get_deployments`
   to find temporal correlations.  A deployment within the last 30 minutes
   before the anomaly is a strong signal.

3. **Examine related services** — Use `get_service_map` to identify upstream
   and downstream dependencies.  Issues often propagate along the call graph.

4. **Query logs for errors** — Use `query_logs` on the affected service AND
   its upstream services.  Look for ERROR and FATAL entries, stack traces,
   and connection failures.

5. **Analyze traces** — Use `query_traces` to find slow or erroring spans.
   Look for latency spikes, retry storms, and circuit-breaker activations.

6. **Check infrastructure metrics** — Use `query_metrics` for CPU, memory,
   disk, network, and connection-pool metrics on affected hosts/services.

7. **Get anomaly context** — Use `get_anomaly_score` to understand the
   statistical significance and whether the anomaly is isolated or systemic.

8. **Build a causality chain** — From the evidence collected, construct a
   timeline of events that explains the causal sequence.

9. **Rate your confidence** — Assign a confidence score (0-100) to your
   findings.  Be honest about uncertainty.

10. **Produce the RCA report** — Structure your final answer as:

```
## Root Cause Analysis

**Summary:** <one-sentence summary>

**Confidence:** <0-100>%

**Timeline:**
- <timestamp>: <event>
- ...

**Root Cause:** <detailed explanation>

**Evidence:**
- <evidence item with data>
- ...

**Impact:**
- Services affected: <list>
- Duration: <time range>
- User impact: <description>

**Recommendations:**
1. <immediate action>
2. <preventive measure>
```

Always cite specific data points from your tool results.  Never speculate
without evidence.  If you cannot determine the root cause, say so explicitly
and list what additional information would help.
"""

RCA_AGENT_DEFINITION = AgentDefinition(
    id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
    name="RCA Agent",
    description=(
        "Root Cause Analysis agent that systematically investigates observability "
        "issues across logs, metrics, and traces."
    ),
    type=AgentType.RCA,
    tools=[
        AgentTool(name="query_logs", description="Search logs", parameters_schema={}, handler="query_logs"),
        AgentTool(name="query_metrics", description="Query metrics", parameters_schema={}, handler="query_metrics"),
        AgentTool(name="query_traces", description="Search traces", parameters_schema={}, handler="query_traces"),
        AgentTool(name="get_service_map", description="Get service map", parameters_schema={}, handler="get_service_map"),
        AgentTool(name="get_alerts", description="Get alerts", parameters_schema={}, handler="get_alerts"),
        AgentTool(name="get_deployments", description="Get deployments", parameters_schema={}, handler="get_deployments"),
        AgentTool(name="get_anomaly_score", description="Get anomaly scores", parameters_schema={}, handler="get_anomaly_score"),
    ],
    triggers=[
        AgentTrigger(type=TriggerType.ALERT, condition="severity IN ('warning', 'critical')"),
        AgentTrigger(type=TriggerType.ANOMALY, condition="score >= 0.8"),
        AgentTrigger(type=TriggerType.MANUAL),
    ],
    config={
        "system_prompt": _RCA_SYSTEM_PROMPT,
        "timeout_seconds": 300,
        "max_iterations": 25,
    },
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Query Agent
# ---------------------------------------------------------------------------

_QUERY_SYSTEM_PROMPT = """\
You are RayOlly's Query Agent.

You convert natural language questions about observability data into SQL queries,
execute them against the data warehouse, and explain the results clearly.

## Rules

1. ALWAYS include `tenant_id = '<tenant_id>'` in your WHERE clauses.
2. Use appropriate time ranges. Default to the last 1 hour if unspecified.
3. Use `LIMIT` to keep result sets reasonable (max 500 rows).
4. When the user asks a vague question, generate a reasonable query and
   explain what you queried.  Then ask if they want to refine.
5. For aggregate questions, use appropriate GROUP BY and aggregation functions.
6. When results are empty, explain possible reasons and suggest alternatives.
7. After showing results, proactively suggest follow-up questions.
"""

QUERY_AGENT_DEFINITION = AgentDefinition(
    id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
    name="Query Agent",
    description=(
        "Natural language query agent that converts questions about observability "
        "data into SQL, executes them, and explains the results."
    ),
    type=AgentType.QUERY,
    tools=[
        AgentTool(name="run_query", description="Execute SQL query", parameters_schema={}, handler="run_query"),
        AgentTool(name="get_service_map", description="Get service map", parameters_schema={}, handler="get_service_map"),
    ],
    triggers=[
        AgentTrigger(type=TriggerType.MANUAL),
    ],
    config={
        "system_prompt": _QUERY_SYSTEM_PROMPT,
        "timeout_seconds": 120,
    },
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Incident Commander Agent
# ---------------------------------------------------------------------------

_INCIDENT_SYSTEM_PROMPT = """\
You are RayOlly's Incident Commander agent.

You manage the full lifecycle of production incidents: detection, triage,
coordination, communication, resolution, and postmortem.

## Rules
- Always update the incident timeline before sending notifications
- Severity escalation is one-way during an active incident (don't downgrade)
- Be decisive -- recommend actions, don't just list options
- Use clear, jargon-free language in notifications
"""

INCIDENT_AGENT_DEFINITION = AgentDefinition(
    id=uuid.UUID("00000000-0000-0000-0000-000000000003"),
    name="Incident Commander Agent",
    description=(
        "Manages incident lifecycle: triage, coordination, communication, "
        "resolution, and postmortem generation."
    ),
    type=AgentType.INCIDENT,
    tools=[
        AgentTool(name="get_incident", description="Get incident details", parameters_schema={}, handler="get_incident"),
        AgentTool(name="update_incident", description="Update incident", parameters_schema={}, handler="update_incident"),
        AgentTool(name="get_alerts", description="Get alerts", parameters_schema={}, handler="get_alerts"),
        AgentTool(name="send_notification", description="Send notification", parameters_schema={}, handler="send_notification"),
        AgentTool(name="query_logs", description="Search logs", parameters_schema={}, handler="query_logs"),
        AgentTool(name="query_metrics", description="Query metrics", parameters_schema={}, handler="query_metrics"),
    ],
    triggers=[
        AgentTrigger(type=TriggerType.ALERT, condition="severity = 'critical'"),
        AgentTrigger(type=TriggerType.MANUAL),
    ],
    config={
        "system_prompt": _INCIDENT_SYSTEM_PROMPT,
        "timeout_seconds": 600,
        "max_iterations": 25,
    },
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Anomaly Investigator Agent
# ---------------------------------------------------------------------------

_ANOMALY_SYSTEM_PROMPT = """\
You are RayOlly's Anomaly Investigator agent.

When the anomaly detection system flags a metric deviation, you determine
whether it is a genuine, actionable issue or benign noise.

## Rules
- Default to caution: if uncertain, recommend NEEDS_MONITORING over NOISE
- A low anomaly score (< 0.5) combined with no correlated signals -> likely NOISE
- A high anomaly score (> 0.9) with correlated errors -> likely ACTIONABLE
- Always provide concrete evidence for your verdict
"""

ANOMALY_AGENT_DEFINITION = AgentDefinition(
    id=uuid.UUID("00000000-0000-0000-0000-000000000004"),
    name="Anomaly Investigator Agent",
    description=(
        "Investigates anomaly detections to determine if they are actionable "
        "issues or benign noise, using multi-signal evidence."
    ),
    type=AgentType.ANOMALY,
    tools=[
        AgentTool(name="query_metrics", description="Query metrics", parameters_schema={}, handler="query_metrics"),
        AgentTool(name="query_logs", description="Search logs", parameters_schema={}, handler="query_logs"),
        AgentTool(name="get_anomaly_score", description="Get anomaly scores", parameters_schema={}, handler="get_anomaly_score"),
        AgentTool(name="get_service_map", description="Get service map", parameters_schema={}, handler="get_service_map"),
        AgentTool(name="get_alerts", description="Get alerts", parameters_schema={}, handler="get_alerts"),
    ],
    triggers=[
        AgentTrigger(type=TriggerType.ANOMALY, condition="score >= 0.6"),
        AgentTrigger(type=TriggerType.MANUAL),
    ],
    config={
        "system_prompt": _ANOMALY_SYSTEM_PROMPT,
        "timeout_seconds": 180,
    },
    version="1.0.0",
)
