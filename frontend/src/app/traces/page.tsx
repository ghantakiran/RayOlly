"use client";

import { useState, useEffect, useMemo } from "react";
import {
  Search,
  GitBranch,
  CheckCircle2,
  XCircle,
  Network,
  SlidersHorizontal,
  Clock,
  Layers,
  AlertTriangle,
} from "lucide-react";
import { cn, formatDuration, relativeTime } from "@/lib/utils";
import { TimeRangePicker } from "@/components/shared/time-range-picker";
import { CardSkeleton } from "@/components/shared/loading-skeleton";
import { searchTraces, getTraceServices } from "@/lib/api";

// ── Types ───────────────────────────────────────────────────────────

interface TraceEntry {
  trace_id: string;
  root_service: string;
  root_operation: string;
  duration_ms: number;
  span_count: number;
  status: string;
}

interface TraceService {
  service: string;
  span_count: number;
  avg_duration_ms: number;
  error_rate: number;
}

// ── Helpers ─────────────────────────────────────────────────────────

function durationColor(ms: number) {
  if (ms > 500) return { bar: "bg-severity-critical", text: "text-severity-critical" };
  if (ms > 100) return { bar: "bg-severity-warning", text: "text-severity-warning" };
  return { bar: "bg-cyan-500", text: "text-text-primary" };
}

function serviceHealthDot(errorRate: number) {
  if (errorRate > 10) return "bg-severity-critical";
  if (errorRate > 3) return "bg-severity-warning";
  return "bg-severity-ok";
}

// ── Skeleton loaders ────────────────────────────────────────────────

function TraceCardSkeleton() {
  return (
    <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-4">
      <div className="flex items-center gap-3">
        <div className="skeleton h-3 w-3 rounded-full" />
        <div className="skeleton h-4 w-20 rounded" />
        <div className="skeleton h-4 w-40 rounded" />
        <div className="ml-auto skeleton h-3 w-48 rounded-full" />
        <div className="skeleton h-4 w-16 rounded" />
      </div>
    </div>
  );
}

function ServiceStatsSkeleton() {
  return (
    <div className="space-y-2">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="rounded-lg bg-navy-800/50 px-3 py-3">
          <div className="skeleton mb-2 h-3 w-24 rounded" />
          <div className="skeleton h-2.5 w-full rounded" />
        </div>
      ))}
    </div>
  );
}

// ── Component ──────────────────────────────────────────────────────

