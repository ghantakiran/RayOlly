# PRD-13: Deployment, Infrastructure & Scalability

**Product**: RayOlly — AI-Native Observability Platform
**Version**: 1.0
**Date**: 2026-03-19
**Status**: Draft
**Parent**: PRD-00 Platform Vision & Architecture
**Dependencies**: All PRDs (PRD-13 is the deployment substrate for the entire platform)

---

## 1. Executive Summary

RayOlly's deployment infrastructure is the foundation upon which the entire AI-native observability platform operates. This PRD defines how RayOlly is packaged, deployed, scaled, and operated across three deployment models: fully managed SaaS, self-hosted on customer infrastructure, and a hybrid model where the data plane runs on-premises while the control plane remains SaaS-managed.

The infrastructure is Kubernetes-native from the ground up. Every component runs as a K8s workload, managed through Helm charts and a custom Kubernetes Operator. The architecture supports scaling from a single-node development setup processing 10K events/sec to a multi-region production cluster handling 10M+ events/sec — with linear horizontal scalability, multi-AZ high availability, and sub-15-minute disaster recovery.

**Key Design Decisions**:
- Kubernetes as the sole production orchestration target (Docker Compose for dev only)
- Helm + Operator pattern for lifecycle management across all deployment models
- gRPC for synchronous inter-service communication; NATS JetStream for async events
- ClickHouse as the primary analytical store with S3/MinIO for cold storage
- GitOps (ArgoCD) as the canonical deployment mechanism for SaaS
- Feature parity across all deployment models — self-hosted customers get every capability

---

## 2. Goals & Non-Goals

### Goals

- Support three deployment models (SaaS, self-hosted, hybrid) with full feature parity
- Provide Kubernetes-native deployment via Helm charts and a custom Operator
- Enable horizontal scaling from 10K to 10M+ events/sec with linear cost scaling
- Achieve 99.95% SaaS availability through multi-AZ, multi-region architecture
- Meet RPO < 1 minute and RTO < 15 minutes for disaster recovery
- Support air-gapped installations for regulated industries
- Deliver a self-monitoring (dogfooding) capability — RayOlly observes itself
- Provide automated CI/CD with canary deployments and rollback
- Enable multi-tenant SaaS with strong isolation guarantees
- Optimize infrastructure costs through spot instances, right-sizing, and storage tiering

### Non-Goals

- Supporting non-Kubernetes orchestrators (Docker Swarm, Nomad, ECS native) in v1.0
- Bare-metal deployment without containerization
- Building a proprietary container runtime
- Supporting Kubernetes versions older than 1.28
- Providing managed database services (customers bring their own or use bundled)
- Windows container support (Linux containers only)

---

## 3. Deployment Models

### 3.1 SaaS (Fully Managed)

RayOlly operates the entire stack. Customers send data via OTEL collectors and access the platform through the web UI and API.

```
┌──────────────────────────────────────────────────────────────┐
│                    Customer Environment                        │
│  ┌─────────────────┐  ┌─────────────────┐                    │
│  │  OTEL Collector  │  │  RayOlly Agent   │                    │
│  └────────┬────────┘  └────────┬────────┘                    │
└───────────┼─────────────────────┼────────────────────────────┘
            │                     │
            ▼                     ▼
┌──────────────────────────────────────────────────────────────┐
│                RayOlly SaaS (Managed by RayOlly)              │
│                                                                │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐   │
│  │   Gateway    │  │   Ingester    │  │   All Services    │   │
│  │  (Regional)  │  │  (Regional)   │  │   (Regional)      │   │
│  └─────────────┘  └──────────────┘  └───────────────────┘   │
│                                                                │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  ClickHouse │ NATS │ Redis │ PostgreSQL │ S3            │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

**SaaS Regions (GA)**: us-east-1, us-west-2, eu-west-1, ap-southeast-1
**SaaS Regions (Post-GA)**: eu-central-1, ap-northeast-1, ca-central-1

### 3.2 Self-Hosted (Customer Infrastructure)

The customer operates the full RayOlly stack on their own Kubernetes cluster. RayOlly provides Helm charts, the Operator, and optional support.

```
┌──────────────────────────────────────────────────────────────┐
│              Customer Kubernetes Cluster                       │
│                                                                │
│  ┌──────────────────────────────────────────────────────┐    │
│  │               RayOlly Namespace                        │    │
│  │                                                        │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐│    │
│  │  │ Gateway  │ │ Ingester │ │  Query   │ │ AI Engine││    │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘│    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐│    │
│  │  │ Storage  │ │ Alerter  │ │Scheduler │ │   Web    ││    │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘│    │
│  │  ┌──────────┐ ┌──────────┐                           │    │
│  │  │  Agent   │ │ Operator │                           │    │
│  │  │ Runtime  │ │          │                           │    │
│  │  └──────────┘ └──────────┘                           │    │
│  │                                                        │    │
│  │  ┌─────────────────────────────────────────────────┐  │    │
│  │  │ ClickHouse │ NATS │ Redis │ PostgreSQL │ MinIO  │  │    │
│  │  └─────────────────────────────────────────────────┘  │    │
│  └──────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

### 3.3 Hybrid (Data Plane Self-Hosted, Control Plane SaaS)

Customer data never leaves their environment. The RayOlly SaaS control plane manages configuration, dashboards, and AI model updates.

```
┌──────────────────────────────────┐    ┌─────────────────────────┐
│   Customer Data Plane (On-Prem)   │    │  RayOlly Control Plane  │
│                                    │    │       (SaaS)             │
│  ┌──────────┐ ┌──────────┐       │    │                          │
│  │ Ingester │ │  Query   │       │◄──►│  Config sync             │
│  └──────────┘ └──────────┘       │    │  Dashboard definitions   │
│  ┌──────────┐ ┌──────────┐       │    │  Alert rules             │
│  │ Storage  │ │ AI Engine│       │    │  Model updates           │
│  └──────────┘ └──────────┘       │    │  License management      │
│  ┌──────────────────────────┐    │    │  Usage telemetry         │
│  │ ClickHouse │ NATS │ MinIO│    │    │  (no customer data)      │
│  └──────────────────────────┘    │    └─────────────────────────┘
└──────────────────────────────────┘
```

### 3.4 Feature Parity Matrix

| Feature | SaaS | Self-Hosted | Hybrid |
|---------|------|-------------|--------|
| Log ingestion & search | Yes | Yes | Yes |
| Metrics & infrastructure monitoring | Yes | Yes | Yes |
| Distributed tracing & APM | Yes | Yes | Yes |
| AI anomaly detection | Yes | Yes | Yes |
| AI Agents (cloud LLM) | Yes | Yes (requires outbound) | Yes |
| AI Agents (local models) | N/A | Yes | Yes |
| Natural language queries | Yes | Yes | Yes |
| Dashboards & alerting | Yes | Yes | Yes |
| Multi-tenancy | Yes | Yes | Yes |
| SSO / SAML / OIDC | Yes | Yes | Yes |
| Auto-scaling | Managed | Customer-managed | Split |
| Upgrades | Automatic | Customer-initiated | Split |
| Air-gapped operation | No | Yes | No |
| Data residency control | Region selection | Full control | Full control |
| Custom agent marketplace | Yes | Enterprise license | Enterprise license |
| SLA guarantee | 99.95% | Self-managed | 99.9% (control plane) |

---

## 4. Kubernetes-Native Architecture

### 4.1 Component Workload Types

| Component | Workload Type | Stateful? | Replicas (min HA) |
|-----------|--------------|-----------|-------------------|
| rayolly-gateway | Deployment | No | 3 |
| rayolly-ingester | Deployment | No | 3 |
| rayolly-query | Deployment | No | 2 |
| rayolly-storage | Deployment | No | 2 |
| rayolly-ai-engine | Deployment | No | 2 |
| rayolly-agent-runtime | Deployment | No | 2 |
| rayolly-alerter | Deployment | No | 2 |
| rayolly-scheduler | Deployment | No | 1 (leader-elected) |
| rayolly-web | Deployment | No | 2 |
| rayolly-operator | Deployment | No | 1 (leader-elected) |
| clickhouse | StatefulSet | Yes | 4 (2 shards x 2 replicas) |
| nats | StatefulSet | Yes | 3 |
| redis | StatefulSet | Yes | 3 (sentinel) |
| postgresql | StatefulSet | Yes | 3 (patroni) |

### 4.2 Helm Chart Structure

```
rayolly/
├── Chart.yaml
├── values.yaml
├── values-small.yaml
├── values-medium.yaml
├── values-large.yaml
├── values-enterprise.yaml
├── charts/
│   ├── clickhouse/
│   ├── nats/
│   ├── redis/
│   └── postgresql/
├── templates/
│   ├── _helpers.tpl
│   ├── NOTES.txt
│   ├── namespace.yaml
│   ├── serviceaccount.yaml
│   ├── configmap-global.yaml
│   ├── secret.yaml
│   ├── gateway/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── hpa.yaml
│   │   ├── pdb.yaml
│   │   └── ingress.yaml
│   ├── ingester/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── hpa.yaml
│   │   └── pdb.yaml
│   ├── query/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── hpa.yaml
│   │   └── pdb.yaml
│   ├── storage/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   └── pdb.yaml
│   ├── ai-engine/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── hpa.yaml
│   │   └── pdb.yaml
│   ├── agent-runtime/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── hpa.yaml
│   │   └── pdb.yaml
│   ├── alerter/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   └── pdb.yaml
│   ├── scheduler/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   └── lease.yaml
│   ├── web/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   └── ingress.yaml
│   ├── operator/
│   │   ├── deployment.yaml
│   │   ├── serviceaccount.yaml
│   │   ├── clusterrole.yaml
│   │   └── clusterrolebinding.yaml
│   ├── networkpolicies/
│   │   └── default-deny.yaml
│   └── monitoring/
│       ├── servicemonitor.yaml
│       └── prometheusrule.yaml
└── crds/
    ├── rayolly.io_rayollyclusters.yaml
    ├── rayolly.io_rayollypipelines.yaml
    └── rayolly.io_rayollytenants.yaml
```

### 4.3 Custom Resource Definitions (CRDs)

#### RayOllyCluster CRD

