"""Agent tool registry and built-in observability tools.

Each tool exposes an Anthropic-compatible JSON schema so the LLM can invoke
it via the tool_use mechanism.  Tools are grouped by AgentType — an agent
only sees the tools listed in its definition.
"""

from __future__ import annotations

import abc
import logging
from dataclasses import dataclass, field
from typing import Any

from rayolly.models.agents import AgentType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Context passed to every tool execution
# ---------------------------------------------------------------------------

@dataclass
class AgentContext:
    """Runtime context available to every tool invocation."""

    tenant_id: str
    user_id: str = ""
    execution_id: str = ""
    permissions: list[str] = field(default_factory=list)
    # Injected infra handles — set by the runtime before tool execution
    clickhouse: Any = None
    redis: Any = None
    nats: Any = None
    pg_pool: Any = None


# ---------------------------------------------------------------------------
# Base tool class
# ---------------------------------------------------------------------------

class BaseTool(abc.ABC):
    """Every tool must declare its Anthropic-compatible schema and implement
    an async ``execute`` method."""

    name: str
    description: str
    parameters_schema: dict[str, Any]  # JSON Schema (``input_schema``)

    @abc.abstractmethod
    async def execute(
        self, parameters: dict[str, Any], context: AgentContext
    ) -> dict[str, Any]:
        ...

    def to_anthropic_tool(self) -> dict[str, Any]:
        """Return the tool descriptor sent in the Anthropic ``tools`` array."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters_schema,
        }


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

class ToolRegistry:
    """Central catalogue of all available tools."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._agent_tools: dict[AgentType, list[str]] = {}

    def register(self, tool: BaseTool, agent_types: list[AgentType] | None = None) -> None:
        self._tools[tool.name] = tool
        if agent_types:
            for at in agent_types:
                self._agent_tools.setdefault(at, []).append(tool.name)

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self, agent_type: AgentType | None = None) -> list[BaseTool]:
        if agent_type is None:
            return list(self._tools.values())
        names = self._agent_tools.get(agent_type, [])
        return [self._tools[n] for n in names if n in self._tools]

    async def execute_tool(
        self, name: str, parameters: dict[str, Any], context: AgentContext
    ) -> dict[str, Any]:
        tool = self._tools.get(name)
        if tool is None:
            return {"error": f"Unknown tool: {name}"}
        try:
            return await tool.execute(parameters, context)
        except Exception as exc:
            logger.exception("Tool %s failed", name)
            return {"error": str(exc)}


# ===================================================================
# Built-in tools
# ===================================================================

class QueryLogsTool(BaseTool):
    name = "query_logs"
    description = (
        "Search logs with filters. Returns matching log entries for a given "
        "service, severity, time range, and/or free-text query."
    )
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "service": {
                "type": "string",
                "description": "Service name to filter logs by.",
            },
            "severity": {
                "type": "string",
                "enum": ["DEBUG", "INFO", "WARN", "ERROR", "FATAL"],
                "description": "Minimum severity level.",
            },
            "time_range": {
                "type": "object",
                "properties": {
                    "start": {"type": "string", "description": "ISO-8601 start time."},
                    "end": {"type": "string", "description": "ISO-8601 end time."},
                },
                "description": "Time window to search within.",
            },
            "query": {
                "type": "string",
                "description": "Free-text search query.",
            },
            "limit": {
                "type": "integer",
                "description": "Max results to return.",
                "default": 50,
            },
        },
        "required": [],
    }

    async def execute(
        self, parameters: dict[str, Any], context: AgentContext
    ) -> dict[str, Any]:
        ch = context.clickhouse
        if ch is None:
            return {"error": "ClickHouse not available"}

        conditions = [f"tenant_id = '{context.tenant_id}'"]
        if parameters.get("service"):
            conditions.append(f"service_name = '{parameters['service']}'")
        if parameters.get("severity"):
            sev_order = {"DEBUG": 0, "INFO": 1, "WARN": 2, "ERROR": 3, "FATAL": 4}
            min_val = sev_order.get(parameters["severity"], 0)
            allowed = [s for s, v in sev_order.items() if v >= min_val]
            conditions.append(
                f"severity IN ({','.join(repr(s) for s in allowed)})"
            )
        if parameters.get("time_range"):
            tr = parameters["time_range"]
            if tr.get("start"):
                conditions.append(f"timestamp >= '{tr['start']}'")
            if tr.get("end"):
                conditions.append(f"timestamp <= '{tr['end']}'")
        if parameters.get("query"):
            conditions.append(f"body ILIKE '%{parameters['query']}%'")

        limit = min(parameters.get("limit", 50), 200)
        where = " AND ".join(conditions)
        sql = f"SELECT timestamp, service_name, severity, body FROM logs WHERE {where} ORDER BY timestamp DESC LIMIT {limit}"

        try:
            rows = ch.execute(sql)
            return {
                "logs": [
                    {
                        "timestamp": str(r[0]),
                        "service": r[1],
                        "severity": r[2],
                        "body": r[3],
                    }
                    for r in rows
                ],
                "count": len(rows),
            }
        except Exception as exc:
            return {"error": f"Query failed: {exc}"}


