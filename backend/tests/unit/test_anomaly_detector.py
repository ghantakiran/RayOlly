"""Tests for rayolly.services.ai.anomaly — AnomalyDetector."""

from __future__ import annotations

import pytest

from rayolly.services.ai.anomaly import AnomalyDetector, AnomalyMethod


@pytest.fixture
def detector() -> AnomalyDetector:
    return AnomalyDetector(sensitivity=0.8)


@pytest.fixture
def normal_series() -> list[float]:
    """A stable series centred around 50 with small noise."""
    import numpy as np

    rng = np.random.default_rng(42)
    return (rng.normal(50, 2, size=100)).tolist()


# -----------------------------------------------------------------------
# Z-score
# -----------------------------------------------------------------------

class TestZScore:
    def test_zscore_normal_value(self, detector: AnomalyDetector, normal_series: list[float]) -> None:
        result = detector.detect(normal_series, 50.0, AnomalyMethod.ZSCORE)
        assert result.is_anomaly is False
        assert result.method == AnomalyMethod.ZSCORE

    def test_zscore_anomaly(self, detector: AnomalyDetector, normal_series: list[float]) -> None:
        result = detector.detect(normal_series, 500.0, AnomalyMethod.ZSCORE)
        assert result.is_anomaly is True
        assert result.score > 0.5

    def test_zscore_constant_series(self, detector: AnomalyDetector) -> None:
        constant = [10.0] * 50
        result = detector.detect(constant, 10.0, AnomalyMethod.ZSCORE)
        assert result.is_anomaly is False
        assert result.score == 0.0
        assert result.expected_range == (10.0, 10.0)


# -----------------------------------------------------------------------
# MAD
# -----------------------------------------------------------------------

class TestMAD:
    def test_mad_normal_value(self, detector: AnomalyDetector, normal_series: list[float]) -> None:
        result = detector.detect(normal_series, 50.0, AnomalyMethod.MAD)
        assert result.is_anomaly is False

    def test_mad_anomaly(self, detector: AnomalyDetector, normal_series: list[float]) -> None:
        result = detector.detect(normal_series, 500.0, AnomalyMethod.MAD)
        assert result.is_anomaly is True

    def test_mad_constant_series(self, detector: AnomalyDetector) -> None:
        constant = [7.0] * 50
        result = detector.detect(constant, 7.0, AnomalyMethod.MAD)
        assert result.is_anomaly is False
        assert result.score == 0.0


# -----------------------------------------------------------------------
# IQR
# -----------------------------------------------------------------------

class TestIQR:
    def test_iqr_normal_value(self, detector: AnomalyDetector, normal_series: list[float]) -> None:
        result = detector.detect(normal_series, 50.0, AnomalyMethod.IQR)
        assert result.is_anomaly is False

    def test_iqr_anomaly(self, detector: AnomalyDetector, normal_series: list[float]) -> None:
        result = detector.detect(normal_series, 500.0, AnomalyMethod.IQR)
        assert result.is_anomaly is True

    def test_iqr_tight_range(self, detector: AnomalyDetector) -> None:
        tight = [10.0] * 50
        result = detector.detect(tight, 10.0, AnomalyMethod.IQR)
        assert result.is_anomaly is False
        assert result.score == 0.0


# -----------------------------------------------------------------------
# Isolation Forest
# -----------------------------------------------------------------------

class TestIsolationForest:
    def test_isolation_forest_normal(self, detector: AnomalyDetector, normal_series: list[float]) -> None:
        result = detector.detect(normal_series, 50.0, AnomalyMethod.ISOLATION_FOREST)
        # Should not flag a value right at the mean
        assert bool(result.is_anomaly) is False

    def test_isolation_forest_anomaly(self, detector: AnomalyDetector, normal_series: list[float]) -> None:
        result = detector.detect(normal_series, 500.0, AnomalyMethod.ISOLATION_FOREST)
        assert bool(result.is_anomaly) is True


# -----------------------------------------------------------------------
# Ensemble
# -----------------------------------------------------------------------

class TestEnsemble:
    def test_ensemble_majority_vote(self, detector: AnomalyDetector, normal_series: list[float]) -> None:
        result = detector.detect_ensemble(normal_series, 500.0)
        assert result.is_anomaly is True

    def test_ensemble_no_anomaly(self, detector: AnomalyDetector, normal_series: list[float]) -> None:
        result = detector.detect_ensemble(normal_series, 50.0)
        assert result.is_anomaly is False


# -----------------------------------------------------------------------
# Edge cases & properties
# -----------------------------------------------------------------------

class TestEdgeCases:
    def test_insufficient_data(self, detector: AnomalyDetector) -> None:
        short = [1.0, 2.0, 3.0]
        result = detector.detect(short, 100.0)
        assert result.is_anomaly is False
        assert result.score == 0.0

    def test_sensitivity_affects_threshold(self) -> None:
        strict = AnomalyDetector(sensitivity=1.0)
        lax = AnomalyDetector(sensitivity=0.3)
        assert strict._zscore_threshold < lax._zscore_threshold

    def test_score_range(self, detector: AnomalyDetector, normal_series: list[float]) -> None:
        for val in [0.0, 50.0, 500.0, -500.0]:
            result = detector.detect(normal_series, val)
            assert 0.0 <= result.score <= 1.0

    def test_severity_mapping(self) -> None:
        assert AnomalyDetector._score_to_severity(0.95) == "critical"
        assert AnomalyDetector._score_to_severity(0.75) == "high"
        assert AnomalyDetector._score_to_severity(0.5) == "medium"
        assert AnomalyDetector._score_to_severity(0.2) == "low"