```yaml
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: rayollyclusters.rayolly.io
spec:
  group: rayolly.io
  versions:
    - name: v1alpha1
      served: true
      storage: true
      schema:
        openAPIV3Schema:
          type: object
          properties:
            spec:
              type: object
              properties:
                version:
                  type: string
                  description: "RayOlly platform version"
                deploymentSize:
                  type: string
                  enum: ["small", "medium", "large", "enterprise"]
                components:
                  type: object
                  properties:
                    gateway:
                      type: object
                      properties:
                        replicas: { type: integer }
                        resources:
                          type: object
                          properties:
                            cpu: { type: string }
                            memory: { type: string }
                    ingester:
                      type: object
                      properties:
                        replicas: { type: integer }
                        resources:
                          type: object
                          properties:
                            cpu: { type: string }
                            memory: { type: string }
                    query:
                      type: object
                      properties:
                        replicas: { type: integer }
                        resources:
                          type: object
                          properties:
                            cpu: { type: string }
                            memory: { type: string }
                storage:
                  type: object
                  properties:
                    clickhouse:
                      type: object
                      properties:
                        shards: { type: integer }
                        replicasPerShard: { type: integer }
                        storageClass: { type: string }
                        storageSize: { type: string }
                    objectStorage:
                      type: object
                      properties:
                        provider: { type: string, enum: ["s3", "gcs", "azure", "minio"] }
                        bucket: { type: string }
                        endpoint: { type: string }
                highAvailability:
                  type: object
                  properties:
                    enabled: { type: boolean }
                    multiAZ: { type: boolean }
                    minAvailabilityZones: { type: integer }
                aiEngine:
                  type: object
                  properties:
                    llmProvider:
                      type: string
                      enum: ["claude", "local", "openai"]
                    localModelPath: { type: string }
                    gpuEnabled: { type: boolean }
            status:
              type: object
              properties:
                phase:
                  type: string
                  enum: ["Pending", "Provisioning", "Running", "Degraded", "Failed"]
                components:
                  type: object
                  additionalProperties:
                    type: object
                    properties:
                      ready: { type: boolean }
                      replicas: { type: integer }
                      readyReplicas: { type: integer }
                conditions:
                  type: array
                  items:
                    type: object
                    properties:
                      type: { type: string }
                      status: { type: string }
                      lastTransitionTime: { type: string }
                      reason: { type: string }
                      message: { type: string }
  scope: Namespaced
  names:
    plural: rayollyclusters
    singular: rayollycluster
    kind: RayOllyCluster
    shortNames: ["roc"]
```

#### RayOllyPipeline CRD

```yaml
apiVersion: rayolly.io/v1alpha1
kind: RayOllyPipeline
metadata:
  name: production-pipeline
spec:
  source:
    type: otlp
    protocols: ["grpc", "http"]
  processors:
    - name: k8s-enrichment
      type: enrichment
      config:
        addClusterName: true
        addNamespace: true
        addPodLabels: true
    - name: pii-redaction
      type: transform
      config:
        rules:
          - field: "body"
            pattern: "\\b\\d{3}-\\d{2}-\\d{4}\\b"
            replacement: "[REDACTED-SSN]"
          - field: "body"
            pattern: "\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Z|a-z]{2,}\\b"
            replacement: "[REDACTED-EMAIL]"
    - name: severity-classifier
      type: classification
      config:
        model: "built-in/severity-v2"
  destinations:
    - name: hot-storage
      type: clickhouse
      retention: 7d
    - name: warm-storage
      type: clickhouse
      retention: 30d
    - name: cold-storage
      type: s3
      retention: 365d
```

### 4.4 Helm Values: Small Deployment (up to 50K events/sec)

```yaml
# values-small.yaml — Development / Small Production
# Target: up to 50K events/sec, 500GB/day ingestion
# Cluster: 3-5 nodes, 16 vCPU / 64GB RAM each

global:
  imageRegistry: registry.rayolly.io
  imageTag: "1.0.0"
  imagePullPolicy: IfNotPresent
  storageClass: "gp3"
  domain: "rayolly.example.com"
  tls:
    enabled: true
    issuer: "letsencrypt-prod"

gateway:
  replicas: 2
  resources:
    requests:
      cpu: "500m"
      memory: "512Mi"
    limits:
      cpu: "2"
      memory: "1Gi"
  autoscaling:
    enabled: true
    minReplicas: 2
    maxReplicas: 5
    targetCPUUtilization: 70

ingester:
  replicas: 2
  resources:
    requests:
      cpu: "1"
      memory: "1Gi"
    limits:
      cpu: "4"
      memory: "4Gi"
  autoscaling:
    enabled: true
    minReplicas: 2
    maxReplicas: 8
    targetCPUUtilization: 65
    customMetrics:
      - type: nats
        metric: queue_depth
        threshold: 10000

query:
  replicas: 2
  resources:
    requests:
      cpu: "1"
      memory: "2Gi"
    limits:
      cpu: "4"
      memory: "8Gi"
  autoscaling:
    enabled: true
    minReplicas: 2
    maxReplicas: 6
    targetCPUUtilization: 70

storage:
  replicas: 2
  resources:
    requests:
      cpu: "500m"
      memory: "1Gi"
    limits:
      cpu: "2"
      memory: "2Gi"

aiEngine:
  replicas: 1
  resources:
    requests:
      cpu: "2"
      memory: "4Gi"
    limits:
      cpu: "4"
      memory: "8Gi"
  gpu:
    enabled: false
  llm:
    provider: "claude"
    model: "claude-sonnet-4-20250514"

agentRuntime:
  replicas: 1
  resources:
    requests:
      cpu: "1"
      memory: "2Gi"
    limits:
      cpu: "2"
      memory: "4Gi"

alerter:
  replicas: 2
  resources:
    requests:
      cpu: "500m"
      memory: "512Mi"
    limits:
      cpu: "1"
      memory: "1Gi"

scheduler:
  replicas: 1
  resources:
    requests:
      cpu: "250m"
      memory: "256Mi"
    limits:
      cpu: "500m"
      memory: "512Mi"

web:
  replicas: 2
  resources:
    requests:
      cpu: "250m"
      memory: "256Mi"
    limits:
      cpu: "1"
      memory: "512Mi"

clickhouse:
  shards: 1
  replicasPerShard: 2
  resources:
    requests:
      cpu: "4"
      memory: "16Gi"
    limits:
      cpu: "8"
      memory: "32Gi"
  storage:
    size: "500Gi"
    class: "gp3"

nats:
  replicas: 3
  resources:
    requests:
      cpu: "500m"
      memory: "1Gi"
    limits:
      cpu: "2"
      memory: "4Gi"
  jetstream:
    enabled: true
    storage:
      size: "50Gi"

redis:
  replicas: 3
  sentinel:
    enabled: true
  resources:
    requests:
      cpu: "250m"
      memory: "512Mi"
    limits:
      cpu: "1"
      memory: "2Gi"

postgresql:
  replicas: 3
  resources:
    requests:
      cpu: "500m"
      memory: "1Gi"
    limits:
      cpu: "2"
      memory: "4Gi"
  storage:
    size: "100Gi"

objectStorage:
  provider: "minio"  # or "s3" for AWS
  minio:
    enabled: true
    replicas: 4
    storage:
      size: "1Ti"
```

### 4.5 Helm Values: Medium Deployment (up to 500K events/sec)

```yaml
# values-medium.yaml — Production
# Target: up to 500K events/sec, 5TB/day ingestion
# Cluster: 10-20 nodes, 32 vCPU / 128GB RAM each

gateway:
  replicas: 3
  resources:
    requests: { cpu: "1", memory: "1Gi" }
    limits: { cpu: "4", memory: "2Gi" }
  autoscaling:
    enabled: true
    minReplicas: 3
    maxReplicas: 10

ingester:
  replicas: 5
  resources:
    requests: { cpu: "2", memory: "4Gi" }
    limits: { cpu: "8", memory: "8Gi" }
  autoscaling:
    enabled: true
    minReplicas: 5
    maxReplicas: 20

query:
  replicas: 4
  resources:
    requests: { cpu: "4", memory: "8Gi" }
    limits: { cpu: "8", memory: "16Gi" }
  autoscaling:
    enabled: true
    minReplicas: 4
    maxReplicas: 12

aiEngine:
  replicas: 3
  resources:
    requests: { cpu: "4", memory: "8Gi" }
    limits: { cpu: "8", memory: "16Gi" }
  gpu:
    enabled: true
    type: "nvidia.com/gpu"
    count: 1

agentRuntime:
  replicas: 3
  resources:
    requests: { cpu: "2", memory: "4Gi" }
    limits: { cpu: "4", memory: "8Gi" }

clickhouse:
  shards: 2
  replicasPerShard: 2
  resources:
    requests: { cpu: "8", memory: "32Gi" }
    limits: { cpu: "16", memory: "64Gi" }
  storage:
    size: "2Ti"
    class: "io2"
```

### 4.6 Helm Values: Large / Enterprise Deployment (up to 10M events/sec)

```yaml
# values-large.yaml — Enterprise
# Target: up to 10M events/sec, 50TB/day ingestion
# Cluster: 50-100+ nodes, dedicated node pools

gateway:
  replicas: 5
  resources:
    requests: { cpu: "2", memory: "2Gi" }
    limits: { cpu: "8", memory: "4Gi" }
  autoscaling:
    enabled: true
    minReplicas: 5
    maxReplicas: 20
  topologySpreadConstraints:
    - maxSkew: 1
      topologyKey: topology.kubernetes.io/zone
      whenUnsatisfiable: DoNotSchedule
  affinity:
    podAntiAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        - labelSelector:
            matchLabels:
              app.kubernetes.io/component: gateway
          topologyKey: kubernetes.io/hostname

ingester:
  replicas: 10
  resources:
    requests: { cpu: "4", memory: "8Gi" }
    limits: { cpu: "16", memory: "16Gi" }
  autoscaling:
    enabled: true
    minReplicas: 10
    maxReplicas: 50
    customMetrics:
      - type: nats
        metric: queue_depth
        threshold: 50000
      - type: prometheus
        metric: rayolly_ingester_events_per_second
        threshold: 100000
  topologySpreadConstraints:
    - maxSkew: 1
      topologyKey: topology.kubernetes.io/zone
      whenUnsatisfiable: DoNotSchedule

query:
  replicas: 8
  resources:
    requests: { cpu: "8", memory: "16Gi" }
    limits: { cpu: "16", memory: "32Gi" }
  autoscaling:
    enabled: true
    minReplicas: 8
    maxReplicas: 30

aiEngine:
  replicas: 5
  resources:
    requests: { cpu: "8", memory: "16Gi" }
    limits: { cpu: "16", memory: "32Gi" }
  gpu:
    enabled: true
    type: "nvidia.com/gpu"
    count: 2
  nodeSelector:
    rayolly.io/node-pool: "gpu"

agentRuntime:
  replicas: 5
  resources:
    requests: { cpu: "4", memory: "8Gi" }
    limits: { cpu: "8", memory: "16Gi" }
  autoscaling:
    enabled: true
    minReplicas: 5
    maxReplicas: 20

clickhouse:
  shards: 8
  replicasPerShard: 3
  resources:
    requests: { cpu: "16", memory: "64Gi" }
    limits: { cpu: "32", memory: "128Gi" }
  storage:
    size: "10Ti"
    class: "io2"
  nodeSelector:
    rayolly.io/node-pool: "clickhouse"
  topologySpreadConstraints:
    - maxSkew: 1
      topologyKey: topology.kubernetes.io/zone
      whenUnsatisfiable: DoNotSchedule
```

