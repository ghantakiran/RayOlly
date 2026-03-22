"""Tests for rayolly.services.ai.forecaster — Forecaster."""

from __future__ import annotations

import time

import pytest

from rayolly.services.ai.forecaster import Forecaster, ForecastResult


@pytest.fixture
def forecaster() -> Forecaster:
    return Forecaster()


def _make_timestamps(n: int, step: float = 3600.0) -> list[float]:
    """Generate *n* evenly-spaced epoch timestamps (1-hour step)."""
    base = time.time() - n * step
    return [base + i * step for i in range(n)]


def _make_uptrend(n: int = 48) -> tuple[list[float], list[float]]:
    ts = _make_timestamps(n)
    vals = [10.0 + 2.0 * i for i in range(n)]
    return ts, vals


def _make_downtrend(n: int = 48) -> tuple[list[float], list[float]]:
    ts = _make_timestamps(n)
    vals = [200.0 - 1.5 * i for i in range(n)]
    return ts, vals


def _make_flat(n: int = 48) -> tuple[list[float], list[float]]:
    ts = _make_timestamps(n)
    vals = [50.0] * n
    return ts, vals


# -----------------------------------------------------------------------
# Linear forecast
# -----------------------------------------------------------------------

class TestLinearForecast:
    def test_linear_forecast_uptrend(self, forecaster: Forecaster) -> None:
        ts, vals = _make_uptrend()
        result = forecaster.forecast_linear(ts, vals, horizon_hours=24)
        assert isinstance(result, ForecastResult)
        assert result.method == "linear"
        # All forecast values should be higher than the last observed value
        assert all(v > vals[-1] for v in result.values)

    def test_linear_forecast_downtrend(self, forecaster: Forecaster) -> None:
        ts, vals = _make_downtrend()
        result = forecaster.forecast_linear(ts, vals, horizon_hours=24)
        assert all(v < vals[-1] for v in result.values)

    def test_linear_forecast_flat(self, forecaster: Forecaster) -> None:
        ts, vals = _make_flat()
        result = forecaster.forecast_linear(ts, vals, horizon_hours=24)
        # Flat series: forecast values should be very close to 50
        for v in result.values:
            assert abs(v - 50.0) < 1.0

    def test_forecast_returns_confidence(self, forecaster: Forecaster) -> None:
        ts, vals = _make_uptrend()
        result = forecaster.forecast_linear(ts, vals)
        assert 0.0 <= result.confidence <= 1.0


# -----------------------------------------------------------------------
# Breach prediction
# -----------------------------------------------------------------------

class TestBreachPrediction:
    def test_breach_prediction_will_breach(self, forecaster: Forecaster) -> None:
        ts, vals = _make_uptrend()
        result = forecaster.forecast_linear(ts, vals, horizon_hours=168, threshold=200.0)
        assert result.breach_prediction is not None
        assert result.breach_prediction.threshold == 200.0

    def test_breach_prediction_no_breach(self, forecaster: Forecaster) -> None:
        ts, vals = _make_flat()
        result = forecaster.forecast_linear(ts, vals, horizon_hours=24, threshold=1000.0)
        assert result.breach_prediction is None


# -----------------------------------------------------------------------
# Resource exhaustion
# -----------------------------------------------------------------------

class TestResourceExhaustion:
    def test_resource_exhaustion_already_full(self, forecaster: Forecaster) -> None:
        ts, vals = _make_uptrend()
        # Current value (last) exceeds capacity
        breach = forecaster.predict_resource_exhaustion(ts, vals, capacity=0.0)
        assert breach is not None
        assert breach.confidence == 1.0

    def test_resource_exhaustion_prediction(self, forecaster: Forecaster) -> None:
        ts, vals = _make_uptrend()
        breach = forecaster.predict_resource_exhaustion(ts, vals, capacity=500.0)
        # Uptrend should eventually breach 500
        assert breach is not None
        assert breach.threshold == 500.0


# -----------------------------------------------------------------------
# Error handling
# -----------------------------------------------------------------------

class TestErrors:
    def test_insufficient_data_raises(self, forecaster: Forecaster) -> None:
        with pytest.raises(ValueError, match="at least 24"):
            forecaster.forecast_linear([1.0, 2.0], [1.0, 2.0])
