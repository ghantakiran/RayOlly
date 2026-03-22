"use client";

import { useState, useEffect } from "react";
import {
  Bell,
  BellOff,
  CheckCircle2,
  Clock,
  Eye,
  ToggleLeft,
  ToggleRight,
} from "lucide-react";
import * as Tabs from "@radix-ui/react-tabs";
import { cn, severityBgColor, formatTimestamp } from "@/lib/utils";
import { TimeRangePicker } from "@/components/shared/time-range-picker";
import { getActiveAlerts, getAlertRules, getAlertHistory } from "@/lib/api";

// ---------------------------------------------------------------------------
// Types for API responses
// ---------------------------------------------------------------------------

interface AlertData {
  id: string;
  name: string;
  severity: string;
  service: string;
  message: string;
  value: number;
  threshold: number;
  status: string;
  fired_at: string;
  rule_id: string;
}

interface RuleData {
  id: string;
  name: string;
  metric_name: string;
  operator: string;
  threshold: number;
  severity: string;
  service: string;
  enabled: boolean;
  query: string;
  condition: string;
}

interface HistoryData {
  id: string;
  alert_name: string;
  service: string;
  severity: string;
  status: string;
  timestamp: string;
  message: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const severityOrder: Record<string, number> = {
  critical: 0,
  error: 1,
  warning: 2,
  info: 3,
};

function SeverityBadge({ severity }: { severity: string }) {
  const s = severity as "ok" | "info" | "warning" | "error" | "critical" | "fatal";
  return (
    <span className={cn("w-16 shrink-0 rounded px-1.5 py-0.5 text-center text-[10px] font-semibold uppercase", severityBgColor(s))}>
      {severity}
    </span>
  );
}

function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center py-12">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-gray-600 border-t-blue-500" />
      <span className="ml-3 text-text-muted">Loading...</span>
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-text-muted">
      <p className="text-sm">{message}</p>
      <p className="text-xs mt-1">Alerts fire when real data thresholds are breached.</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<AlertData[]>([]);
  const [rules, setRules] = useState<RuleData[]>([]);
  const [history, setHistory] = useState<HistoryData[]>([]);
  const [loading, setLoading] = useState(true);
  const [sortBy, setSortBy] = useState<"severity" | "time">("time");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    Promise.all([getActiveAlerts(), getAlertRules(), getAlertHistory()])
      .then(([alertsRes, rulesRes, histRes]) => {
        if (cancelled) return;
        setAlerts(alertsRes?.alerts || []);
        setRules(rulesRes?.rules || []);
        setHistory(histRes?.history || []);
        setLoading(false);
      })
      .catch(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, []);

  const sortedAlerts = [...alerts].sort((a, b) => {
    if (sortBy === "severity") {
      return (severityOrder[a.severity] ?? 5) - (severityOrder[b.severity] ?? 5);
    }
    return new Date(b.fired_at).getTime() - new Date(a.fired_at).getTime();
  });

  const firingCount = alerts.filter((a) => a.status === "firing").length;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-text-primary">Alerts</h1>
          <p className="mt-0.5 text-sm text-text-muted">Manage alerts and rules -- powered by real ClickHouse data</p>
        </div>
        <TimeRangePicker />
      </div>

