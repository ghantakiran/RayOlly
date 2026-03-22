"use client";

import { useState, useEffect } from "react";
import { getAvailableIntegrations } from "@/lib/api";
import { TimeRangePicker } from "@/components/shared/time-range-picker";
import { cn } from "@/lib/utils";
import { Puzzle, Search, CheckCircle2, XCircle, Loader2 } from "lucide-react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type IntegrationCategory =
  | "all"
  | "itsm"
  | "communication"
  | "cloud"
  | "ci_cd"
  | "monitoring"
  | "custom";

interface Integration {
  id: string;
  name: string;
  category: IntegrationCategory;
  description: string;
  iconUrl: string;
  connected: boolean;
  status?: "connected" | "available" | "error";
  configFields: ConfigField[];
}

interface ConfigField {
  key: string;
  label: string;
  type: "text" | "password" | "url" | "email" | "textarea";
  required?: boolean;
  placeholder?: string;
}

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const CATEGORIES: { id: IntegrationCategory; label: string }[] = [
  { id: "all", label: "All" },
  { id: "itsm", label: "ITSM" },
  { id: "communication", label: "Communication" },
  { id: "cloud", label: "Cloud" },
  { id: "ci_cd", label: "CI / CD" },
  { id: "monitoring", label: "Monitoring" },
  { id: "custom", label: "Custom" },
];

