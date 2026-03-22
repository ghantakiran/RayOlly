"""Real alert management API -- evaluates thresholds against ClickHouse data."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel

from rayolly.services.metadata.repositories import AlertRuleRepository

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/data/alerts", tags=["alert-data"])

_TENANT_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _validate_tenant(tenant_id: str) -> bool:
    return bool(_TENANT_RE.match(tenant_id))


# ---------------------------------------------------------------------------
# In-memory alert store (fallback when PostgreSQL is unavailable)
# ---------------------------------------------------------------------------

class AlertRuleCreate(BaseModel):
    name: str
    metric_name: str
    operator: str  # gt, lt, eq
    threshold: float
    severity: str  # critical, warning, info
    service: str = ""


_DEFAULT_ALERT_RULES: list[dict] = [
    {
        "id": "rule-err-rate",
        "name": "High Error Rate",
        "metric_name": "error_rate",
        "operator": "gt",
        "threshold": 10.0,
        "severity": "critical",
        "service": "",
        "enabled": True,
        "query": "error_rate > 10% for any service",
        "condition": "error_rate > 10%",
    },
    {
        "id": "rule-p99-latency",
        "name": "P99 Latency Spike",
        "metric_name": "p99_duration_ms",
        "operator": "gt",
        "threshold": 500.0,
        "severity": "warning",
        "service": "",
        "enabled": True,
        "query": "p99 latency > 500ms for any service",
        "condition": "p99_latency > 500ms",
    },
    {
        "id": "rule-high-error-count",
        "name": "Error Count Surge",
        "metric_name": "error_count",
        "operator": "gt",
        "threshold": 100.0,
        "severity": "warning",
        "service": "",
        "enabled": True,
        "query": "error_count > 100 in last hour",
        "condition": "error_count > 100",
    },
]

_alert_rules: list[dict] = list(_DEFAULT_ALERT_RULES)
_alert_history: list[dict] = []


def _record_history(alert: dict, status: str) -> None:
    """Record an alert state change in history."""
    _alert_history.insert(0, {
        "id": str(uuid.uuid4())[:8],
        "alert_name": alert["name"],
        "service": alert.get("service", ""),
        "severity": alert.get("severity", "warning"),
        "status": status,
        "timestamp": datetime.now(UTC).isoformat(),
        "message": alert.get("message", ""),
    })
    # Keep last 50
    if len(_alert_history) > 50:
        _alert_history[:] = _alert_history[:50]


def _db_rule_to_dict(rule) -> dict:
    """Convert a SQLAlchemy AlertRule to a plain dict for API responses."""
    condition = rule.condition if isinstance(rule.condition, dict) else {}
    return {
        "id": str(rule.id),
        "name": rule.name,
        "metric_name": condition.get("metric_name", ""),
        "operator": condition.get("operator", "gt"),
        "threshold": condition.get("threshold", 0.0),
        "severity": rule.severity,
        "service": condition.get("service", ""),
        "enabled": rule.enabled,
        "query": rule.query,
        "condition": rule.query,
    }


def _evaluate_rules_against_data(rules: list[dict], services: list[dict]) -> list[dict]:
    """Check each rule against real service data and return firing alerts."""
    active: list[dict] = []
    now = datetime.now(UTC).isoformat()

    for rule in rules:
        if not rule.get("enabled", True):
            continue

        metric = rule["metric_name"]
        op = rule["operator"]
        threshold = rule["threshold"]
        rule_service = rule.get("service", "")

        for svc in services:
            # Skip if rule targets a specific service and this isn't it
            if rule_service and svc.get("service") != rule_service:
                continue

            value = svc.get(metric)
            if value is None:
                continue

            fired = False
            if op == "gt" and value > threshold or op == "lt" and value < threshold or op == "eq" and value == threshold:
                fired = True

            if fired:
                alert = {
                    "id": f"{rule['id']}-{svc['service']}",
                    "name": rule["name"],
                    "severity": rule["severity"],
                    "service": svc["service"],
                    "message": f"{metric} = {value:.2f} (threshold: {op} {threshold})",
                    "value": round(value, 2),
                    "threshold": threshold,
                    "status": "firing",
                    "fired_at": now,
                    "rule_id": rule["id"],
                }
                active.append(alert)

    return active


def _get_db_session_factory(request: Request):
    return getattr(request.app.state, "db_session_factory", None)


async def _load_rules(request: Request, tenant_id: str) -> list[dict]:
    """Load alert rules from PostgreSQL, falling back to in-memory defaults."""
    db_factory = _get_db_session_factory(request)
    if db_factory is not None:
        try:
            async with db_factory() as session:
                repo = AlertRuleRepository(session)
                db_rules = await repo.list_by_tenant(tenant_id)
                if db_rules:
                    return [_db_rule_to_dict(r) for r in db_rules]
        except Exception as e:
            logger.warning("postgres_load_rules_fallback", error=str(e))

    return list(_alert_rules)


@router.get("/active")
async def active_alerts(request: Request) -> dict[str, Any]:
    """Return active/firing alerts by evaluating rules against real ClickHouse data."""
    ch = request.app.state.clickhouse
    tenant_id = getattr(request.state, "tenant_id", "default")

    if ch is None or not _validate_tenant(tenant_id):
        return {"alerts": [], "total": 0}

    try:
        rules = await _load_rules(request, tenant_id)

        # Query real service metrics from ClickHouse
        result = ch.query(
            f"SELECT "
            f"  service, "
            f"  count() AS request_count, "
            f"  countIf(status_code = 'ERROR') AS error_count, "
            f"  countIf(status_code = 'ERROR') / count() * 100 AS error_rate, "
            f"  avg(duration_ns) / 1000000.0 AS avg_duration_ms, "
            f"  quantile(0.99)(duration_ns) / 1000000.0 AS p99_duration_ms "
            f"FROM traces.spans "
            f"WHERE tenant_id = '{tenant_id}' "
            f"  AND service != '' "
            f"  AND start_time >= now() - INTERVAL 1 HOUR "
            f"GROUP BY service"
        )

        services = []
        for row in result.result_rows:
            services.append({
                "service": row[0],
                "request_count": row[1],
                "error_count": row[2],
                "error_rate": round(float(row[3]), 2),
                "avg_duration_ms": round(float(row[4]), 2),
                "p99_duration_ms": round(float(row[5]), 2),
            })

        alerts = _evaluate_rules_against_data(rules, services)

        # Record new firings in history
        for a in alerts:
            _record_history(a, "firing")

        return {"alerts": alerts, "total": len(alerts)}
    except Exception as e:
        logger.error("active_alerts_error", error=str(e))
        return {"alerts": [], "total": 0}


@router.get("/rules")
async def list_rules(request: Request) -> dict[str, Any]:
    """Return all configured alert rules."""
    tenant_id = getattr(request.state, "tenant_id", "default")
    rules = await _load_rules(request, tenant_id)
    return {"rules": rules}


@router.post("/rules")
async def create_rule(body: AlertRuleCreate, request: Request) -> dict[str, Any]:
    """Create a new alert rule. Persists to PostgreSQL when available."""
    tenant_id = getattr(request.state, "tenant_id", "default")
    db_factory = _get_db_session_factory(request)

    # Try PostgreSQL first
    if db_factory is not None:
        try:
            async with db_factory() as session:
                repo = AlertRuleRepository(session)
                # We need an org_id -- for now use a deterministic UUID from tenant_id
                # In production this would come from the authenticated user's org
                from rayolly.services.metadata.repositories import OrganizationRepository
                org_repo = OrganizationRepository(session)
                org = await org_repo.get_by_slug(tenant_id)
                org_id = org.id if org else uuid.uuid5(uuid.NAMESPACE_DNS, tenant_id)

                db_rule = await repo.create(
                    name=body.name,
                    tenant_id=tenant_id,
                    org_id=org_id,
                    query=f"{body.metric_name} {body.operator} {body.threshold}",
                    condition={
                        "metric_name": body.metric_name,
                        "operator": body.operator,
                        "threshold": body.threshold,
                        "service": body.service,
                    },
                    severity=body.severity,
                    enabled=True,
                )
                await session.commit()
                return {"rule": _db_rule_to_dict(db_rule)}
        except Exception as e:
            logger.warning("postgres_create_rule_fallback", error=str(e))

    # Fallback: in-memory
    rule = {
        "id": f"rule-{uuid.uuid4().hex[:8]}",
        "name": body.name,
        "metric_name": body.metric_name,
        "operator": body.operator,
        "threshold": body.threshold,
        "severity": body.severity,
        "service": body.service,
        "enabled": True,
        "query": f"{body.metric_name} {body.operator} {body.threshold}",
        "condition": f"{body.metric_name} {body.operator} {body.threshold}",
    }
    _alert_rules.append(rule)
    return {"rule": rule}


@router.get("/history")
async def alert_history() -> dict[str, Any]:
    """Return last 20 alert state changes."""
    return {"history": _alert_history[:20]}
