"""Run the OTLP gRPC server standalone.

Usage::

    python -m rayolly.grpc.runner

Or started automatically by the API lifespan in ``rayolly.api.app``.
"""
from __future__ import annotations

import asyncio

import clickhouse_connect
import structlog

from rayolly.core.config import get_settings
from rayolly.grpc.server import serve
from rayolly.services.ingestion.pipeline import IngestionPipeline

logger = structlog.get_logger(__name__)


async def main() -> None:
    settings = get_settings()

    ch = clickhouse_connect.get_client(
        host=settings.clickhouse.host,
        port=int(settings.clickhouse.port),
        database=settings.clickhouse.database,
        username=settings.clickhouse.user,
        password=settings.clickhouse.password,
    )
    logger.info("clickhouse_connected", host=settings.clickhouse.host)

    pipeline = IngestionPipeline(clickhouse_client=ch)
    await serve(pipeline, port=4317)


if __name__ == "__main__":
    asyncio.run(main())