class QueryMetricsTool(BaseTool):
    name = "query_metrics"
    description = (
        "Query time-series metrics. Supports aggregation over a time range "
        "with label filters."
    )
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "metric_name": {
                "type": "string",
                "description": "Name of the metric to query.",
            },
            "labels": {
                "type": "object",
                "description": "Label key-value pairs for filtering.",
                "additionalProperties": {"type": "string"},
            },
            "time_range": {
                "type": "object",
                "properties": {
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                },
            },
            "aggregation": {
                "type": "string",
                "enum": ["avg", "sum", "min", "max", "count", "p50", "p90", "p95", "p99"],
                "description": "Aggregation function to apply.",
                "default": "avg",
            },
            "step": {
                "type": "string",
                "description": "Bucket interval (e.g., '1m', '5m', '1h').",
                "default": "1m",
            },
        },
        "required": ["metric_name"],
    }

    async def execute(
        self, parameters: dict[str, Any], context: AgentContext
    ) -> dict[str, Any]:
        ch = context.clickhouse
        if ch is None:
            return {"error": "ClickHouse not available"}

        metric = parameters["metric_name"]
        agg = parameters.get("aggregation", "avg")
        step = parameters.get("step", "1m")

        # Map friendly step to ClickHouse interval
        step_map = {
            "1m": "toStartOfMinute(timestamp)",
            "5m": "toStartOfFiveMinutes(timestamp)",
            "1h": "toStartOfHour(timestamp)",
            "1d": "toStartOfDay(timestamp)",
        }
        bucket_expr = step_map.get(step, "toStartOfMinute(timestamp)")

        # Map aggregation to ClickHouse function
        agg_map = {
            "avg": "avg(value)",
            "sum": "sum(value)",
            "min": "min(value)",
            "max": "max(value)",
            "count": "count()",
            "p50": "quantile(0.5)(value)",
            "p90": "quantile(0.9)(value)",
            "p95": "quantile(0.95)(value)",
            "p99": "quantile(0.99)(value)",
        }
        agg_expr = agg_map.get(agg, "avg(value)")

        conditions = [
            f"tenant_id = '{context.tenant_id}'",
            f"metric_name = '{metric}'",
        ]
        for k, v in (parameters.get("labels") or {}).items():
            conditions.append(f"labels['{k}'] = '{v}'")
        if parameters.get("time_range"):
            tr = parameters["time_range"]
            if tr.get("start"):
                conditions.append(f"timestamp >= '{tr['start']}'")
            if tr.get("end"):
                conditions.append(f"timestamp <= '{tr['end']}'")

        where = " AND ".join(conditions)
        sql = (
            f"SELECT {bucket_expr} AS bucket, {agg_expr} AS agg_value "
            f"FROM metrics WHERE {where} "
            f"GROUP BY bucket ORDER BY bucket"
        )

        try:
            rows = ch.execute(sql)
            return {
                "metric": metric,
                "aggregation": agg,
                "datapoints": [
                    {"timestamp": str(r[0]), "value": float(r[1])} for r in rows
                ],
                "count": len(rows),
            }
        except Exception as exc:
            return {"error": f"Metric query failed: {exc}"}


