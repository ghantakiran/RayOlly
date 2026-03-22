"""Health check utilities."""
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

async def check_health(app_state: Any) -> dict:
    """Detailed health check for all components."""
    components = {}
    overall = "healthy"

    # ClickHouse
    ch = getattr(app_state, "clickhouse", None)
    if ch:
        try:
            ch.ping()
            components["clickhouse"] = {"status": "healthy"}
        except Exception as e:
            components["clickhouse"] = {"status": "unhealthy", "error": str(e)}
            overall = "degraded"
    else:
        components["clickhouse"] = {"status": "not_configured"}

    # Redis
    redis = getattr(app_state, "redis", None)
    if redis:
        try:
            await redis.ping()
            components["redis"] = {"status": "healthy"}
        except Exception as e:
            components["redis"] = {"status": "unhealthy", "error": str(e)}
            overall = "degraded"
    else:
        components["redis"] = {"status": "not_configured"}

    # NATS
    nats = getattr(app_state, "nats", None)
    if nats and nats.is_connected:
        components["nats"] = {"status": "healthy"}
    elif nats:
        components["nats"] = {"status": "unhealthy", "error": "disconnected"}
        overall = "degraded"
    else:
        components["nats"] = {"status": "not_configured"}

    return {"status": overall, "components": components}
