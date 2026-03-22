"use client";

import { useState, useEffect } from "react";
import { cn } from "@/lib/utils";
import { Settings, Building2, Users, Key, Bell, Database, Loader2 } from "lucide-react";
import { getCurrentUser } from "@/lib/api";

const tabs = [
  { id: "general", label: "General", icon: Settings },
  { id: "organization", label: "Organization", icon: Building2 },
  { id: "team", label: "Team", icon: Users },
  { id: "api-keys", label: "API Keys", icon: Key },
  { id: "notifications", label: "Notifications", icon: Bell },
  { id: "data-retention", label: "Data Retention", icon: Database },
] as const;

type TabId = (typeof tabs)[number]["id"];

const apiKeys = [
  { name: "Production Ingest", prefix: "ro_prod_8x", created: "2025-11-02", lastUsed: "2m ago", status: "active" as const },
  { name: "Staging Ingest", prefix: "ro_stg_3k", created: "2025-12-15", lastUsed: "1h ago", status: "active" as const },
  { name: "CI/CD Pipeline", prefix: "ro_ci_f2", created: "2026-01-08", lastUsed: "5h ago", status: "active" as const },
  { name: "Dev Testing", prefix: "ro_dev_a1", created: "2026-02-20", lastUsed: "3d ago", status: "active" as const },
  { name: "Legacy Integration", prefix: "ro_leg_9m", created: "2025-06-10", lastUsed: "30d ago", status: "revoked" as const },
];

const teamMembers = [
  { name: "Alice Chen", email: "alice@example.com", role: "Admin" },
  { name: "Bob Martinez", email: "bob@example.com", role: "Editor" },
  { name: "Carol Kim", email: "carol@example.com", role: "Viewer" },
  { name: "Dave Singh", email: "dave@example.com", role: "Editor" },
];

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<TabId>("general");
  const [userData, setUserData] = useState<any>(null);
  const [userLoading, setUserLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setUserLoading(true);
    getCurrentUser()
      .then((data: any) => {
        if (!cancelled && data && Object.keys(data).length > 0) {
          setUserData(data);
        }
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setUserLoading(false); });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-text-primary">
          Settings
        </h1>
        <p className="mt-0.5 text-sm text-text-muted">
          Manage your organization and platform configuration
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-border-default">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "flex items-center gap-2 border-b-2 px-4 py-2.5 text-sm font-medium transition-colors",
                activeTab === tab.id
                  ? "border-cyan-400 text-cyan-400"
                  : "border-transparent text-text-muted hover:text-text-secondary"
              )}
            >
              <Icon className="h-4 w-4" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Tab content */}
      <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-6">
        {activeTab === "general" && <GeneralTab userData={userData} userLoading={userLoading} />}
        {activeTab === "organization" && <OrganizationTab />}
        {activeTab === "team" && <TeamTab />}
        {activeTab === "api-keys" && <ApiKeysTab />}
        {activeTab === "notifications" && <NotificationsTab />}
        {activeTab === "data-retention" && <DataRetentionTab />}
      </div>
    </div>
  );
}

function FieldGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <label className="text-sm font-medium text-text-secondary">{label}</label>
      {children}
    </div>
  );
}

function TextInput({ value, disabled }: { value: string; disabled?: boolean }) {
  return (
    <input
      type="text"
      defaultValue={value}
      disabled={disabled}
      className="w-full rounded-lg border border-border-default bg-navy-800/60 px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-cyan-500/50 focus:outline-none focus:ring-1 focus:ring-cyan-500/30 disabled:opacity-50"
    />
  );
}

function SelectInput({ options, defaultValue }: { options: string[]; defaultValue?: string }) {
  return (
    <select
      defaultValue={defaultValue}
      className="w-full rounded-lg border border-border-default bg-navy-800/60 px-3 py-2 text-sm text-text-primary focus:border-cyan-500/50 focus:outline-none focus:ring-1 focus:ring-cyan-500/30"
    >
      {options.map((o) => (
        <option key={o} value={o}>{o}</option>
      ))}
    </select>
  );
}