### 4.7 Pod Anti-Affinity and Topology Spread

All production components enforce the following scheduling constraints:

```yaml
# Template excerpt — applied to all Deployment/StatefulSet templates
spec:
  topologySpreadConstraints:
    - maxSkew: 1
      topologyKey: topology.kubernetes.io/zone
      whenUnsatisfiable: DoNotSchedule
      labelSelector:
        matchLabels:
          app.kubernetes.io/component: {{ .component }}
    - maxSkew: 1
      topologyKey: kubernetes.io/hostname
      whenUnsatisfiable: ScheduleAnyway
      labelSelector:
        matchLabels:
          app.kubernetes.io/component: {{ .component }}
  affinity:
    podAntiAffinity:
      preferredDuringSchedulingIgnoredDuringExecution:
        - weight: 100
          podAffinityTerm:
            labelSelector:
              matchLabels:
                app.kubernetes.io/component: {{ .component }}
            topologyKey: kubernetes.io/hostname
```

### 4.8 Resource Requests and Limits Summary

| Component | CPU Request | CPU Limit | Memory Request | Memory Limit | Notes |
|-----------|-----------|---------|--------------|------------|-------|
| gateway | 500m–2 | 2–8 | 512Mi–2Gi | 1Gi–4Gi | CPU-bound (TLS termination) |
| ingester | 1–4 | 4–16 | 1Gi–8Gi | 4Gi–16Gi | Throughput-critical |
| query | 1–8 | 4–16 | 2Gi–16Gi | 8Gi–32Gi | Memory-heavy (result buffering) |
| storage | 500m–1 | 2–4 | 1Gi–2Gi | 2Gi–4Gi | I/O management |
| ai-engine | 2–8 | 4–16 | 4Gi–16Gi | 8Gi–32Gi | GPU optional |
| agent-runtime | 1–4 | 2–8 | 2Gi–8Gi | 4Gi–16Gi | Per-agent isolation |
| alerter | 500m | 1–2 | 512Mi–1Gi | 1Gi–2Gi | Lightweight |
| scheduler | 250m | 500m–1 | 256Mi–512Mi | 512Mi–1Gi | Leader-elected singleton |
| web | 250m | 1 | 256Mi | 512Mi | Serves static assets + SSR |
| clickhouse | 4–16 | 8–32 | 16Gi–64Gi | 32Gi–128Gi | Memory-intensive OLAP |
| nats | 500m | 2 | 1Gi | 4Gi | Low overhead |
| redis | 250m | 1 | 512Mi | 2Gi | In-memory cache |
| postgresql | 500m | 2 | 1Gi | 4Gi | Metadata store |

---

## 5. Component Architecture (Microservices)

### 5.1 Service Inventory

```
┌─────────────────────────────────────────────────────────────────────┐
│                         RayOlly Platform                             │
│                                                                       │
│  ┌──────────────┐                                                    │
│  │  rayolly-web │ ◄── React/Next.js frontend                        │
│  └──────┬───────┘                                                    │
│         │ HTTPS                                                       │
│  ┌──────▼──────────┐                                                 │
│  │ rayolly-gateway │ ◄── API gateway, auth, rate limiting, routing   │
│  └──┬───┬───┬───┬──┘                                                 │
│     │   │   │   │  gRPC                                               │
│  ┌──▼┐ ┌▼──┐┌▼──┐┌▼────────────┐                                    │
│  │Ing│ │Qry││Str││  ai-engine  │                                     │
│  │est│ │   ││   ││             │                                     │
│  │er │ │   ││   ││  ┌─────────┐│                                     │
│  └─┬─┘ └─┬─┘└─┬─┘│  │agent-rt ││                                    │
│    │     │    │   │  └─────────┘│                                     │
│    │     │    │   └─────────────┘                                     │
│    │     │    │                                                        │
│  ┌─▼─────▼────▼───────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │   NATS JetStream       │  │  rayolly-    │  │  rayolly-    │    │
│  │   (Event Bus)          │  │  alerter     │  │  scheduler   │    │
│  └────────────────────────┘  └──────────────┘  └──────────────┘    │
│                                                                       │
│  ┌──────────────┐ ┌───────┐ ┌────────────┐ ┌──────────────────┐    │
│  │  ClickHouse  │ │ Redis │ │ PostgreSQL │ │  S3 / MinIO      │    │
│  └──────────────┘ └───────┘ └────────────┘ └──────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

### 5.2 Service Descriptions

**rayolly-gateway** — API Gateway, Authentication & Routing
- Terminates TLS and handles HTTP/2, gRPC-Web transcoding
- JWT validation, API key authentication, OAuth2/OIDC
- Rate limiting (per-tenant, per-API-key)
- Request routing to downstream services via gRPC
- OpenAPI spec serving and request validation
- Port: 8080 (HTTP), 8443 (HTTPS), 9090 (gRPC)

**rayolly-ingester** — Data Ingestion Engine
- Accepts OTLP (gRPC + HTTP), Syslog, Fluent Forward, Datadog-compat
- Schema validation and enrichment (K8s metadata, GeoIP)
- Batching and writing to NATS JetStream
- Backpressure handling via NATS consumer flow control
- Port: 4317 (OTLP gRPC), 4318 (OTLP HTTP), 5140 (Syslog)

**rayolly-query** — Query Engine
- SQL query parsing, planning, and execution
- Federated query across ClickHouse (hot/warm) and S3/Parquet (cold)
- Full-text search via Tantivy
- Query result caching (Redis)
- Query quotas and resource governance
- Port: 9091 (gRPC), 8081 (HTTP debug)

**rayolly-storage** — Storage Lifecycle Manager
- Manages data tiering (hot -> warm -> cold -> archive)
- ClickHouse table management and schema migrations
- Compaction and retention policy enforcement
- Object storage lifecycle rules
- Port: 9092 (gRPC)

**rayolly-ai-engine** — ML/AI Processing
- Anomaly detection model training and inference
- Time-series forecasting
- Log pattern mining and clustering
- LLM integration for natural language to SQL
- Model registry and versioning
- Port: 9093 (gRPC), 8082 (HTTP model API)

**rayolly-agent-runtime** — AI Agent Execution Environment
- Sandboxed execution of AI agents (RCA, Incident, Query, Custom)
- Agent lifecycle management (start, stop, status)
- Tool execution framework (agents calling platform APIs)
- Agent state persistence and checkpointing
- Resource limits per agent execution
- Port: 9094 (gRPC)

**rayolly-alerter** — Alert Evaluation Engine
- Evaluates alert rules on schedule (10s–5m intervals)
- Threshold, anomaly-based, and composite alert types
- Notification routing (PagerDuty, Slack, OpsGenie, webhook)
- Alert deduplication and grouping
- Silence and maintenance window management
- Port: 9095 (gRPC)

**rayolly-scheduler** — Job Scheduling
- Cron-based job execution (report generation, data compaction, model retraining)
- Leader-elected singleton to prevent duplicate execution
- Job history and retry logic
- Port: 9096 (gRPC)

**rayolly-web** — Frontend Application
- React 19 / Next.js 15 server-rendered application
- Serves dashboard UI, log explorer, trace viewer, agent console
- WebSocket proxy for live tail and real-time updates
- Port: 3000 (HTTP)

**rayolly-operator** — Kubernetes Operator
- Watches RayOllyCluster, RayOllyPipeline, RayOllyTenant CRDs
- Reconciles desired state with actual cluster state
- Handles upgrades, scaling decisions, and health management
- Port: 8443 (webhook), 8080 (metrics)

### 5.3 Inter-Service Communication

| Pattern | Technology | Use Case |
|---------|-----------|----------|
| Synchronous RPC | gRPC with protobuf | Service-to-service requests (gateway -> query, gateway -> ingester) |
| Async Events | NATS JetStream | Ingested data streaming, alert events, agent task queues |
| Pub/Sub | NATS Core | Real-time notifications (live tail, dashboard updates) |
| Cache | Redis | Query result cache, session state, rate limit counters |
| Metadata | PostgreSQL | Tenant config, dashboard definitions, alert rules, user accounts |

**Service Mesh (Optional)**:
- Istio or Linkerd can be layered on for mTLS, traffic management, and observability
- Not required — RayOlly handles its own auth and gRPC TLS
- Recommended for enterprise deployments with strict security requirements

---

## 6. Scaling Strategy

### 6.1 Horizontal Pod Autoscaling (HPA)

Each stateless component has an HPA configured with both CPU-based and custom metrics-based scaling.

```yaml
# Example HPA for rayolly-ingester
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: rayolly-ingester
  namespace: rayolly
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: rayolly-ingester
  minReplicas: 3
  maxReplicas: 50
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
        - type: Pods
          value: 4
          periodSeconds: 60
        - type: Percent
          value: 50
          periodSeconds: 60
      selectPolicy: Max
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Pods
          value: 2
          periodSeconds: 120
      selectPolicy: Min
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 65
    - type: Pods
      pods:
        metric:
          name: rayolly_ingester_events_per_second
        target:
          type: AverageValue
          averageValue: "50000"
    - type: External
      external:
        metric:
          name: nats_consumer_pending_messages
          selector:
            matchLabels:
              stream: "rayolly-ingest"
        target:
          type: AverageValue
          averageValue: "10000"
```

### 6.2 Vertical Pod Autoscaling (VPA)

VPA is deployed in recommendation-only mode to inform right-sizing without automatic restarts.

```yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: rayolly-query-vpa
  namespace: rayolly
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: rayolly-query
  updatePolicy:
    updateMode: "Off"  # Recommendation only
  resourcePolicy:
    containerPolicies:
      - containerName: query
        minAllowed:
          cpu: "1"
          memory: "2Gi"
        maxAllowed:
          cpu: "16"
          memory: "32Gi"