class QueryTracesTool(BaseTool):
    name = "query_traces"
    description = (
        "Search distributed traces by service, operation, minimum duration, "
        "or error status."
    )
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "service": {"type": "string", "description": "Service name."},
            "operation": {"type": "string", "description": "Operation/span name."},
            "min_duration_ms": {
                "type": "integer",
                "description": "Minimum span duration in milliseconds.",
            },
            "status": {
                "type": "string",
                "enum": ["OK", "ERROR", "UNSET"],
                "description": "Span status filter.",
            },
            "time_range": {
                "type": "object",
                "properties": {
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                },
            },
            "limit": {"type": "integer", "default": 20},
        },
        "required": [],
    }

    async def execute(
        self, parameters: dict[str, Any], context: AgentContext
    ) -> dict[str, Any]:
        ch = context.clickhouse
        if ch is None:
            return {"error": "ClickHouse not available"}

        conditions = [f"tenant_id = '{context.tenant_id}'"]
        if parameters.get("service"):
            conditions.append(f"service_name = '{parameters['service']}'")
        if parameters.get("operation"):
            conditions.append(f"span_name = '{parameters['operation']}'")
        if parameters.get("min_duration_ms"):
            conditions.append(
                f"duration_ms >= {parameters['min_duration_ms']}"
            )
        if parameters.get("status"):
            conditions.append(f"status_code = '{parameters['status']}'")
        if parameters.get("time_range"):
            tr = parameters["time_range"]
            if tr.get("start"):
                conditions.append(f"timestamp >= '{tr['start']}'")
            if tr.get("end"):
                conditions.append(f"timestamp <= '{tr['end']}'")

        limit = min(parameters.get("limit", 20), 100)
        where = " AND ".join(conditions)
        sql = (
            f"SELECT trace_id, span_id, service_name, span_name, "
            f"duration_ms, status_code, timestamp "
            f"FROM traces WHERE {where} "
            f"ORDER BY timestamp DESC LIMIT {limit}"
        )

        try:
            rows = ch.execute(sql)
            return {
                "traces": [
                    {
                        "trace_id": r[0],
                        "span_id": r[1],
                        "service": r[2],
                        "operation": r[3],
                        "duration_ms": r[4],
                        "status": r[5],
                        "timestamp": str(r[6]),
                    }
                    for r in rows
                ],
                "count": len(rows),
            }
        except Exception as exc:
            return {"error": f"Trace query failed: {exc}"}


class GetServiceMapTool(BaseTool):
    name = "get_service_map"
    description = "Retrieve the service dependency map for the tenant."
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "service": {
                "type": "string",
                "description": "Optional — show only dependencies for this service.",
            },
        },
        "required": [],
    }

    async def execute(
        self, parameters: dict[str, Any], context: AgentContext
    ) -> dict[str, Any]:
        ch = context.clickhouse
        if ch is None:
            return {"error": "ClickHouse not available"}

        conditions = [f"tenant_id = '{context.tenant_id}'"]
        if parameters.get("service"):
            svc = parameters["service"]
            conditions.append(
                f"(source_service = '{svc}' OR target_service = '{svc}')"
            )

        where = " AND ".join(conditions)
        sql = (
            f"SELECT source_service, target_service, "
            f"count() AS call_count, avg(duration_ms) AS avg_latency, "
            f"countIf(status_code = 'ERROR') AS error_count "
            f"FROM service_dependencies WHERE {where} "
            f"AND timestamp >= now() - INTERVAL 1 HOUR "
            f"GROUP BY source_service, target_service "
            f"ORDER BY call_count DESC LIMIT 100"
        )

        try:
            rows = ch.execute(sql)
            return {
                "edges": [
                    {
                        "source": r[0],
                        "target": r[1],
                        "call_count": r[2],
                        "avg_latency_ms": round(float(r[3]), 2),
                        "error_count": r[4],
                    }
                    for r in rows
                ],
            }
        except Exception as exc:
            return {"error": f"Service map query failed: {exc}"}


