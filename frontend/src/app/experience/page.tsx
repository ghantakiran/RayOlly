"use client";

import React, { useState } from "react";
import { TimeRangePicker } from "@/components/shared/time-range-picker";
import { cn } from "@/lib/utils";

// ── Mock Data ──────────────────────────────────────────────────────────

const mockApdex = {
  score: 0.92,
  satisfied: 78,
  tolerating: 16,
  frustrated: 6,
};

const mockRealVsSynthetic = [
  { metric: "LCP", realP75: 2.1, syntheticP50: 1.4, unit: "s" },
  { metric: "FID", realP75: 45, syntheticP50: 12, unit: "ms" },
  { metric: "CLS", realP75: 0.08, syntheticP50: 0.02, unit: "" },
  { metric: "TTFB", realP75: 420, syntheticP50: 180, unit: "ms" },
  { metric: "Page Load", realP75: 2.8, syntheticP50: 1.6, unit: "s" },
];

const mockFunnelSteps = [
  { name: "Homepage", users: 45000, dropoff: 0 },
  { name: "Product View", users: 28000, dropoff: 37.8 },
  { name: "Add to Cart", users: 12500, dropoff: 55.4 },
  { name: "Checkout", users: 8200, dropoff: 34.4 },
  { name: "Payment", users: 6800, dropoff: 17.1 },
  { name: "Confirmation", users: 6100, dropoff: 10.3 },
];

const mockSessionReplays = [
  {
    id: "sess-1",
    user: "user-7a2f@anon",
    duration: "4m 32s",
    pages: 6,
    errors: 2,
    frustration: "high",
    country: "US",
    device: "Chrome / macOS",
    timestamp: "5 min ago",
  },
  {
    id: "sess-2",
    user: "user-3bc1@anon",
    duration: "2m 15s",
    pages: 3,
    errors: 0,
    frustration: "low",
    country: "UK",
    device: "Safari / iOS",
    timestamp: "12 min ago",
  },
  {
    id: "sess-3",
    user: "user-9de4@anon",
    duration: "6m 48s",
    pages: 9,
    errors: 1,
    frustration: "medium",
    country: "DE",
    device: "Firefox / Windows",
    timestamp: "18 min ago",
  },
  {
    id: "sess-4",
    user: "user-1fa8@anon",
    duration: "1m 03s",
    pages: 2,
    errors: 3,
    frustration: "high",
    country: "JP",
    device: "Chrome / Android",
    timestamp: "25 min ago",
  },
  {
    id: "sess-5",
    user: "user-5cb2@anon",
    duration: "3m 20s",
    pages: 5,
    errors: 0,
    frustration: "low",
    country: "BR",
    device: "Edge / Windows",
    timestamp: "32 min ago",
  },
];

const mockImpactAnalysis = [
  {
    service: "product-api",
    p99Latency: 450,
    errorRate: 2.1,
    affectedUsers: 1240,
    frontendImpact: "LCP increased by 800ms for /products",
  },
  {
    service: "search-service",
    p99Latency: 280,
    errorRate: 0.5,
    affectedUsers: 320,
    frontendImpact: "TTI increased by 400ms for /search",
  },
  {
    service: "payment-gateway",
    p99Latency: 1200,
    errorRate: 3.8,
    affectedUsers: 89,
    frontendImpact: "Checkout abandonment up 12%",
  },
];

// ── Helper Components ──────────────────────────────────────────────────

function ApdexGauge({ score }: { score: number }) {
  let color = "text-emerald-400";
  let label = "Excellent";
  if (score < 0.94) { color = "text-accent-blue"; label = "Good"; }
  if (score < 0.85) { color = "text-amber-400"; label = "Fair"; }
  if (score < 0.7) { color = "text-red-400"; label = "Poor"; }

  const angle = score * 180;

  return (
    <div className="flex flex-col items-center">
      <div className="relative w-40 h-20 overflow-hidden mb-2">
        {/* Background arc */}
        <div className="absolute inset-0 border-[12px] border-navy-700 rounded-t-full border-b-0" />
        {/* Colored arc */}
        <div
          className="absolute inset-0 border-[12px] border-transparent rounded-t-full border-b-0"
          style={{
            borderTopColor: score >= 0.85 ? "#34d399" : score >= 0.7 ? "#fbbf24" : "#f87171",
            borderLeftColor: score >= 0.5 ? (score >= 0.85 ? "#34d399" : score >= 0.7 ? "#fbbf24" : "#f87171") : "transparent",
            borderRightColor: score >= 0.85 ? "#34d399" : score >= 0.7 ? "#fbbf24" : "#f87171",
            transform: `rotate(${angle - 180}deg)`,
            transformOrigin: "bottom center",
          }}
        />
      </div>
      <div className={`text-3xl font-bold ${color}`}>{score.toFixed(2)}</div>
      <div className="text-sm text-text-muted">{label}</div>
    </div>
  );
}

