"use client";

import React, { useState } from "react";
import { Activity, Globe, Shield as ShieldIcon, Wifi, RefreshCw, Plus, ChevronRight, CheckCircle2, XCircle, AlertTriangle } from "lucide-react";
import { TimeRangePicker } from "@/components/shared/time-range-picker";
import { cn } from "@/lib/utils";
import { ChartWidget } from "@/components/dashboard/chart-widget";

// ── Mock Data ──────────────────────────────────────────────────────────

const mockMonitors = [
  {
    id: "mon-1",
    name: "Production API",
    type: "HTTP",
    target: "https://api.example.com/health",
    status: "up",
    uptime: 99.98,
    avgResponseTime: 145,
    lastCheck: "30s ago",
    locations: ["us-east-1", "eu-west-1", "ap-southeast-1"],
  },
  {
    id: "mon-2",
    name: "Marketing Website",
    type: "HTTP",
    target: "https://www.example.com",
    status: "up",
    uptime: 99.95,
    avgResponseTime: 320,
    lastCheck: "1m ago",
    locations: ["us-east-1", "eu-west-1"],
  },
  {
    id: "mon-3",
    name: "Payment Gateway",
    type: "API",
    target: "https://payments.example.com/v1/status",
    status: "degraded",
    uptime: 99.82,
    avgResponseTime: 890,
    lastCheck: "15s ago",
    locations: ["us-east-1", "us-west-2"],
  },
  {
    id: "mon-4",
    name: "CDN Edge",
    type: "HTTP",
    target: "https://cdn.example.com/probe.js",
    status: "up",
    uptime: 100,
    avgResponseTime: 42,
    lastCheck: "45s ago",
    locations: ["us-east-1", "eu-west-1", "ap-northeast-1", "ap-southeast-1"],
  },
  {
    id: "mon-5",
    name: "Database Primary",
    type: "TCP",
    target: "db-primary.internal:5432",
    status: "up",
    uptime: 99.99,
    avgResponseTime: 12,
    lastCheck: "20s ago",
    locations: ["us-east-1"],
  },
  {
    id: "mon-6",
    name: "SSL Certificate",
    type: "SSL",
    target: "https://api.example.com",
    status: "up",
    uptime: 100,
    avgResponseTime: 85,
    lastCheck: "5m ago",
    locations: ["us-east-1"],
  },
  {
    id: "mon-7",
    name: "Auth Service",
    type: "HTTP",
    target: "https://auth.example.com/healthz",
    status: "down",
    uptime: 98.5,
    avgResponseTime: 0,
    lastCheck: "10s ago",
    locations: ["us-east-1", "eu-west-1"],
  },
  {
    id: "mon-8",
    name: "DNS Resolution",
    type: "DNS",
    target: "example.com",
    status: "up",
    uptime: 100,
    avgResponseTime: 8,
    lastCheck: "2m ago",
    locations: ["us-east-1", "eu-west-1", "ap-northeast-1"],
  },
];

const mockResponseTimeData = [
  { time: "00:00", value: 142 },
  { time: "02:00", value: 138 },
  { time: "04:00", value: 135 },
  { time: "06:00", value: 140 },
  { time: "08:00", value: 165 },
  { time: "10:00", value: 189 },
  { time: "12:00", value: 210 },
  { time: "14:00", value: 195 },
  { time: "16:00", value: 178 },
  { time: "18:00", value: 155 },
  { time: "20:00", value: 148 },
  { time: "22:00", value: 140 },
];

// 24h uptime segments (each segment = 1 hour)
const mockUptimeTimeline = Array.from({ length: 24 }, (_, i) => {
  if (i === 14) return "degraded";
  if (i === 15) return "down";
  return "up";
});

// ── Helper Components ──────────────────────────────────────────────────

function StatusDot({ status }: { status: string }) {
  const colors: Record<string, string> = {
    up: "bg-emerald-400 shadow-emerald-400/50",
    down: "bg-red-400 shadow-red-400/50",
    degraded: "bg-amber-400 shadow-amber-400/50",
  };
  return (
    <span className={cn("inline-block w-2.5 h-2.5 rounded-full shadow-lg", colors[status] || colors.up)} />
  );
}

function StatusIcon({ status }: { status: string }) {
  if (status === "up") return <CheckCircle2 className="h-4 w-4 text-emerald-400" />;
  if (status === "down") return <XCircle className="h-4 w-4 text-red-400" />;
  return <AlertTriangle className="h-4 w-4 text-amber-400" />;
}

function MonitorTypeIcon({ type }: { type: string }) {
  if (type === "HTTP" || type === "API") return <Globe className="h-3.5 w-3.5" />;
  if (type === "TCP") return <Wifi className="h-3.5 w-3.5" />;
  if (type === "SSL") return <ShieldIcon className="h-3.5 w-3.5" />;
  if (type === "DNS") return <Activity className="h-3.5 w-3.5" />;
  return <Globe className="h-3.5 w-3.5" />;
}

