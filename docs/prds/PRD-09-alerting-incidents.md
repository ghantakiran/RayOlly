# PRD-09: Alerting & Incident Management

**Product**: RayOlly — AI-Native Observability Platform
**Version**: 1.0
**Date**: 2026-03-19
**Status**: Draft
**Parent**: PRD-00 Platform Vision & Architecture
**Dependencies**: PRD-01 (Ingestion), PRD-02 (Storage), PRD-03 (Query Engine), PRD-06 (Logs), PRD-07 (Metrics), PRD-08 (Traces/APM)

---

## 1. Executive Summary

The Alerting & Incident Management module is RayOlly's proactive response layer — the system that transforms raw observability data into actionable operational intelligence. It replaces PagerDuty + OpsGenie + Grafana Alerting + Datadog Monitors with a single, AI-native alerting and incident system that is deeply integrated with all three observability pillars (logs, metrics, traces).

Unlike legacy alerting systems that rely entirely on manually configured static thresholds, RayOlly's alerting is **AI-first**: every metric, log stream, and trace pipeline is continuously analyzed by ML models for anomalies, trend shifts, and predicted breaches — generating high-signal alerts with zero manual threshold configuration required.

**Key Differentiators**:
- AI-powered anomaly alerts by default — no thresholds to configure, works out-of-the-box
- Multi-signal composite alerts that correlate logs + metrics + traces in a single rule
- Intelligent noise reduction: 70%+ reduction in alert volume through deduplication, correlation, and transient suppression
- Predictive alerting — warn 15-60 minutes before an issue occurs based on trend forecasting
- Built-in incident management with AI-generated root cause analysis, timelines, and postmortem drafts
- SLO burn rate alerts — native SLI/SLO integration with error budget tracking

---

## 2. Goals & Non-Goals

### Goals
- Evaluate alert rules across logs, metrics, and traces with < 30s evaluation latency
- Deliver notifications to all configured channels within 60 seconds of alert firing
- Support 10,000+ alert rules per tenant with efficient batch evaluation
- Provide AI-powered anomaly detection that generates useful alerts with zero configuration
- Reduce alert noise by 70%+ through intelligent correlation, deduplication, and suppression
- Offer a complete incident lifecycle from detection through postmortem
- Integrate with existing on-call tools (PagerDuty, OpsGenie) while providing built-in on-call scheduling
- Enable predictive alerts that fire before thresholds are breached
- Support SLO burn rate alerting with multi-window evaluation

### Non-Goals
- Replace dedicated incident communication tools (Statuspage.io, FireHydrant) — integrate instead
- Build a full-featured on-call management platform (leverage PagerDuty/OpsGenie for complex schedules)
- Provide runbook automation execution (future scope — PRD-12)
- Replace dedicated chaos engineering tools
- Support voice call notifications natively (defer to PagerDuty/OpsGenie integration)

---

## 3. Alert Types

### 3.1 Metric Threshold Alerts (Static + Dynamic)

Static threshold alerts fire when a metric crosses a fixed boundary. Dynamic thresholds use historical baselines.

| Subtype | Description | Example |
|---------|------------|---------|
| **Static threshold** | Fixed upper/lower bounds | CPU > 90% for 5 minutes |
| **Dynamic threshold** | ML-computed baseline ± deviation bands | Response time 3 standard deviations above 7-day baseline |
| **Rate of change** | Value changing faster than expected | Error count increasing > 50/min |
| **Absence** | Metric stops reporting | Host heartbeat missing for 2 minutes |

### 3.2 Log-Based Alerts

| Subtype | Description | Example |
|---------|------------|---------|
| **Pattern match** | Specific log pattern appears | Log contains `FATAL` or `OOMKilled` |
| **Count threshold** | Log volume exceeds threshold | More than 100 error logs in 5 minutes |
| **Absence** | Expected log stops appearing | No healthcheck log for 3 minutes |
| **New pattern** | Previously unseen log pattern detected | AI detects a new error cluster |
| **Ratio** | Ratio of log types crosses threshold | Error/total log ratio > 5% |

### 3.3 Trace-Based Alerts

| Subtype | Description | Example |
|---------|------------|---------|
| **Latency threshold** | P99 latency exceeds limit | P99 for `/api/checkout` > 2s |
| **Error rate** | Span error rate crosses threshold | Payment service error rate > 1% |
| **Throughput change** | Request volume drops/spikes | Orders endpoint drops 50% vs last hour |
| **Dependency latency** | Downstream service slows | Database call latency P95 > 500ms |

### 3.4 Composite Alerts (Multi-Signal)

Composite alerts combine conditions across multiple signals, reducing false positives by requiring corroboration.

```
Composite Alert: "Service Degradation"
  ALL of:
    - metrics: http_request_duration_p99{service="checkout"} > 2s
    - logs: count(level="error", service="checkout") > 50 in 5m
    - traces: error_rate{service="checkout"} > 5%
  Fire only when ALL conditions are true simultaneously
```

### 3.5 Anomaly-Based Alerts (AI-Detected)

No manual configuration required. The AI engine continuously learns baselines for all metrics and fires alerts when statistically significant deviations occur.

| Feature | Description |
|---------|------------|
| **Automatic baselining** | 7-day rolling baseline per metric per dimension |
| **Seasonality awareness** | Detects hourly, daily, weekly patterns |
| **Sensitivity tuning** | Adjustable from "low" (only major anomalies) to "high" (subtle shifts) |
| **Context enrichment** | Anomaly alerts include correlated signals automatically |

### 3.6 Predictive Alerts (Forecasted Breach)

Predictive alerts use time-series forecasting to project metric values forward and alert before a threshold is breached.

| Feature | Description |
|---------|------------|
| **Forecast horizon** | 15 minutes to 24 hours ahead |
| **Algorithms** | Prophet, Holt-Winters, LSTM (auto-selected) |
| **Confidence intervals** | Fires when confidence > 80% that breach will occur |
| **Use cases** | Disk fill prediction, certificate expiry, quota exhaustion, memory leak detection |

### 3.7 SLO Burn Rate Alerts

Based on Google's multi-window burn rate approach. Fires when the error budget is being consumed faster than sustainable.

| Window | Burn Rate | Meaning |
|--------|-----------|---------|
| 1h / 5m | 14.4x | Critical — budget exhausted in ~1 hour |
| 6h / 30m | 6x | Urgent — budget exhausted in ~6 hours |
| 1d / 2h | 3x | Warning — budget exhausted in ~2.4 days |
| 3d / 6h | 1x | Informational — budget on track to exhaust |

---

## 4. Alert Rule Engine

### 4.1 Rule Definition Format

Alert rules are defined as YAML documents and can also be created via the UI builder. Both representations are interchangeable — the UI builder generates YAML, and YAML can be imported into the UI.

```yaml
# Schema version
apiVersion: rayolly.io/v1
kind: AlertRule
metadata:
  name: high-cpu-usage
  namespace: infrastructure
  labels:
    team: platform
    tier: critical
    environment: production
spec:
  type: metric_threshold       # metric_threshold | log_pattern | trace_latency |
                                # composite | anomaly | predictive | slo_burn_rate
  enabled: true
  description: "CPU usage exceeds 90% for 5 minutes on any production host"

  # Evaluation
  evaluation:
    interval: 30s              # How often to evaluate (15s, 30s, 1m, 5m)
    for: 5m                    # Condition must be true for this duration before firing
    timezone: "UTC"

  # Condition
  condition:
    query: |
      avg by (host) (
        system_cpu_usage{environment="production"}
      )
    operator: ">"              # >, <, >=, <=, ==, !=
    threshold: 90
    dataSource: metrics        # metrics | logs | traces

  # Severity
  severity: critical           # critical | high | medium | low | info

  # Alert metadata attached to fired alerts
  annotations:
    summary: "High CPU on {{ $labels.host }}"
    description: |
      CPU usage is {{ $value | printf "%.1f" }}% on host {{ $labels.host }}.
      This has been sustained for more than 5 minutes.
    runbook_url: "https://wiki.internal/runbooks/high-cpu"
    dashboard_url: "https://rayolly.example.com/d/infra/host?host={{ $labels.host }}"

  # Routing
  routing:
    channels:
      - slack-platform-alerts
      - pagerduty-infra
    escalation_policy: infra-critical
    mute_timings:
      - maintenance-windows
```

### 4.2 Evaluation Intervals

| Interval | Use Case | Resource Impact |
|----------|---------|-----------------|
| **15s** | Critical real-time alerts (P1 SLO burn rates) | High — reserved for critical rules |
| **30s** | Standard production alerts | Medium — default for most rules |
| **1m** | Non-urgent monitoring | Low |
| **5m** | Trend and capacity alerts | Minimal |