function FrustrationBadge({ level }: { level: string }) {
  const config: Record<string, { bg: string; text: string }> = {
    low: { bg: "bg-emerald-500/20 border-emerald-500/30", text: "text-emerald-400" },
    medium: { bg: "bg-amber-500/20 border-amber-500/30", text: "text-amber-400" },
    high: { bg: "bg-red-500/20 border-red-500/30", text: "text-red-400" },
  };
  const c = config[level] || config.low;
  return (
    <span className={`px-2 py-0.5 text-xs font-medium rounded border ${c.bg} ${c.text}`}>
      {level}
    </span>
  );
}

// ── Main Page ──────────────────────────────────────────────────────────

type Section = "overview" | "journeys" | "replays" | "impact";

const sectionLabels: Record<Section, string> = {
  overview: "Overview",
  journeys: "User Journeys",
  replays: "Session Replays",
  impact: "Impact Analysis",
};

export default function ExperiencePage() {
  const [activeSection, setActiveSection] = useState<Section>("overview");

  return (
    <div className="space-y-4">
      {/* ── Header ───────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-text-primary">Digital Experience Monitoring</h1>
          <p className="mt-0.5 text-sm text-text-muted">
            Unified view combining Real User Monitoring and Synthetic Monitoring with user journey analysis.
          </p>
        </div>
        <TimeRangePicker />
      </div>

      {/* DEM Banner */}
      <div className="rounded-xl border border-violet-500/30 bg-violet-500/5 p-6">
        <div className="flex items-start gap-4">
          <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-violet-500/20">
            <svg className="h-5 w-5 text-violet-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
          </div>
          <div className="flex-1">
            <h3 className="text-sm font-semibold text-violet-400">Digital Experience Monitoring combines RUM + Synthetics data</h3>
            <p className="mt-1 text-xs text-text-muted">
              To see live data in this dashboard, you need to configure both:
            </p>
            <div className="mt-2 flex gap-3">
              <div className="rounded-lg bg-surface-secondary border border-border-default px-3 py-2 flex-1">
                <p className="text-xs font-medium text-accent-blue">1. RUM Browser SDK</p>
                <p className="text-[10px] text-text-muted mt-0.5">Install the SDK on your website to capture real user data</p>
              </div>
              <div className="rounded-lg bg-surface-secondary border border-border-default px-3 py-2 flex-1">
                <p className="text-xs font-medium text-emerald-400">2. Synthetic Monitors</p>
                <p className="text-[10px] text-text-muted mt-0.5">Create monitors to proactively check endpoint health</p>
              </div>
            </div>
            <p className="mt-2 text-[10px] text-text-muted">
              The visualizations below show preview data demonstrating what the dashboard will look like once configured.
            </p>
          </div>
        </div>
      </div>

      {/* ── Section Navigation ─────────────────────────────────── */}
      <div className="flex items-center gap-1 rounded-lg border border-border-default bg-surface-primary p-1 w-fit">
        {(["overview", "journeys", "replays", "impact"] as const).map((section) => (
          <button
            key={section}
            onClick={() => setActiveSection(section)}
            className={cn(
              "px-4 py-2 text-sm font-medium rounded-md transition-colors",
              activeSection === section
                ? "bg-cyan-500/10 text-cyan-400"
                : "text-text-muted hover:text-text-secondary hover:bg-navy-800/40",
            )}
          >
            {sectionLabels[section]}
          </button>
        ))}
      </div>

      {/* Overview Section */}
      {activeSection === "overview" && (
        <div className="space-y-6">
          {/* Top row: Apdex + Satisfaction breakdown */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Apdex Score */}
            <div className="bg-surface-secondary border border-border-default rounded-xl p-6 flex flex-col items-center justify-center">
              <h3 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-4">
                User Satisfaction (Apdex)
              </h3>
              <ApdexGauge score={mockApdex.score} />
              <div className="flex gap-6 mt-4">
                <div className="text-center">
                  <div className="text-lg font-bold text-emerald-400">{mockApdex.satisfied}%</div>
                  <div className="text-[10px] text-text-muted">Satisfied</div>
                </div>
                <div className="text-center">
                  <div className="text-lg font-bold text-amber-400">{mockApdex.tolerating}%</div>
                  <div className="text-[10px] text-text-muted">Tolerating</div>
                </div>
                <div className="text-center">
                  <div className="text-lg font-bold text-red-400">{mockApdex.frustrated}%</div>
                  <div className="text-[10px] text-text-muted">Frustrated</div>
                </div>
              </div>
            </div>

            {/* Real vs Synthetic Comparison */}
            <div className="lg:col-span-2 bg-surface-secondary border border-border-default rounded-xl p-6">
              <h3 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-4">
                Real User vs Synthetic Performance
              </h3>
              <div className="overflow-hidden">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-border-default">
                      <th className="text-left text-xs font-semibold text-text-muted uppercase px-4 py-2">Metric</th>
                      <th className="text-right text-xs font-semibold text-text-muted uppercase px-4 py-2">Real (p75)</th>
                      <th className="text-right text-xs font-semibold text-text-muted uppercase px-4 py-2">Synthetic (p50)</th>
                      <th className="text-right text-xs font-semibold text-text-muted uppercase px-4 py-2">Gap</th>
                    </tr>
                  </thead>
                  <tbody>
                    {mockRealVsSynthetic.map((row) => {
                      const gap = row.unit === "s"
                        ? `+${((row.realP75 - row.syntheticP50) * 1000).toFixed(0)}ms`
                        : row.unit === "ms"
                        ? `+${(row.realP75 - row.syntheticP50).toFixed(0)}ms`
                        : `+${(row.realP75 - row.syntheticP50).toFixed(2)}`;
                      return (
                        <tr key={row.metric} className="border-b border-border-subtle hover:bg-navy-800/40">
                          <td className="px-4 py-3 text-sm font-medium text-text-primary">{row.metric}</td>
                          <td className="px-4 py-3 text-right text-sm text-text-secondary">
                            {row.realP75}{row.unit}
                          </td>
                          <td className="px-4 py-3 text-right text-sm text-text-secondary">
                            {row.syntheticP50}{row.unit}
                          </td>
                          <td className="px-4 py-3 text-right text-sm text-amber-400">{gap}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <p className="text-xs text-text-muted mt-3">
                Gap between real user experience and synthetic checks reflects network variability, device diversity, and third-party script impact.
              </p>
            </div>
          </div>

          {/* Summary stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-surface-secondary border border-border-default rounded-xl p-4">
              <div className="text-xs text-text-muted mb-1">Active Sessions</div>
              <div className="text-2xl font-bold text-text-primary">1,247</div>
              <div className="text-xs text-emerald-400 mt-1">+12% from last hour</div>
            </div>
            <div className="bg-surface-secondary border border-border-default rounded-xl p-4">
              <div className="text-xs text-text-muted mb-1">JS Error Rate</div>
              <div className="text-2xl font-bold text-text-primary">0.4%</div>
              <div className="text-xs text-emerald-400 mt-1">-0.1% from yesterday</div>
            </div>
            <div className="bg-surface-secondary border border-border-default rounded-xl p-4">
              <div className="text-xs text-text-muted mb-1">Synthetic Uptime</div>
              <div className="text-2xl font-bold text-text-primary">99.95%</div>
              <div className="text-xs text-text-muted mt-1">7 monitors active</div>
            </div>
            <div className="bg-surface-secondary border border-border-default rounded-xl p-4">
              <div className="text-xs text-text-muted mb-1">Frustrated Sessions</div>
              <div className="text-2xl font-bold text-red-400">68</div>
              <div className="text-xs text-red-400 mt-1">+23 from last hour</div>
            </div>
          </div>
        </div>
      )}

      {/* User Journeys Section */}
      {activeSection === "journeys" && (
        <div className="space-y-6">
          <div className="bg-surface-secondary border border-border-default rounded-xl p-6">
            <h3 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-6">
              Purchase Funnel
            </h3>
            <div className="space-y-2">
              {mockFunnelSteps.map((step, index) => {
                const maxUsers = mockFunnelSteps[0].users;
                const widthPct = (step.users / maxUsers) * 100;
                return (
                  <div key={step.name} className="flex items-center gap-4">
                    <div className="w-32 text-sm text-text-secondary text-right shrink-0">
                      {step.name}
                    </div>
                    <div className="flex-1 relative">
                      <div className="h-10 bg-navy-700 rounded overflow-hidden">
                        <div
                          className="h-full bg-gradient-to-r from-cyan-600 to-cyan-500 rounded flex items-center px-3 transition-all"
                          style={{ width: `${widthPct}%` }}
                        >
                          <span className="text-xs font-semibold text-text-primary whitespace-nowrap">
                            {step.users.toLocaleString()} users
                          </span>
                        </div>
                      </div>
                    </div>
                    <div className="w-20 text-right shrink-0">
                      {index > 0 ? (
                        <span className="text-xs text-red-400">-{step.dropoff}%</span>
                      ) : (
                        <span className="text-xs text-text-muted">start</span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="mt-6 pt-4 border-t border-border-default flex items-center justify-between">
              <div className="text-sm text-text-muted">
                Overall conversion: <span className="font-semibold text-text-primary">13.6%</span>
              </div>
              <div className="text-sm text-text-muted">
                Biggest drop: <span className="font-semibold text-amber-400">Product View &rarr; Add to Cart (-55.4%)</span>
              </div>
            </div>
          </div>

          {/* Funnel performance correlation */}
          <div className="bg-surface-secondary border border-border-default rounded-xl p-6">
            <h3 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-4">
              Performance by Funnel Step
            </h3>
            <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
              {mockFunnelSteps.map((step) => (
                <div key={step.name} className="bg-navy-950 rounded-xl p-3 text-center">
                  <div className="text-[10px] text-text-muted mb-1">{step.name}</div>
                  <div className="text-sm font-bold text-text-primary">
                    {(1.5 + Math.random() * 2).toFixed(1)}s
                  </div>
                  <div className="text-[10px] text-text-muted">avg load</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Session Replays Section */}
      {activeSection === "replays" && (
        <div className="space-y-4">
          <div className="bg-surface-secondary border border-border-default rounded-xl p-4 flex items-center justify-between">
            <div className="text-sm text-text-muted">
              Showing recent sessions with high frustration signals (rage clicks, error loops, dead clicks)
            </div>
            <div className="flex gap-2">
              <select className="bg-navy-700 border border-navy-600 text-text-secondary text-xs rounded-lg px-3 py-1.5">
                <option>All Frustration Levels</option>
                <option>High</option>
                <option>Medium</option>
                <option>Low</option>
              </select>
              <select className="bg-navy-700 border border-navy-600 text-text-secondary text-xs rounded-lg px-3 py-1.5">
                <option>All Devices</option>
                <option>Desktop</option>
                <option>Mobile</option>
                <option>Tablet</option>
              </select>
            </div>
          </div>

          {mockSessionReplays.map((session) => (
            <div
              key={session.id}
              className="bg-surface-secondary border border-border-default rounded-xl p-5 hover:border-navy-500 transition-colors cursor-pointer"
            >
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-navy-700 flex items-center justify-center text-xs text-text-muted">
                    {session.user.slice(5, 7).toUpperCase()}
                  </div>
                  <div>
                    <div className="text-sm font-medium text-text-primary">{session.user}</div>
                    <div className="text-xs text-text-muted">
                      {session.device} &middot; {session.country}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <FrustrationBadge level={session.frustration} />
                  <span className="text-xs text-text-muted">{session.timestamp}</span>
                </div>
              </div>
              <div className="flex items-center gap-6 text-xs text-text-muted">
                <span>Duration: <span className="text-text-secondary">{session.duration}</span></span>
                <span>Pages: <span className="text-text-secondary">{session.pages}</span></span>
                <span>
                  Errors:{" "}
                  <span className={session.errors > 0 ? "text-red-400" : "text-text-secondary"}>
                    {session.errors}
                  </span>
                </span>
              </div>
              <div className="mt-3 flex items-center gap-2">
                <div className="flex-1 h-1.5 bg-navy-700 rounded-full overflow-hidden">
                  {/* Session timeline visualization */}
                  <div className="h-full flex">
                    <div className="bg-blue-500 h-full" style={{ width: "30%" }} />
                    <div className="bg-blue-400 h-full" style={{ width: "15%" }} />
                    {session.errors > 0 && <div className="bg-red-500 h-full" style={{ width: "5%" }} />}
                    <div className="bg-blue-500 h-full" style={{ width: "25%" }} />
                    <div className="bg-blue-400 h-full" style={{ width: "25%" }} />
                  </div>
                </div>
                <button className="px-3 py-1 text-xs font-medium bg-navy-700 hover:bg-navy-600 text-text-secondary rounded transition-colors">
                  Replay
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Impact Analysis Section */}
      {activeSection === "impact" && (
        <div className="space-y-6">
          <div className="bg-surface-secondary border border-border-default rounded-xl p-6">
            <h3 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-2">
              Backend-to-Frontend Impact Correlation
            </h3>
            <p className="text-xs text-text-muted mb-6">
              Correlating backend service degradation with frontend user experience metrics.
            </p>

            <div className="space-y-4">
              {mockImpactAnalysis.map((item) => (
                <div
                  key={item.service}
                  className="bg-navy-950 border border-border-default rounded-xl p-5"
                >
                  <div className="flex items-start justify-between mb-4">
                    <div>
                      <div className="text-sm font-semibold text-text-primary">{item.service}</div>
                      <div className="text-xs text-text-muted mt-1">{item.frontendImpact}</div>
                    </div>
                    <span className="px-2.5 py-1 text-xs font-medium bg-red-500/20 text-red-400 border border-red-500/30 rounded">
                      {item.affectedUsers.toLocaleString()} users affected
                    </span>
                  </div>

                  <div className="grid grid-cols-3 gap-4">
                    <div>
                      <div className="text-xs text-text-muted mb-1">P99 Latency</div>
                      <div className={cn(
                        "text-lg font-bold",
                        item.p99Latency > 500 ? "text-red-400" : item.p99Latency > 200 ? "text-amber-400" : "text-emerald-400",
                      )}>
                        {item.p99Latency}ms
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-text-muted mb-1">Error Rate</div>
                      <div className={cn(
                        "text-lg font-bold",
                        item.errorRate > 2 ? "text-red-400" : item.errorRate > 1 ? "text-amber-400" : "text-emerald-400",
                      )}>
                        {item.errorRate}%
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-text-muted mb-1">Affected Users</div>
                      <div className="text-lg font-bold text-text-primary">{item.affectedUsers.toLocaleString()}</div>
                    </div>
                  </div>

                  {/* Correlation visualization */}
                  <div className="mt-4 pt-3 border-t border-border-default">
                    <div className="flex items-center gap-2 text-xs">
                      <span className="text-text-muted">Backend</span>
                      <div className="flex-1 h-2 bg-navy-700 rounded-full overflow-hidden">
                        <div
                          className={cn(
                            "h-full rounded-full",
                            item.errorRate > 2 ? "bg-red-500" : "bg-amber-500",
                          )}
                          style={{ width: `${Math.min(100, item.p99Latency / 15)}%` }}
                        />
                      </div>
                      <svg className="w-4 h-4 text-text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
                      </svg>
                      <div className="flex-1 h-2 bg-navy-700 rounded-full overflow-hidden">
                        <div
                          className={cn(
                            "h-full rounded-full",
                            item.affectedUsers > 500 ? "bg-red-500" : "bg-amber-500",
                          )}
                          style={{ width: `${Math.min(100, item.affectedUsers / 15)}%` }}
                        />
                      </div>
                      <span className="text-text-muted">Frontend</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Recommendations */}
          <div className="bg-surface-secondary border border-border-default rounded-xl p-6">
            <h3 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-4">
              Recommended Actions
            </h3>
            <div className="space-y-3">
              <div className="flex items-start gap-3 p-3 bg-red-500/5 border border-red-500/20 rounded-xl">
                <span className="w-6 h-6 rounded-full bg-red-500/20 text-red-400 text-xs flex items-center justify-center flex-shrink-0 mt-0.5">
                  1
                </span>
                <div>
                  <div className="text-sm font-medium text-text-primary">Investigate payment-gateway latency</div>
                  <div className="text-xs text-text-muted mt-0.5">
                    P99 latency at 1200ms is causing checkout abandonment. Check database connection pool and external API dependencies.
                  </div>
                </div>
              </div>
              <div className="flex items-start gap-3 p-3 bg-amber-500/5 border border-amber-500/20 rounded-xl">
                <span className="w-6 h-6 rounded-full bg-amber-500/20 text-amber-400 text-xs flex items-center justify-center flex-shrink-0 mt-0.5">
                  2
                </span>
                <div>
                  <div className="text-sm font-medium text-text-primary">Optimize /products page LCP</div>
                  <div className="text-xs text-text-muted mt-0.5">
                    Real user LCP is 50% higher than synthetic. Investigate third-party scripts and image loading on slow connections.
                  </div>
                </div>
              </div>
              <div className="flex items-start gap-3 p-3 bg-blue-500/5 border border-blue-500/20 rounded-xl">
                <span className="w-6 h-6 rounded-full bg-blue-500/20 text-accent-blue text-xs flex items-center justify-center flex-shrink-0 mt-0.5">
                  3
                </span>
                <div>
                  <div className="text-sm font-medium text-text-primary">Reduce Product View to Cart drop-off</div>
                  <div className="text-xs text-text-muted mt-0.5">
                    55.4% drop-off at Add to Cart step. Correlates with slow product-api responses. Consider edge caching for product data.
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
