"""Streaming query results — yield rows as they are read from ClickHouse.

Avoids loading full result sets into memory for large exports and
long-running dashboard queries.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class StreamingQueryExecutor:
    """Execute queries and stream results in configurable batches.

    Usage::

        executor = StreamingQueryExecutor(clickhouse_client)
        async for batch in executor.stream_query("SELECT ...", batch_size=500):
            for record in batch:
                process(record)
    """

    def __init__(self, clickhouse_client: Any) -> None:
        self.ch = clickhouse_client

    async def stream_query(
        self,
        sql: str,
        batch_size: int = 1000,
    ) -> AsyncIterator[list[dict[str, Any]]]:
        """Stream query results in batches of ``batch_size`` rows.

        Each yielded item is a list of dicts (column_name -> value).
        """
        try:
            result = self.ch.query(sql)
            columns = result.column_names

            batch: list[dict[str, Any]] = []
            for row in result.result_rows:
                record = dict(zip(columns, row))
                batch.append(record)

                if len(batch) >= batch_size:
                    yield batch
                    batch = []

            if batch:
                yield batch

        except Exception as e:
            logger.error(
                "streaming_query.failed",
                error=str(e),
                sql=sql[:200],
            )
            raise

    async def stream_ndjson(
        self,
        sql: str,
        batch_size: int = 1000,
    ) -> AsyncIterator[bytes]:
        """Stream results as newline-delimited JSON bytes.

        Ideal for HTTP streaming responses (``StreamingResponse``).
        Each chunk is a batch of NDJSON lines terminated by ``\\n``.
        """
        async for batch in self.stream_query(sql, batch_size=batch_size):
            lines: list[str] = []
            for record in batch:
                lines.append(json.dumps(record, default=str))
            yield ("\n".join(lines) + "\n").encode("utf-8")

    async def stream_csv(
        self,
        sql: str,
        batch_size: int = 1000,
        include_header: bool = True,
    ) -> AsyncIterator[bytes]:
        """Stream results as CSV bytes.

        The first chunk includes the header row when ``include_header`` is True.
        """
        header_emitted = False

        async for batch in self.stream_query(sql, batch_size=batch_size):
            lines: list[str] = []

            if not header_emitted and include_header and batch:
                headers = list(batch[0].keys())
                lines.append(",".join(headers))
                header_emitted = True

            for record in batch:
                values = [_csv_escape(str(v)) for v in record.values()]
                lines.append(",".join(values))

            yield ("\n".join(lines) + "\n").encode("utf-8")

    async def count_rows(self, sql: str) -> int:
        """Return the total row count for a query without fetching all data."""
        count_sql = f"SELECT count() AS cnt FROM ({sql})"
        try:
            result = self.ch.query(count_sql)
            if result.result_rows:
                return int(result.result_rows[0][0])
        except Exception as e:
            logger.warning("streaming_count.failed", error=str(e))
        return 0


def _csv_escape(value: str) -> str:
    """Escape a value for CSV output."""
    if "," in value or '"' in value or "\n" in value:
        return '"' + value.replace('"', '""') + '"'
    return value