Evaluation is batched — rules sharing the same query and interval are grouped and evaluated in a single query execution pass.

### 4.3 Alert Conditions and Operators

```yaml
# Comparison operators
operator: ">"          # Greater than
operator: "<"          # Less than
operator: ">="         # Greater than or equal
operator: "<="         # Less than or equal
operator: "=="         # Equal
operator: "!="         # Not equal

# Aggregation functions (applied before comparison)
reduce:
  function: avg        # avg, sum, min, max, count, last, percentile
  percentile: 99       # Only for percentile function
  of: "A"              # Reference to query label

# Value transformations
transform:
  - type: rate         # Compute per-second rate
    period: 5m
  - type: abs          # Absolute value
  - type: delta        # Difference from previous evaluation
```

### 4.4 Multi-Condition Rules

```yaml
apiVersion: rayolly.io/v1
kind: AlertRule
metadata:
  name: service-degradation-composite
spec:
  type: composite
  evaluation:
    interval: 30s
    for: 2m
  conditions:
    logic: "A AND (B OR C)"    # Boolean logic across conditions
    rules:
      - id: A
        query: 'avg(http_request_duration_seconds{service="checkout"}) > 2'
        dataSource: metrics
      - id: B
        query: 'count(level="error" AND service="checkout") > 100'
        dataSource: logs
        window: 5m
      - id: C
        query: 'error_rate{service="checkout"} > 0.05'
        dataSource: traces
  severity: critical
```

### 4.5 Template Variables

Template variables allow dynamic content in alert annotations and notification messages.

| Variable | Description | Example Value |
|----------|------------|---------------|
| `{{ $labels.<key> }}` | Label value from the triggering series | `checkout-prod-1` |
| `{{ $value }}` | Current numeric value of the alert condition | `94.7` |
| `{{ $alert.name }}` | Alert rule name | `high-cpu-usage` |
| `{{ $alert.severity }}` | Alert severity | `critical` |
| `{{ $alert.firedAt }}` | ISO timestamp when alert fired | `2026-03-19T14:23:00Z` |
| `{{ $alert.duration }}` | How long the alert has been firing | `12m34s` |
| `{{ $alert.runbook }}` | Runbook URL from annotations | `https://wiki.internal/...` |
| `{{ $alert.dashboardUrl }}` | Auto-generated link to relevant dashboard | `https://rayolly.example.com/...` |
| `{{ $tenant.name }}` | Tenant name | `acme-corp` |

### 4.6 Rule Testing and Preview

Before saving an alert rule, users can test it against historical data.

```
POST /api/v1/alerts/rules/test
Content-Type: application/json

{
  "rule": { ... },             // Full alert rule definition
  "timeRange": {
    "from": "2026-03-18T00:00:00Z",
    "to": "2026-03-19T00:00:00Z"
  },
  "dryRun": true               // Don't actually fire alerts
}

Response:
{
  "wouldHaveFired": 3,
  "firings": [
    {
      "timestamp": "2026-03-18T03:14:00Z",
      "duration": "12m",
      "labels": { "host": "web-prod-7" },
      "value": 94.2
    },
    ...
  ],
  "evaluationStats": {
    "queriesExecuted": 2880,
    "avgEvaluationTime": "12ms",
    "dataPointsScanned": 518400
  }
}
```

### 4.7 Example Alert Rules

#### Example 1: High Error Rate (Metric Threshold)

```yaml
apiVersion: rayolly.io/v1
kind: AlertRule
metadata:
  name: high-error-rate
  namespace: application
  labels:
    team: backend
spec:
  type: metric_threshold
  enabled: true
  description: "HTTP 5xx error rate exceeds 5% for any service"
  evaluation:
    interval: 30s
    for: 3m
  condition:
    query: |
      sum(rate(http_requests_total{status=~"5.."}[5m])) by (service)
      /
      sum(rate(http_requests_total[5m])) by (service)
      * 100
    operator: ">"
    threshold: 5
    dataSource: metrics
  severity: high
  annotations:
    summary: "High error rate on {{ $labels.service }}: {{ $value | printf \"%.1f\" }}%"
  routing:
    channels:
      - slack-backend-alerts
```

#### Example 2: Log Pattern Alert (Fatal Errors)

```yaml
apiVersion: rayolly.io/v1
kind: AlertRule
metadata:
  name: fatal-log-detected
  namespace: application
spec:
  type: log_pattern
  enabled: true
  description: "Any FATAL level log detected in production"
  evaluation:
    interval: 15s
    for: 0s                    # Fire immediately
  condition:
    query: 'level="FATAL" AND environment="production"'
    operator: ">"
    threshold: 0               # Any occurrence
    dataSource: logs
    window: 1m
  severity: critical
  annotations:
    summary: "FATAL log in {{ $labels.service }}: {{ $labels.message | truncate 120 }}"
  routing:
    channels:
      - pagerduty-critical
      - slack-incidents
```

#### Example 3: Trace Latency Alert (P99)

```yaml
apiVersion: rayolly.io/v1
kind: AlertRule
metadata:
  name: checkout-latency-p99
  namespace: application
spec:
  type: trace_latency
  enabled: true
  description: "Checkout endpoint P99 latency exceeds SLO"
  evaluation:
    interval: 30s
    for: 5m
  condition:
    query: |
      histogram_quantile(0.99,
        sum(rate(http_request_duration_bucket{
          service="checkout",
          endpoint="/api/v1/checkout"
        }[5m])) by (le)
      )
    operator: ">"
    threshold: 2.0             # 2 seconds
    dataSource: traces
  severity: high
  annotations:
    summary: "Checkout P99 latency is {{ $value | printf \"%.2f\" }}s (SLO: 2s)"
    dashboard_url: "https://rayolly.example.com/d/svc/checkout?tab=latency"
  routing:
    channels:
      - slack-checkout-team
    escalation_policy: checkout-critical
```

#### Example 4: Log Absence Alert (Missing Healthcheck)

```yaml
apiVersion: rayolly.io/v1
kind: AlertRule
metadata:
  name: missing-healthcheck-log
  namespace: infrastructure
spec:
  type: log_absence
  enabled: true
  description: "Expected healthcheck log not seen for 3 minutes"
  evaluation:
    interval: 1m
    for: 3m
  condition:
    query: 'message="healthcheck OK" AND service="payment-gateway"'
    operator: "=="
    threshold: 0               # Zero occurrences = absence
    dataSource: logs
    window: 3m
  severity: high
  annotations:
    summary: "Payment gateway healthcheck missing for 3+ minutes"
  routing:
    channels:
      - pagerduty-payments
```

#### Example 5: SLO Burn Rate Alert

```yaml
apiVersion: rayolly.io/v1
kind: AlertRule
metadata:
  name: api-availability-slo-burn
  namespace: slo
spec:
  type: slo_burn_rate
  enabled: true
  description: "API availability SLO error budget burning too fast"
  slo:
    name: api-availability
    target: 99.9                # 99.9% availability
    window: 30d                 # 30-day rolling window
  burn_rate_windows:
    - long_window: 1h
      short_window: 5m
      burn_rate: 14.4
      severity: critical        # Budget exhausted in ~1 hour
    - long_window: 6h
      short_window: 30m
      burn_rate: 6
      severity: high            # Budget exhausted in ~6 hours
    - long_window: 1d
      short_window: 2h
      burn_rate: 3
      severity: medium          # Budget exhausted in ~2.4 days
  annotations:
    summary: "SLO burn rate {{ $value }}x — budget exhaustion in {{ $alert.budgetExhaustionEta }}"
  routing:
    channels:
      - slack-sre-alerts
    escalation_policy: slo-burn-rate
```

#### Example 6: Anomaly Detection Alert (AI-Powered)

```yaml
apiVersion: rayolly.io/v1
kind: AlertRule
metadata:
  name: anomaly-order-volume
  namespace: business
spec:
  type: anomaly
  enabled: true
  description: "AI detects anomalous order volume"
  anomaly:
    metric: 'sum(rate(orders_placed_total[5m]))'
    sensitivity: medium         # low | medium | high
    seasonality: auto           # auto | hourly | daily | weekly | none
    baseline_window: 14d        # How much history to learn from
    direction: both             # up | down | both
    min_deviation: 3.0          # Minimum standard deviations
  severity: high
  annotations:
    summary: "Anomalous order volume: {{ $value }} (expected {{ $alert.expected }})"
  routing:
    channels:
      - slack-business-alerts
      - email-commerce-team
```

#### Example 7: Predictive Alert (Disk Space)

