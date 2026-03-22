"""SSO integrations — SAML 2.0 and OIDC for enterprise authentication."""

from __future__ import annotations

from dataclasses import dataclass

import httpx
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class SSOConfig:
    provider: str  # "saml" or "oidc"
    tenant_id: str
    # SAML fields
    idp_entity_id: str = ""
    idp_sso_url: str = ""
    idp_certificate: str = ""
    sp_entity_id: str = ""
    sp_acs_url: str = ""
    # OIDC fields
    client_id: str = ""
    client_secret: str = ""
    issuer_url: str = ""
    redirect_uri: str = ""
    scopes: str = "openid profile email"


@dataclass
class SSOUser:
    email: str
    name: str
    groups: list[str]
    raw_attributes: dict


class OIDCProvider:
    """OpenID Connect authentication provider."""

    def __init__(self, config: SSOConfig):
        self.config = config
        self._http = httpx.AsyncClient(timeout=30)
        self._discovery: dict | None = None

    async def get_authorization_url(self, state: str) -> str:
        """Generate the OIDC authorization URL for redirect."""
        discovery = await self._discover()
        auth_endpoint = discovery["authorization_endpoint"]
        params = {
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "response_type": "code",
            "scope": self.config.scopes,
            "state": state,
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{auth_endpoint}?{query}"

    async def exchange_code(self, code: str) -> SSOUser:
        """Exchange authorization code for tokens and user info."""
        discovery = await self._discover()
        token_resp = await self._http.post(
            discovery["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
                "redirect_uri": self.config.redirect_uri,
            },
        )
        token_resp.raise_for_status()
        tokens = token_resp.json()

        userinfo_resp = await self._http.get(
            discovery["userinfo_endpoint"],
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        userinfo_resp.raise_for_status()
        info = userinfo_resp.json()

        return SSOUser(
            email=info.get("email", ""),
            name=info.get("name", info.get("preferred_username", "")),
            groups=info.get("groups", []),
            raw_attributes=info,
        )

    async def _discover(self) -> dict:
        if self._discovery is None:
            resp = await self._http.get(
                f"{self.config.issuer_url}/.well-known/openid-configuration"
            )
            resp.raise_for_status()
            self._discovery = resp.json()
        return self._discovery


class SAMLProvider:
    """SAML 2.0 authentication provider (stub — needs python3-saml)."""

    def __init__(self, config: SSOConfig):
        self.config = config

    def get_login_url(self) -> str:
        """Generate SAML AuthnRequest redirect URL."""
        # In production, use python3-saml to generate proper SAML request
        return f"{self.config.idp_sso_url}?SAMLRequest=..."

    def process_response(self, saml_response: str) -> SSOUser:
        """Process SAML Response and extract user attributes."""
        # In production, validate signature, parse XML, extract NameID + attributes
        logger.warning("saml.stub_response_processing")
        return SSOUser(email="", name="", groups=[], raw_attributes={})


class SSOManager:
    """Manages SSO configurations per tenant."""

    def __init__(self) -> None:
        self._configs: dict[str, SSOConfig] = {}

    def configure(self, tenant_id: str, config: SSOConfig) -> None:
        config.tenant_id = tenant_id
        self._configs[tenant_id] = config

    def get_config(self, tenant_id: str) -> SSOConfig | None:
        return self._configs.get(tenant_id)

    def get_provider(self, tenant_id: str) -> OIDCProvider | SAMLProvider | None:
        config = self.get_config(tenant_id)
        if not config:
            return None
        if config.provider == "oidc":
            return OIDCProvider(config)
        elif config.provider == "saml":
            return SAMLProvider(config)
        return None