class GetAlertsTool(BaseTool):
    name = "get_alerts"
    description = "Get active or recent alerts, optionally filtered by service or severity."
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "service": {"type": "string"},
            "severity": {
                "type": "string",
                "enum": ["info", "warning", "critical"],
            },
            "status": {
                "type": "string",
                "enum": ["firing", "resolved"],
                "default": "firing",
            },
            "limit": {"type": "integer", "default": 20},
        },
        "required": [],
    }

    async def execute(
        self, parameters: dict[str, Any], context: AgentContext
    ) -> dict[str, Any]:
        ch = context.clickhouse
        if ch is None:
            return {"error": "ClickHouse not available"}

        conditions = [f"tenant_id = '{context.tenant_id}'"]
        if parameters.get("service"):
            conditions.append(f"service_name = '{parameters['service']}'")
        if parameters.get("severity"):
            conditions.append(f"severity = '{parameters['severity']}'")
        status = parameters.get("status", "firing")
        conditions.append(f"status = '{status}'")

        limit = min(parameters.get("limit", 20), 100)
        where = " AND ".join(conditions)
        sql = (
            f"SELECT id, alert_name, service_name, severity, status, "
            f"message, fired_at FROM alerts WHERE {where} "
            f"ORDER BY fired_at DESC LIMIT {limit}"
        )

        try:
            rows = ch.execute(sql)
            return {
                "alerts": [
                    {
                        "id": str(r[0]),
                        "name": r[1],
                        "service": r[2],
                        "severity": r[3],
                        "status": r[4],
                        "message": r[5],
                        "fired_at": str(r[6]),
                    }
                    for r in rows
                ],
                "count": len(rows),
            }
        except Exception as exc:
            return {"error": f"Alerts query failed: {exc}"}


class GetDeploymentsTool(BaseTool):
    name = "get_deployments"
    description = "Get recent deployments and change events for temporal correlation."
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "service": {"type": "string"},
            "hours_back": {
                "type": "integer",
                "description": "How many hours back to look.",
                "default": 24,
            },
            "limit": {"type": "integer", "default": 20},
        },
        "required": [],
    }

    async def execute(
        self, parameters: dict[str, Any], context: AgentContext
    ) -> dict[str, Any]:
        ch = context.clickhouse
        if ch is None:
            return {"error": "ClickHouse not available"}

        hours = parameters.get("hours_back", 24)
        conditions = [
            f"tenant_id = '{context.tenant_id}'",
            f"timestamp >= now() - INTERVAL {hours} HOUR",
        ]
        if parameters.get("service"):
            conditions.append(f"service_name = '{parameters['service']}'")

        limit = min(parameters.get("limit", 20), 100)
        where = " AND ".join(conditions)
        sql = (
            f"SELECT id, service_name, version, environment, deployer, "
            f"timestamp, status, change_type FROM change_events "
            f"WHERE {where} ORDER BY timestamp DESC LIMIT {limit}"
        )

        try:
            rows = ch.execute(sql)
            return {
                "deployments": [
                    {
                        "id": str(r[0]),
                        "service": r[1],
                        "version": r[2],
                        "environment": r[3],
                        "deployer": r[4],
                        "timestamp": str(r[5]),
                        "status": r[6],
                        "change_type": r[7],
                    }
                    for r in rows
                ],
                "count": len(rows),
            }
        except Exception as exc:
            return {"error": f"Deployments query failed: {exc}"}