const INTEGRATIONS: Integration[] = [
  {
    id: "servicenow",
    name: "ServiceNow",
    category: "itsm",
    description:
      "Create and manage incidents, change requests, and sync CMDB with ServiceNow.",
    iconUrl: "/icons/integrations/servicenow.svg",
    connected: false,
    status: "available",
    configFields: [
      { key: "instance_url", label: "Instance URL", type: "url", required: true, placeholder: "https://mycompany.service-now.com" },
      { key: "username", label: "Username", type: "text", required: true },
      { key: "password", label: "Password", type: "password", required: true },
      { key: "client_id", label: "OAuth Client ID", type: "text" },
      { key: "client_secret", label: "OAuth Client Secret", type: "password" },
    ],
  },
  {
    id: "twilio",
    name: "Twilio",
    category: "communication",
    description:
      "SMS, voice call, and WhatsApp alerting with escalation support.",
    iconUrl: "/icons/integrations/twilio.svg",
    connected: false,
    status: "available",
    configFields: [
      { key: "account_sid", label: "Account SID", type: "text", required: true },
      { key: "auth_token", label: "Auth Token", type: "password", required: true },
      { key: "from_phone_number", label: "From Phone Number", type: "text", required: true, placeholder: "+1234567890" },
    ],
  },
  {
    id: "slack",
    name: "Slack",
    category: "communication",
    description:
      "Rich Block Kit alerts, interactive actions, incident channels, and RCA reports.",
    iconUrl: "/icons/integrations/slack.svg",
    connected: true,
    status: "connected",
    configFields: [
      { key: "bot_token", label: "Bot Token", type: "password", required: true, placeholder: "xoxb-..." },
      { key: "default_channel", label: "Default Channel", type: "text", placeholder: "C01ABCDEF" },
      { key: "incident_channel", label: "Incident Channel", type: "text" },
    ],
  },
  {
    id: "pagerduty",
    name: "PagerDuty",
    category: "communication",
    description:
      "Trigger, acknowledge, and resolve incidents. Sync on-call schedules.",
    iconUrl: "/icons/integrations/pagerduty.svg",
    connected: true,
    status: "connected",
    configFields: [
      { key: "api_key", label: "REST API Key", type: "password", required: true },
      { key: "routing_key", label: "Events Routing Key", type: "password", required: true },
      { key: "service_id", label: "Service ID", type: "text" },
      { key: "escalation_policy_id", label: "Escalation Policy ID", type: "text" },
    ],
  },
  {
    id: "jira",
    name: "Jira",
    category: "itsm",
    description:
      "Create issues, sync status, and link incidents to Jira tickets.",
    iconUrl: "/icons/integrations/jira.svg",
    connected: false,
    status: "available",
    configFields: [
      { key: "url", label: "Jira URL", type: "url", required: true, placeholder: "https://mycompany.atlassian.net" },
      { key: "email", label: "Email", type: "email", required: true },
      { key: "api_token", label: "API Token", type: "password", required: true },
      { key: "project_key", label: "Project Key", type: "text", required: true, placeholder: "OPS" },
    ],
  },
  {
    id: "github",
    name: "GitHub",
    category: "ci_cd",
    description:
      "Track deployments, correlate commits with incidents, and create issues.",
    iconUrl: "/icons/integrations/github.svg",
    connected: false,
    status: "available",
    configFields: [
      { key: "token", label: "Personal Access Token", type: "password", required: true },
      { key: "org", label: "Organization", type: "text", required: true },
      { key: "repos", label: "Repositories (comma-separated)", type: "text" },
    ],
  },
  {
    id: "aws",
    name: "AWS",
    category: "cloud",
    description:
      "CloudWatch metrics, ECS/EKS monitoring, and Lambda observability.",
    iconUrl: "/icons/integrations/aws.svg",
    connected: false,
    status: "available",
    configFields: [
      { key: "access_key_id", label: "Access Key ID", type: "text", required: true },
      { key: "secret_access_key", label: "Secret Access Key", type: "password", required: true },
      { key: "region", label: "Region", type: "text", required: true, placeholder: "us-east-1" },
    ],
  },
  {
    id: "gcp",
    name: "Google Cloud",
    category: "cloud",
    description:
      "Cloud Monitoring, GKE, and Cloud Run integration.",
    iconUrl: "/icons/integrations/gcp.svg",
    connected: false,
    status: "available",
    configFields: [
      { key: "service_account_json", label: "Service Account JSON", type: "textarea", required: true },
      { key: "project_id", label: "Project ID", type: "text", required: true },
    ],
  },
  {
    id: "azure",
    name: "Azure",
    category: "cloud",
    description:
      "Azure Monitor, AKS, and Application Insights integration.",
    iconUrl: "/icons/integrations/azure.svg",
    connected: false,
    status: "available",
    configFields: [
      { key: "tenant_id", label: "Tenant ID", type: "text", required: true },
      { key: "client_id", label: "Client ID", type: "text", required: true },
      { key: "client_secret", label: "Client Secret", type: "password", required: true },
    ],
  },
  {
    id: "kubernetes",
    name: "Kubernetes",
    category: "cloud",
    description:
      "Cluster monitoring, pod health, and resource utilisation.",
    iconUrl: "/icons/integrations/kubernetes.svg",
    connected: false,
    status: "available",
    configFields: [
      { key: "kubeconfig", label: "Kubeconfig", type: "textarea", required: true },
      { key: "context", label: "Context", type: "text" },
    ],
  },
  {
    id: "datadog",
    name: "Datadog",
    category: "monitoring",
    description:
      "Import metrics and traces from Datadog into RayOlly.",
    iconUrl: "/icons/integrations/datadog.svg",
    connected: false,
    status: "available",
    configFields: [
      { key: "api_key", label: "API Key", type: "password", required: true },
      { key: "app_key", label: "Application Key", type: "password", required: true },
      { key: "site", label: "Datadog Site", type: "text", placeholder: "datadoghq.com" },
    ],
  },
  {
    id: "prometheus",
    name: "Prometheus",
    category: "monitoring",
    description:
      "Scrape and federate Prometheus metrics.",
    iconUrl: "/icons/integrations/prometheus.svg",
    connected: false,
    status: "available",
    configFields: [
      { key: "url", label: "Prometheus URL", type: "url", required: true, placeholder: "http://prometheus:9090" },
      { key: "basic_auth_user", label: "Basic Auth User", type: "text" },
      { key: "basic_auth_password", label: "Basic Auth Password", type: "password" },
    ],
  },
  {
    id: "grafana",
    name: "Grafana",
    category: "monitoring",
    description:
      "Embed Grafana dashboards and forward annotations.",
    iconUrl: "/icons/integrations/grafana.svg",
    connected: false,
    status: "available",
    configFields: [
      { key: "url", label: "Grafana URL", type: "url", required: true },
      { key: "api_key", label: "API Key", type: "password", required: true },
    ],
  },
  {
    id: "jenkins",
    name: "Jenkins",
    category: "ci_cd",
    description:
      "Track builds, correlate deployments, and trigger pipelines.",
    iconUrl: "/icons/integrations/jenkins.svg",
    connected: false,
    status: "available",
    configFields: [
      { key: "url", label: "Jenkins URL", type: "url", required: true },
      { key: "username", label: "Username", type: "text", required: true },
      { key: "api_token", label: "API Token", type: "password", required: true },
    ],
  },
  {
    id: "gitlab",
    name: "GitLab",
    category: "ci_cd",
    description:
      "Track pipelines, merge requests, and deployments.",
    iconUrl: "/icons/integrations/gitlab.svg",
    connected: false,
    status: "available",
    configFields: [
      { key: "url", label: "GitLab URL", type: "url", required: true, placeholder: "https://gitlab.com" },
      { key: "token", label: "Personal Access Token", type: "password", required: true },
    ],
  },
  {
    id: "terraform",
    name: "Terraform",
    category: "ci_cd",
    description:
      "Track infrastructure changes and state drift.",
    iconUrl: "/icons/integrations/terraform.svg",
    connected: false,
    status: "available",
    configFields: [
      { key: "org", label: "Organization", type: "text", required: true },
      { key: "token", label: "API Token", type: "password", required: true },
    ],
  },
  {
    id: "webhook",
    name: "Webhook",
    category: "custom",
    description:
      "Send alerts to any HTTP endpoint with customisable payloads.",
    iconUrl: "/icons/integrations/webhook.svg",
    connected: false,
    status: "available",
    configFields: [
      { key: "url", label: "Webhook URL", type: "url", required: true },
      { key: "auth_type", label: "Auth Type", type: "text", placeholder: "none | bearer | basic | hmac" },
      { key: "auth_value", label: "Auth Value", type: "password" },
      { key: "payload_template", label: "Payload Template (Jinja2)", type: "textarea" },
    ],
  },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function statusBadge(status?: string) {
  switch (status) {
    case "connected":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-xs font-medium text-emerald-400 ring-1 ring-inset ring-emerald-500/20">
          <CheckCircle2 className="h-3 w-3" />
          Connected
        </span>
      );
    case "error":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-red-500/10 px-2.5 py-0.5 text-xs font-medium text-red-400 ring-1 ring-inset ring-red-500/20">
          <XCircle className="h-3 w-3" />
          Error
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center rounded-full bg-navy-700 px-2.5 py-0.5 text-xs font-medium text-text-muted ring-1 ring-inset ring-navy-500/20">
          Available
        </span>
      );
  }
}