function GeneralTab({ userData, userLoading }: { userData: any; userLoading: boolean }) {
  return (
    <div className="max-w-lg space-y-5">
      {/* User info from API */}
      {userLoading ? (
        <div className="flex items-center gap-2 text-text-muted py-4">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span className="text-sm">Loading user data...</span>
        </div>
      ) : userData ? (
        <div className="rounded-lg border border-cyan-500/20 bg-cyan-500/5 p-4 space-y-2">
          <h3 className="text-sm font-medium text-cyan-400">Account Info</h3>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <span className="text-text-muted">Email</span>
            <span className="text-text-primary">{userData.email || userData.username || 'N/A'}</span>
            <span className="text-text-muted">Role</span>
            <span className="text-text-primary">{userData.role || 'N/A'}</span>
            <span className="text-text-muted">Tenant</span>
            <span className="text-text-primary">{userData.tenant || userData.tenant_id || 'demo'}</span>
          </div>
        </div>
      ) : (
        <div className="rounded-lg border border-border-default bg-navy-800/30 p-4">
          <p className="text-sm text-text-muted">
            Could not load user data from API. Showing default settings.
          </p>
        </div>
      )}

      <FieldGroup label="Organization Name">
        <TextInput value={userData?.organization || userData?.tenant || "Acme Corp"} />
      </FieldGroup>
      <FieldGroup label="Timezone">
        <SelectInput
          options={["UTC", "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles", "Europe/London", "Asia/Tokyo"]}
          defaultValue="UTC"
        />
      </FieldGroup>
      <FieldGroup label="Default Time Range">
        <SelectInput
          options={["Last 15 minutes", "Last 1 hour", "Last 4 hours", "Last 24 hours", "Last 7 days"]}
          defaultValue="Last 1 hour"
        />
      </FieldGroup>
      <button className="rounded-lg bg-cyan-500/20 px-4 py-2 text-sm font-medium text-cyan-400 transition-colors hover:bg-cyan-500/30">
        Save Changes
      </button>
    </div>
  );
}

function OrganizationTab() {
  return (
    <div className="max-w-lg space-y-5">
      <FieldGroup label="Organization ID">
        <TextInput value="org_acme_82kf3" disabled />
      </FieldGroup>
      <FieldGroup label="Plan">
        <div className="flex items-center gap-3">
          <span className="rounded-full bg-cyan-500/20 px-3 py-1 text-xs font-semibold text-cyan-400">Enterprise</span>
          <span className="text-xs text-text-muted">Unlimited seats, 90-day retention</span>
        </div>
      </FieldGroup>
      <FieldGroup label="Region">
        <TextInput value="us-east-1" disabled />
      </FieldGroup>
    </div>
  );
}