```yaml
apiVersion: rayolly.io/v1
kind: AlertRule
metadata:
  name: disk-fill-prediction
  namespace: infrastructure
spec:
  type: predictive
  enabled: true
  description: "Predicted disk fill within 4 hours"
  predictive:
    metric: 'node_filesystem_avail_bytes{mountpoint="/"}'
    forecast_horizon: 4h
    breach_threshold: 0         # Will hit zero bytes free
    confidence: 0.85            # 85% confidence required
    algorithm: auto             # auto | prophet | holt_winters | linear
  severity: high
  annotations:
    summary: "Disk {{ $labels.mountpoint }} on {{ $labels.host }} predicted full in {{ $alert.timeToBreachHuman }}"
  routing:
    channels:
      - slack-infra-alerts
```

#### Example 8: Composite Alert (Multi-Signal Service Degradation)

```yaml
apiVersion: rayolly.io/v1
kind: AlertRule
metadata:
  name: payment-service-degradation
  namespace: application
spec:
  type: composite
  enabled: true
  description: "Payment service showing multiple degradation signals"
  evaluation:
    interval: 30s
    for: 2m
  conditions:
    logic: "A AND (B OR C)"
    rules:
      - id: A
        description: "Elevated latency"
        query: 'histogram_quantile(0.95, sum(rate(http_request_duration_bucket{service="payment"}[5m])) by (le)) > 1.5'
        dataSource: metrics
      - id: B
        description: "Elevated error logs"
        query: 'count(level="error" AND service="payment") > 50'
        dataSource: logs
        window: 5m
      - id: C
        description: "Database timeout pattern"
        query: 'count(message=~".*timeout.*" AND service="payment" AND component="db") > 10'
        dataSource: logs
        window: 5m
  severity: critical
  annotations:
    summary: "Payment service degradation — multiple signals firing"
  routing:
    channels:
      - pagerduty-payments
      - slack-incidents
```

#### Example 9: Log Count Rate Alert (Error Spike)

```yaml
apiVersion: rayolly.io/v1
kind: AlertRule
metadata:
  name: error-log-spike
  namespace: application
spec:
  type: log_pattern
  enabled: true
  description: "Error log volume spikes 3x above normal rate"
  evaluation:
    interval: 1m
    for: 2m
  condition:
    query: 'level="error"'
    dataSource: logs
    window: 5m
    compare:
      type: ratio_vs_baseline
      baseline_window: 1h
      operator: ">"
      threshold: 3.0            # 3x the normal rate
  severity: medium
  annotations:
    summary: "Error log volume {{ $value }}x above normal in {{ $labels.service }}"
  routing:
    channels:
      - slack-backend-alerts
```

#### Example 10: Kubernetes Pod Restart Alert

```yaml
apiVersion: rayolly.io/v1
kind: AlertRule
metadata:
  name: k8s-pod-restart-loop
  namespace: infrastructure
spec:
  type: metric_threshold
  enabled: true
  description: "Kubernetes pod restarting repeatedly"
  evaluation:
    interval: 1m
    for: 10m
  condition:
    query: |
      increase(kube_pod_container_status_restarts_total[30m]) > 5
    operator: ">"
    threshold: 5
    dataSource: metrics
  severity: high
  annotations:
    summary: "Pod {{ $labels.namespace }}/{{ $labels.pod }} restarted {{ $value }} times in 30m"
    runbook_url: "https://wiki.internal/runbooks/pod-restart-loop"
  routing:
    channels:
      - slack-k8s-alerts
```

#### Example 11: Certificate Expiry Predictive Alert

```yaml
apiVersion: rayolly.io/v1
kind: AlertRule
metadata:
  name: tls-cert-expiry
  namespace: security
spec:
  type: metric_threshold
  enabled: true
  description: "TLS certificate expires within 14 days"
  evaluation:
    interval: 5m
    for: 0s
  condition:
    query: |
      (tls_certificate_not_after - time()) / 86400
    operator: "<"
    threshold: 14               # Less than 14 days remaining
    dataSource: metrics
  severity: medium
  annotations:
    summary: "Certificate for {{ $labels.domain }} expires in {{ $value | printf \"%.0f\" }} days"
  routing:
    channels:
      - slack-security-alerts
      - email-security-team
```

---

## 5. AI-Powered Alerting

### 5.1 Anomaly-Based Alerts (No Manual Thresholds)

RayOlly automatically monitors every metric series for anomalies. No alert rules need to be created — the system detects anomalies out-of-the-box.

**How It Works**:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Anomaly Detection Pipeline                    │
│                                                                  │
│  ┌──────────┐    ┌──────────────┐    ┌─────────────────┐       │
│  │  Metric   │───▶│   Baseline   │───▶│   Deviation     │       │
│  │  Stream   │    │   Learner    │    │   Detector      │       │
│  └──────────┘    │  (14d window) │    │  (z-score > 3)  │       │
│                  └──────────────┘    └───────┬─────────┘       │
│                                              │                   │
│                  ┌──────────────┐    ┌───────▼─────────┐       │
│                  │   Context    │◀───│   Anomaly       │       │
│                  │   Enricher   │    │   Scorer        │       │
│                  │  (correlate  │    │  (severity,     │       │
│                  │   signals)   │    │   confidence)   │       │
│                  └──────┬───────┘    └─────────────────┘       │
│                         │                                        │
│                  ┌──────▼───────┐                                │
│                  │   Alert      │                                │
│                  │   Emitter    │                                │
│                  └──────────────┘                                │
└─────────────────────────────────────────────────────────────────┘
```

**Anomaly Detection Algorithms**:

| Algorithm | Use Case | Strengths |
|-----------|---------|-----------|
| **Isolation Forest** | Multi-dimensional metric anomalies | Fast, handles high-cardinality data |
| **Seasonal Decomposition (STL)** | Metrics with strong periodicity | Separates trend, season, residual |
| **DBSCAN Clustering** | Log pattern anomalies | Finds new clusters without predefined count |
| **Prophet** | Business metrics with complex seasonality | Handles holidays, special events |
| **Statistical (z-score)** | Simple metrics without strong patterns | Low cost, interpretable |

### 5.2 Alert Correlation (Group Related Alerts)

When multiple alerts fire within a time window, the correlation engine groups them into a single incident.

**Correlation Strategies**:

| Strategy | Description | Example |
|----------|------------|---------|
| **Topology-based** | Alerts on services sharing dependency paths | DB alert + all downstream service alerts |
| **Time-based** | Alerts firing within configurable window | 5 alerts within 2 minutes |
| **Label-based** | Alerts sharing common labels | All alerts with `host=web-prod-3` |
| **Causal graph** | AI infers causal relationships from historical data | Network alert → service timeout → error rate |

```yaml
# Correlation rule configuration
apiVersion: rayolly.io/v1
kind: AlertCorrelation
metadata:
  name: infra-cascade-correlation
spec:
  strategy: topology
  window: 5m
  group_by:
    - cluster
    - namespace
  suppress_symptoms: true      # Only notify for root cause alert
  min_group_size: 2            # Minimum alerts to form a group
```

### 5.3 Noise Reduction (Suppress Redundant/Transient Alerts)

| Technique | Description | Configuration |
|-----------|------------|---------------|
| **Deduplication** | Identical alerts merged into one | Dedup key: `rule_name + label_hash` |
| **Transient suppression** | Ignore alerts that resolve within N seconds | `suppress_if_resolves_within: 60s` |
| **Flap detection** | Detect and suppress alerts toggling on/off | `max_state_changes: 5 in 30m` |
| **Dependency suppression** | Suppress child alerts when parent fires | Based on service dependency graph |
| **Business hours filter** | Reduce severity outside business hours | `schedule: weekdays 09:00-18:00 UTC` |

### 5.4 Alert Priority Scoring (AI Determines Severity)

The AI engine assigns a priority score (0-100) to each alert based on multiple signals.

**Scoring Factors**:

| Factor | Weight | Description |
|--------|--------|------------|
| **Service criticality** | 25% | Business impact tier of the affected service |
| **Blast radius** | 20% | Number of downstream services/users affected |
| **Error budget impact** | 20% | Impact on SLO error budget |
| **Historical MTTR** | 15% | How long similar alerts typically take to resolve |
| **Time context** | 10% | Business hours, peak traffic, release window |
| **Repeat frequency** | 10% | First occurrence vs recurring pattern |

**Priority Mapping**:

| Score | Priority | Routing |
|-------|----------|---------|
| 80-100 | P1 — Critical | Page on-call immediately |
| 60-79 | P2 — High | Page on-call with 5m delay |
| 40-59 | P3 — Medium | Slack notification |
| 20-39 | P4 — Low | Email digest |
| 0-19 | P5 — Info | Dashboard only |

### 5.5 Root Cause Linking

When multiple correlated alerts fire, the AI engine identifies which is the probable root cause and which are symptoms.

```
Example: Database connection pool exhaustion cascade