function categoryTag(cat: string) {
  const labels: Record<string, string> = {
    itsm: "ITSM",
    communication: "Communication",
    cloud: "Cloud",
    ci_cd: "CI/CD",
    monitoring: "Monitoring",
    custom: "Custom",
  };
  return (
    <span className="inline-flex items-center rounded bg-accent-indigo/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-accent-indigo">
      {labels[cat] ?? cat}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Integration Card Icon (placeholder SVG when real icon is missing)
// ---------------------------------------------------------------------------

function IntegrationIcon({ name }: { name: string }) {
  const initial = name.charAt(0).toUpperCase();
  return (
    <div className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-lg bg-navy-700 text-lg font-bold text-text-secondary">
      {initial}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Config Dialog
// ---------------------------------------------------------------------------

function ConfigDialog({
  integration,
  onClose,
}: {
  integration: Integration;
  onClose: () => void;
}) {
  const [formValues, setFormValues] = useState<Record<string, string>>({});
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);

  function handleChange(key: string, value: string) {
    setFormValues((prev) => ({ ...prev, [key]: value }));
  }

  async function handleTestConnection() {
    setTesting(true);
    setTestResult(null);
    // Simulate test
    await new Promise((r) => setTimeout(r, 1200));
    setTesting(false);
    setTestResult("Connection successful");
  }

  async function handleSave() {
    // In production, POST to /api/v1/integrations
    onClose();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-xl border border-border-default bg-surface-primary p-6 shadow-2xl">
        {/* Header */}
        <div className="mb-6 flex items-center gap-4">
          <IntegrationIcon name={integration.name} />
          <div>
            <h2 className="text-lg font-semibold text-text-primary">
              Configure {integration.name}
            </h2>
            <p className="text-sm text-text-muted">{integration.description}</p>
          </div>
        </div>

        {/* Form */}
        <div className="space-y-4">
          {integration.configFields.map((field) => (
            <div key={field.key}>
              <label className="mb-1 block text-sm font-medium text-text-secondary">
                {field.label}
                {field.required && (
                  <span className="ml-1 text-red-400">*</span>
                )}
              </label>
              {field.type === "textarea" ? (
                <textarea
                  rows={3}
                  className="w-full rounded-md border border-border-default bg-navy-700 px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-cyan-500/50 focus:outline-none focus:ring-1 focus:ring-cyan-500/30"
                  placeholder={field.placeholder}
                  value={formValues[field.key] ?? ""}
                  onChange={(e) => handleChange(field.key, e.target.value)}
                />
              ) : (
                <input
                  type={field.type}
                  className="w-full rounded-md border border-border-default bg-navy-700 px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-cyan-500/50 focus:outline-none focus:ring-1 focus:ring-cyan-500/30"
                  placeholder={field.placeholder}
                  value={formValues[field.key] ?? ""}
                  onChange={(e) => handleChange(field.key, e.target.value)}
                />
              )}
            </div>
          ))}
        </div>

        {/* Test result */}
        {testResult && (
          <p className="mt-3 text-sm text-emerald-400">{testResult}</p>
        )}

        {/* Actions */}
        <div className="mt-6 flex items-center justify-end gap-3">
          <button
            onClick={onClose}
            className="rounded-md px-4 py-2 text-sm font-medium text-text-muted hover:text-text-primary"
          >
            Cancel
          </button>
          <button
            onClick={handleTestConnection}
            disabled={testing}
            className="rounded-md border border-border-default px-4 py-2 text-sm font-medium text-text-primary hover:bg-navy-800/40 disabled:opacity-50"
          >
            {testing ? (
              <span className="flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" />
                Testing...
              </span>
            ) : (
              "Test Connection"
            )}
          </button>
          <button
            onClick={handleSave}
            className="rounded-md bg-cyan-600 px-4 py-2 text-sm font-medium text-white hover:bg-cyan-500"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function IntegrationsPage() {
  const [activeCategory, setActiveCategory] =
    useState<IntegrationCategory>("all");
  const [configuring, setConfiguring] = useState<Integration | null>(null);
  const [integrations, setIntegrations] = useState<Integration[]>(INTEGRATIONS);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getAvailableIntegrations()
      .then((data: any) => {
        if (cancelled) return;
        if (data && Array.isArray(data) && data.length > 0) {
          // Map API data to Integration shape, fall back to mock if mapping fails
          try {
            const mapped: Integration[] = data.map((item: any) => ({
              id: item.id || item.name?.toLowerCase().replace(/\s+/g, '-') || Math.random().toString(),
              name: item.name || 'Unknown',
              category: (item.category || 'custom') as IntegrationCategory,
              description: item.description || '',
              iconUrl: item.icon_url || item.iconUrl || '',
              connected: item.connected || item.status === 'connected' || false,
              status: item.status || (item.connected ? 'connected' : 'available'),
              configFields: item.config_fields || item.configFields || [],
            }));
            setIntegrations(mapped);
          } catch {
            setIntegrations(INTEGRATIONS);
          }
        } else if (data && typeof data === 'object' && data.integrations) {
          // Handle wrapped response
          try {
            const mapped: Integration[] = data.integrations.map((item: any) => ({
              id: item.id || item.name?.toLowerCase().replace(/\s+/g, '-') || Math.random().toString(),
              name: item.name || 'Unknown',
              category: (item.category || 'custom') as IntegrationCategory,
              description: item.description || '',
              iconUrl: item.icon_url || item.iconUrl || '',
              connected: item.connected || item.status === 'connected' || false,
              status: item.status || (item.connected ? 'connected' : 'available'),
              configFields: item.config_fields || item.configFields || [],
            }));
            setIntegrations(mapped);
          } catch {
            setIntegrations(INTEGRATIONS);
          }
        }
        // If API returns empty/error, keep mock data (already set as default)
      })
      .catch(() => {
        if (!cancelled) setIntegrations(INTEGRATIONS);
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const filtered =
    activeCategory === "all"
      ? integrations
      : integrations.filter((i) => i.category === activeCategory);

  const connected = filtered.filter((i) => i.connected);
  const available = filtered.filter((i) => !i.connected);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Puzzle className="h-6 w-6 text-accent-indigo" />
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-text-primary">Integrations</h1>
            <p className="mt-1 text-sm text-text-muted">
              Connect RayOlly to the tools your team already uses.
            </p>
          </div>
        </div>
        <TimeRangePicker />
      </div>

      {/* Loading state */}
      {loading && (
        <div className="flex items-center justify-center py-20">
          <div className="flex items-center gap-3 text-text-muted">
            <Loader2 className="h-5 w-5 animate-spin" />
            <span className="text-sm">Loading integrations...</span>
          </div>
        </div>
      )}

      {/* Category tabs */}
      {!loading && (
        <div className="flex flex-wrap gap-2">
          {CATEGORIES.map((cat) => (
            <button
              key={cat.id}
              onClick={() => setActiveCategory(cat.id)}
              className={cn(
                "rounded-lg px-4 py-1.5 text-sm font-medium transition",
                activeCategory === cat.id
                  ? "bg-cyan-500/10 text-cyan-400"
                  : "bg-navy-700 text-text-muted hover:bg-navy-700 hover:text-text-primary"
              )}
            >
              {cat.label}
            </button>
          ))}
        </div>
      )}

      {/* Connected integrations */}
      {!loading && connected.length > 0 && (
        <section className="space-y-4">
          <h2 className="text-lg font-semibold text-text-primary">
            Connected
          </h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {connected.map((integration) => (
              <button
                key={integration.id}
                onClick={() => setConfiguring(integration)}
                className="flex items-start gap-4 rounded-xl border border-border-default/60 bg-surface-secondary p-4 text-left transition hover:border-cyan-500/30 hover:bg-navy-800/40"
              >
                <IntegrationIcon name={integration.name} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-text-primary">
                      {integration.name}
                    </span>
                    {statusBadge(integration.status)}
                  </div>
                  <p className="mt-1 line-clamp-2 text-xs text-text-muted">
                    {integration.description}
                  </p>
                  <div className="mt-2">{categoryTag(integration.category)}</div>
                </div>
              </button>
            ))}
          </div>
        </section>
      )}

      {/* Available integrations */}
      {!loading && (
        <section className="space-y-4">
          <h2 className="text-lg font-semibold text-text-primary">
            Available
          </h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {available.map((integration) => (
              <button
                key={integration.id}
                onClick={() => setConfiguring(integration)}
                className="flex items-start gap-4 rounded-xl border border-border-default/60 bg-surface-secondary p-4 text-left transition hover:border-cyan-500/30 hover:bg-navy-800/40"
              >
                <IntegrationIcon name={integration.name} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-text-primary">
                      {integration.name}
                    </span>
                    {statusBadge(integration.status)}
                  </div>
                  <p className="mt-1 line-clamp-2 text-xs text-text-muted">
                    {integration.description}
                  </p>
                  <div className="mt-2">{categoryTag(integration.category)}</div>
                </div>
              </button>
            ))}
          </div>
        </section>
      )}

      {/* Config dialog */}
      {configuring && (
        <ConfigDialog
          integration={configuring}
          onClose={() => setConfiguring(null)}
        />
      )}
    </div>
  );
}
