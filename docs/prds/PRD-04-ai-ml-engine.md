# PRD-04: AI/ML Engine Core

**Product**: RayOlly — AI-Native Observability Platform
**Version**: 1.0
**Date**: 2026-03-19
**Status**: Draft
**Author**: AI/ML Platform Team
**Stakeholders**: Engineering, Data Science, SRE, Product, Security
**Dependencies**: PRD-02 (Storage Engine), PRD-03 (Query Engine)
**Downstream**: PRD-05 (AI Agents), PRD-09 (Alerting), PRD-10 (Dashboards)

---

## 1. Overview

### 1.1 Purpose

The AI/ML Engine is a **foundational layer** of the RayOlly platform, not an add-on or premium feature. Every telemetry signal flowing through RayOlly passes through or is enriched by the AI/ML Engine. It powers anomaly detection, forecasting, pattern mining, root cause analysis, and metric correlation — and critically, it provides the intelligence substrate that the Agent system (PRD-05) relies on for autonomous operations.

This PRD defines the complete AI/ML Engine architecture: algorithms, training pipelines, inference infrastructure, model management, multi-tenancy, and integration points across the platform.

### 1.2 Strategic Context

The AI/ML Engine is RayOlly's primary competitive differentiator against legacy observability platforms that retrofit machine learning onto rule-based architectures:

| Platform | AI Approach | Limitation |
|----------|-------------|------------|
| **Dynatrace Davis AI** | Deterministic causality engine with pre-coded topology rules | Limited to known topology patterns; no generative reasoning; requires OneAgent lock-in |
| **Datadog Watchdog** | Anomaly detection on metrics with basic correlation | Siloed per-product (separate for APM, logs, infra); limited RCA; no autonomous agents |
| **Splunk ITSI** | ML Toolkit with manual model configuration | Requires significant manual configuration; slow to adapt; expensive compute |
| **New Relic NRAI** | LLM wrapper over NRQL queries | Thin AI layer; no deep anomaly detection; limited to query generation |
| **RayOlly** | AI-native engine with unified anomaly detection, forecasting, pattern mining, causal inference, and agent-ready ML scoring | Full-stack AI across all telemetry types; autonomous agent integration; per-tenant adaptive models |

### 1.3 AI/ML Engine Position in Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Ingestion Pipeline (PRD-01)                       │
│   OTLP → Schema Validation → Enrichment → Stream Processing             │
└─────────────────────┬───────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     ┌──────────────────────────────────────┐            │
│   Storage (PRD-02)  │     AI/ML Engine (THIS PRD)          │            │
│   ClickHouse ───────┤                                      │            │
│   S3/Parquet ───────┤  ┌────────────┐  ┌───────────────┐  │            │
│                     │  │  Training   │  │  Inference    │  │            │
│   Query Engine ─────┤  │  Pipeline   │  │  Pipeline     │  │            │
│   (PRD-03)          │  │  (Batch)    │  │  (Streaming)  │  │            │
│                     │  └──────┬─────┘  └───────┬───────┘  │            │
│                     │         │                 │           │            │
│                     │  ┌──────▼─────────────────▼───────┐  │            │
│                     │  │       Model Registry            │  │            │
│                     │  │  (Versioned, Per-Tenant)        │  │            │
│                     │  └──────┬──────────────────────────┘  │            │
│                     │         │                              │            │
│                     │  ┌──────▼──────────────────────────┐  │            │
│                     │  │       Feature Store              │  │            │
│                     │  │  (Offline + Online)              │  │            │
│                     │  └─────────────────────────────────┘  │            │
│                     └──────────────────┬───────────────────┘            │
└────────────────────────────────────────┼────────────────────────────────┘
                                         │
                      ┌──────────────────▼──────────────────┐
                      │  ML Scores, Anomalies, Forecasts     │
                      │  Published to:                        │
                      │  ├─ Agent Orchestrator (PRD-05)       │
                      │  ├─ Alerting Engine (PRD-09)          │
                      │  ├─ Dashboard API (PRD-10)            │
                      │  └─ Query Engine (PRD-03)             │
                      └─────────────────────────────────────┘
```

---

## 2. Goals & Non-Goals

### 2.1 Goals

| ID | Goal | Success Criteria |
|----|------|-----------------|
| G1 | Detect anomalies automatically across all telemetry types without manual threshold configuration | Zero-config anomaly detection active within 24h of first data ingestion |
| G2 | Provide predictive alerting that warns before failures occur | SLO breach predicted 4+ hours in advance with >80% accuracy |
| G3 | Extract patterns from unstructured logs automatically | >95% of log lines clustered into known patterns within 1 hour |
| G4 | Identify root causes of incidents by correlating signals across the topology | RCA narrows to correct root cause in top-3 candidates >70% of the time |
| G5 | Forecast capacity exhaustion for infrastructure resources | Disk/memory/CPU exhaustion predicted 7+ days in advance |
| G6 | Deliver real-time ML scoring with sub-100ms latency on the ingestion hot path | P99 scoring latency < 100ms for streaming inference |
| G7 | Maintain per-tenant model isolation with efficient resource sharing | No cross-tenant data leakage; shared GPU utilization > 60% |
| G8 | Learn continuously from user feedback to reduce false positives | False positive rate < 5% after 2 weeks of active learning |
| G9 | Provide an ML pipeline that is observable, auditable, and reproducible | Every model version traceable to training data, hyperparameters, and evaluation metrics |
| G10 | Feed all ML outputs into the Agent system for autonomous operations | All anomaly, forecast, and RCA signals available via Agent API within 1s of generation |

### 2.2 Non-Goals

| ID | Non-Goal | Rationale |
|----|----------|-----------|
| NG1 | General-purpose ML platform (AutoML for arbitrary datasets) | RayOlly's ML is purpose-built for observability telemetry, not a generic ML-as-a-Service |
| NG2 | Custom model upload by end users (v1) | Users can consume ML outputs but not deploy arbitrary models; planned for v2 |
| NG3 | Natural language query generation | Handled by PRD-11 (Natural Language Interface) using LLMs |
| NG4 | LLM-based reasoning and agent orchestration | Handled by PRD-05 (AI Agents); this PRD provides the ML scoring that agents consume |
| NG5 | Real-time training on streaming data (online learning) | v1 uses batch retraining with streaming inference; online learning planned for v2 |
| NG6 | GPU cluster management | Relies on Kubernetes GPU scheduling (PRD-13); this PRD defines resource requests |
| NG7 | Security threat detection (SIEM use case) | Security analytics is a future module; this PRD focuses on operational observability |

---

## 3. Anomaly Detection Engine

The anomaly detection engine is the highest-value component of the AI/ML Engine. It must detect anomalies across metrics, logs, and traces without requiring users to configure thresholds manually.

### 3.1 Detection Method Hierarchy

RayOlly employs a **tiered detection strategy** that matches algorithm complexity to data characteristics. Simpler methods run first (cheaper, faster); complex methods activate for signals that require them.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Anomaly Detection Tiers                           │
│                                                                     │
│  Tier 1: Statistical (All metrics, always-on)                       │
│  ├─ Z-Score / Modified Z-Score                                      │
│  ├─ Median Absolute Deviation (MAD)                                 │
│  ├─ Interquartile Range (IQR)                                       │
│  └─ Grubbs Test                                                     │
│                                                                     │
│  Tier 2: Time-Series (Metrics with seasonality)                     │
│  ├─ STL Decomposition                                               │
│  ├─ Prophet-based Seasonal Detection                                │
│  └─ Change Point Detection (PELT, BOCPD)                            │
│                                                                     │
│  Tier 3: ML Models (High-value metrics, complex patterns)           │
│  ├─ Isolation Forest                                                │
│  ├─ Local Outlier Factor (LOF)                                      │
│  └─ Autoencoder (reconstruction error)                              │
│                                                                     │
│  Tier 4: Deep Learning (Multi-variate, long-range dependencies)     │
│  ├─ LSTM Autoencoder                                                │
│  └─ Temporal Convolutional Network (TCN)                            │
│                                                                     │
│  Tier 5: Ensemble (Critical SLO-linked metrics)                     │
│  └─ Weighted voting across Tiers 1-4                                │
│                                                                     │
│  Automatic tier selection based on:                                  │
│  - Metric cardinality and history length                            │
│  - Detected seasonality strength                                     │
│  - Multi-variate correlation count                                   │
│  - Tenant tier (free vs enterprise)                                  │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 Statistical Methods (Tier 1)

#### 3.2.1 Z-Score and Modified Z-Score

The Z-score measures how many standard deviations a data point is from the mean. The modified Z-score uses the median and MAD for robustness against outliers in the baseline itself.

**Standard Z-Score**:

```
z = (x - μ) / σ

Where:
  x = observed value
  μ = rolling mean (configurable window, default 7 days)
  σ = rolling standard deviation

Anomaly threshold: |z| > 3.0 (configurable per sensitivity level)
```

**Modified Z-Score** (robust variant):

```
M = 0.6745 * (x - median) / MAD

Where:
  MAD = median(|x_i - median(x)|)
  0.6745 = the 0.75th quantile of the standard normal distribution

Anomaly threshold: |M| > 3.5
```

The modified Z-score is the default for Tier 1 because it is resistant to masking — where a cluster of outliers shifts the mean and standard deviation, hiding true anomalies.

**Implementation**:

```python
import numpy as np
from dataclasses import dataclass
from enum import Enum

class Sensitivity(Enum):
    LOW = "low"         # Fewer alerts, only extreme anomalies
    MEDIUM = "medium"   # Balanced (default)
    HIGH = "high"       # More alerts, catches subtle anomalies

SENSITIVITY_THRESHOLDS = {
    Sensitivity.LOW: {"z_score": 4.0, "modified_z": 4.5},
    Sensitivity.MEDIUM: {"z_score": 3.0, "modified_z": 3.5},
    Sensitivity.HIGH: {"z_score": 2.0, "modified_z": 2.5},
}

@dataclass
class AnomalyScore:
    value: float
    score: float           # 0.0 - 1.0 normalized anomaly score
    confidence: float      # 0.0 - 1.0 confidence in the detection
    method: str            # detection method used
    is_anomaly: bool
    direction: str         # "above", "below", "both"
    expected_range: tuple  # (lower_bound, upper_bound)

def modified_z_score(values: np.ndarray, current: float) -> AnomalyScore:
    """Compute modified Z-score for a single observation against a baseline."""
    median = np.median(values)
    mad = np.median(np.abs(values - median))

    if mad == 0:
        # All values identical — any deviation is anomalous
        mad = 1.4826 * np.mean(np.abs(values - median))
        if mad == 0:
            return AnomalyScore(
                value=current,
                score=0.0 if current == median else 1.0,
                confidence=0.5,
                method="modified_z_score",
                is_anomaly=current != median,
                direction="above" if current > median else "below",
                expected_range=(median, median),
            )

    m_score = 0.6745 * (current - median) / mad
    normalized = min(abs(m_score) / 10.0, 1.0)  # normalize to 0-1

    return AnomalyScore(
        value=current,
        score=normalized,
        confidence=min(len(values) / 1000.0, 1.0),  # more data = more confidence
        method="modified_z_score",
        is_anomaly=abs(m_score) > 3.5,
        direction="above" if m_score > 0 else "below",
        expected_range=(
            median - 3.5 * mad / 0.6745,
            median + 3.5 * mad / 0.6745,
        ),
    )
```

#### 3.2.2 Interquartile Range (IQR) Method

Effective for skewed distributions common in latency metrics (long-tailed).

```
IQR = Q3 - Q1
Lower fence = Q1 - k * IQR
Upper fence = Q3 + k * IQR

Where k = 1.5 (standard) or 3.0 (extreme outliers only)
```

#### 3.2.3 Grubbs Test

Used for confirming individual outliers when the underlying distribution is approximately normal. Applied as a secondary confirmation step after Z-score detection.

```
G = max|x_i - x̄| / s

Critical value compared against t-distribution:
G_critical = ((N-1) / √N) * √(t²(α/(2N), N-2) / (N - 2 + t²(α/(2N), N-2)))
```

### 3.3 Time-Series Methods (Tier 2)

#### 3.3.1 STL Decomposition

Seasonal and Trend decomposition using Loess (STL) separates a time series into three components:

```
Y(t) = T(t) + S(t) + R(t)

Where:
  Y(t) = observed value at time t
  T(t) = trend component (long-term direction)
  S(t) = seasonal component (repeating patterns)
  R(t) = residual component (noise + anomalies)
```

Anomalies are detected in the **residual** component after removing trend and seasonality. This prevents false positives from normal seasonal traffic spikes (e.g., Monday morning login surge).

```python
from statsmodels.tsa.seasonal import STL

def stl_anomaly_detection(
    series: pd.Series,
    period: int = 1440,  # default: 1-day period for minute-level data
    seasonal_window: int = 7,
    residual_threshold: float = 3.0,
) -> list[AnomalyScore]:
    """
    Detect anomalies using STL decomposition.

    The residual component is analyzed using modified Z-score.
    Seasonal patterns are automatically learned and excluded from detection.
    """
    stl = STL(
        series,
        period=period,
        seasonal=seasonal_window,
        robust=True,  # resistant to outliers in fitting
    )
    result = stl.fit()

    residuals = result.resid
    seasonal = result.seasonal
    trend = result.trend

    # Detect anomalies in residuals using modified Z-score
    scores = []
    for i, (val, resid) in enumerate(zip(series, residuals)):
        expected = trend.iloc[i] + seasonal.iloc[i]
        mad = np.median(np.abs(residuals - np.median(residuals)))
        m_score = 0.6745 * resid / mad if mad > 0 else 0

        scores.append(AnomalyScore(
            value=val,
            score=min(abs(m_score) / 10.0, 1.0),
            confidence=0.85,
            method="stl_decomposition",
            is_anomaly=abs(m_score) > residual_threshold,
            direction="above" if m_score > 0 else "below",
            expected_range=(
                expected - residual_threshold * mad / 0.6745,
                expected + residual_threshold * mad / 0.6745,
            ),
        ))

    return scores
