"use client";

import { useState, useEffect, useMemo, useCallback } from "react";
import { Search, TrendingUp, Hash, Clock, Activity, ArrowDown, ArrowUp, Minus } from "lucide-react";
import { cn } from "@/lib/utils";
import { TimeRangePicker } from "@/components/shared/time-range-picker";
import { ChartWidget } from "@/components/dashboard/chart-widget";
import { CardSkeleton, ChartSkeleton } from "@/components/shared/loading-skeleton";
import { getMetricsList, getMetricQuery } from "@/lib/api";

// ── Types ───────────────────────────────────────────────────────────

interface MetricItem {
  name: string;
  type: string;
  point_count: number;
}

interface MetricPoint {
  timestamp: string;
  value: number;
}

// ── Helpers ─────────────────────────────────────────────────────────

function typeBadgeColor(type: string) {
  switch (type) {
    case "counter":
      return "bg-cyan-500/15 text-cyan-400 border-cyan-500/30";
    case "gauge":
      return "bg-accent-blue/15 text-accent-blue border-accent-blue/30";
    case "histogram":
      return "bg-accent-indigo/15 text-accent-indigo border-accent-indigo/30";
    default:
      return "bg-navy-700 text-text-muted border-navy-600";
  }
}

function typeIcon(type: string) {
  switch (type) {
    case "counter":
      return <TrendingUp className="h-3 w-3" />;
    case "gauge":
      return <Hash className="h-3 w-3" />;
    case "histogram":
      return <Clock className="h-3 w-3" />;
    default:
      return <Activity className="h-3 w-3" />;
  }
}

