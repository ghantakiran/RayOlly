"""Agent Accuracy & Hallucination Detection.

Validates that agent outputs match the actual data returned by tools,
detects hallucinations (fabricated metrics, wrong values, invented errors),
and tracks accuracy trends over time.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class AgentClaim:
    """A verifiable claim extracted from an agent's output."""

    claim_type: str  # "metric_value", "error_count", "service_status", "root_cause"
    claim_text: str  # What the agent said
    source_tool: str  # Which tool provided the data
    source_data: dict[str, Any] = field(default_factory=dict)  # Actual tool output


@dataclass
class ClaimValidation:
    """Result of validating a single claim."""

    claim: AgentClaim
    is_valid: bool
    actual_value: Any = None
    deviation_pct: float = 0.0  # How far off was the agent
    explanation: str = ""


@dataclass
class Hallucination:
    """A detected case where agent output doesn't match tool results."""

    execution_id: str
    step_number: int
    claim_text: str
    expected_data: dict[str, Any] = field(default_factory=dict)
    actual_data: dict[str, Any] = field(default_factory=dict)
    severity: str = "minor"  # "minor" (rounding), "moderate" (wrong value), "critical" (fabricated)


@dataclass
class AccuracyReport:
    """Post-execution accuracy validation report."""

    execution_id: str
    total_claims: int = 0
    valid_claims: int = 0
    invalid_claims: int = 0
    hallucinations: list[Hallucination] = field(default_factory=list)
    accuracy_pct: float = 0.0