```

#### 3.3.2 Prophet-Based Seasonality Detection

Facebook Prophet (now Meta Prophet) handles multiple seasonality periods simultaneously — critical for observability data that has daily, weekly, and monthly patterns.

```
y(t) = g(t) + s(t) + h(t) + ε(t)

Where:
  g(t) = piecewise linear or logistic growth trend
  s(t) = Fourier series for seasonality: Σ(a_n * cos(2πnt/P) + b_n * sin(2πnt/P))
  h(t) = holiday/event effects (mapped to deployment windows, maintenance)
  ε(t) = residual (anomaly detection target)
```

**Seasonality periods auto-detected**:

| Pattern | Period | Example |
|---------|--------|---------|
| Intra-day | 24 hours | Business hours traffic peak |
| Day-of-week | 7 days | Monday morning logins, weekend traffic drop |
| Monthly | 30 days | End-of-month batch processing |
| Pay cycle | 14 days | Payroll processing spikes |
| Custom | Configurable | Deployment windows, maintenance schedules |

#### 3.3.3 Change Point Detection

Detects abrupt changes in the statistical properties of a time series — essential for catching step-changes after deployments, configuration changes, or infrastructure failures.

**PELT (Pruned Exact Linear Time)**:

```
Minimize: Σ [C(y(t_i:t_{i+1}))] + β * k

Where:
  C() = cost function (e.g., change in mean, change in variance)
  β = penalty for number of change points (controls sensitivity)
  k = number of change points
```

**BOCPD (Bayesian Online Change Point Detection)**:

For real-time streaming change point detection. Maintains a run-length probability distribution:

```
P(r_t | x_{1:t}) ∝ P(x_t | r_t, x_{t-r_t:t-1}) * P(r_t | r_{t-1}) * P(r_{t-1} | x_{1:t-1})

Where:
  r_t = run length at time t (time since last change point)
  x_t = observation at time t
```

### 3.4 ML Methods (Tier 3)

#### 3.4.1 Isolation Forest

Isolation Forest is the primary unsupervised anomaly detector for multi-dimensional metrics. It works by randomly partitioning data — anomalies require fewer partitions to isolate.

```
Anomaly Score: s(x, n) = 2^(-E(h(x)) / c(n))

Where:
  h(x) = path length of observation x in the isolation tree
  E(h(x)) = average path length across all trees in the forest
  c(n) = average path length of unsuccessful search in BST (normalization)
  c(n) = 2 * H(n-1) - 2(n-1)/n, where H(i) = ln(i) + Euler's constant

Score interpretation:
  s ≈ 1.0 → anomaly (short average path length)
  s ≈ 0.5 → normal (average path length matches expected)
  s ≈ 0.0 → very normal / dense region
```

**Configuration**:

```yaml
isolation_forest:
  n_estimators: 200          # number of trees
  max_samples: 4096          # samples per tree (auto-tuned)
  contamination: "auto"      # expected anomaly ratio (auto-estimated)
  max_features: 1.0          # feature fraction per tree
  bootstrap: false
  random_state: 42

  # RayOlly-specific parameters
  training_window: "7d"      # rolling window for training data
  retrain_interval: "6h"     # how often to retrain
  feature_groups:             # correlated feature sets
    - ["cpu_usage", "memory_usage", "load_avg"]
    - ["request_rate", "error_rate", "latency_p99"]
    - ["disk_io_read", "disk_io_write", "disk_queue_depth"]
```

#### 3.4.2 Local Outlier Factor (LOF)

LOF detects anomalies based on local density deviation — a point is anomalous if its neighborhood is significantly less dense than its neighbors' neighborhoods. Particularly effective for metrics with varying density patterns (e.g., microservice latency during different traffic levels).

```
LOF_k(x) = Σ(lrd_k(o) / lrd_k(x)) / |N_k(x)|

Where:
  lrd_k(x) = local reachability density = |N_k(x)| / Σ reach_dist_k(x, o)
  reach_dist_k(x, o) = max(k-dist(o), d(x, o))
  N_k(x) = k-nearest neighbors of x

LOF ≈ 1 → similar density to neighbors (normal)
LOF >> 1 → much lower density than neighbors (anomaly)
```

#### 3.4.3 Autoencoder-Based Detection

Autoencoders learn a compressed representation of normal patterns. Anomalies produce high reconstruction error because they deviate from learned normal patterns.

```
Architecture:
  Input (n features) → Encoder → Latent Space (d dimensions) → Decoder → Output (n features)

  Anomaly score = ||x - x̂||² (reconstruction error)

  Where:
    x = input observation
    x̂ = reconstructed output
    Threshold = μ(errors) + k * σ(errors) on validation set
```

**Implementation**:

```python
import torch
import torch.nn as nn

class MetricAutoencoder(nn.Module):
    """
    Autoencoder for multi-variate metric anomaly detection.

    Learns compressed representation of normal metric patterns.
    High reconstruction error indicates anomaly.
    """

    def __init__(self, input_dim: int, latent_dim: int = 8):
        super().__init__()

        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 64),
            nn.ReLU(),
            nn.BatchNorm1d(64),
            nn.Dropout(0.2),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.BatchNorm1d(32),
            nn.Linear(32, latent_dim),
        )

        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, 32),
            nn.ReLU(),
            nn.BatchNorm1d(32),
            nn.Dropout(0.2),
            nn.Linear(32, 64),
            nn.ReLU(),
            nn.BatchNorm1d(64),
            nn.Linear(64, input_dim),
        )

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        latent = self.encoder(x)
        reconstructed = self.decoder(latent)
        return reconstructed, latent

    def anomaly_score(self, x: torch.Tensor) -> torch.Tensor:
        """Compute reconstruction error as anomaly score."""
        reconstructed, _ = self.forward(x)
        return torch.mean((x - reconstructed) ** 2, dim=1)
```

### 3.5 Deep Learning Methods (Tier 4)

#### 3.5.1 LSTM Autoencoder

For complex temporal patterns with long-range dependencies. The LSTM encoder captures temporal dynamics; high reconstruction error on a sequence of observations indicates a temporal anomaly that point-wise detectors miss.

```
Architecture:
  Input sequence (T timesteps x n features)
      │
      ▼
  LSTM Encoder (2 layers, hidden_dim=128)
      │
      ▼
  Latent representation (hidden state)
      │
      ▼
  LSTM Decoder (2 layers, hidden_dim=128)
      │
      ▼
  Reconstructed sequence (T timesteps x n features)

  Anomaly score = mean(||x_t - x̂_t||²) over the sequence window
```

**Configuration**:

```yaml
lstm_autoencoder:
  sequence_length: 60       # 60 timesteps input window
  hidden_dim: 128
  num_layers: 2
  dropout: 0.2
  learning_rate: 0.001
  batch_size: 256
  epochs: 50
  early_stopping_patience: 5

  # Activation criteria (when to use LSTM vs simpler methods)
  activation_rules:
    min_history_days: 14
    min_seasonality_strength: 0.3
    max_metrics_per_group: 20
```

#### 3.5.2 Temporal Convolutional Network (TCN)

TCN alternative for sequences where parallelizable training is important (faster than LSTM). Uses dilated causal convolutions to capture temporal patterns at multiple scales.

```
Dilated Convolution:
  Layer 1: dilation = 1  → captures patterns at 1-step scale
  Layer 2: dilation = 2  → captures patterns at 2-step scale
  Layer 3: dilation = 4  → captures patterns at 4-step scale
  Layer 4: dilation = 8  → captures patterns at 8-step scale

  Receptive field = 2^(num_layers) * (kernel_size - 1) + 1
  With 8 layers and kernel_size=3: receptive field = 513 timesteps
```

### 3.6 Ensemble Scoring (Tier 5)

For critical metrics linked to SLOs, an ensemble combines multiple detectors to maximize precision and recall.

```
ensemble_score = Σ(w_i * score_i) / Σ(w_i)

Where:
  w_i = weight for detector i, learned from feedback
  score_i = normalized anomaly score from detector i

Initial weights (before feedback):
  Statistical:   w = 0.15
  STL:           w = 0.25
  Isolation Forest: w = 0.25
  Autoencoder:   w = 0.20
  LSTM:          w = 0.15

Ensemble anomaly: ensemble_score > threshold (default 0.65)
```

### 3.7 Multi-Variate Anomaly Detection

Single-metric anomaly detection misses failures that manifest as subtle correlated shifts across multiple metrics (e.g., CPU normal, memory normal, but the combination of both at those levels is abnormal).

**Approach**: Group correlated metrics and feed them as feature vectors to Isolation Forest or Autoencoder models.

**Automatic metric grouping**:

```python
def discover_metric_groups(
    metric_names: list[str],
    correlation_matrix: np.ndarray,
    threshold: float = 0.6,
) -> list[list[str]]:
    """
    Discover groups of correlated metrics using hierarchical clustering
    on the correlation matrix. Each group is modeled jointly for
    multi-variate anomaly detection.
    """
    from scipy.cluster.hierarchy import linkage, fcluster

    # Convert correlation to distance
    distance_matrix = 1 - np.abs(correlation_matrix)

    # Hierarchical clustering
    condensed = distance_matrix[np.triu_indices_from(distance_matrix, k=1)]
    Z = linkage(condensed, method="complete")
    clusters = fcluster(Z, t=1 - threshold, criterion="distance")

    groups = {}
    for metric, cluster_id in zip(metric_names, clusters):
        groups.setdefault(cluster_id, []).append(metric)

    return [g for g in groups.values() if len(g) > 1]
```

### 3.8 Anomaly Scoring and Confidence

Every anomaly detection produces a standardized `AnomalyEvent`:

```python
@dataclass
class AnomalyEvent:
    # Identity
    tenant_id: str
    anomaly_id: str               # UUID
    timestamp: datetime

    # Source
    metric_name: str
    resource_id: str              # host, service, container, etc.
    dimensions: dict[str, str]    # metric labels/tags

    # Detection
    score: float                  # 0.0 - 1.0 (normalized severity)
    confidence: float             # 0.0 - 1.0 (confidence in detection)
    severity: str                 # "info", "warning", "critical"
    direction: str                # "above", "below", "both"

    # Context
    observed_value: float
    expected_value: float
    expected_range: tuple[float, float]  # (lower, upper)
    baseline_window: str          # "7d", "30d", etc.

    # Detection details
    detection_method: str         # "modified_z_score", "stl", "isolation_forest", etc.
    detection_tier: int           # 1-5
    contributing_metrics: list[str]  # for multi-variate

    # Lifecycle
    state: str                    # "open", "acknowledged", "resolved", "suppressed"
    first_seen: datetime
    last_seen: datetime
    occurrence_count: int

    # Feedback
    user_feedback: str | None     # "true_positive", "false_positive", None
    feedback_timestamp: datetime | None
```

**Severity mapping**:

```
score < 0.3  → severity = "info"       (subtle deviation)
score 0.3-0.7 → severity = "warning"   (notable anomaly)
score > 0.7  → severity = "critical"   (severe deviation)

Confidence adjustment:
  if confidence < 0.5: downgrade severity by one level
  if confidence < 0.3: suppress anomaly (do not alert)
```

### 3.9 Automatic Baseline Learning

RayOlly learns baselines automatically without any user configuration. The baseline learning process adapts to the data characteristics:

```
┌─────────────────────────────────────────────────────────────────┐
│                  Baseline Learning Timeline                       │
│                                                                   │
│  T+0h: Data ingestion begins                                     │
│  ├─ Tier 1 (statistical) active immediately with 1h rolling      │
│  │  window — catches extreme outliers only                       │
│  │                                                                │
│  T+4h: Minimum baseline for Tier 1                               │
│  ├─ Modified Z-score with 4h baseline — moderate sensitivity     │
│  │                                                                │
│  T+24h: Seasonality detection begins                             │
│  ├─ Check for intra-day patterns using autocorrelation           │
│  ├─ If seasonality detected: activate Tier 2 (STL)              │
│  │                                                                │
│  T+7d: Full weekly baseline                                      │
│  ├─ Day-of-week patterns now modeled                             │
│  ├─ Activate Tier 3 (Isolation Forest, LOF)                     │
│  ├─ Multi-variate groups discovered                              │
│  │                                                                │
│  T+14d: Stable baseline                                          │
│  ├─ Confidence levels reach operating threshold                  │
│  ├─ Activate Tier 4 (LSTM) for high-value metrics               │
│  ├─ Enable ensemble (Tier 5) for SLO-linked metrics             │
│  │                                                                │
│  T+30d: Full maturity                                            │
│  ├─ Monthly patterns captured                                    │
│  └─ Model accuracy stabilized                                    │
└─────────────────────────────────────────────────────────────────┘
```

### 3.10 Configuration

```yaml
# anomaly_detection.yaml — per-tenant configuration
anomaly_detection:
  # Global sensitivity (overridable per metric)
  sensitivity: "medium"   # low | medium | high

  # Training windows
  training:
    default_window: "7d"
    max_window: "90d"
    min_data_points: 100
    retrain_interval: "6h"

  # Exclusion rules
  exclusions:
    - metric_pattern: "test.*"
      reason: "Test environment metrics"
    - metric_pattern: "*.debug.*"
      reason: "Debug metrics excluded"
    - time_windows:
        - cron: "0 2 * * SUN"    # Sundays 2am
          duration: "4h"
          reason: "Weekly maintenance window"

  # Per-metric overrides
  overrides:
    - metric: "api.latency.p99"
      sensitivity: "high"
      detection_tiers: [1, 2, 3, 5]  # include ensemble
      training_window: "30d"
    - metric: "batch.job.duration"
      sensitivity: "low"
      seasonality_periods: ["24h", "7d", "30d"]

  # Suppression rules
  suppression:
    deduplicate_window: "15m"       # same anomaly within 15m = single event
    min_duration: "5m"              # anomaly must persist 5m to alert
    max_anomalies_per_metric: 10    # suppress after 10 open anomalies

  # Multi-variate settings
  multivariate:
    auto_grouping: true
    correlation_threshold: 0.6
    max_group_size: 20
    grouping_refresh_interval: "24h"
