"use client";

import React, { useState } from "react";
import { cn } from "@/lib/utils";
import { TimeRangePicker } from "@/components/shared/time-range-picker";
import { ChartWidget } from "@/components/dashboard/chart-widget";

// ── Mock Data ──────────────────────────────────────────────────────────

const mockWebVitals = {
  lcp: { value: 2.1, unit: "s", rating: "good", threshold: 2.5 },
  fid: { value: 45, unit: "ms", rating: "good", threshold: 100 },
  cls: { value: 0.08, unit: "", rating: "good", threshold: 0.1 },
  fcp: { value: 1.4, unit: "s", rating: "good", threshold: 1.8 },
  tti: { value: 3.2, unit: "s", rating: "good", threshold: 3.8 },
  inp: { value: 120, unit: "ms", rating: "needs_improvement", threshold: 200 },
};

const mockLoadTimeData = [
  { time: "00:00", value: 2.1 },
  { time: "04:00", value: 1.9 },
  { time: "08:00", value: 2.8 },
  { time: "12:00", value: 3.1 },
  { time: "16:00", value: 2.6 },
  { time: "20:00", value: 2.3 },
  { time: "24:00", value: 2.0 },
];

const mockPages = [
  { url: "/", views: 45230, avgLoad: 1.8, errorRate: 0.2, lcp: 2.1, fid: 32, cls: 0.05 },
  { url: "/products", views: 28100, avgLoad: 2.4, errorRate: 0.5, lcp: 2.8, fid: 55, cls: 0.12 },
  { url: "/checkout", views: 12500, avgLoad: 3.1, errorRate: 1.2, lcp: 3.5, fid: 89, cls: 0.18 },
  { url: "/dashboard", views: 8900, avgLoad: 2.9, errorRate: 0.8, lcp: 3.2, fid: 67, cls: 0.09 },
  { url: "/search", views: 21400, avgLoad: 2.0, errorRate: 0.3, lcp: 2.3, fid: 41, cls: 0.06 },
  { url: "/profile", views: 6700, avgLoad: 1.5, errorRate: 0.1, lcp: 1.8, fid: 28, cls: 0.03 },
];

const mockErrors = [
  {
    id: "err-1",
    message: "TypeError: Cannot read properties of undefined (reading 'map')",
    filename: "/static/js/main.a2f4c.js",
    line: 1247,
    count: 342,
    sessions: 189,
    lastSeen: "2 min ago",
    stack: `TypeError: Cannot read properties of undefined (reading 'map')
    at ProductList (webpack:///src/components/ProductList.tsx:45:23)
    at renderWithHooks (webpack:///node_modules/react-dom/cjs/react-dom.development.js:14985:18)
    at mountIndeterminateComponent (webpack:///node_modules/react-dom/cjs/react-dom.development.js:17811:13)`,
  },
  {
    id: "err-2",
    message: "ReferenceError: analytics is not defined",
    filename: "/static/js/analytics.8b2e1.js",
    line: 89,
    count: 156,
    sessions: 98,
    lastSeen: "15 min ago",
    stack: `ReferenceError: analytics is not defined
    at trackEvent (webpack:///src/utils/analytics.ts:89:5)
    at onClick (webpack:///src/components/Button.tsx:23:9)`,
  },
  {
    id: "err-3",
    message: "NetworkError: Failed to fetch",
    filename: "/static/js/api.c3d5e.js",
    line: 34,
    count: 89,
    sessions: 67,
    lastSeen: "1 hour ago",
    stack: `TypeError: Failed to fetch
    at fetchData (webpack:///src/api/client.ts:34:20)
    at async loadProducts (webpack:///src/pages/Products.tsx:18:22)`,
  },
];

const mockGeoData = [
  { country: "United States", views: 42000, avgLoad: 1.9, errorRate: 0.3 },
  { country: "United Kingdom", views: 12500, avgLoad: 2.3, errorRate: 0.4 },
  { country: "Germany", views: 9800, avgLoad: 2.1, errorRate: 0.2 },
  { country: "Japan", views: 8200, avgLoad: 3.4, errorRate: 0.6 },
  { country: "Brazil", views: 6500, avgLoad: 4.1, errorRate: 1.1 },
  { country: "India", views: 5800, avgLoad: 4.8, errorRate: 1.4 },
  { country: "Australia", views: 4200, avgLoad: 2.8, errorRate: 0.5 },
];

