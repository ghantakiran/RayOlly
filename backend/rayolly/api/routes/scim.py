"""SCIM 2.0 API endpoints — user and group provisioning for identity providers."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

from rayolly.services.auth.scim import SCIMService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/scim/v2", tags=["scim"])

# Shared SCIM service instance
_scim_service = SCIMService()

SCIM_CONTENT_TYPE = "application/scim+json"


# ---------------------------------------------------------------------------
# SCIM 2.0 User endpoints
# ---------------------------------------------------------------------------


@router.get("/Users")
async def list_users(
    filter: str = Query("", alias="filter"),
    startIndex: int = Query(1, ge=1),
    count: int = Query(100, ge=1, le=1000),
) -> JSONResponse:
    """List provisioned users with optional SCIM filter."""
    result = await _scim_service.list_users(
        filter_str=filter, start=startIndex, count=count
    )
    return JSONResponse(content=result, media_type=SCIM_CONTENT_TYPE)


@router.post("/Users", status_code=status.HTTP_201_CREATED)
async def create_user(request: Request) -> JSONResponse:
    """Provision a new user from the identity provider."""
    body = await request.json()
    user = await _scim_service.create_user(body)
    return JSONResponse(
        content=SCIMService._user_to_dict(user),
        status_code=status.HTTP_201_CREATED,
        media_type=SCIM_CONTENT_TYPE,
    )


@router.get("/Users/{user_id}")
async def get_user(user_id: str) -> JSONResponse:
    """Get a single provisioned user."""
    user = await _scim_service.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return JSONResponse(
        content=SCIMService._user_to_dict(user), media_type=SCIM_CONTENT_TYPE
    )


@router.put("/Users/{user_id}")
async def replace_user(user_id: str, request: Request) -> JSONResponse:
    """Full replacement of a provisioned user."""
    body = await request.json()
    user = await _scim_service.update_user(user_id, body)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return JSONResponse(
        content=SCIMService._user_to_dict(user), media_type=SCIM_CONTENT_TYPE
    )


@router.patch("/Users/{user_id}")
async def patch_user(user_id: str, request: Request) -> JSONResponse:
    """Partial update of a provisioned user (e.g., deactivation)."""
    body = await request.json()
    # SCIM PATCH uses Operations array; flatten to simple updates
    updates: dict[str, Any] = {}
    for op in body.get("Operations", []):
        path = op.get("path", "")
        value = op.get("value")
        if path == "active" or (not path and isinstance(value, dict)):
            if isinstance(value, dict):
                updates.update(value)
            else:
                updates["active"] = value

    user = await _scim_service.update_user(user_id, updates)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return JSONResponse(
        content=SCIMService._user_to_dict(user), media_type=SCIM_CONTENT_TYPE
    )


@router.delete("/Users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: str) -> None:
    """Deprovision (deactivate) a user."""
    deleted = await _scim_service.delete_user(user_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )


# ---------------------------------------------------------------------------
# SCIM 2.0 Group endpoints
# ---------------------------------------------------------------------------


@router.get("/Groups")
async def list_groups(
    startIndex: int = Query(1, ge=1),
    count: int = Query(100, ge=1, le=1000),
) -> JSONResponse:
    """List provisioned groups."""
    result = await _scim_service.list_groups(start=startIndex, count=count)
    return JSONResponse(content=result, media_type=SCIM_CONTENT_TYPE)


@router.post("/Groups", status_code=status.HTTP_201_CREATED)
async def create_group(request: Request) -> JSONResponse:
    """Provision a new group from the identity provider."""
    body = await request.json()
    group = await _scim_service.create_group(body)
    return JSONResponse(
        content={
            "schemas": ["urn:ietf:params:scim:core:2.0:Group"],
            "id": group.id,
            "displayName": group.displayName,
            "members": group.members,
        },
        status_code=status.HTTP_201_CREATED,
        media_type=SCIM_CONTENT_TYPE,
    )


# ---------------------------------------------------------------------------
# SCIM 2.0 Service Provider Config & Schemas
# ---------------------------------------------------------------------------


@router.get("/ServiceProviderConfig")
async def service_provider_config() -> JSONResponse:
    """Return SCIM service provider capabilities."""
    return JSONResponse(
        content={
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"],
            "documentationUri": "https://docs.rayolly.dev/scim",
            "patch": {"supported": True},
            "bulk": {"supported": False, "maxOperations": 0, "maxPayloadSize": 0},
            "filter": {"supported": True, "maxResults": 1000},
            "changePassword": {"supported": False},
            "sort": {"supported": False},
            "etag": {"supported": False},
            "authenticationSchemes": [
                {
                    "type": "oauthbearertoken",
                    "name": "OAuth Bearer Token",
                    "description": "Authentication via OAuth 2.0 Bearer Token",
                }
            ],
        },
        media_type=SCIM_CONTENT_TYPE,
    )


@router.get("/Schemas")
async def schemas() -> JSONResponse:
    """Return SCIM resource schemas."""
    return JSONResponse(
        content={
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
            "totalResults": 2,
            "Resources": [
                {
                    "id": "urn:ietf:params:scim:schemas:core:2.0:User",
                    "name": "User",
                    "description": "SCIM User resource",
                    "attributes": [
                        {"name": "userName", "type": "string", "required": True},
                        {"name": "name", "type": "complex", "required": False},
                        {"name": "emails", "type": "complex", "multiValued": True},
                        {"name": "active", "type": "boolean", "required": False},
                    ],
                },
                {
                    "id": "urn:ietf:params:scim:schemas:core:2.0:Group",
                    "name": "Group",
                    "description": "SCIM Group resource",
                    "attributes": [
                        {"name": "displayName", "type": "string", "required": True},
                        {"name": "members", "type": "complex", "multiValued": True},
                    ],
                },
            ],
        },
        media_type=SCIM_CONTENT_TYPE,
    )