function TeamTab() {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-text-muted">{teamMembers.length} members</p>
        <button className="rounded-lg bg-cyan-500/20 px-3 py-1.5 text-xs font-medium text-cyan-400 opacity-50 cursor-not-allowed" disabled>
          Invite Member
        </button>
      </div>
      <div className="overflow-hidden rounded-lg border border-border-default">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border-default bg-navy-800/40">
              <th className="px-4 py-2.5 text-left font-medium text-text-muted">Name</th>
              <th className="px-4 py-2.5 text-left font-medium text-text-muted">Email</th>
              <th className="px-4 py-2.5 text-left font-medium text-text-muted">Role</th>
            </tr>
          </thead>
          <tbody>
            {teamMembers.map((m) => (
              <tr key={m.email} className="border-b border-border-subtle last:border-0">
                <td className="px-4 py-2.5 text-text-primary">{m.name}</td>
                <td className="px-4 py-2.5 text-text-secondary">{m.email}</td>
                <td className="px-4 py-2.5">
                  <span className={cn(
                    "rounded-full px-2 py-0.5 text-xs font-medium",
                    m.role === "Admin" ? "bg-cyan-500/20 text-cyan-400" :
                    m.role === "Editor" ? "bg-accent-blue/20 text-accent-blue" :
                    "bg-navy-700 text-text-muted"
                  )}>
                    {m.role}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ApiKeysTab() {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-text-muted">{apiKeys.length} API keys</p>
        <button className="rounded-lg bg-cyan-500/20 px-3 py-1.5 text-xs font-medium text-cyan-400 opacity-50 cursor-not-allowed" disabled>
          Generate New Key
        </button>
      </div>
      <div className="overflow-hidden rounded-lg border border-border-default">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border-default bg-navy-800/40">
              <th className="px-4 py-2.5 text-left font-medium text-text-muted">Name</th>
              <th className="px-4 py-2.5 text-left font-medium text-text-muted">Key Prefix</th>
              <th className="px-4 py-2.5 text-left font-medium text-text-muted">Created</th>
              <th className="px-4 py-2.5 text-left font-medium text-text-muted">Last Used</th>
              <th className="px-4 py-2.5 text-left font-medium text-text-muted">Status</th>
              <th className="px-4 py-2.5 text-right font-medium text-text-muted">Action</th>
            </tr>
          </thead>
          <tbody>
            {apiKeys.map((k) => (
              <tr key={k.prefix} className="border-b border-border-subtle last:border-0">
                <td className="px-4 py-2.5 text-text-primary font-medium">{k.name}</td>
                <td className="px-4 py-2.5">
                  <code className="rounded bg-navy-800/60 px-1.5 py-0.5 text-xs text-text-secondary font-mono">
                    {k.prefix}...
                  </code>
                </td>
                <td className="px-4 py-2.5 text-text-secondary">{k.created}</td>
                <td className="px-4 py-2.5 text-text-secondary">{k.lastUsed}</td>
                <td className="px-4 py-2.5">
                  <span className={cn(
                    "rounded-full px-2 py-0.5 text-xs font-medium",
                    k.status === "active"
                      ? "bg-severity-ok/10 text-severity-ok"
                      : "bg-severity-critical/10 text-severity-critical"
                  )}>
                    {k.status}
                  </span>
                </td>
                <td className="px-4 py-2.5 text-right">
                  {k.status === "active" ? (
                    <button className="rounded px-2 py-1 text-xs font-medium text-severity-critical hover:bg-severity-critical/10 transition-colors">
                      Revoke
                    </button>
                  ) : (
                    <span className="text-xs text-text-muted">-</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function NotificationsTab() {
  return (
    <div className="max-w-lg space-y-5">
      <FieldGroup label="Email Notifications">
        <SelectInput options={["All alerts", "Critical only", "None"]} defaultValue="Critical only" />
      </FieldGroup>
      <FieldGroup label="Slack Webhook URL">
        <TextInput value="https://hooks.slack.com/services/T00.../B00.../xxxx" />
      </FieldGroup>
      <FieldGroup label="PagerDuty Integration Key">
        <TextInput value="" />
      </FieldGroup>
      <button className="rounded-lg bg-cyan-500/20 px-4 py-2 text-sm font-medium text-cyan-400 transition-colors hover:bg-cyan-500/30">
        Save Changes
      </button>
    </div>
  );
}

function DataRetentionTab() {
  return (
    <div className="max-w-lg space-y-5">
      <FieldGroup label="Logs Retention">
        <SelectInput options={["7 days", "14 days", "30 days", "60 days", "90 days"]} defaultValue="30 days" />
      </FieldGroup>
      <FieldGroup label="Metrics Retention">
        <SelectInput options={["30 days", "60 days", "90 days", "180 days", "365 days"]} defaultValue="90 days" />
      </FieldGroup>
      <FieldGroup label="Traces Retention">
        <SelectInput options={["7 days", "14 days", "30 days", "60 days"]} defaultValue="14 days" />
      </FieldGroup>
      <button className="rounded-lg bg-cyan-500/20 px-4 py-2 text-sm font-medium text-cyan-400 transition-colors hover:bg-cyan-500/30">
        Save Changes
      </button>
    </div>
  );
}
