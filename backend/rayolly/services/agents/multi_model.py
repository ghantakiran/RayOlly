"""Multi-model routing — intelligent model selection based on task complexity."""
from __future__ import annotations

from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ModelConfig:
    """Configuration for a single LLM model."""

    name: str
    model_id: str
    cost_per_1m_input: float
    cost_per_1m_output: float
    max_tokens: int
    suitable_for: list[str] = field(default_factory=list)


MODELS: dict[str, ModelConfig] = {
    "haiku": ModelConfig(
        name="Haiku",
        model_id="claude-haiku-4-5-20251001",
        cost_per_1m_input=0.80,
        cost_per_1m_output=4.00,
        max_tokens=8192,
        suitable_for=["simple_query", "summarization", "classification"],
    ),
    "sonnet": ModelConfig(
        name="Sonnet",
        model_id="claude-sonnet-4-20250514",
        cost_per_1m_input=3.00,
        cost_per_1m_output=15.00,
        max_tokens=8192,
        suitable_for=["complex_query", "investigation", "analysis"],
    ),
    "opus": ModelConfig(
        name="Opus",
        model_id="claude-opus-4-20250514",
        cost_per_1m_input=15.00,
        cost_per_1m_output=75.00,
        max_tokens=8192,
        suitable_for=["complex_rca", "deep_analysis", "multi_step_reasoning"],
    ),
}

# Keywords that indicate a simple, direct question
_SIMPLE_KEYWORDS = frozenset(
    ["list", "count", "show", "what is", "how many", "status", "uptime"]
)


class ModelRouter:
    """Routes agent tasks to the most cost-effective model."""

    def __init__(self, default_model: str = "sonnet") -> None:
        if default_model not in MODELS:
            raise ValueError(
                f"Unknown default model '{default_model}'. "
                f"Choose from: {', '.join(MODELS)}"
            )
        self.default = default_model

    def select_model(
        self,
        agent_type: str,
        input_data: dict,
        budget_remaining: float = float("inf"),
    ) -> ModelConfig:
        """Select the best model based on task complexity and budget."""
        complexity = self._assess_complexity(agent_type, input_data)

        if budget_remaining < 0.01:
            logger.warning("model_router.budget_exhausted", using="haiku")
            return MODELS["haiku"]

        if complexity == "simple":
            model = MODELS["haiku"]
        elif complexity == "complex":
            model = MODELS["opus"] if budget_remaining > 0.10 else MODELS["sonnet"]
        else:
            model = MODELS["sonnet"]

        logger.debug(
            "model_router.selected",
            model=model.name,
            complexity=complexity,
            agent=agent_type,
        )
        return model

    def _assess_complexity(self, agent_type: str, input_data: dict) -> str:
        """Assess task complexity: simple, medium, complex."""
        # Simple: direct questions, status checks
        if agent_type == "QUERY":
            question = input_data.get("question", "")
            if len(question) < 50 and any(
                w in question.lower() for w in _SIMPLE_KEYWORDS
            ):
                return "simple"
            return "medium"

        # Complex: RCA, multi-service investigation
        if agent_type == "RCA":
            return "complex"

        # Medium: incidents, anomalies
        if agent_type in ("INCIDENT", "ANOMALY"):
            return "medium"

        return "medium"

    @staticmethod
    def estimate_cost(model: ModelConfig, estimated_tokens: int = 5000) -> float:
        """Estimate the cost of a single model invocation.

        Assumes a 70/30 split between input and output tokens, which is
        a reasonable average for agent workloads.
        """
        input_tokens = estimated_tokens * 0.7
        output_tokens = estimated_tokens * 0.3
        input_cost = (input_tokens / 1_000_000) * model.cost_per_1m_input
        output_cost = (output_tokens / 1_000_000) * model.cost_per_1m_output
        return round(input_cost + output_cost, 6)

    @staticmethod
    def list_models() -> list[dict]:
        """Return available models with their metadata."""
        return [
            {
                "key": key,
                "name": m.name,
                "model_id": m.model_id,
                "cost_per_1m_input": m.cost_per_1m_input,
                "cost_per_1m_output": m.cost_per_1m_output,
                "max_tokens": m.max_tokens,
                "suitable_for": m.suitable_for,
            }
            for key, m in MODELS.items()
        ]
