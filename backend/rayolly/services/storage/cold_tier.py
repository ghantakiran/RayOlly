"""Cold tier storage -- writes aged data to S3 as Parquet files."""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import structlog

logger = structlog.get_logger(__name__)


class ColdTierWriter:
    """Compacts ClickHouse data to Parquet on S3/MinIO for long-term retention."""

    def __init__(
        self,
        clickhouse_client: Any,
        s3_client: Any,
        bucket: str = "rayolly-cold",
    ) -> None:
        self.ch = clickhouse_client
        self.s3 = s3_client
        self.bucket = bucket

    async def archive_logs(
        self,
        tenant_id: str,
        older_than_days: int = 7,
    ) -> dict:
        """Move logs older than *older_than_days* from ClickHouse to S3 Parquet."""
        cutoff = datetime.now(UTC) - timedelta(days=older_than_days)

        # Query data to archive
        sql = (
            "SELECT * FROM logs.log_entries "
            f"WHERE tenant_id = '{tenant_id}' "
            f"AND timestamp < '{cutoff.isoformat()}'"
        )
        result = self.ch.query(sql)

        if not result.result_rows:
            return {"archived": 0, "bytes": 0}

        # Convert to Parquet via PyArrow
        table = pa.table(
            {
                name: [row[i] for row in result.result_rows]
                for i, name in enumerate(result.column_names)
            }
        )

        buf = io.BytesIO()
        pq.write_table(table, buf, compression="zstd")
        parquet_bytes = buf.getvalue()

        # Upload to S3
        key = (
            f"{tenant_id}/logs/{cutoff.strftime('%Y/%m/%d')}/"
            f"archive_{datetime.now(UTC).strftime('%H%M%S')}.parquet"
        )
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=parquet_bytes)

        # Delete archived data from ClickHouse
        self.ch.command(
            "ALTER TABLE logs.log_entries DELETE "
            f"WHERE tenant_id = '{tenant_id}' "
            f"AND timestamp < '{cutoff.isoformat()}'"
        )

        logger.info(
            "cold_tier.logs_archived",
            tenant=tenant_id,
            rows=len(result.result_rows),
            bytes=len(parquet_bytes),
            key=key,
        )
        return {
            "archived": len(result.result_rows),
            "bytes": len(parquet_bytes),
            "key": key,
        }

    async def archive_metrics(
        self,
        tenant_id: str,
        older_than_days: int = 30,
    ) -> dict:
        """Archive old metric samples to Parquet (rollups stay in ClickHouse)."""
        cutoff = datetime.now(UTC) - timedelta(days=older_than_days)

        sql = (
            "SELECT * FROM metrics.samples "
            f"WHERE tenant_id = '{tenant_id}' "
            f"AND timestamp < '{cutoff.isoformat()}'"
        )
        result = self.ch.query(sql)

        if not result.result_rows:
            return {"archived": 0}

        table = pa.table(
            {
                name: [row[i] for row in result.result_rows]
                for i, name in enumerate(result.column_names)
            }
        )
        buf = io.BytesIO()
        pq.write_table(table, buf, compression="zstd")

        key = f"{tenant_id}/metrics/{cutoff.strftime('%Y/%m/%d')}/archive.parquet"
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=buf.getvalue())

        self.ch.command(
            "ALTER TABLE metrics.samples DELETE "
            f"WHERE tenant_id = '{tenant_id}' "
            f"AND timestamp < '{cutoff.isoformat()}'"
        )

        logger.info(
            "cold_tier.metrics_archived",
            tenant=tenant_id,
            rows=len(result.result_rows),
            key=key,
        )
        return {"archived": len(result.result_rows), "key": key}

    async def query_cold(self, tenant_id: str, sql_query: str) -> list:
        """Query cold-tier Parquet files via DuckDB."""
        import duckdb  # noqa: local import — optional dependency

        conn = duckdb.connect()
        conn.execute(
            "SET s3_endpoint='localhost:9002'; "
            "SET s3_access_key_id='minioadmin'; "
            "SET s3_secret_access_key='minioadmin'; "
            "SET s3_use_ssl=false; "
            "SET s3_url_style='path';"
        )

        parquet_path = f"s3://{self.bucket}/{tenant_id}/**/*.parquet"
        try:
            result = conn.execute(
                f"SELECT * FROM read_parquet('{parquet_path}') "
                f"WHERE {sql_query} LIMIT 1000"
            ).fetchall()
            return result
        except Exception as e:
            logger.warning("cold_tier.query_failed", error=str(e))
            return []