Root Cause Alert (identified by AI):
  ├─ [ROOT] postgresql_active_connections > max_connections (95%)
  │
  Symptom Alerts (auto-suppressed, linked to root cause):
  ├─ [SYMPTOM] payment-service: connection timeout errors
  ├─ [SYMPTOM] payment-service: P99 latency > 5s
  ├─ [SYMPTOM] order-service: elevated error rate
  └─ [SYMPTOM] checkout-frontend: 503 errors
```

### 5.6 Predictive Alerting

The forecasting engine projects time series forward and fires alerts when a future breach is predicted with high confidence.

**Forecast Pipeline**:
1. Ingest last 14 days of metric history
2. Decompose into trend + seasonality + residual
3. Project forward by configured horizon (15m to 24h)
4. Compute confidence interval at each future point
5. If projected value breaches threshold with > 80% confidence, fire predictive alert
6. Include estimated time-to-breach in alert metadata

---

## 6. Alert Routing & Notification

### 6.1 Notification Channels

| Channel | Delivery Method | Configuration |
|---------|----------------|---------------|
| **Slack** | Bot message to channel or DM | Webhook URL or Slack App OAuth |
| **PagerDuty** | Event via Events API v2 | Integration key per service |
| **OpsGenie** | Alert API | API key + team routing |
| **Microsoft Teams** | Incoming webhook | Webhook URL per channel |
| **Email** | SMTP or SendGrid/SES | Recipient list or distribution group |
| **Webhook** | HTTP POST with JSON payload | URL + optional auth headers |
| **SMS** | Via Twilio integration | Phone numbers + Twilio credentials |

**Channel Configuration Example**:

```yaml
apiVersion: rayolly.io/v1
kind: NotificationChannel
metadata:
  name: slack-platform-alerts
spec:
  type: slack
  config:
    webhook_url: "${SLACK_WEBHOOK_PLATFORM}"   # Secret reference
    channel: "#platform-alerts"
    username: "RayOlly Alerts"
    icon_emoji: ":rotating_light:"
    mention_users_on_critical:
      - "@oncall-platform"
  defaults:
    include_chart: true         # Attach metric chart image
    include_runbook: true       # Include runbook link
    include_dashboard: true     # Include dashboard link
```

### 6.2 Routing Rules

```yaml
apiVersion: rayolly.io/v1
kind: AlertRouting
metadata:
  name: default-routing
spec:
  routes:
    # Critical → PagerDuty + Slack
    - match:
        severity: critical
      channels:
        - pagerduty-infra
        - slack-incidents
      repeat_interval: 5m

    # High → Slack with on-call mention
    - match:
        severity: high
      channels:
        - slack-platform-alerts
      repeat_interval: 15m

    # Medium → Slack
    - match:
        severity: medium
      channels:
        - slack-platform-alerts
      repeat_interval: 1h

    # Low → Email digest
    - match:
        severity: low
      channels:
        - email-daily-digest
      group_wait: 1h            # Batch low-sev alerts into hourly digest

    # Team-specific routing overrides
    - match:
        labels:
          team: payments
      channels:
        - slack-payments-alerts
        - pagerduty-payments

  # Default route for unmatched alerts
  default:
    channels:
      - slack-general-alerts
    repeat_interval: 4h
```

### 6.3 Escalation Policies

```yaml
apiVersion: rayolly.io/v1
kind: EscalationPolicy
metadata:
  name: infra-critical
spec:
  steps:
    - delay: 0m                # Immediate
      notify:
        - type: on_call_schedule
          schedule: infra-primary-oncall
        - type: channel
          channel: slack-incidents

    - delay: 10m               # If not acknowledged in 10 minutes
      notify:
        - type: on_call_schedule
          schedule: infra-secondary-oncall
        - type: user
          user: engineering-manager@example.com

    - delay: 30m               # If still not acknowledged
      notify:
        - type: user
          user: vp-engineering@example.com
        - type: channel
          channel: slack-leadership-alerts

  repeat:
    enabled: true
    interval: 15m              # Re-notify every 15 minutes until acknowledged
    max_repeats: 10
```

### 6.4 On-Call Schedules

RayOlly provides basic built-in on-call scheduling with full PagerDuty/OpsGenie integration for complex rotations.

```yaml
apiVersion: rayolly.io/v1
kind: OnCallSchedule
metadata:
  name: infra-primary-oncall
spec:
  timezone: "America/Los_Angeles"
  rotation:
    type: weekly               # weekly | daily | custom
    handoff_time: "09:00"      # Handoff at 9 AM
    handoff_day: monday
    participants:
      - user: alice@example.com
      - user: bob@example.com
      - user: carol@example.com
  overrides:                   # Manual overrides
    - start: "2026-03-25T00:00:00"
      end: "2026-03-27T00:00:00"
      user: dave@example.com
      reason: "Covering for Alice (PTO)"
  external_integration:
    type: pagerduty
    schedule_id: "PABCDEF"     # Sync with PagerDuty schedule
    sync_direction: pull       # pull | push | bidirectional
```

### 6.5 Notification Templates

```yaml
apiVersion: rayolly.io/v1
kind: NotificationTemplate
metadata:
  name: slack-critical-template
spec:
  type: slack
  template: |
    :red_circle: *{{ .Alert.Severity | upper }} ALERT: {{ .Alert.Name }}*

    *Summary*: {{ .Alert.Annotations.summary }}
    *Service*: {{ .Alert.Labels.service }}
    *Environment*: {{ .Alert.Labels.environment }}
    *Firing Since*: {{ .Alert.FiredAt | timeAgo }}
    *Duration*: {{ .Alert.Duration }}

    {{ if .Alert.Annotations.description }}
    *Details*: {{ .Alert.Annotations.description }}
    {{ end }}

    {{ if .Alert.Annotations.runbook_url }}
    :book: <{{ .Alert.Annotations.runbook_url }}|View Runbook>
    {{ end }}

    :chart_with_upwards_trend: <{{ .Alert.DashboardURL }}|View Dashboard>
    :mag: <{{ .Alert.InvestigateURL }}|Investigate in RayOlly>

    {{ if .Alert.RelatedAlerts }}
    *Related Alerts* ({{ len .Alert.RelatedAlerts }}):
    {{ range .Alert.RelatedAlerts }}
    • {{ .Name }} ({{ .Severity }})
    {{ end }}
    {{ end }}
```

### 6.6 Alert Deduplication

Alerts are deduplicated using a composite key to prevent duplicate notifications.

```
Dedup Key = hash(tenant_id + rule_name + sorted_labels)
```

| Scenario | Behavior |
|----------|----------|
| Same alert fires again while active | Suppressed, update `lastEvaluatedAt` |
| Alert resolves then re-fires within `resolve_cooldown` | Suppressed (flap protection) |
| Same alert, different label set | Treated as separate alert instance |
| Rule modified while alert is active | New evaluation cycle, existing alert updated |

### 6.7 Muting/Silencing Rules

```yaml
apiVersion: rayolly.io/v1
kind: MuteRule
metadata:
  name: maintenance-window-us-east
spec:
  schedule:
    type: recurring            # one_time | recurring
    recurrence:
      day_of_week: sunday
      start_time: "02:00"
      end_time: "06:00"
      timezone: "America/New_York"
  matchers:
    - label: environment
      value: production
      operator: "="
    - label: region
      value: us-east-1
      operator: "="
  comment: "Weekly maintenance window for US East production"
  created_by: "alice@example.com"
```

---

## 7. Incident Management

### 7.1 Incident Lifecycle

```
┌──────────┐    ┌──────────────┐    ┌───────────────┐    ┌─────────────┐
│ DETECTED │───▶│ ACKNOWLEDGED │───▶│ INVESTIGATING │───▶│ MITIGATING  │
└──────────┘    └──────────────┘    └───────────────┘    └──────┬──────┘
     │                                                          │
     │          ┌──────────────┐    ┌───────────────┐          │
     │          │  POSTMORTEM  │◀───│   RESOLVED    │◀─────────┘
     │          └──────────────┘    └───────────────┘
     │
     └─────────────────────────────────────────────────▶ AUTO-RESOLVED
                    (condition clears within grace period)