```

### 3.11 Example: Latency Anomaly vs Normal Traffic Spike

**Scenario**: An e-commerce service sees `api.checkout.latency.p99` jump from 200ms to 800ms at 10am on a Monday.

```
Step 1: Tier 1 (Statistical)
  Modified Z-score: M = 0.6745 * (800 - 195) / 22.3 = 18.3
  → Score = 1.0, clearly anomalous by statistics alone.

Step 2: Tier 2 (Seasonal)
  STL decomposition shows Monday 10am has a seasonal component:
    seasonal_value = +50ms (normal Monday morning increase)
    trend_value = 200ms (stable trend)
    expected = 250ms
    residual = 800 - 250 = 550ms
    → Residual is still severely anomalous (|M| = 12.8)
    → Confirmed: NOT a normal traffic spike.

Step 3: Context enrichment
  Concurrent signals:
    - error_rate increased 0.1% → 2.3% (anomaly score 0.92)
    - database.query.duration increased 50ms → 400ms (anomaly score 0.95)
    - cpu_usage stable at 45% (no anomaly)

  Multi-variate grouping confirms correlated anomaly across
  [latency, error_rate, db_query_duration].

Step 4: Final anomaly event
  AnomalyEvent(
    score=0.97,
    confidence=0.94,
    severity="critical",
    direction="above",
    observed_value=800,
    expected_value=250,
    expected_range=(180, 320),
    contributing_metrics=["error_rate", "database.query.duration"],
    detection_method="ensemble",
  )
```

**Counter-example**: Same metric jumps from 200ms to 280ms on Monday at 10am.

```
Tier 2 (Seasonal):
  seasonal_value = +50ms → expected = 250ms
  residual = 280 - 250 = 30ms
  |M| = 0.91 → below threshold
  → NOT anomalous. Normal seasonal traffic increase.
```

---

## 4. Predictive Alerting & Forecasting

### 4.1 Forecasting Engine Architecture

```
┌───────────────────────────────────────────────────────────────────┐
│                     Forecasting Engine                             │
│                                                                   │
│  ┌─────────────────┐   ┌─────────────────┐   ┌───────────────┐  │
│  │    Prophet /     │   │  NeuralProphet   │   │   Temporal    │  │
│  │   StatsForecast  │   │  (PyTorch-based) │   │   Fusion     │  │
│  │                  │   │                  │   │  Transformer  │  │
│  │  - Additive      │   │  - AR-Net        │   │              │  │
│  │  - Multiplicative│   │  - Lagged        │   │  - Attention │  │
│  │  - Logistic      │   │    regressors    │   │  - Covariates│  │
│  │    growth        │   │  - Neural        │   │  - Long      │  │
│  │                  │   │    seasonality   │   │    horizon   │  │
│  └────────┬────────┘   └────────┬────────┘   └──────┬───────┘  │
│           │                      │                    │          │
│           └──────────────────────┼────────────────────┘          │
│                                  │                               │
│                      ┌───────────▼──────────┐                   │
│                      │  Model Selection /    │                   │
│                      │  Auto-Selection       │                   │
│                      │  (based on data       │                   │
│                      │   characteristics)    │                   │
│                      └───────────┬──────────┘                   │
│                                  │                               │
│                      ┌───────────▼──────────┐                   │
│                      │  Forecast Output      │                   │
│                      │  - Point forecast     │                   │
│                      │  - Confidence bands   │                   │
│                      │  - Prediction interval│                   │
│                      └──────────────────────┘                   │
└───────────────────────────────────────────────────────────────────┘
```

### 4.2 Forecasting Methods

#### 4.2.1 Prophet / StatsForecast

Default forecasting method for metrics with clear seasonality and trend. Uses additive or multiplicative decomposition with configurable changepoints.

```python
from prophet import Prophet

def forecast_metric(
    history: pd.DataFrame,      # columns: ds (timestamp), y (value)
    horizon: str = "24h",
    changepoint_prior_scale: float = 0.05,
    seasonality_mode: str = "additive",
) -> pd.DataFrame:
    """
    Generate forecast with confidence intervals.

    Returns DataFrame with columns:
      ds, yhat (point forecast), yhat_lower (5th percentile), yhat_upper (95th percentile)
    """
    model = Prophet(
        changepoint_prior_scale=changepoint_prior_scale,
        seasonality_mode=seasonality_mode,
        daily_seasonality=True,
        weekly_seasonality=True,
        yearly_seasonality=False,  # observability data rarely has yearly patterns
        interval_width=0.90,
    )

    # Add custom seasonality for operational patterns
    model.add_seasonality(
        name="business_hours",
        period=1,  # 1 day
        fourier_order=8,
    )

    model.fit(history)

    future = model.make_future_dataframe(
        periods=pd.Timedelta(horizon).total_seconds() // 60,
        freq="1min",
    )

    return model.predict(future)
```

#### 4.2.2 NeuralProphet

Neural network extension of Prophet. Used for metrics where traditional Prophet underfits — captures non-linear trends and complex interaction patterns via auto-regressive neural networks.

```python
from neuralprophet import NeuralProphet

def neural_forecast(
    history: pd.DataFrame,
    horizon_steps: int = 1440,   # 24h at 1min resolution
    n_lags: int = 60,            # auto-regressive lags
) -> pd.DataFrame:
    model = NeuralProphet(
        n_lags=n_lags,
        n_forecasts=horizon_steps,
        changepoints_range=0.9,
        learning_rate=0.01,
        epochs=100,
        batch_size=256,
        ar_layers=[64, 32],
    )

    model.fit(history, freq="1min")
    future = model.make_future_dataframe(history, periods=horizon_steps)
    return model.predict(future)
```

#### 4.2.3 Temporal Fusion Transformer (TFT)

For multi-step, multi-variate forecasting with known covariates (e.g., predicting latency given planned deployment schedule, traffic forecast, and infrastructure state).

```
TFT architecture:
  Known inputs (future-known): time features, planned events
  Observed inputs (past-only): metric values, concurrent signals
  Static inputs: service tier, region, resource type
      │
  Variable Selection Network (attention-based feature selection)
      │
  LSTM Encoder → Interpretable Multi-Head Attention → LSTM Decoder
      │
  Quantile outputs: [q10, q25, q50, q75, q90]
```

### 4.3 Capacity Forecasting

**Use cases**: Predict when disk, memory, CPU, or connection pools will be exhausted.

```python
@dataclass
class CapacityForecast:
    resource: str              # "disk", "memory", "cpu", "connections"
    resource_id: str           # host/container identifier
    current_usage: float       # current value
    capacity_limit: float      # maximum capacity
    current_utilization: float # percentage

    # Forecast
    exhaustion_timestamp: datetime | None   # when resource will be full
    time_to_exhaustion: timedelta | None    # hours/days until full
    forecast_confidence: float              # 0-1

    # Trend
    daily_growth_rate: float   # average daily increase
    weekly_growth_rate: float  # average weekly increase

    # Recommendations
    recommended_action: str    # "scale_up", "cleanup", "investigate", "no_action"
    urgency: str               # "immediate", "this_week", "this_month", "no_action"

def forecast_capacity(
    usage_history: pd.Series,
    capacity_limit: float,
    forecast_horizon: str = "30d",
) -> CapacityForecast:
    """
    Forecast when a resource will reach capacity.

    Uses linear regression for simple trends, Prophet for seasonal resources.
    Alerts generated at: 70%, 80%, 90% thresholds AND predicted exhaustion.
    """
    # Detect if usage has seasonality (e.g., disk cleanup cycles)
    has_seasonality = detect_seasonality(usage_history)

    if has_seasonality:
        forecast = prophet_forecast(usage_history, horizon=forecast_horizon)
    else:
        forecast = linear_extrapolation(usage_history, horizon=forecast_horizon)

    # Find first timestamp where forecast exceeds capacity
    breach_points = forecast[forecast["yhat"] >= capacity_limit]

    if len(breach_points) > 0:
        exhaustion_time = breach_points.iloc[0]["ds"]
        return CapacityForecast(
            exhaustion_timestamp=exhaustion_time,
            time_to_exhaustion=exhaustion_time - datetime.utcnow(),
            urgency=classify_urgency(exhaustion_time),
            # ... other fields
        )

    return CapacityForecast(
        exhaustion_timestamp=None,
        time_to_exhaustion=None,
        urgency="no_action",
        # ...
    )
```

### 4.4 SLO Burn Rate Forecasting

Predicts when an SLO error budget will be exhausted based on current and forecasted burn rate.

```
Error budget remaining = 1 - (error_budget_consumed / total_error_budget)

Burn rate = (error_budget_consumed_in_window / window_size) / (total_error_budget / slo_period)

Time to SLO breach = remaining_budget / current_burn_rate

Example:
  SLO: 99.9% availability over 30 days
  Total error budget: 0.1% * 30d = 43.2 minutes of downtime
  Consumed so far: 20 minutes (in 15 days)
  Current burn rate: (20/15d) / (43.2/30d) = 0.926x (under budget)

  But if burn rate accelerates to 2x:
  Remaining budget: 23.2 minutes
  At 2x burn: exhaustion in 23.2 / (2 * 1.44 min/day) = 8.06 days
  Alert: "SLO will breach in ~8 days at current error rate"
```

**Forecasted burn rate** uses the forecasting engine to predict future error rates, not just extrapolate current rates linearly.

### 4.5 Forecast Configuration

```yaml
forecasting:
  # Default forecast settings
  default_horizon: "24h"
  max_horizon: "90d"
  confidence_level: 0.90        # 90% prediction interval

  # Model auto-selection
  model_selection:
    strategy: "auto"            # auto | prophet | neural_prophet | tft
    evaluation_metric: "mape"   # mean absolute percentage error
    cross_validation_folds: 3

  # Capacity forecasting
  capacity:
    enabled: true
    resources: ["disk", "memory", "cpu", "connections"]
    alert_thresholds: [70, 80, 90]  # percentage utilization
    exhaustion_alert_horizon: "7d"   # alert if exhaustion within 7 days

  # SLO burn rate
  slo_forecasting:
    enabled: true
    update_interval: "5m"
    alert_horizons: ["1h", "4h", "24h", "7d"]

  # Retraining
  retrain_interval: "24h"
  min_training_data: "7d"
```

---

## 5. Pattern Mining & Log Analytics

### 5.1 Automatic Log Pattern Extraction

#### 5.1.1 Drain Algorithm

Drain is the primary log parsing algorithm. It extracts templates from unstructured log messages in a single pass using a fixed-depth parse tree.

```
Input log:  "Connection to database db-prod-1 failed after 3 retries"
Input log:  "Connection to database db-prod-2 failed after 5 retries"
Input log:  "Connection to database db-staging failed after 1 retries"

Extracted template: "Connection to database <*> failed after <*> retries"
Parameters:         [("db-prod-1", "db-prod-2", "db-staging"), ("3", "5", "1")]
```

**Drain parse tree structure**:

```
Root
├── Length 9 (9 tokens)
│   ├── "Connection" (first token)
│   │   └── Cluster: "Connection to database <*> failed after <*> retries"
│   └── "Server" (first token)
│       └── Cluster: "Server <*> started on port <*>"
├── Length 5 (5 tokens)
│   ├── "Error" (first token)
│   │   └── Cluster: "Error processing request <*>"
│   ...
```

**Configuration**:

```python
class DrainConfig:
    depth: int = 4                  # parse tree depth
    similarity_threshold: float = 0.4  # cluster merge threshold
    max_children: int = 100         # max children per tree node
    max_clusters: int = 10000       # max templates per tenant

    # Preprocessing
    masking_rules: list = [
        (r"\d+\.\d+\.\d+\.\d+", "<IP>"),       # IP addresses
        (r"[0-9a-f]{8}-[0-9a-f]{4}-", "<UUID>"),  # UUIDs
        (r"\d{4}-\d{2}-\d{2}", "<DATE>"),        # dates
        (r"\d+", "<NUM>"),                        # numbers (last, catch-all)
    ]
```

#### 5.1.2 Spell Algorithm (Streaming)

Spell (Streaming Parser for Event Logs) is used as a secondary parser for real-time streaming parsing with lower memory footprint. It uses a longest common subsequence (LCS) approach.

```
LCS("Connection to db-prod-1 failed", "Connection to db-prod-2 failed")
  = "Connection to * failed"
```

### 5.2 Log Clustering

After template extraction, logs are clustered by template similarity to group related log patterns.

```
┌───────────────────────────────────────────────────────┐
│              Log Clustering Pipeline                    │
│                                                        │
│  Raw Logs → Drain Parser → Template Extraction         │
│       │                         │                      │
│       │                    Template IDs                 │
│       │                         │                      │
│       │              ┌──────────▼──────────┐           │
│       │              │  Template Embedding  │           │
│       │              │  (TF-IDF or BERT)   │           │
│       │              └──────────┬──────────┘           │
│       │                         │                      │
│       │              ┌──────────▼──────────┐           │
│       │              │  Hierarchical        │           │
│       │              │  Clustering          │           │
│       │              │  (HDBSCAN)          │           │
│       │              └──────────┬──────────┘           │
│       │                         │                      │
│       │              ┌──────────▼──────────┐           │
│       │              │  Cluster Labels      │           │
│       │              │  "Database Errors"   │           │
│       │              │  "Auth Failures"     │           │
│       │              │  "Health Checks"     │           │
│       │              └─────────────────────┘           │
└───────────────────────────────────────────────────────┘
```

### 5.3 Pattern Frequency Analysis

Track how often each log pattern occurs over time. Sudden changes in pattern frequency are strong anomaly signals.

```python
@dataclass
class PatternStats:
    template_id: str
    template: str

    # Current window
    count_current: int
    rate_per_minute: float

    # Baseline
    count_baseline_avg: float
    rate_baseline_avg: float

    # Anomaly
    frequency_anomaly_score: float   # deviation from baseline frequency
    is_frequency_anomaly: bool

    # Trend
    trend: str    # "increasing", "decreasing", "stable", "new", "disappeared"

    # First/last seen
    first_seen: datetime
    last_seen: datetime
    total_occurrences: int