      {loading ? (
        <LoadingSpinner />
      ) : (
        <Tabs.Root defaultValue="active" className="space-y-4">
          <Tabs.List className="flex gap-1 rounded-lg bg-surface-secondary p-1 w-fit border border-border-default">
            <Tabs.Trigger
              value="active"
              className="rounded-md px-4 py-1.5 text-sm font-medium text-text-muted data-[state=active]:bg-navy-700 data-[state=active]:text-text-primary transition-colors"
            >
              Active Alerts
              {firingCount > 0 && (
                <span className="ml-1.5 rounded-full bg-severity-critical/20 px-1.5 py-px text-[10px] font-semibold text-severity-critical">
                  {firingCount}
                </span>
              )}
            </Tabs.Trigger>
            <Tabs.Trigger
              value="rules"
              className="rounded-md px-4 py-1.5 text-sm font-medium text-text-muted data-[state=active]:bg-navy-700 data-[state=active]:text-text-primary transition-colors"
            >
              Alert Rules
            </Tabs.Trigger>
            <Tabs.Trigger
              value="history"
              className="rounded-md px-4 py-1.5 text-sm font-medium text-text-muted data-[state=active]:bg-navy-700 data-[state=active]:text-text-primary transition-colors"
            >
              History
            </Tabs.Trigger>
          </Tabs.List>

          {/* Active Alerts Tab */}
          <Tabs.Content value="active" className="space-y-3">
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1 rounded-lg border border-border-default/60 bg-surface-secondary">
                <button
                  onClick={() => setSortBy("time")}
                  className={cn(
                    "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                    sortBy === "time" ? "bg-navy-700 text-text-primary" : "text-text-muted",
                  )}
                >
                  <Clock className="inline h-3 w-3 mr-1" />
                  Time
                </button>
                <button
                  onClick={() => setSortBy("severity")}
                  className={cn(
                    "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                    sortBy === "severity" ? "bg-navy-700 text-text-primary" : "text-text-muted",
                  )}
                >
                  Severity
                </button>
              </div>
              <span className="ml-auto text-xs text-text-muted">
                {sortedAlerts.length} alert{sortedAlerts.length !== 1 ? "s" : ""}
              </span>
            </div>

            {sortedAlerts.length === 0 ? (
              <EmptyState message="No active alerts. All systems nominal." />
            ) : (
              <div className="rounded-xl border border-border-default/60 bg-surface-secondary">
                {sortedAlerts.map((alert, i) => (
                  <div
                    key={alert.id}
                    className={cn(
                      "flex items-center gap-4 px-4 py-3 transition-colors hover:bg-navy-800/40",
                      i < sortedAlerts.length - 1 && "border-b border-border-subtle",
                    )}
                  >
                    <Bell className={cn(
                      "h-4 w-4 shrink-0",
                      alert.severity === "critical" ? "text-severity-critical" : "text-severity-warning"
                    )} />
                    <SeverityBadge severity={alert.severity} />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-text-primary">{alert.name}</p>
                      <p className="text-xs text-text-muted">
                        {alert.service} &middot; {alert.message}
                      </p>
                    </div>
                    <div className="shrink-0 text-right">
                      <p className="text-xs text-text-muted">{formatTimestamp(alert.fired_at)}</p>
                      <p className="text-[10px] font-medium capitalize text-severity-critical">
                        {alert.status}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Tabs.Content>

          {/* Rules Tab */}
          <Tabs.Content value="rules">
            {rules.length === 0 ? (
              <EmptyState message="No alert rules configured." />
            ) : (
              <div className="rounded-xl border border-border-default/60 bg-surface-secondary">
                <div className="grid grid-cols-[1fr_200px_100px_120px_80px] gap-2 border-b border-border-default px-4 py-2 text-[10px] font-medium uppercase tracking-wider text-text-muted">
                  <span>Rule Name</span>
                  <span>Condition</span>
                  <span>Severity</span>
                  <span>Service</span>
                  <span>Enabled</span>
                </div>
                {rules.map((rule, i) => (
                  <div
                    key={rule.id}
                    className={cn(
                      "grid grid-cols-[1fr_200px_100px_120px_80px] items-center gap-2 px-4 py-2.5",
                      i < rules.length - 1 && "border-b border-border-subtle",
                    )}
                  >
                    <span className="text-sm font-medium text-text-primary">{rule.name}</span>
                    <span className="truncate font-mono text-xs text-text-muted">{rule.condition}</span>
                    <SeverityBadge severity={rule.severity} />
                    <span className="text-xs text-text-secondary">{rule.service || "all"}</span>
                    <span>
                      {rule.enabled ? (
                        <ToggleRight className="h-5 w-5 text-severity-ok" />
                      ) : (
                        <ToggleLeft className="h-5 w-5 text-text-muted" />
                      )}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Tabs.Content>

          {/* History Tab */}
          <Tabs.Content value="history">
            {history.length === 0 ? (
              <EmptyState message="No alert history yet." />
            ) : (
              <div className="rounded-xl border border-border-default/60 bg-surface-secondary">
                {history.map((entry, i) => (
                  <div
                    key={entry.id}
                    className={cn(
                      "flex items-center gap-4 px-4 py-3",
                      i < history.length - 1 && "border-b border-border-subtle",
                    )}
                  >
                    <SeverityBadge severity={entry.severity} />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-text-primary">{entry.alert_name}</p>
                      <p className="text-xs text-text-muted">
                        {entry.service} &middot; {entry.message}
                      </p>
                    </div>
                    <div className="shrink-0 text-right">
                      <p className="text-xs text-text-muted">{formatTimestamp(entry.timestamp)}</p>
                      <p className={cn(
                        "text-[10px] font-medium capitalize",
                        entry.status === "firing" ? "text-severity-critical" : "text-severity-ok"
                      )}>
                        {entry.status}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Tabs.Content>
        </Tabs.Root>
      )}
    </div>
  );
}