```

| State | Description | Actions Available |
|-------|------------|-------------------|
| **Detected** | Alert fired, incident created | Acknowledge, assign, escalate |
| **Acknowledged** | Responder has seen the incident | Begin investigation, update severity |
| **Investigating** | Active investigation in progress | Add notes, run queries, attach findings |
| **Mitigating** | Root cause identified, applying fix | Deploy fix, run remediation |
| **Resolved** | Service restored to normal | Close incident, start postmortem |
| **Postmortem** | Reviewing incident for improvements | Write postmortem, assign action items |
| **Auto-Resolved** | Alert condition cleared automatically | No action needed, logged for history |

### 7.2 Incident Creation

**Automatic (from alerts)**:

```yaml
# Alert rule with auto-incident creation
spec:
  incident:
    auto_create: true
    severity_mapping:
      critical: P1
      high: P2
      medium: P3
    assign_to: on_call          # on_call | specific_user | team
    create_war_room: true       # Auto-create Slack channel for P1/P2
    communication:
      notify_stakeholders: true
      status_page_update: true  # For P1 only
```

**Manual**:

```
POST /api/v1/incidents
Content-Type: application/json

{
  "title": "Checkout service returning 503 errors",
  "severity": "P1",
  "description": "Multiple customers reporting checkout failures. Error rate spiked at 14:23 UTC.",
  "commander": "alice@example.com",
  "responders": ["bob@example.com", "carol@example.com"],
  "related_alerts": ["alert-id-123", "alert-id-456"],
  "affected_services": ["checkout", "payment-gateway"],
  "tags": ["customer-facing", "revenue-impacting"]
}
```

### 7.3 Incident Timeline

The incident timeline is automatically populated with events from all observability signals.

```
INCIDENT INC-2026-0342: "Checkout Service 503 Errors"
Severity: P1 | Commander: Alice | Status: Mitigating

Timeline:
─────────────────────────────────────────────────────────────────

14:21:00  [METRIC]    payment-gateway: DB connection pool at 92%
14:22:30  [ANOMALY]   AI detected unusual connection pool growth rate
14:23:00  [ALERT]     payment-gateway-error-rate fired (5.2% > 5%)
14:23:05  [INCIDENT]  INC-2026-0342 auto-created from alert
14:23:05  [NOTIFY]    PagerDuty page sent to Alice (on-call)
14:23:12  [ALERT]     checkout-p99-latency fired (3.4s > 2s)
14:23:12  [CORRELATE] Alert correlated to INC-2026-0342
14:23:45  [ACK]       Alice acknowledged the incident
14:24:00  [AI-RCA]    Root cause analysis started
14:24:15  [AI-RCA]    Probable root cause: PostgreSQL connection leak
                       in payment-gateway (deploy v2.14.3, 13:45 UTC)
14:24:15  [DEPLOY]    Deployment detected: payment-gateway v2.14.3
14:25:00  [NOTE]      Alice: "Confirming DB connection leak hypothesis"
14:27:00  [RUNBOOK]   AI suggested: "Restart payment-gateway pods"
14:28:00  [ACTION]    Bob: Initiated rolling restart of payment-gateway
14:31:00  [METRIC]    payment-gateway: DB connections dropping
14:33:00  [METRIC]    checkout error rate back to 0.1%
14:35:00  [RESOLVED]  Alice marked incident as resolved
14:35:00  [AI]        Postmortem draft generated

─────────────────────────────────────────────────────────────────
Duration: 12 minutes | MTTR: 12m | Customer Impact: ~340 failed checkouts
```

### 7.4 Incident Severity Levels

| Level | Name | Description | Response Time | Communication |
|-------|------|------------|---------------|---------------|
| **P1** | Critical | Revenue-impacting, widespread user impact | < 5 minutes | Exec notification, status page, war room |
| **P2** | High | Significant degradation, partial user impact | < 15 minutes | Team notification, war room |
| **P3** | Medium | Limited impact, workaround available | < 1 hour | Slack notification |
| **P4** | Low | Minor issue, cosmetic or edge case | < 4 hours | Ticket creation |
| **P5** | Info | Informational, no user impact | Next business day | Email digest |

### 7.5 Incident Commander Assignment

```yaml
apiVersion: rayolly.io/v1
kind: IncidentPolicy
metadata:
  name: commander-assignment
spec:
  auto_assign:
    P1:
      strategy: on_call
      schedule: senior-sre-oncall
      fallback: engineering-manager
    P2:
      strategy: on_call
      schedule: sre-primary-oncall
    P3:
      strategy: alert_owner       # Creator of the alert rule
    P4:
      strategy: team_lead
      team_from_label: team       # Use "team" label from the alert
    P5:
      strategy: none              # No commander needed
```

### 7.6 War Room (Collaborative Incident Workspace)

For P1/P2 incidents, RayOlly auto-creates a dedicated war room.

**War Room Features**:

| Feature | Description |
|---------|------------|
| **Dedicated Slack channel** | Auto-created `#inc-2026-0342-checkout-503` |
| **Embedded dashboards** | Real-time metrics for affected services |
| **Shared timeline** | All responders see the same auto-populated timeline |
| **AI assistant** | Chat-based RCA queries: "What changed in the last hour?" |
| **Action tracker** | Track remediation steps with owners and status |
| **Stakeholder updates** | Templated updates posted to status channel on cadence |

**War Room Creation**:

```
POST /api/v1/incidents/{incident_id}/war-room
{
  "create_slack_channel": true,
  "invite_responders": true,
  "pin_dashboards": [
    "dashboard-id-checkout-overview",
    "dashboard-id-payment-gateway"
  ],
  "enable_ai_assistant": true,
  "stakeholder_update_cadence": "15m"
}
```

### 7.7 Communication Templates

```yaml
apiVersion: rayolly.io/v1
kind: IncidentTemplate
metadata:
  name: stakeholder-update
spec:
  type: stakeholder_update
  template: |
    *Incident Update: {{ .Incident.Title }}*
    Severity: {{ .Incident.Severity }} | Status: {{ .Incident.Status }}
    Commander: {{ .Incident.Commander }}

    *Current Situation*:
    {{ .Update.Summary }}

    *Impact*:
    - Affected Services: {{ .Incident.AffectedServices | join ", " }}
    - User Impact: {{ .Update.UserImpact }}
    - Duration: {{ .Incident.Duration }}

    *Next Steps*:
    {{ .Update.NextSteps }}

    *Next Update*: {{ .Update.NextUpdateTime }}
```

### 7.8 Status Page Integration

```yaml
apiVersion: rayolly.io/v1
kind: StatusPageIntegration
metadata:
  name: statuspage-io
spec:
  provider: statuspage_io       # statuspage_io | cachet | custom_webhook
  config:
    api_key: "${STATUSPAGE_API_KEY}"
    page_id: "abc123"
  auto_update:
    on_incident_create:
      severity_filter: [P1]     # Only P1 auto-posts to status page
      component_mapping:
        checkout: "cmp_checkout"
        payment-gateway: "cmp_payments"
      initial_status: major_outage
    on_incident_update:
      enabled: true
    on_incident_resolve:
      status: operational
      post_template: "The issue has been resolved. {{ .Incident.ResolutionSummary }}"
```

---

## 8. AI Incident Agent Integration

### 8.1 Auto-RCA During Incidents

When an incident is created, the AI RCA agent automatically starts investigating.

**RCA Agent Process**:

```
1. Gather context
   ├─ Triggering alert(s) and their metrics
   ├─ Related alerts (correlated)
   ├─ Recent deployments (within 2 hours)
   ├─ Recent config changes
   └─ Service dependency graph

2. Analyze signals
   ├─ Query anomalous metrics for affected services
   ├─ Search error logs for new patterns
   ├─ Analyze trace error paths
   └─ Compare current state vs baseline

3. Generate hypothesis
   ├─ Rank probable root causes by confidence
   ├─ Link supporting evidence for each
   └─ Suggest verification steps

4. Present findings
   ├─ Post to incident timeline
   ├─ Post to war room (if active)
   └─ Attach to incident record
```

**Example AI RCA Output**:

```json
{
  "incident_id": "INC-2026-0342",
  "analysis_duration": "42s",
  "probable_root_causes": [
    {
      "rank": 1,
      "confidence": 0.87,
      "summary": "Database connection leak introduced in payment-gateway v2.14.3",
      "evidence": [
        "payment-gateway deployed v2.14.3 at 13:45 UTC (38 minutes before incident)",
        "postgresql_active_connections increased linearly since 13:45",
        "New error pattern: 'connection pool exhausted' first seen at 14:21",
        "payment-gateway v2.14.2 did not exhibit this pattern over prior 7 days"
      ],
      "suggested_actions": [
        "Rollback payment-gateway to v2.14.2",
        "Alternatively: restart pods to clear leaked connections (temporary fix)"
      ]
    },
    {
      "rank": 2,
      "confidence": 0.12,
      "summary": "PostgreSQL primary under increased load from batch job",
      "evidence": [
        "batch-processor job started at 14:00 (normal schedule)",
        "DB CPU slightly elevated but within normal range"
      ],
      "suggested_actions": [
        "Check if batch job query plan changed"
      ]
    }
  ]
}
```

