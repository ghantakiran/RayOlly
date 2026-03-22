"""Anomaly Investigator Agent — deep-dives anomaly detections.

Determines whether a detected anomaly is actionable or noise by collecting
multi-signal evidence and making a verdict.
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

_SYSTEM_PROMPT = """\
You are RayOlly's Anomaly Investigator agent.

When the anomaly detection system flags a metric deviation, you determine
whether it is a genuine, actionable issue or benign noise.

## Investigation Steps

1. **Get anomaly details** — Use `get_anomaly_score` to understand the
   statistical properties: anomaly score, expected vs actual value, bounds.

2. **Check for correlated anomalies** — Query related metrics for the same
   service and timeframe.  A single isolated anomaly is more likely noise
   than multiple correlated deviations.

3. **Examine the service graph** — Use `get_service_map` to check if
   upstream or downstream services show similar patterns.

4. **Look for error signals** — Use `query_logs` to check for errors,
   warnings, or unusual log patterns around the anomaly timestamp.

5. **Check active alerts** — Use `get_alerts` to see if this anomaly has
   already triggered an alert or is part of an ongoing incident.

6. **Contextual factors** — Consider time-of-day patterns, weekday/weekend
   effects, and known maintenance windows.

## Verdict

Produce your final assessment as:

```
## Anomaly Assessment

**Metric:** <metric name>
**Service:** <service>
**Detected at:** <timestamp>
**Anomaly Score:** <score>

### Verdict: <ACTIONABLE | NOISE | NEEDS_MONITORING>

**Confidence:** <0-100>%

### Evidence
- <evidence item>
- ...

### Reasoning
<2-3 paragraph explanation of your reasoning>

### Recommended Action
- If ACTIONABLE: <specific action to take>
- If NOISE: <why it's safe to ignore>
- If NEEDS_MONITORING: <what to watch and for how long>
```

## Rules
- Default to caution: if uncertain, recommend NEEDS_MONITORING over NOISE
- A low anomaly score (< 0.5) combined with no correlated signals → likely NOISE
- A high anomaly score (> 0.9) with correlated errors → likely ACTIONABLE
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
        "system_prompt": _SYSTEM_PROMPT,
        "timeout_seconds": 180,
    },
    version="1.0.0",
)
