"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  Search,
  Filter,
  X,
  ChevronDown,
  ChevronRight,
  FileText,
  RefreshCw,
  Command,
  ArrowDown,
  ArrowUp,
  Copy,
  CheckCircle2,
} from "lucide-react";
import { cn, severityColor, severityBgColor, formatTimestamp, truncate, relativeTime } from "@/lib/utils";
import { TimeRangePicker } from "@/components/shared/time-range-picker";
import { ChartWidget } from "@/components/dashboard/chart-widget";
import {
  CardSkeleton,
  TableSkeleton,
  ChartSkeleton,
} from "@/components/shared/loading-skeleton";
import { searchLogs, getLogServices, getLogVolume } from "@/lib/api";
import type { Severity } from "@/types";

// ── Types ───────────────────────────────────────────────────────────

interface LogEntry {
  timestamp: string;
  service: string;
  host: string;
  severity: string;
  body: string;
  attributes: Record<string, string>;
}

// ── Severity config ──────────────────────────────────────────────────

const SEVERITY_CONFIG: Record<string, { label: string; dotColor: string; pillBg: string; pillText: string }> = {
  info: { label: "INFO", dotColor: "bg-blue-400", pillBg: "bg-blue-500/15", pillText: "text-blue-400" },
  warning: { label: "WARN", dotColor: "bg-yellow-400", pillBg: "bg-yellow-500/15", pillText: "text-yellow-400" },
  error: { label: "ERROR", dotColor: "bg-red-400", pillBg: "bg-red-500/15", pillText: "text-red-400" },
  critical: { label: "FATAL", dotColor: "bg-purple-400", pillBg: "bg-purple-500/15", pillText: "text-purple-400" },
  fatal: { label: "FATAL", dotColor: "bg-purple-400", pillBg: "bg-purple-500/15", pillText: "text-purple-400" },
};

function getSevConfig(sev: string) {
  return SEVERITY_CONFIG[sev.toLowerCase()] ?? { label: sev.toUpperCase(), dotColor: "bg-slate-400", pillBg: "bg-slate-500/15", pillText: "text-slate-400" };
}

// ── Component ──────────────────────────────────────────────────────