export default function TracesPage() {
  const [loading, setLoading] = useState(true);
  const [traces, setTraces] = useState<TraceEntry[]>([]);
  const [traceServices, setTraceServices] = useState<TraceService[]>([]);

  const [serviceFilter, setServiceFilter] = useState("");
  const [minDuration, setMinDuration] = useState("");
  const [statusFilter, setStatusFilter] = useState<"" | "ok" | "error">("");

  useEffect(() => {
    async function load() {
      try {
        const [traceData, svcData] = await Promise.all([
          searchTraces({}),
          getTraceServices(),
        ]);
        setTraces(Array.isArray(traceData) ? traceData : []);
        setTraceServices(Array.isArray(svcData) ? svcData : []);
      } catch {
        // keep defaults
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const filteredTraces = useMemo(() => {
    const minMs = minDuration ? parseFloat(minDuration) : 0;
    return traces.filter((t) => {
      if (serviceFilter && !t.root_service.toLowerCase().includes(serviceFilter.toLowerCase()))
        return false;
      if (minMs > 0 && t.duration_ms < minMs) return false;
      if (statusFilter && t.status !== statusFilter) return false;
      return true;
    });
  }, [traces, serviceFilter, minDuration, statusFilter]);

  const maxDuration = useMemo(
    () => Math.max(...filteredTraces.map((t) => t.duration_ms), 1),
    [filteredTraces],
  );

  const uniqueServices = useMemo(
    () => [...new Set(traces.map((t) => t.root_service))].sort(),
    [traces],
  );

  // ── Loading state ─────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="skeleton h-7 w-52 rounded" />
            <div className="skeleton mt-1.5 h-4 w-72 rounded" />
          </div>
          <div className="skeleton h-9 w-32 rounded-lg" />
        </div>
        <div className="flex gap-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="skeleton h-8 w-36 rounded-lg" />
          ))}
        </div>
        <div className="flex gap-4">
          <div className="flex-1 space-y-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <TraceCardSkeleton key={i} />
            ))}
          </div>
          <div className="hidden w-[300px] xl:block">
            <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-4">
              <div className="skeleton mb-4 h-4 w-28 rounded" />
              <ServiceStatsSkeleton />
            </div>
          </div>
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
            Distributed Traces
          </h1>
          <p className="mt-0.5 text-sm text-text-muted">
            Search and inspect distributed traces across all services
          </p>
        </div>
        <TimeRangePicker />
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-border-default/60 bg-surface-secondary px-4 py-3">
        <SlidersHorizontal className="h-4 w-4 text-text-muted" />

        {/* Service dropdown */}
        <select
          value={serviceFilter}
          onChange={(e) => setServiceFilter(e.target.value)}
          className="rounded-lg border border-border-default bg-navy-800 px-3 py-1.5 text-xs text-text-primary transition-colors duration-150 focus:border-cyan-500/50 focus:outline-none"
        >
          <option value="">All services</option>
          {uniqueServices.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>

        {/* Min duration */}
        <div className="relative">
          <Clock className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-text-muted" />
          <input
            type="number"
            value={minDuration}
            onChange={(e) => setMinDuration(e.target.value)}
            placeholder="Min ms..."
            className="w-28 rounded-lg border border-border-default bg-navy-800 py-1.5 pl-8 pr-3 text-xs text-text-primary placeholder:text-text-muted transition-colors duration-150 focus:border-cyan-500/50 focus:outline-none"
          />
        </div>

        {/* Status filter */}
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as "" | "ok" | "error")}
          className="rounded-lg border border-border-default bg-navy-800 px-3 py-1.5 text-xs text-text-primary transition-colors duration-150 focus:border-cyan-500/50 focus:outline-none"
        >
          <option value="">All statuses</option>
          <option value="ok">OK</option>
          <option value="error">Error</option>
        </select>

        <span className="ml-auto tabular-nums text-xs text-text-muted">
          {filteredTraces.length} trace{filteredTraces.length !== 1 ? "s" : ""}
        </span>
      </div>

      <div className="flex gap-4">
        {/* Trace list */}
        <div className="min-w-0 flex-1">
          {filteredTraces.length === 0 ? (
            <div className="flex flex-col items-center rounded-xl border border-border-default/60 bg-surface-secondary py-16 text-center">
              <Search className="mb-3 h-8 w-8 text-text-muted" />
              <p className="text-sm text-text-secondary">No traces found</p>
              <p className="mt-1 text-xs text-text-muted">
                Try adjusting your filters or expanding the time range
              </p>
            </div>
          ) : (
            <div className="space-y-1.5">
              {filteredTraces.map((trace) => {
                const dc = durationColor(trace.duration_ms);
                const barWidth = Math.max(3, (trace.duration_ms / maxDuration) * 100);

                return (
                  <div
                    key={trace.trace_id}
                    className="group cursor-pointer rounded-xl border border-border-default/60 bg-surface-secondary p-4 transition-all duration-150 hover:border-navy-500 hover:bg-navy-800/40"
                  >
                    <div className="flex items-center gap-3">
                      {/* Status dot */}
                      <span
                        className={cn(
                          "inline-block h-2 w-2 shrink-0 rounded-full",
                          trace.status === "ok" ? "bg-severity-ok" : "bg-severity-critical",
                        )}
                      />

                      {/* Service badge */}
                      <span className="shrink-0 rounded border border-accent-blue/30 bg-accent-blue/10 px-2 py-0.5 text-[10px] font-medium text-accent-blue">
                        {trace.root_service}
                      </span>

                      {/* Operation name */}
                      <span className="min-w-0 truncate text-sm font-medium text-text-primary">
                        {trace.root_operation}
                      </span>

                      {/* Duration bar */}
                      <div className="hidden flex-1 items-center gap-2 sm:flex">
                        <div className="relative h-2 w-full rounded-full bg-navy-700">
                          <div
                            className={cn("absolute left-0 top-0 h-full rounded-full transition-all", dc.bar)}
                            style={{ width: `${barWidth}%` }}
                          />
                        </div>
                      </div>

                      {/* Duration text */}
                      <span className={cn("shrink-0 tabular-nums text-xs font-semibold", dc.text)}>
                        {formatDuration(trace.duration_ms)}
                      </span>

                      {/* Span count */}
                      <span className="flex shrink-0 items-center gap-1 rounded bg-navy-700/80 px-1.5 py-0.5 text-[10px] text-text-muted">
                        <Layers className="h-3 w-3" />
                        {trace.span_count}
                      </span>

                      {/* Trace ID (truncated) */}
                      <span className="hidden shrink-0 font-mono text-[10px] text-text-muted md:inline">
                        {trace.trace_id.slice(0, 8)}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Service stats sidebar */}
        <div className="hidden w-[300px] shrink-0 xl:block">
          <div className="rounded-xl border border-border-default/60 bg-surface-secondary">
            <div className="flex items-center gap-2 border-b border-border-default px-4 py-3">
              <Network className="h-4 w-4 text-accent-indigo" />
              <h3 className="text-sm font-medium text-text-secondary">Service Stats</h3>
              <span className="ml-auto text-[10px] text-text-muted">
                {traceServices.length} services
              </span>
            </div>

            <div className="max-h-[calc(100vh-320px)] overflow-y-auto p-3">
              {traceServices.length === 0 ? (
                <div className="flex flex-col items-center py-8 text-center">
                  <Network className="mb-2 h-5 w-5 text-text-muted" />
                  <p className="text-xs text-text-muted">No service data available</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {traceServices.map((svc) => (
                    <div
                      key={svc.service}
                      className="rounded-lg border border-border-default bg-navy-800/50 px-3 py-3 transition-colors duration-150 hover:bg-navy-700/50"
                    >
                      <div className="flex items-center gap-2">
                        <span
                          className={cn(
                            "inline-block h-2 w-2 rounded-full",
                            serviceHealthDot(svc.error_rate),
                          )}
                        />
                        <p className="truncate text-xs font-medium text-text-primary">
                          {svc.service}
                        </p>
                      </div>
                      <div className="mt-2 grid grid-cols-3 gap-2">
                        <div>
                          <p className="text-[9px] uppercase tracking-wider text-text-muted">Spans</p>
                          <p className="tabular-nums text-xs font-semibold text-text-primary">
                            {svc.span_count.toLocaleString()}
                          </p>
                        </div>
                        <div>
                          <p className="text-[9px] uppercase tracking-wider text-text-muted">Avg</p>
                          <p className="tabular-nums text-xs font-semibold text-text-primary">
                            {svc.avg_duration_ms.toFixed(1)}ms
                          </p>
                        </div>
                        <div>
                          <p className="text-[9px] uppercase tracking-wider text-text-muted">Err%</p>
                          <p
                            className={cn(
                              "tabular-nums text-xs font-semibold",
                              svc.error_rate > 5
                                ? "text-severity-critical"
                                : svc.error_rate > 1
                                  ? "text-severity-warning"
                                  : "text-text-primary",
                            )}
                          >
                            {svc.error_rate.toFixed(1)}%
                          </p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
