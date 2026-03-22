"""Anomaly detection engine — multi-method anomaly scoring for metrics."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np
import structlog

logger = structlog.get_logger(__name__)


class AnomalyMethod(str, Enum):
    ZSCORE = "zscore"
    MAD = "mad"
    IQR = "iqr"
    ISOLATION_FOREST = "isolation_forest"


@dataclass
class AnomalyResult:
    is_anomaly: bool
    score: float  # 0.0 to 1.0
    method: AnomalyMethod
    expected_range: tuple[float, float]
    actual_value: float
    severity: str  # low, medium, high, critical


class AnomalyDetector:
    """Multi-method anomaly detection for time-series metrics."""

    def __init__(self, sensitivity: float = 0.8) -> None:
        self.sensitivity = sensitivity
        self._zscore_threshold = 3.0 * (1 / sensitivity)
        self._mad_threshold = 3.5 * (1 / sensitivity)

    def detect(
        self,
        values: list[float],
        current_value: float,
        method: AnomalyMethod = AnomalyMethod.ZSCORE,
    ) -> AnomalyResult:
        """Detect if current_value is anomalous given historical values."""
        if len(values) < 10:
            return AnomalyResult(
                is_anomaly=False,
                score=0.0,
                method=method,
                expected_range=(0.0, 0.0),
                actual_value=current_value,
                severity="low",
            )

        match method:
            case AnomalyMethod.ZSCORE:
                return self._detect_zscore(values, current_value)
            case AnomalyMethod.MAD:
                return self._detect_mad(values, current_value)
            case AnomalyMethod.IQR:
                return self._detect_iqr(values, current_value)
            case AnomalyMethod.ISOLATION_FOREST:
                return self._detect_isolation_forest(values, current_value)

    def detect_ensemble(
        self, values: list[float], current_value: float
    ) -> AnomalyResult:
        """Run multiple methods and combine scores."""
        results = [
            self._detect_zscore(values, current_value),
            self._detect_mad(values, current_value),
            self._detect_iqr(values, current_value),
        ]

        avg_score = sum(r.score for r in results) / len(results)
        votes = sum(1 for r in results if r.is_anomaly)
        is_anomaly = votes >= 2  # Majority voting

        return AnomalyResult(
            is_anomaly=is_anomaly,
            score=avg_score,
            method=AnomalyMethod.ZSCORE,  # ensemble
            expected_range=results[0].expected_range,
            actual_value=current_value,
            severity=self._score_to_severity(avg_score),
        )

    def _detect_zscore(self, values: list[float], current: float) -> AnomalyResult:
        """Z-score based anomaly detection."""
        arr = np.array(values)
        mean = float(np.mean(arr))
        std = float(np.std(arr))

        if std == 0:
            return AnomalyResult(
                is_anomaly=False, score=0.0, method=AnomalyMethod.ZSCORE,
                expected_range=(mean, mean), actual_value=current, severity="low",
            )

        zscore = abs(current - mean) / std
        score = min(zscore / self._zscore_threshold, 1.0)
        is_anomaly = zscore > self._zscore_threshold
        expected = (mean - self._zscore_threshold * std, mean + self._zscore_threshold * std)

        return AnomalyResult(
            is_anomaly=is_anomaly,
            score=score,
            method=AnomalyMethod.ZSCORE,
            expected_range=expected,
            actual_value=current,
            severity=self._score_to_severity(score),
        )

    def _detect_mad(self, values: list[float], current: float) -> AnomalyResult:
        """Median Absolute Deviation — robust to outliers."""
        arr = np.array(values)
        median = float(np.median(arr))
        mad = float(np.median(np.abs(arr - median)))

        if mad == 0:
            return AnomalyResult(
                is_anomaly=False, score=0.0, method=AnomalyMethod.MAD,
                expected_range=(median, median), actual_value=current, severity="low",
            )

        modified_zscore = 0.6745 * abs(current - median) / mad
        score = min(modified_zscore / self._mad_threshold, 1.0)
        is_anomaly = modified_zscore > self._mad_threshold
        bound = self._mad_threshold * mad / 0.6745
        expected = (median - bound, median + bound)

        return AnomalyResult(
            is_anomaly=is_anomaly,
            score=score,
            method=AnomalyMethod.MAD,
            expected_range=expected,
            actual_value=current,
            severity=self._score_to_severity(score),
        )

    def _detect_iqr(self, values: list[float], current: float) -> AnomalyResult:
        """Interquartile Range method."""
        arr = np.array(values)
        q1 = float(np.percentile(arr, 25))
        q3 = float(np.percentile(arr, 75))
        iqr = q3 - q1

        if iqr == 0:
            return AnomalyResult(
                is_anomaly=False, score=0.0, method=AnomalyMethod.IQR,
                expected_range=(q1, q3), actual_value=current, severity="low",
            )

        multiplier = 1.5 / self.sensitivity
        lower = q1 - multiplier * iqr
        upper = q3 + multiplier * iqr
        is_anomaly = current < lower or current > upper

        if is_anomaly:
            distance = max(lower - current, current - upper, 0)
            score = min(distance / (multiplier * iqr), 1.0)
        else:
            score = 0.0

        return AnomalyResult(
            is_anomaly=is_anomaly,
            score=score,
            method=AnomalyMethod.IQR,
            expected_range=(lower, upper),
            actual_value=current,
            severity=self._score_to_severity(score),
        )

    def _detect_isolation_forest(
        self, values: list[float], current: float
    ) -> AnomalyResult:
        """Isolation Forest — ML-based anomaly detection."""
        try:
            from sklearn.ensemble import IsolationForest

            arr = np.array(values + [current]).reshape(-1, 1)
            clf = IsolationForest(contamination=0.05, random_state=42)
            clf.fit(arr)
            scores = clf.decision_function(arr)
            current_score = float(scores[-1])

            # decision_function returns negative for anomalies
            normalized_score = max(0.0, min(1.0, -current_score))
            is_anomaly = clf.predict(np.array([[current]]))[0] == -1

            mean = float(np.mean(values))
            std = float(np.std(values))
            expected = (mean - 3 * std, mean + 3 * std)

            return AnomalyResult(
                is_anomaly=is_anomaly,
                score=normalized_score,
                method=AnomalyMethod.ISOLATION_FOREST,
                expected_range=expected,
                actual_value=current,
                severity=self._score_to_severity(normalized_score),
            )
        except ImportError:
            logger.warning("sklearn_not_available_fallback_to_zscore")
            return self._detect_zscore(values, current)

    @staticmethod
    def _score_to_severity(score: float) -> str:
        if score >= 0.9:
            return "critical"
        if score >= 0.7:
            return "high"
        if score >= 0.4:
            return "medium"
        return "low"