```

### 5.4 New Pattern Detection

Detecting log lines that match no known template is a critical early warning signal. A "never-before-seen" pattern often indicates a new error condition, a deployment introducing new code paths, or unexpected system behavior.

```
New pattern detection flow:

  Incoming log line
       │
       ▼
  Match against Drain parse tree
       │
  ┌────┴────┐
  │ Match?  │
  └────┬────┘
   Yes │    No
       │     │
       ▼     ▼
  Increment  Create new template
  counter    ├─ Flag as "new_pattern"
             ├─ Emit NewPatternEvent
             ├─ If rate > threshold → anomaly alert
             └─ Auto-categorize via LLM (async)
```

**New pattern alert logic**:

```yaml
new_pattern_detection:
  enabled: true
  alert_on_new_pattern: true
  min_occurrences_for_alert: 5    # must appear 5+ times to alert
  time_window: "15m"               # within 15 minutes
  ignore_patterns:
    - "DEBUG"
    - "TRACE"
  severity: "warning"
```

### 5.5 Automatic Field Extraction

Extract structured fields from unstructured log lines without user configuration.

```
Input:  "2026-03-19 10:23:45 ERROR [api-gateway] Request POST /api/v1/checkout
         from 192.168.1.100 failed with status=500 duration=2345ms user_id=u-12345"

Extracted fields:
  timestamp: "2026-03-19 10:23:45"
  level: "ERROR"
  service: "api-gateway"
  method: "POST"
  path: "/api/v1/checkout"
  client_ip: "192.168.1.100"
  status: 500
  duration_ms: 2345
  user_id: "u-12345"
```

**Extraction methods** (applied in order):

1. **Regex-based**: Known patterns (IP, UUID, timestamps, HTTP methods)
2. **Key-value parser**: `key=value` and `key: value` patterns
3. **JSON embedded**: Detect and parse embedded JSON objects
4. **ML-based (NER)**: Named entity recognition for remaining fields (async, batch)

### 5.6 Event Correlation

Link related events across services, time windows, and telemetry types.

```
Correlation strategies:
  1. Trace-based:  Events sharing the same trace_id
  2. Time-based:   Events within configurable time window (±5m default)
  3. Resource-based: Events from the same host, pod, or service
  4. Pattern-based: Events with similar error patterns
  5. Causal:        Events with Granger-causal relationships (see Section 6)

Correlation output:
  CorrelatedEventGroup(
    group_id="corr-abc123",
    events=[event_1, event_2, event_3],
    correlation_type="trace_and_time",
    confidence=0.92,
    root_event=event_1,  # earliest event, likely cause
  )
```

---

## 6. Root Cause Analysis Engine

### 6.1 Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     Root Cause Analysis Engine                           │
│                                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  ┌───────────┐  │
│  │  Topology    │  │   Causal     │  │  Correlation  │  │  Change   │  │
│  │  Walker      │  │   Inference  │  │  Analyzer     │  │  Detector │  │
│  │             │  │              │  │               │  │           │  │
│  │ Walk service│  │ Granger test │  │ Cross-signal  │  │ Deploys,  │  │
│  │ dependency  │  │ Transfer     │  │ correlation   │  │ configs,  │  │
│  │ graph to    │  │ entropy      │  │ across metrics│  │ scaling   │  │
│  │ find origin │  │              │  │ logs, traces  │  │ events    │  │
│  └──────┬──────┘  └──────┬───────┘  └──────┬────────┘  └─────┬─────┘  │
│         │                │                  │                  │        │
│         └────────────────┼──────────────────┼──────────────────┘        │
│                          │                  │                           │
│                 ┌────────▼──────────────────▼────────┐                  │
│                 │        RCA Scoring Engine           │                  │
│                 │                                     │                  │
│                 │  Combine evidence from all sources  │                  │
│                 │  Rank candidate root causes         │                  │
│                 │  Produce confidence scores          │                  │
│                 └────────────────┬───────────────────┘                  │
│                                  │                                      │
│                 ┌────────────────▼───────────────────┐                  │
│                 │      RCA Report Generator           │                  │
│                 │  - Timeline of events               │                  │
│                 │  - Ranked root causes               │                  │
│                 │  - Evidence chain                   │                  │
│                 │  - Suggested remediation            │                  │
│                 └────────────────────────────────────┘                  │
└─────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Topology-Aware RCA

Traverse the service dependency graph to find upstream causes of downstream symptoms.

```python
@dataclass
class ServiceNode:
    service_name: str
    anomaly_score: float
    anomaly_start_time: datetime
    anomalous_metrics: list[str]
    dependencies: list[str]      # upstream services this depends on

def topology_walk_rca(
    affected_service: str,
    service_graph: dict[str, ServiceNode],
    time_window: timedelta = timedelta(minutes=30),
) -> list[tuple[str, float]]:
    """
    Walk the service dependency graph backwards from the affected service.
    Find upstream services with anomalies that started BEFORE the downstream
    anomaly — these are root cause candidates.

    Returns: List of (service_name, rca_score) sorted by likelihood.
    """
    affected = service_graph[affected_service]
    candidates = []

    def walk(service_name: str, depth: int, path: list[str]):
        if depth > 10 or service_name in path:
            return  # prevent cycles and excessive depth

        node = service_graph.get(service_name)
        if not node or node.anomaly_score < 0.3:
            return

        # Upstream anomaly must start before downstream anomaly
        time_delta = affected.anomaly_start_time - node.anomaly_start_time
        if timedelta(0) < time_delta < time_window:
            # Score based on: anomaly severity, temporal precedence, graph distance
            temporal_score = 1.0 - (time_delta.total_seconds() / time_window.total_seconds())
            distance_score = 1.0 / (depth + 1)
            rca_score = node.anomaly_score * 0.4 + temporal_score * 0.4 + distance_score * 0.2
            candidates.append((service_name, rca_score, path + [service_name]))

        for dep in node.dependencies:
            walk(dep, depth + 1, path + [service_name])

    for dep in affected.dependencies:
        walk(dep, depth=1, path=[affected_service])

    return sorted(candidates, key=lambda x: x[1], reverse=True)
```

### 6.3 Causal Inference

#### 6.3.1 Granger Causality

Tests whether past values of time series X improve the prediction of time series Y beyond what past values of Y alone provide.

```
Model 1 (restricted):  Y_t = Σ(α_i * Y_{t-i}) + ε_1
Model 2 (unrestricted): Y_t = Σ(α_i * Y_{t-i}) + Σ(β_j * X_{t-j}) + ε_2

F-statistic: F = ((RSS_1 - RSS_2) / p) / (RSS_2 / (T - 2p - 1))

Where:
  RSS = residual sum of squares
  p = number of lags
  T = number of observations

If F > F_critical (p-value < 0.05):
  → X Granger-causes Y (X contains predictive information for Y)
```

**Application**: If `database.query_duration` Granger-causes `api.latency`, then database slowdowns are a leading indicator (potential root cause) for API latency issues.

#### 6.3.2 Transfer Entropy

Non-linear generalization of Granger causality. Measures the amount of information transferred from X to Y.

```
TE(X→Y) = Σ p(y_{t+1}, y_t, x_t) * log(p(y_{t+1} | y_t, x_t) / p(y_{t+1} | y_t))

If TE(X→Y) >> TE(Y→X):
  → X causally influences Y more than Y influences X
  → X is a root cause candidate for Y
```

### 6.4 Change Correlation

Correlate anomalies with change events (deployments, configuration changes, scaling events, infrastructure changes).

```python
@dataclass
class ChangeEvent:
    timestamp: datetime
    change_type: str      # "deployment", "config_change", "scaling", "infra"
    service: str
    description: str
    diff_summary: str | None   # what changed
    author: str

def correlate_with_changes(
    anomaly: AnomalyEvent,
    changes: list[ChangeEvent],
    lookback: timedelta = timedelta(hours=2),
) -> list[tuple[ChangeEvent, float]]:
    """
    Find change events that occurred shortly before an anomaly.
    Score by temporal proximity and service relationship.
    """
    correlated = []
    for change in changes:
        time_delta = anomaly.timestamp - change.timestamp

        if timedelta(0) < time_delta < lookback:
            # Closer in time = higher correlation score
            temporal_score = 1.0 - (time_delta.total_seconds() / lookback.total_seconds())

            # Same service = higher score
            service_score = 1.0 if change.service == anomaly.resource_id else 0.5

            # Deployment changes more likely to cause issues
            type_weights = {
                "deployment": 1.0,
                "config_change": 0.9,
                "scaling": 0.6,
                "infra": 0.7,
            }
            type_score = type_weights.get(change.change_type, 0.5)

            score = temporal_score * 0.4 + service_score * 0.3 + type_score * 0.3
            correlated.append((change, score))

    return sorted(correlated, key=lambda x: x[1], reverse=True)
```

### 6.5 Historical Incident Pattern Matching

Match current incident patterns against previously resolved incidents to suggest root causes.

```python
@dataclass
class IncidentPattern:
    pattern_id: str
    symptoms: list[str]        # anomalous metrics/services
    root_cause: str            # confirmed root cause
    resolution: str            # how it was resolved
    occurrence_count: int      # how many times this pattern occurred
    avg_ttd: timedelta         # average time to detect
    avg_ttr: timedelta         # average time to resolve

def match_historical_patterns(
    current_symptoms: list[str],
    historical_patterns: list[IncidentPattern],
    min_similarity: float = 0.6,
) -> list[tuple[IncidentPattern, float]]:
    """
    Use Jaccard similarity between current symptoms and historical incident
    symptoms to find matching past incidents.
    """
    matches = []
    current_set = set(current_symptoms)

    for pattern in historical_patterns:
        pattern_set = set(pattern.symptoms)

        jaccard = len(current_set & pattern_set) / len(current_set | pattern_set)

        if jaccard >= min_similarity:
            # Boost score by occurrence count (more frequent patterns are more likely)
            frequency_boost = min(pattern.occurrence_count / 10.0, 1.0)
            score = jaccard * 0.7 + frequency_boost * 0.3
            matches.append((pattern, score))

    return sorted(matches, key=lambda x: x[1], reverse=True)
```

### 6.6 RCA Output and Confidence Scoring

```python
@dataclass
class RootCauseCandidate:
    rank: int
    cause: str                    # description of root cause
    confidence: float             # 0.0 - 1.0
    evidence: list[str]           # supporting evidence
    source_signals: list[str]     # contributing analysis methods
    related_changes: list[ChangeEvent]
    historical_match: IncidentPattern | None
    suggested_remediation: str

@dataclass
class RCAReport:
    incident_id: str
    affected_services: list[str]
    impact_summary: str
    timeline: list[tuple[datetime, str]]   # chronological event timeline
    root_causes: list[RootCauseCandidate]  # ranked by confidence
    correlation_graph: dict                 # service → anomaly relationships
    generated_at: datetime

    # Metadata
    analysis_duration_ms: int
    methods_used: list[str]
    data_coverage: float           # 0-1, how much data was available for analysis
```

### 6.7 Example RCA Flow

```
INCIDENT: "Checkout API latency spiked to 5s (normal: 200ms)"

Timeline:
  T-15m  Deploy v2.14.3 to payment-service (canary)
  T-12m  payment-service DB connection pool utilization → 95%
  T-10m  payment-service latency p99: 180ms → 2100ms
  T-8m   checkout-api latency p99: 200ms → 3500ms (depends on payment-service)
  T-6m   order-service error rate: 0.1% → 12% (depends on checkout-api)
  T-5m   Anomaly detected on checkout-api latency → RCA triggered
  T-0m   RCA report generated

RCA Analysis:
  1. Topology Walk:
     checkout-api ← payment-service ← payment-db
     payment-service anomaly started 2m before checkout-api → upstream cause

  2. Change Correlation:
     Deploy v2.14.3 to payment-service at T-15m
     Score: 0.92 (temporal proximity + same service + deployment type)

  3. Causal Inference:
     Granger test: payment-db.connection_pool → payment-service.latency (p < 0.001)

  4. Historical Match:
     Pattern "payment-service deploy + DB pool exhaustion" matched 3 prior incidents
     Prior resolution: "Rollback deployment, fix connection leak in v2.14.x"

RCA Report:
  Root Cause #1 (confidence: 0.94):
    "Deployment v2.14.3 to payment-service introduced a DB connection leak,
     exhausting the connection pool and causing cascading latency to downstream
     services."
    Evidence:
      - Deploy v2.14.3 occurred 15 minutes before incident
      - DB connection pool reached 95% (anomaly score 0.98)
      - Payment-service latency anomaly preceded checkout-api by 2 minutes
      - Historical pattern matches 3 prior incidents with same symptoms
    Suggested remediation:
      "Rollback payment-service to v2.14.2. Investigate connection pool handling
       in v2.14.3 diff."