### 8.2 Suggested Runbooks

The AI agent matches incidents to relevant runbooks using semantic search.

```json
{
  "incident_id": "INC-2026-0342",
  "suggested_runbooks": [
    {
      "title": "Database Connection Pool Exhaustion",
      "url": "https://wiki.internal/runbooks/db-connection-pool",
      "relevance_score": 0.94,
      "matched_on": ["postgresql", "connection pool", "exhausted"]
    },
    {
      "title": "Payment Gateway Emergency Rollback",
      "url": "https://wiki.internal/runbooks/payment-rollback",
      "relevance_score": 0.81,
      "matched_on": ["payment-gateway", "deployment", "rollback"]
    }
  ]
}
```

### 8.3 Auto-Generated Incident Timeline

The AI continuously updates the incident timeline by correlating events from all observability signals — deployments, alerts, metric changes, log patterns, and human actions are woven into a single narrative.

### 8.4 Postmortem Draft Generation

After incident resolution, the AI generates a structured postmortem draft.

**Generated Postmortem Structure**:

```markdown
# Postmortem: INC-2026-0342 — Checkout Service 503 Errors

**Date**: 2026-03-19
**Duration**: 12 minutes (14:23 – 14:35 UTC)
**Severity**: P1
**Commander**: Alice
**Authors**: AI-Generated (review required)

## Summary
A database connection leak in payment-gateway v2.14.3 caused connection pool
exhaustion, leading to 503 errors on the checkout endpoint for approximately
12 minutes. ~340 checkout attempts failed during the incident window.

## Impact
- **User Impact**: 340 failed checkout attempts
- **Revenue Impact**: Estimated $12,400 in delayed/lost orders
- **SLO Impact**: Consumed 8.2% of monthly error budget

## Timeline
[Auto-populated from incident timeline — see Section 7.3]

## Root Cause
The payment-gateway v2.14.3 release introduced a code path where database
connections were not returned to the pool after timeout errors in the
new retry logic (commit abc123f). Under normal load, connections leaked
at ~2/minute, exhausting the 100-connection pool in ~50 minutes.

## Detection
- **Time to Detect**: 2 minutes (anomaly detected at 14:22:30)
- **Detection Method**: AI anomaly detection on connection pool metric
- **First Alert**: payment-gateway-error-rate at 14:23:00

## Resolution
Rolling restart of payment-gateway pods cleared the leaked connections.
Rollback to v2.14.2 deployed at 15:00 UTC as permanent fix.

## Action Items
| # | Action | Owner | Priority | Due |
|---|--------|-------|----------|-----|
| 1 | Fix connection leak in retry logic | Bob | P1 | 2026-03-21 |
| 2 | Add connection pool leak detection alert | Carol | P2 | 2026-03-26 |
| 3 | Add integration test for connection cleanup | Bob | P2 | 2026-03-26 |
| 4 | Reduce connection pool exhaustion detection time | Alice | P3 | 2026-04-02 |

## Lessons Learned
- AI anomaly detection caught the connection pool growth 1 minute before
  user-facing errors began — invest in acting on early warnings.
- The retry logic code path lacked unit tests for connection cleanup.
```

### 8.5 Similar Past Incident Search

The AI searches historical incidents using semantic similarity to surface relevant precedents.

```
POST /api/v1/incidents/{incident_id}/similar

Response:
{
  "similar_incidents": [
    {
      "id": "INC-2026-0198",
      "title": "Payment service DB connection timeout",
      "date": "2026-02-14",
      "similarity_score": 0.89,
      "resolution": "Increased connection pool size from 50 to 100",
      "duration": "23m",
      "root_cause": "Connection pool sizing insufficient for traffic spike"
    },
    {
      "id": "INC-2025-1847",
      "title": "Order service connection leak after v1.8.0 deploy",
      "date": "2025-11-30",
      "similarity_score": 0.82,
      "resolution": "Patched connection leak in HTTP client library",
      "duration": "45m",
      "root_cause": "HTTP client not closing connections on context cancellation"
    }
  ]
}
```

---

## 9. Alert & Incident API

### 9.1 CRUD for Alert Rules

```
# List alert rules
GET /api/v1/alerts/rules
  ?namespace=application
  &severity=critical,high
  &enabled=true
  &page=1&per_page=50

# Create alert rule
POST /api/v1/alerts/rules
Content-Type: application/json
{
  "apiVersion": "rayolly.io/v1",
  "kind": "AlertRule",
  "metadata": { ... },
  "spec": { ... }
}

# Get alert rule
GET /api/v1/alerts/rules/{rule_id}

# Update alert rule
PUT /api/v1/alerts/rules/{rule_id}
Content-Type: application/json
{ ... }

# Patch alert rule (partial update)
PATCH /api/v1/alerts/rules/{rule_id}
Content-Type: application/json
{
  "spec": {
    "enabled": false
  }
}

# Delete alert rule
DELETE /api/v1/alerts/rules/{rule_id}

# Test alert rule against historical data
POST /api/v1/alerts/rules/test
Content-Type: application/json
{
  "rule": { ... },
  "timeRange": { "from": "...", "to": "..." }
}
```

### 9.2 Alert History API

```
# List fired alerts (history)
GET /api/v1/alerts/history
  ?rule_id=high-cpu-usage
  &state=firing,resolved
  &severity=critical
  &from=2026-03-18T00:00:00Z
  &to=2026-03-19T00:00:00Z
  &service=checkout
  &page=1&per_page=100

Response:
{
  "alerts": [
    {
      "id": "alert-abc123",
      "rule_id": "high-cpu-usage",
      "rule_name": "High CPU Usage",
      "state": "resolved",
      "severity": "critical",
      "fired_at": "2026-03-18T14:23:00Z",
      "resolved_at": "2026-03-18T14:35:00Z",
      "duration": "12m",
      "labels": {
        "host": "web-prod-7",
        "service": "checkout",
        "environment": "production"
      },
      "annotations": {
        "summary": "High CPU on web-prod-7: 94.2%"
      },
      "value": 94.2,
      "incident_id": "INC-2026-0342",
      "notifications_sent": [
        {
          "channel": "slack-platform-alerts",
          "sent_at": "2026-03-18T14:23:05Z",
          "status": "delivered"
        },
        {
          "channel": "pagerduty-infra",
          "sent_at": "2026-03-18T14:23:06Z",
          "status": "delivered"
        }
      ]
    }
  ],
  "total": 47,
  "page": 1,
  "per_page": 100
}
```

### 9.3 Incident Management API

```
# List incidents
GET /api/v1/incidents
  ?severity=P1,P2
  &status=investigating,mitigating
  &commander=alice@example.com
  &from=2026-03-01T00:00:00Z
  &page=1&per_page=50

# Create incident
POST /api/v1/incidents
Content-Type: application/json
{
  "title": "Checkout service 503 errors",
  "severity": "P1",
  "description": "...",
  "commander": "alice@example.com",
  "affected_services": ["checkout", "payment-gateway"]
}

# Get incident
GET /api/v1/incidents/{incident_id}

# Update incident status
PATCH /api/v1/incidents/{incident_id}
Content-Type: application/json
{
  "status": "mitigating",
  "update_note": "Identified root cause as DB connection leak. Initiating rollback."
}

# Add timeline event
POST /api/v1/incidents/{incident_id}/timeline
Content-Type: application/json
{
  "type": "note",
  "content": "Confirmed: payment-gateway v2.14.3 introduced the connection leak",
  "author": "alice@example.com"
}

# Get incident timeline
GET /api/v1/incidents/{incident_id}/timeline

# Resolve incident
POST /api/v1/incidents/{incident_id}/resolve
Content-Type: application/json
{
  "resolution_summary": "Rolled back payment-gateway to v2.14.2",
  "resolution_type": "rollback"
}

# Get AI-generated postmortem
GET /api/v1/incidents/{incident_id}/postmortem

# Search similar incidents
POST /api/v1/incidents/{incident_id}/similar
```

### 9.4 Webhook Payload Formats

**Alert Firing Webhook**:

```json
{
  "version": "1.0",
  "event": "alert.firing",
  "timestamp": "2026-03-19T14:23:00Z",
  "alert": {
    "id": "alert-abc123",
    "rule_id": "high-error-rate",
    "rule_name": "High Error Rate",
    "state": "firing",
    "severity": "critical",
    "fired_at": "2026-03-19T14:23:00Z",
    "value": 5.2,
    "threshold": 5.0,
    "labels": {
      "service": "checkout",
      "environment": "production"
    },
    "annotations": {
      "summary": "High error rate on checkout: 5.2%",
      "runbook_url": "https://wiki.internal/runbooks/high-error-rate"
    }
  },
  "tenant": {
    "id": "tenant-123",
    "name": "acme-corp"
  },
  "links": {
    "alert_url": "https://rayolly.example.com/alerts/alert-abc123",
    "dashboard_url": "https://rayolly.example.com/d/svc/checkout",
    "investigate_url": "https://rayolly.example.com/investigate?alert=alert-abc123"
  }
}
```