function miniSparkline(data: number[], color: string) {
  if (data.length < 2) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const w = 80;
  const h = 24;
  const points = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - ((v - min) / range) * h;
    return `${x},${y}`;
  });
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="shrink-0">
      <polyline
        points={points.join(" ")}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function computeStats(data: MetricPoint[]) {
  if (data.length === 0) return { min: 0, max: 0, avg: 0, latest: 0, points: 0 };
  const values = data.map((d) => d.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const avg = values.reduce((a, b) => a + b, 0) / values.length;
  const latest = values[values.length - 1];
  return { min, max, avg, latest, points: data.length };
}

function formatStatValue(v: number): string {
  if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M`;
  if (Math.abs(v) >= 1_000) return `${(v / 1_000).toFixed(2)}K`;
  if (Number.isInteger(v)) return v.toString();
  return v.toFixed(2);
}

// ── Skeleton loaders ────────────────────────────────────────────────

function SidebarSkeleton() {
  return (
    <div className="space-y-1">
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="rounded-lg px-3 py-2.5">
          <div className="skeleton mb-1.5 h-3 w-3/4 rounded" />
          <div className="skeleton h-2.5 w-1/2 rounded" />
        </div>
      ))}
    </div>
  );
}

function StatsRowSkeleton() {
  return (
    <div className="grid grid-cols-5 gap-3">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="rounded-lg border border-border-default bg-navy-800/50 p-3">
          <div className="skeleton mb-2 h-2.5 w-12 rounded" />
          <div className="skeleton h-5 w-16 rounded" />
        </div>
      ))}
    </div>
  );
}

function AllMetricsGridSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {Array.from({ length: 8 }).map((_, i) => (
        <CardSkeleton key={i} />
      ))}
    </div>
  );
}

// ── Component ──────────────────────────────────────────────────────

export default function MetricsPage() {
  const [loading, setLoading] = useState(true);
  const [metrics, setMetrics] = useState<MetricItem[]>([]);
  const [metricFilter, setMetricFilter] = useState("");
  const [selectedMetric, setSelectedMetric] = useState<string | null>(null);
  const [chartData, setChartData] = useState<MetricPoint[]>([]);
  const [chartLoading, setChartLoading] = useState(false);
  const [allMetricData, setAllMetricData] = useState<Record<string, MetricPoint[]>>({});
  const [allMetricLoading, setAllMetricLoading] = useState(false);

  // Load metric list on mount
  useEffect(() => {
    async function load() {
      try {
        const data = await getMetricsList();
        const list = Array.isArray(data) ? data : [];
        setMetrics(list);
        if (list.length > 0) {
          setSelectedMetric(list[0].name);
        }
      } catch {
        // keep defaults
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  // Load all sparkline data for the grid
  useEffect(() => {
    if (metrics.length === 0) return;
    async function loadAll() {
      setAllMetricLoading(true);
      const results: Record<string, MetricPoint[]> = {};
      await Promise.allSettled(
        metrics.map(async (m) => {
          try {
            const data = await getMetricQuery(m.name);
            results[m.name] = Array.isArray(data) ? data : [];
          } catch {
            results[m.name] = [];
          }
        }),
      );
      setAllMetricData(results);
      setAllMetricLoading(false);
    }
    loadAll();
  }, [metrics]);

  // Load chart data when selected metric changes
  useEffect(() => {
    if (!selectedMetric) {
      setChartData([]);
      return;
    }
    async function loadChart() {
      setChartLoading(true);
      try {
        const data = await getMetricQuery(selectedMetric!);
        setChartData(Array.isArray(data) ? data : []);
      } catch {
        setChartData([]);
      } finally {
        setChartLoading(false);
      }
    }
    loadChart();
  }, [selectedMetric]);

  const filteredMetrics = metrics.filter((m) =>
    m.name.toLowerCase().includes(metricFilter.toLowerCase()),
  );

  const chartXData = chartData.map((d) => {
    const date = new Date(d.timestamp);
    return date.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });
  });
  const chartYData = chartData.map((d) => d.value);
  const stats = useMemo(() => computeStats(chartData), [chartData]);
  const selectedMeta = metrics.find((m) => m.name === selectedMetric);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!filteredMetrics.length) return;
      const idx = filteredMetrics.findIndex((m) => m.name === selectedMetric);
      if (e.key === "ArrowDown" || e.key === "j") {
        e.preventDefault();
        const next = Math.min(idx + 1, filteredMetrics.length - 1);
        setSelectedMetric(filteredMetrics[next].name);
      } else if (e.key === "ArrowUp" || e.key === "k") {
        e.preventDefault();
        const prev = Math.max(idx - 1, 0);
        setSelectedMetric(filteredMetrics[prev].name);
      }
    },
    [filteredMetrics, selectedMetric],
  );

  // ── Loading state ─────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="skeleton h-7 w-48 rounded" />
            <div className="skeleton mt-1.5 h-4 w-64 rounded" />
          </div>
          <div className="skeleton h-9 w-32 rounded-lg" />
        </div>
        <div className="flex gap-4">
          <div className="hidden w-[250px] shrink-0 lg:block">
            <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-4">
              <div className="skeleton mb-3 h-8 w-full rounded-lg" />
              <SidebarSkeleton />
            </div>
          </div>
          <div className="flex-1 space-y-4">
            <ChartSkeleton className="h-[360px]" />
            <StatsRowSkeleton />
            <AllMetricsGridSkeleton />
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
            Metrics Explorer
          </h1>
          <p className="mt-0.5 text-sm text-text-muted">
            Query, visualize, and correlate metric data across all services
          </p>
        </div>
        <TimeRangePicker />
      </div>

      <div className="flex gap-4">
        {/* Left sidebar: Metric list */}
        <div
          className="hidden w-[250px] shrink-0 lg:block"
          onKeyDown={handleKeyDown}
          tabIndex={0}
        >
          <div className="rounded-xl border border-border-default/60 bg-surface-secondary">
            {/* Search */}
            <div className="border-b border-border-default p-3">
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-text-muted" />
                <input
                  type="text"
                  value={metricFilter}
                  onChange={(e) => setMetricFilter(e.target.value)}
                  placeholder="Search metrics..."
                  className="w-full rounded-lg border border-border-default bg-navy-800 py-1.5 pl-8 pr-3 text-xs text-text-primary placeholder:text-text-muted transition-colors duration-150 focus:border-cyan-500/50 focus:outline-none"
                />
              </div>
              <p className="mt-2 text-[10px] text-text-muted">
                {filteredMetrics.length} of {metrics.length} metrics
              </p>
            </div>

            {/* Metric list */}
            <div className="max-h-[calc(100vh-280px)] overflow-y-auto p-1">
              {filteredMetrics.length === 0 ? (
                <div className="flex flex-col items-center py-8 text-center">
                  <Search className="mb-2 h-5 w-5 text-text-muted" />
                  <p className="text-xs text-text-muted">No metrics match your filter</p>
                </div>
              ) : (
                filteredMetrics.map((m) => {
                  const isSelected = selectedMetric === m.name;
                  return (
                    <button
                      key={m.name}
                      onClick={() => setSelectedMetric(m.name)}
                      className={cn(
                        "flex w-full flex-col gap-1 rounded-lg px-3 py-2.5 text-left transition-colors duration-150",
                        isSelected
                          ? "border-l-2 border-l-cyan-400 bg-cyan-500/10 text-cyan-400"
                          : "border-l-2 border-l-transparent text-text-secondary hover:bg-navy-700/60 hover:text-text-primary",
                      )}
                    >
                      <span className="truncate font-mono text-xs font-medium">{m.name}</span>
                      <span className="flex items-center gap-2">
                        <span
                          className={cn(
                            "inline-flex items-center gap-1 rounded border px-1.5 py-px text-[9px] font-medium uppercase",
                            typeBadgeColor(m.type),
                          )}
                        >
                          {typeIcon(m.type)}
                          {m.type}
                        </span>
                        <span className="tabular-nums text-[10px] text-text-muted">
                          {m.point_count.toLocaleString()} pts
                        </span>
                      </span>
                    </button>
                  );
                })
              )}
            </div>
          </div>
        </div>

        {/* Main content */}
        <div className="min-w-0 flex-1 space-y-4">
          {/* Selected metric header + chart */}
          {selectedMetric && selectedMeta ? (
            <>
              {/* Metric heading */}
              <div className="flex items-center gap-3">
                <h2 className="truncate font-mono text-lg font-semibold text-text-primary">
                  {selectedMetric}
                </h2>
                <span
                  className={cn(
                    "inline-flex shrink-0 items-center gap-1 rounded border px-2 py-0.5 text-[10px] font-medium uppercase",
                    typeBadgeColor(selectedMeta.type),
                  )}
                >
                  {typeIcon(selectedMeta.type)}
                  {selectedMeta.type}
                </span>
              </div>

              {/* Chart */}
              <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-4">
                {chartLoading ? (
                  <div className="flex items-center justify-center py-20">
                    <div className="h-6 w-6 animate-spin rounded-full border-2 border-cyan-500 border-t-transparent" />
                    <span className="ml-2 text-xs text-text-muted">Loading chart data...</span>
                  </div>
                ) : chartData.length === 0 ? (
                  <div className="flex flex-col items-center py-20 text-center">
                    <Activity className="mb-2 h-8 w-8 text-text-muted" />
                    <p className="text-sm text-text-muted">
                      No data available for <span className="font-mono text-text-secondary">{selectedMetric}</span>
                    </p>
                    <p className="mt-1 text-xs text-text-muted">Try expanding the time range</p>
                  </div>
                ) : (
                  <ChartWidget
                    title=""
                    type="area"
                    xData={chartXData}
                    series={[{ name: selectedMetric, data: chartYData, color: "#06b6d4" }]}
                    height={320}
                    yAxisLabel="value"
                  />
                )}
              </div>

              {/* Stats row */}
              {!chartLoading && chartData.length > 0 && (
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-5">
                  {[
                    { label: "Min", value: stats.min, icon: <ArrowDown className="h-3.5 w-3.5 text-accent-blue" /> },
                    { label: "Max", value: stats.max, icon: <ArrowUp className="h-3.5 w-3.5 text-severity-warning" /> },
                    { label: "Avg", value: stats.avg, icon: <Minus className="h-3.5 w-3.5 text-text-muted" /> },
                    { label: "Latest", value: stats.latest, icon: <Activity className="h-3.5 w-3.5 text-cyan-400" /> },
                    { label: "Points", value: stats.points, icon: <Hash className="h-3.5 w-3.5 text-accent-indigo" /> },
                  ].map((s) => (
                    <div
                      key={s.label}
                      className="rounded-xl border border-border-default/60 bg-surface-secondary p-3"
                    >
                      <div className="flex items-center gap-1.5">
                        {s.icon}
                        <p className="text-[10px] font-medium uppercase tracking-wider text-text-muted">
                          {s.label}
                        </p>
                      </div>
                      <p className="mt-1 tabular-nums text-lg font-semibold text-text-primary">
                        {formatStatValue(s.value)}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <div className="flex flex-col items-center rounded-xl border border-border-default/60 bg-surface-secondary py-20 text-center">
              <Activity className="mb-3 h-10 w-10 text-text-muted" />
              <p className="text-sm text-text-secondary">
                Select a metric from the sidebar to explore its time series
              </p>
              <p className="mt-1 text-xs text-text-muted">
                Use arrow keys or click to navigate
              </p>
            </div>
          )}

          {/* All Metrics sparkline grid */}
          <div>
            <h3 className="mb-3 text-sm font-medium text-text-secondary">All Metrics</h3>
            {allMetricLoading ? (
              <AllMetricsGridSkeleton />
            ) : metrics.length === 0 ? (
              <div className="flex flex-col items-center rounded-xl border border-border-default/60 bg-surface-secondary py-12 text-center">
                <Activity className="mb-2 h-6 w-6 text-text-muted" />
                <p className="text-sm text-text-muted">No metrics ingested yet</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                {metrics.map((m) => {
                  const mData = allMetricData[m.name] || [];
                  const values = mData.map((d) => d.value);
                  const latest = values.length > 0 ? values[values.length - 1] : null;
                  const prev = values.length > 1 ? values[values.length - 2] : null;
                  const trend =
                    latest !== null && prev !== null
                      ? latest > prev
                        ? "up"
                        : latest < prev
                          ? "down"
                          : "flat"
                      : "flat";
                  const trendColor =
                    trend === "up" ? "#22c55e" : trend === "down" ? "#f97316" : "#64748b";
                  const isSelected = selectedMetric === m.name;

                  return (
                    <button
                      key={m.name}
                      onClick={() => setSelectedMetric(m.name)}
                      className={cn(
                        "group flex flex-col justify-between rounded-xl border p-3 text-left transition-all duration-150",
                        isSelected
                          ? "border-cyan-500/40 bg-cyan-500/5"
                          : "border-border-default/60 bg-surface-secondary hover:border-navy-500 hover:bg-navy-800/40",
                      )}
                    >
                      <div className="mb-2 flex items-start justify-between">
                        <div className="min-w-0 flex-1">
                          <p className="truncate font-mono text-xs font-medium text-text-primary">
                            {m.name}
                          </p>
                          <span
                            className={cn(
                              "mt-1 inline-flex items-center gap-0.5 rounded border px-1 py-px text-[8px] font-medium uppercase",
                              typeBadgeColor(m.type),
                            )}
                          >
                            {m.type}
                          </span>
                        </div>
                        {miniSparkline(values.slice(-20), trendColor)}
                      </div>
                      <div className="flex items-end justify-between">
                        <p className="tabular-nums text-base font-semibold text-text-primary">
                          {latest !== null ? formatStatValue(latest) : "--"}
                        </p>
                        <div className="flex items-center gap-0.5 text-[10px]" style={{ color: trendColor }}>
                          {trend === "up" && <ArrowUp className="h-3 w-3" />}
                          {trend === "down" && <ArrowDown className="h-3 w-3" />}
                          {trend === "flat" && <Minus className="h-3 w-3" />}
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