class CreateAlertTool(BaseTool):
    name = "create_alert"
    description = "Create or update an alert rule."
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Alert rule name."},
            "condition": {
                "type": "string",
                "description": "Alert condition expression (e.g., 'error_rate > 0.05').",
            },
            "severity": {
                "type": "string",
                "enum": ["info", "warning", "critical"],
            },
            "service": {"type": "string"},
            "notification_channels": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Channel IDs to notify.",
            },
        },
        "required": ["name", "condition", "severity"],
    }

    async def execute(
        self, parameters: dict[str, Any], context: AgentContext
    ) -> dict[str, Any]:
        # In production this would persist via the alert-rules service.
        # For now we publish an event so the alert engine picks it up.
        nats = context.nats
        if nats is None:
            return {"error": "NATS not available"}

        import json

        payload = {
            "tenant_id": context.tenant_id,
            "created_by": f"agent:{context.execution_id}",
            **parameters,
        }
        try:
            await nats.publish(
                "rayolly.alerts.rules.upsert",
                json.dumps(payload).encode(),
            )
            return {"status": "created", "alert_name": parameters["name"]}
        except Exception as exc:
            return {"error": f"Failed to create alert: {exc}"}


class SendNotificationTool(BaseTool):
    name = "send_notification"
    description = "Send a notification to Slack, PagerDuty, or a webhook."
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "channel_type": {
                "type": "string",
                "enum": ["slack", "pagerduty", "webhook"],
            },
            "channel_id": {
                "type": "string",
                "description": "Channel/webhook identifier.",
            },
            "title": {"type": "string"},
            "message": {"type": "string"},
            "severity": {
                "type": "string",
                "enum": ["info", "warning", "critical"],
                "default": "info",
            },
            "metadata": {
                "type": "object",
                "description": "Extra key-value pairs to include.",
            },
        },
        "required": ["channel_type", "channel_id", "title", "message"],
    }

    async def execute(
        self, parameters: dict[str, Any], context: AgentContext
    ) -> dict[str, Any]:
        nats = context.nats
        if nats is None:
            return {"error": "NATS not available"}

        import json

        payload = {
            "tenant_id": context.tenant_id,
            "sent_by": f"agent:{context.execution_id}",
            **parameters,
        }
        try:
            await nats.publish(
                f"rayolly.notifications.{parameters['channel_type']}",
                json.dumps(payload).encode(),
            )
            return {"status": "sent", "channel": parameters["channel_type"]}
        except Exception as exc:
            return {"error": f"Notification failed: {exc}"}


class RunQueryTool(BaseTool):
    name = "run_query"
    description = (
        "Execute an arbitrary RayQL or SQL query against the observability "
        "data warehouse. Use with care."
    )
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The SQL/RayQL query to execute.",
            },
            "limit": {
                "type": "integer",
                "description": "Max rows to return.",
                "default": 100,
            },
        },
        "required": ["query"],
    }

    async def execute(
        self, parameters: dict[str, Any], context: AgentContext
    ) -> dict[str, Any]:
        ch = context.clickhouse
        if ch is None:
            return {"error": "ClickHouse not available"}

        raw_query = parameters["query"].strip().rstrip(";")
        limit = min(parameters.get("limit", 100), 500)

        # Safety: inject tenant_id and prevent destructive statements
        forbidden = {"DROP", "ALTER", "TRUNCATE", "DELETE", "INSERT", "UPDATE", "CREATE"}
        first_word = raw_query.split()[0].upper() if raw_query else ""
        if first_word in forbidden:
            return {"error": f"Forbidden operation: {first_word}"}

        # Ensure tenant isolation — append WHERE clause if not present
        if "tenant_id" not in raw_query.lower():
            return {
                "error": "Query must include a tenant_id filter for safety."
            }

        query = f"{raw_query} LIMIT {limit}"

        try:
            rows = ch.execute(query)
            # Try to get column names
            columns: list[str] = []
            try:
                columns = [col[0] for col in ch.execute(f"DESCRIBE ({raw_query} LIMIT 0)")]
            except Exception:
                columns = [f"col_{i}" for i in range(len(rows[0]) if rows else 0)]

            return {
                "columns": columns,
                "rows": [
                    {columns[i]: str(v) for i, v in enumerate(row)}
                    for row in rows
                ],
                "count": len(rows),
            }
        except Exception as exc:
            return {"error": f"Query execution failed: {exc}"}


