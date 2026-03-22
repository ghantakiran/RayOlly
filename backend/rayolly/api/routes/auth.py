"""Authentication routes for RayOlly MVP."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, EmailStr

from rayolly.core.config import get_settings
from rayolly.services.metadata.auth import AuthService
from rayolly.services.metadata.repositories import APIKeyRepository, UserRepository

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# ---------------------------------------------------------------------------
# In-memory stores (fallback when PostgreSQL is unavailable)
# ---------------------------------------------------------------------------
_users: dict[str, dict[str, Any]] = {}  # email -> {email, name, password, role, tenant_id}
_api_keys: dict[str, list[dict[str, Any]]] = {}  # tenant_id -> [keys]

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str


class CreateApiKeyRequest(BaseModel):
    name: str


class UserResponse(BaseModel):
    email: str
    name: str
    role: str
    tenant_id: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class ApiKeyResponse(BaseModel):
    key: str
    name: str
    created_at: str


class ApiKeyListItem(BaseModel):
    name: str
    key_prefix: str
    created_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_token(email: str, tenant_id: str, role: str) -> tuple[str, int]:
    settings = get_settings()
    expires_delta = timedelta(minutes=settings.auth.access_token_expire_minutes)
    expire = datetime.now(UTC) + expires_delta
    payload = {
        "sub": email,
        "tenant_id": tenant_id,
        "role": role,
        "exp": expire,
    }
    token = jwt.encode(payload, settings.auth.jwt_secret, algorithm=settings.auth.jwt_algorithm)
    return token, int(expires_delta.total_seconds())


def _decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(
            token,
            settings.auth.jwt_secret,
            algorithms=[settings.auth.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def _get_current_user(authorization: str = Header(...)) -> dict[str, Any]:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization header")
    token = authorization.removeprefix("Bearer ")
    payload = _decode_token(token)
    email = payload.get("sub")
    if not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    # Return user from in-memory store or build from JWT claims
    user = _users.get(email, {
        "email": email,
        "name": email.split("@")[0],
        "role": payload.get("role", "admin"),
        "tenant_id": payload.get("tenant_id", "demo"),
    })
    return user


def _get_db_session_factory(request: Request):
    """Return the session factory from app state, or None."""
    return getattr(request.app.state, "db_session_factory", None)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request) -> TokenResponse:
    """Authenticate and return a JWT."""
    db_factory = _get_db_session_factory(request)

    # Try PostgreSQL first
    if db_factory is not None:
        try:
            async with db_factory() as session:
                user_repo = UserRepository(session)
                db_user = await user_repo.get_by_email(body.email)
                if db_user is not None:
                    # Verify password using bcrypt
                    if AuthService.verify_password(body.password, db_user.password_hash):
                        tenant_id = str(db_user.org_id)
                        token, expires_in = _create_token(db_user.email, tenant_id, db_user.role)
                        return TokenResponse(
                            access_token=token,
                            expires_in=expires_in,
                            user=UserResponse(
                                email=db_user.email,
                                name=db_user.name,
                                role=db_user.role,
                                tenant_id=tenant_id,
                            ),
                        )
                    else:
                        raise HTTPException(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid email or password",
                        )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning("postgres_login_fallback", error=str(e))

    # Fallback: in-memory / MVP mode (accepts password 'demo')
    if body.password != "demo":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    user = _users.get(body.email, {
        "email": body.email,
        "name": body.email.split("@")[0],
        "password": "demo",
        "role": "admin",
        "tenant_id": "demo",
    })

    token, expires_in = _create_token(user["email"], user["tenant_id"], user["role"])
    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
        user=UserResponse(
            email=user["email"],
            name=user["name"],
            role=user["role"],
            tenant_id=user["tenant_id"],
        ),
    )


@router.post("/register", response_model=TokenResponse)
async def register(body: RegisterRequest, request: Request) -> TokenResponse:
    """Register a new user. Persists to PostgreSQL when available, else in-memory."""
    db_factory = _get_db_session_factory(request)

    # Try PostgreSQL first
    if db_factory is not None:
        try:
            async with db_factory() as session:
                user_repo = UserRepository(session)
                from rayolly.services.metadata.repositories import OrganizationRepository

                # Check if user already exists
                existing = await user_repo.get_by_email(body.email)
                if existing is not None:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Email already registered",
                    )

                # Create a default organization for the user (slug from email domain)
                org_repo = OrganizationRepository(session)
                slug = body.email.split("@")[0].lower().replace(".", "-") + "-" + uuid.uuid4().hex[:6]
                org = await org_repo.create(
                    name=f"{body.name}'s Organization",
                    slug=slug,
                )

                # Create the user with hashed password
                password_hash = AuthService.hash_password(body.password)
                db_user = await user_repo.create(
                    email=body.email,
                    name=body.name,
                    password_hash=password_hash,
                    org_id=org.id,
                    role="admin",
                )
                await session.commit()

                tenant_id = str(db_user.org_id)
                token, expires_in = _create_token(db_user.email, tenant_id, db_user.role)
                return TokenResponse(
                    access_token=token,
                    expires_in=expires_in,
                    user=UserResponse(
                        email=db_user.email,
                        name=db_user.name,
                        role=db_user.role,
                        tenant_id=tenant_id,
                    ),
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning("postgres_register_fallback", error=str(e))

    # Fallback: in-memory
    if body.email in _users:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = {
        "email": body.email,
        "name": body.name,
        "password": body.password,
        "role": "admin",
        "tenant_id": "demo",
    }
    _users[body.email] = user

    token, expires_in = _create_token(user["email"], user["tenant_id"], user["role"])
    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
        user=UserResponse(
            email=user["email"],
            name=user["name"],
            role=user["role"],
            tenant_id=user["tenant_id"],
        ),
    )


@router.get("/me", response_model=UserResponse)
async def me(user: dict[str, Any] = Depends(_get_current_user)) -> UserResponse:
    """Return current user info from the JWT."""
    return UserResponse(
        email=user["email"],
        name=user["name"],
        role=user["role"],
        tenant_id=user["tenant_id"],
    )


@router.post("/api-keys", response_model=ApiKeyResponse)
async def create_api_key(
    body: CreateApiKeyRequest,
    request: Request,
    user: dict[str, Any] = Depends(_get_current_user),
) -> ApiKeyResponse:
    """Create an API key for the current tenant. The full key is shown only once."""
    tenant_id = user["tenant_id"]
    now = datetime.now(UTC).isoformat()
    db_factory = _get_db_session_factory(request)

    # Try PostgreSQL first
    if db_factory is not None:
        try:
            async with db_factory() as session:
                api_key_repo = APIKeyRepository(session)
                user_repo = UserRepository(session)

                # Resolve org_id and user_id from the JWT email
                db_user = await user_repo.get_by_email(user["email"])
                if db_user is not None:
                    auth_svc = AuthService(
                        user_repo=user_repo,
                        api_key_repo=api_key_repo,
                        jwt_secret=get_settings().auth.jwt_secret,
                    )
                    raw_key, api_key_record = await auth_svc.create_api_key(
                        name=body.name,
                        tenant_id=tenant_id,
                        org_id=db_user.org_id,
                        scopes=["read", "write"],
                        created_by=db_user.id,
                    )
                    await session.commit()
                    return ApiKeyResponse(
                        key=raw_key,
                        name=body.name,
                        created_at=api_key_record.created_at.isoformat(),
                    )
        except Exception as e:
            logger.warning("postgres_create_api_key_fallback", error=str(e))

    # Fallback: in-memory
    raw_key = f"ro_{secrets.token_hex(24)}"
    key_record = {
        "key_hash": raw_key,  # MVP: store plaintext; production would hash
        "name": body.name,
        "created_at": now,
        "tenant_id": tenant_id,
    }
    _api_keys.setdefault(tenant_id, []).append(key_record)
    return ApiKeyResponse(key=raw_key, name=body.name, created_at=now)


@router.get("/api-keys", response_model=list[ApiKeyListItem])
async def list_api_keys(
    request: Request,
    user: dict[str, Any] = Depends(_get_current_user),
) -> list[ApiKeyListItem]:
    """List API keys (masked) for the current tenant."""
    tenant_id = user["tenant_id"]
    db_factory = _get_db_session_factory(request)

    # Try PostgreSQL first
    if db_factory is not None:
        try:
            async with db_factory() as session:
                api_key_repo = APIKeyRepository(session)
                db_keys = await api_key_repo.list_by_tenant(tenant_id)
                return [
                    ApiKeyListItem(
                        name=k.name,
                        key_prefix=k.key_prefix + "...",
                        created_at=k.created_at.isoformat(),
                    )
                    for k in db_keys
                ]
        except Exception as e:
            logger.warning("postgres_list_api_keys_fallback", error=str(e))

    # Fallback: in-memory
    keys = _api_keys.get(tenant_id, [])
    return [
        ApiKeyListItem(
            name=k["name"],
            key_prefix=k["key_hash"][:10] + "...",
            created_at=k["created_at"],
        )
        for k in keys
    ]