```

### 6.3 Component Scaling Matrix

| Component | Scaling Trigger | Scale Unit | Max Scale Factor | Bottleneck |
|-----------|----------------|------------|-----------------|------------|
| gateway | Request rate, CPU | +1 pod | 20x | CPU (TLS) |
| ingester | Queue depth, events/sec | +2–4 pods | 50x | Network I/O |
| query | Active queries, CPU, memory | +1 pod | 30x | Memory |
| ai-engine | Inference queue depth | +1 pod | 10x | GPU / CPU |
| agent-runtime | Active agent count | +1 pod | 20x | Memory |
| alerter | Rule count, evaluation lag | +1 pod | 5x | CPU |
| web | Request rate | +1 pod | 10x | CPU |
| clickhouse | Storage utilization, query latency | +1 shard | 16x shards | Disk I/O |
| nats | Message throughput | +1 node | 5x | Network |

### 6.4 Scaling Targets

| Tier | Events/sec | Daily Ingest | ClickHouse Shards | Ingester Pods | Query Pods | Nodes |
|------|-----------|-------------|-------------------|--------------|-----------|-------|
| Development | 1K | 10GB | 1 | 1 | 1 | 1–3 |
| Small | 50K | 500GB | 1 (2 replicas) | 2–4 | 2 | 3–5 |
| Medium | 500K | 5TB | 2–4 (2 replicas) | 5–10 | 4–8 | 10–20 |
| Large | 2M | 20TB | 4–8 (3 replicas) | 10–20 | 8–16 | 30–60 |
| Enterprise | 10M+ | 100TB+ | 8–16 (3 replicas) | 20–50 | 16–30 | 60–100+ |

### 6.5 ClickHouse Cluster Scaling

ClickHouse scaling is managed by the Operator and follows this process:

1. **Add Replicas** (read scaling): Operator adds a replica to an existing shard, triggers data replication
2. **Add Shards** (write scaling): Operator adds a new shard, rebalances distributed table routing
3. **Vertical scaling**: Operator updates resource requests, triggers rolling restart
4. **Storage expansion**: PVC resize (if storage class supports it) or migration to larger volumes

```
Shard 1:  [Replica A] ←→ [Replica B] ←→ [Replica C]
Shard 2:  [Replica A] ←→ [Replica B] ←→ [Replica C]
Shard 3:  [Replica A] ←→ [Replica B] ←→ [Replica C]
   ...
Shard N:  [Replica A] ←→ [Replica B] ←→ [Replica C]

Distributed table routes writes across shards via consistent hashing.
Reads fan out to one replica per shard for parallel execution.
```

---

## 7. High Availability

### 7.1 Multi-AZ Deployment

Production deployments span a minimum of 3 availability zones. Every stateful and stateless component is distributed across AZs.

```
         AZ-1                    AZ-2                    AZ-3
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ gateway (1)     │    │ gateway (1)     │    │ gateway (1)     │
│ ingester (2)    │    │ ingester (2)    │    │ ingester (2)    │
│ query (1)       │    │ query (1)       │    │ query (1)       │
│ ai-engine (1)   │    │ ai-engine (1)   │    │                 │
│ alerter (1)     │    │ alerter (1)     │    │                 │
│ web (1)         │    │ web (1)         │    │                 │
│                 │    │                 │    │                 │
│ CH shard1-rep1  │    │ CH shard1-rep2  │    │ CH shard2-rep1  │
│ CH shard2-rep2  │    │ NATS node 1     │    │ NATS node 2     │
│ NATS node 0     │    │ Redis sentinel  │    │ Redis sentinel  │
│ Redis primary   │    │ PG replica      │    │ PG replica      │
│ PG primary      │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### 7.2 Component Redundancy

| Component | Min Replicas (HA) | PDB (minAvailable) | Leader Election | Notes |
|-----------|------------------|--------------------|--------------------|-------|
| gateway | 3 | 2 | No | Stateless, load-balanced |
| ingester | 3 | 2 | No | Stateless, NATS consumers |
| query | 2 | 1 | No | Stateless |
| storage | 2 | 1 | No | Stateless coordinator |
| ai-engine | 2 | 1 | No | Stateless inference |
| agent-runtime | 2 | 1 | No | Agent state in Redis/PG |
| alerter | 2 | 1 | No | Sharded rule evaluation |
| scheduler | 1 | 1 | Yes | Leader-elected singleton |
| web | 2 | 1 | No | Stateless SSR |
| clickhouse | 2 replicas/shard | N/A | Via ZooKeeper/Keeper | Quorum writes |
| nats | 3 | 2 | Raft | JetStream Raft consensus |
| redis | 3 | 2 | Sentinel | Automatic failover |
| postgresql | 3 | 2 | Patroni | Synchronous replication |

### 7.3 Health Checks

Every component exposes:

```yaml
livenessProbe:
  httpGet:
    path: /healthz
    port: health
  initialDelaySeconds: 15
  periodSeconds: 10
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /readyz
    port: health
  initialDelaySeconds: 5
  periodSeconds: 5
  failureThreshold: 2

startupProbe:
  httpGet:
    path: /healthz
    port: health
  initialDelaySeconds: 5
  periodSeconds: 5
  failureThreshold: 30  # 150s max startup
```

### 7.4 Graceful Shutdown

All components implement graceful shutdown:

1. K8s sends SIGTERM to the pod
2. Pod marks itself as not-ready (readiness probe fails)
3. Pod stops accepting new requests/messages
4. Pod drains in-flight work (configurable timeout, default 30s)
5. Pod flushes buffers (ingester flushes to NATS, query completes running queries)
6. Pod exits cleanly

```yaml
spec:
  terminationGracePeriodSeconds: 60
  containers:
    - name: ingester
      lifecycle:
        preStop:
          exec:
            command: ["/bin/sh", "-c", "sleep 5"]  # Allow LB to drain
```

### 7.5 Circuit Breaker Patterns

Inter-service calls use circuit breakers to prevent cascade failures:

| Circuit | Failure Threshold | Open Duration | Half-Open Probes |
|---------|------------------|--------------|-----------------|
| gateway -> query | 5 failures in 10s | 30s | 3 |
| gateway -> ingester | 5 failures in 10s | 30s | 3 |
| query -> clickhouse | 3 failures in 10s | 60s | 2 |
| ai-engine -> LLM API | 3 failures in 30s | 120s | 1 |
| alerter -> notification | 5 failures in 60s | 300s | 2 |

---

## 8. Multi-Region Architecture

### 8.1 Active-Active Deployment

```
                    ┌─────────────────────────┐
                    │   Global Load Balancer    │
                    │  (Cloudflare / Route53)   │
                    └──────┬──────────┬────────┘
                           │          │
              ┌────────────▼──┐  ┌───▼────────────┐
              │   US-EAST-1    │  │   EU-WEST-1     │
              │                │  │                  │
              │  ┌──────────┐ │  │  ┌──────────┐  │
              │  │ RayOlly  │ │  │  │ RayOlly  │  │
              │  │ Full     │ │  │  │ Full     │  │
              │  │ Stack    │ │  │  │ Stack    │  │
              │  └──────────┘ │  │  └──────────┘  │
              │                │  │                  │
              │  ┌──────────┐ │  │  ┌──────────┐  │
              │  │ClickHouse│ │  │  │ClickHouse│  │
              │  │ + S3     │ │  │  │ + S3     │  │
              │  └──────────┘ │  │  └──────────┘  │
              │                │  │                  │
              └───────┬────────┘  └───────┬────────┘
                      │                    │
                      ▼                    ▼
              ┌────────────────────────────────────┐
              │    Cross-Region Metadata Sync       │
              │   (PostgreSQL logical replication)   │
              │                                      │
              │  Synced: dashboards, alert rules,    │
              │          tenant config, users         │
              │  NOT synced: observability data       │
              │             (stays in region)         │
              └────────────────────────────────────┘
```

### 8.2 Data Locality Rules

| Data Type | Locality | Cross-Region Sync |
|-----------|----------|-------------------|
| Logs, metrics, traces (observability data) | Region-local only | Never replicated cross-region |
| Dashboard definitions | Region-local, synced | Async replication (< 5s lag) |
| Alert rules | Region-local, synced | Async replication (< 5s lag) |
| User accounts and RBAC | Region-local, synced | Async replication (< 5s lag) |
| Tenant configuration | Region-local, synced | Async replication (< 5s lag) |
| AI models | Region-local, synced | Async replication (model push) |
| Agent definitions | Region-local, synced | Async replication (< 5s lag) |

### 8.3 Region Failover

**Automated failover triggers**:
1. Health check failures from 2+ AZs in the region for > 2 minutes
2. Global load balancer removes region from DNS rotation (TTL: 30s)
3. Failover region begins accepting traffic

**Data implications during failover**:
- Observability data ingested during outage in failed region is lost (RPO applies)
- Metadata (dashboards, alerts, config) is available in failover region
- After recovery, failed region resumes independently — no data backfill across regions

### 8.4 Compliance-Driven Data Residency

| Regulation | Requirement | Implementation |
|-----------|-------------|----------------|
| GDPR | EU data stays in EU | EU tenants routed exclusively to EU region |
| CCPA | California resident data | US-WEST region option |
| Data Sovereignty (Germany) | Data in-country | eu-central-1 region (Frankfurt) |
| HIPAA | US-only, encrypted | Dedicated US cluster, encryption at rest + transit |
| FedRAMP | GovCloud | us-gov-west-1 (roadmap) |

---

## 9. Disaster Recovery

### 9.1 Recovery Objectives

| Objective | Target | Measurement |
|-----------|--------|-------------|
| RPO (Recovery Point Objective) | < 1 minute | Maximum data loss window |
| RTO (Recovery Time Objective) | < 15 minutes | Time to full service restoration |
| Backup Frequency | Continuous (streaming) + hourly snapshots | |
| Backup Retention | 30 days (daily), 12 months (weekly), 7 years (monthly) | |
| DR Test Frequency | Quarterly | Full failover drill |

### 9.2 Backup Strategy

| Component | Backup Method | Frequency | Storage | Retention |
|-----------|--------------|-----------|---------|-----------|
| ClickHouse | Native backup to S3 + replication | Hourly snapshots, continuous replication | S3 (cross-region) | 30 days |
| PostgreSQL | pg_basebackup + WAL archiving | Continuous WAL, daily base backup | S3 (cross-region) | 30 days |
| NATS JetStream | Stream replication (R=3) | Real-time | Persistent volumes | 7 days |
| Redis | RDB snapshots + AOF | Hourly RDB, continuous AOF | S3 | 7 days |
| Object Storage (S3/MinIO) | Cross-region replication | Real-time | S3 (DR region) | Same as source |
| Configuration (Helm values, CRDs) | Git (ArgoCD) | Every change | Git repository | Indefinite |
| Secrets | Vault snapshots | Hourly | Encrypted S3 | 30 days |

