"""SSO API routes — OIDC and SAML 2.0 authentication flows."""

from __future__ import annotations

import secrets
import uuid
from typing import Any

import jwt
import structlog
from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel

from rayolly.core.config import get_settings
from rayolly.services.auth.sso import OIDCProvider, SAMLProvider, SSOConfig, SSOManager

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/auth/sso", tags=["sso"])

# Shared SSO manager instance
_sso_manager = SSOManager()

# Pending OIDC states (in production, use Redis)
_pending_states: dict[str, str] = {}  # state -> tenant_id


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class SSOConfigRequest(BaseModel):
    provider: str  # "oidc" or "saml"
    # OIDC
    client_id: str = ""
    client_secret: str = ""
    issuer_url: str = ""
    redirect_uri: str = ""
    scopes: str = "openid profile email"
    # SAML
    idp_entity_id: str = ""
    idp_sso_url: str = ""
    idp_certificate: str = ""
    sp_entity_id: str = ""
    sp_acs_url: str = ""


class SSOConfigResponse(BaseModel):
    provider: str
    configured: bool
    issuer_url: str = ""
    idp_entity_id: str = ""


# ---------------------------------------------------------------------------
# OIDC flow
# ---------------------------------------------------------------------------


@router.get("/oidc/authorize")
async def oidc_authorize(
    request: Request,
    tenant_id: str = Query(..., description="Tenant identifier"),
) -> dict[str, str]:
    """Redirect user to OIDC provider (Okta, Google, Azure AD, etc.)."""
    provider = _sso_manager.get_provider(tenant_id)
    if not isinstance(provider, OIDCProvider):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="OIDC not configured for this tenant",
        )

    state = secrets.token_urlsafe(32)
    _pending_states[state] = tenant_id

    redirect_url = await provider.get_authorization_url(state=state)
    return {"redirect_url": redirect_url}


@router.get("/oidc/callback")
async def oidc_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
) -> dict[str, Any]:
    """Handle OIDC callback — exchange code for tokens, create/update user, return JWT."""
    tenant_id = _pending_states.pop(state, None)
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired state parameter",
        )

    provider = _sso_manager.get_provider(tenant_id)
    if not isinstance(provider, OIDCProvider):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="OIDC not configured for this tenant",
        )

    try:
        sso_user = await provider.exchange_code(code)
    except Exception as exc:
        logger.error("oidc.code_exchange_failed", error=str(exc), tenant=tenant_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to authenticate with identity provider",
        )

    # Issue internal JWT
    settings = get_settings()
    token = jwt.encode(
        {
            "sub": sso_user.email,
            "email": sso_user.email,
            "name": sso_user.name,
            "tenant_id": tenant_id,
            "groups": sso_user.groups,
            "role": "member",
            "jti": str(uuid.uuid4()),
        },
        settings.auth.jwt_secret,
        algorithm=settings.auth.jwt_algorithm,
    )

    logger.info("oidc.login_success", email=sso_user.email, tenant=tenant_id)
    return {"access_token": token, "token_type": "bearer", "email": sso_user.email}


# ---------------------------------------------------------------------------
# SAML flow
# ---------------------------------------------------------------------------


@router.get("/saml/login")
async def saml_login(
    tenant_id: str = Query(..., description="Tenant identifier"),
) -> dict[str, str]:
    """Redirect user to SAML IdP."""
    provider = _sso_manager.get_provider(tenant_id)
    if not isinstance(provider, SAMLProvider):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SAML not configured for this tenant",
        )

    redirect_url = provider.get_login_url()
    return {"redirect_url": redirect_url}


@router.post("/saml/acs")
async def saml_acs(request: Request) -> dict[str, Any]:
    """SAML Assertion Consumer Service — process SAML Response, return JWT."""
    form = await request.form()
    saml_response = str(form.get("SAMLResponse", ""))
    if not saml_response:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing SAMLResponse",
        )

    # In production: determine tenant from RelayState or ACS URL
    tenant_id = str(form.get("RelayState", "default"))
    provider = _sso_manager.get_provider(tenant_id)
    if not isinstance(provider, SAMLProvider):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SAML not configured for this tenant",
        )

    sso_user = provider.process_response(saml_response)
    if not sso_user.email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="SAML authentication failed",
        )

    settings = get_settings()
    token = jwt.encode(
        {
            "sub": sso_user.email,
            "email": sso_user.email,
            "name": sso_user.name,
            "tenant_id": tenant_id,
            "groups": sso_user.groups,
            "role": "member",
            "jti": str(uuid.uuid4()),
        },
        settings.auth.jwt_secret,
        algorithm=settings.auth.jwt_algorithm,
    )

    logger.info("saml.login_success", email=sso_user.email, tenant=tenant_id)
    return {"access_token": token, "token_type": "bearer", "email": sso_user.email}


# ---------------------------------------------------------------------------
# SSO configuration (admin-only)
# ---------------------------------------------------------------------------


@router.get("/config")
async def get_sso_config(
    request: Request,
    tenant_id: str = Query(...),
) -> SSOConfigResponse:
    """Get SSO configuration for a tenant (admin only)."""
    config = _sso_manager.get_config(tenant_id)
    if not config:
        return SSOConfigResponse(provider="none", configured=False)
    return SSOConfigResponse(
        provider=config.provider,
        configured=True,
        issuer_url=config.issuer_url,
        idp_entity_id=config.idp_entity_id,
    )


@router.put("/config")
async def update_sso_config(
    request: Request,
    tenant_id: str = Query(...),
    body: SSOConfigRequest = ...,
) -> dict[str, str]:
    """Update SSO configuration for a tenant (admin only)."""
    config = SSOConfig(
        provider=body.provider,
        tenant_id=tenant_id,
        client_id=body.client_id,
        client_secret=body.client_secret,
        issuer_url=body.issuer_url,
        redirect_uri=body.redirect_uri,
        scopes=body.scopes,
        idp_entity_id=body.idp_entity_id,
        idp_sso_url=body.idp_sso_url,
        idp_certificate=body.idp_certificate,
        sp_entity_id=body.sp_entity_id,
        sp_acs_url=body.sp_acs_url,
    )
    _sso_manager.configure(tenant_id, config)
    logger.info("sso.config_updated", tenant=tenant_id, provider=body.provider)
    return {"status": "ok", "provider": body.provider}
