"""Time-series forecasting for capacity planning and predictive alerting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ForecastResult:
    timestamps: list[datetime]
    values: list[float]
    lower_bound: list[float]
    upper_bound: list[float]
    method: str
    confidence: float
    breach_prediction: BreachPrediction | None = None


@dataclass
class BreachPrediction:
    threshold: float
    predicted_breach_time: datetime
    current_value: float
    confidence: float


class Forecaster:
    """Time-series forecasting using multiple methods."""

    def forecast_linear(
        self,
        timestamps: list[float],
        values: list[float],
        horizon_hours: int = 168,
        threshold: float | None = None,
    ) -> ForecastResult:
        """Linear regression forecast — simple but fast."""
        if len(values) < 24:
            raise ValueError("Need at least 24 data points for forecasting")

        x = np.array(timestamps)
        y = np.array(values)

        # Linear regression
        coeffs = np.polyfit(x, y, 1)
        slope, intercept = coeffs

        # Generate future timestamps
        last_ts = timestamps[-1]
        step = (timestamps[-1] - timestamps[0]) / (len(timestamps) - 1) if len(timestamps) > 1 else 3600
        future_ts = [last_ts + step * i for i in range(1, horizon_hours + 1)]

        predicted = [float(slope * t + intercept) for t in future_ts]

        # Confidence interval (using residual standard deviation)
        residuals = y - (slope * x + intercept)
        std_residual = float(np.std(residuals))
        lower = [v - 2 * std_residual for v in predicted]
        upper = [v + 2 * std_residual for v in predicted]

        # Convert timestamps back to datetime
        base_time = datetime.fromtimestamp(last_ts)
        future_dts = [
            base_time + timedelta(seconds=(t - last_ts)) for t in future_ts
        ]

        # Check for threshold breach
        breach = None
        if threshold is not None:
            for i, v in enumerate(predicted):
                if v >= threshold:
                    breach = BreachPrediction(
                        threshold=threshold,
                        predicted_breach_time=future_dts[i],
                        current_value=float(values[-1]),
                        confidence=0.7,
                    )
                    break

        return ForecastResult(
            timestamps=future_dts,
            values=predicted,
            lower_bound=lower,
            upper_bound=upper,
            method="linear",
            confidence=max(0.0, min(1.0, 1.0 - std_residual / (np.std(y) + 1e-10))),
            breach_prediction=breach,
        )

    def forecast_prophet(
        self,
        timestamps: list[datetime],
        values: list[float],
        horizon_hours: int = 168,
        threshold: float | None = None,
    ) -> ForecastResult:
        """Prophet-based forecast with seasonality detection."""
        try:
            import pandas as pd
            from prophet import Prophet

            df = pd.DataFrame({
                "ds": timestamps,
                "y": values,
            })

            model = Prophet(
                yearly_seasonality=False,
                weekly_seasonality=True,
                daily_seasonality=True,
                changepoint_prior_scale=0.05,
            )
            model.fit(df)

            future = model.make_future_dataframe(periods=horizon_hours, freq="h")
            forecast = model.predict(future)

            # Extract future predictions only
            future_mask = forecast["ds"] > df["ds"].max()
            future_forecast = forecast[future_mask]

            result_timestamps = future_forecast["ds"].tolist()
            result_values = future_forecast["yhat"].tolist()
            lower = future_forecast["yhat_lower"].tolist()
            upper = future_forecast["yhat_upper"].tolist()

            breach = None
            if threshold is not None:
                for i, v in enumerate(result_values):
                    if v >= threshold:
                        breach = BreachPrediction(
                            threshold=threshold,
                            predicted_breach_time=result_timestamps[i],
                            current_value=float(values[-1]),
                            confidence=0.8,
                        )
                        break

            return ForecastResult(
                timestamps=result_timestamps,
                values=result_values,
                lower_bound=lower,
                upper_bound=upper,
                method="prophet",
                confidence=0.8,
                breach_prediction=breach,
            )

        except ImportError:
            logger.warning("prophet_not_available_fallback_to_linear")
            float_timestamps = [dt.timestamp() for dt in timestamps]
            return self.forecast_linear(float_timestamps, values, horizon_hours, threshold)

    def predict_resource_exhaustion(
        self,
        timestamps: list[float],
        values: list[float],
        capacity: float,
    ) -> BreachPrediction | None:
        """Predict when a resource (disk, memory, etc.) will be exhausted."""
        if len(values) < 24:
            return None

        current = values[-1]
        if current >= capacity:
            return BreachPrediction(
                threshold=capacity,
                predicted_breach_time=datetime.now(),
                current_value=current,
                confidence=1.0,
            )

        result = self.forecast_linear(
            timestamps, values, horizon_hours=720, threshold=capacity
        )
        return result.breach_prediction