```

---

## 7. Metric Correlation

### 7.1 Automatic Correlation Discovery

Continuously compute pairwise correlations between metrics to discover relationships without manual configuration.

```python
def compute_correlation_matrix(
    metrics: dict[str, np.ndarray],   # metric_name → time series values
    method: str = "pearson",           # pearson, spearman, kendall
    min_correlation: float = 0.6,
    lag_range: range = range(-10, 11),  # check lags from -10 to +10 periods
) -> list[MetricCorrelation]:
    """
    Compute pairwise correlation with lag detection.
    Returns only correlations above the significance threshold.
    """
    results = []
    metric_names = list(metrics.keys())

    for i, name_a in enumerate(metric_names):
        for name_b in metric_names[i+1:]:
            best_corr = 0
            best_lag = 0

            for lag in lag_range:
                if lag >= 0:
                    a = metrics[name_a][lag:]
                    b = metrics[name_b][:len(a)]
                else:
                    b = metrics[name_b][-lag:]
                    a = metrics[name_a][:len(b)]

                if len(a) < 30:
                    continue

                corr, p_value = scipy.stats.pearsonr(a, b)

                if abs(corr) > abs(best_corr) and p_value < 0.01:
                    best_corr = corr
                    best_lag = lag

            if abs(best_corr) >= min_correlation:
                results.append(MetricCorrelation(
                    metric_a=name_a,
                    metric_b=name_b,
                    correlation=best_corr,
                    lag=best_lag,
                    p_value=p_value,
                    relationship="lead" if best_lag > 0 else "lag" if best_lag < 0 else "synchronous",
                ))

    return results
```

### 7.2 Lead/Lag Indicator Detection

Identifies metrics that consistently lead or lag other metrics — critical for proactive alerting.

```
Example lead/lag relationships:

  queue_depth (leads by 5m) → processing_latency → error_rate (lags by 2m)

  Meaning: Queue depth increases predict latency increases 5 minutes later,
           which in turn predicts error rate increases 2 minutes after that.

  Actionable: Alert on queue_depth anomaly to prevent errors 7 minutes early.
```

### 7.3 Cross-Service Correlation

Discover correlations between metrics from different services that share no explicit dependency in the service topology. These often reveal hidden dependencies (shared infrastructure, resource contention, external API dependencies).

```yaml
# Example discovered cross-service correlations
cross_service_correlations:
  - service_a: "user-service"
    metric_a: "latency_p99"
    service_b: "search-service"
    metric_b: "latency_p99"
    correlation: 0.87
    lag: 0
    explanation: "Both services share the same Redis cluster"

  - service_a: "payment-service"
    metric_a: "external_api_duration"
    service_b: "notification-service"
    metric_b: "external_api_duration"
    correlation: 0.92
    lag: 0
    explanation: "Both depend on same third-party email API"
```

### 7.4 Statistical Significance Testing

All correlations are validated for statistical significance to prevent spurious correlations from polluting the system.

```
For each correlation pair:
  1. Pearson/Spearman correlation coefficient (r)
  2. p-value must be < 0.01 (99% confidence)
  3. Minimum sample size: 100 data points
  4. Bonferroni correction for multiple comparisons:
     adjusted_alpha = 0.01 / (n_metrics * (n_metrics - 1) / 2)
  5. Effect size check: |r| >= 0.6 (medium-to-large effect)
  6. Stationarity check: both series must pass ADF test
```

---

## 8. Model Management

### 8.1 Model Registry

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Model Registry                                │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Model Entry                                                │    │
│  │                                                             │    │
│  │  model_id:      "anomaly-iso-forest-tenant123-v7"          │    │
│  │  model_type:    "isolation_forest"                          │    │
│  │  tenant_id:     "tenant123"                                │    │
│  │  version:       7                                          │    │
│  │  status:        "active" | "staging" | "retired"           │    │
│  │  created_at:    2026-03-19T10:00:00Z                       │    │
│  │  training_data: { start: ..., end: ..., rows: 1.2M }      │    │
│  │  hyperparams:   { n_estimators: 200, max_samples: 4096 }  │    │
│  │  metrics:       { precision: 0.94, recall: 0.87, f1: 0.90 }│   │
│  │  artifact_path: "s3://rayolly-models/tenant123/iso-v7.onnx"│   │
│  │  format:        "onnx"                                     │    │
│  │  size_bytes:    4_200_000                                  │    │
│  │  serving_config: { max_batch: 256, timeout_ms: 50 }       │    │
│  │  lineage:       { parent_version: 6, data_hash: "abc..." } │   │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  Operations:                                                        │
│  - register(model) → version_id                                    │
│  - promote(model_id, "staging" → "active")                         │
│  - rollback(model_id, target_version)                              │
│  - list(tenant_id, model_type) → [models]                         │
│  - get_active(tenant_id, model_type) → model                      │
│  - delete(model_id, version)                                       │
│  - compare(version_a, version_b) → metric_diff                    │
└─────────────────────────────────────────────────────────────────────┘
```

### 8.2 Model Training Pipeline

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  Data    │    │  Feature │    │  Train   │    │ Evaluate │    │  Deploy  │
│  Extract │───▶│  Engine  │───▶│  Model   │───▶│  Model   │───▶│  Model   │
│          │    │          │    │          │    │          │    │          │
│ Query    │    │ Compute  │    │ Fit algo │    │ Holdout  │    │ ONNX     │
│ training │    │ features,│    │ on train │    │ test,    │    │ export,  │
│ data from│    │ normalize│    │ split    │    │ compare  │    │ register,│
│ storage  │    │ impute   │    │          │    │ to prev  │    │ promote  │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
     │               │               │               │               │
     ▼               ▼               ▼               ▼               ▼
  ClickHouse     Feature Store   Ray Workers     MLflow/Custom    ONNX Runtime
  + S3/Parquet   (Redis + S3)   (GPU if needed)  Model Registry   Serving
```

### 8.3 Model Evaluation and A/B Testing

```yaml
model_evaluation:
  # Holdout test evaluation
  test_split: 0.2           # 20% holdout
  metrics:
    - precision
    - recall
    - f1_score
    - false_positive_rate
    - detection_latency

  # Promotion criteria (new model must beat current)
  promotion_rules:
    min_f1_improvement: 0.01     # must improve F1 by at least 1%
    max_fpr_increase: 0.005      # FPR must not increase by more than 0.5%
    min_evaluation_samples: 1000

  # A/B testing (shadow mode)
  ab_testing:
    enabled: true
    shadow_traffic_pct: 10       # 10% of inference traffic goes to candidate
    min_duration: "24h"
    auto_promote: true           # auto-promote if criteria met
    rollback_on_regression: true
```

### 8.4 Model Serving Infrastructure

All models are exported to ONNX format for unified serving.

```python
# Model export to ONNX
import onnxruntime as ort

class ONNXModelServer:
    """
    Unified model serving via ONNX Runtime.
    Supports CPU and GPU inference with automatic batching.
    """

    def __init__(self, model_path: str, device: str = "cpu"):
        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"] if device == "gpu" else ["CPUExecutionProvider"]

        self.session = ort.InferenceSession(
            model_path,
            providers=providers,
            sess_options=self._get_session_options(),
        )

    def _get_session_options(self) -> ort.SessionOptions:
        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        opts.intra_op_num_threads = 4
        opts.inter_op_num_threads = 2
        opts.execution_mode = ort.ExecutionMode.ORT_PARALLEL
        return opts

    def predict(self, features: np.ndarray) -> np.ndarray:
        """Run inference. Input shape: (batch_size, n_features)."""
        input_name = self.session.get_inputs()[0].name
        return self.session.run(None, {input_name: features.astype(np.float32)})[0]
```

### 8.5 Model Retraining Triggers

```yaml
retraining_triggers:
  # Scheduled retraining
  schedule:
    default: "0 2 * * *"       # daily at 2am UTC
    heavy_models: "0 2 * * SUN"  # weekly on Sunday (LSTM, TFT)

  # Drift-based retraining
  drift_detection:
    method: "psi"                # Population Stability Index
    threshold: 0.2               # PSI > 0.2 → retrain
    check_interval: "1h"

    # Feature drift: distribution of input features changed
    feature_drift:
      method: "ks_test"          # Kolmogorov-Smirnov test
      p_value_threshold: 0.01

    # Concept drift: relationship between features and target changed
    concept_drift:
      method: "ddm"              # Drift Detection Method
      warning_level: 2.0         # standard deviations
      drift_level: 3.0

  # Performance-based retraining
  performance:
    fpr_threshold: 0.10          # retrain if FPR exceeds 10%
    min_feedback_samples: 50     # need 50+ feedback data points to evaluate
    evaluation_window: "7d"
```

### 8.6 Per-Tenant Model Isolation

```
┌───────────────────────────────────────────────────────────────┐
│                  Model Isolation Architecture                  │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐     │
│  │            Shared Base Models                        │     │
│  │                                                     │     │
│  │  - Pre-trained on anonymized, aggregated data       │     │
│  │  - Generic anomaly patterns (spike, drop, plateau)  │     │
│  │  - Used for cold-start (new tenants)                │     │
│  │  - Updated monthly from aggregated feedback         │     │
│  └───────────────────────┬─────────────────────────────┘     │
│                          │ fine-tune                          │
│           ┌──────────────┼──────────────┐                    │
│           ▼              ▼              ▼                     │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │
│  │  Tenant A    │ │  Tenant B    │ │  Tenant C    │        │
│  │  Models      │ │  Models      │ │  Models      │        │
│  │             │ │             │ │             │        │
│  │ Trained on  │ │ Trained on  │ │ Uses shared │        │
│  │ Tenant A    │ │ Tenant B    │ │ base model  │        │
│  │ data only   │ │ data only   │ │ (new tenant)│        │
│  │             │ │             │ │             │        │
│  │ Storage:    │ │ Storage:    │ │ Storage:    │        │
│  │ s3://models │ │ s3://models │ │ (none yet)  │        │
│  │ /tenant-a/  │ │ /tenant-b/  │ │             │        │
│  └──────────────┘ └──────────────┘ └──────────────┘        │
│                                                               │
│  Guarantees:                                                  │
│  - Training data never crosses tenant boundaries              │
│  - Model artifacts stored in tenant-scoped paths              │
│  - Inference isolated (no shared state between tenants)       │
│  - GPU time tracked and quota-enforced per tenant             │
└───────────────────────────────────────────────────────────────┘
```

### 8.7 GPU Resource Management

```yaml
gpu_resources:
  # Cluster-level GPU allocation
  cluster:
    total_gpus: 8                    # NVIDIA A100 or equivalent
    training_pool: 4                 # GPUs reserved for training
    inference_pool: 4                # GPUs reserved for inference

  # Per-tenant quotas
  tenant_tiers:
    free:
      gpu_training_hours_per_day: 0.5
      max_concurrent_training_jobs: 1
      inference: "cpu_only"
    professional:
      gpu_training_hours_per_day: 4
      max_concurrent_training_jobs: 2
      inference: "shared_gpu"
    enterprise:
      gpu_training_hours_per_day: 24
      max_concurrent_training_jobs: 8
      inference: "dedicated_gpu"

  # Scheduling
  training_scheduler:
    priority_queue: true
    preemption: true               # lower-tier jobs can be preempted
    max_job_duration: "4h"
    retry_on_oom: true
```

---

## 9. ML Pipeline Architecture

### 9.1 Training Pipeline

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       Training Pipeline (Batch)                          │
│                                                                         │
│  Trigger ─────────────────────────────────────────────────────────────  │
│  (Schedule / Drift / Manual)                                            │
│       │                                                                 │
│       ▼                                                                 │
│  ┌────────────────┐                                                     │
│  │ Job Scheduler   │  Ray / Celery worker pool                          │
│  │ (Priority Queue)│  GPU-aware scheduling                              │
│  └───────┬────────┘                                                     │
│          │                                                              │
│          ▼                                                              │
│  ┌────────────────┐    ┌──────────────────┐    ┌──────────────────┐    │
│  │ 1. Data Extract │───▶│ 2. Feature Eng.  │───▶│ 3. Train         │    │
│  │                │    │                  │    │                  │    │
│  │ - Query CH/S3  │    │ - Rolling stats  │    │ - Algorithm fit  │    │
│  │ - Filter tenant│    │ - Lag features   │    │ - Cross-validate │    │
│  │ - Time window  │    │ - Seasonality    │    │ - Hyperparameter │    │
│  │ - Downsample   │    │   indicators     │    │   tuning (Optuna)│    │
│  │   if needed    │    │ - Normalize      │    │                  │    │
│  └────────────────┘    │ - Cache to store │    └────────┬─────────┘    │
│                        └──────────────────┘             │              │
│                                                         ▼              │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐ │
│  │ 6. Deploy        │◀───│ 5. Register      │◀───│ 4. Evaluate      │ │
│  │                  │    │                  │    │                  │ │
│  │ - ONNX export   │    │ - Version model  │    │ - Holdout test   │ │
│  │ - Load to       │    │ - Store artifact │    │ - Compare prev   │ │
│  │   inference pool│    │ - Record lineage │    │ - Gate check     │ │
│  │ - Shadow/canary │    │ - Update registry│    │ - A/B decision   │ │
│  └──────────────────┘    └──────────────────┘    └──────────────────┘ │
│                                                                         │
│  Observable: Every step emits metrics and logs (dogfooded into RayOlly) │
└─────────────────────────────────────────────────────────────────────────┘
```

### 9.2 Inference Pipeline

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     Inference Pipeline (Real-Time)                       │
│                                                                         │
│  Ingestion Stream (NATS JetStream)                                      │
│       │                                                                 │
│       ▼                                                                 │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ Feature Extraction (Streaming)                                     │ │
│  │                                                                    │ │
│  │ For each incoming data point:                                      │ │
│  │ 1. Lookup online features from Feature Store (Redis)               │ │
│  │    - Rolling mean, std, median (pre-computed)                      │ │
│  │    - Seasonal component (pre-computed by training pipeline)        │ │
│  │    - Recent anomaly history                                        │ │
│  │ 2. Compute real-time features                                      │ │
│  │    - Delta from previous value                                     │ │
│  │    - Rate of change                                                │ │
│  │    - Multi-variate feature vector                                  │ │
│  └───────────────────────────┬────────────────────────────────────────┘ │
│                              │                                          │
│                              ▼                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ Model Scoring (ONNX Runtime)                                       │ │
│  │                                                                    │ │
│  │ - Batch incoming features (micro-batch: 50ms window)               │ │
│  │ - Run active model for tenant + metric type                        │ │
│  │ - Output: anomaly_score, confidence, expected_range                │ │
│  │ - Latency target: < 100ms P99                                     │ │
│  └───────────────────────────┬────────────────────────────────────────┘ │
│                              │                                          │
│                              ▼                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ Post-Processing                                                    │ │
│  │                                                                    │ │
│  │ - Apply threshold (per sensitivity config)                         │ │
│  │ - Deduplicate (same anomaly within window = update, not new)       │ │
│  │ - Enrich with context (service, topology, recent changes)          │ │
│  │ - Publish to:                                                      │ │
│  │   ├─ Anomaly topic (NATS) → Alerting Engine (PRD-09)             │ │
│  │   ├─ Agent inbox (NATS) → Agent Orchestrator (PRD-05)            │ │
│  │   ├─ Storage (ClickHouse) → Query Engine (PRD-03)                │ │
│  │   └─ WebSocket → Dashboard live updates (PRD-10)                 │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

