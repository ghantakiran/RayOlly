"""ClickHouse connection pool for high-concurrency query handling.

Manages a fixed-size pool of ClickHouse clients with async semaphore-based
access control.  Each connection is created once and recycled; health-checks
are performed on acquire to transparently replace dead connections.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import clickhouse_connect
import structlog

logger = structlog.get_logger(__name__)


class ClickHousePool:
    """Async-safe connection pool for ClickHouse ``clickhouse_connect`` clients.

    Usage::

        pool = ClickHousePool(host="localhost", port=8123, ...)
        await pool.initialize()

        async with pool.acquire() as client:
            result = client.query("SELECT 1")

        await pool.close()
    """

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        database: str = "default",
        pool_size: int = 10,
        connect_timeout: int = 10,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._database = database
        self._pool_size = pool_size
        self._connect_timeout = connect_timeout
        self._semaphore: asyncio.Semaphore | None = None
        self._available: asyncio.Queue[Any] = asyncio.Queue()
        self._all_clients: list[Any] = []
        self._closed = False

    async def initialize(self) -> None:
        """Create the pool of ClickHouse connections."""
        self._semaphore = asyncio.Semaphore(self._pool_size)
        for i in range(self._pool_size):
            client = self._create_client()
            self._all_clients.append(client)
            await self._available.put(client)
        logger.info("ch_pool.initialized", size=self._pool_size, host=self._host)

    def _create_client(self) -> Any:
        """Create a single ClickHouse client."""
        return clickhouse_connect.get_client(
            host=self._host,
            port=self._port,
            username=self._username,
            password=self._password,
            database=self._database,
            connect_timeout=self._connect_timeout,
        )

    def _health_check(self, client: Any) -> bool:
        """Return True if the client connection is alive."""
        try:
            return client.ping()
        except Exception:
            return False

    def _replace_client(self, dead_client: Any) -> Any:
        """Close a dead client and create a replacement."""
        try:
            dead_client.close()
        except Exception:
            pass
        if dead_client in self._all_clients:
            self._all_clients.remove(dead_client)
        new_client = self._create_client()
        self._all_clients.append(new_client)
        logger.info("ch_pool.connection_replaced")
        return new_client

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[Any]:
        """Acquire a connection from the pool.

        Performs a health-check and replaces the connection transparently
        if it has gone stale.
        """
        if self._closed:
            raise RuntimeError("Connection pool is closed")
        if self._semaphore is None:
            raise RuntimeError("Connection pool not initialized — call initialize() first")

        async with self._semaphore:
            client = await self._available.get()
            try:
                # Transparent health-check
                if not self._health_check(client):
                    logger.warning("ch_pool.stale_connection_detected")
                    client = self._replace_client(client)
                yield client
            except Exception:
                # On query-level errors the connection itself may still be fine,
                # so we just return it.  If the connection itself is broken the
                # next acquire() will detect it via health_check.
                raise
            finally:
                if not self._closed:
                    await self._available.put(client)

    # ------------------------------------------------------------------
    # Convenience methods (single-connection, for simple / legacy callers)
    # ------------------------------------------------------------------

    def query(self, sql: str) -> Any:
        """Synchronous query on the first available client (non-pooled)."""
        if not self._all_clients:
            raise RuntimeError("Connection pool not initialized")
        return self._all_clients[0].query(sql)

    def insert(self, *args: Any, **kwargs: Any) -> Any:
        """Synchronous insert on the first available client."""
        if not self._all_clients:
            raise RuntimeError("Connection pool not initialized")
        return self._all_clients[0].insert(*args, **kwargs)

    def ping(self) -> bool:
        """Ping using the first available client."""
        if self._all_clients:
            return self._health_check(self._all_clients[0])
        return False

    @property
    def size(self) -> int:
        return len(self._all_clients)

    @property
    def available_count(self) -> int:
        return self._available.qsize()

    async def close(self) -> None:
        """Close all connections in the pool."""
        self._closed = True
        for client in self._all_clients:
            try:
                client.close()
            except Exception:
                pass
        self._all_clients.clear()
        # Drain the queue
        while not self._available.empty():
            try:
                self._available.get_nowait()
            except asyncio.QueueEmpty:
                break
        logger.info("ch_pool.closed")
