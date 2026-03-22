"""Agent A/B Testing Framework -- compare agent configurations with statistical rigour.

Enables controlled experiments on agent system prompts, models, tool sets,
and iteration limits.  Uses consistent hashing for deterministic variant
assignment and computes statistical significance via two-proportion z-tests.
"""

from __future__ import annotations

import hashlib
import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ABVariant:
    """Configuration for one side of an A/B test."""

    name: str  # "A" (control) or "B" (treatment)
    system_prompt: str | None = None
    model: str | None = None
    tools: list[str] | None = None
    max_iterations: int | None = None
    description: str = ""


@dataclass
class ABExperiment:
    """A single A/B test experiment."""

    id: str
    tenant_id: str
    agent_type: str
    name: str
    description: str
    variant_a: ABVariant
    variant_b: ABVariant
    traffic_split: float = 0.5  # 0.5 = 50/50
    success_metric: str = "accuracy"  # "accuracy", "speed", "cost", "satisfaction"
    min_sample_size: int = 100
    status: str = "running"  # "running", "concluded", "paused"
    started_at: str = ""
    concluded_at: str | None = None
    winner: str | None = None


@dataclass
class ABMetrics:
    """Outcome metrics for a single execution in an experiment."""

    success: bool = True
    duration_ms: float = 0.0
    tokens_used: int = 0
    cost_usd: float = 0.0
    user_satisfaction: int | None = None  # 1 (thumbs down) or 5 (thumbs up)
    accuracy_score: float | None = None  # 0.0-1.0 if validated


@dataclass
class AggregatedMetrics:
    """Aggregated metrics for one variant in an experiment."""

    success_rate: float = 0.0
    avg_duration_ms: float = 0.0
    avg_cost_usd: float = 0.0
    avg_satisfaction: float = 0.0
    avg_accuracy: float = 0.0
    p95_duration_ms: float = 0.0


