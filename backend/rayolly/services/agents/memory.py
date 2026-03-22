"""Agent memory system — short-term (Redis) and long-term (PostgreSQL) storage."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Short-term memory TTL (seconds)
# ---------------------------------------------------------------------------
SHORT_TERM_TTL = 3600  # 1 hour


@dataclass
class MemoryEntry:
    """Single memory entry with metadata."""

    key: str
    value: str
    timestamp: float = field(default_factory=time.time)
    context: dict[str, Any] = field(default_factory=dict)


class AgentMemoryStore:
    """Dual-layer memory: Redis for ephemeral conversation state,
    PostgreSQL (via asyncpg pool) for persistent knowledge."""

    def __init__(self, redis: Redis, pg_pool: Any | None = None) -> None:
        self._redis = redis
        self._pg = pg_pool  # asyncpg connection pool

    # ------------------------------------------------------------------
    # Short-term memory (Redis)  — scoped per execution
    # ------------------------------------------------------------------

    def _st_key(self, execution_id: str) -> str:
        return f"agent:memory:st:{execution_id}"

    async def get_short_term(self, execution_id: str) -> list[dict[str, Any]]:
        """Return the conversation history for a running execution."""
        raw = await self._redis.get(self._st_key(execution_id))
        if raw is None:
            return []
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Corrupt short-term memory for %s", execution_id)
            return []

    async def set_short_term(
        self, execution_id: str, messages: list[dict[str, Any]]
    ) -> None:
        """Persist conversation history with a TTL."""
        await self._redis.set(
            self._st_key(execution_id),
            json.dumps(messages, default=str),
            ex=SHORT_TERM_TTL,
        )

    async def clear_short_term(self, execution_id: str) -> None:
        await self._redis.delete(self._st_key(execution_id))

    # ------------------------------------------------------------------
    # Long-term memory (PostgreSQL)
    # ------------------------------------------------------------------

    def _validate_pg(self) -> None:
        if self._pg is None:
            raise RuntimeError(
                "PostgreSQL pool is not configured — long-term memory unavailable"
            )

    async def get_long_term(
        self, tenant_id: str, agent_type: str, key: str
    ) -> str | None:
        """Retrieve a single long-term memory entry."""
        self._validate_pg()
        row = await self._pg.fetchrow(
            """
            SELECT value FROM agent_memory
            WHERE tenant_id = $1 AND agent_type = $2 AND key = $3
            """,
            tenant_id,
            agent_type,
            key,
        )
        return row["value"] if row else None

    async def set_long_term(
        self,
        tenant_id: str,
        agent_type: str,
        key: str,
        value: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Upsert a long-term memory entry."""
        self._validate_pg()
        await self._pg.execute(
            """
            INSERT INTO agent_memory (tenant_id, agent_type, key, value, context, updated_at)
            VALUES ($1, $2, $3, $4, $5::jsonb, NOW())
            ON CONFLICT (tenant_id, agent_type, key)
            DO UPDATE SET value = EXCLUDED.value,
                         context = EXCLUDED.context,
                         updated_at = NOW()
            """,
            tenant_id,
            agent_type,
            key,
            value,
            json.dumps(context or {}),
        )

    async def search_long_term(
        self, tenant_id: str, agent_type: str, query: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Full-text search over long-term memory entries."""
        self._validate_pg()
        rows = await self._pg.fetch(
            """
            SELECT key, value, context, updated_at
            FROM agent_memory
            WHERE tenant_id = $1
              AND agent_type = $2
              AND (value ILIKE '%' || $3 || '%' OR key ILIKE '%' || $3 || '%')
            ORDER BY updated_at DESC
            LIMIT $4
            """,
            tenant_id,
            agent_type,
            query,
            limit,
        )
        return [dict(r) for r in rows]

    async def get_past_investigations(
        self, tenant_id: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Return past agent execution summaries for a tenant."""
        self._validate_pg()
        rows = await self._pg.fetch(
            """
            SELECT id, agent_type, status, input_summary, output_summary,
                   started_at, completed_at, tokens_used, cost
            FROM agent_executions
            WHERE tenant_id = $1
            ORDER BY started_at DESC
            LIMIT $2
            """,
            tenant_id,
            limit,
        )
        return [dict(r) for r in rows]