**Alert Resolved Webhook**:

```json
{
  "version": "1.0",
  "event": "alert.resolved",
  "timestamp": "2026-03-19T14:35:00Z",
  "alert": {
    "id": "alert-abc123",
    "rule_id": "high-error-rate",
    "state": "resolved",
    "severity": "critical",
    "fired_at": "2026-03-19T14:23:00Z",
    "resolved_at": "2026-03-19T14:35:00Z",
    "duration": "12m",
    "value": 0.1,
    "labels": {
      "service": "checkout",
      "environment": "production"
    }
  }
}
```

**Incident Webhook**:

```json
{
  "version": "1.0",
  "event": "incident.status_change",
  "timestamp": "2026-03-19T14:25:00Z",
  "incident": {
    "id": "INC-2026-0342",
    "title": "Checkout Service 503 Errors",
    "severity": "P1",
    "previous_status": "acknowledged",
    "status": "investigating",
    "commander": "alice@example.com",
    "affected_services": ["checkout", "payment-gateway"],
    "related_alerts": ["alert-abc123", "alert-def456"],
    "duration": "2m",
    "url": "https://rayolly.example.com/incidents/INC-2026-0342"
  }
}
```

---

## 10. Frontend Components

### 10.1 Alert Management UI

```
┌─────────────────────────────────────────────────────────────────────────┐
│  RayOlly > Alerts > Rules                                    [+ New Rule]│
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Filters: [All Types ▼] [All Severities ▼] [All Namespaces ▼] [Search] │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │ Status │ Name                     │ Type      │ Sev  │ Firing │   │  │
│  │────────┼──────────────────────────┼───────────┼──────┼────────┼   │  │
│  │ ● ON   │ high-error-rate          │ Metric    │ CRIT │  2     │ ⋮ │  │
│  │ ● ON   │ checkout-latency-p99     │ Trace     │ HIGH │  1     │ ⋮ │  │
│  │ ● ON   │ fatal-log-detected       │ Log       │ CRIT │  0     │ ⋮ │  │
│  │ ● ON   │ payment-degradation      │ Composite │ CRIT │  0     │ ⋮ │  │
│  │ ● ON   │ api-availability-slo     │ SLO Burn  │ HIGH │  1     │ ⋮ │  │
│  │ ● ON   │ disk-fill-prediction     │ Predict   │ HIGH │  0     │ ⋮ │  │
│  │ ○ OFF  │ memory-usage-high        │ Metric    │ MED  │  -     │ ⋮ │  │
│  │ ● ON   │ k8s-pod-restart-loop     │ Metric    │ HIGH │  3     │ ⋮ │  │
│  │ ● ON   │ anomaly-order-volume     │ Anomaly   │ HIGH │  0     │ ⋮ │  │
│  │ ● ON   │ error-log-spike          │ Log       │ MED  │  0     │ ⋮ │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  Showing 10 of 147 rules          [< Prev] Page 1 of 15 [Next >]      │
│                                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│  Summary: 147 rules | 138 enabled | 7 currently firing | 12 alerts     │
└─────────────────────────────────────────────────────────────────────────┘
```

### 10.2 Alert Timeline/Feed

```
┌─────────────────────────────────────────────────────────────────────────┐
│  RayOlly > Alerts > Feed                    [Live ●] [Filter] [Export] │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  14:35:00  ✓ RESOLVED  high-error-rate                                 │
│            checkout | production | Duration: 12m                        │
│            Error rate back to 0.1%                                      │
│                                                                         │
│  14:23:12  ▲ FIRING    checkout-latency-p99            [View] [Ack]    │
│            checkout | production | P99: 3.4s (threshold: 2s)           │
│            ├─ Correlated with: high-error-rate                          │
│            └─ Incident: INC-2026-0342                                   │
│                                                                         │
│  14:23:00  ▲ FIRING    high-error-rate                 [View] [Ack]    │
│            checkout | production | Error rate: 5.2%                     │
│            ├─ AI Priority Score: 92/100                                 │
│            ├─ AI Root Cause: DB connection pool exhaustion              │
│            └─ Incident: INC-2026-0342 (auto-created)                   │
│                                                                         │
│  14:22:30  ◆ ANOMALY   payment-gateway connection pool                 │
│            AI detected abnormal growth rate (3.2σ above baseline)       │
│                                                                         │
│  13:45:00  ℹ INFO      Deployment detected                              │
│            payment-gateway v2.14.3 deployed to production               │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 10.3 Incident Dashboard

```
┌─────────────────────────────────────────────────────────────────────────┐
│  RayOlly > Incidents                               [+ New Incident]    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Active Incidents                                                       │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ 🔴 P1  INC-2026-0342  Checkout Service 503 Errors               │  │
│  │        Status: Mitigating | Commander: Alice | Duration: 12m     │  │
│  │        Services: checkout, payment-gateway                       │  │
│  │        Alerts: 3 | Responders: 3 | [Open War Room]              │  │
│  ├──────────────────────────────────────────────────────────────────┤  │
│  │ 🟠 P2  INC-2026-0341  Elevated latency on search service        │  │
│  │        Status: Investigating | Commander: Dave | Duration: 45m   │  │
│  │        Services: search-api                                      │  │
│  │        Alerts: 1 | Responders: 2                                 │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌─ Metrics ────────────────────────────────────────────────────────┐  │
│  │                                                                   │  │
│  │  Active: 2    MTTR (30d): 18m    Incidents (30d): 23             │  │
│  │  P1s (30d): 3    P2s (30d): 8    Avg Duration: 22m              │  │
│  │                                                                   │  │
│  │  MTTR Trend (Last 6 Months):                                     │  │
│  │  45m ┤                                                            │  │
│  │  30m ┤  ██                                                        │  │
│  │  15m ┤  ██  ██  ██                                                │  │
│  │   0m ┤  ██  ██  ██  ██  ██  ██                                    │  │
│  │      └──Oct──Nov──Dec──Jan──Feb──Mar                              │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  Recent Resolved                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ Severity │ ID              │ Title                  │ MTTR │ Date │  │
│  │──────────┼─────────────────┼────────────────────────┼──────┼──────│  │
│  │ P2       │ INC-2026-0340   │ Redis cluster failover │ 8m   │ 3/18 │  │
│  │ P3       │ INC-2026-0339   │ Certificate renewal    │ 5m   │ 3/17 │  │
│  │ P1       │ INC-2026-0335   │ Network partition      │ 34m  │ 3/15 │  │
│  │ P3       │ INC-2026-0334   │ Batch job timeout      │ 12m  │ 3/14 │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 10.4 On-Call Schedule View

