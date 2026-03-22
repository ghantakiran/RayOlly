"use client";

import React, { useState, useEffect, useMemo, useCallback } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  ChevronDown,
  ChevronUp,
  Clock,
  ExternalLink,
  Layers,
  Network,
  Server,
  X,
  Zap,
} from "lucide-react";
import { cn, formatDuration } from "@/lib/utils";
import { TimeRangePicker } from "@/components/shared/time-range-picker";
import { CardSkeleton, TableSkeleton } from "@/components/shared/loading-skeleton";
import { getAPMServices, getServiceMap, getServiceEndpoints, getServiceErrors } from "@/lib/api";

// ── Types ───────────────────────────────────────────────────────────

interface ServiceData {
  service: string;
  request_count: number;
  error_count: number;
  error_rate: number;
  avg_duration_ms: number;
  p99_duration_ms: number;
  status: string;
}

interface MapNode {
  id: string;
  service: string;
  type: string;
  health: string;
  metrics: { request_count: number; error_rate: number; avg_ms: number; p99_ms: number };
}

interface MapEdge {
  source: string;
  target: string;
  request_count: number;
  error_rate: number;
  avg_latency_ms: number;
}

interface EndpointData {
  operation: string;
  request_count: number;
  error_count: number;
  avg_ms: number;
  p50_ms: number;
  p99_ms: number;
}

interface ErrorData {
  message: string;
  count: number;
  first_seen: string;
  last_seen: string;
  sample_trace_id: string;
}

// ── Helpers ─────────────────────────────────────────────────────────

const HEALTH_BORDER: Record<string, string> = {
  healthy: "border-l-severity-ok",
  warning: "border-l-severity-warning",
  critical: "border-l-severity-critical",
};

const HEALTH_DOT: Record<string, string> = {
  healthy: "bg-severity-ok",
  warning: "bg-severity-warning",
  critical: "bg-severity-critical",
};

const HEALTH_TEXT: Record<string, string> = {
  healthy: "text-severity-ok",
  warning: "text-severity-warning",
  critical: "text-severity-critical",
};

function formatRate(count: number): string {
  if (count >= 1_000_000) return `${(count / 1_000_000).toFixed(1)}M`;
  if (count >= 1_000) return `${(count / 1_000).toFixed(1)}k`;
  return `${count}`;
}

