"""Agent Marketplace API routes."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from rayolly.services.agents.marketplace import AgentMarketplace

router = APIRouter(prefix="/api/v1/marketplace", tags=["marketplace"])

# Singleton marketplace instance (replaced by DI in production)
_marketplace = AgentMarketplace()


def _get_tenant_id(request: Request) -> str:
    """Extract tenant ID from request state."""
    return getattr(request.state, "tenant_id", "default")


def _agent_to_dict(agent: Any) -> dict:
    """Serialise a MarketplaceAgent dataclass for API responses."""
    data = asdict(agent)
    # Remove the full system prompt from list views for brevity
    data.pop("system_prompt", None)
    return data


# ------------------------------------------------------------------
# Catalog
# ------------------------------------------------------------------


@router.get("/agents")
async def list_agents(
    category: str | None = Query(None, description="Filter by category"),
) -> dict:
    """List marketplace catalog, optionally filtered by category."""
    agents = _marketplace.list_catalog(category=category)
    return {
        "agents": [_agent_to_dict(a) for a in agents],
        "total": len(agents),
    }


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str) -> dict:
    """Get full details for a marketplace agent."""
    agent = _marketplace.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"agent": asdict(agent)}


# ------------------------------------------------------------------
# Installation
# ------------------------------------------------------------------


class InstallRequest(BaseModel):
    config: dict = Field(default_factory=dict)


@router.post("/agents/{agent_id}/install", status_code=201)
async def install_agent(
    agent_id: str, body: InstallRequest, request: Request
) -> dict:
    """Install a marketplace agent for the current tenant."""
    tenant_id = _get_tenant_id(request)
    installed = _marketplace.install(tenant_id, agent_id, config=body.config)
    if not installed:
        raise HTTPException(
            status_code=400,
            detail="Agent not found or already installed",
        )
    return {
        "message": f"Agent '{agent_id}' installed",
        "installed_at": installed.installed_at,
    }


@router.delete("/agents/{agent_id}/uninstall")
async def uninstall_agent(agent_id: str, request: Request) -> dict:
    """Uninstall a marketplace agent for the current tenant."""
    tenant_id = _get_tenant_id(request)
    if not _marketplace.uninstall(tenant_id, agent_id):
        raise HTTPException(
            status_code=404, detail="Agent not installed"
        )
    return {"message": f"Agent '{agent_id}' uninstalled"}


@router.get("/installed")
async def list_installed(request: Request) -> dict:
    """List agents installed by the current tenant."""
    tenant_id = _get_tenant_id(request)
    installed = _marketplace.list_installed(tenant_id)
    items = []
    for entry in installed:
        agent_dict = _agent_to_dict(entry["agent"])
        inst = asdict(entry["installation"])
        items.append({**agent_dict, "installation": inst})
    return {"agents": items, "total": len(items)}


# ------------------------------------------------------------------
# Ratings
# ------------------------------------------------------------------


class RateRequest(BaseModel):
    rating: float = Field(..., ge=1.0, le=5.0, description="Rating between 1.0 and 5.0")


@router.post("/agents/{agent_id}/rate")
async def rate_agent(agent_id: str, body: RateRequest) -> dict:
    """Submit a rating for a marketplace agent."""
    if not _marketplace.rate(agent_id, body.rating):
        raise HTTPException(
            status_code=404, detail="Agent not found"
        )
    agent = _marketplace.get_agent(agent_id)
    return {
        "message": "Rating submitted",
        "new_rating": agent.rating if agent else None,
        "rating_count": agent.rating_count if agent else None,
    }


# ------------------------------------------------------------------
# Categories
# ------------------------------------------------------------------


@router.get("/categories")
async def list_categories() -> dict:
    """List marketplace categories with agent counts."""
    return {"categories": _marketplace.list_categories()}
