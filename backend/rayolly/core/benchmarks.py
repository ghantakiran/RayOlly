"""Performance benchmarks for RayOlly core operations.

Provides an automated benchmark suite that measures ClickHouse query latency,
Redis round-trip time, and reports percentile statistics.  Designed to be
triggered from the admin API or CI pipelines.
"""

from __future__ import annotations

import statistics
import time
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class Benchmark:
    """Run and report performance benchmarks."""

    def __init__(
        self,
        clickhouse_client: Any = None,
        redis_client: Any = None,
    ) -> None:
        self.ch = clickhouse_client
        self.redis = redis_client

    async def run_all(self) -> dict[str, Any]:
        """Run every available benchmark and return aggregated results."""
        results: dict[str, Any] = {}
        if self.ch:
            results["clickhouse"] = await self._benchmark_clickhouse()
        if self.redis:
            results["redis"] = await self._benchmark_redis()
        return results

    # ------------------------------------------------------------------
    # ClickHouse benchmarks
    # ------------------------------------------------------------------

    CLICKHOUSE_QUERIES: dict[str, str] = {
        "simple_count": "SELECT count() FROM logs.log_entries",
        "filter_severity": (
            "SELECT count() FROM logs.log_entries WHERE severity = 'ERROR'"
        ),
        "group_by_service": (
            "SELECT service, count() FROM logs.log_entries GROUP BY service"
        ),
        "full_text_search": (
            "SELECT count() FROM logs.log_entries WHERE hasToken(body, 'timeout')"
        ),
        "time_range_1h": (
            "SELECT count() FROM logs.log_entries "
            "WHERE timestamp >= now() - INTERVAL 1 HOUR"
        ),
        "metrics_latest": (
            "SELECT metric_name, max(value) "
            "FROM metrics.samples GROUP BY metric_name"
        ),
        "trace_latency_avg": (
            "SELECT avg(duration_ns) FROM traces.spans WHERE service != ''"
        ),
        "metrics_rate_1m": (
            "SELECT toStartOfMinute(timestamp) AS ts, "
            "(max(value) - min(value)) / 60 AS rate "
            "FROM metrics.samples "
            "WHERE metric_name = 'http_requests_total' "
            "GROUP BY ts ORDER BY ts LIMIT 60"
        ),
    }

    async def _benchmark_clickhouse(
        self,
        iterations: int = 5,
    ) -> dict[str, dict[str, Any]]:
        results: dict[str, dict[str, Any]] = {}

        for name, sql in self.CLICKHOUSE_QUERIES.items():
            times: list[float] = []
            errors = 0
            for _ in range(iterations):
                start = time.perf_counter()
                try:
                    self.ch.query(sql)
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    times.append(elapsed_ms)
                except Exception:
                    errors += 1

            if times:
                sorted_times = sorted(times)
                p99_idx = max(0, int(len(sorted_times) * 0.99) - 1)
                results[name] = {
                    "p50_ms": round(statistics.median(times), 2),
                    "p99_ms": round(sorted_times[p99_idx], 2),
                    "avg_ms": round(statistics.mean(times), 2),
                    "min_ms": round(min(times), 2),
                    "max_ms": round(max(times), 2),
                    "runs": len(times),
                    "errors": errors,
                }
            else:
                results[name] = {
                    "p50_ms": -1,
                    "p99_ms": -1,
                    "avg_ms": -1,
                    "min_ms": -1,
                    "max_ms": -1,
                    "runs": 0,
                    "errors": errors,
                }

        return results

    # ------------------------------------------------------------------
    # Redis benchmarks
    # ------------------------------------------------------------------

    async def _benchmark_redis(
        self,
        iterations: int = 100,
    ) -> dict[str, dict[str, Any]]:
        set_get_times: list[float] = []
        pipeline_times: list[float] = []

        # SET / GET / DELETE round-trip
        for i in range(iterations):
            key = f"rayolly:bench:{i}"
            start = time.perf_counter()
            await self.redis.set(key, "benchmark_payload")
            await self.redis.get(key)
            await self.redis.delete(key)
            elapsed_ms = (time.perf_counter() - start) * 1000
            set_get_times.append(elapsed_ms)

        # Pipeline benchmark (batched ops)
        for i in range(0, iterations, 10):
            pipe = self.redis.pipeline()
            for j in range(10):
                key = f"rayolly:bench:pipe:{i + j}"
                pipe.set(key, "x")
                pipe.get(key)
                pipe.delete(key)
            start = time.perf_counter()
            await pipe.execute()
            elapsed_ms = (time.perf_counter() - start) * 1000
            pipeline_times.append(elapsed_ms)

        return {
            "set_get_delete": self._compute_stats(set_get_times),
            "pipeline_batch_10": self._compute_stats(pipeline_times),
        }

    @staticmethod
    def _compute_stats(times: list[float]) -> dict[str, Any]:
        if not times:
            return {"p50_ms": -1, "p99_ms": -1, "avg_ms": -1, "ops": 0}
        sorted_times = sorted(times)
        p99_idx = max(0, int(len(sorted_times) * 0.99) - 1)
        return {
            "p50_ms": round(statistics.median(times), 3),
            "p99_ms": round(sorted_times[p99_idx], 3),
            "avg_ms": round(statistics.mean(times), 3),
            "min_ms": round(min(times), 3),
            "max_ms": round(max(times), 3),
            "ops": len(times),
        }
