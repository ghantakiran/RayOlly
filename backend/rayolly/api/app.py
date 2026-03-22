"""RayOlly API application factory."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import clickhouse_connect
import nats as nats_client
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from rayolly import __version__
from rayolly.api.middleware.cors_config import get_cors_origins
from rayolly.api.middleware.error_handler import ErrorHandlerMiddleware
from rayolly.api.middleware.logging import RequestLoggingMiddleware
from rayolly.api.middleware.rate_limit import RateLimitMiddleware
from rayolly.api.middleware.rbac import RBACMiddleware
from rayolly.api.middleware.request_id import RequestIdMiddleware
from rayolly.api.middleware.tenant import TenantMiddleware
from rayolly.core.config import get_settings
from rayolly.core.logging import setup_logging
from rayolly.services.metadata.database import close_db, init_db

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    setup_logging(debug=settings.server.debug)

    # Connect to NATS (optional — app works without it for queries)
    app.state.nats = None
    try:
        app.state.nats = await nats_client.connect(
            settings.nats.url,
            max_reconnect_attempts=2,
            reconnect_time_wait=1,
            connect_timeout=3,
        )
        logger.info("nats_connected", url=settings.nats.url)
    except Exception as e:
        logger.warning("nats_unavailable_ingestion_disabled", error=str(e))

    # Connect to Redis
    try:
        app.state.redis = Redis.from_url(
            settings.redis.url,
            max_connections=settings.redis.max_connections,
            decode_responses=True,
        )
        await app.state.redis.ping()
        logger.info("redis_connected", url=settings.redis.url)
    except Exception as e:
        logger.warning("redis_connection_failed", error=str(e))
        app.state.redis = None

    # Connect to PostgreSQL metadata store
    app.state.db_session_factory = None
    try:
        app.state.db_session_factory = await init_db(settings.postgres.url)
        logger.info("postgres_connected", url=settings.postgres.url.split("@")[-1])
    except Exception as e:
        logger.warning("postgres_unavailable", error=str(e))

    # Connect to ClickHouse (optional — app works without it for non-query endpoints)
    app.state.clickhouse = None
    try:
        app.state.clickhouse = clickhouse_connect.get_client(
            host=settings.clickhouse.host,
            port=int(settings.clickhouse.port),
            database=settings.clickhouse.database,
            username=settings.clickhouse.user,
            password=settings.clickhouse.password,
        )
        app.state.clickhouse.ping()
        logger.info("clickhouse_connected", host=settings.clickhouse.host)
    except Exception as e:
        logger.warning("clickhouse_unavailable_queries_disabled", error=str(e))

    # Start OTLP gRPC server in background
    app.state.grpc_task = None
    try:
        from rayolly.grpc.server import serve as grpc_serve
        from rayolly.services.ingestion.pipeline import IngestionPipeline

        grpc_pipeline = IngestionPipeline(
            nats_client=app.state.nats,
            clickhouse_client=app.state.clickhouse,
        )
        app.state.grpc_task = asyncio.create_task(grpc_serve(grpc_pipeline, port=4317))
        logger.info("grpc_server_starting", port=4317)
    except Exception as e:
        logger.warning("grpc_server_failed", error=str(e))

    yield

    # Cleanup
    if app.state.grpc_task is not None:
        app.state.grpc_task.cancel()
        try:
            await app.state.grpc_task
        except asyncio.CancelledError:
            pass
        logger.info("grpc_server_stopped")
    if app.state.nats:
        await app.state.nats.close()
    if app.state.redis:
        await app.state.redis.close()
    if app.state.db_session_factory:
        await close_db()
    if app.state.clickhouse:
        app.state.clickhouse.close()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="RayOlly API",
        description="AI-Native Observability Platform",
        version=__version__,
        lifespan=lifespan,
        debug=settings.server.debug,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Set default state so endpoints don't crash when services are unavailable
    app.state.nats = None
    app.state.redis = None
    app.state.clickhouse = None
    app.state.db_session_factory = None

    # Middleware (order matters — last added = first executed)
    # 7. CORSMiddleware (innermost)
    env = os.environ.get("RAYOLLY_ENV", "development")
    cors_origins = get_cors_origins(env)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # 6. RBACMiddleware (runs after tenant + role are resolved)
    app.add_middleware(RBACMiddleware)
    # 5. TenantMiddleware (extracts tenant_id and user_role)
    app.add_middleware(TenantMiddleware)
    # 4. RateLimitMiddleware (after tenant is extracted)
    app.add_middleware(RateLimitMiddleware)
    # 3. RequestLoggingMiddleware (has request_id available)
    app.add_middleware(RequestLoggingMiddleware)
    # 2. RequestIdMiddleware
    app.add_middleware(RequestIdMiddleware)
    # 1. ErrorHandlerMiddleware (outermost — catches all exceptions)
    app.add_middleware(ErrorHandlerMiddleware)

    # Import routes lazily to avoid circular imports and allow graceful degradation
    _register_routes(app)

    return app


def _register_routes(app: FastAPI) -> None:
    """Register all API route modules. Skip modules that fail to import."""
    route_modules = [
        ("rayolly.api.routes.auth", "router"),
        ("rayolly.api.routes.health", "router"),
        ("rayolly.api.routes.ingest", "router"),
        ("rayolly.api.routes.compat", "router"),
        ("rayolly.api.routes.query", "router"),
        ("rayolly.api.routes.logs", "router"),
        ("rayolly.api.routes.alerts", "router"),
        ("rayolly.api.routes.alerts", "incidents_router"),
        ("rayolly.api.routes.apm", "router"),
        ("rayolly.api.routes.infrastructure", "router"),
        ("rayolly.api.routes.rum", "router"),
        ("rayolly.api.routes.synthetics", "router"),
        ("rayolly.api.routes.agents", "router"),
        ("rayolly.api.routes.agent_observability", "router"),
        ("rayolly.api.routes.integrations", "router"),
        ("rayolly.api.routes.dashboard", "router"),
        ("rayolly.api.routes.log_data", "router"),
        ("rayolly.api.routes.metric_data", "router"),
        ("rayolly.api.routes.trace_data", "router"),
        ("rayolly.api.routes.apm_data", "router"),
        ("rayolly.api.routes.alert_data", "router"),
        ("rayolly.api.routes.storage", "router"),
        ("rayolly.api.routes.sso", "router"),
        ("rayolly.api.routes.scim", "router"),
        ("rayolly.api.routes.marketplace", "router"),
        ("rayolly.api.routes.benchmarks", "router"),
    ]

    for module_path, router_name in route_modules:
        try:
            import importlib
            module = importlib.import_module(module_path)
            router = getattr(module, router_name)
            app.include_router(router)
            logger.debug("route_registered", module=module_path, router=router_name)
        except Exception as e:
            logger.warning(
                "route_registration_failed",
                module=module_path,
                router=router_name,
                error=str(e),
            )


app = create_app()