class GetAnomalyScoreTool(BaseTool):
    name = "get_anomaly_score"
    description = "Get anomaly detection scores for a metric over a time range."
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "metric_name": {"type": "string"},
            "service": {"type": "string"},
            "time_range": {
                "type": "object",
                "properties": {
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                },
            },
        },
        "required": ["metric_name"],
    }

    async def execute(
        self, parameters: dict[str, Any], context: AgentContext
    ) -> dict[str, Any]:
        ch = context.clickhouse
        if ch is None:
            return {"error": "ClickHouse not available"}

        conditions = [
            f"tenant_id = '{context.tenant_id}'",
            f"metric_name = '{parameters['metric_name']}'",
        ]
        if parameters.get("service"):
            conditions.append(f"service_name = '{parameters['service']}'")
        if parameters.get("time_range"):
            tr = parameters["time_range"]
            if tr.get("start"):
                conditions.append(f"timestamp >= '{tr['start']}'")
            if tr.get("end"):
                conditions.append(f"timestamp <= '{tr['end']}'")

        where = " AND ".join(conditions)
        sql = (
            f"SELECT timestamp, value, anomaly_score, is_anomaly, "
            f"expected_value, upper_bound, lower_bound "
            f"FROM anomaly_scores WHERE {where} "
            f"ORDER BY timestamp DESC LIMIT 100"
        )

        try:
            rows = ch.execute(sql)
            return {
                "metric": parameters["metric_name"],
                "scores": [
                    {
                        "timestamp": str(r[0]),
                        "value": float(r[1]),
                        "anomaly_score": float(r[2]),
                        "is_anomaly": bool(r[3]),
                        "expected_value": float(r[4]),
                        "upper_bound": float(r[5]),
                        "lower_bound": float(r[6]),
                    }
                    for r in rows
                ],
                "count": len(rows),
            }
        except Exception as exc:
            return {"error": f"Anomaly score query failed: {exc}"}


class GetIncidentTool(BaseTool):
    name = "get_incident"
    description = "Get full details of an incident including timeline."
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "incident_id": {"type": "string", "description": "Incident UUID."},
        },
        "required": ["incident_id"],
    }

    async def execute(
        self, parameters: dict[str, Any], context: AgentContext
    ) -> dict[str, Any]:
        pg = context.pg_pool
        if pg is None:
            return {"error": "PostgreSQL not available"}

        incident_id = parameters["incident_id"]
        row = await pg.fetchrow(
            """
            SELECT id, title, severity, status, started_at, resolved_at,
                   services, summary, commander, timeline
            FROM incidents
            WHERE id = $1 AND tenant_id = $2
            """,
            incident_id,
            context.tenant_id,
        )
        if not row:
            return {"error": f"Incident {incident_id} not found"}

        return {
            "incident": {
                "id": str(row["id"]),
                "title": row["title"],
                "severity": row["severity"],
                "status": row["status"],
                "started_at": str(row["started_at"]),
                "resolved_at": str(row["resolved_at"]) if row["resolved_at"] else None,
                "services": row["services"],
                "summary": row["summary"],
                "commander": row["commander"],
                "timeline": row["timeline"],
            }
        }


