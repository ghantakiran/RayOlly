"""Authentication service for RayOlly.

Handles password-based login, API key verification, and JWT token management.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from passlib.context import CryptContext

from .models import APIKey, User
from .repositories import APIKeyRepository, UserRepository

__all__ = ["AuthService", "TokenPayload"]

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

# API keys are 40-char hex strings; first 8 chars serve as a lookup prefix.
_API_KEY_LENGTH = 40


@dataclass(frozen=True, slots=True)
class TokenPayload:
    """Decoded JWT payload."""

    sub: uuid.UUID  # user id
    tenant_id: str
    org_id: uuid.UUID
    role: str
    scopes: list[str]
    exp: datetime


class AuthService:
    """Stateless authentication facade.

    Args:
        user_repo: Repository for user lookups.
        api_key_repo: Repository for API key lookups.
        jwt_secret: Secret used to sign / verify JWTs.
        jwt_algorithm: Algorithm for JWT signing (default HS256).
        access_token_ttl: Lifetime of access tokens.
    """

    def __init__(
        self,
        user_repo: UserRepository,
        api_key_repo: APIKeyRepository,
        jwt_secret: str,
        jwt_algorithm: str = "HS256",
        access_token_ttl: timedelta = timedelta(hours=1),
    ) -> None:
        self._user_repo = user_repo
        self._api_key_repo = api_key_repo
        self._jwt_secret = jwt_secret
        self._jwt_algorithm = jwt_algorithm
        self._access_token_ttl = access_token_ttl

    # ------------------------------------------------------------------
    # Password authentication
    # ------------------------------------------------------------------

    async def authenticate_password(
        self,
        email: str,
        password: str,
    ) -> User | None:
        """Verify email + password and return the user, or ``None``."""
        user = await self._user_repo.get_by_email(email)
        if user is None:
            # Run a dummy verify to prevent timing attacks.
            self.verify_password(password, "$2b$12$" + "x" * 53)
            return None
        if not user.is_active:
            return None
        if not self.verify_password(password, user.password_hash):
            return None
        return user

    # ------------------------------------------------------------------
    # API key authentication
    # ------------------------------------------------------------------

    async def authenticate_api_key(
        self,
        raw_key: str,
    ) -> tuple[str, list[str]] | None:
        """Authenticate an API key.

        Returns:
            ``(tenant_id, scopes)`` on success, or ``None`` on failure.
        """
        if len(raw_key) < 8:
            return None

        prefix = raw_key[:8]
        api_key = await self._api_key_repo.get_by_prefix(prefix)
        if api_key is None:
            return None

        # Verify full key against stored hash.
        if not self.verify_password(raw_key, api_key.key_hash):
            return None

        # Check expiration.
        if api_key.expires_at is not None:
            if datetime.now(UTC) >= api_key.expires_at:
                return None

        # Check active.
        if not api_key.is_active:
            return None

        # Update last-used timestamp (fire-and-forget within the same session).
        await self._api_key_repo.update_last_used(api_key.id)

        scopes: list[str] = api_key.scopes if isinstance(api_key.scopes, list) else []
        return (api_key.tenant_id, scopes)

    # ------------------------------------------------------------------
    # JWT management
    # ------------------------------------------------------------------

    def create_access_token(self, user: User) -> str:
        """Issue a signed JWT for the given user."""
        now = datetime.now(UTC)
        payload = {
            "sub": str(user.id),
            "tenant_id": str(user.org_id),  # org doubles as tenant in single-org mode
            "org_id": str(user.org_id),
            "role": user.role,
            "scopes": _role_scopes(user.role),
            "iat": now,
            "exp": now + self._access_token_ttl,
        }
        return jwt.encode(payload, self._jwt_secret, algorithm=self._jwt_algorithm)

    def verify_token(self, token: str) -> TokenPayload | None:
        """Decode and validate a JWT.  Returns ``None`` on any failure."""
        try:
            data = jwt.decode(
                token,
                self._jwt_secret,
                algorithms=[self._jwt_algorithm],
            )
            return TokenPayload(
                sub=uuid.UUID(data["sub"]),
                tenant_id=data["tenant_id"],
                org_id=uuid.UUID(data["org_id"]),
                role=data["role"],
                scopes=data.get("scopes", []),
                exp=datetime.fromtimestamp(data["exp"], tz=UTC),
            )
        except (jwt.PyJWTError, KeyError, ValueError):
            return None

    # ------------------------------------------------------------------
    # API key generation
    # ------------------------------------------------------------------

    async def create_api_key(
        self,
        name: str,
        tenant_id: str,
        org_id: uuid.UUID,
        scopes: list[str],
        created_by: uuid.UUID,
        expires_at: datetime | None = None,
    ) -> tuple[str, APIKey]:
        """Generate a new API key.

        Returns:
            ``(raw_key, api_key_model)`` — the raw key is shown to the user
            exactly once and never stored.
        """
        raw_key = secrets.token_hex(_API_KEY_LENGTH // 2)  # 40 hex chars
        prefix = raw_key[:8]
        key_hash = self.hash_password(raw_key)

        api_key = await self._api_key_repo.create(
            name=name,
            key_hash=key_hash,
            key_prefix=prefix,
            tenant_id=tenant_id,
            org_id=org_id,
            scopes=scopes,
            created_by=created_by,
            expires_at=expires_at,
        )
        return (raw_key, api_key)

    # ------------------------------------------------------------------
    # Password hashing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def hash_password(password: str) -> str:
        """Return a bcrypt hash of the supplied plaintext."""
        return _pwd_ctx.hash(password)

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """Verify *password* against a bcrypt *password_hash*."""
        return _pwd_ctx.verify(password, password_hash)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _role_scopes(role: str) -> list[str]:
    """Map a user role to a list of granted scopes."""
    base = ["read"]
    if role in ("editor", "admin"):
        base.append("write")
    if role == "admin":
        base.extend(["admin", "manage_users", "manage_keys"])
    return base