### 9.3 Feature Store Design

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Feature Store                                │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    Online Store (Redis)                      │   │
│  │                                                             │   │
│  │  Key: tenant:{tenant_id}:metric:{metric_name}:features     │   │
│  │  Value: {                                                   │   │
│  │    "rolling_mean_1h": 245.3,                               │   │
│  │    "rolling_std_1h": 18.7,                                 │   │
│  │    "rolling_median_1h": 242.0,                             │   │
│  │    "rolling_mean_24h": 230.1,                              │   │
│  │    "rolling_std_24h": 35.2,                                │   │
│  │    "seasonal_component": 15.3,                             │   │
│  │    "trend_component": 228.5,                               │   │
│  │    "last_anomaly_score": 0.12,                             │   │
│  │    "anomaly_count_1h": 0,                                  │   │
│  │    "updated_at": "2026-03-19T10:30:00Z"                   │   │
│  │  }                                                         │   │
│  │                                                             │   │
│  │  TTL: 24 hours (refreshed by feature computation job)       │   │
│  │  Latency: < 1ms read                                       │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                   Offline Store (S3 + Parquet)              │   │
│  │                                                             │   │
│  │  Path: s3://rayolly-features/{tenant_id}/{date}/            │   │
│  │  Format: Parquet, partitioned by metric_name and date       │   │
│  │  Contents: Full feature history for training data           │   │
│  │  Retention: 90 days                                         │   │
│  │  Updated: Batch job every 6 hours                           │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  Feature computation pipeline:                                      │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────────┐          │
│  │ClickHouse│───▶│ Feature Eng  │───▶│ Write to Online  │          │
│  │ (raw data)│   │ (rolling     │    │ Store (Redis) +  │          │
│  │          │    │  aggregates, │    │ Offline Store    │          │
│  │          │    │  decompose)  │    │ (S3/Parquet)     │          │
│  └──────────┘    └──────────────┘    └──────────────────┘          │
└─────────────────────────────────────────────────────────────────────┘
```

### 9.4 Data Preprocessing Pipeline

```python
class PreprocessingPipeline:
    """
    Standard preprocessing for all ML models in the AI/ML Engine.
    Applied consistently in both training and inference paths.
    """

    steps = [
        # 1. Missing value handling
        "impute_missing",       # forward-fill for time series, median for features

        # 2. Outlier capping (for training data only)
        "cap_extreme_values",   # cap at 1st/99th percentile to prevent training distortion

        # 3. Normalization
        "normalize",            # StandardScaler (z-normalization) for most models
                                # MinMaxScaler for autoencoder inputs

        # 4. Stationarity transform
        "differencing",         # first-order differencing if ADF test fails

        # 5. Feature engineering
        "compute_rolling_stats",     # mean, std, min, max over [5m, 1h, 24h]
        "compute_rate_of_change",    # first derivative
        "compute_lag_features",      # values at t-1, t-5, t-60
        "compute_time_features",     # hour_of_day, day_of_week, is_weekend
        "compute_seasonal_residual", # value minus seasonal component
    ]
```

---

## 10. Real-Time Scoring

### 10.1 Streaming Inference Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│              Real-Time Scoring on Ingestion Hot Path                  │
│                                                                     │
│  Data Point Arrives (NATS)                                          │
│       │                                                             │
│       ├──────────────────────────────────────────────────────────┐  │
│       │ (async, non-blocking)                                    │  │
│       ▼                                                          │  │
│  ┌──────────────────────────────┐                                │  │
│  │ Scoring Worker Pool           │                                │  │
│  │                              │                                │  │
│  │ Workers: 8-64 (auto-scaled) │                                │  │
│  │ Each worker:                 │                                │  │
│  │  1. Read online features     │   ◄── Redis (< 1ms)           │  │
│  │  2. Build feature vector     │                                │  │
│  │  3. ONNX inference           │   ◄── CPU: < 5ms per point   │  │
│  │  4. Post-process score       │       GPU: < 1ms per batch    │  │
│  │  5. Publish if anomalous     │   ──▶ NATS anomaly topic      │  │
│  │                              │                                │  │
│  │ Micro-batching:              │                                │  │
│  │  Collect points for 50ms     │                                │  │
│  │  then score batch together   │                                │  │
│  │  (GPU utilization +          │                                │  │
│  │   throughput optimization)   │                                │  │
│  └──────────────────────────────┘                                │  │
│       │                                                          │  │
│       │ (main path continues without waiting for scoring)        │  │
│       ▼                                                          │  │
│  Storage Writer (ClickHouse)     ◄───────────────────────────────┘  │
│  (data written regardless of scoring result)                        │
└─────────────────────────────────────────────────────────────────────┘
```

### 10.2 Latency Requirements

| Component | P50 Latency | P99 Latency | Max Acceptable |
|-----------|-------------|-------------|----------------|
| Feature lookup (Redis) | < 0.5ms | < 2ms | 5ms |
| Feature vector assembly | < 0.5ms | < 1ms | 2ms |
| ONNX inference (CPU, single) | < 2ms | < 5ms | 10ms |
| ONNX inference (GPU, batch 256) | < 1ms | < 3ms | 5ms |
| Post-processing | < 0.5ms | < 1ms | 2ms |
| **Total scoring pipeline** | **< 5ms** | **< 15ms** | **100ms** |
| Anomaly event publish (NATS) | < 1ms | < 5ms | 10ms |

### 10.3 Batch Scoring for Historical Analysis

For retroactive anomaly detection on historical data (e.g., "were there anomalies last week that we missed?"):

```python
async def batch_score_historical(
    tenant_id: str,
    metric_name: str,
    start_time: datetime,
    end_time: datetime,
    model_version: int | None = None,  # None = use current active model
) -> list[AnomalyEvent]:
    """
    Score historical data in batch mode.
    Used for:
      - Retroactive analysis after model improvement
      - Incident post-mortems
      - Model evaluation

    Runs on batch workers, not on the real-time inference path.
    """
    # Fetch historical data from ClickHouse/S3
    data = await query_engine.fetch_metric_series(
        tenant_id, metric_name, start_time, end_time
    )

    # Load model
    model = model_registry.get_model(
        tenant_id, "anomaly_detection", version=model_version
    )

    # Compute features in batch
    features = feature_engine.compute_batch(data)

    # Score in chunks
    chunk_size = 10000
    anomalies = []
    for i in range(0, len(features), chunk_size):
        chunk = features[i:i + chunk_size]
        scores = model.predict(chunk)

        for j, score in enumerate(scores):
            if score > threshold:
                anomalies.append(create_anomaly_event(
                    data.iloc[i + j], score, model.version
                ))

    return anomalies
```

### 10.4 Score Aggregation and Rollup

Anomaly scores are aggregated at multiple levels for different consumers:

```yaml
score_aggregation:
  levels:
    - name: "metric"
      granularity: "per data point"
      storage: "clickhouse (raw)"
      retention: "7d"

    - name: "resource"
      granularity: "per host/container, per 1m window"
      aggregation: "max(score) across all metrics for resource"
      storage: "clickhouse (rollup)"
      retention: "30d"

    - name: "service"
      granularity: "per service, per 5m window"
      aggregation: "weighted_avg(resource_scores)"
      storage: "clickhouse (rollup)"
      retention: "90d"

    - name: "environment"
      granularity: "per environment (prod/staging), per 15m window"
      aggregation: "max(service_scores)"
      storage: "clickhouse (rollup)"
      retention: "1y"
```

---

## 11. AI Feedback Loop

### 11.1 User Feedback Collection

```
┌───────────────────────────────────────────────────────────────┐
│                     Feedback Loop                              │
│                                                               │
│  Anomaly Displayed in UI/Alert                                │
│       │                                                       │
│       ▼                                                       │
│  User Action:                                                 │
│  ┌────────────────┐  ┌────────────────┐  ┌─────────────────┐│
│  │ 👍 True       │  │ 👎 False      │  │ 🔇 Suppress    ││
│  │  Positive      │  │  Positive      │  │  (not useful)   ││
│  └───────┬────────┘  └───────┬────────┘  └───────┬─────────┘│
│          │                   │                    │          │
│          ▼                   ▼                    ▼          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                 Feedback Store                        │   │
│  │  (tenant_id, anomaly_id, metric, model_version,     │   │
│  │   feedback_type, timestamp, user_id)                 │   │
│  └────────────────────┬─────────────────────────────────┘   │
│                       │                                      │
│          ┌────────────┼────────────────┐                    │
│          ▼            ▼                ▼                    │
│  ┌──────────┐  ┌───────────┐  ┌──────────────────┐        │
│  │ Active   │  │ Threshold │  │ Suppression      │        │
│  │ Learning │  │ Adjustment│  │ Rules Engine     │        │
│  └──────────┘  └───────────┘  └──────────────────┘        │
└───────────────────────────────────────────────────────────────┘
```

### 11.2 Active Learning from Feedback

```python
class ActiveLearningEngine:
    """
    Uses user feedback to improve model quality over time.

    Feedback types:
      - true_positive:  model correctly identified anomaly
      - false_positive: model incorrectly flagged normal behavior
      - false_negative: user reports anomaly that model missed (manual creation)
    """

    def process_feedback(self, feedback: AnomalyFeedback):
        # Store feedback for retraining
        self.feedback_store.save(feedback)

        # Immediate adjustments (no retraining needed)
        if feedback.feedback_type == "false_positive":
            # Increase threshold for this specific metric/pattern
            self.threshold_adjuster.increase(
                tenant_id=feedback.tenant_id,
                metric=feedback.metric_name,
                amount=0.05,  # raise threshold by 5%
            )

        elif feedback.feedback_type == "false_negative":
            # Decrease threshold for this specific metric/pattern
            self.threshold_adjuster.decrease(
                tenant_id=feedback.tenant_id,
                metric=feedback.metric_name,
                amount=0.05,
            )

        # Check if enough feedback to trigger retraining
        recent_feedback = self.feedback_store.get_recent(
            tenant_id=feedback.tenant_id,
            window="7d",
        )

        if len(recent_feedback) >= 50:
            fpr = sum(1 for f in recent_feedback if f.type == "false_positive") / len(recent_feedback)

            if fpr > 0.10:  # FPR exceeds 10%
                self.trigger_retraining(
                    tenant_id=feedback.tenant_id,
                    reason="high_fpr_from_feedback",
                    feedback_data=recent_feedback,
                )

    def incorporate_feedback_into_training(
        self,
        training_data: pd.DataFrame,
        feedback: list[AnomalyFeedback],
    ) -> pd.DataFrame:
        """
        Augment training data with feedback labels.

        - True positives are added as positive examples
        - False positives are re-labeled as normal in training data
        - False negatives are added as positive examples
        """
        for fb in feedback:
            if fb.feedback_type == "false_positive":
                # Mark this data point as normal in training set
                training_data.loc[
                    training_data["timestamp"] == fb.anomaly_timestamp,
                    "label"
                ] = "normal"

            elif fb.feedback_type == "false_negative":
                # Add this as an anomaly example
                training_data.loc[
                    training_data["timestamp"] == fb.anomaly_timestamp,
                    "label"
                ] = "anomaly"

        return training_data
```

### 11.3 Model Performance Tracking

```yaml
model_performance_dashboard:
  metrics_tracked:
    - name: "precision"
      description: "Of all anomalies flagged, how many were true?"
      target: "> 0.90"

    - name: "recall"
      description: "Of all true anomalies, how many did we catch?"
      target: "> 0.85"

    - name: "false_positive_rate"
      description: "Percentage of normal events incorrectly flagged"
      target: "< 0.05"

    - name: "mean_time_to_detect"
      description: "Average time between anomaly start and detection"
      target: "< 60 seconds"

    - name: "feedback_rate"
      description: "Percentage of anomalies that receive user feedback"
      target: "> 0.10"

    - name: "model_drift_score"
      description: "PSI between training and inference distributions"
      target: "< 0.20"

  alerting:
    - condition: "fpr > 0.10 for 7 consecutive days"
      action: "trigger_retraining + notify_ml_team"
    - condition: "recall < 0.70"
      action: "notify_ml_team (critical)"
    - condition: "feedback_rate < 0.01"
      action: "prompt_users_for_feedback (in-product)"
```

### 11.4 Anomaly Suppression Rules

```yaml
suppression_rules:
  # Automatic suppression
  auto:
    - type: "maintenance_window"
      description: "Suppress during scheduled maintenance"
      match:
        tags: { "maintenance": "true" }

    - type: "known_pattern"
      description: "Suppress known benign patterns"
      match:
        metric_pattern: "k8s.pod.restart_count"
        conditions: "value < 3 AND resource.labels.environment = 'dev'"

    - type: "low_impact"
      description: "Suppress anomalies on non-critical services"
      match:
        service_tier: "tier-3"
        anomaly_score: "< 0.5"

  # User-created suppression rules
  user:
    max_rules_per_tenant: 100
    max_duration: "30d"       # suppression rules auto-expire
    audit_logged: true        # all suppressions are tracked
```

---

## 12. Multi-Tenancy

### 12.1 Per-Tenant Model Training

