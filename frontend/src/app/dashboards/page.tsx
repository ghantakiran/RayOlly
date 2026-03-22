"use client";

import { useState } from "react";
import { LayoutGrid, Plus, Clock, User, RefreshCw, CheckCircle2, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { getDashboardsList } from "@/lib/api";

const dashboards = [
  {
    name: "Service Overview",
    description: "High-level view of all service health, latency, and throughput across the platform.",
    lastModified: "2h ago",
    creator: "Platform Team",
  },
  {
    name: "Kubernetes Cluster",
    description: "Node utilization, pod status, resource requests vs limits, and cluster autoscaling metrics.",
    lastModified: "1d ago",
    creator: "Infra Team",
  },
  {
    name: "Payment Pipeline",
    description: "End-to-end payment flow metrics including success rates, latency percentiles, and error breakdown.",
    lastModified: "4h ago",
    creator: "Payments Team",
  },
  {
    name: "Infrastructure Health",
    description: "CPU, memory, disk, and network metrics for all hosts and containers.",
    lastModified: "30m ago",
    creator: "SRE Team",
  },
  {
    name: "SLO Dashboard",
    description: "Service level objectives tracking with error budgets, burn rates, and compliance status.",
    lastModified: "6h ago",
    creator: "Reliability Team",
  },
  {
    name: "Error Budget",
    description: "Remaining error budget per service with projected exhaustion dates and historical trends.",
    lastModified: "1h ago",
    creator: "Reliability Team",
  },
];

export default function DashboardsPage() {
  const [refreshing, setRefreshing] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<'idle' | 'connected' | 'error'>('idle');

  async function handleRefresh() {
    setRefreshing(true);
    setConnectionStatus('idle');
    try {
      const data = await getDashboardsList();
      if (data && typeof data === 'object') {
        setConnectionStatus('connected');
      } else {
        setConnectionStatus('error');
      }
    } catch {
      setConnectionStatus('error');
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-text-primary">
            Dashboards
          </h1>
          <p className="mt-0.5 text-sm text-text-muted">
            Browse and manage your team dashboards
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* Connection status indicator */}
          {connectionStatus !== 'idle' && (
            <div className={cn(
              "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium",
              connectionStatus === 'connected'
                ? "bg-emerald-500/10 text-emerald-400"
                : "bg-red-500/10 text-red-400"
            )}>
              {connectionStatus === 'connected' ? (
                <><CheckCircle2 className="h-3.5 w-3.5" /> API Connected</>
              ) : (
                <><XCircle className="h-3.5 w-3.5" /> API Unreachable</>
              )}
            </div>
          )}

          {/* Refresh Data button */}
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="flex items-center gap-2 rounded-lg bg-accent-indigo/20 px-4 py-2 text-sm font-medium text-accent-indigo transition-colors hover:bg-accent-indigo/30 disabled:opacity-50"
          >
            <RefreshCw className={cn("h-4 w-4", refreshing && "animate-spin")} />
            {refreshing ? "Refreshing..." : "Refresh Data"}
          </button>

          <button
            disabled
            className="flex items-center gap-2 rounded-lg bg-cyan-500/20 px-4 py-2 text-sm font-medium text-cyan-400 opacity-50 cursor-not-allowed"
          >
            <Plus className="h-4 w-4" />
            Create Dashboard
          </button>
        </div>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {dashboards.map((d) => (
          <div
            key={d.name}
            className="group rounded-xl border border-border-default/60 bg-surface-secondary p-5 transition-colors hover:border-cyan-500/30 hover:bg-surface-elevated"
          >
            {/* Preview placeholder */}
            <div className="mb-4 flex h-32 items-center justify-center rounded-lg bg-navy-800/60 border border-border-subtle">
              <LayoutGrid className="h-8 w-8 text-text-muted/40" />
            </div>

            <h3 className="text-sm font-semibold text-text-primary group-hover:text-cyan-400 transition-colors">
              {d.name}
            </h3>
            <p className="mt-1 text-xs text-text-muted line-clamp-2">
              {d.description}
            </p>

            <div className="mt-3 flex items-center gap-4 text-[11px] text-text-muted">
              <span className="flex items-center gap-1">
                <Clock className="h-3 w-3" />
                {d.lastModified}
              </span>
              <span className="flex items-center gap-1">
                <User className="h-3 w-3" />
                {d.creator}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
