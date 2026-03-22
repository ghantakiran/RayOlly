"use client";

import { useState, useEffect } from "react";
import { getAgentObsDashboard } from "@/lib/api";
import {
  Activity,
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  BarChart3,
  Beaker,
  Bot,
  BrainCircuit,
  CheckCircle2,
  Clock,
  DollarSign,
  Eye,
  FlaskConical,
  Gauge,
  Lightbulb,
  Search,
  Shield,
  ShieldAlert,
  Target,
  ThumbsDown,
  ThumbsUp,
  Timer,
  TrendingDown,
  TrendingUp,
  XCircle,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ── Types ───────────────────────────────────────────────────────────

interface AgentMetric {
  agentType: string;
  label: string;
  executions: number;
  successRate: number;
  avgDuration: string;
  avgCost: string;
  satisfaction: number;
  trend: "up" | "down" | "flat";
  color: string;
}

interface CostEntry {
  agentType: string;
  label: string;
  cost: number;
  pct: number;
  color: string;
}

interface ToolUsage {
  name: string;
  invocations: number;
  avgLatency: string;
  errorRate: number;
}

interface RecentFailure {
  id: string;
  agentType: string;
  error: string;
  timestamp: string;
}

interface SatisfactionPoint {
  label: string;
  up: number;
  down: number;
  pct: number;
}

interface TimelinePoint {
  label: string;
  rca: number;
  query: number;
  incident: number;
  anomaly: number;
}

interface WaterfallSpan {
  id: string;
  parentId: string;
  name: string;
  type: "thinking" | "llm_call" | "tool_call" | "tool_result" | "planning" | "response";
  startMs: number;
  durationMs: number;
  tokens: number;
  cost: number;
  error?: string;
}

interface AccuracyDataPoint {
  date: string;
  accuracy: number;
  executions: number;
  hallucinations: number;
}

interface HallucinationEntry {
  id: string;
  agentType: string;
  claimText: string;
  severity: "minor" | "moderate" | "critical";
  timestamp: string;
  accuracy: number;
}

interface CostForecastData {
  dailyAvg: number;
  projectedMonthly: number;
  trend: "increasing" | "stable" | "decreasing";
  trendPct: number;
  confidence: number;
}

interface BudgetData {
  dailyBudget: number;
  spentToday: number;
  remaining: number;
  onTrack: boolean;
  projectedOverage: number;
}

interface CostSuggestionData {
  suggestion: string;
  savingsPct: number;
  effort: "low" | "medium" | "high";
  details: string;
}

interface ABExperimentData {
  id: string;
  name: string;
  agentType: string;
  status: "running" | "concluded" | "paused";
  successMetric: string;
  variantA: { description: string; model: string; successRate: number; avgDuration: number; avgCost: number; samples: number };
  variantB: { description: string; model: string; successRate: number; avgDuration: number; avgCost: number; samples: number };
  winner: string | null;
  confidence: number;
  isSignificant: boolean;
}

interface AgentSLOData {
  id: string;
  name: string;
  agentType: string;
  sliType: string;
  target: number;
  currentValue: number;
  isMeeting: boolean;
  errorBudgetRemainingPct: number;
  burnRate1h: number;
  burnRate6h: number;
  trend: "improving" | "stable" | "degrading";
}

// ── Tab definitions ─────────────────────────────────────────────────

const tabs = [
  { id: "overview", label: "Overview", icon: Activity },
  { id: "traces", label: "Execution Traces", icon: Timer },
  { id: "accuracy", label: "Accuracy & Hallucinations", icon: BrainCircuit },
  { id: "costs", label: "Cost Management", icon: DollarSign },
  { id: "ab-testing", label: "A/B Testing", icon: FlaskConical },
  { id: "slos", label: "Agent SLOs", icon: Target },
] as const;

type TabId = (typeof tabs)[number]["id"];

// ── Mock Data ───────────────────────────────────────────────────────

const overviewCards = [
  { label: "Total Executions", value: "1,847", change: "+12%", icon: Activity, color: "text-cyan-400", bgColor: "bg-cyan-500/10" },
  { label: "Success Rate", value: "94.2%", change: "+1.3%", icon: CheckCircle2, color: "text-severity-ok", bgColor: "bg-severity-ok/10" },
  { label: "Avg Duration", value: "8.4s", change: "-0.6s", icon: Clock, color: "text-accent-indigo", bgColor: "bg-accent-indigo/10" },
  { label: "Total Cost (Today)", value: "$42.18", change: "+$3.20", icon: DollarSign, color: "text-severity-warning", bgColor: "bg-severity-warning/10" },
];

const agentMetrics: AgentMetric[] = [
  { agentType: "rca", label: "Root Cause Analysis", executions: 342, successRate: 91.5, avgDuration: "14.2s", avgCost: "$0.048", satisfaction: 88, trend: "up", color: "text-cyan-400" },
  { agentType: "query", label: "Query Assistant", executions: 1024, successRate: 97.8, avgDuration: "3.1s", avgCost: "$0.012", satisfaction: 94, trend: "up", color: "text-accent-indigo" },
  { agentType: "incident", label: "Incident Manager", executions: 187, successRate: 89.3, avgDuration: "22.7s", avgCost: "$0.082", satisfaction: 85, trend: "down", color: "text-severity-error" },
  { agentType: "anomaly", label: "Anomaly Detection", executions: 294, successRate: 96.2, avgDuration: "6.8s", avgCost: "$0.028", satisfaction: 91, trend: "flat", color: "text-severity-warning" },
];

const costBreakdown: CostEntry[] = [
  { agentType: "incident", label: "Incident Manager", cost: 15.33, pct: 36.3, color: "bg-severity-error" },
  { agentType: "rca", label: "Root Cause Analysis", cost: 12.42, pct: 29.5, color: "bg-cyan-500" },
  { agentType: "anomaly", label: "Anomaly Detection", cost: 8.23, pct: 19.5, color: "bg-severity-warning" },
  { agentType: "query", label: "Query Assistant", cost: 6.20, pct: 14.7, color: "bg-accent-indigo" },
];

const executionTimeline: TimelinePoint[] = [
  { label: "00:00", rca: 8, query: 32, incident: 4, anomaly: 10 },
  { label: "03:00", rca: 3, query: 12, incident: 2, anomaly: 8 },
  { label: "06:00", rca: 6, query: 28, incident: 5, anomaly: 11 },
  { label: "09:00", rca: 22, query: 68, incident: 12, anomaly: 18 },
  { label: "12:00", rca: 28, query: 82, incident: 15, anomaly: 22 },
  { label: "15:00", rca: 24, query: 76, incident: 14, anomaly: 20 },
  { label: "18:00", rca: 18, query: 64, incident: 10, anomaly: 16 },
  { label: "21:00", rca: 14, query: 48, incident: 8, anomaly: 14 },
];

const toolUsageData: ToolUsage[] = [
  { name: "query_logs", invocations: 2840, avgLatency: "1.2s", errorRate: 0.8 },
  { name: "query_metrics", invocations: 2210, avgLatency: "0.9s", errorRate: 0.3 },
  { name: "search_traces", invocations: 1540, avgLatency: "2.1s", errorRate: 1.2 },
  { name: "get_service_map", invocations: 890, avgLatency: "3.4s", errorRate: 0.5 },
  { name: "create_timeline", invocations: 620, avgLatency: "0.4s", errorRate: 0.0 },
  { name: "run_sql", invocations: 510, avgLatency: "1.8s", errorRate: 2.1 },
  { name: "get_alert_context", invocations: 380, avgLatency: "0.6s", errorRate: 0.2 },
  { name: "notify_channel", invocations: 240, avgLatency: "0.8s", errorRate: 3.4 },
];

const recentFailures: RecentFailure[] = [
  { id: "exec-f1", agentType: "incident", error: "Execution timed out after 300s: tool get_service_map did not respond", timestamp: "14m ago" },
  { id: "exec-f2", agentType: "rca", error: "Rate limit exceeded (429) from Anthropic API. Retry after 12s.", timestamp: "28m ago" },
  { id: "exec-f3", agentType: "rca", error: "Tool search_traces returned connection error: upstream timeout", timestamp: "47m ago" },
  { id: "exec-f4", agentType: "incident", error: "Execution cancelled by user", timestamp: "1h ago" },
  { id: "exec-f5", agentType: "anomaly", error: "Context window exceeded: 204,812 tokens > 200,000 limit", timestamp: "2h ago" },
];

const satisfactionTrend: SatisfactionPoint[] = [
  { label: "Mon", up: 142, down: 12, pct: 92.2 },
  { label: "Tue", up: 168, down: 14, pct: 92.3 },
  { label: "Wed", up: 155, down: 10, pct: 93.9 },
  { label: "Thu", up: 181, down: 18, pct: 90.9 },
  { label: "Fri", up: 192, down: 11, pct: 94.6 },
  { label: "Sat", up: 88, down: 6, pct: 93.6 },
  { label: "Sun", up: 72, down: 5, pct: 93.5 },
];

// -- Waterfall mock data --
const waterfallSpans: WaterfallSpan[] = [
  { id: "s1", parentId: "", name: "Planning", type: "planning", startMs: 0, durationMs: 420, tokens: 312, cost: 0.0009 },
  { id: "s2", parentId: "", name: "Thinking: analyze error pattern", type: "thinking", startMs: 420, durationMs: 680, tokens: 524, cost: 0.0016 },
  { id: "s3", parentId: "", name: "LLM Call: generate query", type: "llm_call", startMs: 1100, durationMs: 1240, tokens: 1842, cost: 0.0055 },
  { id: "s4", parentId: "", name: "Tool: query_logs", type: "tool_call", startMs: 2340, durationMs: 2180, tokens: 0, cost: 0.0 },
  { id: "s5", parentId: "s4", name: "Tool Result: 847 log lines", type: "tool_result", startMs: 4520, durationMs: 120, tokens: 3240, cost: 0.0 },
  { id: "s6", parentId: "", name: "Thinking: correlate logs with metrics", type: "thinking", startMs: 4640, durationMs: 920, tokens: 1124, cost: 0.0034 },
  { id: "s7", parentId: "", name: "Tool: query_metrics", type: "tool_call", startMs: 5560, durationMs: 1640, tokens: 0, cost: 0.0 },
  { id: "s8", parentId: "s7", name: "Tool Result: p99 latency spike", type: "tool_result", startMs: 7200, durationMs: 80, tokens: 1820, cost: 0.0 },
  { id: "s9", parentId: "", name: "Thinking: identify root cause", type: "thinking", startMs: 7280, durationMs: 1340, tokens: 2148, cost: 0.0064 },
  { id: "s10", parentId: "", name: "Response: root cause analysis", type: "response", startMs: 8620, durationMs: 1880, tokens: 3420, cost: 0.0103 },
];

const totalWaterfallMs = Math.max(...waterfallSpans.map((s) => s.startMs + s.durationMs));
const totalWaterfallTokens = waterfallSpans.reduce((a, s) => a + s.tokens, 0);
const totalWaterfallCost = waterfallSpans.reduce((a, s) => a + s.cost, 0);

// -- Accuracy mock data --
const accuracyTrend: AccuracyDataPoint[] = [
  { date: "Mar 5", accuracy: 94.2, executions: 48, hallucinations: 3 },
  { date: "Mar 6", accuracy: 95.1, executions: 62, hallucinations: 2 },
  { date: "Mar 7", accuracy: 93.8, executions: 55, hallucinations: 4 },
  { date: "Mar 8", accuracy: 96.3, executions: 71, hallucinations: 1 },
  { date: "Mar 9", accuracy: 95.7, executions: 68, hallucinations: 2 },
  { date: "Mar 10", accuracy: 97.1, executions: 44, hallucinations: 0 },
  { date: "Mar 11", accuracy: 96.8, executions: 52, hallucinations: 1 },
  { date: "Mar 12", accuracy: 94.5, executions: 78, hallucinations: 5 },
  { date: "Mar 13", accuracy: 95.9, executions: 65, hallucinations: 2 },
  { date: "Mar 14", accuracy: 97.4, executions: 59, hallucinations: 0 },
];

const hallucinations: HallucinationEntry[] = [
  { id: "h1", agentType: "rca", claimText: "Error rate was 12.4% (actual: 8.1%)", severity: "moderate", timestamp: "2h ago", accuracy: 87.2 },
  { id: "h2", agentType: "incident", claimText: "Service payment-api was down for 47 minutes (actual: 23 minutes)", severity: "critical", timestamp: "5h ago", accuracy: 72.1 },
  { id: "h3", agentType: "query", claimText: "P99 latency was 340ms (actual: 328ms)", severity: "minor", timestamp: "8h ago", accuracy: 96.5 },
  { id: "h4", agentType: "rca", claimText: "Database connection pool exhausted at 14:22 (actual: 14:18)", severity: "minor", timestamp: "1d ago", accuracy: 98.1 },
  { id: "h5", agentType: "incident", claimText: "3,200 users affected (actual: 1,847 based on session data)", severity: "critical", timestamp: "1d ago", accuracy: 57.7 },
];

// -- Cost management mock data --
const costForecast: CostForecastData = {
  dailyAvg: 42.18,
  projectedMonthly: 1265.40,
  trend: "increasing",
  trendPct: 8.4,
  confidence: 0.87,
};

const budgetData: BudgetData = {
  dailyBudget: 75.00,
  spentToday: 42.18,
  remaining: 32.82,
  onTrack: true,
  projectedOverage: 0,
};

const costSuggestions: CostSuggestionData[] = [
  { suggestion: "Switch Incident Manager to Haiku for triage classification", savingsPct: 68, effort: "low", details: "Incident triage uses only ~800 tokens avg. Haiku handles classification at 10x lower cost with minimal accuracy loss." },
  { suggestion: "Reduce RCA agent max iterations from 12 to 8", savingsPct: 25, effort: "low", details: "92% of RCA investigations complete within 8 iterations. Capping saves ~$3.10/day on runaway executions." },
  { suggestion: "Enable 5-min response cache for Query Assistant", savingsPct: 18, effort: "medium", details: "34% of query assistant requests are near-duplicates. Caching tool results for 5 min saves ~$1.12/day." },
  { suggestion: "Fix search_traces timeout to reduce failed retries", savingsPct: 12, effort: "medium", details: "search_traces failures cost $1.84/day in wasted tokens from failed executions that are retried." },
];

// -- A/B Testing mock data --
const experiments: ABExperimentData[] = [
  {
    id: "exp-001", name: "RCA Prompt v2 vs v1", agentType: "rca", status: "running",
    successMetric: "accuracy",
    variantA: { description: "Current production prompt (v1)", model: "claude-sonnet-4-20250514", successRate: 91.5, avgDuration: 14200, avgCost: 0.048, samples: 171 },
    variantB: { description: "Chain-of-thought prompt with structured output (v2)", model: "claude-sonnet-4-20250514", successRate: 94.8, avgDuration: 16100, avgCost: 0.052, samples: 164 },
    winner: null, confidence: 0.89, isSignificant: false,
  },
  {
    id: "exp-002", name: "Query Agent: Sonnet vs Haiku", agentType: "query", status: "concluded",
    successMetric: "cost",
    variantA: { description: "Claude Sonnet (current)", model: "claude-sonnet-4-20250514", successRate: 97.8, avgDuration: 3100, avgCost: 0.012, samples: 512 },
    variantB: { description: "Claude Haiku (cheaper)", model: "claude-haiku", successRate: 96.1, avgDuration: 2200, avgCost: 0.002, samples: 508 },
    winner: "B", confidence: 0.97, isSignificant: true,
  },
  {
    id: "exp-003", name: "Incident Agent: Tool Set Comparison", agentType: "incident", status: "running",
    successMetric: "speed",
    variantA: { description: "Full toolset (8 tools)", model: "claude-sonnet-4-20250514", successRate: 89.3, avgDuration: 22700, avgCost: 0.082, samples: 94 },
    variantB: { description: "Streamlined toolset (5 tools)", model: "claude-sonnet-4-20250514", successRate: 87.1, avgDuration: 15400, avgCost: 0.061, samples: 88 },
    winner: null, confidence: 0.72, isSignificant: false,
  },
];

// -- SLO mock data --
const sloData: AgentSLOData[] = [
  { id: "slo-1", name: "RCA Success Rate", agentType: "rca", sliType: "success_rate", target: 0.90, currentValue: 0.915, isMeeting: true, errorBudgetRemainingPct: 68.2, burnRate1h: 0.8, burnRate6h: 1.1, trend: "stable" },
  { id: "slo-2", name: "Query Latency P95", agentType: "query", sliType: "latency_p95", target: 10000, currentValue: 6200, isMeeting: true, errorBudgetRemainingPct: 84.5, burnRate1h: 0.3, burnRate6h: 0.5, trend: "improving" },
  { id: "slo-3", name: "Incident Success Rate", agentType: "incident", sliType: "success_rate", target: 0.90, currentValue: 0.893, isMeeting: false, errorBudgetRemainingPct: 12.4, burnRate1h: 6.2, burnRate6h: 3.8, trend: "degrading" },
  { id: "slo-4", name: "Overall Agent Accuracy", agentType: "all", sliType: "accuracy", target: 0.95, currentValue: 0.957, isMeeting: true, errorBudgetRemainingPct: 71.8, burnRate1h: 0.6, burnRate6h: 0.9, trend: "improving" },
  { id: "slo-5", name: "RCA Cost Per Execution", agentType: "rca", sliType: "cost_per_execution", target: 0.06, currentValue: 0.048, isMeeting: true, errorBudgetRemainingPct: 92.1, burnRate1h: 0.2, burnRate6h: 0.4, trend: "stable" },
];

// ── Helpers ─────────────────────────────────────────────────────────

const maxTimeline = Math.max(
  ...executionTimeline.map((p) => p.rca + p.query + p.incident + p.anomaly)
);

const spanTypeColors: Record<string, { bg: string; text: string; border: string }> = {
  planning: { bg: "bg-purple-500/20", text: "text-purple-400", border: "border-purple-500/40" },
  thinking: { bg: "bg-cyan-500/20", text: "text-cyan-400", border: "border-cyan-500/40" },
  llm_call: { bg: "bg-accent-indigo/20", text: "text-accent-indigo", border: "border-accent-indigo/40" },
  tool_call: { bg: "bg-severity-warning/20", text: "text-severity-warning", border: "border-severity-warning/40" },
  tool_result: { bg: "bg-severity-ok/20", text: "text-severity-ok", border: "border-severity-ok/40" },
  response: { bg: "bg-pink-500/20", text: "text-pink-400", border: "border-pink-500/40" },
};

const severityBadge: Record<string, string> = {
  minor: "bg-severity-warning/10 text-severity-warning border-severity-warning/30",
  moderate: "bg-orange-500/10 text-orange-400 border-orange-500/30",
  critical: "bg-severity-error/10 text-severity-error border-severity-error/30",
};

const effortBadge: Record<string, string> = {
  low: "bg-severity-ok/10 text-severity-ok",
  medium: "bg-severity-warning/10 text-severity-warning",
  high: "bg-severity-error/10 text-severity-error",
};

function formatSliValue(sliType: string, value: number): string {
  if (sliType === "success_rate" || sliType === "accuracy") return `${(value * 100).toFixed(1)}%`;
  if (sliType === "latency_p95") return `${(value / 1000).toFixed(1)}s`;
  if (sliType === "cost_per_execution") return `$${value.toFixed(3)}`;
  return String(value);
}

function formatSliTarget(sliType: string, target: number): string {
  if (sliType === "success_rate" || sliType === "accuracy") return `${(target * 100).toFixed(0)}%`;
  if (sliType === "latency_p95") return `${(target / 1000).toFixed(0)}s`;
  if (sliType === "cost_per_execution") return `$${target.toFixed(3)}`;
  return String(target);
}

// ── Component ───────────────────────────────────────────────────────

export default function AgentObservabilityPage() {
  const [timeRange, setTimeRange] = useState("24h");
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const [dashboardData, setDashboardData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [hasRealData, setHasRealData] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getAgentObsDashboard()
      .then((data: any) => {
        if (cancelled) return;
        const hasData = data && Object.keys(data).length > 0 && !data.error;
        setDashboardData(hasData ? data : null);
        setHasRealData(hasData);
      })
      .catch(() => {
        if (!cancelled) {
          setDashboardData(null);
          setHasRealData(false);
        }
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-text-primary">
            Agent Observability
          </h1>
          <p className="mt-0.5 text-sm text-text-muted">
            Monitor AI agent performance, costs, accuracy, and reliability
          </p>
        </div>
        <div className="flex items-center gap-2">
          {["1h", "6h", "24h", "7d", "30d"].map((range) => (
            <button
              key={range}
              onClick={() => setTimeRange(range)}
              className={cn(
                "rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
                timeRange === range
                  ? "bg-cyan-500/15 text-cyan-400"
                  : "text-text-muted hover:text-text-secondary hover:bg-navy-700"
              )}
            >
              {range}
            </button>
          ))}
        </div>
      </div>

      {/* Loading state */}
      {loading && (
        <div className="flex items-center justify-center py-20">
          <div className="flex items-center gap-3 text-text-muted">
            <svg className="h-5 w-5 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <span className="text-sm">Loading agent observability data...</span>
          </div>
        </div>
      )}

      {!loading && (
        <>
          {/* Tab bar */}
          <div className="flex items-center gap-1 rounded-xl border border-border-default/60 bg-surface-secondary p-1">
            {tabs.map((tab) => {
              const isComingSoon = !hasRealData && tab.id !== "overview";
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={cn(
                    "flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-medium transition-all",
                    activeTab === tab.id
                      ? "bg-cyan-500/15 text-cyan-400 shadow-sm shadow-cyan-500/10"
                      : "text-text-muted hover:text-text-secondary hover:bg-navy-700/50"
                  )}
                >
                  <tab.icon className="h-3.5 w-3.5" />
                  {tab.label}
                  {isComingSoon && (
                    <span className="rounded-full bg-navy-700 px-1.5 py-0.5 text-[9px] text-text-muted">
                      Coming Soon
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {/* Tab content */}
          {activeTab === "overview" && <OverviewTab dashboardData={dashboardData} hasRealData={hasRealData} />}
          {activeTab === "traces" && <TracesTab />}
          {activeTab === "accuracy" && <AccuracyTab />}
          {activeTab === "costs" && <CostsTab />}
          {activeTab === "ab-testing" && <ABTestingTab />}
          {activeTab === "slos" && <SLOsTab />}
        </>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════
// TAB 1: Overview (existing dashboard)
// ══════════════════════════════════════════════════════════════════════

function OverviewTab({ dashboardData, hasRealData }: { dashboardData: any; hasRealData: boolean }) {
  if (!hasRealData) {
    return (
      <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-12 text-center">
        <Activity className="mx-auto h-12 w-12 text-text-muted/40" />
        <h3 className="mt-4 text-lg font-medium text-text-primary">No agent executions yet</h3>
        <p className="mt-2 text-sm text-text-muted max-w-md mx-auto">
          Start using AI agents (Root Cause Analysis, Query Assistant, Incident Manager, or Anomaly Detection) to see observability data here.
        </p>
        <p className="mt-4 text-xs text-text-muted">
          The overview below shows example data to preview the dashboard layout.
        </p>
      </div>
    );
  }

  return (
    <>
      {/* Overview cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {overviewCards.map((card) => (
          <div
            key={card.label}
            className="rounded-xl border border-border-default/60 bg-surface-secondary p-5"
          >
            <div className="flex items-center justify-between">
              <div className={cn("flex h-10 w-10 items-center justify-center rounded-xl", card.bgColor)}>
                <card.icon className={cn("h-5 w-5", card.color)} />
              </div>
              <span className={cn(
                "text-xs font-medium",
                card.change.startsWith("+") ? "text-severity-ok" : "text-cyan-400"
              )}>
                {card.change}
              </span>
            </div>
            <p className="mt-3 text-2xl font-semibold text-text-primary">{card.value}</p>
            <p className="mt-0.5 text-xs text-text-muted">{card.label}</p>
          </div>
        ))}
      </div>

      {/* Agent performance table */}
      <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-4">
        <h3 className="mb-4 flex items-center gap-2 text-sm font-medium text-text-secondary">
          <Bot className="h-4 w-4 text-cyan-400" />
          Agent Performance
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-border-default text-xs text-text-muted">
                <th className="pb-3 pr-4 font-medium">Agent</th>
                <th className="pb-3 pr-4 font-medium text-right">Executions</th>
                <th className="pb-3 pr-4 font-medium text-right">Success Rate</th>
                <th className="pb-3 pr-4 font-medium text-right">Avg Duration</th>
                <th className="pb-3 pr-4 font-medium text-right">Avg Cost</th>
                <th className="pb-3 pr-4 font-medium text-right">Satisfaction</th>
                <th className="pb-3 font-medium text-right">Trend</th>
              </tr>
            </thead>
            <tbody className="text-text-primary">
              {agentMetrics.map((agent) => (
                <tr
                  key={agent.agentType}
                  className="border-b border-border-default/50 last:border-0"
                >
                  <td className="py-3 pr-4">
                    <span className={cn("font-medium", agent.color)}>
                      {agent.label}
                    </span>
                  </td>
                  <td className="py-3 pr-4 text-right font-mono text-xs">
                    {agent.executions.toLocaleString()}
                  </td>
                  <td className="py-3 pr-4 text-right">
                    <span className={cn(
                      "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
                      agent.successRate >= 95
                        ? "bg-severity-ok/10 text-severity-ok"
                        : agent.successRate >= 90
                        ? "bg-severity-warning/10 text-severity-warning"
                        : "bg-severity-error/10 text-severity-error"
                    )}>
                      {agent.successRate}%
                    </span>
                  </td>
                  <td className="py-3 pr-4 text-right font-mono text-xs text-text-secondary">
                    {agent.avgDuration}
                  </td>
                  <td className="py-3 pr-4 text-right font-mono text-xs text-text-secondary">
                    {agent.avgCost}
                  </td>
                  <td className="py-3 pr-4 text-right">
                    <div className="flex items-center justify-end gap-1.5">
                      <ThumbsUp className="h-3 w-3 text-severity-ok" />
                      <span className="text-xs text-text-secondary">{agent.satisfaction}%</span>
                    </div>
                  </td>
                  <td className="py-3 text-right">
                    {agent.trend === "up" && <ArrowUp className="ml-auto h-4 w-4 text-severity-ok" />}
                    {agent.trend === "down" && <ArrowDown className="ml-auto h-4 w-4 text-severity-error" />}
                    {agent.trend === "flat" && <span className="ml-auto block h-0.5 w-4 rounded bg-text-muted" />}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        {/* Cost breakdown bar chart */}
        <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-4">
          <h3 className="mb-4 flex items-center gap-2 text-sm font-medium text-text-secondary">
            <DollarSign className="h-4 w-4 text-severity-warning" />
            Cost Breakdown by Agent
          </h3>
          <div className="space-y-3">
            {costBreakdown.map((entry) => (
              <div key={entry.agentType}>
                <div className="mb-1 flex items-center justify-between text-xs">
                  <span className="text-text-secondary">{entry.label}</span>
                  <span className="font-mono text-text-primary">${entry.cost.toFixed(2)}</span>
                </div>
                <div className="h-2.5 w-full rounded-full bg-navy-800">
                  <div
                    className={cn("h-2.5 rounded-full transition-all", entry.color)}
                    style={{ width: `${entry.pct}%` }}
                  />
                </div>
                <div className="mt-0.5 text-right text-[10px] text-text-muted">
                  {entry.pct}%
                </div>
              </div>
            ))}
            <div className="mt-2 flex items-center justify-between border-t border-border-default pt-2">
              <span className="text-xs font-medium text-text-secondary">Total</span>
              <span className="font-mono text-sm font-semibold text-text-primary">
                ${costBreakdown.reduce((a, b) => a + b.cost, 0).toFixed(2)}
              </span>
            </div>
          </div>
        </div>

        {/* Execution timeline chart */}
        <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-4">
          <h3 className="mb-4 flex items-center gap-2 text-sm font-medium text-text-secondary">
            <BarChart3 className="h-4 w-4 text-accent-indigo" />
            Execution Timeline (Today)
          </h3>
          <div className="flex items-end gap-2" style={{ height: 180 }}>
            {executionTimeline.map((point) => {
              const total = point.rca + point.query + point.incident + point.anomaly;
              const scale = maxTimeline > 0 ? 160 / maxTimeline : 1;
              return (
                <div key={point.label} className="flex flex-1 flex-col items-center gap-1">
                  <div className="flex w-full flex-col items-center">
                    <div
                      className="w-full rounded-t bg-severity-warning/80"
                      style={{ height: point.anomaly * scale }}
                    />
                    <div
                      className="w-full bg-severity-error/80"
                      style={{ height: point.incident * scale }}
                    />
                    <div
                      className="w-full bg-accent-indigo/80"
                      style={{ height: point.query * scale }}
                    />
                    <div
                      className="w-full rounded-b bg-cyan-500/80"
                      style={{ height: point.rca * scale }}
                    />
                  </div>
                  <span className="text-[10px] text-text-muted">{point.label}</span>
                </div>
              );
            })}
          </div>
          <div className="mt-3 flex items-center justify-center gap-4">
            <Legend color="bg-cyan-500/80" label="RCA" />
            <Legend color="bg-accent-indigo/80" label="Query" />
            <Legend color="bg-severity-error/80" label="Incident" />
            <Legend color="bg-severity-warning/80" label="Anomaly" />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        {/* Tool usage table */}
        <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-4">
          <h3 className="mb-4 flex items-center gap-2 text-sm font-medium text-text-secondary">
            <Zap className="h-4 w-4 text-cyan-400" />
            Tool Usage
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-border-default text-xs text-text-muted">
                  <th className="pb-2 pr-4 font-medium">Tool</th>
                  <th className="pb-2 pr-4 font-medium text-right">Invocations</th>
                  <th className="pb-2 pr-4 font-medium text-right">Avg Latency</th>
                  <th className="pb-2 font-medium text-right">Error Rate</th>
                </tr>
              </thead>
              <tbody>
                {toolUsageData.map((tool) => (
                  <tr
                    key={tool.name}
                    className="border-b border-border-default/30 last:border-0"
                  >
                    <td className="py-2 pr-4 font-mono text-xs text-text-primary">
                      {tool.name}
                    </td>
                    <td className="py-2 pr-4 text-right font-mono text-xs text-text-secondary">
                      {tool.invocations.toLocaleString()}
                    </td>
                    <td className="py-2 pr-4 text-right font-mono text-xs text-text-secondary">
                      {tool.avgLatency}
                    </td>
                    <td className="py-2 text-right">
                      <span className={cn(
                        "text-xs font-medium",
                        tool.errorRate === 0
                          ? "text-severity-ok"
                          : tool.errorRate < 2
                          ? "text-severity-warning"
                          : "text-severity-error"
                      )}>
                        {tool.errorRate}%
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Recent failures */}
        <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-4">
          <h3 className="mb-4 flex items-center gap-2 text-sm font-medium text-text-secondary">
            <AlertTriangle className="h-4 w-4 text-severity-error" />
            Recent Failures
          </h3>
          <div className="space-y-2 max-h-[340px] overflow-y-auto">
            {recentFailures.map((failure) => (
              <div
                key={failure.id}
                className="rounded-lg bg-navy-800/50 p-3"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <XCircle className="h-3.5 w-3.5 text-severity-error" />
                    <span className="text-xs font-medium text-text-primary">
                      {failure.agentType}
                    </span>
                  </div>
                  <span className="text-[10px] text-text-muted">{failure.timestamp}</span>
                </div>
                <p className="mt-1.5 rounded bg-severity-error/5 px-2 py-1.5 text-xs text-severity-error/90 leading-relaxed">
                  {failure.error}
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Satisfaction trend */}
      <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-4">
        <h3 className="mb-4 flex items-center gap-2 text-sm font-medium text-text-secondary">
          <ThumbsUp className="h-4 w-4 text-severity-ok" />
          User Satisfaction Trend (7d)
        </h3>
        <div className="flex items-end gap-3" style={{ height: 140 }}>
          {satisfactionTrend.map((point) => {
            const total = point.up + point.down;
            const barHeight = Math.max(20, (total / 210) * 120);
            const upHeight = (point.up / total) * barHeight;
            const downHeight = barHeight - upHeight;
            return (
              <div key={point.label} className="flex flex-1 flex-col items-center gap-1">
                <span className="text-[10px] font-medium text-severity-ok">
                  {point.pct.toFixed(1)}%
                </span>
                <div className="flex w-full flex-col items-center">
                  <div
                    className="w-full rounded-t bg-severity-ok/70"
                    style={{ height: upHeight }}
                  />
                  <div
                    className="w-full rounded-b bg-severity-error/50"
                    style={{ height: downHeight }}
                  />
                </div>
                <span className="text-[10px] text-text-muted">{point.label}</span>
              </div>
            );
          })}
        </div>
        <div className="mt-3 flex items-center justify-center gap-4">
          <Legend color="bg-severity-ok/70" label="Thumbs Up" />
          <Legend color="bg-severity-error/50" label="Thumbs Down" />
        </div>
      </div>
    </>
  );
}

// ══════════════════════════════════════════════════════════════════════
// TAB 2: Execution Traces (Waterfall View)
// ══════════════════════════════════════════════════════════════════════

function TracesTab() {
  return (
    <>
      {/* Execution header */}
      <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-5">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-3">
              <h3 className="text-sm font-semibold text-text-primary">
                Execution: exec-rca-2024-0319-a7f2
              </h3>
              <span className="rounded-full bg-severity-ok/10 px-2.5 py-0.5 text-xs font-medium text-severity-ok">
                completed
              </span>
            </div>
            <p className="mt-1 text-xs text-text-muted">
              Root Cause Analysis -- "Why is the checkout service returning 500 errors?"
            </p>
          </div>
          <div className="flex items-center gap-6 text-xs">
            <div className="text-center">
              <p className="font-mono text-lg font-semibold text-text-primary">
                {(totalWaterfallMs / 1000).toFixed(1)}s
              </p>
              <p className="text-text-muted">Duration</p>
            </div>
            <div className="text-center">
              <p className="font-mono text-lg font-semibold text-text-primary">
                {totalWaterfallTokens.toLocaleString()}
              </p>
              <p className="text-text-muted">Tokens</p>
            </div>
            <div className="text-center">
              <p className="font-mono text-lg font-semibold text-text-primary">
                ${totalWaterfallCost.toFixed(4)}
              </p>
              <p className="text-text-muted">Cost</p>
            </div>
          </div>
        </div>
      </div>

      {/* Span type legend */}
      <div className="flex items-center gap-4">
        {Object.entries(spanTypeColors).map(([type, colors]) => (
          <div key={type} className="flex items-center gap-1.5">
            <div className={cn("h-2.5 w-2.5 rounded-sm", colors.bg, "border", colors.border)} />
            <span className="text-[10px] capitalize text-text-muted">{type.replace("_", " ")}</span>
          </div>
        ))}
      </div>

      {/* Waterfall chart */}
      <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-4">
        <h3 className="mb-4 flex items-center gap-2 text-sm font-medium text-text-secondary">
          <Timer className="h-4 w-4 text-cyan-400" />
          Execution Waterfall
        </h3>

        {/* Time ruler */}
        <div className="mb-2 flex items-center justify-between px-[220px] text-[10px] text-text-muted">
          {[0, 2, 4, 6, 8, 10].map((sec) => (
            <span key={sec}>{sec}s</span>
          ))}
        </div>
        <div className="mb-3 ml-[220px] h-px bg-border-default" />

        {/* Spans */}
        <div className="space-y-1.5">
          {waterfallSpans.map((span) => {
            const colors = spanTypeColors[span.type] || spanTypeColors.thinking;
            const leftPct = (span.startMs / totalWaterfallMs) * 100;
            const widthPct = Math.max(0.5, (span.durationMs / totalWaterfallMs) * 100);
            const indent = span.parentId ? 16 : 0;

            return (
              <div key={span.id} className="flex items-center gap-3">
                {/* Span label */}
                <div
                  className="w-[208px] shrink-0 truncate text-xs text-text-secondary"
                  style={{ paddingLeft: indent }}
                  title={span.name}
                >
                  <span className={cn("font-medium", colors.text)}>
                    {span.parentId ? "  " : ""}{span.name}
                  </span>
                </div>

                {/* Bar container */}
                <div className="relative flex-1 h-7">
                  {/* Bar */}
                  <div
                    className={cn(
                      "absolute top-0 h-7 rounded-md border flex items-center px-2 text-[10px] font-medium transition-all",
                      colors.bg, colors.border, colors.text,
                    )}
                    style={{
                      left: `${leftPct}%`,
                      width: `${widthPct}%`,
                      minWidth: "2px",
                    }}
                  >
                    {widthPct > 8 && (
                      <span className="truncate">
                        {span.durationMs >= 1000
                          ? `${(span.durationMs / 1000).toFixed(1)}s`
                          : `${span.durationMs}ms`}
                      </span>
                    )}
                  </div>
                </div>

                {/* Metadata */}
                <div className="flex w-[120px] shrink-0 items-center justify-end gap-3 text-[10px] text-text-muted">
                  {span.tokens > 0 && (
                    <span className="font-mono">{span.tokens.toLocaleString()} tok</span>
                  )}
                  {span.cost > 0 && (
                    <span className="font-mono">${span.cost.toFixed(4)}</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Summary */}
        <div className="mt-4 flex items-center justify-between border-t border-border-default pt-3">
          <div className="flex items-center gap-4 text-xs text-text-muted">
            <span>{waterfallSpans.length} spans</span>
            <span>Critical path: {waterfallSpans.filter((s) => !s.parentId).length} spans</span>
          </div>
          <div className="flex items-center gap-1 text-xs text-cyan-400">
            <Eye className="h-3 w-3" />
            <span className="font-medium">View raw trace JSON</span>
          </div>
        </div>
      </div>
    </>
  );
}

// ══════════════════════════════════════════════════════════════════════
// TAB 3: Accuracy & Hallucinations
// ══════════════════════════════════════════════════════════════════════

function AccuracyTab() {
  const maxAcc = Math.max(...accuracyTrend.map((d) => d.accuracy));
  const minAcc = Math.min(...accuracyTrend.map((d) => d.accuracy));
  const range = maxAcc - minAcc || 1;

  return (
    <>
      {/* Summary cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
        <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-5">
          <p className="text-xs text-text-muted">Avg Accuracy (7d)</p>
          <p className="mt-1 text-2xl font-semibold text-severity-ok">95.7%</p>
        </div>
        <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-5">
          <p className="text-xs text-text-muted">Total Claims Validated</p>
          <p className="mt-1 text-2xl font-semibold text-text-primary">2,847</p>
        </div>
        <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-5">
          <p className="text-xs text-text-muted">Hallucinations Detected</p>
          <p className="mt-1 text-2xl font-semibold text-severity-warning">20</p>
        </div>
        <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-5">
          <p className="text-xs text-text-muted">Critical Hallucinations</p>
          <p className="mt-1 text-2xl font-semibold text-severity-error">2</p>
        </div>
      </div>

      {/* Accuracy trend chart */}
      <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-4">
        <h3 className="mb-4 flex items-center gap-2 text-sm font-medium text-text-secondary">
          <TrendingUp className="h-4 w-4 text-severity-ok" />
          Accuracy Trend (10d)
        </h3>
        <div className="relative" style={{ height: 200 }}>
          {/* Y-axis labels */}
          <div className="absolute left-0 top-0 bottom-0 flex flex-col justify-between text-[10px] text-text-muted w-10">
            <span>{maxAcc.toFixed(0)}%</span>
            <span>{((maxAcc + minAcc) / 2).toFixed(0)}%</span>
            <span>{minAcc.toFixed(0)}%</span>
          </div>
          {/* Chart area */}
          <div className="ml-12 flex items-end gap-1 h-full">
            {accuracyTrend.map((point) => {
              const normalized = ((point.accuracy - minAcc) / range);
              const barHeight = 40 + normalized * 140; // min 40px, max 180px
              return (
                <div key={point.date} className="flex flex-1 flex-col items-center gap-1">
                  <span className="text-[10px] font-medium text-severity-ok">
                    {point.accuracy.toFixed(1)}%
                  </span>
                  <div className="w-full flex flex-col items-center">
                    <div
                      className="w-full rounded-t bg-severity-ok/60"
                      style={{ height: barHeight }}
                    />
                    {point.hallucinations > 0 && (
                      <div
                        className="w-full rounded-b bg-severity-error/40"
                        style={{ height: point.hallucinations * 6 }}
                      />
                    )}
                  </div>
                  <span className="text-[10px] text-text-muted">{point.date}</span>
                </div>
              );
            })}
          </div>
        </div>
        <div className="mt-3 flex items-center justify-center gap-4">
          <Legend color="bg-severity-ok/60" label="Accuracy" />
          <Legend color="bg-severity-error/40" label="Hallucinations" />
        </div>
      </div>

      {/* Hallucinations list */}
      <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-4">
        <h3 className="mb-4 flex items-center gap-2 text-sm font-medium text-text-secondary">
          <ShieldAlert className="h-4 w-4 text-severity-warning" />
          Recent Hallucinations Detected
        </h3>
        <div className="space-y-2">
          {hallucinations.map((h) => (
            <div key={h.id} className="rounded-lg bg-navy-800/50 p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className={cn(
                    "rounded-full border px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider",
                    severityBadge[h.severity],
                  )}>
                    {h.severity}
                  </span>
                  <span className="text-xs font-medium text-text-primary">{h.agentType}</span>
                  <span className="text-[10px] text-text-muted">{h.timestamp}</span>
                </div>
                <span className={cn(
                  "font-mono text-xs font-medium",
                  h.accuracy >= 90 ? "text-severity-ok" : h.accuracy >= 70 ? "text-severity-warning" : "text-severity-error"
                )}>
                  {h.accuracy}% accurate
                </span>
              </div>
              <p className="mt-2 text-xs text-text-secondary leading-relaxed">
                {h.claimText}
              </p>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

// ══════════════════════════════════════════════════════════════════════
// TAB 4: Cost Management
// ══════════════════════════════════════════════════════════════════════

function CostsTab() {
  const budgetPct = (budgetData.spentToday / budgetData.dailyBudget) * 100;
  const budgetColor = budgetPct >= 90 ? "bg-severity-error" : budgetPct >= 70 ? "bg-severity-warning" : "bg-severity-ok";

  return (
    <>
      {/* Forecast + Budget cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {/* Monthly forecast card */}
        <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-5">
          <div className="flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-severity-warning" />
            <h3 className="text-sm font-medium text-text-secondary">Monthly Forecast</h3>
          </div>
          <p className="mt-3 text-3xl font-bold text-text-primary">
            ${costForecast.projectedMonthly.toFixed(2)}
          </p>
          <div className="mt-2 flex items-center gap-2">
            <span className={cn(
              "rounded-full px-2 py-0.5 text-[10px] font-medium",
              costForecast.trend === "increasing" ? "bg-severity-error/10 text-severity-error"
                : costForecast.trend === "decreasing" ? "bg-severity-ok/10 text-severity-ok"
                : "bg-navy-700 text-text-muted"
            )}>
              {costForecast.trend === "increasing" ? "+" : costForecast.trend === "decreasing" ? "" : ""}{costForecast.trendPct}% vs last period
            </span>
          </div>
          <div className="mt-3 flex items-center justify-between text-xs text-text-muted">
            <span>Daily avg: ${costForecast.dailyAvg.toFixed(2)}</span>
            <span>Confidence: {(costForecast.confidence * 100).toFixed(0)}%</span>
          </div>
        </div>

        {/* Budget gauge card */}
        <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-5">
          <div className="flex items-center gap-2">
            <Gauge className="h-4 w-4 text-cyan-400" />
            <h3 className="text-sm font-medium text-text-secondary">Daily Budget</h3>
          </div>
          <div className="mt-3 flex items-end justify-between">
            <p className="text-3xl font-bold text-text-primary">
              ${budgetData.spentToday.toFixed(2)}
            </p>
            <p className="text-sm text-text-muted">
              / ${budgetData.dailyBudget.toFixed(2)}
            </p>
          </div>
          {/* Gauge bar */}
          <div className="mt-3 h-3 w-full rounded-full bg-navy-800">
            <div
              className={cn("h-3 rounded-full transition-all", budgetColor)}
              style={{ width: `${Math.min(100, budgetPct)}%` }}
            />
          </div>
          <div className="mt-2 flex items-center justify-between text-xs">
            <span className={cn(
              "font-medium",
              budgetData.onTrack ? "text-severity-ok" : "text-severity-error"
            )}>
              {budgetData.onTrack ? "On track" : `Projected overage: $${budgetData.projectedOverage.toFixed(2)}`}
            </span>
            <span className="text-text-muted">${budgetData.remaining.toFixed(2)} remaining</span>
          </div>
        </div>

        {/* Cost per investigation card */}
        <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-5">
          <div className="flex items-center gap-2">
            <Search className="h-4 w-4 text-accent-indigo" />
            <h3 className="text-sm font-medium text-text-secondary">Cost per Investigation</h3>
          </div>
          <div className="mt-3 space-y-2">
            {agentMetrics.map((agent) => (
              <div key={agent.agentType} className="flex items-center justify-between text-xs">
                <span className={cn("font-medium", agent.color)}>{agent.label}</span>
                <span className="font-mono text-text-primary">{agent.avgCost}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Optimization suggestions */}
      <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-4">
        <h3 className="mb-4 flex items-center gap-2 text-sm font-medium text-text-secondary">
          <Lightbulb className="h-4 w-4 text-severity-warning" />
          Cost Optimization Suggestions
        </h3>
        <div className="space-y-3">
          {costSuggestions.map((suggestion, i) => (
            <div key={i} className="rounded-lg border border-border-default bg-navy-800/30 p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="text-sm font-medium text-text-primary">
                    {suggestion.suggestion}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className={cn(
                    "rounded-full px-2 py-0.5 text-[10px] font-medium",
                    effortBadge[suggestion.effort],
                  )}>
                    {suggestion.effort} effort
                  </span>
                  <span className="rounded-full bg-severity-ok/10 px-2.5 py-0.5 text-xs font-semibold text-severity-ok">
                    -{suggestion.savingsPct}%
                  </span>
                </div>
              </div>
              <p className="mt-2 text-xs text-text-muted leading-relaxed">
                {suggestion.details}
              </p>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

// ══════════════════════════════════════════════════════════════════════
// TAB 5: A/B Testing
// ══════════════════════════════════════════════════════════════════════

function ABTestingTab() {
  return (
    <>
      {/* Summary */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-5">
          <p className="text-xs text-text-muted">Active Experiments</p>
          <p className="mt-1 text-2xl font-semibold text-cyan-400">
            {experiments.filter((e) => e.status === "running").length}
          </p>
        </div>
        <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-5">
          <p className="text-xs text-text-muted">Concluded</p>
          <p className="mt-1 text-2xl font-semibold text-severity-ok">
            {experiments.filter((e) => e.status === "concluded").length}
          </p>
        </div>
        <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-5">
          <p className="text-xs text-text-muted">Total Samples Collected</p>
          <p className="mt-1 text-2xl font-semibold text-text-primary">
            {experiments.reduce((a, e) => a + e.variantA.samples + e.variantB.samples, 0).toLocaleString()}
          </p>
        </div>
      </div>

      {/* Experiment cards */}
      <div className="space-y-4">
        {experiments.map((exp) => (
          <div key={exp.id} className="rounded-xl border border-border-default/60 bg-surface-secondary p-5">
            {/* Experiment header */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <FlaskConical className="h-4 w-4 text-accent-indigo" />
                <h3 className="text-sm font-semibold text-text-primary">{exp.name}</h3>
                <span className={cn(
                  "rounded-full px-2.5 py-0.5 text-[10px] font-medium",
                  exp.status === "running" ? "bg-cyan-500/10 text-cyan-400"
                    : exp.status === "concluded" ? "bg-severity-ok/10 text-severity-ok"
                    : "bg-navy-700 text-text-muted"
                )}>
                  {exp.status}
                </span>
                {exp.winner && (
                  <span className="rounded-full bg-severity-ok/10 border border-severity-ok/30 px-2.5 py-0.5 text-[10px] font-semibold text-severity-ok">
                    Winner: Variant {exp.winner}
                  </span>
                )}
              </div>
              <div className="text-xs text-text-muted">
                Metric: <span className="font-medium text-text-secondary">{exp.successMetric}</span>
                {" | "}
                Confidence: <span className={cn(
                  "font-medium",
                  exp.isSignificant ? "text-severity-ok" : "text-severity-warning"
                )}>
                  {(exp.confidence * 100).toFixed(0)}%
                </span>
              </div>
            </div>

            {/* Variant comparison */}
            <div className="mt-4 grid grid-cols-2 gap-4">
              {/* Variant A */}
              <div className={cn(
                "rounded-lg border p-4",
                exp.winner === "A" ? "border-severity-ok/40 bg-severity-ok/5" : "border-border-default bg-navy-800/30"
              )}>
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-text-primary">
                    Variant A (Control)
                  </span>
                  {exp.winner === "A" && (
                    <CheckCircle2 className="h-4 w-4 text-severity-ok" />
                  )}
                </div>
                <p className="mt-1 text-[10px] text-text-muted">{exp.variantA.description}</p>
                <p className="mt-0.5 text-[10px] text-text-muted">Model: {exp.variantA.model}</p>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <MetricCell label="Success Rate" value={`${exp.variantA.successRate}%`} />
                  <MetricCell label="Avg Duration" value={`${(exp.variantA.avgDuration / 1000).toFixed(1)}s`} />
                  <MetricCell label="Avg Cost" value={`$${exp.variantA.avgCost.toFixed(3)}`} />
                  <MetricCell label="Samples" value={exp.variantA.samples.toString()} />
                </div>
              </div>

              {/* Variant B */}
              <div className={cn(
                "rounded-lg border p-4",
                exp.winner === "B" ? "border-severity-ok/40 bg-severity-ok/5" : "border-border-default bg-navy-800/30"
              )}>
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-text-primary">
                    Variant B (Treatment)
                  </span>
                  {exp.winner === "B" && (
                    <CheckCircle2 className="h-4 w-4 text-severity-ok" />
                  )}
                </div>
                <p className="mt-1 text-[10px] text-text-muted">{exp.variantB.description}</p>
                <p className="mt-0.5 text-[10px] text-text-muted">Model: {exp.variantB.model}</p>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <MetricCell label="Success Rate" value={`${exp.variantB.successRate}%`}
                    highlight={exp.variantB.successRate > exp.variantA.successRate} />
                  <MetricCell label="Avg Duration" value={`${(exp.variantB.avgDuration / 1000).toFixed(1)}s`}
                    highlight={exp.variantB.avgDuration < exp.variantA.avgDuration} />
                  <MetricCell label="Avg Cost" value={`$${exp.variantB.avgCost.toFixed(3)}`}
                    highlight={exp.variantB.avgCost < exp.variantA.avgCost} />
                  <MetricCell label="Samples" value={exp.variantB.samples.toString()} />
                </div>
              </div>
            </div>

            {/* Significance bar */}
            <div className="mt-3 flex items-center gap-3 text-xs">
              <span className="text-text-muted">Statistical significance:</span>
              <div className="h-2 flex-1 rounded-full bg-navy-800">
                <div
                  className={cn(
                    "h-2 rounded-full transition-all",
                    exp.isSignificant ? "bg-severity-ok" : "bg-severity-warning"
                  )}
                  style={{ width: `${exp.confidence * 100}%` }}
                />
              </div>
              <span className={cn(
                "font-mono font-medium",
                exp.isSignificant ? "text-severity-ok" : "text-severity-warning"
              )}>
                {(exp.confidence * 100).toFixed(0)}%
              </span>
              <span className="text-text-muted">
                {exp.isSignificant ? "(p < 0.05)" : "(not yet significant)"}
              </span>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

function MetricCell({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div>
      <p className="text-[10px] text-text-muted">{label}</p>
      <p className={cn(
        "font-mono text-xs font-medium",
        highlight ? "text-severity-ok" : "text-text-primary"
      )}>
        {value}
      </p>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════
// TAB 6: Agent SLOs
// ══════════════════════════════════════════════════════════════════════

function SLOsTab() {
  const meetingCount = sloData.filter((s) => s.isMeeting).length;
  const violatingCount = sloData.filter((s) => !s.isMeeting).length;

  return (
    <>
      {/* Summary */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-5">
          <p className="text-xs text-text-muted">SLOs Meeting Target</p>
          <p className="mt-1 text-2xl font-semibold text-severity-ok">{meetingCount}/{sloData.length}</p>
        </div>
        <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-5">
          <p className="text-xs text-text-muted">SLOs Violated</p>
          <p className="mt-1 text-2xl font-semibold text-severity-error">{violatingCount}</p>
        </div>
        <div className="rounded-xl border border-border-default/60 bg-surface-secondary p-5">
          <p className="text-xs text-text-muted">Avg Error Budget Remaining</p>
          <p className="mt-1 text-2xl font-semibold text-text-primary">
            {(sloData.reduce((a, s) => a + s.errorBudgetRemainingPct, 0) / sloData.length).toFixed(1)}%
          </p>
        </div>
      </div>

      {/* SLO cards */}
      <div className="space-y-4">
        {sloData.map((slo) => {
          const budgetColor = slo.errorBudgetRemainingPct >= 50
            ? "bg-severity-ok"
            : slo.errorBudgetRemainingPct >= 20
            ? "bg-severity-warning"
            : "bg-severity-error";

          const burnRateColor = (rate: number) =>
            rate >= 6 ? "text-severity-error" : rate >= 3 ? "text-severity-warning" : "text-severity-ok";

          return (
            <div
              key={slo.id}
              className={cn(
                "rounded-xl border bg-surface-secondary p-5",
                slo.isMeeting ? "border-border-default" : "border-severity-error/40"
              )}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Target className={cn("h-4 w-4", slo.isMeeting ? "text-severity-ok" : "text-severity-error")} />
                  <h3 className="text-sm font-semibold text-text-primary">{slo.name}</h3>
                  <span className="rounded-full bg-navy-700 px-2 py-0.5 text-[10px] text-text-muted">
                    {slo.agentType}
                  </span>
                  <span className={cn(
                    "rounded-full px-2.5 py-0.5 text-[10px] font-medium",
                    slo.isMeeting
                      ? "bg-severity-ok/10 text-severity-ok"
                      : "bg-severity-error/10 text-severity-error"
                  )}>
                    {slo.isMeeting ? "Meeting" : "Violated"}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  {slo.trend === "improving" && <TrendingUp className="h-3.5 w-3.5 text-severity-ok" />}
                  {slo.trend === "degrading" && <TrendingDown className="h-3.5 w-3.5 text-severity-error" />}
                  {slo.trend === "stable" && <span className="block h-0.5 w-4 rounded bg-text-muted" />}
                  <span className="text-[10px] text-text-muted capitalize">{slo.trend}</span>
                </div>
              </div>

              <div className="mt-4 grid grid-cols-4 gap-6">
                {/* Current vs Target */}
                <div>
                  <p className="text-[10px] text-text-muted">Current / Target</p>
                  <div className="mt-1 flex items-baseline gap-1">
                    <span className={cn(
                      "font-mono text-lg font-semibold",
                      slo.isMeeting ? "text-text-primary" : "text-severity-error"
                    )}>
                      {formatSliValue(slo.sliType, slo.currentValue)}
                    </span>
                    <span className="text-xs text-text-muted">
                      / {formatSliTarget(slo.sliType, slo.target)}
                    </span>
                  </div>
                </div>

                {/* Error Budget */}
                <div>
                  <p className="text-[10px] text-text-muted">Error Budget Remaining</p>
                  <div className="mt-1">
                    <div className="flex items-center gap-2">
                      <div className="h-2.5 flex-1 rounded-full bg-navy-800">
                        <div
                          className={cn("h-2.5 rounded-full transition-all", budgetColor)}
                          style={{ width: `${slo.errorBudgetRemainingPct}%` }}
                        />
                      </div>
                      <span className="font-mono text-xs font-medium text-text-primary">
                        {slo.errorBudgetRemainingPct.toFixed(1)}%
                      </span>
                    </div>
                  </div>
                </div>

                {/* 1h Burn Rate */}
                <div>
                  <p className="text-[10px] text-text-muted">Burn Rate (1h)</p>
                  <p className={cn("mt-1 font-mono text-lg font-semibold", burnRateColor(slo.burnRate1h))}>
                    {slo.burnRate1h.toFixed(1)}x
                  </p>
                </div>

                {/* 6h Burn Rate */}
                <div>
                  <p className="text-[10px] text-text-muted">Burn Rate (6h)</p>
                  <p className={cn("mt-1 font-mono text-lg font-semibold", burnRateColor(slo.burnRate6h))}>
                    {slo.burnRate6h.toFixed(1)}x
                  </p>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}

// ── Shared components ───────────────────────────────────────────────

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <div className={cn("h-2.5 w-2.5 rounded-sm", color)} />
      <span className="text-[10px] text-text-muted">{label}</span>
    </div>
  );
}