export default function LogsPage() {
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [expandedLog, setExpandedLog] = useState<number | null>(null);
  const [selectedSeverities, setSelectedSeverities] = useState<Severity[]>([]);
  const [selectedService, setSelectedService] = useState<string | null>(null);
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [services, setServices] = useState<{ service: string; count: number }[]>([]);
  const [volume, setVolume] = useState<{ timestamp: string; count: number; error_count: number }[]>([]);

  const searchInputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<NodeJS.Timeout | null>(null);

  // Build current filter params
  const buildParams = useCallback(() => {
    const params: Record<string, string> = {};
    if (searchQuery) params.q = searchQuery;
    if (selectedSeverities.length > 0) params.severity = selectedSeverities.join(",");
    if (selectedService) params.service = selectedService;
    return params;
  }, [searchQuery, selectedSeverities, selectedService]);

  const fetchLogs = useCallback(async (params: Record<string, string>) => {
    try {
      const data = await searchLogs(params);
      const arr = Array.isArray(data) ? data : [];
      setLogs(arr);
      setTotalCount(arr.length);
    } catch {
      setLogs([]);
      setTotalCount(0);
    }
  }, []);

  // Initial load
  useEffect(() => {
    async function load() {
      try {
        const [logsData, svcData, volData] = await Promise.all([
          searchLogs({}),
          getLogServices(),
          getLogVolume(),
        ]);
        const arr = Array.isArray(logsData) ? logsData : [];
        setLogs(arr);
        setTotalCount(arr.length);
        setServices(Array.isArray(svcData) ? svcData : []);
        setVolume(Array.isArray(volData) ? volData : []);
      } catch {
        // keep defaults
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  // Keyboard shortcut: "/" to focus search
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "/" && document.activeElement?.tagName !== "INPUT") {
        e.preventDefault();
        searchInputRef.current?.focus();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Debounced search on type
  const handleSearchInput = (value: string) => {
    setSearchQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      const params: Record<string, string> = {};
      if (value) params.q = value;
      if (selectedSeverities.length > 0) params.severity = selectedSeverities.join(",");
      if (selectedService) params.service = selectedService;
      fetchLogs(params);
    }, 300);
  };

  const toggleSeverity = (sev: Severity) => {
    setSelectedSeverities((prev) => {
      const next = prev.includes(sev) ? prev.filter((s) => s !== sev) : [...prev, sev];
      const params: Record<string, string> = {};
      if (searchQuery) params.q = searchQuery;
      if (next.length > 0) params.severity = next.join(",");
      if (selectedService) params.service = selectedService;
      fetchLogs(params);
      return next;
    });
  };

  const selectService = (service: string | null) => {
    setSelectedService(service);
    const params: Record<string, string> = {};
    if (searchQuery) params.q = searchQuery;
    if (selectedSeverities.length > 0) params.severity = selectedSeverities.join(",");
    if (service) params.service = service;
    fetchLogs(params);
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    await fetchLogs(buildParams());
    setRefreshing(false);
  };

  const copyLogBody = (idx: number, body: string) => {
    navigator.clipboard.writeText(body).catch(() => {});
    setCopiedIdx(idx);
    setTimeout(() => setCopiedIdx(null), 1500);
  };

  // Volume chart data
  const volumeXData = volume.map((d) => {
    const date = new Date(d.timestamp);
    return date.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });
  });
  const volumeYData = volume.map((d) => d.count);
  const volumeErrorYData = volume.map((d) => d.error_count);

  const severities: Severity[] = ["info", "warning", "error", "critical"];

  // Severity counts derived from current logs
  const sevCounts = logs.reduce<Record<string, number>>((acc, l) => {
    const s = l.severity.toLowerCase();
    acc[s] = (acc[s] || 0) + 1;
    return acc;
  }, {});

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-12 animate-pulse rounded-lg bg-navy-800/50" />
        <div className="h-10 animate-pulse rounded-lg bg-navy-800/50" />
        <ChartSkeleton className="h-20" />
        <div className="flex gap-4">
          <CardSkeleton className="w-52 shrink-0 hidden xl:block" />
          <TableSkeleton className="flex-1" rows={10} columns={4} />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* ── Header ───────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-text-primary">
            Log Explorer
          </h1>
          <p className="mt-0.5 text-sm text-text-muted">
            Search and analyze log data across all services
            {totalCount > 0 && (
              <span className="ml-1.5 text-text-secondary font-medium tabular-nums">&middot; {totalCount.toLocaleString()} results</span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleRefresh}
            className="flex items-center gap-1.5 rounded-lg border border-border-default/60 bg-surface-secondary px-3 py-1.5 text-sm text-text-secondary transition-all duration-150 hover:border-navy-500 hover:text-text-primary"
          >
            <RefreshCw className={cn("h-3.5 w-3.5", refreshing && "animate-spin")} />
          </button>
          <TimeRangePicker />
        </div>
      </div>

      {/* ── Search Bar (prominent) ───────────────────────────────── */}
      <div className="relative">
        <Search className="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
        <input
          ref={searchInputRef}
          type="text"
          value={searchQuery}
          onChange={(e) => handleSearchInput(e.target.value)}
          placeholder='Search logs by message, service, trace ID... (press "/" to focus)'
          className="w-full rounded-xl border border-border-default/60 bg-surface-secondary py-2.5 pl-11 pr-16 text-sm text-text-primary placeholder:text-text-muted/60 focus:border-cyan-500/50 focus:outline-none focus:ring-1 focus:ring-cyan-500/30 transition-all duration-150"
        />
        <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-1.5">
          <kbd className="hidden sm:inline-flex items-center rounded border border-border-default bg-navy-800 px-1.5 py-0.5 text-[10px] font-medium text-text-muted">
            /
          </kbd>
        </div>
      </div>

      {/* ── Filter Chips ─────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-2">
        {/* Severity chips */}
        {severities.map((sev) => {
          const cfg = getSevConfig(sev);
          const isSelected = selectedSeverities.includes(sev);
          return (
            <button
              key={sev}
              onClick={() => toggleSeverity(sev)}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium transition-colors duration-150 border",
                isSelected
                  ? cn(cfg.pillBg, cfg.pillText, "border-current/20")
                  : "border-border-default text-text-muted hover:text-text-secondary hover:border-border-default/80",
              )}
            >
              <span className={cn("h-1.5 w-1.5 rounded-full", cfg.dotColor)} />
              {cfg.label}
              {sevCounts[sev] !== undefined && (
                <span className="text-[10px] opacity-60">{sevCounts[sev]}</span>
              )}
              {isSelected && (
                <X className="h-3 w-3 opacity-60 hover:opacity-100" />
              )}
            </button>
          );
        })}

        {/* Service filter */}
        {selectedService && (
          <span className="inline-flex items-center gap-1 rounded-full border border-cyan-500/20 bg-cyan-500/10 px-2.5 py-1 text-xs font-medium text-cyan-400">
            {selectedService}
            <button onClick={() => selectService(null)}>
              <X className="h-3 w-3" />
            </button>
          </span>
        )}

        {/* Clear all */}
        {(selectedSeverities.length > 0 || selectedService) && (
          <button
            onClick={() => {
              setSelectedSeverities([]);
              setSelectedService(null);
              const params: Record<string, string> = {};
              if (searchQuery) params.q = searchQuery;
              fetchLogs(params);
            }}
            className="text-xs text-text-muted hover:text-text-secondary transition-colors"
          >
            Clear all
          </button>
        )}
      </div>

      {/* ── Volume Histogram (compact) ───────────────────────────── */}
      <div className="rounded-xl border border-border-default/60 bg-surface-secondary px-4 py-2">
        <ChartWidget
          type="bar"
          xData={volumeXData}
          series={[
            { name: "Volume", data: volumeYData, color: "#06b6d4" },
            { name: "Errors", data: volumeErrorYData, color: "#ef4444" },
          ]}
          height={56}
          showLegend={false}
        />
      </div>

      {/* ── Main Content: Sidebar + Logs ─────────────────────────── */}
      <div className="flex gap-4">
        {/* Left Sidebar: Facets */}
        <div className="hidden xl:block w-52 shrink-0 space-y-3">
          {/* Severity Facet */}
          <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-3">
            <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
              Severity
            </h4>
            <div className="space-y-0.5">
              {severities.map((sev) => {
                const cfg = getSevConfig(sev);
                const count = sevCounts[sev] ?? 0;
                const isSelected = selectedSeverities.includes(sev);
                return (
                  <button
                    key={sev}
                    onClick={() => toggleSeverity(sev)}
                    className={cn(
                      "flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-xs transition-colors duration-150",
                      isSelected
                        ? "bg-navy-700 text-text-primary"
                        : "text-text-secondary hover:bg-navy-800/60",
                    )}
                  >
                    <span className="flex items-center gap-2">
                      <span className={cn("h-2 w-2 rounded-full", cfg.dotColor)} />
                      <span className={isSelected ? cfg.pillText : ""}>{cfg.label}</span>
                    </span>
                    <span className="font-mono text-[10px] text-text-muted" style={{ fontFeatureSettings: '"tnum"' }}>
                      {count}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Services Facet */}
          <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-3">
            <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
              Services
            </h4>
            <div className="space-y-0.5 max-h-64 overflow-y-auto">
              {services.map((svc) => {
                const isSelected = selectedService === svc.service;
                return (
                  <button
                    key={svc.service}
                    onClick={() => selectService(isSelected ? null : svc.service)}
                    className={cn(
                      "flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-xs transition-colors duration-150",
                      isSelected
                        ? "bg-cyan-500/10 text-cyan-400"
                        : "text-text-secondary hover:bg-navy-800/60",
                    )}
                  >
                    <span className="truncate">{svc.service}</span>
                    <span className="ml-2 shrink-0 font-mono text-[10px] text-text-muted" style={{ fontFeatureSettings: '"tnum"' }}>
                      {svc.count}
                    </span>
                  </button>
                );
              })}
              {services.length === 0 && (
                <p className="px-2 py-2 text-[10px] text-text-muted">No services</p>
              )}
            </div>
          </div>
        </div>

        {/* Right: Log Entries */}
        <div className="flex-1 min-w-0">
          <div className="rounded-xl border border-border-default/60 bg-surface-secondary overflow-hidden">
            {/* Table Header */}
            <div className="flex items-center justify-between border-b border-border-default px-4 py-2">
              <span className="text-xs font-medium text-text-muted" style={{ fontFeatureSettings: '"tnum"' }}>
                Showing {logs.length > 0 ? "1" : "0"}-{logs.length} of {totalCount} logs
              </span>
              <span className="text-[10px] text-text-muted">Newest first</span>
            </div>

            {/* Log Rows */}
            <div className="max-h-[600px] overflow-y-auto">
              {logs.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 px-4">
                  <FileText className="h-10 w-10 text-text-muted/40 mb-3" />
                  <p className="text-sm text-text-muted font-medium">No logs found</p>
                  <p className="mt-1 text-xs text-text-muted/70">
                    Try adjusting your search query or filters
                  </p>
                </div>
              ) : (
                logs.map((log, idx) => {
                  const isExpanded = expandedLog === idx;
                  const isError = log.severity.toLowerCase() === "error" || log.severity.toLowerCase() === "critical" || log.severity.toLowerCase() === "fatal";
                  const sevCfg = getSevConfig(log.severity);

                  return (
                    <div key={idx}>
                      <button
                        onClick={() => setExpandedLog(isExpanded ? null : idx)}
                        className={cn(
                          "flex w-full items-start gap-2.5 px-4 py-2 text-left transition-colors duration-150 hover:bg-navy-800/40",
                          idx % 2 === 1 && "bg-navy-900/20",
                          isError && "border-l-2 border-l-red-500/50",
                          !isError && "border-l-2 border-l-transparent",
                        )}
                      >
                        {/* Expand icon */}
                        <span className="mt-0.5 shrink-0">
                          {isExpanded ? (
                            <ChevronDown className="h-3 w-3 text-text-muted" />
                          ) : (
                            <ChevronRight className="h-3 w-3 text-text-muted" />
                          )}
                        </span>

                        {/* Timestamp */}
                        <span
                          className="w-[72px] shrink-0 text-[11px] text-text-muted font-mono leading-relaxed"
                          title={formatTimestamp(log.timestamp)}
                          style={{ fontFeatureSettings: '"tnum"' }}
                        >
                          {relativeTime(log.timestamp)}
                        </span>

                        {/* Severity badge */}
                        <span
                          className={cn(
                            "w-14 shrink-0 rounded px-1.5 py-0.5 text-center text-[10px] font-semibold",
                            sevCfg.pillBg,
                            sevCfg.pillText,
                          )}
                        >
                          {sevCfg.label}
                        </span>

                        {/* Service tag */}
                        <span className="w-28 shrink-0 truncate rounded bg-accent-blue/8 px-1.5 py-0.5 text-[11px] font-medium text-accent-blue">
                          {log.service}
                        </span>

                        {/* Message body */}
                        <span className="min-w-0 flex-1 truncate text-xs text-text-primary font-mono leading-relaxed">
                          {log.body}
                        </span>
                      </button>

                      {/* Expanded details */}
                      {isExpanded && (
                        <div className={cn(
                          "border-b border-border-subtle bg-navy-900/40 px-4 py-3",
                          isError && "border-l-2 border-l-red-500/50",
                          !isError && "border-l-2 border-l-transparent",
                        )}>
                          <div className="ml-5 space-y-3">
                            {/* Key-Value pairs */}
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-1.5">
                              <KVPair label="Timestamp" value={formatTimestamp(log.timestamp)} />
                              <KVPair label="Service" value={log.service} />
                              <KVPair label="Host" value={log.host} />
                              <KVPair label="Severity" value={log.severity} />
                              {log.attributes &&
                                Object.entries(log.attributes).map(([k, v]) => (
                                  <KVPair key={k} label={k} value={v} />
                                ))}
                            </div>

                            {/* Full message */}
                            <div className="relative">
                              <pre className="overflow-x-auto rounded-lg bg-navy-950 border border-border-default p-3 text-xs font-mono text-text-primary leading-relaxed whitespace-pre-wrap break-all">
                                {log.body}
                              </pre>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  copyLogBody(idx, log.body);
                                }}
                                className="absolute right-2 top-2 rounded bg-navy-800 p-1 text-text-muted hover:text-text-secondary transition-colors"
                                title="Copy log body"
                              >
                                {copiedIdx === idx ? (
                                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                                ) : (
                                  <Copy className="h-3.5 w-3.5" />
                                )}
                              </button>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>

            {/* Footer / Pagination */}
            {logs.length > 0 && (
              <div className="flex items-center justify-between border-t border-border-default px-4 py-2">
                <span className="text-xs text-text-muted" style={{ fontFeatureSettings: '"tnum"' }}>
                  Showing 1&ndash;{logs.length} of {totalCount}
                </span>
                <button
                  onClick={handleRefresh}
                  className="flex items-center gap-1.5 rounded-lg border border-border-default bg-navy-800/30 px-2.5 py-1 text-xs text-text-secondary transition-colors hover:border-navy-500 hover:text-text-primary"
                >
                  <RefreshCw className={cn("h-3 w-3", refreshing && "animate-spin")} />
                  Refresh
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Sub-components ─────────────────────────────────────────────────

function KVPair({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline gap-2 text-xs">
      <span className="w-24 shrink-0 text-text-muted truncate">{label}</span>
      <span className="font-mono text-text-primary break-all">{value}</span>
    </div>
  );
}