const mockDevices = [
  { name: "Chrome", type: "browser", views: 52000, avgLoad: 2.0 },
  { name: "Safari", type: "browser", views: 18000, avgLoad: 2.2 },
  { name: "Firefox", type: "browser", views: 8500, avgLoad: 2.4 },
  { name: "Edge", type: "browser", views: 5200, avgLoad: 2.1 },
  { name: "Desktop", type: "device", views: 48000, avgLoad: 1.8 },
  { name: "Mobile", type: "device", views: 32000, avgLoad: 3.1 },
  { name: "Tablet", type: "device", views: 4500, avgLoad: 2.6 },
];

// ── Helper Components ──────────────────────────────────────────────────

function VitalRatingBadge({ rating }: { rating: string }) {
  const colors: Record<string, string> = {
    good: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
    needs_improvement: "bg-amber-500/20 text-amber-400 border-amber-500/30",
    poor: "bg-red-500/20 text-red-400 border-red-500/30",
  };
  const labels: Record<string, string> = {
    good: "Good",
    needs_improvement: "Needs Work",
    poor: "Poor",
  };
  return (
    <span className={cn("px-2 py-0.5 text-xs font-medium rounded border", colors[rating] || colors.good)}>
      {labels[rating] || rating}
    </span>
  );
}

// ── Tab Config ──────────────────────────────────────────────────────────

const TABS = [
  { id: "pages" as const, label: "Top Pages" },
  { id: "errors" as const, label: "JS Errors" },
  { id: "geo" as const, label: "Geography" },
  { id: "devices" as const, label: "Devices" },
];

// ── Main Page ──────────────────────────────────────────────────────────

