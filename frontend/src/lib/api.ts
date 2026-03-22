const API_BASE = "/api/v1";

function getHeaders(): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("rayolly_token");
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    } else {
      headers["X-RayOlly-Tenant"] = "demo";
    }
  } else {
    headers["X-RayOlly-Tenant"] = "demo";
  }
  return headers;
}

async function fetchApi<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { headers: getHeaders() });
  if (!res.ok) return {} as T; // Graceful fallback
  return res.json();
}

// Dashboard
export async function getDashboardOverview() {
  return fetchApi<{
    total_services: number;
    healthy: number;
    warning: number;
    critical: number;
    total_logs_24h: number;
    error_count_24h: number;
    error_rate_pct: number;
    ingestion_rate_per_min: number;
  }>("/dashboard/overview");
}

export async function getIngestionChart() {
  return fetchApi<{ timestamp: string; count: number; error_count: number }[]>(
    "/dashboard/ingestion-chart",
  );
}

export async function getTopServices() {
  return fetchApi<
    { service: string; log_count: number; error_count: number; error_rate_pct: number }[]
  >("/dashboard/top-services");
}

export async function getRecentErrors() {
  return fetchApi<
    { timestamp: string; service: string; body: string; attributes: Record<string, string> }[]
  >("/dashboard/recent-errors");
}

// Logs
export async function searchLogs(params: Record<string, string>) {
  const qs = new URLSearchParams(params).toString();
  return fetchApi<
    {
      timestamp: string;
      service: string;
      host: string;
      severity: string;
      body: string;
      attributes: Record<string, string>;
    }[]
  >(`/data/logs/search?${qs}`);
}

export async function getLogVolume() {
  return fetchApi<{ timestamp: string; count: number; error_count: number }[]>(
    "/data/logs/volume",
  );
}

export async function getLogServices() {
  return fetchApi<{ service: string; count: number }[]>("/data/logs/services");
}

// Metrics
export async function getMetricsList() {
  return fetchApi<{ name: string; type: string; point_count: number }[]>("/data/metrics/list");
}

export async function getMetricQuery(name: string) {
  return fetchApi<{ timestamp: string; value: number }[]>(
    `/data/metrics/query?name=${encodeURIComponent(name)}`,
  );
}

// Traces
export async function searchTraces(params: Record<string, string>) {
  const qs = new URLSearchParams(params).toString();
  return fetchApi<
    {
      trace_id: string;
      root_service: string;
      root_operation: string;
      duration_ms: number;
      span_count: number;
      status: string;
    }[]
  >(`/data/traces/search?${qs}`);
}

export async function getTraceServices() {
  return fetchApi<
    { service: string; span_count: number; avg_duration_ms: number; error_rate: number }[]
  >("/data/traces/services");
}

// Agent invocation
export async function invokeAgent(agentType: string, input: Record<string, any>) {
  const res = await fetch(`${API_BASE}/agents/invoke`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({ agent_type: agentType, input, async_mode: false }),
  });
  if (!res.ok) return { status: "FAILED", output: { error: await res.text() } };
  return res.json();
}

export async function chatWithAgent(agentType: string, message: string, conversationId?: string) {
  const res = await fetch(`${API_BASE}/agents/chat`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({ agent_type: agentType, message, conversation_id: conversationId }),
  });
  if (!res.ok) return { error: await res.text() };
  return res.json();
}

export async function getAgentsList() { return fetchApi('/agents'); }

// APM
export async function getAPMServices() {
  return fetchApi<{ services: { service: string; request_count: number; error_count: number; error_rate: number; avg_duration_ms: number; p99_duration_ms: number; status: string }[] }>('/data/apm/services');
}
export async function getServiceMap() {
  return fetchApi<{ nodes: { id: string; service: string; type: string; health: string; metrics: { request_count: number; error_rate: number; avg_ms: number; p99_ms: number } }[]; edges: { source: string; target: string; request_count: number; error_rate: number; avg_latency_ms: number }[] }>('/data/apm/service-map');
}
export async function getServiceEndpoints(service: string) {
  return fetchApi<{ endpoints: { operation: string; request_count: number; error_count: number; avg_ms: number; p50_ms: number; p99_ms: number }[] }>(`/data/apm/services/${encodeURIComponent(service)}/endpoints`);
}
export async function getServiceErrors(service: string) {
  return fetchApi<{ errors: { message: string; count: number; first_seen: string; last_seen: string; sample_trace_id: string }[] }>(`/data/apm/services/${encodeURIComponent(service)}/errors`);
}

// Alerts
export async function getActiveAlerts() {
  return fetchApi<{ alerts: { id: string; name: string; severity: string; service: string; message: string; value: number; threshold: number; status: string; fired_at: string; rule_id: string }[]; total: number }>('/data/alerts/active');
}
export async function getAlertRules() {
  return fetchApi<{ rules: { id: string; name: string; metric_name: string; operator: string; threshold: number; severity: string; service: string; enabled: boolean; query: string; condition: string }[] }>('/data/alerts/rules');
}
export async function getAlertHistory() {
  return fetchApi<{ history: { id: string; alert_name: string; service: string; severity: string; status: string; timestamp: string; message: string }[] }>('/data/alerts/history');
}

// Agent Observability
export async function getAgentObsDashboard() { return fetchApi('/agents/observability/dashboard'); }
export async function getAgentObsCosts() { return fetchApi('/agents/observability/costs/forecast'); }

// Integrations
export async function getAvailableIntegrations() { return fetchApi('/integrations/available'); }
export async function getConfiguredIntegrations() { return fetchApi('/integrations'); }

// Settings
export async function getCurrentUser() { return fetchApi('/auth/me'); }

// Dashboard library
export async function getDashboardsList() { return fetchApi('/dashboard/overview'); }
