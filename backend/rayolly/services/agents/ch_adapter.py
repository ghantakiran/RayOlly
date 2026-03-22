"""Adapter wrapping clickhouse_connect client for agent tools.

Agent tools were written expecting `.execute(sql)` returning list of tuples.
clickhouse_connect uses `.query(sql)` returning QueryResult.
This adapter bridges the gap and also remaps table/column names.
"""

from __future__ import annotations

import re
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Table name remapping: tools use short names, real tables are database.table
TABLE_MAP = {
    " logs ": " logs.log_entries ",
    " metrics ": " metrics.samples ",
    " traces ": " traces.spans ",
    " agents ": " agents.agent_executions ",
    " events ": " events.events ",
    "FROM logs\n": "FROM logs.log_entries\n",
    "FROM logs ": "FROM logs.log_entries ",
    "FROM metrics\n": "FROM metrics.samples\n",
    "FROM metrics ": "FROM metrics.samples ",
    "FROM traces\n": "FROM traces.spans\n",
    "FROM traces ": "FROM traces.spans ",
}

# Column name remapping: tools use various names, real columns differ
COLUMN_MAP = {
    "service_name": "service",
    "host_name": "host",
    "log_message": "body",
    "message": "body",
    "metric_value": "value",
    "span_name": "operation_name",
}


class ClickHouseAdapter:
    """Wraps clickhouse_connect client to provide .execute() compatibility."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def execute(self, sql: str) -> list[tuple]:
        """Execute SQL and return list of tuples (like clickhouse-driver)."""
        sql = self._remap_sql(sql)
        try:
            result = self._client.query(sql)
            return result.result_rows
        except Exception as e:
            logger.warning("ch_adapter.query_failed", error=str(e), sql=sql[:200])
            raise

    def query(self, sql: str) -> Any:
        """Pass-through to the real client."""
        sql = self._remap_sql(sql)
        return self._client.query(sql)

    def insert(self, *args: Any, **kwargs: Any) -> Any:
        return self._client.insert(*args, **kwargs)

    def ping(self) -> bool:
        return self._client.ping()

    def _remap_sql(self, sql: str) -> str:
        """Remap table and column names to match actual ClickHouse schema."""
        # Table remapping
        for old, new in TABLE_MAP.items():
            sql = sql.replace(old, new)

        # Also handle FROM without trailing space/newline
        sql = re.sub(r'\bFROM logs\b(?!\.)', 'FROM logs.log_entries', sql)
        sql = re.sub(r'\bFROM metrics\b(?!\.)', 'FROM metrics.samples', sql)
        sql = re.sub(r'\bFROM traces\b(?!\.)', 'FROM traces.spans', sql)
        sql = re.sub(r'\bFROM events\b(?!\.)', 'FROM events.events', sql)

        # Column remapping
        for old, new in COLUMN_MAP.items():
            sql = re.sub(rf'\b{old}\b', new, sql)

        return sql

    def __getattr__(self, name: str) -> Any:
        """Forward any other method to the underlying client."""
        return getattr(self._client, name)