@dataclass
class ABResults:
    """Full experiment results with statistical analysis."""

    experiment: ABExperiment
    variant_a_metrics: AggregatedMetrics = field(default_factory=AggregatedMetrics)
    variant_b_metrics: AggregatedMetrics = field(default_factory=AggregatedMetrics)
    winner: str | None = None
    confidence: float = 0.0  # 1 - p_value
    sample_size_a: int = 0
    sample_size_b: int = 0
    is_significant: bool = False  # p < 0.05


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class AgentABTestService:
    """A/B test different agent configurations (prompts, models, tools)."""

    def __init__(self, clickhouse_client: Any, metadata_session: Any = None) -> None:
        self.clickhouse = clickhouse_client
        self.metadata = metadata_session

    # ------------------------------------------------------------------
    # Experiment lifecycle
    # ------------------------------------------------------------------

    async def create_experiment(
        self,
        tenant_id: str,
        experiment: ABExperiment,
    ) -> ABExperiment:
        """Create a new A/B test experiment."""
        if not experiment.id:
            experiment.id = uuid.uuid4().hex[:12]
        experiment.tenant_id = tenant_id
        experiment.status = "running"
        experiment.started_at = datetime.now(UTC).isoformat()

        await self.clickhouse.execute(
            """
            INSERT INTO agents.ab_experiments (
                experiment_id, tenant_id, agent_type, name, description,
                variant_a_desc, variant_b_desc,
                variant_a_model, variant_b_model,
                traffic_split, success_metric, min_sample_size,
                status, started_at
            ) VALUES
            """,
            [
                {
                    "experiment_id": experiment.id,
                    "tenant_id": tenant_id,
                    "agent_type": experiment.agent_type,
                    "name": experiment.name,
                    "description": experiment.description,
                    "variant_a_desc": experiment.variant_a.description,
                    "variant_b_desc": experiment.variant_b.description,
                    "variant_a_model": experiment.variant_a.model or "",
                    "variant_b_model": experiment.variant_b.model or "",
                    "traffic_split": experiment.traffic_split,
                    "success_metric": experiment.success_metric,
                    "min_sample_size": experiment.min_sample_size,
                    "status": experiment.status,
                    "started_at": experiment.started_at,
                },
            ],
        )

        logger.info(
            "Created A/B experiment %s: %s (%s)",
            experiment.id,
            experiment.name,
            experiment.agent_type,
        )

        return experiment

    async def get_variant(
        self,
        tenant_id: str,
        experiment_id: str,
        execution_id: str,
    ) -> str:
        """Assign a variant (A or B) using consistent hashing.

        The same execution_id always maps to the same variant, ensuring
        deterministic assignment even across retries.
        """
        # Consistent hash: SHA-256 of experiment_id + execution_id
        hash_input = f"{experiment_id}:{execution_id}"
        hash_val = int(hashlib.sha256(hash_input.encode()).hexdigest(), 16)

        # Load traffic split from experiment
        rows = await self.clickhouse.execute(
            """
            SELECT traffic_split
            FROM agents.ab_experiments
            WHERE experiment_id = %(experiment_id)s
              AND tenant_id = %(tenant_id)s
            LIMIT 1
            """,
            {"experiment_id": experiment_id, "tenant_id": tenant_id},
        )

        split = float(rows[0][0]) if rows else 0.5

        # Map hash to [0, 1) range
        normalized = (hash_val % 10000) / 10000.0
        return "A" if normalized < split else "B"

    async def record_outcome(
        self,
        experiment_id: str,
        execution_id: str,
        variant: str,
        metrics: ABMetrics,
    ) -> None:
        """Record the outcome of an execution for the experiment."""
        await self.clickhouse.execute(
            """
            INSERT INTO agents.ab_outcomes (
                experiment_id, execution_id, variant,
                success, duration_ms, tokens_used, cost_usd,
                user_satisfaction, accuracy_score
            ) VALUES
            """,
            [
                {
                    "experiment_id": experiment_id,
                    "execution_id": execution_id,
                    "variant": variant,
                    "success": 1 if metrics.success else 0,
                    "duration_ms": metrics.duration_ms,
                    "tokens_used": metrics.tokens_used,
                    "cost_usd": metrics.cost_usd,
                    "user_satisfaction": metrics.user_satisfaction or 0,
                    "accuracy_score": metrics.accuracy_score or 0.0,
                },
            ],
        )

    # ------------------------------------------------------------------
    # Results & statistical analysis
    # ------------------------------------------------------------------

    async def get_results(self, experiment_id: str, tenant_id: str = "") -> ABResults:
        """Get experiment results with statistical significance."""
        # Load experiment metadata
        exp_rows = await self.clickhouse.execute(
            """
            SELECT
                agent_type, name, description,
                variant_a_desc, variant_b_desc,
                variant_a_model, variant_b_model,
                traffic_split, success_metric, min_sample_size,
                status, started_at
            FROM agents.ab_experiments
            WHERE experiment_id = %(experiment_id)s
            LIMIT 1
            """,
            {"experiment_id": experiment_id},
        )

        if not exp_rows:
            # Return empty results
            return ABResults(
                experiment=ABExperiment(
                    id=experiment_id,
                    tenant_id=tenant_id,
                    agent_type="unknown",
                    name="Not found",
                    description="",
                    variant_a=ABVariant(name="A"),
                    variant_b=ABVariant(name="B"),
                ),
            )

        r = exp_rows[0]
        experiment = ABExperiment(
            id=experiment_id,
            tenant_id=tenant_id,
            agent_type=r[0],
            name=r[1],
            description=r[2],
            variant_a=ABVariant(name="A", description=r[3], model=r[5] or None),
            variant_b=ABVariant(name="B", description=r[4], model=r[6] or None),
            traffic_split=float(r[7]),
            success_metric=r[8],
            min_sample_size=int(r[9]),
            status=r[10],
            started_at=str(r[11]),
        )

        # Aggregate metrics per variant
        metrics_a = await self._aggregate_variant(experiment_id, "A")
        metrics_b = await self._aggregate_variant(experiment_id, "B")
        count_a, count_b = metrics_a[1], metrics_b[1]

        agg_a = metrics_a[0]
        agg_b = metrics_b[0]

        # Statistical significance via z-test on the success metric
        winner, confidence, is_significant = self._compute_significance(
            experiment.success_metric, agg_a, count_a, agg_b, count_b,
        )

        return ABResults(
            experiment=experiment,
            variant_a_metrics=agg_a,
            variant_b_metrics=agg_b,
            winner=winner,
            confidence=round(confidence, 4),
            sample_size_a=count_a,
            sample_size_b=count_b,
            is_significant=is_significant,
        )

    async def _aggregate_variant(
        self,
        experiment_id: str,
        variant: str,
    ) -> tuple[AggregatedMetrics, int]:
        """Aggregate metrics for a single variant."""
        rows = await self.clickhouse.execute(
            """
            SELECT
                count() AS n,
                avg(success) AS success_rate,
                avg(duration_ms) AS avg_duration,
                quantile(0.95)(duration_ms) AS p95_duration,
                avg(cost_usd) AS avg_cost,
                avgIf(user_satisfaction, user_satisfaction > 0) AS avg_sat,
                avgIf(accuracy_score, accuracy_score > 0) AS avg_acc
            FROM agents.ab_outcomes
            WHERE experiment_id = %(experiment_id)s
              AND variant = %(variant)s
            """,
            {"experiment_id": experiment_id, "variant": variant},
        )

        if not rows or not rows[0][0]:
            return AggregatedMetrics(), 0

        r = rows[0]
        n = int(r[0])

        return AggregatedMetrics(
            success_rate=round(float(r[1] or 0) * 100, 2),
            avg_duration_ms=round(float(r[2] or 0), 2),
            p95_duration_ms=round(float(r[3] or 0), 2),
            avg_cost_usd=round(float(r[4] or 0), 6),
            avg_satisfaction=round(float(r[5] or 0), 2),
            avg_accuracy=round(float(r[6] or 0), 4),
        ), n

    def _compute_significance(
        self,
        metric: str,
        agg_a: AggregatedMetrics,
        n_a: int,
        agg_b: AggregatedMetrics,
        n_b: int,
    ) -> tuple[str | None, float, bool]:
        """Two-proportion z-test (or two-sample t-test proxy) for significance."""
        if n_a < 5 or n_b < 5:
            return None, 0.0, False

        # Choose metric to compare
        if metric == "accuracy":
            val_a, val_b = agg_a.avg_accuracy, agg_b.avg_accuracy
        elif metric == "speed":
            # Lower is better for speed
            val_a, val_b = -agg_a.avg_duration_ms, -agg_b.avg_duration_ms
        elif metric == "cost":
            # Lower is better for cost
            val_a, val_b = -agg_a.avg_cost_usd, -agg_b.avg_cost_usd
        elif metric == "satisfaction":
            val_a, val_b = agg_a.avg_satisfaction, agg_b.avg_satisfaction
        else:
            val_a, val_b = agg_a.success_rate / 100, agg_b.success_rate / 100

        # Z-test for two proportions (simplified)
        p_a = max(0.001, min(0.999, agg_a.success_rate / 100))
        p_b = max(0.001, min(0.999, agg_b.success_rate / 100))
        p_pool = (p_a * n_a + p_b * n_b) / (n_a + n_b)
        se = math.sqrt(p_pool * (1 - p_pool) * (1 / n_a + 1 / n_b))

        if se == 0:
            return None, 0.0, False

        z = abs(p_a - p_b) / se

        # Approximate p-value from z-score (standard normal)
        # Using the complementary error function approximation
        p_value = math.erfc(z / math.sqrt(2))
        confidence = 1.0 - p_value
        is_significant = p_value < 0.05

        # Determine winner (higher val is better, we already negated for lower-is-better)
        if is_significant:
            winner = "A" if val_a > val_b else "B"
        else:
            winner = None

        return winner, confidence, is_significant

    # ------------------------------------------------------------------
    # Experiment management
    # ------------------------------------------------------------------

    async def conclude_experiment(
        self,
        experiment_id: str,
        tenant_id: str = "",
    ) -> str:
        """Determine winner based on results. Returns winning variant."""
        results = await self.get_results(experiment_id, tenant_id)

        winner = results.winner or "inconclusive"

        await self.clickhouse.execute(
            """
            ALTER TABLE agents.ab_experiments
            UPDATE
                status = 'concluded',
                winner = %(winner)s
            WHERE experiment_id = %(experiment_id)s
            """,
            {"experiment_id": experiment_id, "winner": winner},
        )

        logger.info("Concluded experiment %s. Winner: %s", experiment_id, winner)
        return winner

    async def list_experiments(
        self,
        tenant_id: str,
        status_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """List all experiments for a tenant."""
        conditions = ["tenant_id = %(tenant_id)s"]
        params: dict[str, Any] = {"tenant_id": tenant_id}

        if status_filter:
            conditions.append("status = %(status)s")
            params["status"] = status_filter

        where = " AND ".join(conditions)

        rows = await self.clickhouse.execute(
            f"""
            SELECT
                experiment_id, agent_type, name, description,
                variant_a_desc, variant_b_desc,
                variant_a_model, variant_b_model,
                traffic_split, success_metric, min_sample_size,
                status, started_at, winner
            FROM agents.ab_experiments
            WHERE {where}
            ORDER BY started_at DESC
            """,
            params,
        )

        return [
            {
                "id": r[0],
                "agent_type": r[1],
                "name": r[2],
                "description": r[3],
                "variant_a": {"description": r[4], "model": r[6]},
                "variant_b": {"description": r[5], "model": r[7]},
                "traffic_split": float(r[8]),
                "success_metric": r[9],
                "min_sample_size": int(r[10]),
                "status": r[11],
                "started_at": str(r[12]),
                "winner": r[13] if len(r) > 13 else None,
            }
            for r in (rows or [])
        ]