### 9.3 Restore Procedures

**Full Cluster Restore (RTO target: < 15 minutes)**:

1. **Minutes 0–2**: Trigger DR runbook (automated or manual)
2. **Minutes 2–5**: ArgoCD deploys RayOlly stack to DR cluster from Git
3. **Minutes 5–8**: Restore PostgreSQL from latest base backup + WAL replay
4. **Minutes 8–12**: ClickHouse attaches from replicated data or restores from S3 backup
5. **Minutes 12–14**: NATS JetStream recovers from persistent volumes or recreates streams
6. **Minutes 14–15**: Health checks pass, traffic routing switches to DR cluster

**Single Component Restore**:

| Component | Restore Time | Procedure |
|-----------|-------------|-----------|
| PostgreSQL | 3–5 min | Patroni automatic failover to replica |
| ClickHouse (1 replica) | 1–2 min | ZooKeeper triggers re-replication from surviving replica |
| ClickHouse (full shard) | 10–15 min | Restore from S3 backup |
| NATS node | 1–2 min | Raft consensus restores from peers |
| Redis | < 1 min | Sentinel promotes replica |
| Any stateless service | < 1 min | K8s restarts pod automatically |

### 9.4 DR Runbooks

DR runbooks are maintained as executable scripts in the `ops/runbooks/` directory:

```
ops/runbooks/
├── dr-full-failover.sh          # Complete region failover
├── dr-clickhouse-restore.sh     # ClickHouse restore from backup
├── dr-postgresql-restore.sh     # PostgreSQL PITR restore
├── dr-verify-data-integrity.sh  # Post-restore data verification
├── dr-traffic-switchover.sh     # DNS/LB traffic cutover
└── dr-test-quarterly.sh         # Quarterly DR drill automation
```

---

## 10. SaaS Infrastructure

### 10.1 Multi-Tenant Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    Shared Infrastructure                       │
│                                                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │   Gateway     │  │   Ingester    │  │   Query Engine   │   │
│  │ (tenant-aware)│  │ (tenant-aware)│  │ (tenant-aware)   │   │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────────┘   │
│         │                  │                  │                │
│  ┌──────▼──────────────────▼──────────────────▼─────────┐    │
│  │              Tenant Isolation Layer                     │    │
│  │                                                        │    │
│  │  Tenant A: ClickHouse DB "tenant_a", S3 prefix "a/"   │    │
│  │  Tenant B: ClickHouse DB "tenant_b", S3 prefix "b/"   │    │
│  │  Tenant C: ClickHouse DB "tenant_c", S3 prefix "c/"   │    │
│  └────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

### 10.2 Isolation Model

| Resource | Shared Tier | Dedicated Tier |
|----------|------------|----------------|
| Kubernetes cluster | Shared | Dedicated cluster |
| Compute (pods) | Shared, resource-limited | Dedicated node pool |
| ClickHouse | Shared cluster, separate databases | Dedicated ClickHouse cluster |
| NATS | Shared, separate accounts/subjects | Dedicated NATS cluster |
| PostgreSQL | Shared, row-level security | Dedicated PostgreSQL |
| Object Storage | Shared bucket, tenant prefix | Dedicated bucket |
| Network | Shared, network policies | Dedicated VPC |
| Encryption keys | Shared KMS, per-tenant data keys | Dedicated KMS keys |

### 10.3 Tenant Provisioning

When a new tenant signs up, the following is automatically provisioned:

1. Tenant record in PostgreSQL (config, billing, limits)
2. ClickHouse database and tables (from schema template)
3. NATS account with subject permissions
4. S3 prefix with lifecycle rules
5. Redis namespace for query cache
6. Default dashboards and alert rules
7. API keys and initial admin user
8. Usage metering counters

Provisioning time target: < 30 seconds.

### 10.4 Usage Metering

Metered dimensions for billing:

| Dimension | Unit | Collection Method |
|-----------|------|-------------------|
| Data ingestion | GB/month | Ingester measures at intake |
| Active time series | Count (gauge, hourly) | Storage manager counts |
| Query executions | Count/month | Query engine counts |
| AI agent invocations | Count/month | Agent runtime counts |
| Custom agent deployments | Count (gauge) | Agent runtime counts |
| Data retention beyond default | GB-months | Storage manager calculates |
| Users | Count (gauge) | PostgreSQL count |

Metering data is published to NATS, aggregated by the scheduler, and pushed to the billing system (Stripe/Lago) hourly.

### 10.5 Capacity Planning

The SaaS platform uses predictive capacity planning:

1. **Ingestion forecast**: Linear regression on 30-day ingestion trend per tenant
2. **Storage forecast**: Current usage + growth rate projection
3. **Compute forecast**: Peak CPU/memory usage patterns (weekly seasonality)
4. **Alerting**: Trigger capacity alerts at 70% utilization
5. **Auto-provisioning**: Add ClickHouse shards at 80% storage, add ingester pods via HPA

---

## 11. Self-Hosted Packaging

### 11.1 Docker Compose (Development / Small)

```yaml
# docker-compose.yml — for development and small deployments (< 10K events/sec)
version: "3.9"

services:
  gateway:
    image: registry.rayolly.io/rayolly-gateway:${RAYOLLY_VERSION:-latest}
    ports:
      - "8080:8080"
      - "4317:4317"  # OTLP gRPC passthrough
      - "4318:4318"  # OTLP HTTP passthrough
    environment:
      - RAYOLLY_NATS_URL=nats://nats:4222
      - RAYOLLY_POSTGRES_URL=postgresql://rayolly:rayolly@postgresql:5432/rayolly
      - RAYOLLY_REDIS_URL=redis://redis:6379
    depends_on:
      - nats
      - postgresql
      - redis

  ingester:
    image: registry.rayolly.io/rayolly-ingester:${RAYOLLY_VERSION:-latest}
    environment:
      - RAYOLLY_NATS_URL=nats://nats:4222
      - RAYOLLY_CLICKHOUSE_URL=clickhouse://clickhouse:9000
    depends_on:
      - nats
      - clickhouse

  query:
    image: registry.rayolly.io/rayolly-query:${RAYOLLY_VERSION:-latest}
    environment:
      - RAYOLLY_CLICKHOUSE_URL=clickhouse://clickhouse:9000
      - RAYOLLY_REDIS_URL=redis://redis:6379
      - RAYOLLY_S3_ENDPOINT=http://minio:9000
    depends_on:
      - clickhouse
      - redis
      - minio

  storage:
    image: registry.rayolly.io/rayolly-storage:${RAYOLLY_VERSION:-latest}
    environment:
      - RAYOLLY_CLICKHOUSE_URL=clickhouse://clickhouse:9000
      - RAYOLLY_S3_ENDPOINT=http://minio:9000
    depends_on:
      - clickhouse
      - minio

  ai-engine:
    image: registry.rayolly.io/rayolly-ai-engine:${RAYOLLY_VERSION:-latest}
    environment:
      - RAYOLLY_LLM_PROVIDER=claude
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - RAYOLLY_CLICKHOUSE_URL=clickhouse://clickhouse:9000
    depends_on:
      - clickhouse

  agent-runtime:
    image: registry.rayolly.io/rayolly-agent-runtime:${RAYOLLY_VERSION:-latest}
    environment:
      - RAYOLLY_NATS_URL=nats://nats:4222
      - RAYOLLY_POSTGRES_URL=postgresql://rayolly:rayolly@postgresql:5432/rayolly
    depends_on:
      - nats
      - postgresql

  alerter:
    image: registry.rayolly.io/rayolly-alerter:${RAYOLLY_VERSION:-latest}
    environment:
      - RAYOLLY_CLICKHOUSE_URL=clickhouse://clickhouse:9000
      - RAYOLLY_NATS_URL=nats://nats:4222
      - RAYOLLY_POSTGRES_URL=postgresql://rayolly:rayolly@postgresql:5432/rayolly
    depends_on:
      - clickhouse
      - nats
      - postgresql

  scheduler:
    image: registry.rayolly.io/rayolly-scheduler:${RAYOLLY_VERSION:-latest}
    environment:
      - RAYOLLY_POSTGRES_URL=postgresql://rayolly:rayolly@postgresql:5432/rayolly
      - RAYOLLY_NATS_URL=nats://nats:4222
    depends_on:
      - postgresql
      - nats

  web:
    image: registry.rayolly.io/rayolly-web:${RAYOLLY_VERSION:-latest}
    ports:
      - "3000:3000"
    environment:
      - RAYOLLY_API_URL=http://gateway:8080
    depends_on:
      - gateway

  # Infrastructure dependencies
  clickhouse:
    image: clickhouse/clickhouse-server:24.3
    ports:
      - "8123:8123"
      - "9000:9000"
    volumes:
      - clickhouse_data:/var/lib/clickhouse
    ulimits:
      nofile:
        soft: 262144
        hard: 262144

  nats:
    image: nats:2.10-alpine
    command: ["--jetstream", "--store_dir=/data"]
    ports:
      - "4222:4222"
    volumes:
      - nats_data:/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  postgresql:
    image: postgres:16-alpine
    environment:
      - POSTGRES_USER=rayolly
      - POSTGRES_PASSWORD=rayolly
      - POSTGRES_DB=rayolly
    ports:
      - "5432:5432"
    volumes:
      - postgresql_data:/var/lib/postgresql/data

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    ports:
      - "9000:9000"
      - "9001:9001"
    environment:
      - MINIO_ROOT_USER=rayolly
      - MINIO_ROOT_PASSWORD=rayolly123
    volumes:
      - minio_data:/data

volumes:
  clickhouse_data:
  nats_data:
  redis_data:
  postgresql_data:
  minio_data:
```

### 11.2 Air-Gapped Installation

For environments without internet access:

1. **Offline image bundle**: All container images packaged as a tarball
   ```bash
   rayolly-images-v1.0.0-amd64.tar.gz  # ~4GB
   rayolly-images-v1.0.0-arm64.tar.gz  # ~4GB
   ```

2. **Local model support**: AI engine ships with bundled local models (Llama 3.1 8B quantized) for NL queries and anomaly classification when Claude API is not accessible

3. **Offline Helm chart**: Chart and all sub-chart dependencies bundled
   ```bash
   rayolly-chart-v1.0.0.tgz
   ```