@dataclass
class AccuracyPoint:
    """A single data-point in an accuracy trend."""

    date: str
    accuracy_pct: float
    total_executions: int
    hallucination_count: int


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class AgentAccuracyTracker:
    """Track and validate agent output accuracy."""

    def __init__(self, clickhouse_client: Any) -> None:
        self.clickhouse = clickhouse_client

    # ------------------------------------------------------------------
    # Claim-level validation
    # ------------------------------------------------------------------

    async def validate_claim(
        self,
        claim: AgentClaim,
        tenant_id: str,
    ) -> ClaimValidation:
        """Validate a specific claim made by an agent against actual data.

        Example: Agent says "error rate is 5.2%" -> query actual error rate -> compare.
        """
        if claim.claim_type == "metric_value":
            return await self._validate_metric_claim(claim, tenant_id)
        elif claim.claim_type == "error_count":
            return await self._validate_error_count_claim(claim, tenant_id)
        elif claim.claim_type == "service_status":
            return await self._validate_service_status_claim(claim, tenant_id)
        else:
            # For root_cause and other qualitative claims, compare against
            # the source tool data directly
            return self._validate_against_source(claim)

    async def _validate_metric_claim(
        self,
        claim: AgentClaim,
        tenant_id: str,
    ) -> ClaimValidation:
        """Validate a numeric metric claim by re-querying the data source."""
        # Extract the numeric value from the claim text
        numbers = re.findall(r"[\d]+\.?\d*", claim.claim_text)
        if not numbers:
            return ClaimValidation(
                claim=claim,
                is_valid=True,  # Can't validate without a number
                explanation="No numeric value found in claim text to validate.",
            )

        claimed_value = float(numbers[0])
        source_value = claim.source_data.get("value")

        if source_value is None:
            return ClaimValidation(
                claim=claim,
                is_valid=True,
                explanation="No source value available for comparison.",
            )

        source_value = float(source_value)
        if source_value == 0:
            deviation = abs(claimed_value) * 100
        else:
            deviation = abs(claimed_value - source_value) / abs(source_value) * 100

        # Allow 5% tolerance for rounding
        is_valid = deviation <= 5.0

        return ClaimValidation(
            claim=claim,
            is_valid=is_valid,
            actual_value=source_value,
            deviation_pct=round(deviation, 2),
            explanation=(
                f"Claimed {claimed_value}, actual {source_value} "
                f"(deviation: {deviation:.1f}%)"
                if not is_valid
                else f"Claimed {claimed_value} matches source {source_value} within tolerance."
            ),
        )

    async def _validate_error_count_claim(
        self,
        claim: AgentClaim,
        tenant_id: str,
    ) -> ClaimValidation:
        """Validate an error count claim."""
        numbers = re.findall(r"[\d,]+", claim.claim_text)
        if not numbers:
            return ClaimValidation(
                claim=claim,
                is_valid=True,
                explanation="No numeric value found in error count claim.",
            )

        claimed_count = int(numbers[0].replace(",", ""))
        source_count = claim.source_data.get("count", claim.source_data.get("total"))

        if source_count is None:
            return ClaimValidation(
                claim=claim,
                is_valid=True,
                explanation="No source count available for comparison.",
            )

        source_count = int(source_count)
        if source_count == 0:
            deviation = float(claimed_count) * 100
        else:
            deviation = abs(claimed_count - source_count) / source_count * 100

        is_valid = deviation <= 5.0

        return ClaimValidation(
            claim=claim,
            is_valid=is_valid,
            actual_value=source_count,
            deviation_pct=round(deviation, 2),
            explanation=(
                f"Claimed {claimed_count} errors, actual {source_count} "
                f"(deviation: {deviation:.1f}%)"
            ),
        )

    async def _validate_service_status_claim(
        self,
        claim: AgentClaim,
        tenant_id: str,
    ) -> ClaimValidation:
        """Validate a service status claim (healthy/degraded/down)."""
        source_status = claim.source_data.get("status", "").lower()
        claim_lower = claim.claim_text.lower()

        # Check if the claimed status matches the source
        status_keywords = {
            "healthy": ["healthy", "up", "running", "ok", "green"],
            "degraded": ["degraded", "warning", "yellow", "slow"],
            "down": ["down", "error", "red", "failing", "unavailable"],
        }

        claimed_status = "unknown"
        for status, keywords in status_keywords.items():
            if any(kw in claim_lower for kw in keywords):
                claimed_status = status
                break

        source_normalized = "unknown"
        for status, keywords in status_keywords.items():
            if any(kw in source_status for kw in keywords):
                source_normalized = status
                break

        is_valid = claimed_status == source_normalized or claimed_status == "unknown"

        return ClaimValidation(
            claim=claim,
            is_valid=is_valid,
            actual_value=source_status,
            deviation_pct=0.0 if is_valid else 100.0,
            explanation=(
                f"Claimed status '{claimed_status}' "
                f"{'matches' if is_valid else 'does not match'} "
                f"actual status '{source_status}'"
            ),
        )

    def _validate_against_source(self, claim: AgentClaim) -> ClaimValidation:
        """Generic validation: check if claim text references data from source."""
        if not claim.source_data:
            return ClaimValidation(
                claim=claim,
                is_valid=True,
                explanation="No source data to validate against.",
            )

        # Check if key values from source_data appear in the claim text
        mismatches: list[str] = []
        for key, value in claim.source_data.items():
            if isinstance(value, (int, float)):
                str_val = str(value)
                if str_val not in claim.claim_text and f"{value:.1f}" not in claim.claim_text:
                    mismatches.append(f"{key}={value}")

        is_valid = len(mismatches) == 0

        return ClaimValidation(
            claim=claim,
            is_valid=is_valid,
            actual_value=claim.source_data,
            deviation_pct=0.0 if is_valid else 100.0,
            explanation=(
                "All source values found in claim."
                if is_valid
                else f"Values not found in claim: {', '.join(mismatches)}"
            ),
        )

    # ------------------------------------------------------------------
    # Execution-level validation
    # ------------------------------------------------------------------

    async def validate_execution(
        self,
        execution_id: str,
        tenant_id: str,
    ) -> AccuracyReport:
        """Post-execution validation: check all tool results the agent cited.

        Loads the execution steps, extracts claims from response steps, and
        compares them against preceding tool_result steps.
        """
        # Load steps
        step_rows = await self.clickhouse.execute(
            """
            SELECT
                step_number, step_type, tool_name, content_preview, tokens_used
            FROM agents.agent_steps
            WHERE execution_id = %(execution_id)s
            ORDER BY step_number ASC
            """,
            {"execution_id": execution_id},
        )

        if not step_rows:
            return AccuracyReport(execution_id=execution_id)

        # Build a map of tool results
        tool_results: dict[int, dict[str, Any]] = {}
        for row in step_rows:
            step_num, step_type, tool_name, content, _ = row
            if step_type == "tool_result":
                tool_results[step_num] = {
                    "tool_name": tool_name or "",
                    "content": content or "",
                }

        # Extract claims from response steps
        claims: list[AgentClaim] = []
        hallucinations: list[Hallucination] = []
        response_steps = [r for r in step_rows if r[1] == "response"]

        for resp in response_steps:
            step_num, _, _, content, _ = resp
            if not content:
                continue

            # Extract numeric claims from the response text
            extracted = self._extract_claims_from_text(content, tool_results)
            claims.extend(extracted)

        # Validate each claim
        valid_count = 0
        invalid_count = 0

        for claim in claims:
            validation = await self.validate_claim(claim, tenant_id)
            if validation.is_valid:
                valid_count += 1
            else:
                invalid_count += 1
                severity = "minor"
                if validation.deviation_pct > 50:
                    severity = "critical"
                elif validation.deviation_pct > 10:
                    severity = "moderate"

                hallucinations.append(
                    Hallucination(
                        execution_id=execution_id,
                        step_number=0,
                        claim_text=claim.claim_text,
                        expected_data=claim.source_data,
                        actual_data={"deviation_pct": validation.deviation_pct},
                        severity=severity,
                    )
                )

        total = valid_count + invalid_count
        accuracy = (valid_count / total * 100) if total > 0 else 100.0

        report = AccuracyReport(
            execution_id=execution_id,
            total_claims=total,
            valid_claims=valid_count,
            invalid_claims=invalid_count,
            hallucinations=hallucinations,
            accuracy_pct=round(accuracy, 2),
        )

        # Persist the report
        await self._persist_accuracy_report(report, tenant_id)

        return report

    def _extract_claims_from_text(
        self,
        text: str,
        tool_results: dict[int, dict[str, Any]],
    ) -> list[AgentClaim]:
        """Extract verifiable claims from agent response text."""
        claims: list[AgentClaim] = []

        # Pattern: "X is Y%" or "X: Y%"
        pct_patterns = re.findall(
            r"([\w\s]+(?:rate|ratio|percentage|pct)[\s:]+[\d.]+%)",
            text,
            re.IGNORECASE,
        )
        for match in pct_patterns:
            claims.append(
                AgentClaim(
                    claim_type="metric_value",
                    claim_text=match.strip(),
                    source_tool="inferred",
                    source_data={},
                )
            )

        # Pattern: "N errors" or "N failures"
        count_patterns = re.findall(
            r"([\d,]+ (?:errors?|failures?|incidents?|alerts?|exceptions?))",
            text,
            re.IGNORECASE,
        )
        for match in count_patterns:
            claims.append(
                AgentClaim(
                    claim_type="error_count",
                    claim_text=match.strip(),
                    source_tool="inferred",
                    source_data={},
                )
            )

        return claims

    async def _persist_accuracy_report(
        self,
        report: AccuracyReport,
        tenant_id: str,
    ) -> None:
        """Store accuracy report in ClickHouse for trend analysis."""
        await self.clickhouse.execute(
            """
            INSERT INTO agents.agent_accuracy_reports (
                execution_id, tenant_id, total_claims, valid_claims,
                invalid_claims, accuracy_pct, hallucination_count
            ) VALUES
            """,
            [
                {
                    "execution_id": report.execution_id,
                    "tenant_id": tenant_id,
                    "total_claims": report.total_claims,
                    "valid_claims": report.valid_claims,
                    "invalid_claims": report.invalid_claims,
                    "accuracy_pct": report.accuracy_pct,
                    "hallucination_count": len(report.hallucinations),
                },
            ],
        )

    # ------------------------------------------------------------------
    # Trends
    # ------------------------------------------------------------------

    async def get_accuracy_trend(
        self,
        tenant_id: str,
        agent_type: str | None = None,
        days: int = 30,
    ) -> list[AccuracyPoint]:
        """Historical accuracy trend for an agent type (or all agents)."""
        agent_filter = ""
        params: dict[str, Any] = {"tenant_id": tenant_id, "days": days}

        if agent_type:
            agent_filter = "AND e.agent_type = %(agent_type)s"
            params["agent_type"] = agent_type

        rows = await self.clickhouse.execute(
            f"""
            SELECT
                toDate(e.started_at) AS dt,
                avg(a.accuracy_pct) AS avg_accuracy,
                count() AS total_executions,
                sum(a.hallucination_count) AS hallucinations
            FROM agents.agent_accuracy_reports AS a
            INNER JOIN agents.agent_executions AS e
                ON a.execution_id = e.execution_id
            WHERE a.tenant_id = %(tenant_id)s
              {agent_filter}
              AND e.started_at >= now() - INTERVAL %(days)s DAY
            GROUP BY dt
            ORDER BY dt ASC
            """,
            params,
        )

        return [
            AccuracyPoint(
                date=str(r[0]),
                accuracy_pct=round(float(r[1]), 2),
                total_executions=int(r[2]),
                hallucination_count=int(r[3]),
            )
            for r in (rows or [])
        ]

    # ------------------------------------------------------------------
    # Hallucination detection
    # ------------------------------------------------------------------

    async def detect_hallucinations(
        self,
        execution_id: str,
        tenant_id: str,
    ) -> list[Hallucination]:
        """Find cases where agent output doesn't match tool results.

        Compares each response step's content against the tool results
        that preceded it, looking for numeric mismatches.
        """
        report = await self.validate_execution(execution_id, tenant_id)
        return report.hallucinations

    async def get_recent_hallucinations(
        self,
        tenant_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get recently detected hallucinations across all executions."""
        rows = await self.clickhouse.execute(
            """
            SELECT
                a.execution_id,
                e.agent_type,
                a.accuracy_pct,
                a.hallucination_count,
                e.started_at,
                e.model
            FROM agents.agent_accuracy_reports AS a
            INNER JOIN agents.agent_executions AS e
                ON a.execution_id = e.execution_id
            WHERE a.tenant_id = %(tenant_id)s
              AND a.hallucination_count > 0
            ORDER BY e.started_at DESC
            LIMIT %(limit)s
            """,
            {"tenant_id": tenant_id, "limit": limit},
        )

        return [
            {
                "execution_id": r[0],
                "agent_type": r[1],
                "accuracy_pct": float(r[2]),
                "hallucination_count": int(r[3]),
                "timestamp": r[4].isoformat() if hasattr(r[4], "isoformat") else str(r[4]),
                "model": r[5],
            }
            for r in (rows or [])
        ]
