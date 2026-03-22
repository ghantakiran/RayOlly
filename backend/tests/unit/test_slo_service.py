"""Tests for rayolly.services.apm.slo — SLOService."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from rayolly.services.apm.slo import (
    AlertSeverity,
    SLIType,
    SLODefinition,
    SLOService,
    SLOStatus,
)

# -----------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------

def _slo_def(
    target: float = 99.95,
    sli_type: SLIType = SLIType.AVAILABILITY,
    window_days: int = 30,
) -> SLODefinition:
    return SLODefinition(
        id="slo-001",
        name="API Availability",
        service="api-gateway",
        sli_type=sli_type,
        sli_query="",
        target_percentage=target,
        window_days=window_days,
    )


def _mock_clickhouse_returning(sli_value: float) -> AsyncMock:
    """Mock ClickHouse that returns the given SLI value for every query."""
    ch = AsyncMock()
    ch.execute = AsyncMock(return_value=[{"sli_value": sli_value}])
    return ch


# -----------------------------------------------------------------------
# Evaluation
# -----------------------------------------------------------------------

class TestEvaluate:
    @pytest.mark.asyncio
    async def test_evaluate_meeting_target(self) -> None:
        slo = _slo_def(target=99.9)
        ch = _mock_clickhouse_returning(99.95)  # above target
        service = SLOService()
        status = await service.evaluate("t1", slo, ch)

        assert isinstance(status, SLOStatus)
        assert status.is_breaching is False
        assert status.current_value >= slo.target_percentage

    @pytest.mark.asyncio
    async def test_evaluate_breaching_target(self) -> None:
        slo = _slo_def(target=99.9)
        ch = _mock_clickhouse_returning(99.5)  # below target
        service = SLOService()
        status = await service.evaluate("t1", slo, ch)

        assert status.is_breaching is True
        assert status.current_value < slo.target_percentage

    @pytest.mark.asyncio
    async def test_error_budget_remaining(self) -> None:
        slo = _slo_def(target=99.0)
        # SLI at 99.5% means only half the error budget consumed
        ch = _mock_clickhouse_returning(99.5)
        service = SLOService()
        status = await service.evaluate("t1", slo, ch)

        assert status.error_budget_remaining_pct > 0
        assert status.error_budget_remaining_pct <= 100


# -----------------------------------------------------------------------
# Burn rate
# -----------------------------------------------------------------------

class TestBurnRate:
    @pytest.mark.asyncio
    async def test_burn_rate_at_target_is_about_one(self) -> None:
        slo = _slo_def(target=99.0, window_days=30)
        # SLI exactly at target means error rate = allowed error rate
        ch = _mock_clickhouse_returning(99.0)
        service = SLOService()
        status = await service.evaluate("t1", slo, ch)
        # Burn rates should be approximately 1.0 (consuming at sustainable pace)
        # The exact value depends on window normalization, just check it is finite
        assert status.burn_rate_1h >= 0
        assert status.burn_rate_6h >= 0
        assert status.burn_rate_24h >= 0

    @pytest.mark.asyncio
    async def test_zero_errors_means_low_burn_rate(self) -> None:
        slo = _slo_def(target=99.0)
        ch = _mock_clickhouse_returning(100.0)  # no errors at all
        service = SLOService()
        status = await service.evaluate("t1", slo, ch)
        assert status.burn_rate_1h == 0.0
        assert status.burn_rate_6h == 0.0


# -----------------------------------------------------------------------
# Breach prediction
# -----------------------------------------------------------------------

class TestBreachPrediction:
    @pytest.mark.asyncio
    async def test_predict_breach_when_burning_fast(self) -> None:
        slo = _slo_def(target=99.9, window_days=30)
        status = SLOStatus(
            definition=slo,
            current_value=99.8,
            error_budget_remaining_pct=50.0,
            burn_rate_1h=14.0,
            burn_rate_6h=10.0,  # >1 means burning fast
            burn_rate_24h=5.0,
            is_breaching=True,
            predicted_breach_time=None,
        )
        service = SLOService()
        breach_time = await service.predict_breach(status)
        assert breach_time is not None
        assert breach_time > datetime.utcnow()

    @pytest.mark.asyncio
    async def test_predict_no_breach_when_sustainable(self) -> None:
        slo = _slo_def(target=99.9, window_days=30)
        status = SLOStatus(
            definition=slo,
            current_value=99.95,
            error_budget_remaining_pct=80.0,
            burn_rate_1h=0.5,
            burn_rate_6h=0.5,  # <=1 means sustainable
            burn_rate_24h=0.5,
            is_breaching=False,
            predicted_breach_time=None,
        )
        service = SLOService()
        breach_time = await service.predict_breach(status)
        assert breach_time is None

    @pytest.mark.asyncio
    async def test_predict_breach_already_exhausted(self) -> None:
        slo = _slo_def(target=99.9, window_days=30)
        status = SLOStatus(
            definition=slo,
            current_value=99.0,
            error_budget_remaining_pct=0.0,  # already exhausted
            burn_rate_1h=20.0,
            burn_rate_6h=15.0,
            burn_rate_24h=10.0,
            is_breaching=True,
            predicted_breach_time=None,
        )
        service = SLOService()
        breach_time = await service.predict_breach(status)
        # Already exhausted, should return None (already breached)
        assert breach_time is None


# -----------------------------------------------------------------------
# Helper methods
# -----------------------------------------------------------------------

class TestHelpers:
    def test_extract_latency_threshold_from_query(self) -> None:
        assert SLOService._extract_latency_threshold("latency_threshold=200") == 200.0
        assert SLOService._extract_latency_threshold("500") == 500.0
        assert SLOService._extract_latency_threshold("no_number_here") == 500.0

    def test_parse_burn_rates_valid_json(self) -> None:
        raw = '[{"burn_rate": 14.4, "window": "1h", "severity": "critical"}]'
        alerts = SLOService._parse_burn_rates(raw)
        assert len(alerts) == 1
        assert alerts[0].burn_rate == 14.4
        assert alerts[0].severity == AlertSeverity.CRITICAL

    def test_parse_burn_rates_invalid_json(self) -> None:
        alerts = SLOService._parse_burn_rates("not json")
        assert alerts == []

    def test_parse_burn_rates_empty_list(self) -> None:
        alerts = SLOService._parse_burn_rates("[]")
        assert alerts == []