4. **Installation procedure**:
   ```bash
   # Load images into local registry
   rayolly-cli images load --archive rayolly-images-v1.0.0-amd64.tar.gz \
     --registry registry.internal.example.com

   # Install via Helm
   helm install rayolly ./rayolly-chart-v1.0.0.tgz \
     --namespace rayolly \
     --create-namespace \
     -f values-airgapped.yaml \
     --set global.imageRegistry=registry.internal.example.com \
     --set aiEngine.llm.provider=local \
     --set aiEngine.llm.localModelPath=/models/llama-3.1-8b-q4
   ```

### 11.3 Minimum Hardware Requirements

| Size | Nodes | vCPU/Node | RAM/Node | Storage/Node | Total vCPU | Total RAM | Total Storage | Max Events/sec |
|------|-------|-----------|----------|-------------|-----------|---------|--------------|----------------|
| Small | 3 | 8 | 32GB | 500GB SSD | 24 | 96GB | 1.5TB | 50K |
| Medium | 5 | 16 | 64GB | 1TB SSD | 80 | 320GB | 5TB | 500K |
| Large | 10 | 32 | 128GB | 2TB NVMe | 320 | 1.28TB | 20TB | 2M |
| Enterprise | 20+ | 64 | 256GB | 4TB NVMe | 1280+ | 5TB+ | 80TB+ | 10M+ |

### 11.4 Installation Wizard