export default function RUMPage() {
  const [expandedError, setExpandedError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"pages" | "errors" | "geo" | "devices">("pages");

  return (
    <div className="space-y-4">
      {/* ── Header ───────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-text-primary">Real User Monitoring</h1>
          <p className="mt-0.5 text-sm text-text-muted">
            Core Web Vitals, page performance, and user experience metrics from real browser sessions.
          </p>
        </div>
        <TimeRangePicker />
      </div>

      {/* SDK Installation Banner */}
      <div className="rounded-xl border border-accent-blue/20 bg-accent-blue/5 p-6">
        <div className="flex items-start gap-4">
          <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-accent-blue/15">
            <svg className="h-5 w-5 text-accent-blue" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div className="flex-1">
            <h3 className="text-sm font-semibold text-accent-blue">Install the RayOlly Browser SDK to start collecting RUM data</h3>
            <p className="mt-1 text-xs text-text-muted">
              Add the following snippet to your website to begin capturing real user metrics, Core Web Vitals, JS errors, and session data.
            </p>
            <div className="mt-3 rounded-lg border border-border-default/60 bg-surface-secondary p-3">
              <code className="text-xs text-emerald-400 font-mono">
                {'<script src="https://cdn.rayolly.io/rum.js"></script>'}
              </code>
            </div>
            <p className="mt-2 text-[10px] text-text-muted">
              The data below is preview/sample data showing what the dashboard will look like once the SDK is installed.
            </p>
          </div>
        </div>
      </div>

      {/* Core Web Vitals Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        {Object.entries(mockWebVitals).map(([key, vital]) => (
          <div
            key={key}
            className="rounded-xl border border-border-default/60 bg-surface-secondary p-4 transition-colors hover:border-navy-500"
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-text-muted uppercase tracking-wider">
                {key.toUpperCase()}
              </span>
              <VitalRatingBadge rating={vital.rating} />
            </div>
            <div className="text-2xl font-bold text-text-primary">
              {vital.value}
              <span className="text-sm font-normal text-text-muted ml-1">{vital.unit}</span>
            </div>
            <div className="mt-2 h-1.5 bg-navy-700 rounded-full overflow-hidden">
              <div
                className={cn(
                  "h-full rounded-full transition-all",
                  vital.rating === "good"
                    ? "bg-emerald-500"
                    : vital.rating === "needs_improvement"
                    ? "bg-amber-500"
                    : "bg-red-500",
                )}
                style={{
                  width: `${Math.min(100, (vital.value / vital.threshold) * 100)}%`,
                }}
              />
            </div>
            <div className="text-[10px] text-text-muted mt-1">
              Threshold: {vital.threshold}
              {vital.unit}
            </div>
          </div>
        ))}
      </div>

      {/* Page Load Time Chart */}
      <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-6">
        <ChartWidget
          title="Page Load Time (24h)"
          type="bar"
          xData={mockLoadTimeData.map((d) => d.time)}
          series={[{ name: "Load Time", data: mockLoadTimeData.map((d) => d.value), color: "#06b6d4" }]}
          height={160}
          showLegend={false}
          yAxisLabel="seconds"
        />
      </div>

      {/* ── Tabs ─────────────────────────────────────────────────── */}
      <div className="flex items-center gap-1 rounded-lg border border-border-default bg-surface-primary p-1">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
              activeTab === tab.id
                ? "bg-cyan-500/10 text-cyan-400"
                : "text-text-muted hover:text-text-secondary hover:bg-navy-800/40",
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Top Pages Table */}
      {activeTab === "pages" && (
        <div className="rounded-xl border border-border-default/60 bg-surface-secondary overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border-default">
                <th className="text-left text-xs font-semibold text-text-muted uppercase tracking-wider px-6 py-3">
                  URL
                </th>
                <th className="text-right text-xs font-semibold text-text-muted uppercase tracking-wider px-6 py-3">
                  Views
                </th>
                <th className="text-right text-xs font-semibold text-text-muted uppercase tracking-wider px-6 py-3">
                  Avg Load
                </th>
                <th className="text-right text-xs font-semibold text-text-muted uppercase tracking-wider px-6 py-3">
                  LCP
                </th>
                <th className="text-right text-xs font-semibold text-text-muted uppercase tracking-wider px-6 py-3">
                  FID
                </th>
                <th className="text-right text-xs font-semibold text-text-muted uppercase tracking-wider px-6 py-3">
                  CLS
                </th>
                <th className="text-right text-xs font-semibold text-text-muted uppercase tracking-wider px-6 py-3">
                  Error Rate
                </th>
              </tr>
            </thead>
            <tbody>
              {mockPages.map((page) => (
                <tr key={page.url} className="border-b border-border-subtle transition-colors hover:bg-navy-800/40">
                  <td className="px-6 py-4">
                    <span className="text-accent-blue font-mono text-sm">{page.url}</span>
                  </td>
                  <td className="px-6 py-4 text-right text-sm text-text-secondary">
                    {page.views.toLocaleString()}
                  </td>
                  <td className="px-6 py-4 text-right text-sm text-text-secondary">{page.avgLoad}s</td>
                  <td className="px-6 py-4 text-right">
                    <span className={cn("text-sm", page.lcp <= 2.5 ? "text-emerald-400" : page.lcp <= 4 ? "text-amber-400" : "text-red-400")}>
                      {page.lcp}s
                    </span>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <span className={cn("text-sm", page.fid <= 100 ? "text-emerald-400" : page.fid <= 300 ? "text-amber-400" : "text-red-400")}>
                      {page.fid}ms
                    </span>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <span className={cn("text-sm", page.cls <= 0.1 ? "text-emerald-400" : page.cls <= 0.25 ? "text-amber-400" : "text-red-400")}>
                      {page.cls}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <span className={cn("text-sm", page.errorRate < 0.5 ? "text-emerald-400" : page.errorRate < 1 ? "text-amber-400" : "text-red-400")}>
                      {page.errorRate}%
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* JS Errors */}
      {activeTab === "errors" && (
        <div className="space-y-3">
          {mockErrors.map((error) => (
            <div
              key={error.id}
              className="rounded-xl border border-border-default/60 bg-surface-secondary overflow-hidden transition-colors hover:border-navy-500"
            >
              <button
                className="w-full text-left px-6 py-4 flex items-start justify-between"
                onClick={() => setExpandedError(expandedError === error.id ? null : error.id)}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 mb-1">
                    <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-red-500/20 text-red-400 text-xs flex-shrink-0">
                      !
                    </span>
                    <span className="text-sm font-medium text-text-primary truncate">{error.message}</span>
                  </div>
                  <div className="flex gap-4 ml-8 text-xs text-text-muted">
                    <span className="font-mono">{error.filename}:{error.line}</span>
                    <span>{error.count} occurrences</span>
                    <span>{error.sessions} sessions</span>
                    <span>Last: {error.lastSeen}</span>
                  </div>
                </div>
                <svg
                  className={cn(
                    "w-5 h-5 text-text-muted transition-transform flex-shrink-0 ml-4",
                    expandedError === error.id && "rotate-180",
                  )}
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              {expandedError === error.id && (
                <div className="px-6 pb-4 border-t border-border-default">
                  <pre className="mt-3 p-4 bg-navy-950 rounded-lg text-xs text-red-300 font-mono overflow-x-auto whitespace-pre-wrap">
                    {error.stack}
                  </pre>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Geography */}
      {activeTab === "geo" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Map placeholder */}
          <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-6">
            <h3 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-4">
              Performance by Region
            </h3>
            <div className="h-64 flex items-center justify-center border border-dashed border-navy-500 rounded-lg bg-navy-950/50">
              <div className="text-center">
                <svg className="w-12 h-12 text-text-muted mx-auto mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <p className="text-sm text-text-muted">Geographic performance map</p>
                <p className="text-xs text-text-muted">Integrate with Mapbox or similar</p>
              </div>
            </div>
          </div>

          {/* Country table */}
          <div className="rounded-xl border border-border-default/60 bg-surface-secondary overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border-default">
                  <th className="text-left text-xs font-semibold text-text-muted uppercase tracking-wider px-4 py-3">Country</th>
                  <th className="text-right text-xs font-semibold text-text-muted uppercase tracking-wider px-4 py-3">Views</th>
                  <th className="text-right text-xs font-semibold text-text-muted uppercase tracking-wider px-4 py-3">Avg Load</th>
                  <th className="text-right text-xs font-semibold text-text-muted uppercase tracking-wider px-4 py-3">Errors</th>
                </tr>
              </thead>
              <tbody>
                {mockGeoData.map((geo) => (
                  <tr key={geo.country} className="border-b border-border-subtle transition-colors hover:bg-navy-800/40">
                    <td className="px-4 py-3 text-sm text-text-secondary">{geo.country}</td>
                    <td className="px-4 py-3 text-right text-sm text-text-secondary">{geo.views.toLocaleString()}</td>
                    <td className="px-4 py-3 text-right">
                      <span className={cn("text-sm", geo.avgLoad <= 2.5 ? "text-emerald-400" : geo.avgLoad <= 4 ? "text-amber-400" : "text-red-400")}>
                        {geo.avgLoad}s
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className={cn("text-sm", geo.errorRate < 0.5 ? "text-emerald-400" : geo.errorRate < 1 ? "text-amber-400" : "text-red-400")}>
                        {geo.errorRate}%
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Devices / Browsers */}
      {activeTab === "devices" && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Browsers */}
          <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-6">
            <h3 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-4">
              By Browser
            </h3>
            <div className="space-y-3">
              {mockDevices
                .filter((d) => d.type === "browser")
                .map((device) => {
                  const total = mockDevices.filter((d) => d.type === "browser").reduce((s, d) => s + d.views, 0);
                  const pct = ((device.views / total) * 100).toFixed(1);
                  return (
                    <div key={device.name}>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm text-text-secondary">{device.name}</span>
                        <div className="flex items-center gap-3">
                          <span className="text-xs text-text-muted">{device.views.toLocaleString()} views</span>
                          <span className="text-xs text-text-muted">{pct}%</span>
                        </div>
                      </div>
                      <div className="h-2 bg-navy-700 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-cyan-500 rounded-full"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <div className="text-[10px] text-text-muted mt-0.5">Avg load: {device.avgLoad}s</div>
                    </div>
                  );
                })}
            </div>
          </div>

          {/* Device Types */}
          <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-6">
            <h3 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-4">
              By Device Type
            </h3>
            <div className="space-y-3">
              {mockDevices
                .filter((d) => d.type === "device")
                .map((device) => {
                  const total = mockDevices.filter((d) => d.type === "device").reduce((s, d) => s + d.views, 0);
                  const pct = ((device.views / total) * 100).toFixed(1);
                  const colors: Record<string, string> = {
                    Desktop: "bg-violet-500",
                    Mobile: "bg-cyan-500",
                    Tablet: "bg-amber-500",
                  };
                  return (
                    <div key={device.name}>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm text-text-secondary">{device.name}</span>
                        <div className="flex items-center gap-3">
                          <span className="text-xs text-text-muted">{device.views.toLocaleString()} views</span>
                          <span className="text-xs text-text-muted">{pct}%</span>
                        </div>
                      </div>
                      <div className="h-2 bg-navy-700 rounded-full overflow-hidden">
                        <div
                          className={cn("h-full rounded-full", colors[device.name] || "bg-cyan-500")}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <div className="text-[10px] text-text-muted mt-0.5">Avg load: {device.avgLoad}s</div>
                    </div>
                  );
                })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
