export type Severity = "ok" | "info" | "warning" | "error" | "critical" | "fatal";

export type AlertState = "firing" | "resolved" | "acknowledged" | "silenced";

export type AgentType = "rca" | "query" | "incident" | "anomaly" | "capacity" | "slo";

export type AgentStatus = "idle" | "running" | "completed" | "failed";

export interface LogRecord {
  id: string;
  timestamp: string;
  severity: Severity;
  service: string;
  message: string;
  traceId?: string;
  spanId?: string;
  attributes: Record<string, string>;
}

export interface MetricDataPoint {
  timestamp: string;
  value: number;
  labels: Record<string, string>;
}

export interface MetricSeries {
  name: string;
  unit: string;
  type: "gauge" | "counter" | "histogram" | "summary";
  dataPoints: MetricDataPoint[];
}

export interface Span {
  traceId: string;
  spanId: string;
  parentSpanId?: string;
  operationName: string;
  serviceName: string;
  startTime: string;
  duration: number; // ms
  status: "ok" | "error" | "unset";
  attributes: Record<string, string>;
  events: SpanEvent[];
}

export interface SpanEvent {
  name: string;
  timestamp: string;
  attributes: Record<string, string>;
}

export interface Trace {
  traceId: string;
  rootService: string;
  rootOperation: string;
  startTime: string;
  duration: number;
  spanCount: number;
  status: "ok" | "error";
  services: string[];
}

export interface Alert {
  id: string;
  name: string;
  severity: Severity;
  state: AlertState;
  service: string;
  message: string;
  firedAt: string;
  resolvedAt?: string;
  labels: Record<string, string>;
}

export interface AlertRule {
  id: string;
  name: string;
  condition: string;
  severity: Severity;
  enabled: boolean;
  service: string;
  evaluationInterval: string;
}

export interface Incident {
  id: string;
  title: string;
  severity: Severity;
  status: "open" | "investigating" | "mitigated" | "resolved";
  startedAt: string;
  resolvedAt?: string;
  services: string[];
  alertCount: number;
  assignee?: string;
}

export interface AgentCard {
  type: AgentType;
  name: string;
  description: string;
  status: AgentStatus;
  icon: string;
}

export interface AgentExecution {
  id: string;
  agentType: AgentType;
  status: AgentStatus;
  startedAt: string;
  completedAt?: string;
  input: string;
  output?: string;
  tokensUsed?: number;
}

export interface ServiceHealth {
  name: string;
  status: "healthy" | "degraded" | "down";
  latencyP99: number;
  errorRate: number;
  throughput: number;
}

export interface TimeRange {
  from: Date;
  to: Date;
  label?: string;
}
