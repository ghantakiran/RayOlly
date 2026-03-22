"""Integration management API routes."""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from rayolly.services.integrations.github import GitHubIntegration
from rayolly.services.integrations.jira import JiraIntegration
from rayolly.services.integrations.pagerduty import PagerDutyIntegration
from rayolly.services.integrations.registry import (
    IntegrationCategory,
    IntegrationStatus,
    integration_registry,
)

# Register all built-in integrations on module load
from rayolly.services.integrations.servicenow import ServiceNowIntegration
from rayolly.services.integrations.slack import SlackIntegration
from rayolly.services.integrations.twilio import TwilioIntegration
from rayolly.services.integrations.webhook import WebhookIntegration

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])

# ---------------------------------------------------------------------------
# Bootstrap built-in integrations
# ---------------------------------------------------------------------------

_BUILTIN_INTEGRATIONS: list[type] = [
    ServiceNowIntegration,
    TwilioIntegration,
    SlackIntegration,
    PagerDutyIntegration,
    JiraIntegration,
    GitHubIntegration,
    WebhookIntegration,
]

for _cls in _BUILTIN_INTEGRATIONS:
    try:
        integration_registry.register(_cls)
    except Exception:
        logger.exception("Failed to register integration %s", _cls.__name__)


# ---------------------------------------------------------------------------
# Helper to extract tenant_id from request (placeholder for auth middleware)
# ---------------------------------------------------------------------------


def _tenant_id(request: Request) -> str:
    return getattr(request.state, "tenant_id", "default")


def _serialize(obj: Any) -> Any:
    """Convert dataclass / enum instances to JSON-safe dicts."""
    if hasattr(obj, "__dataclass_fields__"):
        data = asdict(obj)
        # Ensure enums are serialized as their value
        for k, v in data.items():
            if isinstance(v, IntegrationCategory) or isinstance(v, IntegrationStatus):
                data[k] = v.value
        return data
    return obj


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/categories")
async def list_categories() -> dict[str, Any]:
    """List all integration categories."""
    return {
        "categories": [
            {"id": c.value, "name": c.name.replace("_", " ").title()}
            for c in IntegrationCategory
        ]
    }


@router.get("/available")
async def list_available(category: str | None = None) -> dict[str, Any]:
    """List all available integration types, optionally filtered by category."""
    if category:
        try:
            cat = IntegrationCategory(category)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid category: {category}")
        definitions = integration_registry.list_by_category(cat)
    else:
        definitions = integration_registry.list_available()

    return {
        "integrations": [_serialize(d) for d in definitions],
        "total": len(definitions),
    }


@router.get("")
async def list_instances(request: Request) -> dict[str, Any]:
    """List configured integration instances for the current tenant."""
    tenant = _tenant_id(request)
    instances = integration_registry.list_instances(tenant)
    return {
        "instances": [_serialize(i) for i in instances],
        "total": len(instances),
    }


@router.post("")
async def create_instance(request: Request) -> dict[str, Any]:
    """Create a new integration instance."""
    tenant = _tenant_id(request)
    body = await request.json()

    definition_id = body.get("definition_id")
    name = body.get("name")
    config = body.get("config", {})

    if not definition_id or not name:
        raise HTTPException(status_code=400, detail="definition_id and name are required")

    try:
        instance = await integration_registry.create_instance(tenant, definition_id, name, config)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("Failed to create integration instance")
        raise HTTPException(status_code=500, detail=str(exc))

    return {"instance": _serialize(instance)}


@router.get("/{instance_id}")
async def get_instance(instance_id: str) -> dict[str, Any]:
    """Get a single integration instance by ID."""
    try:
        instance = integration_registry.get_instance(instance_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"instance": _serialize(instance)}


@router.put("/{instance_id}")
async def update_instance(instance_id: str, request: Request) -> dict[str, Any]:
    """Update an integration instance's name or config."""
    try:
        instance = integration_registry.get_instance(instance_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    body = await request.json()
    if "name" in body:
        instance.name = body["name"]
    if "config" in body:
        instance.config = body["config"]
    if "status" in body:
        try:
            instance.status = IntegrationStatus(body["status"])
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {body['status']}")

    return {"instance": _serialize(instance)}


@router.delete("/{instance_id}")
async def delete_instance(instance_id: str) -> dict[str, Any]:
    """Delete an integration instance."""
    try:
        integration_registry.delete_instance(instance_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"deleted": True}


@router.post("/{instance_id}/test")
async def test_instance(instance_id: str) -> dict[str, Any]:
    """Test an integration instance's connection."""
    try:
        success = await integration_registry.test_instance(instance_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("Test connection error")
        raise HTTPException(status_code=500, detail=str(exc))

    instance = integration_registry.get_instance(instance_id)
    return {
        "success": success,
        "status": instance.status.value,
        "error": instance.error_message,
    }


@router.post("/{instance_id}/sync")
async def sync_instance(instance_id: str) -> dict[str, Any]:
    """Trigger a sync for an integration instance."""
    try:
        result = await integration_registry.sync_instance(instance_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("Sync error")
        raise HTTPException(status_code=500, detail=str(exc))

    return {"result": _serialize(result)}


@router.post("/{instance_id}/actions/{action}")
async def execute_action(instance_id: str, action: str, request: Request) -> dict[str, Any]:
    """Execute a named action on an integration (e.g. create_incident, send_sms)."""
    try:
        instance = integration_registry.get_instance(instance_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    integration = integration_registry.get(instance.definition_id)
    body = await request.json()

    # Inject the instance config so actions have access
    params = {**body, "config": instance.config}

    try:
        result = await integration.execute_action(action, params)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Action '%s' failed for instance %s", action, instance_id)
        raise HTTPException(status_code=500, detail=str(exc))

    return {"result": result}