Every tenant gets dedicated models trained exclusively on their data. This ensures:

1. **Data isolation**: Tenant A's data never influences Tenant B's models
2. **Customization**: Models adapt to each tenant's unique traffic patterns, infrastructure, and operational rhythms
3. **Compliance**: Training data provenance is tenant-scoped for audit trails

```python
class TenantModelManager:
    """Manages the lifecycle of ML models per tenant."""

    async def ensure_models(self, tenant_id: str):
        """
        Ensure all required models exist for a tenant.
        Creates from shared base models if tenant is new.
        """
        required_models = [
            "anomaly_statistical",
            "anomaly_isolation_forest",
            "anomaly_autoencoder",
            "forecast_prophet",
            "log_pattern_drain",
            "correlation_matrix",
        ]

        for model_type in required_models:
            active = await self.registry.get_active(tenant_id, model_type)

            if active is None:
                # New tenant — initialize from shared base model
                base_model = await self.registry.get_shared_base(model_type)
                await self.registry.register(
                    tenant_id=tenant_id,
                    model_type=model_type,
                    artifact=base_model.artifact,
                    source="shared_base",
                    version=1,
                )
```

### 12.2 Resource Isolation

```yaml
resource_isolation:
  training:
    # Kubernetes namespace per tenant for training jobs
    namespace_template: "ml-training-{tenant_id}"
    resource_limits:
      cpu: "4"
      memory: "16Gi"
      gpu: "1"           # max 1 GPU per training job
    network_policy: "deny-all-except-storage"

  inference:
    # Shared inference pool with tenant-aware routing
    model: "shared_pool"
    isolation_mechanism: "process_level"  # separate ONNX sessions per tenant
    max_concurrent_per_tenant: 100
    request_timeout: "100ms"

  data:
    # Feature store keys are tenant-prefixed
    redis_key_prefix: "tenant:{tenant_id}:"
    s3_path_prefix: "s3://rayolly-ml/{tenant_id}/"
    # Cross-tenant access is impossible by key design
```

### 12.3 Shared Base Models with Tenant-Specific Fine-Tuning

```
Shared base models are trained on:
  - Synthetic data that mimics common observability patterns
  - Anonymized, aggregated patterns from opt-in telemetry
  - Public datasets (Numenta Anomaly Benchmark, Yahoo S5, etc.)

Fine-tuning process:
  1. Load shared base model weights
  2. Freeze early layers (generic feature extractors)
  3. Train final layers on tenant-specific data
  4. Evaluate against tenant's labeled feedback
  5. Deploy if performance meets promotion criteria

Benefits:
  - New tenants get reasonable anomaly detection within minutes
  - Fine-tuning requires 10x less data than training from scratch
  - Shared base models improve as the platform accumulates anonymized patterns
```

---

## 13. Technology Stack

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| **Core ML** | scikit-learn | 1.5+ | Statistical models, Isolation Forest, LOF, preprocessing |
| **Deep Learning** | PyTorch | 2.4+ | LSTM, Autoencoder, TCN training |
| **Time Series** | Prophet / NeuralProphet | Latest | Forecasting with seasonality |
| **Temporal Fusion** | pytorch-forecasting | Latest | TFT for multi-variate forecasting |
| **Statistics** | statsmodels | 0.14+ | STL decomposition, Granger causality, ADF test |
| **Inference** | ONNX Runtime | 1.18+ | Unified model serving (CPU + GPU) |
| **Data Format** | Apache Arrow / Parquet | Latest | Zero-copy data interchange between components |
| **Distributed Training** | Ray | 2.9+ | Distributed training jobs, GPU scheduling |
| **Task Queue** | Celery (fallback) | 5.4+ | Lightweight task scheduling when Ray is overkill |
| **Feature Cache** | Redis / DragonflyDB | 7.2+ | Online feature store, low-latency feature lookup |
| **Model Registry** | Custom (backed by PostgreSQL + S3) | N/A | Model versioning, artifact storage, lineage |
| **Hyperparameter Tuning** | Optuna | 3.6+ | Bayesian hyperparameter optimization |
| **Log Parsing** | drain3 | Latest | Streaming log template extraction |
| **Model Export** | ONNX | 1.16+ | Model serialization format |
| **Numerical** | NumPy / SciPy | Latest | Numerical computation, statistical tests |
| **Data Processing** | Pandas / Polars | Latest | Data manipulation (Polars for performance-critical paths) |
| **Monitoring** | OpenTelemetry (self) | Latest | ML pipeline observability (dogfooding) |

### 13.1 Dependency Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    ML Engine Dependencies                      │
│                                                              │
│  Training Path:                                              │
│    ClickHouse → Arrow → Polars → scikit-learn/PyTorch        │
│                                → Optuna (hyperparams)         │
│                                → ONNX (export)               │
│                                → S3 (artifact store)         │
│                                                              │
│  Inference Path:                                             │
│    NATS → Arrow → Redis (features) → ONNX Runtime → NATS    │
│                                                              │
│  Orchestration:                                              │
│    Ray Cluster (GPU workers) ← Job Scheduler (Celery Beat)   │
│                                                              │
│  Data Flow:                                                  │
│    All inter-component data exchange uses Apache Arrow        │
│    (zero-copy, language-agnostic, columnar)                   │
└──────────────────────────────────────────────────────────────┘
```

---

## 14. Performance Requirements

### 14.1 Latency Requirements

| Operation | Target | Max Acceptable | Notes |
|-----------|--------|----------------|-------|
| Real-time anomaly scoring (per point) | < 15ms P99 | 100ms | On ingestion hot path |
| Feature lookup | < 2ms P99 | 5ms | Redis online store |
| Anomaly event publication | < 5ms | 10ms | NATS publish |
| End-to-end detection latency | < 1 minute | 5 minutes | From data ingestion to anomaly event |
| Forecast generation (single metric) | < 5 seconds | 30 seconds | On-demand via API |
| RCA analysis | < 30 seconds | 2 minutes | For a single incident |
| Log pattern matching | < 10ms | 50ms | Per log line |

### 14.2 Throughput Requirements

| Operation | Target | Scale Limit |
|-----------|--------|-------------|
| Streaming inference | 500K data points/sec per node | Linear scale with nodes |
| Log pattern extraction | 200K log lines/sec per node | Linear scale with nodes |
| Batch training (single model) | 10M data points/hour (CPU) | 100M/hour (GPU) |
| Correlation computation | 10K metric pairs/minute | Batched, background |
| Feature computation | 1M features/sec per node | Linear scale with nodes |

### 14.3 Accuracy Requirements

| Metric | Target (2 weeks) | Target (30 days) | Target (90 days) |
|--------|-------------------|-------------------|-------------------|
| Anomaly precision | > 85% | > 90% | > 95% |
| Anomaly recall | > 80% | > 85% | > 90% |
| False positive rate | < 10% | < 5% | < 3% |
| Forecast MAPE (24h horizon) | < 15% | < 10% | < 8% |
| RCA top-3 accuracy | > 60% | > 70% | > 80% |
| Log pattern coverage | > 90% | > 95% | > 98% |

### 14.4 Resource Requirements

| Resource | Per Tenant (Standard) | Per Tenant (Enterprise) | Platform Total |
|----------|----------------------|------------------------|----------------|
| Model storage | < 100MB | < 1GB | < 10TB |
| Feature store (Redis) | < 500MB | < 5GB | < 500GB |
| Training compute (daily) | 0.5 CPU-hours | 4 GPU-hours | Cluster-dependent |
| Inference memory | < 256MB | < 2GB | < 64GB per node |
| Training data retention | 30 days | 90 days | Configurable |

### 14.5 Training Time Requirements

| Model Type | Training Time (30-day baseline) | Training Time (90-day baseline) |
|-----------|-------------------------------|-------------------------------|
| Statistical (Z-score, MAD) | < 1 minute | < 5 minutes |
| Isolation Forest | < 10 minutes | < 30 minutes |
| Autoencoder | < 30 minutes (CPU) / 5 min (GPU) | < 1 hour (CPU) / 15 min (GPU) |
| LSTM Autoencoder | < 1 hour (GPU required) | < 3 hours (GPU required) |
| Prophet forecast | < 5 minutes per metric | < 15 minutes per metric |
| Log pattern extraction | < 10 minutes per 1M logs | < 30 minutes per 10M logs |

---

## 15. Integration Points

### 15.1 Integration Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                    AI/ML Engine Integration Map                       │
│                                                                      │
│  ┌──────────────────┐         ┌───────────────────────┐             │
│  │  PRD-01           │         │  PRD-02                │             │
│  │  Data Ingestion   │────────▶│  Storage Engine        │             │
│  │                   │         │                       │             │
│  │  Provides:        │         │  Provides:            │             │
│  │  - Raw telemetry  │         │  - Historical data    │             │
│  │    stream (NATS)  │         │    for training       │             │
│  │  - Enriched data  │         │  - Time-series query  │             │
│  │    points         │         │    results            │             │
│  └──────────┬───────┘         └────────────┬──────────┘             │
│             │                               │                        │
│             ▼                               ▼                        │
│  ┌───────────────────────────────────────────────────┐              │
│  │               AI/ML Engine (PRD-04)                │              │
│  │                                                   │              │
│  │  Consumes:                                        │              │
│  │  - Streaming data from NATS (real-time scoring)   │              │
│  │  - Historical data from ClickHouse (training)     │              │
│  │  - Change events from PRD-01 (RCA correlation)    │              │
│  │                                                   │              │
│  │  Produces:                                        │              │
│  │  - Anomaly events → NATS topic "ml.anomalies"     │              │
│  │  - Forecasts → stored in ClickHouse               │              │
│  │  - RCA reports → stored in PostgreSQL              │              │
│  │  - Model metrics → OpenTelemetry (self-monitoring) │              │
│  └───────┬───────────┬──────────┬──────────┬─────────┘              │
│          │           │          │          │                         │
│          ▼           ▼          ▼          ▼                         │
│  ┌──────────┐ ┌──────────┐ ┌────────┐ ┌────────────┐               │
│  │ PRD-05   │ │ PRD-09   │ │PRD-03  │ │ PRD-10     │               │
│  │ Agent    │ │ Alerting │ │Query   │ │ Dashboards │               │
│  │ System   │ │ Engine   │ │Engine  │ │            │               │
│  │          │ │          │ │        │ │            │               │
│  │ Consumes:│ │Consumes: │ │Exposes:│ │ Displays:  │               │
│  │ Anomalies│ │Anomaly   │ │Anomaly │ │ Anomaly    │               │
│  │ RCA      │ │events →  │ │data via│ │ overlays,  │               │
│  │ reports  │ │generate  │ │SQL/API │ │ forecasts, │               │
│  │ for auto │ │alerts    │ │        │ │ RCA views  │               │
│  │ diagnosis│ │          │ │        │ │            │               │
│  └──────────┘ └──────────┘ └────────┘ └────────────┘               │
└──────────────────────────────────────────────────────────────────────┘
```

### 15.2 API Contracts

#### ML Engine → Agent System (PRD-05)

```python
# Published to NATS topic: "ml.anomalies.{tenant_id}"
class MLAnomalyEvent:
    tenant_id: str
    anomaly_id: str
    timestamp: datetime
    severity: str              # "info", "warning", "critical"
    score: float               # 0.0 - 1.0
    affected_resource: str
    affected_metrics: list[str]
    summary: str               # human-readable summary
    rca_available: bool        # if RCA has been computed
    rca_report_id: str | None

# Published to NATS topic: "ml.forecasts.{tenant_id}"
class MLForecastEvent:
    tenant_id: str
    metric_name: str
    resource_id: str
    forecast_type: str         # "capacity", "slo_burn", "traffic"
    predicted_breach_time: datetime | None
    confidence: float
    urgency: str
    summary: str
```

#### ML Engine → Alerting Engine (PRD-09)

```python
# Published to NATS topic: "ml.alerts.{tenant_id}"
class MLAlertTrigger:
    tenant_id: str
    alert_type: str            # "anomaly", "forecast_breach", "new_log_pattern"
    source_id: str             # anomaly_id or forecast_id
    severity: str
    title: str
    description: str
    metric_name: str
    current_value: float
    threshold_value: float
    dashboard_link: str        # deep link to relevant dashboard
```

#### Query Engine (PRD-03) → ML Engine

```sql
-- Anomaly data is queryable via standard SQL
SELECT
    timestamp,
    metric_name,
    resource_id,
    anomaly_score,
    severity,
    detection_method,
    expected_value,
    observed_value
FROM ml.anomalies
WHERE tenant_id = 'tenant123'
  AND timestamp > now() - INTERVAL 24 HOUR
  AND severity = 'critical'
ORDER BY anomaly_score DESC;

-- Forecast data
SELECT
    timestamp,
    metric_name,
    forecast_value,
    forecast_lower,
    forecast_upper,
    confidence
FROM ml.forecasts
WHERE tenant_id = 'tenant123'
  AND metric_name = 'api.latency.p99'
  AND timestamp > now();
```

#### Dashboard (PRD-10) → ML Engine

```
REST API endpoints:

GET  /api/v1/ml/anomalies?tenant_id=X&time_range=24h&severity=critical
GET  /api/v1/ml/anomalies/{anomaly_id}
POST /api/v1/ml/anomalies/{anomaly_id}/feedback  { "type": "true_positive" }

GET  /api/v1/ml/forecasts?tenant_id=X&metric=cpu_usage&horizon=7d
GET  /api/v1/ml/forecasts/capacity?tenant_id=X&resource_type=disk

GET  /api/v1/ml/rca/{incident_id}
GET  /api/v1/ml/rca/{incident_id}/timeline

GET  /api/v1/ml/correlations?tenant_id=X&metric=api.latency
GET  /api/v1/ml/patterns/logs?tenant_id=X&service=api-gateway

GET  /api/v1/ml/models?tenant_id=X
GET  /api/v1/ml/models/{model_id}/performance

WebSocket: /ws/v1/ml/anomalies/live?tenant_id=X  (real-time anomaly stream)
```