class UpdateIncidentTool(BaseTool):
    name = "update_incident"
    description = "Update an incident's status, add timeline entries, or set fields."
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "incident_id": {"type": "string"},
            "status": {
                "type": "string",
                "enum": ["investigating", "identified", "mitigating", "resolved", "postmortem"],
            },
            "timeline_entry": {
                "type": "string",
                "description": "New timeline entry to append.",
            },
            "summary": {"type": "string", "description": "Updated summary."},
            "severity": {"type": "string", "enum": ["SEV1", "SEV2", "SEV3", "SEV4"]},
        },
        "required": ["incident_id"],
    }

    async def execute(
        self, parameters: dict[str, Any], context: AgentContext
    ) -> dict[str, Any]:
        pg = context.pg_pool
        if pg is None:
            return {"error": "PostgreSQL not available"}

        incident_id = parameters["incident_id"]
        updates: list[str] = []
        args: list[Any] = []
        idx = 3  # $1=incident_id, $2=tenant_id

        if parameters.get("status"):
            updates.append(f"status = ${idx}")
            args.append(parameters["status"])
            idx += 1
        if parameters.get("summary"):
            updates.append(f"summary = ${idx}")
            args.append(parameters["summary"])
            idx += 1
        if parameters.get("severity"):
            updates.append(f"severity = ${idx}")
            args.append(parameters["severity"])
            idx += 1
        if parameters.get("timeline_entry"):
            updates.append(
                f"timeline = timeline || jsonb_build_array(jsonb_build_object("
                f"'timestamp', now()::text, 'entry', ${idx}, "
                f"'author', 'agent'))"
            )
            args.append(parameters["timeline_entry"])
            idx += 1

        if not updates:
            return {"error": "No fields to update"}

        if parameters.get("status") == "resolved":
            updates.append("resolved_at = NOW()")

        sql = (
            f"UPDATE incidents SET {', '.join(updates)}, updated_at = NOW() "
            f"WHERE id = $1 AND tenant_id = $2"
        )

        try:
            await pg.execute(sql, incident_id, context.tenant_id, *args)
            return {"status": "updated", "incident_id": incident_id}
        except Exception as exc:
            return {"error": f"Incident update failed: {exc}"}


# ---------------------------------------------------------------------------
# Registry factory
# ---------------------------------------------------------------------------

def create_default_registry() -> ToolRegistry:
    """Build a registry with all built-in tools wired to their agent types."""
    registry = ToolRegistry()

    # RCA agent tools
    rca_types = [AgentType.RCA]
    registry.register(QueryLogsTool(), [AgentType.RCA, AgentType.INCIDENT, AgentType.ANOMALY])
    registry.register(QueryMetricsTool(), [AgentType.RCA, AgentType.INCIDENT, AgentType.ANOMALY, AgentType.CAPACITY, AgentType.SLO])
    registry.register(QueryTracesTool(), [AgentType.RCA])
    registry.register(GetServiceMapTool(), [AgentType.RCA, AgentType.QUERY, AgentType.ANOMALY])
    registry.register(GetAlertsTool(), [AgentType.RCA, AgentType.INCIDENT, AgentType.ANOMALY])
    registry.register(GetDeploymentsTool(), [AgentType.RCA])
    registry.register(GetAnomalyScoreTool(), [AgentType.RCA, AgentType.ANOMALY])

    # Incident agent tools
    registry.register(GetIncidentTool(), [AgentType.INCIDENT])
    registry.register(UpdateIncidentTool(), [AgentType.INCIDENT])
    registry.register(SendNotificationTool(), [AgentType.INCIDENT])
    registry.register(CreateAlertTool(), [AgentType.INCIDENT])

    # Query agent tools
    registry.register(RunQueryTool(), [AgentType.QUERY])

    return registry