function UptimeBadge({ uptime }: { uptime: number }) {
  let color = "text-emerald-400";
  if (uptime < 99.5) color = "text-amber-400";
  if (uptime < 99) color = "text-red-400";
  return <span className={cn("text-sm font-semibold", color)}>{uptime}%</span>;
}

function UptimeTimeline({ segments }: { segments: string[] }) {
  const colors: Record<string, string> = {
    up: "bg-emerald-500",
    down: "bg-red-500",
    degraded: "bg-amber-500",
  };
  return (
    <div className="flex gap-0.5 h-8 rounded overflow-hidden">
      {segments.map((status, i) => (
        <div
          key={i}
          className={cn("flex-1 hover:opacity-80 transition-opacity cursor-default", colors[status] || colors.up)}
          title={`${i}:00 - ${status}`}
        />
      ))}
    </div>
  );
}

// ── Main Page ──────────────────────────────────────────────────────────

export default function SyntheticsPage() {
  const [selectedMonitor, setSelectedMonitor] = useState<string | null>(mockMonitors[0].id);
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");

  const selected = mockMonitors.find((m) => m.id === selectedMonitor);

  const statusCounts = {
    up: mockMonitors.filter((m) => m.status === "up").length,
    degraded: mockMonitors.filter((m) => m.status === "degraded").length,
    down: mockMonitors.filter((m) => m.status === "down").length,
  };

  return (
    <div className="space-y-4">
      {/* ── Header ───────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-text-primary">
            Synthetic Monitoring
          </h1>
          <p className="mt-0.5 text-sm text-text-muted">
            Proactive endpoint monitoring from multiple global locations.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <TimeRangePicker />
          <button className="flex items-center gap-2 rounded-lg bg-cyan-600 px-4 py-2 text-sm font-medium text-text-primary transition-colors hover:bg-cyan-500">
            <Plus className="h-4 w-4" />
            Create Monitor
          </button>
        </div>
      </div>

      {/* Create your first monitor CTA */}
      <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-6">
        <div className="flex items-start gap-4">
          <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-emerald-500/20">
            <Plus className="h-5 w-5 text-emerald-400" />
          </div>
          <div className="flex-1">
            <h3 className="text-sm font-semibold text-emerald-400">Create your first monitor</h3>
            <p className="mt-1 text-xs text-text-muted">
              Set up HTTP, TCP, DNS, or SSL monitors to proactively check your endpoints from multiple global locations.
              The monitor cards below show a preview of what the dashboard will look like.
            </p>
            <div className="mt-3 rounded-lg bg-surface-secondary border border-border-default p-3">
              <p className="text-[10px] text-text-muted mb-1">API Example:</p>
              <code className="text-xs text-emerald-400 font-mono whitespace-pre">{`POST /api/v1/synthetics/monitors
{
  "name": "My API Health Check",
  "type": "HTTP",
  "target": "https://api.example.com/health",
  "interval_seconds": 60,
  "locations": ["us-east-1", "eu-west-1"]
}`}</code>
            </div>
          </div>
        </div>
      </div>

      {/* View mode toggle & controls */}
      <div className="flex items-center justify-between">
        <div />
        <div className="flex items-center gap-3">
          {/* View mode toggle */}
          <div className="flex rounded-lg border border-border-default/60 bg-surface-secondary p-0.5">
            <button
              onClick={() => setViewMode("grid")}
              className={cn(
                "px-3 py-1.5 text-xs rounded-md transition-colors",
                viewMode === "grid"
                  ? "bg-cyan-500/10 text-cyan-400"
                  : "text-text-muted hover:text-text-primary",
              )}
            >
              Grid
            </button>
            <button
              onClick={() => setViewMode("list")}
              className={cn(
                "px-3 py-1.5 text-xs rounded-md transition-colors",
                viewMode === "list"
                  ? "bg-cyan-500/10 text-cyan-400"
                  : "text-text-muted hover:text-text-primary",
              )}
            >
              List
            </button>
          </div>
        </div>
      </div>

      {/* Status summary */}
      <div className="flex gap-4">
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl border border-border-default/60 bg-surface-secondary">
          <StatusDot status="up" />
          <span className="text-sm text-text-secondary">{statusCounts.up} Up</span>
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl border border-border-default/60 bg-surface-secondary">
          <StatusDot status="degraded" />
          <span className="text-sm text-text-secondary">{statusCounts.degraded} Degraded</span>
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl border border-border-default/60 bg-surface-secondary">
          <StatusDot status="down" />
          <span className="text-sm text-text-secondary">{statusCounts.down} Down</span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Monitor Grid/List */}
        <div className={cn(
          "lg:col-span-2",
          viewMode === "grid" ? "grid grid-cols-1 md:grid-cols-2 gap-4" : "space-y-3",
        )}>
          {mockMonitors.map((monitor) => (
            <button
              key={monitor.id}
              onClick={() => setSelectedMonitor(monitor.id)}
              className={cn(
                "w-full text-left bg-surface-secondary border rounded-xl p-4 transition-all hover:border-navy-500",
                selectedMonitor === monitor.id
                  ? "border-cyan-500/30 ring-1 ring-cyan-500/20"
                  : "border-border-default",
              )}
            >
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-2.5">
                  <StatusDot status={monitor.status} />
                  <div>
                    <div className="text-sm font-semibold text-text-primary">{monitor.name}</div>
                    <div className="text-xs text-text-muted">{monitor.type}</div>
                  </div>
                </div>
                <UptimeBadge uptime={monitor.uptime} />
              </div>
              <div className="text-xs text-text-muted font-mono truncate mb-3">{monitor.target}</div>
              <div className="flex items-center justify-between text-xs text-text-muted">
                <span>
                  {monitor.avgResponseTime > 0 ? `${monitor.avgResponseTime}ms` : "N/A"} avg
                </span>
                <span>Last: {monitor.lastCheck}</span>
              </div>
              {viewMode === "grid" && (
                <div className="flex gap-0.5 mt-3">
                  {monitor.locations.map((loc) => (
                    <span
                      key={loc}
                      className="px-1.5 py-0.5 text-[10px] bg-navy-800 text-text-muted rounded"
                    >
                      {loc}
                    </span>
                  ))}
                </div>
              )}
            </button>
          ))}
        </div>

        {/* Detail Panel */}
        <div className="space-y-4">
          {selected ? (
            <>
              {/* Monitor Detail */}
              <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-6">
                <div className="flex items-center gap-3 mb-4">
                  <StatusDot status={selected.status} />
                  <div>
                    <h2 className="text-lg font-semibold text-text-primary">{selected.name}</h2>
                    <p className="text-xs text-text-muted font-mono">{selected.target}</p>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4 mb-6">
                  <div className="rounded-xl bg-navy-950 p-3">
                    <div className="text-xs text-text-muted mb-1">Uptime</div>
                    <UptimeBadge uptime={selected.uptime} />
                  </div>
                  <div className="rounded-xl bg-navy-950 p-3">
                    <div className="text-xs text-text-muted mb-1">Avg Response</div>
                    <span className="text-sm font-semibold text-text-primary">
                      {selected.avgResponseTime > 0 ? `${selected.avgResponseTime}ms` : "N/A"}
                    </span>
                  </div>
                  <div className="rounded-xl bg-navy-950 p-3">
                    <div className="text-xs text-text-muted mb-1">Type</div>
                    <span className="text-sm font-semibold text-text-primary">{selected.type}</span>
                  </div>
                  <div className="rounded-xl bg-navy-950 p-3">
                    <div className="text-xs text-text-muted mb-1">Locations</div>
                    <span className="text-sm font-semibold text-text-primary">{selected.locations.length}</span>
                  </div>
                </div>

                <div className="flex gap-2">
                  <button className="flex-1 flex items-center justify-center gap-2 px-3 py-2 text-xs font-medium rounded-lg bg-cyan-600 text-text-primary transition-colors hover:bg-cyan-500">
                    <RefreshCw className="h-3.5 w-3.5" />
                    Run Now
                  </button>
                  <button className="flex-1 px-3 py-2 text-xs font-medium rounded-lg bg-navy-800 text-text-secondary transition-colors hover:bg-navy-700">
                    Edit
                  </button>
                </div>
              </div>

              {/* Response Time Chart */}
              <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-6">
                <h3 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-4">
                  Response Time (24h)
                </h3>
                <ChartWidget
                  type="bar"
                  xData={mockResponseTimeData.map((d) => d.time)}
                  series={[
                    {
                      name: "Response Time",
                      data: mockResponseTimeData.map((d) => d.value),
                      color: "#06b6d4",
                    },
                  ]}
                  height={160}
                  showLegend={false}
                  yAxisLabel="ms"
                />
              </div>

              {/* Uptime Timeline */}
              <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-6">
                <h3 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-4">
                  Uptime (24h)
                </h3>
                <UptimeTimeline segments={mockUptimeTimeline} />
                <div className="flex justify-between mt-2 text-[10px] text-text-muted">
                  <span>24h ago</span>
                  <span>Now</span>
                </div>
              </div>
            </>
          ) : (
            <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-6 flex items-center justify-center h-64">
              <p className="text-text-muted text-sm">Select a monitor to view details</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