---

## 16. Success Metrics

### 16.1 Product Success Metrics

| Metric | Measurement Method | Target (GA) | Target (6mo post-GA) |
|--------|-------------------|-------------|----------------------|
| **Anomaly detection accuracy** | Precision from user feedback | > 85% | > 93% |
| **False positive rate** | FP count / total anomalies flagged | < 10% | < 5% |
| **Mean time to detect (MTTD)** | Time from anomaly start to detection | < 2 minutes | < 1 minute |
| **Forecast accuracy (MAPE)** | Mean Absolute Percentage Error on 24h forecasts | < 15% | < 10% |
| **RCA accuracy (top-3)** | Correct root cause in top 3 candidates | > 60% | > 75% |
| **Log pattern coverage** | % of log lines matched to a known pattern | > 90% | > 97% |
| **Capacity forecast lead time** | How far in advance exhaustion is predicted | > 3 days | > 7 days |
| **SLO breach prediction** | Accuracy of "SLO will breach in X hours" | > 70% | > 85% |
| **User feedback rate** | % of anomalies receiving thumbs up/down | > 5% | > 15% |
| **Scoring latency P99** | Real-time inference latency | < 50ms | < 20ms |

### 16.2 Operational Success Metrics

| Metric | Target |
|--------|--------|
| ML pipeline uptime | > 99.9% |
| Model training success rate | > 95% (jobs completing without failure) |
| Model retraining frequency | At least daily for active metrics |
| Feature store freshness | < 5 minutes staleness |
| GPU utilization (training pool) | > 60% |
| Model storage cost per tenant | < $5/month (standard tier) |

### 16.3 Business Impact Metrics

| Metric | Target |
|--------|--------|
| **MTTR reduction** | 50% reduction vs manual investigation |
| **Alert noise reduction** | 80% fewer false-positive alerts compared to threshold-based |
| **Feature adoption** | > 70% of active tenants using AI-powered anomaly detection |
| **Agent enablement** | 100% of Agent actions use ML scores as input |
| **Competitive win rate** | AI/ML capabilities cited as top-3 reason in 40% of deals |

---

## 17. Dependencies and Risks

### 17.1 Dependencies

| Dependency | Type | Impact if Delayed | Mitigation |
|-----------|------|-------------------|------------|
| PRD-02 Storage Engine | Hard | Cannot train models without historical data access | Use synthetic data for initial model development |
| PRD-03 Query Engine | Hard | Cannot query training data efficiently | Direct ClickHouse access as fallback |
| GPU infrastructure (PRD-13) | Hard | Deep learning models cannot train | CPU-only models for v1; GPU models as enhancement |
| Redis cluster | Hard | Feature store unavailable → inference degraded | Fallback to on-the-fly feature computation (slower) |
| NATS JetStream | Hard | Streaming inference pipeline stops | Queue backpressure + batch scoring as fallback |
| Model registry (PostgreSQL) | Soft | Model metadata unavailable; cached models continue serving | Local model cache survives registry outages |

### 17.2 Risks

#### Risk 1: GPU Cost Management (Probability: High, Impact: High)

**Description**: GPU compute for training and inference can become the largest infrastructure cost, especially with per-tenant model training.

**Mitigation strategy**:
- Tiered model complexity: free tenants get CPU-only statistical models; enterprise gets GPU deep learning
- Aggressive model caching: train once, serve from ONNX (CPU inference for most models)
- Shared base models reduce per-tenant training compute by 10x
- Training job scheduling during off-peak hours (spot instances)
- Model size budgets per tenant tier
- GPU sharing via MPS (Multi-Process Service) for inference

**Cost estimates**:

| Component | Monthly Cost (100 tenants) | Monthly Cost (1000 tenants) |
|-----------|--------------------------|---------------------------|
| Training GPUs (4x A100) | $6,000 | $18,000 (12x A100) |
| Inference GPUs (4x T4) | $2,400 | $8,000 (12x T4) |
| Redis (feature store) | $500 | $3,000 |
| S3 (model artifacts) | $200 | $1,500 |
| **Total ML infra** | **$9,100** | **$30,500** |

#### Risk 2: Model Accuracy Across Diverse Workloads (Probability: Medium, Impact: High)

**Description**: Different tenants have radically different workload patterns (web app vs batch processing vs IoT). A one-size-fits-all model architecture may underperform for edge cases.

**Mitigation strategy**:
- Automatic workload classification: detect if metric is periodic, bursty, trend-dominated, or stationary
- Workload-specific model selection: batch-heavy tenants get different default algorithms than web-app tenants
- Ensemble approach (Tier 5) provides robustness across workload types
- Continuous evaluation and automatic retraining based on feedback
- Human-in-the-loop for edge cases: low-confidence detections routed to users for feedback

#### Risk 3: Cold Start Problem for New Tenants (Probability: High, Impact: Medium)

**Description**: New tenants have no historical data, so models have no training data. This leads to poor anomaly detection and high false-positive rates during the initial period.

**Mitigation strategy**:
- **Phase 1 (T+0 to T+4h)**: Only Tier 1 statistical detection with wide thresholds — catches extreme outliers only, very low FPR
- **Phase 2 (T+4h to T+24h)**: Statistical baselines stabilize — standard anomaly detection active
- **Phase 3 (T+24h to T+7d)**: Seasonality detection kicks in — daily patterns modeled
- **Phase 4 (T+7d+)**: Full model suite active
- Shared base models provide reasonable detection from minute one
- Explicit UI messaging: "AI accuracy improves with more data. Current confidence: 60%. Full accuracy in ~7 days."
- Accelerated learning: allow users to mark known normal/abnormal periods to bootstrap models faster

#### Risk 4: Adversarial and Degenerate Data Patterns (Probability: Low, Impact: High)

**Description**: Certain data patterns can fool ML models — extremely noisy metrics, metrics with no discernible pattern, or adversarial inputs.

**Mitigation strategy**:
- Data quality scoring: assess each metric's "modelability" (entropy, stationarity, signal-to-noise ratio)
- Graceful degradation: for unmodelable metrics, fall back to simple threshold alerting and inform the user
- Anomaly score confidence reflects data quality — low-quality data produces low-confidence scores that are suppressed

#### Risk 5: Model Serving Latency Under Load (Probability: Medium, Impact: Medium)

**Description**: During traffic spikes, the inference pipeline may not keep up, leading to delayed anomaly detection or dropped scoring.

**Mitigation strategy**:
- ONNX Runtime provides highly optimized inference (typically < 5ms per prediction)
- Micro-batching smooths load spikes
- Horizontal scaling of scoring workers (Kubernetes HPA on queue depth)
- Priority scoring: SLO-linked metrics scored first; informational metrics can be deferred
- Circuit breaker: if scoring latency exceeds 500ms, bypass scoring and log for batch processing later
- Backpressure signaling to NATS to slow ingestion if inference pool is saturated

### 17.3 Open Questions

| # | Question | Impact | Decision Needed By |
|---|----------|--------|-------------------|
| 1 | Should we support customer-provided models in v1 or v2? | Architecture impact on model serving | Architecture review |
| 2 | MLflow vs custom model registry? | Build vs buy decision | Sprint 1 |
| 3 | Ray vs Celery for distributed training? | Infrastructure complexity | Sprint 1 |
| 4 | GPU instance type (A100 vs T4 vs L4) for inference? | Cost and latency tradeoff | Infrastructure review |
| 5 | Should shared base models include anonymized customer data (with opt-in)? | Privacy and legal review | Legal review |
| 6 | Online learning (streaming model updates) in v1 or v2? | Complexity and accuracy tradeoff | Architecture review |
| 7 | Support for custom seasonality periods (e.g., bi-weekly pay cycles)? | UX and model complexity | Product review |

---

## Appendix A: Algorithm Selection Decision Tree

```
For each metric/signal entering the ML Engine:

  1. Is there >= 4h of historical data?
     ├─ No → Use Tier 1 (statistical) with wide thresholds only
     └─ Yes → Continue

  2. Is the metric univariate or part of a known multi-variate group?
     ├─ Multi-variate → Use Isolation Forest on feature group (Tier 3)
     └─ Univariate → Continue

  3. Does the metric have detected seasonality (autocorrelation test)?
     ├─ Yes → Use STL decomposition (Tier 2) + detect residual anomalies
     └─ No → Use Modified Z-Score (Tier 1)

  4. Is the metric linked to an SLO or critical service?
     ├─ Yes → Add Ensemble scoring (Tier 5) combining all applicable tiers
     └─ No → Use highest applicable single tier

  5. Does the metric have >= 14 days of history AND complex temporal patterns?
     ├─ Yes → Add LSTM/TCN (Tier 4) as additional signal
     └─ No → Keep current tier selection

  6. Is this a capacity metric (disk, memory, CPU, connections)?
     ├─ Yes → Also run through Forecasting Engine for exhaustion prediction
     └─ No → Anomaly detection only
```

## Appendix B: Data Schema for ML Tables in ClickHouse

```sql
-- Anomaly events table
CREATE TABLE ml.anomalies (
    tenant_id       String,
    anomaly_id      UUID,
    timestamp       DateTime64(3),
    metric_name     String,
    resource_id     String,
    dimensions      Map(String, String),

    score           Float32,
    confidence      Float32,
    severity        Enum8('info' = 1, 'warning' = 2, 'critical' = 3),
    direction       Enum8('above' = 1, 'below' = 2, 'both' = 3),

    observed_value  Float64,
    expected_value  Float64,
    expected_lower  Float64,
    expected_upper  Float64,

    detection_method String,
    detection_tier  UInt8,
    model_version   UInt32,

    state           Enum8('open' = 1, 'acknowledged' = 2, 'resolved' = 3, 'suppressed' = 4),
    user_feedback   Nullable(Enum8('true_positive' = 1, 'false_positive' = 2)),

    first_seen      DateTime64(3),
    last_seen       DateTime64(3),
    occurrence_count UInt32
)
ENGINE = MergeTree()
PARTITION BY (tenant_id, toYYYYMM(timestamp))
ORDER BY (tenant_id, metric_name, timestamp)
TTL timestamp + INTERVAL 90 DAY;

-- Forecasts table
CREATE TABLE ml.forecasts (
    tenant_id       String,
    metric_name     String,
    resource_id     String,
    generated_at    DateTime64(3),

    timestamp       DateTime64(3),     -- forecast timestamp (future)
    forecast_value  Float64,
    forecast_lower  Float64,           -- lower confidence bound
    forecast_upper  Float64,           -- upper confidence bound
    confidence      Float32,

    model_type      String,
    model_version   UInt32,
    horizon         String
)
ENGINE = MergeTree()
PARTITION BY (tenant_id, toYYYYMM(timestamp))
ORDER BY (tenant_id, metric_name, timestamp)
TTL timestamp + INTERVAL 30 DAY;

-- Log patterns table
CREATE TABLE ml.log_patterns (
    tenant_id       String,
    pattern_id      String,
    template        String,
    service         String,

    first_seen      DateTime64(3),
    last_seen       DateTime64(3),
    total_count     UInt64,

    -- Rolling counts
    count_1h        UInt32,
    count_24h       UInt32,
    count_7d        UInt64,

    -- Anomaly
    frequency_anomaly_score Float32,
    is_new_pattern  Bool,

    -- Cluster
    cluster_id      UInt32,
    cluster_label   String
)
ENGINE = ReplacingMergeTree(last_seen)
PARTITION BY (tenant_id)
ORDER BY (tenant_id, pattern_id);

-- Metric correlations table
CREATE TABLE ml.correlations (
    tenant_id       String,
    metric_a        String,
    metric_b        String,

    correlation     Float32,
    lag_periods     Int16,
    p_value         Float64,

    relationship    Enum8('synchronous' = 1, 'lead' = 2, 'lag' = 3),

    computed_at     DateTime64(3),
    sample_size     UInt32
)
ENGINE = ReplacingMergeTree(computed_at)
PARTITION BY (tenant_id)
ORDER BY (tenant_id, metric_a, metric_b);
```

## Appendix C: Glossary

| Term | Definition |
|------|-----------|
| **Anomaly score** | Normalized value (0.0 - 1.0) indicating how anomalous a data point is |
| **Baseline** | Historical data used to establish "normal" behavior for a metric |
| **Burn rate** | Rate at which an SLO error budget is being consumed |
| **Change point** | A point in time where the statistical properties of a time series change abruptly |
| **Cold start** | Period when a new tenant or metric lacks sufficient data for accurate ML models |
| **Concept drift** | When the relationship between input features and target changes over time |
| **Feature drift** | When the distribution of input features changes over time |
| **Feature store** | Centralized repository of pre-computed features for ML model training and inference |
| **Granger causality** | Statistical test for whether one time series is useful in forecasting another |
| **Isolation Forest** | Unsupervised anomaly detection algorithm based on random recursive partitioning |
| **MAD** | Median Absolute Deviation — robust measure of variability |
| **MAPE** | Mean Absolute Percentage Error — measure of forecast accuracy |
| **ONNX** | Open Neural Network Exchange — portable model format for cross-framework inference |
| **PSI** | Population Stability Index — measure of distribution shift between datasets |
| **RCA** | Root Cause Analysis — process of identifying the underlying cause of an incident |
| **STL** | Seasonal and Trend decomposition using Loess |
| **TCN** | Temporal Convolutional Network — CNN-based architecture for sequence modeling |
| **TFT** | Temporal Fusion Transformer — attention-based architecture for multi-horizon forecasting |
| **Transfer entropy** | Information-theoretic measure of directed information transfer between time series |

---

*PRD-04 is a dependency for PRD-05 (AI Agents-as-a-Service) and PRD-09 (Alerting & Incident Management). All ML outputs described in this document are consumed by downstream systems via the integration contracts defined in Section 15.*

*RayOlly AI/ML Engine v1.0 | PRD-04 | Platform Architecture Team*
