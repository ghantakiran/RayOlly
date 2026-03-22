"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import {
  Activity,
  Server,
  AlertTriangle,
  Bell,
  Search,
  BarChart3,
  Bot,
  ArrowUpRight,
  ArrowDownRight,
  CheckCircle2,
  XCircle,
  Clock,
  Zap,
  ShieldAlert,
  TrendingUp,
  RefreshCw,
  ChevronRight,
  Gauge,
  Plus,
  Cpu,
  Globe,
  GitCommit,
  Users,
  Timer,
  Sparkles,
} from "lucide-react";
import { cn, formatNumber, relativeTime, truncate } from "@/lib/utils";
import { ChartWidget } from "@/components/dashboard/chart-widget";
import { TimeRangePicker } from "@/components/shared/time-range-picker";
import {
  CardSkeleton,
  ChartSkeleton,
  TableSkeleton,
} from "@/components/shared/loading-skeleton";
import {
  getDashboardOverview,
  getIngestionChart,
  getTopServices,
  getRecentErrors,
  getActiveAlerts,
} from "@/lib/api";

// ── Component ──────────────────────────────────────────────────────

export default function DashboardPage() {
  const [loading, setLoading] = useState(true);
  const [overview, setOverview] = useState<{
    total_services: number;
    healthy: number;
    warning: number;
    critical: number;
    total_logs_24h: number;
    error_count_24h: number;
    error_rate_pct: number;
    ingestion_rate_per_min: number;
  } | null>(null);
  const [ingestionChart, setIngestionChart] = useState<
    { timestamp: string; count: number; error_count: number }[]
  >([]);
  const [topServices, setTopServices] = useState<
    { service: string; log_count: number; error_count: number; error_rate_pct: number }[]
  >([]);
  const [recentErrors, setRecentErrors] = useState<
    { timestamp: string; service: string; body: string; attributes: Record<string, string> }[]
  >([]);
  const [activeAlertCount, setActiveAlertCount] = useState(0);

  useEffect(() => {
    async function load() {
      try {
        const [ov, ic, ts, re, alerts] = await Promise.all([
          getDashboardOverview(),
          getIngestionChart(),
          getTopServices(),
          getRecentErrors(),
          getActiveAlerts().catch(() => ({ alerts: [], total: 0 })),
        ]);
        setOverview(ov);
        setIngestionChart(Array.isArray(ic) ? ic : []);
        setTopServices(Array.isArray(ts) ? ts : []);
        setRecentErrors(Array.isArray(re) ? re : []);
        setActiveAlertCount((alerts as any)?.total ?? (alerts as any)?.alerts?.length ?? 0);
      } catch {
        // graceful fallback
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const totalServices = overview?.total_services ?? 0;
  const ingestionRate = overview?.ingestion_rate_per_min ?? 0;
  const errorRate = overview?.error_rate_pct ?? 0;
  const totalLogs = overview?.total_logs_24h ?? 0;
  const errorCount = overview?.error_count_24h ?? 0;

  const ingestionXData = ingestionChart.map((d) => {
    const date = new Date(d.timestamp);
    return date.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });
  });
  const ingestionYData = ingestionChart.map((d) => d.count);
  const errorYData = ingestionChart.map((d) => d.error_count);

  // Sparkline data for stat cards (last 12 data points)
  const sparkIngestion = ingestionYData.slice(-12);
  const sparkErrors = errorYData.slice(-12);

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-20 skeleton-glow rounded-xl" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <CardSkeleton />
          <CardSkeleton />
          <CardSkeleton />
          <CardSkeleton />
        </div>
        <ChartSkeleton className="h-72" />
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <TableSkeleton className="xl:col-span-2" rows={5} columns={5} />
          <CardSkeleton />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/* ── Welcome Banner ─────────────────────────────────────────── */}
      <div className="relative overflow-hidden rounded-xl border border-border-default/60 gradient-mesh aurora-bg p-5">
        <div className="relative z-10 flex items-center justify-between">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-semibold tracking-tight text-text-primary">
                Mission Control
              </h1>
              <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/15 px-2.5 py-0.5 text-[10px] font-semibold text-emerald-400">
                <span className="relative flex h-1.5 w-1.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-400" />
                </span>
                LIVE
              </span>
            </div>
            <p className="mt-1 text-sm text-text-muted">
              <span className="text-cyan-400 font-medium">{totalServices} services</span> monitored
              {" \u00B7 "}
              <span className="text-text-secondary font-medium">{formatNumber(totalLogs)} logs</span> ingested (24h)
              {activeAlertCount > 0 && (
                <>
                  {" \u00B7 "}
                  <span className="text-severity-warning font-medium">{activeAlertCount} active alert{activeAlertCount !== 1 ? "s" : ""}</span>
                </>
              )}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <TimeRangePicker />
          </div>
        </div>
      </div>

      {/* ── Stat Cards Row ─────────────────────────────────────────── */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Total Services"
          value={totalServices}
          suffix=""
          trend={{ value: overview?.healthy ?? 0, label: "healthy", positive: true }}
          sparkData={[]}
          gradient="from-cyan-500/8 to-cyan-500/[0.02]"
          accentColor="text-cyan-400"
          iconBg="bg-cyan-500/12"
          icon={Server}
        />
        <StatCard
          label="Ingestion Rate"
          value={ingestionRate}
          suffix="/min"
          trend={{ value: 12, label: "vs 1h ago", positive: true }}
          sparkData={sparkIngestion}
          gradient="from-emerald-500/8 to-emerald-500/[0.02]"
          accentColor="text-emerald-400"
          iconBg="bg-emerald-500/12"
          icon={TrendingUp}
        />
        <StatCard
          label="Error Rate"
          value={errorRate}
          suffix="%"
          trend={{
            value: errorRate > 5 ? errorRate : errorRate,
            label: errorCount + " errors (24h)",
            positive: errorRate <= 2,
          }}
          sparkData={sparkErrors}
          gradient="from-red-500/8 to-red-500/[0.02]"
          accentColor={errorRate > 5 ? "text-red-400" : errorRate > 2 ? "text-orange-400" : "text-emerald-400"}
          iconBg={errorRate > 5 ? "bg-red-500/12" : errorRate > 2 ? "bg-orange-500/12" : "bg-emerald-500/12"}
          icon={ShieldAlert}
        />
        <StatCard
          label="Active Alerts"
          value={activeAlertCount}
          suffix=""
          trend={{
            value: activeAlertCount,
            label: activeAlertCount === 0 ? "all clear" : "needs attention",
            positive: activeAlertCount === 0,
          }}
          sparkData={[]}
          gradient="from-yellow-500/8 to-yellow-500/[0.02]"
          accentColor={activeAlertCount > 0 ? "text-yellow-400" : "text-emerald-400"}
          iconBg={activeAlertCount > 0 ? "bg-yellow-500/12" : "bg-emerald-500/12"}
          icon={Bell}
        />
      </div>

      {/* ── Ingestion Chart (Full Width) ───────────────────────────── */}
      <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-4">
        <ChartWidget
          title="Ingestion Volume & Error Rate"
          type="area"
          xData={ingestionXData}
          series={[
            { name: "Ingested", data: ingestionYData, color: "#06b6d4" },
            { name: "Errors", data: errorYData, color: "#ef4444" },
          ]}
          height={280}
          yAxisLabel="events"
        />
      </div>

      {/* ── Row 3: Top Services + Recent Errors ────────────────────── */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        {/* Top Services Table (2/3 width) */}
        <div className="xl:col-span-2 rounded-xl border border-border-default/60 bg-surface-secondary overflow-hidden">
          <div className="flex items-center justify-between border-b border-border-default/60 px-4 py-3">
            <div className="flex items-center gap-2">
              <Cpu className="h-4 w-4 text-text-muted/50" />
              <h3 className="text-sm font-medium text-text-secondary">Top Services</h3>
            </div>
            <Link href="/apm" className="text-xs text-cyan-400 hover:text-cyan-300 transition-colors flex items-center gap-0.5">
              View all <ChevronRight className="h-3 w-3" />
            </Link>
          </div>
          {topServices.length === 0 ? (
            <p className="px-4 py-8 text-center text-xs text-text-muted">No service data available</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border-default/40 text-[10px] font-medium uppercase tracking-wider text-text-muted/70">
                    <th className="px-4 py-2.5 text-left">Service</th>
                    <th className="px-4 py-2.5 text-left w-10">Health</th>
                    <th className="px-4 py-2.5 text-right">Requests</th>
                    <th className="px-4 py-2.5 text-left w-32">Error Rate</th>
                    <th className="px-4 py-2.5 text-right">Errors</th>
                  </tr>
                </thead>
                <tbody>
                  {topServices.map((svc) => {
                    const healthColor =
                      svc.error_rate_pct > 10
                        ? "bg-red-400 shadow-[0_0_6px_rgba(239,68,68,0.4)]"
                        : svc.error_rate_pct > 3
                          ? "bg-yellow-400 shadow-[0_0_6px_rgba(234,179,8,0.3)]"
                          : "bg-emerald-400 shadow-[0_0_6px_rgba(34,197,94,0.3)]";
                    return (
                      <tr
                        key={svc.service}
                        className="border-b border-border-subtle/50 last:border-b-0 transition-colors hover:bg-navy-800/30"
                      >
                        <td className="px-4 py-2.5">
                          <span className="font-medium text-accent-blue text-xs">
                            {svc.service}
                          </span>
                        </td>
                        <td className="px-4 py-2.5">
                          <span className={cn("inline-block h-2 w-2 rounded-full", healthColor)} />
                        </td>
                        <td className="px-4 py-2.5 text-right">
                          <span className="font-mono text-xs text-text-primary tabular-nums">
                            {formatNumber(svc.log_count)}
                          </span>
                        </td>
                        <td className="px-4 py-2.5">
                          <div className="flex items-center gap-2">
                            <div className="h-1.5 flex-1 rounded-full bg-navy-700/60 overflow-hidden">
                              <div
                                className={cn(
                                  "h-full rounded-full transition-all",
                                  svc.error_rate_pct > 10
                                    ? "bg-red-500"
                                    : svc.error_rate_pct > 3
                                      ? "bg-yellow-500"
                                      : "bg-emerald-500",
                                )}
                                style={{ width: `${Math.min(svc.error_rate_pct, 100)}%` }}
                              />
                            </div>
                            <span className="text-xs text-text-muted w-10 text-right font-mono tabular-nums">
                              {svc.error_rate_pct.toFixed(1)}%
                            </span>
                          </div>
                        </td>
                        <td className="px-4 py-2.5 text-right">
                          <span className="font-mono text-xs text-severity-error tabular-nums">
                            {formatNumber(svc.error_count)}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Recent Errors (1/3 width) */}
        <div className="rounded-xl border border-border-default/60 bg-surface-secondary overflow-hidden">
          <div className="flex items-center justify-between border-b border-border-default/60 px-4 py-3">
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-red-400/50" />
              <h3 className="text-sm font-medium text-text-secondary">Recent Errors</h3>
            </div>
            <Link href="/logs?severity=error" className="text-xs text-cyan-400 hover:text-cyan-300 transition-colors flex items-center gap-0.5">
              View all <ChevronRight className="h-3 w-3" />
            </Link>
          </div>
          {recentErrors.length === 0 ? (
            <p className="px-4 py-8 text-center text-xs text-text-muted">No recent errors</p>
          ) : (
            <div className="max-h-[340px] overflow-y-auto divide-y divide-border-subtle/50">
              {recentErrors.slice(0, 8).map((err, i) => (
                <div
                  key={i}
                  className="px-4 py-2.5 transition-colors hover:bg-navy-800/30 border-l-2 border-l-red-500/30"
                >
                  <div className="flex items-start gap-2">
                    <span className="mt-0.5 inline-flex shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase bg-severity-error/15 text-severity-error border border-severity-error/10">
                      error
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-xs text-text-primary font-mono leading-relaxed">
                        {truncate(err.body, 80)}
                      </p>
                      <div className="mt-0.5 flex items-center gap-1.5 text-[10px] text-text-muted">
                        <span className="rounded bg-accent-blue/8 px-1.5 py-0.5 text-accent-blue font-medium">
                          {err.service}
                        </span>
                        <span>{relativeTime(err.timestamp)}</span>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── Row 4: AI Agent Activity + Quick Actions ───────────────── */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        {/* AI Agent Activity (2/3) */}
        <div className="xl:col-span-2 rounded-xl border border-border-default/60 bg-surface-secondary overflow-hidden">
          <div className="flex items-center justify-between border-b border-border-default/60 px-4 py-3">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-purple-400/60" />
              <h3 className="text-sm font-medium text-text-secondary">AI Agent Activity</h3>
            </div>
            <Link href="/agents" className="text-xs text-cyan-400 hover:text-cyan-300 transition-colors flex items-center gap-0.5">
              View all <ChevronRight className="h-3 w-3" />
            </Link>
          </div>
          <div className="divide-y divide-border-subtle/50">
            <AgentRow
              type="RCA"
              status="completed"
              description="Root cause analysis for payment-service errors"
              duration="4.2s"
              timestamp="12m ago"
            />
            <AgentRow
              type="Query"
              status="completed"
              description="'Show me error rate for auth-service last 1h'"
              duration="1.8s"
              timestamp="34m ago"
            />
            <AgentRow
              type="Anomaly"
              status="running"
              description="Detecting anomalies in api-gateway latency"
              duration="..."
              timestamp="2m ago"
            />
          </div>
        </div>

        {/* Quick Actions (1/3) */}
        <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-4">
          <h3 className="mb-3 text-sm font-medium text-text-secondary">Quick Actions</h3>
          <div className="grid grid-cols-2 gap-2">
            <QuickAction icon={Search} label="Search Logs" href="/logs" color="cyan" />
            <QuickAction icon={BarChart3} label="Query Metrics" href="/metrics" color="blue" />
            <QuickAction icon={Bot} label="Invoke AI Agent" href="/agents" color="purple" />
            <QuickAction icon={Bell} label="Create Alert" href="/alerts" color="yellow" />
          </div>
        </div>
      </div>

      {/* ── Row 5: SLO Burn Rates ────────────────────────────────────── */}
      <div className="rounded-xl border border-border-default/60 bg-surface-secondary overflow-hidden">
        <div className="flex items-center justify-between border-b border-border-default/60 px-4 py-3">
          <div className="flex items-center gap-2">
            <Gauge className="h-4 w-4 text-text-muted/50" />
            <h3 className="text-sm font-medium text-text-secondary">SLO Burn Rates</h3>
          </div>
          <span className="text-[10px] text-text-muted">30-day window</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 divide-y sm:divide-y-0 sm:divide-x divide-border-subtle/50">
          <SLOCard
            name="API Availability"
            target={99.9}
            current={99.95}
            errorBudgetRemaining={82}
            burnRate={0.6}
          />
          <SLOCard
            name="API Latency (p99)"
            target={99.5}
            current={99.2}
            errorBudgetRemaining={34}
            burnRate={2.1}
          />
          <SLOCard
            name="Ingestion Pipeline"
            target={99.99}
            current={99.98}
            errorBudgetRemaining={67}
            burnRate={1.0}
          />
          <SLOCard
            name="Query Response Time"
            target={99.0}
            current={99.4}
            errorBudgetRemaining={91}
            burnRate={0.3}
          />
        </div>
      </div>

      {/* ── Row 6: Recent Deployments + On-call ──────────────────────── */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        {/* Recent Deployments */}
        <div className="rounded-xl border border-border-default/60 bg-surface-secondary overflow-hidden">
          <div className="flex items-center justify-between border-b border-border-default/60 px-4 py-3">
            <div className="flex items-center gap-2">
              <GitCommit className="h-4 w-4 text-text-muted/50" />
              <h3 className="text-sm font-medium text-text-secondary">Recent Deployments</h3>
            </div>
            <span className="text-[10px] text-text-muted">Last 7 days</span>
          </div>
          <div className="divide-y divide-border-subtle/50">
            <DeployRow service="api-gateway" version="v2.4.1" status="success" timestamp="2h ago" author="kiran" />
            <DeployRow service="payment-service" version="v1.8.3" status="rollback" timestamp="5h ago" author="alex" />
            <DeployRow service="auth-service" version="v3.1.0" status="success" timestamp="1d ago" author="sam" />
            <DeployRow service="notification-svc" version="v1.2.7" status="canary" timestamp="1d ago" author="kiran" />
          </div>
        </div>

        {/* On-call Roster */}
        <div className="rounded-xl border border-border-default/60 bg-surface-secondary overflow-hidden">
          <div className="flex items-center justify-between border-b border-border-default/60 px-4 py-3">
            <div className="flex items-center gap-2">
              <Users className="h-4 w-4 text-text-muted/50" />
              <h3 className="text-sm font-medium text-text-secondary">On-Call Roster</h3>
            </div>
            <span className="rounded-full bg-emerald-500/10 border border-emerald-500/15 px-2 py-0.5 text-[10px] font-semibold text-emerald-400">Current Shift</span>
          </div>
          <div className="divide-y divide-border-subtle/50">
            <OnCallRow team="Platform" primary="Kiran R." secondary="Alex M." shift="06:00 - 18:00 PST" active />
            <OnCallRow team="Backend" primary="Sam L." secondary="Jordan K." shift="06:00 - 18:00 PST" active={false} />
            <OnCallRow team="Infrastructure" primary="Morgan T." secondary="Casey N." shift="18:00 - 06:00 PST" active={false} />
          </div>
          <div className="border-t border-border-default/40 px-4 py-2.5">
            <div className="flex items-center justify-between text-xs text-text-muted">
              <span>Next rotation: Tomorrow 06:00 PST</span>
              <span className="flex items-center gap-1">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 pulse-live" />
                PagerDuty synced
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Sub-components ─────────────────────────────────────────────────

function StatCard({
  label,
  value,
  suffix,
  trend,
  sparkData,
  gradient,
  accentColor,
  iconBg,
  icon: Icon,
}: {
  label: string;
  value: number;
  suffix: string;
  trend: { value: number; label: string; positive: boolean };
  sparkData: number[];
  gradient: string;
  accentColor: string;
  iconBg: string;
  icon: React.ComponentType<{ className?: string }>;
}) {
  return (
    <div
      className={cn(
        "card-interactive relative overflow-hidden bg-gradient-to-br p-4",
        gradient,
      )}
    >
      <div className="flex items-start justify-between">
        <div className={cn("flex h-9 w-9 items-center justify-center rounded-lg", iconBg)}>
          <Icon className={cn("h-4 w-4", accentColor)} />
        </div>
        <span
          className={cn(
            "flex items-center gap-0.5 text-[11px] font-medium",
            trend.positive ? "text-emerald-400" : "text-red-400",
          )}
        >
          {trend.positive ? (
            <ArrowUpRight className="h-3 w-3" />
          ) : (
            <ArrowDownRight className="h-3 w-3" />
          )}
          <span className="truncate max-w-[80px]">{trend.label}</span>
        </span>
      </div>
      <div className="mt-3 flex items-end justify-between">
        <div>
          <p
            className="metric-hero text-3xl font-bold text-text-primary"
          >
            {typeof value === "number" && value % 1 !== 0 ? value.toFixed(1) : formatNumber(value)}
            {suffix && <span className="ml-0.5 text-base font-normal text-text-muted">{suffix}</span>}
          </p>
          <p className="mt-0.5 text-xs text-text-muted">{label}</p>
        </div>
        {/* Mini sparkline */}
        {sparkData.length > 0 && (
          <div className="flex items-end gap-[2px] h-8 opacity-50">
            {sparkData.map((v, i) => {
              const max = Math.max(...sparkData, 1);
              const h = Math.max((v / max) * 100, 4);
              return (
                <div
                  key={i}
                  className={cn("w-1 rounded-t-sm", accentColor.replace("text-", "bg-"))}
                  style={{ height: `${h}%`, opacity: 0.3 + (i / sparkData.length) * 0.7 }}
                />
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function AgentRow({
  type,
  status,
  description,
  duration,
  timestamp,
}: {
  type: string;
  status: "completed" | "running" | "failed";
  description: string;
  duration: string;
  timestamp: string;
}) {
  const statusConfig = {
    completed: { color: "text-emerald-400", bg: "bg-emerald-500/12", borderColor: "border-emerald-500/10", icon: CheckCircle2 },
    running: { color: "text-cyan-400", bg: "bg-cyan-500/12", borderColor: "border-cyan-500/10", icon: RefreshCw },
    failed: { color: "text-red-400", bg: "bg-red-500/12", borderColor: "border-red-500/10", icon: XCircle },
  };
  const config = statusConfig[status];
  const StatusIcon = config.icon;

  return (
    <div className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-navy-800/30">
      <div className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-lg", config.bg)}>
        <StatusIcon className={cn("h-4 w-4", config.color, status === "running" && "animate-spin")} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className={cn("rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase border", "bg-purple-500/10 text-purple-400 border-purple-500/10")}>
            {type}
          </span>
          <p className="truncate text-xs text-text-primary">{description}</p>
        </div>
        <div className="mt-0.5 flex items-center gap-3 text-[10px] text-text-muted">
          <span className="flex items-center gap-1">
            <Clock className="h-3 w-3" />
            {duration}
          </span>
          <span>{timestamp}</span>
        </div>
      </div>
      <span
        className={cn(
          "shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium capitalize border",
          config.bg,
          config.color,
          config.borderColor,
        )}
      >
        {status}
      </span>
    </div>
  );
}

function QuickAction({
  icon: Icon,
  label,
  href,
  color,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  href: string;
  color: string;
}) {
  const colorMap: Record<string, { border: string; bg: string; icon: string; glow: string }> = {
    cyan: { border: "hover:border-cyan-500/25", bg: "hover:bg-cyan-500/5", icon: "text-cyan-400", glow: "group-hover:shadow-[0_0_12px_rgba(6,182,212,0.1)]" },
    blue: { border: "hover:border-blue-500/25", bg: "hover:bg-blue-500/5", icon: "text-blue-400", glow: "group-hover:shadow-[0_0_12px_rgba(59,130,246,0.1)]" },
    purple: { border: "hover:border-purple-500/25", bg: "hover:bg-purple-500/5", icon: "text-purple-400", glow: "group-hover:shadow-[0_0_12px_rgba(168,85,247,0.1)]" },
    yellow: { border: "hover:border-yellow-500/25", bg: "hover:bg-yellow-500/5", icon: "text-yellow-400", glow: "group-hover:shadow-[0_0_12px_rgba(234,179,8,0.1)]" },
  };
  const c = colorMap[color] ?? colorMap.cyan;

  return (
    <Link
      href={href}
      className={cn(
        "group flex flex-col items-center gap-2 rounded-lg border border-border-default/60 bg-navy-800/20 p-3 text-center transition-all duration-200",
        c.border,
        c.bg,
        c.glow,
      )}
    >
      <Icon className={cn("h-5 w-5 transition-transform group-hover:scale-110", c.icon)} />
      <span className="text-xs font-medium text-text-secondary">{label}</span>
    </Link>
  );
}

function SLOCard({
  name,
  target,
  current,
  errorBudgetRemaining,
  burnRate,
}: {
  name: string;
  target: number;
  current: number;
  errorBudgetRemaining: number;
  burnRate: number;
}) {
  const isBreaching = current < target;
  const isBurning = burnRate > 1;
  const budgetColor =
    errorBudgetRemaining > 60
      ? "text-emerald-400"
      : errorBudgetRemaining > 30
        ? "text-amber-400"
        : "text-red-400";
  const budgetBg =
    errorBudgetRemaining > 60
      ? "bg-emerald-500"
      : errorBudgetRemaining > 30
        ? "bg-amber-500"
        : "bg-red-500";

  return (
    <div className="px-4 py-3 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-text-primary truncate">{name}</span>
        {isBurning && (
          <span className="rounded bg-red-500/12 border border-red-500/10 px-1.5 py-0.5 text-[9px] font-semibold text-red-400">
            BURNING {burnRate.toFixed(1)}x
          </span>
        )}
      </div>
      <div className="flex items-end gap-1.5">
        <span
          className={cn(
            "metric-hero text-2xl font-bold",
            isBreaching ? "text-red-400" : "text-text-primary",
          )}
        >
          {current.toFixed(2)}%
        </span>
        <span className="mb-0.5 text-[10px] text-text-muted">
          / {target}% target
        </span>
      </div>
      <div className="space-y-1">
        <div className="flex items-center justify-between text-[10px]">
          <span className="text-text-muted">Error budget</span>
          <span className={cn("font-semibold tabular-nums", budgetColor)}>
            {errorBudgetRemaining}% remaining
          </span>
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-navy-700/60">
          <div
            className={cn("h-full rounded-full transition-all duration-500", budgetBg)}
            style={{ width: `${errorBudgetRemaining}%` }}
          />
        </div>
      </div>
    </div>
  );
}

function DeployRow({
  service,
  version,
  status,
  timestamp,
  author,
}: {
  service: string;
  version: string;
  status: "success" | "failed" | "rollback" | "canary" | "in-progress";
  timestamp: string;
  author: string;
}) {
  const statusConfig = {
    success: { color: "text-emerald-400", bg: "bg-emerald-500/10", border: "border-emerald-500/10", label: "Deployed" },
    failed: { color: "text-red-400", bg: "bg-red-500/10", border: "border-red-500/10", label: "Failed" },
    rollback: { color: "text-amber-400", bg: "bg-amber-500/10", border: "border-amber-500/10", label: "Rolled back" },
    canary: { color: "text-cyan-400", bg: "bg-cyan-500/10", border: "border-cyan-500/10", label: "Canary" },
    "in-progress": { color: "text-blue-400", bg: "bg-blue-500/10", border: "border-blue-500/10", label: "Deploying..." },
  };
  const cfg = statusConfig[status];

  return (
    <div className="flex items-center gap-3 px-4 py-2.5 transition-colors hover:bg-navy-800/30">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-accent-blue">{service}</span>
          <span className="font-mono text-[10px] text-text-muted tabular-nums">{version}</span>
        </div>
        <div className="mt-0.5 flex items-center gap-2 text-[10px] text-text-muted">
          <span>{author}</span>
          <span className="text-text-muted/30">&middot;</span>
          <span>{timestamp}</span>
        </div>
      </div>
      <span className={cn("shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-medium", cfg.bg, cfg.color, cfg.border)}>
        {cfg.label}
      </span>
    </div>
  );
}

function OnCallRow({
  team,
  primary,
  secondary,
  shift,
  active,
}: {
  team: string;
  primary: string;
  secondary: string;
  shift: string;
  active: boolean;
}) {
  return (
    <div className={cn(
      "flex items-center gap-3 px-4 py-2.5 transition-colors hover:bg-navy-800/30",
      active && "bg-emerald-500/[0.03]",
    )}>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-text-primary">{team}</span>
          {active && (
            <span className="flex items-center gap-1 rounded-full bg-emerald-500/10 border border-emerald-500/15 px-1.5 py-0.5 text-[9px] font-semibold text-emerald-400">
              <span className="h-1 w-1 rounded-full bg-emerald-400 pulse-live" />
              Active
            </span>
          )}
        </div>
        <div className="mt-0.5 text-[10px] text-text-muted">
          <span className="text-text-secondary">{primary}</span>
          <span className="mx-1 text-text-muted/30">&middot;</span>
          <span>Backup: {secondary}</span>
        </div>
      </div>
      <span className="shrink-0 text-[10px] text-text-muted font-mono tabular-nums">{shift}</span>
    </div>
  );
}
