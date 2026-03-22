"use client";

import { useState } from "react";
import {
  Server,
  Cpu,
  HardDrive,
  MemoryStick,
  Network,
  Container,
  Cloud,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  ChevronRight,
  Activity,
  Thermometer,
  Wifi,
  Box,
  Layers,
  RefreshCw,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { TimeRangePicker } from "@/components/shared/time-range-picker";

// ── Types ──────────────────────────────────────────────────────────

interface Host {
  id: string;
  hostname: string;
  ip: string;
  status: "healthy" | "warning" | "critical" | "unreachable";
  cpu: number;
  memory: number;
  disk: number;
  network_in: number;
  network_out: number;
  os: string;
  uptime: string;
  containers: number;
  region: string;
  provider: "aws" | "gcp" | "azure" | "on-prem";
  tags: string[];
}

interface K8sCluster {
  name: string;
  status: "healthy" | "degraded" | "critical";
  nodes: number;
  pods_running: number;
  pods_pending: number;
  pods_failed: number;
  cpu_usage: number;
  memory_usage: number;
  namespaces: K8sNamespace[];
}

interface K8sNamespace {
  name: string;
  pods: number;
  restarts_1h: number;
  crashloops: number;
  oom_kills: number;
}

// ── Mock Data ──────────────────────────────────────────────────────

const MOCK_HOSTS: Host[] = [
  { id: "h1", hostname: "prod-api-01", ip: "10.0.1.12", status: "healthy", cpu: 42, memory: 68, disk: 55, network_in: 245, network_out: 189, os: "Ubuntu 22.04", uptime: "45d 12h", containers: 8, region: "us-east-1", provider: "aws", tags: ["api", "production"] },
  { id: "h2", hostname: "prod-api-02", ip: "10.0.1.13", status: "healthy", cpu: 38, memory: 72, disk: 52, network_in: 198, network_out: 165, os: "Ubuntu 22.04", uptime: "45d 12h", containers: 8, region: "us-east-1", provider: "aws", tags: ["api", "production"] },
  { id: "h3", hostname: "prod-worker-01", ip: "10.0.2.20", status: "warning", cpu: 87, memory: 91, disk: 78, network_in: 412, network_out: 356, os: "Ubuntu 22.04", uptime: "23d 8h", containers: 12, region: "us-east-1", provider: "aws", tags: ["worker", "production"] },
  { id: "h4", hostname: "prod-db-primary", ip: "10.0.3.5", status: "healthy", cpu: 55, memory: 82, disk: 67, network_in: 890, network_out: 1240, os: "Ubuntu 22.04", uptime: "90d 3h", containers: 3, region: "us-east-1", provider: "aws", tags: ["database", "production", "primary"] },
  { id: "h5", hostname: "prod-db-replica", ip: "10.0.3.6", status: "healthy", cpu: 32, memory: 65, disk: 64, network_in: 445, network_out: 120, os: "Ubuntu 22.04", uptime: "90d 3h", containers: 3, region: "us-east-1", provider: "aws", tags: ["database", "production", "replica"] },
  { id: "h6", hostname: "prod-cache-01", ip: "10.0.4.10", status: "healthy", cpu: 18, memory: 45, disk: 22, network_in: 567, network_out: 534, os: "Alpine 3.18", uptime: "60d 1h", containers: 2, region: "us-east-1", provider: "aws", tags: ["cache", "redis", "production"] },
  { id: "h7", hostname: "prod-nats-01", ip: "10.0.4.15", status: "healthy", cpu: 24, memory: 38, disk: 15, network_in: 1890, network_out: 1756, os: "Alpine 3.18", uptime: "60d 1h", containers: 1, region: "us-east-1", provider: "aws", tags: ["nats", "messaging", "production"] },
  { id: "h8", hostname: "prod-worker-02", ip: "10.0.2.21", status: "critical", cpu: 98, memory: 96, disk: 92, network_in: 45, network_out: 12, os: "Ubuntu 22.04", uptime: "2d 4h", containers: 12, region: "us-west-2", provider: "aws", tags: ["worker", "production"] },
  { id: "h9", hostname: "staging-api-01", ip: "10.1.1.10", status: "healthy", cpu: 12, memory: 35, disk: 28, network_in: 34, network_out: 28, os: "Ubuntu 22.04", uptime: "14d 6h", containers: 8, region: "us-west-2", provider: "aws", tags: ["api", "staging"] },
  { id: "h10", hostname: "prod-ingestion-01", ip: "10.0.5.8", status: "warning", cpu: 76, memory: 84, disk: 45, network_in: 2340, network_out: 890, os: "Ubuntu 22.04", uptime: "30d 2h", containers: 6, region: "us-east-1", provider: "aws", tags: ["ingestion", "production"] },
];

const MOCK_K8S: K8sCluster = {
  name: "prod-us-east-1",
  status: "degraded",
  nodes: 12,
  pods_running: 156,
  pods_pending: 3,
  pods_failed: 2,
  cpu_usage: 64,
  memory_usage: 72,
  namespaces: [
    { name: "rayolly-api", pods: 24, restarts_1h: 0, crashloops: 0, oom_kills: 0 },
    { name: "rayolly-workers", pods: 36, restarts_1h: 5, crashloops: 1, oom_kills: 2 },
    { name: "rayolly-ingestion", pods: 18, restarts_1h: 2, crashloops: 0, oom_kills: 1 },
    { name: "rayolly-agents", pods: 12, restarts_1h: 0, crashloops: 0, oom_kills: 0 },
    { name: "monitoring", pods: 8, restarts_1h: 0, crashloops: 0, oom_kills: 0 },
    { name: "cert-manager", pods: 3, restarts_1h: 0, crashloops: 0, oom_kills: 0 },
    { name: "kube-system", pods: 42, restarts_1h: 0, crashloops: 0, oom_kills: 0 },
    { name: "istio-system", pods: 13, restarts_1h: 1, crashloops: 1, oom_kills: 0 },
  ],
};

// ── Component ──────────────────────────────────────────────────────

type Tab = "hosts" | "kubernetes" | "containers" | "cloud";

export default function InfrastructurePage() {
  const [activeTab, setActiveTab] = useState<Tab>("hosts");
  const [selectedHost, setSelectedHost] = useState<string | null>(null);
  const [hostFilter, setHostFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<string | null>(null);

  const tabs: { id: Tab; label: string; icon: any; count?: number }[] = [
    { id: "hosts", label: "Host Map", icon: Server, count: MOCK_HOSTS.length },
    { id: "kubernetes", label: "Kubernetes", icon: Box, count: MOCK_K8S.nodes },
    { id: "containers", label: "Containers", icon: Container, count: MOCK_HOSTS.reduce((a, h) => a + h.containers, 0) },
    { id: "cloud", label: "Cloud", icon: Cloud },
  ];

  const filteredHosts = MOCK_HOSTS.filter((h) => {
    if (hostFilter && !h.hostname.toLowerCase().includes(hostFilter.toLowerCase()) && !h.ip.includes(hostFilter)) return false;
    if (statusFilter && h.status !== statusFilter) return false;
    return true;
  });

  const statusCounts = MOCK_HOSTS.reduce<Record<string, number>>((acc, h) => {
    acc[h.status] = (acc[h.status] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="space-y-4">
      {/* ── Header ───────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-text-primary">Infrastructure</h1>
          <p className="mt-0.5 text-sm text-text-muted">
            <span className="text-cyan-400 font-medium">{MOCK_HOSTS.length} hosts</span>
            {" \u00B7 "}
            <span className="text-text-secondary">{MOCK_K8S.nodes} K8s nodes</span>
            {" \u00B7 "}
            <span className="text-text-secondary">{MOCK_HOSTS.reduce((a, h) => a + h.containers, 0)} containers</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button className="flex items-center gap-1.5 rounded-lg border border-border-default/60 bg-surface-secondary px-3 py-1.5 text-sm text-text-secondary transition-colors hover:border-navy-500 hover:text-text-primary">
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
          <TimeRangePicker />
        </div>
      </div>

      {/* ── Tabs ─────────────────────────────────────────────────── */}
      <div className="flex items-center gap-1 rounded-lg border border-border-default bg-surface-primary p-1">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              "flex items-center gap-2 rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
              activeTab === tab.id
                ? "bg-cyan-500/10 text-cyan-400"
                : "text-text-muted hover:text-text-secondary hover:bg-navy-800/40",
            )}
          >
            <tab.icon className="h-3.5 w-3.5" />
            {tab.label}
            {tab.count !== undefined && (
              <span className={cn(
                "rounded-full px-1.5 py-0.5 text-[10px] font-semibold",
                activeTab === tab.id ? "bg-cyan-500/15 text-cyan-400" : "bg-navy-700 text-text-muted",
              )}>
                {tab.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* ── Tab Content ──────────────────────────────────────────── */}
      {activeTab === "hosts" && (
        <div className="space-y-4">
          {/* Summary Row */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <SummaryCard label="Healthy" value={statusCounts["healthy"] ?? 0} color="emerald" />
            <SummaryCard label="Warning" value={statusCounts["warning"] ?? 0} color="amber" />
            <SummaryCard label="Critical" value={statusCounts["critical"] ?? 0} color="red" />
            <SummaryCard label="Unreachable" value={statusCounts["unreachable"] ?? 0} color="slate" />
          </div>

          {/* Host Map Grid (heatmap-style) */}
          <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-4">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-medium text-text-secondary">Host Map</h3>
              <div className="flex items-center gap-2">
                <div className="flex items-center gap-1.5 text-[10px] text-text-muted">
                  <span className="h-3 w-3 rounded bg-emerald-500/40" /> Low
                  <span className="h-3 w-3 rounded bg-amber-500/40" /> Med
                  <span className="h-3 w-3 rounded bg-red-500/40" /> High
                </div>
              </div>
            </div>

            {/* Heat map tiles */}
            <div className="grid grid-cols-5 sm:grid-cols-8 xl:grid-cols-10 gap-2">
              {MOCK_HOSTS.map((host) => {
                const cpuColor = host.cpu > 85 ? "border-red-500/50 bg-red-500/10" : host.cpu > 60 ? "border-amber-500/50 bg-amber-500/10" : "border-emerald-500/30 bg-emerald-500/5";
                const selected = selectedHost === host.id;

                return (
                  <button
                    key={host.id}
                    onClick={() => setSelectedHost(selected ? null : host.id)}
                    className={cn(
                      "relative flex flex-col items-center justify-center rounded-lg border p-3 transition-all duration-150",
                      cpuColor,
                      selected && "ring-2 ring-cyan-500/50 border-cyan-500/30",
                      "hover:scale-105 hover:shadow-lg",
                    )}
                    title={`${host.hostname} - CPU: ${host.cpu}% MEM: ${host.memory}%`}
                  >
                    <Server className={cn(
                      "h-5 w-5 mb-1",
                      host.status === "critical" ? "text-red-400" : host.status === "warning" ? "text-amber-400" : "text-emerald-400",
                    )} />
                    <span className="text-[9px] font-medium text-text-primary truncate w-full text-center">
                      {host.hostname.replace("prod-", "").replace("staging-", "s:")}
                    </span>
                    <span className="text-[8px] text-text-muted font-mono mt-0.5" style={{ fontFeatureSettings: '"tnum"' }}>
                      {host.cpu}%
                    </span>
                    {/* Status dot */}
                    <span className={cn(
                      "absolute right-1 top-1 h-1.5 w-1.5 rounded-full",
                      host.status === "healthy" ? "bg-emerald-400" : host.status === "warning" ? "bg-amber-400" : host.status === "critical" ? "bg-red-400 pulse-critical" : "bg-slate-400",
                    )} />
                  </button>
                );
              })}
            </div>
          </div>

          {/* Host Detail Panel */}
          {selectedHost && (() => {
            const host = MOCK_HOSTS.find((h) => h.id === selectedHost);
            if (!host) return null;
            return (
              <div className="rounded-xl border border-cyan-500/20 bg-surface-secondary p-4 slide-up">
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-base font-semibold text-text-primary">{host.hostname}</h3>
                      <span className={cn(
                        "rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase",
                        host.status === "healthy" ? "bg-emerald-500/15 text-emerald-400" : host.status === "warning" ? "bg-amber-500/15 text-amber-400" : "bg-red-500/15 text-red-400",
                      )}>
                        {host.status}
                      </span>
                    </div>
                    <p className="mt-0.5 text-xs text-text-muted">{host.ip} &middot; {host.os} &middot; up {host.uptime} &middot; {host.region}</p>
                  </div>
                  <button onClick={() => setSelectedHost(null)} className="text-text-muted hover:text-text-primary">
                    <XCircle className="h-4 w-4" />
                  </button>
                </div>

                <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
                  <ResourceGauge label="CPU" value={host.cpu} icon={<Cpu className="h-4 w-4" />} />
                  <ResourceGauge label="Memory" value={host.memory} icon={<MemoryStick className="h-4 w-4" />} />
                  <ResourceGauge label="Disk" value={host.disk} icon={<HardDrive className="h-4 w-4" />} />
                  <div className="rounded-lg border border-border-default bg-navy-800/30 p-3">
                    <div className="flex items-center gap-2 text-xs text-text-muted mb-2">
                      <Network className="h-4 w-4" />
                      Network
                    </div>
                    <div className="space-y-1">
                      <div className="flex justify-between text-xs">
                        <span className="text-text-muted">In</span>
                        <span className="font-mono text-emerald-400" style={{ fontFeatureSettings: '"tnum"' }}>{host.network_in} Mbps</span>
                      </div>
                      <div className="flex justify-between text-xs">
                        <span className="text-text-muted">Out</span>
                        <span className="font-mono text-cyan-400" style={{ fontFeatureSettings: '"tnum"' }}>{host.network_out} Mbps</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="mt-3 flex flex-wrap gap-1.5">
                  {host.tags.map((tag) => (
                    <span key={tag} className="rounded-md bg-navy-700 px-2 py-0.5 text-[10px] font-medium text-text-secondary">
                      {tag}
                    </span>
                  ))}
                  <span className="rounded-md bg-navy-700 px-2 py-0.5 text-[10px] font-medium text-text-muted">
                    {host.containers} containers
                  </span>
                  <span className="rounded-md bg-navy-700 px-2 py-0.5 text-[10px] font-medium text-text-muted">
                    {host.provider}
                  </span>
                </div>
              </div>
            );
          })()}

          {/* Host Table */}
          <div className="rounded-xl border border-border-default/60 bg-surface-secondary overflow-hidden">
            <div className="flex items-center justify-between border-b border-border-default px-4 py-3">
              <h3 className="text-sm font-medium text-text-secondary">All Hosts</h3>
              <div className="flex items-center gap-2">
                {/* Status filter chips */}
                {["healthy", "warning", "critical"].map((status) => (
                  <button
                    key={status}
                    onClick={() => setStatusFilter(statusFilter === status ? null : status)}
                    className={cn(
                      "rounded-full px-2 py-0.5 text-[10px] font-medium transition-colors border",
                      statusFilter === status
                        ? status === "healthy" ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/20" : status === "warning" ? "bg-amber-500/15 text-amber-400 border-amber-500/20" : "bg-red-500/15 text-red-400 border-red-500/20"
                        : "border-border-default text-text-muted hover:text-text-secondary",
                    )}
                  >
                    {status}
                  </button>
                ))}
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border-default text-[10px] font-medium uppercase tracking-wider text-text-muted">
                    <th className="px-4 py-2.5 text-left">Host</th>
                    <th className="px-4 py-2.5 text-left">Status</th>
                    <th className="px-4 py-2.5 text-right">CPU</th>
                    <th className="px-4 py-2.5 text-right">Memory</th>
                    <th className="px-4 py-2.5 text-right">Disk</th>
                    <th className="px-4 py-2.5 text-right">Network I/O</th>
                    <th className="px-4 py-2.5 text-right">Containers</th>
                    <th className="px-4 py-2.5 text-left">Region</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredHosts.map((host) => (
                    <tr
                      key={host.id}
                      onClick={() => setSelectedHost(selectedHost === host.id ? null : host.id)}
                      className={cn(
                        "border-b border-border-subtle last:border-b-0 transition-colors cursor-pointer",
                        selectedHost === host.id ? "bg-cyan-500/5" : "hover:bg-navy-800/40",
                      )}
                    >
                      <td className="px-4 py-2.5">
                        <div>
                          <span className="text-xs font-medium text-accent-blue">{host.hostname}</span>
                          <p className="text-[10px] text-text-muted font-mono">{host.ip}</p>
                        </div>
                      </td>
                      <td className="px-4 py-2.5">
                        <span className={cn(
                          "inline-flex items-center gap-1.5 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase",
                          host.status === "healthy" ? "bg-emerald-500/15 text-emerald-400" : host.status === "warning" ? "bg-amber-500/15 text-amber-400" : "bg-red-500/15 text-red-400",
                        )}>
                          <span className={cn(
                            "h-1.5 w-1.5 rounded-full",
                            host.status === "healthy" ? "bg-emerald-400" : host.status === "warning" ? "bg-amber-400" : "bg-red-400",
                          )} />
                          {host.status}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        <ResourceMini value={host.cpu} />
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        <ResourceMini value={host.memory} />
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        <ResourceMini value={host.disk} />
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        <span className="font-mono text-[10px] text-text-muted" style={{ fontFeatureSettings: '"tnum"' }}>
                          {host.network_in}/{host.network_out}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        <span className="font-mono text-xs text-text-primary" style={{ fontFeatureSettings: '"tnum"' }}>{host.containers}</span>
                      </td>
                      <td className="px-4 py-2.5">
                        <span className="text-[10px] text-text-muted">{host.region}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {activeTab === "kubernetes" && (
        <div className="space-y-4">
          {/* Cluster Overview */}
          <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-4">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className={cn(
                  "flex h-10 w-10 items-center justify-center rounded-lg",
                  MOCK_K8S.status === "healthy" ? "bg-emerald-500/15" : MOCK_K8S.status === "degraded" ? "bg-amber-500/15" : "bg-red-500/15",
                )}>
                  <Box className={cn(
                    "h-5 w-5",
                    MOCK_K8S.status === "healthy" ? "text-emerald-400" : MOCK_K8S.status === "degraded" ? "text-amber-400" : "text-red-400",
                  )} />
                </div>
                <div>
                  <h3 className="text-base font-semibold text-text-primary">{MOCK_K8S.name}</h3>
                  <span className={cn(
                    "text-xs font-medium",
                    MOCK_K8S.status === "healthy" ? "text-emerald-400" : MOCK_K8S.status === "degraded" ? "text-amber-400" : "text-red-400",
                  )}>
                    {MOCK_K8S.status === "healthy" ? "Cluster Healthy" : MOCK_K8S.status === "degraded" ? "Cluster Degraded" : "Cluster Critical"}
                  </span>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 xl:grid-cols-6 gap-3">
              <MiniMetric label="Nodes" value={MOCK_K8S.nodes} />
              <MiniMetric label="Running Pods" value={MOCK_K8S.pods_running} color="emerald" />
              <MiniMetric label="Pending Pods" value={MOCK_K8S.pods_pending} color={MOCK_K8S.pods_pending > 0 ? "amber" : undefined} />
              <MiniMetric label="Failed Pods" value={MOCK_K8S.pods_failed} color={MOCK_K8S.pods_failed > 0 ? "red" : undefined} />
              <MiniMetric label="CPU Usage" value={`${MOCK_K8S.cpu_usage}%`} color={MOCK_K8S.cpu_usage > 80 ? "red" : MOCK_K8S.cpu_usage > 60 ? "amber" : undefined} />
              <MiniMetric label="Memory Usage" value={`${MOCK_K8S.memory_usage}%`} color={MOCK_K8S.memory_usage > 80 ? "red" : MOCK_K8S.memory_usage > 60 ? "amber" : undefined} />
            </div>
          </div>

          {/* Namespace Table */}
          <div className="rounded-xl border border-border-default/60 bg-surface-secondary overflow-hidden">
            <div className="border-b border-border-default px-4 py-3">
              <h3 className="text-sm font-medium text-text-secondary">Namespaces</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border-default text-[10px] font-medium uppercase tracking-wider text-text-muted">
                    <th className="px-4 py-2.5 text-left">Namespace</th>
                    <th className="px-4 py-2.5 text-right">Pods</th>
                    <th className="px-4 py-2.5 text-right">Restarts (1h)</th>
                    <th className="px-4 py-2.5 text-right">CrashLoopBackOff</th>
                    <th className="px-4 py-2.5 text-right">OOMKilled</th>
                    <th className="px-4 py-2.5 text-left">Health</th>
                  </tr>
                </thead>
                <tbody>
                  {MOCK_K8S.namespaces.map((ns) => {
                    const hasIssues = ns.crashloops > 0 || ns.oom_kills > 0;
                    return (
                      <tr key={ns.name} className="border-b border-border-subtle last:border-b-0 transition-colors hover:bg-navy-800/40">
                        <td className="px-4 py-2.5">
                          <span className="text-xs font-medium text-accent-blue font-mono">{ns.name}</span>
                        </td>
                        <td className="px-4 py-2.5 text-right">
                          <span className="font-mono text-xs text-text-primary" style={{ fontFeatureSettings: '"tnum"' }}>{ns.pods}</span>
                        </td>
                        <td className="px-4 py-2.5 text-right">
                          <span className={cn(
                            "font-mono text-xs",
                            ns.restarts_1h > 0 ? "text-amber-400" : "text-text-muted",
                          )} style={{ fontFeatureSettings: '"tnum"' }}>
                            {ns.restarts_1h}
                          </span>
                        </td>
                        <td className="px-4 py-2.5 text-right">
                          {ns.crashloops > 0 ? (
                            <span className="inline-flex items-center gap-1 rounded bg-red-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-red-400">
                              <AlertTriangle className="h-3 w-3" />
                              {ns.crashloops}
                            </span>
                          ) : (
                            <span className="font-mono text-xs text-text-muted" style={{ fontFeatureSettings: '"tnum"' }}>0</span>
                          )}
                        </td>
                        <td className="px-4 py-2.5 text-right">
                          {ns.oom_kills > 0 ? (
                            <span className="inline-flex items-center gap-1 rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-amber-400">
                              {ns.oom_kills}
                            </span>
                          ) : (
                            <span className="font-mono text-xs text-text-muted" style={{ fontFeatureSettings: '"tnum"' }}>0</span>
                          )}
                        </td>
                        <td className="px-4 py-2.5">
                          <span className={cn(
                            "inline-block h-2 w-2 rounded-full",
                            hasIssues ? "bg-amber-400" : "bg-emerald-400",
                          )} />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {activeTab === "containers" && (
        <div className="flex flex-col items-center justify-center py-20 rounded-xl border border-border-default/60 bg-surface-secondary">
          <Container className="h-12 w-12 text-text-muted/30 mb-4" />
          <p className="text-sm font-medium text-text-muted">Container View</p>
          <p className="mt-1 text-xs text-text-muted/70">Docker container inventory and resource monitoring coming soon</p>
        </div>
      )}

      {activeTab === "cloud" && (
        <div className="flex flex-col items-center justify-center py-20 rounded-xl border border-border-default/60 bg-surface-secondary">
          <Cloud className="h-12 w-12 text-text-muted/30 mb-4" />
          <p className="text-sm font-medium text-text-muted">Cloud Resources</p>
          <p className="mt-1 text-xs text-text-muted/70">AWS, GCP, Azure resource inventory and cost monitoring coming soon</p>
        </div>
      )}
    </div>
  );
}

// ── Sub-components ─────────────────────────────────────────────────

function SummaryCard({ label, value, color }: { label: string; value: number; color: string }) {
  const colorMap: Record<string, { bg: string; text: string; border: string }> = {
    emerald: { bg: "bg-emerald-500/10", text: "text-emerald-400", border: "border-emerald-500/20" },
    amber: { bg: "bg-amber-500/10", text: "text-amber-400", border: "border-amber-500/20" },
    red: { bg: "bg-red-500/10", text: "text-red-400", border: "border-red-500/20" },
    slate: { bg: "bg-slate-500/10", text: "text-slate-400", border: "border-slate-500/20" },
  };
  const c = colorMap[color] ?? colorMap.slate;

  return (
    <div className={cn("rounded-lg border p-3", c.bg, c.border)}>
      <p className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">{label}</p>
      <p className={cn("mt-1 text-2xl font-bold", c.text)} style={{ fontFeatureSettings: '"tnum"' }}>{value}</p>
    </div>
  );
}

function ResourceGauge({ label, value, icon }: { label: string; value: number; icon: React.ReactNode }) {
  const color = value > 85 ? "red" : value > 60 ? "amber" : "emerald";
  const colorMap: Record<string, { bar: string; text: string }> = {
    emerald: { bar: "bg-emerald-500", text: "text-emerald-400" },
    amber: { bar: "bg-amber-500", text: "text-amber-400" },
    red: { bar: "bg-red-500", text: "text-red-400" },
  };
  const c = colorMap[color];

  return (
    <div className="rounded-lg border border-border-default bg-navy-800/30 p-3">
      <div className="flex items-center justify-between text-xs text-text-muted mb-2">
        <div className="flex items-center gap-2">
          {icon}
          {label}
        </div>
        <span className={cn("font-bold text-sm", c.text)} style={{ fontFeatureSettings: '"tnum"' }}>{value}%</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-navy-700">
        <div className={cn("h-full rounded-full transition-all duration-500", c.bar)} style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}

function ResourceMini({ value }: { value: number }) {
  const color = value > 85 ? "text-red-400" : value > 60 ? "text-amber-400" : "text-emerald-400";
  return (
    <div className="flex items-center justify-end gap-2">
      <div className="h-1 w-12 overflow-hidden rounded-full bg-navy-700">
        <div
          className={cn(
            "h-full rounded-full",
            value > 85 ? "bg-red-500" : value > 60 ? "bg-amber-500" : "bg-emerald-500",
          )}
          style={{ width: `${value}%` }}
        />
      </div>
      <span className={cn("font-mono text-xs w-8 text-right", color)} style={{ fontFeatureSettings: '"tnum"' }}>
        {value}%
      </span>
    </div>
  );
}

function MiniMetric({ label, value, color }: { label: string; value: string | number; color?: string }) {
  const textColor = color === "emerald" ? "text-emerald-400" : color === "amber" ? "text-amber-400" : color === "red" ? "text-red-400" : "text-text-primary";
  return (
    <div className="rounded-lg border border-border-default bg-navy-800/30 px-3 py-2.5">
      <p className="text-[10px] font-medium uppercase tracking-wider text-text-muted">{label}</p>
      <p className={cn("mt-1 text-xl font-bold", textColor)} style={{ fontFeatureSettings: '"tnum"' }}>{value}</p>
    </div>
  );
}