```bash
$ rayolly-cli install

  ____             ___  _ _
 |  _ \ __ _ _   _/ _ \| | |_   _
 | |_) / _` | | | | | | | | | | |
 |  _ < (_| | |_| | |_| | | |_| |
 |_| \_\__,_|\__, |\___/|_|_|\__, |
             |___/            |___/

 Welcome to RayOlly Installation Wizard v1.0.0

 [1/7] Deployment model:
       (1) Self-hosted — Full stack on your K8s cluster
       (2) Hybrid — Data plane here, control plane SaaS
       > 1

 [2/7] Cluster size:
       (1) Small  — up to 50K events/sec  (min 3 nodes, 8 vCPU/32GB each)
       (2) Medium — up to 500K events/sec (min 5 nodes, 16 vCPU/64GB each)
       (3) Large  — up to 2M events/sec   (min 10 nodes, 32 vCPU/128GB each)
       (4) Custom
       > 2

 [3/7] Object storage:
       (1) MinIO (bundled)
       (2) AWS S3
       (3) Google Cloud Storage
       (4) Azure Blob Storage
       > 2

 [4/7] AI/LLM configuration:
       (1) Claude API (requires internet + API key)
       (2) Local models (air-gapped compatible, reduced capability)
       (3) OpenAI API
       > 1

 [5/7] High availability:
       (1) Enabled  — Multi-AZ, 2+ replicas per service (recommended)
       (2) Disabled — Single replica (development only)
       > 1

 [6/7] TLS configuration:
       (1) Let's Encrypt (automatic)
       (2) Bring your own certificate
       (3) Disabled (not recommended)
       > 2

 [7/7] Namespace: rayolly

 Generating Helm values... done.
 Validating cluster prerequisites... done.
   ✓ Kubernetes 1.29.2 detected
   ✓ 7 nodes available (meets minimum of 5)
   ✓ StorageClass 'gp3' available
   ✓ Ingress controller detected (nginx)

 Ready to install. Proceed? [Y/n] Y

 Installing RayOlly...
   ✓ Namespace created
   ✓ CRDs installed
   ✓ Operator deployed
   ✓ Infrastructure (ClickHouse, NATS, Redis, PostgreSQL) deployed
   ✓ RayOlly services deployed
   ✓ Ingress configured

 RayOlly is running! Access at: https://rayolly.example.com
 Admin credentials saved to: ~/.rayolly/admin-credentials.json
```

### 11.5 Upgrade Procedures

**Rolling Update (zero-downtime)**:
```bash
# Update Helm chart
helm upgrade rayolly rayolly/rayolly \
  --namespace rayolly \
  --set global.imageTag="1.1.0" \
  --reuse-values

# The Operator handles:
# 1. Stateless services: rolling update (maxUnavailable: 0, maxSurge: 1)
# 2. ClickHouse: rolling restart one replica at a time
# 3. NATS: rolling restart maintaining quorum
# 4. PostgreSQL: Patroni-managed switchover
```

**Blue-Green Deployment (for major versions)**:
```bash
# Deploy new version alongside old
helm install rayolly-v2 rayolly/rayolly \
  --namespace rayolly-v2 \
  --create-namespace \
  -f values-production.yaml \
  --set global.imageTag="2.0.0"

# Run migration and validation
rayolly-cli upgrade validate --from rayolly --to rayolly-v2

# Switch traffic
rayolly-cli upgrade cutover --from rayolly --to rayolly-v2

# Clean up old version (after validation period)
helm uninstall rayolly --namespace rayolly
```

---

## 12. Observability (Self-Monitoring)

### 12.1 Dogfooding Architecture

RayOlly monitors itself. Every component is instrumented with OpenTelemetry and sends telemetry to a dedicated internal RayOlly tenant.

```
┌───────────────────────────────────────────────────────────┐
│                  RayOlly Platform                           │
│                                                             │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐           │
│  │  gateway   │  │  ingester  │  │   query    │  ...      │
│  │  ┌──────┐  │  │  ┌──────┐  │  │  ┌──────┐  │           │
│  │  │ OTEL │  │  │  │ OTEL │  │  │  │ OTEL │  │           │
│  │  │ SDK  │  │  │  │ SDK  │  │  │  │ SDK  │  │           │
│  │  └──┬───┘  │  │  └──┬───┘  │  │  └──┬───┘  │           │
│  └─────┼──────┘  └─────┼──────┘  └─────┼──────┘           │
│        │               │               │                    │
│        ▼               ▼               ▼                    │
│  ┌─────────────────────────────────────────────────┐       │
│  │          OTEL Collector (sidecar or daemonset)    │       │
│  └────────────────────┬────────────────────────────┘       │
│                       │                                     │
│                       ▼                                     │
│  ┌─────────────────────────────────────────────────┐       │
│  │     RayOlly Internal Tenant ("__rayolly__")       │       │
│  │     (Same platform, isolated tenant namespace)     │       │
│  └─────────────────────────────────────────────────┘       │
└───────────────────────────────────────────────────────────┘
```

### 12.2 Internal Metrics

Key metrics exposed by each component via OTEL:

| Metric | Component | Type | Description |
|--------|-----------|------|-------------|
| `rayolly_gateway_requests_total` | gateway | Counter | Total API requests |
| `rayolly_gateway_request_duration_seconds` | gateway | Histogram | Request latency |
| `rayolly_ingester_events_total` | ingester | Counter | Total events ingested |
| `rayolly_ingester_events_per_second` | ingester | Gauge | Current ingestion rate |
| `rayolly_ingester_batch_size` | ingester | Histogram | Batch sizes written |
| `rayolly_query_executions_total` | query | Counter | Total queries executed |
| `rayolly_query_duration_seconds` | query | Histogram | Query latency |
| `rayolly_query_rows_scanned` | query | Counter | Total rows scanned |
| `rayolly_storage_bytes_total` | storage | Gauge | Total storage used |
| `rayolly_storage_tier_bytes` | storage | Gauge | Storage per tier |
| `rayolly_ai_inference_total` | ai-engine | Counter | Total ML inferences |
| `rayolly_ai_inference_duration_seconds` | ai-engine | Histogram | Inference latency |
| `rayolly_agent_executions_total` | agent-runtime | Counter | Total agent runs |
| `rayolly_agent_active` | agent-runtime | Gauge | Currently running agents |
| `rayolly_alerter_evaluations_total` | alerter | Counter | Alert rule evaluations |
| `rayolly_alerter_firing` | alerter | Gauge | Currently firing alerts |

### 12.3 Platform SLOs

| Service | SLI | SLO Target | Burn Rate Alert |
|---------|-----|-----------|-----------------|
| Ingestion | Successful ingest / total ingest attempts | 99.95% | 14.4x (1h), 6x (6h) |
| Query | Queries completing < 5s / total queries | 99.0% | 14.4x (1h), 6x (6h) |
| API Availability | Successful responses (non-5xx) / total | 99.95% | 14.4x (1h), 6x (6h) |
| Alert Evaluation | Evaluations on-time / total evaluations | 99.9% | 14.4x (1h), 6x (6h) |
| Dashboard Load | Page loads < 3s / total loads | 99.0% | 14.4x (1h), 6x (6h) |
| AI Agent | Successful completions / total invocations | 99.0% | 6x (6h) |

### 12.4 Internal Dashboards

Pre-built dashboards for platform operators:

1. **Platform Overview** — Service health, ingestion rate, query rate, error rate, active tenants
2. **Ingestion Pipeline** — Events/sec, batch sizes, NATS queue depth, backpressure events
3. **Query Performance** — Query latency percentiles, slow queries, cache hit rate, rows scanned
4. **Storage Health** — ClickHouse disk usage, replication lag, compaction status, S3 usage
5. **AI Engine** — Inference latency, model accuracy, LLM token usage, agent success rate
6. **Capacity Planning** — Resource utilization trends, scaling events, cost projections
7. **SLO Dashboard** — Error budget remaining per SLO, burn rate, historical compliance

---

## 13. CI/CD Pipeline

### 13.1 Pipeline Architecture

```
┌────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  Git   │───►│  Build   │───►│   Test   │───►│ Publish  │───►│  Deploy  │
│  Push  │    │  (GHA)   │    │  (GHA)   │    │  (GHA)   │    │ (ArgoCD) │
└────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
                  │                │                │                │
                  ▼                ▼                ▼                ▼
             Build images    Unit tests       Push to         GitOps sync
             (multi-arch)   Integration      registry        Canary → Prod
             Lint + SAST     E2E tests      Sign images
                            Load tests      Helm package
```

### 13.2 GitHub Actions Workflow

```yaml
# .github/workflows/ci.yml
name: CI/CD Pipeline

on:
  push:
    branches: [main, release/*]
  pull_request:
    branches: [main]

env:
  REGISTRY: registry.rayolly.io

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Python lint (ruff)
        run: ruff check .
      - name: TypeScript lint (eslint)
        run: cd web && npm ci && npm run lint
      - name: Helm lint
        run: helm lint deploy/helm/rayolly

  test-unit:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        service: [gateway, ingester, query, storage, ai-engine, agent-runtime, alerter, scheduler]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Run unit tests
        run: |
          cd services/${{ matrix.service }}
          pip install -e ".[test]"
          pytest tests/unit -v --cov --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v4

  test-integration:
    runs-on: ubuntu-latest
    needs: [lint, test-unit]
    services:
      clickhouse:
        image: clickhouse/clickhouse-server:24.3
        ports: ["9000:9000", "8123:8123"]
      nats:
        image: nats:2.10-alpine
        ports: ["4222:4222"]
        options: --entrypoint "/nats-server" -- "--jetstream"
      redis:
        image: redis:7-alpine
        ports: ["6379:6379"]
      postgres:
        image: postgres:16-alpine
        ports: ["5432:5432"]
        env:
          POSTGRES_PASSWORD: test
    steps:
      - uses: actions/checkout@v4
      - name: Run integration tests
        run: pytest tests/integration -v --timeout=120

  test-e2e:
    runs-on: ubuntu-latest
    needs: [test-integration]
    steps:
      - uses: actions/checkout@v4
      - name: Create Kind cluster
        uses: helm/kind-action@v1
      - name: Deploy RayOlly
        run: |
          helm install rayolly deploy/helm/rayolly \
            -f deploy/helm/rayolly/values-test.yaml \
            --namespace rayolly --create-namespace --wait --timeout=10m
      - name: Run E2E tests
        run: pytest tests/e2e -v --timeout=300
      - name: Collect logs on failure
        if: failure()
        run: kubectl logs -n rayolly -l app.kubernetes.io/part-of=rayolly --tail=200

  build-images:
    runs-on: ubuntu-latest
    needs: [test-integration]
    if: github.ref == 'refs/heads/main' || startsWith(github.ref, 'refs/heads/release/')
    strategy:
      matrix:
        service: [gateway, ingester, query, storage, ai-engine, agent-runtime, alerter, scheduler, web, operator]
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-qemu-action@v3
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ secrets.REGISTRY_USER }}
          password: ${{ secrets.REGISTRY_PASS }}
      - name: Build and push (multi-arch)
        uses: docker/build-push-action@v5
        with:
          context: services/${{ matrix.service }}
          platforms: linux/amd64,linux/arm64
          push: true
          tags: |
            ${{ env.REGISTRY }}/rayolly-${{ matrix.service }}:${{ github.sha }}
            ${{ env.REGISTRY }}/rayolly-${{ matrix.service }}:latest
          cache-from: type=gha
          cache-to: type=gha,mode=max
      - name: Sign image
        run: cosign sign --key env://COSIGN_KEY ${{ env.REGISTRY }}/rayolly-${{ matrix.service }}:${{ github.sha }}
        env:
          COSIGN_KEY: ${{ secrets.COSIGN_PRIVATE_KEY }}

  deploy-staging:
    runs-on: ubuntu-latest
    needs: [build-images, test-e2e]
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - name: Update staging manifests
        run: |
          cd deploy/argocd/overlays/staging
          kustomize edit set image "registry.rayolly.io/rayolly-*=registry.rayolly.io/rayolly-*:${{ github.sha }}"
      - name: Commit and push
        run: |
          git config user.name "CI Bot"
          git config user.email "ci@rayolly.io"
          git add -A
          git commit -m "deploy: staging ${{ github.sha }}"
          git push
      # ArgoCD auto-syncs staging
```

### 13.3 ArgoCD GitOps Structure

```
deploy/argocd/
├── base/
│   ├── kustomization.yaml
│   └── rayolly-application.yaml
├── overlays/
│   ├── staging/
│   │   ├── kustomization.yaml
│   │   └── patches/
│   │       ├── replicas.yaml
│   │       └── resources.yaml
│   ├── production-us-east/
│   │   ├── kustomization.yaml
│   │   └── patches/
│   │       ├── replicas.yaml
│   │       ├── resources.yaml
│   │       └── ingress.yaml
│   └── production-eu-west/
│       ├── kustomization.yaml
│       └── patches/
```

### 13.4 Canary Deployment

Production deployments use Argo Rollouts for canary analysis:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: rayolly-gateway
  namespace: rayolly
spec:
  replicas: 5
  strategy:
    canary:
      canaryService: rayolly-gateway-canary
      stableService: rayolly-gateway-stable
      steps:
        - setWeight: 5
        - pause: { duration: 5m }
        - analysis:
            templates:
              - templateName: gateway-success-rate
            args:
              - name: service-name
                value: rayolly-gateway-canary
        - setWeight: 25
        - pause: { duration: 10m }
        - analysis:
            templates:
              - templateName: gateway-success-rate
              - templateName: gateway-latency
        - setWeight: 50
        - pause: { duration: 10m }
        - setWeight: 100
      analysis:
        templates:
          - templateName: gateway-success-rate
        startingStep: 2
        args:
          - name: service-name
            value: rayolly-gateway-canary

---
apiVersion: argoproj.io/v1alpha1
kind: AnalysisTemplate
metadata:
  name: gateway-success-rate
spec:
  args:
    - name: service-name
  metrics:
    - name: success-rate
      interval: 60s
      successCondition: result[0] >= 0.995
      failureLimit: 3
      provider:
        prometheus:
          address: http://prometheus:9090
          query: |
            sum(rate(rayolly_gateway_requests_total{service="{{args.service-name}}",status!~"5.."}[5m]))
            /
            sum(rate(rayolly_gateway_requests_total{service="{{args.service-name}}"}[5m]))
```

### 13.5 Feature Flags

RayOlly uses a built-in feature flag system (with optional LaunchDarkly integration for SaaS):

| Flag | Scope | Purpose |
|------|-------|---------|
| `ai_agents_v2` | Global / Tenant | Enable v2 agent runtime |
| `clickhouse_v24` | Global | Enable ClickHouse 24.x features |
| `nl_query_claude_opus` | Tenant | Use Opus model for NL queries |
| `experimental_traces_sampling` | Tenant | New trace sampling algorithm |
| `dark_launch_metrics_v2` | Global | Shadow-launch new metrics pipeline |

---

## 14. Security Hardening

### 14.1 Pod Security Standards

All RayOlly pods run with the `restricted` Pod Security Standard:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: rayolly
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/warn: restricted
```

Container security context applied to all pods:

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 10001
  runAsGroup: 10001
  fsGroup: 10001
  seccompProfile:
    type: RuntimeDefault
  capabilities:
    drop: ["ALL"]
  readOnlyRootFilesystem: true
  allowPrivilegeEscalation: false
```

### 14.2 Network Policies

Default deny-all with explicit allowlists:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: rayolly
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress

---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-gateway-ingress
  namespace: rayolly
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/component: gateway
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: ingress-nginx
      ports:
        - port: 8080
          protocol: TCP
        - port: 8443
          protocol: TCP

---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-ingester-from-gateway
  namespace: rayolly
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/component: ingester
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app.kubernetes.io/component: gateway
      ports:
        - port: 9090
          protocol: TCP
```

### 14.3 Secrets Management

| Secret Type | Storage | Rotation | Access |
|-------------|---------|----------|--------|
| Database credentials | HashiCorp Vault / Sealed Secrets | 90 days | Service-specific |
| API keys (tenant) | PostgreSQL (encrypted) | Customer-controlled | Gateway only |
| TLS certificates | cert-manager / Vault PKI | Auto (Let's Encrypt) or annual | Ingress, gateway |
| Encryption keys (data at rest) | AWS KMS / Vault Transit | Annual | Storage, ClickHouse |
| LLM API keys | Vault | 90 days | AI engine only |
| Image signing keys | Vault | Annual | CI/CD only |
| OAuth/OIDC secrets | Vault / Sealed Secrets | Annual | Gateway only |

### 14.4 Image Signing and Verification

All RayOlly container images are signed with Cosign and verified at deployment:

```yaml
# Kyverno policy to enforce image signatures
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: verify-rayolly-images
spec:
  validationFailureAction: Enforce
  rules:
    - name: verify-signature
      match:
        resources:
          namespaces: ["rayolly"]
      verifyImages:
        - imageReferences:
            - "registry.rayolly.io/rayolly-*"
          attestors:
            - entries:
                - keys:
                    publicKeys: |-
                      -----BEGIN PUBLIC KEY-----
                      <rayolly-cosign-public-key>
                      -----END PUBLIC KEY-----
```

### 14.5 RBAC for Kubernetes Resources

```yaml
# ClusterRole for RayOlly Operator
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: rayolly-operator
rules:
  - apiGroups: ["rayolly.io"]
    resources: ["rayollyclusters", "rayollypipelines", "rayollytenants"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
  - apiGroups: ["rayolly.io"]
    resources: ["rayollyclusters/status", "rayollypipelines/status", "rayollytenants/status"]
    verbs: ["get", "update", "patch"]
  - apiGroups: ["apps"]
    resources: ["deployments", "statefulsets"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
  - apiGroups: [""]
    resources: ["services", "configmaps", "secrets", "persistentvolumeclaims"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
  - apiGroups: ["autoscaling"]
    resources: ["horizontalpodautoscalers"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
  - apiGroups: ["policy"]
    resources: ["poddisruptionbudgets"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
  - apiGroups: ["coordination.k8s.io"]
    resources: ["leases"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
```

---

## 15. Performance Testing

### 15.1 Load Testing Framework

Performance testing uses a combination of tools:

| Tool | Purpose | Scope |
|------|---------|-------|
| Locust | HTTP/gRPC load generation | API endpoints |
| Custom OTEL generator | High-volume OTEL data generation | Ingestion pipeline |
| ClickHouse benchmark | Query performance | Storage layer |
| k6 | Frontend load testing | Web UI |

### 15.2 Benchmark Suite

| Benchmark | Methodology | Target |
|-----------|-------------|--------|
| Ingestion throughput | Sustained OTEL event generation for 1 hour | > 1M events/sec/node |
| Ingestion latency (e2e) | Time from OTEL send to queryable in ClickHouse | < 5s p99 |
| Simple query latency | `SELECT count(*) WHERE service='x' AND timestamp > now()-1h` | < 200ms p99 |
| Complex query latency | Multi-join, aggregation across 1TB dataset | < 2s p99 |
| Full-text search | Free-text search across 100M log entries | < 500ms p99 |
| Dashboard render | 10-panel dashboard with 24h time range | < 3s full load |
| AI agent execution | RCA agent on a simulated incident | < 30s to first finding |
| Concurrent users | Simultaneous dashboard viewers | 1000 users, < 5s p99 |

### 15.3 Performance Regression Detection

Every CI build runs a subset of benchmarks against the staging environment. Results are compared to the rolling 7-day baseline:

- **Regression threshold**: > 10% degradation in p99 latency or throughput triggers a CI failure
- **Results storage**: Benchmark results stored in ClickHouse (self-monitoring tenant)
- **Alerting**: Automatic Slack notification on regression detection
- **Trend dashboard**: Historical performance trends visible in the internal RayOlly dashboard

---

## 16. Cost Optimization

### 16.1 Compute Cost Strategies

| Strategy | Applicability | Savings | Risk |
|----------|--------------|---------|------|
| Spot/preemptible instances | Stateless services (gateway, ingester, query, web) | 60–70% | Pod preemption, mitigated by PDBs |
| Reserved instances | ClickHouse, PostgreSQL, NATS (stateful) | 30–40% | Commitment lock-in |
| ARM instances (Graviton/Ampere) | All services (multi-arch images) | 20–30% | None (full support) |
| Right-sizing (VPA recommendations) | All services | 10–20% | None |
| Cluster autoscaler | Node-level scaling | Variable | Cold start latency |

### 16.2 Storage Cost Strategies

| Tier | Storage Type | Cost (approx) | Retention | Access Pattern |
|------|-------------|---------------|-----------|----------------|
| Hot | ClickHouse on NVMe/SSD | $0.10/GB/mo | 1–7 days | Frequent queries |
| Warm | ClickHouse on gp3/standard SSD | $0.05/GB/mo | 7–30 days | Occasional queries |
| Cold | Parquet on S3 Standard | $0.023/GB/mo | 30–365 days | Rare queries |
| Archive | Parquet on S3 Glacier | $0.004/GB/mo | 1–7 years | Compliance only |

**Example cost comparison** (1TB/day ingestion, 30-day hot, 365-day total):

| Vendor | Monthly Cost | Annual Cost |
|--------|-------------|-------------|
| Datadog (per GB) | ~$75,000 | ~$900,000 |
| Splunk (per GB) | ~$60,000 | ~$720,000 |
| **RayOlly** | **~$8,000** | **~$96,000** |

### 16.3 Reserved Capacity Planning

For SaaS operations, reserved capacity is planned quarterly:

1. Analyze 90-day usage trends per region
2. Reserve baseline compute (RI/Savings Plans) at p50 utilization
3. Use on-demand/spot for p50–p90 burst capacity
4. Alert at p80 reserved capacity utilization for re-evaluation

---

## 17. Success Metrics

### 17.1 Infrastructure KPIs

| Metric | Target | Measurement |
|--------|--------|-------------|
| SaaS Availability | 99.95% monthly | Uptime monitoring (external) |
| Deployment frequency | Multiple per day (SaaS) | ArgoCD sync count |
| Deployment failure rate | < 2% | Failed canary analysis / total deploys |
| Mean time to deploy | < 15 minutes (canary to full rollout) | ArgoCD metrics |
| Self-hosted install success rate | > 95% first attempt | Telemetry from install wizard |
| Upgrade success rate | > 99% | Operator upgrade tracking |
| DR recovery time (tested) | < 15 minutes | Quarterly DR drill results |
| Infrastructure cost per event | < $0.000001 | Cost tracking / event count |

### 17.2 Scaling KPIs

| Metric | Target | Notes |
|--------|--------|-------|
| Max sustained ingestion | 10M events/sec | Enterprise tier |
| Linear scaling efficiency | > 85% | Throughput per pod stays within 85% of single-pod baseline |
| Auto-scale reaction time | < 2 minutes | Time from trigger to new pod ready |
| ClickHouse query latency at scale | < 2s p99 at 100TB | With proper shard count |

### 17.3 Operational KPIs

| Metric | Target | Notes |
|--------|--------|-------|
| Tenant provisioning time | < 30 seconds | SaaS new tenant setup |
| Platform incidents (P1/P2) | < 2 per quarter | Self-monitoring effectiveness |
| Mean time to detect (platform issues) | < 2 minutes | Dogfooding alerting |
| Mean time to resolve (platform issues) | < 30 minutes | Runbook effectiveness |

---

## 18. Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Kubernetes complexity for self-hosted customers | High | High | Installation wizard, extensive docs, support tiers, Docker Compose fallback |
| ClickHouse operational burden | Medium | High | Operator automates lifecycle; managed ClickHouse Cloud as alternative |
| Multi-region data consistency | Medium | Medium | Async replication with conflict resolution; observability data is region-local |
| Spot instance preemption during load spike | Medium | Medium | PodDisruptionBudgets, graceful drain, fallback to on-demand |
| Air-gapped AI model quality | Medium | Medium | Fine-tune local models on observability domain; hybrid mode available |
| Helm chart complexity | Medium | Low | Opinionated defaults, size-based value presets, validation hooks |
| Supply chain attack (compromised images) | Low | Critical | Image signing (Cosign), SBOM generation, vulnerability scanning |
| ClickHouse shard rebalancing during growth | Medium | Medium | Operator-managed, off-peak scheduling, incremental rebalancing |
| NATS JetStream message loss | Low | High | R=3 replication, publisher acks, consumer replay from last ack |
| Cost overrun in SaaS (unexpected tenant growth) | Medium | Medium | Usage alerts, automatic throttling, capacity planning automation |
| Cross-region latency for hybrid deployments | Medium | Low | Edge caching for config, local-first data path |
| Kubernetes version incompatibility | Low | Medium | Test matrix across K8s 1.28–1.31, CI validation |

---

## Appendix A: Kubernetes Manifest — Complete Gateway Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: rayolly-gateway
  namespace: rayolly
  labels:
    app.kubernetes.io/name: rayolly
    app.kubernetes.io/component: gateway
    app.kubernetes.io/part-of: rayolly
    app.kubernetes.io/version: "1.0.0"
spec:
  replicas: 3
  revisionHistoryLimit: 5
  selector:
    matchLabels:
      app.kubernetes.io/component: gateway
  template:
    metadata:
      labels:
        app.kubernetes.io/name: rayolly
        app.kubernetes.io/component: gateway
        app.kubernetes.io/part-of: rayolly
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "9102"
        prometheus.io/path: "/metrics"
    spec:
      serviceAccountName: rayolly-gateway
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app.kubernetes.io/component: gateway
      containers:
        - name: gateway
          image: registry.rayolly.io/rayolly-gateway:1.0.0
          ports:
            - name: http
              containerPort: 8080
              protocol: TCP
            - name: grpc
              containerPort: 9090
              protocol: TCP
            - name: health
              containerPort: 8081
              protocol: TCP
            - name: metrics
              containerPort: 9102
              protocol: TCP
          env:
            - name: RAYOLLY_ENV
              value: "production"
            - name: RAYOLLY_LOG_LEVEL
              value: "info"
            - name: RAYOLLY_LOG_FORMAT
              value: "json"
            - name: RAYOLLY_NATS_URL
              valueFrom:
                secretKeyRef:
                  name: rayolly-nats-credentials
                  key: url
            - name: RAYOLLY_POSTGRES_URL
              valueFrom:
                secretKeyRef:
                  name: rayolly-postgres-credentials
                  key: url
            - name: RAYOLLY_REDIS_URL
              valueFrom:
                secretKeyRef:
                  name: rayolly-redis-credentials
                  key: url
          resources:
            requests:
              cpu: "1"
              memory: "1Gi"
            limits:
              cpu: "4"
              memory: "2Gi"
          securityContext:
            readOnlyRootFilesystem: true
            allowPrivilegeEscalation: false
            capabilities:
              drop: ["ALL"]
          livenessProbe:
            httpGet:
              path: /healthz
              port: health
            initialDelaySeconds: 15
            periodSeconds: 10
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /readyz
              port: health
            initialDelaySeconds: 5
            periodSeconds: 5
            failureThreshold: 2
          startupProbe:
            httpGet:
              path: /healthz
              port: health
            initialDelaySeconds: 5
            periodSeconds: 5
            failureThreshold: 30
          volumeMounts:
            - name: tmp
              mountPath: /tmp
            - name: config
              mountPath: /etc/rayolly
              readOnly: true
      volumes:
        - name: tmp
          emptyDir: {}
        - name: config
          configMap:
            name: rayolly-gateway-config
      terminationGracePeriodSeconds: 60

---
apiVersion: v1
kind: Service
metadata:
  name: rayolly-gateway
  namespace: rayolly
spec:
  selector:
    matchLabels:
      app.kubernetes.io/component: gateway
  ports:
    - name: http
      port: 8080
      targetPort: http
    - name: grpc
      port: 9090
      targetPort: grpc

---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: rayolly-gateway
  namespace: rayolly
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app.kubernetes.io/component: gateway

---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: rayolly-gateway
  namespace: rayolly
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/proxy-body-size: "50m"
spec:
  ingressClassName: nginx
  tls:
    - hosts:
        - api.rayolly.example.com
      secretName: rayolly-gateway-tls
  rules:
    - host: api.rayolly.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: rayolly-gateway
                port:
                  number: 8080
```

---

## Appendix B: Operator Reconciliation Flow

```
                    ┌─────────────────────────┐
                    │  RayOllyCluster CR       │
                    │  (desired state)         │
                    └───────────┬──────────────┘
                                │
                    ┌───────────▼──────────────┐
                    │  Operator Reconcile Loop  │
                    └───────────┬──────────────┘
                                │
                ┌───────────────┼───────────────┐
                │               │               │
        ┌───────▼──────┐ ┌─────▼──────┐ ┌─────▼──────────┐
        │ Ensure       │ │ Ensure     │ │ Ensure          │
        │ Infrastructure│ │ Services  │ │ Configuration   │
        │ (CH, NATS,   │ │ (gateway, │ │ (ConfigMaps,    │
        │  Redis, PG)  │ │  ingester,│ │  Secrets,       │
        └───────┬──────┘ │  etc.)    │ │  NetworkPolicies│
                │        └─────┬─────┘ └────────┬────────┘
                │              │                 │
                └──────────────┼─────────────────┘
                               │
                    ┌──────────▼──────────────┐
                    │  Update Status           │
                    │  (phase, conditions,     │
                    │   component readiness)   │
                    └──────────┬──────────────┘
                               │
                    ┌──────────▼──────────────┐
                    │  Requeue after 30s       │
                    └─────────────────────────┘
```

The Operator handles:
- Initial deployment of all components from a `RayOllyCluster` spec
- Scaling adjustments when the spec changes
- Version upgrades (rolling update strategy)
- Health monitoring and automatic remediation (restart crashed components)
- ClickHouse schema migrations on version upgrade
- Certificate rotation

---

*PRD-13 defines the deployment, infrastructure, and scalability foundation for the RayOlly platform. All other PRDs depend on this infrastructure to operate in production.*