function formatLatency(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`;
  return `${ms.toFixed(1)}ms`;
}

function formatPercent(pct: number): string {
  return `${pct.toFixed(2)}%`;
}

function latencyColor(ms: number) {
  if (ms > 1000) return "text-severity-critical";
  if (ms > 500) return "text-severity-warning";
  return "text-text-primary";
}

// ── Loading skeletons ───────────────────────────────────────────────

function ServiceCardsSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {Array.from({ length: 6 }).map((_, i) => (
        <CardSkeleton key={i} />
      ))}
    </div>
  );
}

function ServiceMapSkeleton() {
  return (
    <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-6">
      <div className="skeleton mb-4 h-4 w-40 rounded" />
      <div className="flex items-center justify-center gap-8 py-12">
        {Array.from({ length: 4 }).map((_, i) => (
          <React.Fragment key={i}>
            <div className="skeleton h-16 w-16 rounded-full" />
            {i < 3 && <div className="skeleton h-0.5 w-12 rounded" />}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
}

// ── Service Map (CSS Flow Diagram) ──────────────────────────────────

function ServiceMapFlow({
  nodes,
  edges,
  selectedService,
  onSelect,
}: {
  nodes: MapNode[];
  edges: MapEdge[];
  selectedService: string | null;
  onSelect: (name: string) => void;
}) {
  if (nodes.length === 0) {
    return (
      <div className="flex flex-col items-center py-12 text-center">
        <Network className="mb-2 h-8 w-8 text-text-muted" />
        <p className="text-sm text-text-muted">No service topology data available</p>
        <p className="mt-1 text-xs text-text-muted">Services will appear once traces are ingested</p>
      </div>
    );
  }

  // Build adjacency for layout: find roots (no incoming) and group by depth
  const incoming = new Set(edges.map((e) => e.target));
  const roots = nodes.filter((n) => !incoming.has(n.service));
  const nonRoots = nodes.filter((n) => incoming.has(n.service));

  // Simple layout: roots first, then the rest
  const orderedNodes = [...roots, ...nonRoots.filter((n) => !roots.includes(n))];

  return (
    <div className="overflow-x-auto pb-2">
      <div className="flex flex-wrap items-center justify-center gap-4 py-4">
        {orderedNodes.map((node, idx) => {
          const isSelected = selectedService === node.service;
          const outgoing = edges.filter((e) => e.source === node.service);
          const healthDot = HEALTH_DOT[node.health] || "bg-text-muted";
          const healthBorder = node.health === "critical"
            ? "border-severity-critical"
            : node.health === "warning"
              ? "border-severity-warning"
              : "border-border-default";

          return (
            <React.Fragment key={node.service}>
              <button
                onClick={() => onSelect(node.service)}
                className={cn(
                  "relative flex flex-col items-center rounded-xl border-2 bg-surface-secondary px-5 py-4 transition-all duration-150",
                  isSelected
                    ? "border-cyan-500 bg-cyan-500/5 shadow-lg shadow-cyan-500/10"
                    : `${healthBorder} hover:border-navy-500 hover:bg-navy-800/40`,
                )}
              >
                {/* Health dot */}
                <span
                  className={cn(
                    "absolute -right-1 -top-1 h-3 w-3 rounded-full border-2 border-surface-primary",
                    healthDot,
                  )}
                />

                {/* Icon */}
                <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-lg bg-navy-800">
                  {node.type === "database" ? (
                    <Layers className="h-5 w-5 text-accent-indigo" />
                  ) : node.type === "gateway" ? (
                    <Zap className="h-5 w-5 text-cyan-400" />
                  ) : (
                    <Server className="h-5 w-5 text-accent-blue" />
                  )}
                </div>

                {/* Name */}
                <p className="max-w-[100px] truncate text-xs font-medium text-text-primary">
                  {node.service}
                </p>

                {/* Metrics */}
                <p className="mt-1 tabular-nums text-[10px] text-text-muted">
                  {formatRate(node.metrics.request_count)} req/s
                </p>
                {node.metrics.error_rate > 0 && (
                  <p className="tabular-nums text-[10px] text-severity-critical">
                    {node.metrics.error_rate.toFixed(1)}% err
                  </p>
                )}
              </button>

              {/* Arrow connector */}
              {outgoing.length > 0 && idx < orderedNodes.length - 1 && (
                <div className="hidden items-center sm:flex">
                  <div className="h-px w-6 bg-navy-600" />
                  <ArrowRight className="h-3.5 w-3.5 text-navy-500" />
                  <div className="h-px w-6 bg-navy-600" />
                </div>
              )}
            </React.Fragment>
          );
        })}
      </div>

      {/* Legend */}
      <div className="flex items-center justify-center gap-6 border-t border-border-default pt-3 text-[10px] text-text-muted">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2 w-2 rounded-full bg-severity-ok" />
          Healthy
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2 w-2 rounded-full bg-severity-warning" />
          Warning
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2 w-2 rounded-full bg-severity-critical" />
          Critical
        </span>
        <span className="flex items-center gap-1.5">
          <ArrowRight className="h-3 w-3 text-navy-500" />
          Dependency
        </span>
      </div>
    </div>
  );
}

// ── Service Detail Panel ────────────────────────────────────────────

function ServiceDetailPanel({
  service,
  onClose,
}: {
  service: ServiceData;
  onClose: () => void;
}) {
  const [endpoints, setEndpoints] = useState<EndpointData[]>([]);
  const [errors, setErrors] = useState<ErrorData[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    Promise.all([
      getServiceEndpoints(service.service),
      getServiceErrors(service.service),
    ])
      .then(([epRes, errRes]) => {
        if (cancelled) return;
        setEndpoints(epRes?.endpoints || []);
        setErrors(errRes?.errors || []);
        setLoading(false);
      })
      .catch(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [service.service]);

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      {/* Endpoints table */}
      <div className="rounded-xl border border-border-default/60 bg-surface-secondary">
        <div className="flex items-center justify-between border-b border-border-default px-4 py-3">
          <h3 className="flex items-center gap-2 text-sm font-medium text-text-secondary">
            <Activity className="h-4 w-4 text-cyan-400" />
            Endpoints
          </h3>
          <span className="text-[10px] text-text-muted">
            {endpoints.length} endpoint{endpoints.length !== 1 ? "s" : ""}
          </span>
        </div>

        {loading ? (
          <div className="p-4">
            <TableSkeleton rows={4} columns={5} />
          </div>
        ) : endpoints.length === 0 ? (
          <div className="flex flex-col items-center py-8 text-center">
            <Activity className="mb-2 h-5 w-5 text-text-muted" />
            <p className="text-xs text-text-muted">No endpoint data</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border-default text-left text-[10px] font-medium uppercase tracking-wider text-text-muted">
                  <th className="px-4 py-2">Operation</th>
                  <th className="px-4 py-2 text-right">Reqs</th>
                  <th className="px-4 py-2 text-right">Errors</th>
                  <th className="px-4 py-2 text-right">Avg</th>
                  <th className="px-4 py-2 text-right">P99</th>
                </tr>
              </thead>
              <tbody>
                {endpoints.map((ep) => (
                  <tr
                    key={ep.operation}
                    className="border-b border-border-subtle transition-colors duration-150 hover:bg-navy-800/40"
                  >
                    <td className="px-4 py-2.5 font-mono text-text-primary">
                      {ep.operation}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums text-text-secondary">
                      {formatRate(ep.request_count)}
                    </td>
                    <td
                      className={cn(
                        "px-4 py-2.5 text-right tabular-nums",
                        ep.error_count > 0 ? "text-severity-critical" : "text-text-secondary",
                      )}
                    >
                      {ep.error_count}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums text-text-secondary">
                      {formatLatency(ep.avg_ms)}
                    </td>
                    <td className={cn("px-4 py-2.5 text-right tabular-nums font-semibold", latencyColor(ep.p99_ms))}>
                      {formatLatency(ep.p99_ms)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Error groups */}
      <div className="rounded-xl border border-border-default/60 bg-surface-secondary">
        <div className="flex items-center justify-between border-b border-border-default px-4 py-3">
          <h3 className="flex items-center gap-2 text-sm font-medium text-text-secondary">
            <AlertTriangle className="h-4 w-4 text-severity-critical" />
            Error Groups
          </h3>
          <span className="text-[10px] text-text-muted">
            {errors.length} group{errors.length !== 1 ? "s" : ""}
          </span>
        </div>

        {loading ? (
          <div className="p-4">
            <TableSkeleton rows={3} columns={3} />
          </div>
        ) : errors.length === 0 ? (
          <div className="flex flex-col items-center py-8 text-center">
            <AlertTriangle className="mb-2 h-5 w-5 text-text-muted" />
            <p className="text-xs text-text-muted">No errors recorded</p>
          </div>
        ) : (
          <div className="max-h-[400px] space-y-2 overflow-y-auto p-3">
            {errors.map((err, i) => (
              <div
                key={i}
                className="rounded-lg border border-border-default bg-navy-800/50 p-3 transition-colors duration-150 hover:bg-navy-700/50"
              >
                <div className="mb-1.5 flex items-start justify-between gap-2">
                  <p className="min-w-0 flex-1 truncate font-mono text-xs text-severity-critical">
                    {err.message}
                  </p>
                  <span className="shrink-0 rounded border border-severity-critical/30 bg-severity-critical/10 px-1.5 py-0.5 tabular-nums text-[10px] font-semibold text-severity-critical">
                    {err.count.toLocaleString()}x
                  </span>
                </div>
                <div className="flex flex-wrap gap-3 text-[10px] text-text-muted">
                  <span>Last: {new Date(err.last_seen).toLocaleString()}</span>
                  {err.sample_trace_id && (
                    <span className="flex items-center gap-1 font-mono text-accent-blue">
                      <ExternalLink className="h-2.5 w-2.5" />
                      {err.sample_trace_id.slice(0, 12)}...
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main APM Page ───────────────────────────────────────────────────

export default function APMPage() {
  const [services, setServices] = useState<ServiceData[]>([]);
  const [mapNodes, setMapNodes] = useState<MapNode[]>([]);
  const [mapEdges, setMapEdges] = useState<MapEdge[]>([]);
  const [selectedService, setSelectedService] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    Promise.all([getAPMServices(), getServiceMap()])
      .then(([svcRes, mapRes]) => {
        if (cancelled) return;
        setServices(svcRes?.services || []);
        setMapNodes(mapRes?.nodes || []);
        setMapEdges(mapRes?.edges || []);
        setLoading(false);
      })
      .catch(() => {
        if (!cancelled) {
          setError("Failed to load APM data");
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const selectedSvc = useMemo(
    () => services.find((s) => s.service === selectedService) ?? null,
    [services, selectedService],
  );

  const handleSelectService = useCallback((name: string) => {
    setSelectedService((prev) => (prev === name ? null : name));
  }, []);

  const healthCounts = useMemo(() => {
    const counts = { healthy: 0, warning: 0, critical: 0 };
    services.forEach((s) => {
      const status = s.status as keyof typeof counts;
      if (status in counts) counts[status]++;
    });
    return counts;
  }, [services]);

  // ── Loading state ─────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="skeleton h-7 w-56 rounded" />
            <div className="skeleton mt-1.5 h-4 w-72 rounded" />
          </div>
          <div className="skeleton h-9 w-32 rounded-lg" />
        </div>
        <ServiceCardsSkeleton />
        <ServiceMapSkeleton />
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-text-primary">
              Application Performance
            </h1>
          </div>
          <TimeRangePicker />
        </div>
        <div className="flex flex-col items-center rounded-xl border border-border-default/60 bg-surface-secondary py-16 text-center">
          <AlertTriangle className="mb-3 h-8 w-8 text-severity-critical" />
          <p className="text-sm text-severity-critical">{error}</p>
          <button
            onClick={() => window.location.reload()}
            className="mt-3 text-xs text-accent-blue transition-colors duration-150 hover:text-cyan-400"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  // ── Render ────────────────────────────────────────────────────────

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-text-primary">
            Application Performance
          </h1>
          <p className="mt-0.5 flex items-center gap-3 text-sm text-text-muted">
            Service health and dependency monitoring
            <span className="flex items-center gap-3 text-xs">
              <span className="flex items-center gap-1">
                <span className="inline-block h-2 w-2 rounded-full bg-severity-ok" />
                {healthCounts.healthy}
              </span>
              <span className="flex items-center gap-1">
                <span className="inline-block h-2 w-2 rounded-full bg-severity-warning" />
                {healthCounts.warning}
              </span>
              <span className="flex items-center gap-1">
                <span className="inline-block h-2 w-2 rounded-full bg-severity-critical" />
                {healthCounts.critical}
              </span>
            </span>
          </p>
        </div>
        <TimeRangePicker />
      </div>

      {services.length === 0 ? (
        <div className="flex flex-col items-center rounded-xl border border-border-default/60 bg-surface-secondary py-16 text-center">
          <Server className="mb-3 h-8 w-8 text-text-muted" />
          <p className="text-sm text-text-secondary">No services detected yet</p>
          <p className="mt-1 text-xs text-text-muted">
            Data will appear once traces are ingested
          </p>
        </div>
      ) : (
        <>
          {/* Row 1: Service health cards */}
          <div>
            <h2 className="mb-3 text-xs font-medium uppercase tracking-wider text-text-muted">
              Service Health
            </h2>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {services.map((svc) => {
                const isSelected = selectedService === svc.service;
                return (
                  <button
                    key={svc.service}
                    onClick={() => handleSelectService(svc.service)}
                    className={cn(
                      "group relative flex flex-col rounded-xl border-l-[3px] border border-border-default/60 bg-surface-secondary p-4 text-left transition-all duration-150",
                      HEALTH_BORDER[svc.status] || "border-l-text-muted",
                      isSelected
                        ? "border-cyan-500/40 bg-cyan-500/5 shadow-lg shadow-cyan-500/5"
                        : "hover:border-navy-500 hover:bg-navy-800/40",
                    )}
                  >
                    {/* Header */}
                    <div className="mb-3 flex items-center gap-2">
                      <span
                        className={cn(
                          "inline-block h-2 w-2 rounded-full",
                          HEALTH_DOT[svc.status] || "bg-text-muted",
                        )}
                      />
                      <span className="truncate text-sm font-medium text-text-primary">
                        {svc.service}
                      </span>
                      {isSelected && (
                        <ChevronUp className="ml-auto h-3.5 w-3.5 text-cyan-400" />
                      )}
                      {!isSelected && (
                        <ChevronDown className="ml-auto h-3.5 w-3.5 text-text-muted opacity-0 transition-opacity group-hover:opacity-100" />
                      )}
                    </div>

                    {/* Metrics */}
                    <div className="grid grid-cols-3 gap-2">
                      <div>
                        <p className="text-[9px] uppercase tracking-wider text-text-muted">req/s</p>
                        <p className="tabular-nums text-sm font-semibold text-text-primary">
                          {formatRate(svc.request_count)}
                        </p>
                      </div>
                      <div>
                        <p className="text-[9px] uppercase tracking-wider text-text-muted">err%</p>
                        <p
                          className={cn(
                            "tabular-nums text-sm font-semibold",
                            svc.error_rate > 5
                              ? "text-severity-critical"
                              : svc.error_rate > 1
                                ? "text-severity-warning"
                                : "text-text-primary",
                          )}
                        >
                          {formatPercent(svc.error_rate)}
                        </p>
                      </div>
                      <div>
                        <p className="text-[9px] uppercase tracking-wider text-text-muted">p99</p>
                        <p className={cn("tabular-nums text-sm font-semibold", latencyColor(svc.p99_duration_ms))}>
                          {formatLatency(svc.p99_duration_ms)}
                        </p>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Row 2: Service Map */}
          <div>
            <h2 className="mb-3 text-xs font-medium uppercase tracking-wider text-text-muted">
              Service Topology
            </h2>
            <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-4">
              <ServiceMapFlow
                nodes={mapNodes}
                edges={mapEdges}
                selectedService={selectedService}
                onSelect={handleSelectService}
              />
            </div>
          </div>

          {/* Row 3: Service detail (endpoints + errors) */}
          {selectedSvc && (
            <div>
              <div className="mb-3 flex items-center justify-between">
                <h2 className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-text-muted">
                  <span
                    className={cn(
                      "inline-block h-2 w-2 rounded-full",
                      HEALTH_DOT[selectedSvc.status] || "bg-text-muted",
                    )}
                  />
                  {selectedSvc.service}
                  <span className={cn("text-[10px] normal-case", HEALTH_TEXT[selectedSvc.status] || "text-text-muted")}>
                    ({selectedSvc.status})
                  </span>
                </h2>
                <button
                  onClick={() => setSelectedService(null)}
                  className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-text-muted transition-colors duration-150 hover:bg-navy-700 hover:text-text-primary"
                >
                  <X className="h-3 w-3" />
                  Close
                </button>
              </div>

              {/* Quick stats row */}
              <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
                {[
                  { label: "Requests", value: formatRate(selectedSvc.request_count) },
                  { label: "Error Rate", value: formatPercent(selectedSvc.error_rate), danger: selectedSvc.error_rate > 5 },
                  { label: "Avg Latency", value: formatLatency(selectedSvc.avg_duration_ms) },
                  { label: "P99 Latency", value: formatLatency(selectedSvc.p99_duration_ms), danger: selectedSvc.p99_duration_ms > 1000 },
                ].map((m) => (
                  <div key={m.label} className="rounded-xl border border-border-default/60 bg-surface-secondary p-3">
                    <p className="text-[9px] font-medium uppercase tracking-wider text-text-muted">
                      {m.label}
                    </p>
                    <p
                      className={cn(
                        "mt-1 tabular-nums text-lg font-semibold",
                        m.danger ? "text-severity-critical" : "text-text-primary",
                      )}
                    >
                      {m.value}
                    </p>
                  </div>
                ))}
              </div>

              <ServiceDetailPanel service={selectedSvc} onClose={() => setSelectedService(null)} />
            </div>
          )}
        </>
      )}
    </div>
  );
}