```
┌─────────────────────────────────────────────────────────────────────────┐
│  RayOlly > On-Call > infra-primary-oncall                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Current On-Call: Alice (since Mon 9:00 AM PT)                         │
│  Next Handoff:   Bob   (Mon Mar 24, 9:00 AM PT)                       │
│                                                                         │
│  ┌─ March 2026 ────────────────────────────────────────────────────┐   │
│  │  Mon    Tue    Wed    Thu    Fri    Sat    Sun                   │   │
│  │  ┌──────────────────────────────────────────────┐               │   │
│  │  │17     18     19     20     21     22     23  │  Alice        │   │
│  │  └──────────────────────────────────────────────┘               │   │
│  │  ┌──────────────────────────────────────────────┐               │   │
│  │  │24     25     26     27     28     29     30  │  Bob          │   │
│  │  └──────────────────────────────────────────────┘               │   │
│  │  ┌──────────────────────────────────────────────┐               │   │
│  │  │31     1      2      3      4      5      6   │  Carol        │   │
│  │  └──────────────────────────────────────────────┘               │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  Overrides:                                                             │
│  • Mar 25-27: Dave (covering for Alice — PTO)                          │
│                                                                         │
│  [+ Add Override]  [Edit Rotation]  [Sync from PagerDuty]              │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 11. Performance Requirements

### 11.1 Alert Evaluation

| Metric | Target | Notes |
|--------|--------|-------|
| **Evaluation latency** | < 30s from data ingestion to alert state change | For 15s interval rules |
| **Evaluation throughput** | 10,000 rules per evaluation cycle per tenant | Batched by shared queries |
| **Rule storage** | 50,000 rules per tenant max | Soft limit, can be raised |
| **Concurrent evaluations** | 1,000 parallel rule evaluations | Across worker pool |

### 11.2 Notification Delivery

| Metric | Target | Notes |
|--------|--------|-------|
| **End-to-end latency** | < 60s from condition met to notification delivered | Includes evaluation + routing + delivery |
| **Webhook delivery** | < 5s from alert firing to HTTP POST sent | Excludes external network time |
| **Slack delivery** | < 10s from alert firing to Slack message | Via Slack API |
| **PagerDuty delivery** | < 10s from alert firing to PagerDuty event | Via Events API v2 |
| **Delivery reliability** | 99.9% successful delivery | With retry (3x exponential backoff) |

### 11.3 Incident Management

| Metric | Target | Notes |
|--------|--------|-------|
| **Incident creation** | < 2s from alert to incident created | Including war room creation |
| **Timeline update** | < 5s for new events to appear | Real-time via WebSocket |
| **AI RCA initiation** | < 10s from incident creation to RCA start | Background agent process |
| **AI RCA completion** | < 120s for initial analysis | Depends on data volume |
| **Similar incident search** | < 5s to return results | Vector similarity search |

### 11.4 Storage and Retention

| Data | Default Retention | Storage |
|------|-------------------|---------|
| **Alert rules** | Indefinite | PostgreSQL |
| **Alert history** | 90 days (hot), 1 year (cold) | ClickHouse + S3 |
| **Incident records** | 2 years | PostgreSQL |
| **Incident timelines** | 1 year | ClickHouse |
| **Postmortems** | Indefinite | PostgreSQL + S3 |
| **Notification logs** | 90 days | ClickHouse |

---

## 12. Success Metrics

### 12.1 Alert Quality Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Alert noise reduction** | 70% fewer alerts vs comparable static threshold setup | A/B comparison |
| **False positive rate** | < 5% of alerts are false positives | User feedback + auto-resolve tracking |
| **Alert-to-incident ratio** | > 0.3 (30%+ of alerts lead to real incidents) | Correlation analysis |
| **Mean time to detect (MTTD)** | < 2 minutes for P1 issues | From metric deviation to alert firing |
| **Predictive alert accuracy** | > 80% of predictive alerts verified | Threshold eventually breached |

### 12.2 Incident Response Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| **MTTA (acknowledge)** | < 5 minutes for P1 | Time from page to acknowledgement |
| **MTTR (resolve)** | 30% reduction in first 6 months | Compared to pre-RayOlly baseline |
| **AI RCA accuracy** | > 70% correct root cause in top-3 suggestions | Validated in postmortems |
| **Postmortem completion rate** | > 90% of P1/P2 incidents have postmortems | AI draft lowers friction |
| **Recurring incident rate** | < 15% of incidents are repeats of prior incidents | Action items from postmortems reduce recurrence |

### 12.3 Platform Adoption Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Alert rule creation** | > 50 rules per tenant within 30 days | Onboarding tracking |
| **PagerDuty/OpsGenie migration** | > 60% of alerts routed through RayOlly in 90 days | Integration usage |
| **Incident management adoption** | > 80% of P1/P2 incidents managed in RayOlly | vs external tools |
| **AI feature usage** | > 70% of incidents use AI RCA | Feature engagement |

---

## 13. Risks & Mitigations

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|------------|
| 1 | **Alert storm during major outage** — thousands of alerts fire simultaneously, overwhelming notification channels | High | High | Alert correlation groups related alerts; rate limiting on notification channels; dependency suppression auto-silences symptom alerts |
| 2 | **AI false positives erode trust** — anomaly detection alerts on normal variations, causing alert fatigue | Medium | High | Conservative default sensitivity; user feedback loop to retrain models; 2-week learning period before anomaly alerts activate; easy per-metric opt-out |
| 3 | **Notification delivery failure** — Slack/PagerDuty API outage prevents alert delivery | Medium | Critical | Multi-channel fallback (if Slack fails, try email); delivery confirmation tracking; dead letter queue for retry; health checks on notification channels |
| 4 | **Alert evaluation lag during data ingestion spikes** — high ingest volume delays metric availability | Medium | High | Dedicated evaluation cluster separate from ingest; priority queues for critical rules; pre-aggregated metrics for common alert queries |
| 5 | **On-call burnout from excessive pages** — too many P1/P2 alerts pages responders too frequently | Medium | Medium | AI priority scoring reduces false critical alerts; burn rate tracking for on-call load; automatic escalation load balancing |
| 6 | **Incident management tool fragmentation** — teams continue using external tools alongside RayOlly | High | Medium | Bidirectional sync with PagerDuty/OpsGenie; gradual migration path; superior AI-powered features as incentive to consolidate |
| 7 | **Complex composite rules cause evaluation timeouts** — multi-condition rules with heavy queries exceed evaluation window | Low | Medium | Query complexity scoring at rule creation; timeout per rule with degradation to simpler fallback; rule optimization suggestions |
| 8 | **SLO burn rate calculation drift** — clock skew or data gaps cause inaccurate error budget tracking | Low | High | NTP synchronization requirements; gap-fill interpolation; data completeness checks before SLO evaluation; manual budget adjustment API |
| 9 | **Postmortem generation hallucination** — AI includes incorrect information in postmortem drafts | Medium | Medium | All AI-generated content clearly marked as "draft — requires human review"; evidence links for every claim; confidence scores per section |
| 10 | **Multi-tenant alert isolation failure** — one tenant's alert storm affects evaluation latency for others | Low | Critical | Per-tenant evaluation resource quotas; tenant-level rate limiting; isolated evaluation workers per tier; circuit breaker on runaway rules |

---

## Appendix A: Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Alert & Incident Architecture                    │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │   Metrics    │  │    Logs      │  │   Traces     │   Data       │
│  │  (ClickHouse)│  │ (ClickHouse) │  │ (ClickHouse) │   Sources    │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘              │
│         │                  │                  │                       │
│  ┌──────▼──────────────────▼──────────────────▼───────┐             │
│  │              Alert Evaluation Engine                 │             │
│  │  ┌────────────┐  ┌────────────┐  ┌──────────────┐  │             │
│  │  │  Rule      │  │  Anomaly   │  │  Predictive  │  │             │
│  │  │  Evaluator │  │  Detector  │  │  Engine      │  │             │
│  │  └────────────┘  └────────────┘  └──────────────┘  │             │
│  └───────────────────────┬────────────────────────────┘             │
│                          │                                           │
│  ┌───────────────────────▼────────────────────────────┐             │
│  │              Alert State Manager                    │             │
│  │  ┌────────────┐  ┌────────────┐  ┌──────────────┐  │             │
│  │  │ Dedup &    │  │ Correlation│  │  Priority    │  │             │
│  │  │ Suppress   │  │ Engine     │  │  Scorer      │  │             │
│  │  └────────────┘  └────────────┘  └──────────────┘  │             │
│  └───────────────────────┬────────────────────────────┘             │
│                          │                                           │
│  ┌───────────────────────▼────────────────────────────┐             │
│  │              Notification Router                    │             │
│  │  ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐          │             │
│  │  │ Slack │ │Pager  │ │ Email │ │Webhook│  ...      │             │
│  │  │       │ │Duty   │ │       │ │       │           │             │
│  │  └───────┘ └───────┘ └───────┘ └───────┘          │             │
│  └───────────────────────┬────────────────────────────┘             │
│                          │                                           │
│  ┌───────────────────────▼────────────────────────────┐             │
│  │              Incident Manager                       │             │
│  │  ┌────────────┐  ┌────────────┐  ┌──────────────┐  │             │
│  │  │ Lifecycle  │  │  War Room  │  │  AI Agent    │  │             │
│  │  │ Manager    │  │  Manager   │  │  (RCA)       │  │             │
│  │  └────────────┘  └────────────┘  └──────────────┘  │             │
│  └────────────────────────────────────────────────────┘             │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Appendix B: Migration Guide from Existing Tools

| Source Tool | Migration Path |
|-------------|---------------|
| **Prometheus Alertmanager** | Import alerting rules via PromQL compatibility; map receivers to RayOlly notification channels; import silences as mute rules |
| **Grafana Alerts** | Convert Grafana alert rules to RayOlly YAML format (automated converter provided); map notification policies to routing rules |
| **PagerDuty** | Bidirectional integration — keep PagerDuty for on-call, route alerts from RayOlly; or gradually migrate schedules to built-in |
| **OpsGenie** | Same pattern as PagerDuty — integration-first, optional full migration |
| **Datadog Monitors** | Import monitor definitions via API conversion tool; map Datadog notification channels to RayOlly channels |

---

*PRD-09 v1.0 | RayOlly Alerting & Incident Management | AI-Native Observability Platform*
