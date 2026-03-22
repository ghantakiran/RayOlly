"use client";

import { useState, useEffect, useRef, Fragment } from "react";
import {
  Bot,
  Search,
  Zap,
  Shield,
  AlertTriangle,
  TrendingUp,
  Target,
  Send,
  Clock,
  CheckCircle2,
  XCircle,
  Loader2,
  Sparkles,
  Wrench,
  Download,
  Star,
  ArrowRight,
  ArrowUpRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { getAgentsList, invokeAgent } from "@/lib/api";

// ── Types ────────────────────────────────────────────────────────

interface AgentInfo {
  type: string;
  name: string;
  description: string;
  status: string;
  tools_count?: number;
  tools?: string[];
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  tokensInput?: number;
  tokensOutput?: number;
  cost?: number;
  durationMs?: number;
  isError?: boolean;
}

interface Execution {
  id: string;
  agentType: string;
  input: string;
  status: "completed" | "failed" | "running";
  durationMs?: number;
  cost?: number;
  timestamp: Date;
}

// ── Agent styling config ─────────────────────────────────────────

const agentStyleMap: Record<
  string,
  {
    icon: React.ComponentType<{ className?: string }>;
    gradient: string;
    borderGradient: string;
    color: string;
    bgColor: string;
  }
> = {
  rca: {
    icon: Search,
    gradient: "from-red-500 to-red-600",
    borderGradient: "from-red-500/80 via-red-500/40 to-transparent",
    color: "text-red-400",
    bgColor: "bg-red-500/10",
  },
  query: {
    icon: Sparkles,
    gradient: "from-cyan-400 to-cyan-600",
    borderGradient: "from-cyan-400/80 via-cyan-400/40 to-transparent",
    color: "text-cyan-400",
    bgColor: "bg-cyan-500/10",
  },
  incident: {
    icon: Shield,
    gradient: "from-orange-400 to-orange-600",
    borderGradient: "from-orange-400/80 via-orange-400/40 to-transparent",
    color: "text-orange-400",
    bgColor: "bg-orange-500/10",
  },
  anomaly: {
    icon: AlertTriangle,
    gradient: "from-purple-400 to-purple-600",
    borderGradient: "from-purple-400/80 via-purple-400/40 to-transparent",
    color: "text-purple-400",
    bgColor: "bg-purple-500/10",
  },
  capacity: {
    icon: TrendingUp,
    gradient: "from-green-400 to-green-600",
    borderGradient: "from-green-400/80 via-green-400/40 to-transparent",
    color: "text-green-400",
    bgColor: "bg-green-500/10",
  },
  slo: {
    icon: Target,
    gradient: "from-blue-400 to-blue-600",
    borderGradient: "from-blue-400/80 via-blue-400/40 to-transparent",
    color: "text-blue-400",
    bgColor: "bg-blue-500/10",
  },
};

const defaultStyle = {
  icon: Bot,
  gradient: "from-cyan-400 to-cyan-600",
  borderGradient: "from-cyan-400/80 via-cyan-400/40 to-transparent",
  color: "text-cyan-400",
  bgColor: "bg-cyan-500/10",
};

// ── Suggested questions ──────────────────────────────────────────

const suggestedQuestions = [
  "What are the top 5 errors in the last hour?",
  "Which service has the highest latency?",
  "Analyze the error rate trend for payment-api",
  "Show me slow traces over 500ms",
];

// ── Marketplace agents ───────────────────────────────────────────

const marketplaceAgents = [
  {
    name: "Cost Optimizer",
    description:
      "Analyzes cloud resource usage and recommends cost-saving optimizations across your infrastructure.",
    downloads: 12400,
    rating: 4.8,
    icon: TrendingUp,
    color: "text-green-400",
    bgColor: "bg-green-500/10",
  },
  {
    name: "Security Scanner",
    description:
      "Continuously scans logs and traces for security anomalies, CVEs, and suspicious access patterns.",
    downloads: 9800,
    rating: 4.9,
    icon: Shield,
    color: "text-red-400",
    bgColor: "bg-red-500/10",
  },
  {
    name: "Deployment Guardian",
    description:
      "Monitors deployments in real-time, auto-detects regressions, and triggers rollbacks when needed.",
    downloads: 7200,
    rating: 4.7,
    icon: Zap,
    color: "text-amber-400",
    bgColor: "bg-amber-500/10",
  },
];

// ── Simple markdown renderer ─────────────────────────────────────

function renderMarkdown(text: string) {
  const lines = text.split("\n");
  const elements: React.ReactNode[] = [];
  let inCodeBlock = false;
  let codeLines: string[] = [];

  lines.forEach((line, idx) => {
    if (line.startsWith("```")) {
      if (inCodeBlock) {
        elements.push(
          <pre
            key={`code-${idx}`}
            className="my-2 overflow-x-auto rounded-lg bg-navy-950/80 p-3 text-xs font-mono text-cyan-300"
          >
            {codeLines.join("\n")}
          </pre>
        );
        codeLines = [];
        inCodeBlock = false;
      } else {
        inCodeBlock = true;
      }
      return;
    }
    if (inCodeBlock) {
      codeLines.push(line);
      return;
    }

    // Bold
    let processed: React.ReactNode = line;
    if (line.includes("**")) {
      const parts = line.split(/\*\*(.*?)\*\*/g);
      processed = parts.map((part, i) =>
        i % 2 === 1 ? (
          <strong key={i} className="font-semibold text-text-primary">
            {part}
          </strong>
        ) : (
          <Fragment key={i}>{part}</Fragment>
        )
      );
    }

    // Inline code
    if (typeof processed === "string" && processed.includes("`")) {
      const parts = processed.split(/`(.*?)`/g);
      processed = parts.map((part, i) =>
        i % 2 === 1 ? (
          <code
            key={i}
            className="rounded bg-navy-950/60 px-1 py-0.5 text-xs font-mono text-cyan-300"
          >
            {part}
          </code>
        ) : (
          <Fragment key={i}>{part}</Fragment>
        )
      );
    }

    // Bullet points
    if (line.match(/^[\s]*[-*]\s/)) {
      elements.push(
        <div key={idx} className="flex items-start gap-2 pl-2">
          <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-cyan-400/60" />
          <span>{typeof processed === "string" ? processed : processed}</span>
        </div>
      );
      return;
    }

    // Empty line
    if (line.trim() === "") {
      elements.push(<div key={idx} className="h-2" />);
      return;
    }

    elements.push(<div key={idx}>{processed}</div>);
  });

  return <div className="space-y-0.5">{elements}</div>;
}

// ── Component ────────────────────────────────────────────────────

export default function AgentsPage() {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [agentsLoading, setAgentsLoading] = useState(true);
  const [agentsError, setAgentsError] = useState<string | null>(null);

  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);

  const [executions, setExecutions] = useState<Execution[]>([]);
  const [visibleMessages, setVisibleMessages] = useState<Set<number>>(
    new Set()
  );

  const chatEndRef = useRef<HTMLDivElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);

  // Load agents on mount
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await getAgentsList();
        if (cancelled) return;
        if (Array.isArray(data)) {
          setAgents(data);
        } else if (
          data &&
          typeof data === "object" &&
          "agents" in (data as any)
        ) {
          setAgents((data as any).agents);
        } else {
          setAgents([
            {
              type: "rca",
              name: "Root Cause Analysis",
              description:
                "Analyzes incidents to identify root causes by correlating logs, metrics, and traces.",
              status: "idle",
              tools_count: 5,
            },
            {
              type: "query",
              name: "Query Assistant",
              description:
                "Natural language to observability queries. Ask questions in plain English.",
              status: "idle",
              tools_count: 8,
            },
            {
              type: "incident",
              name: "Incident Manager",
              description:
                "Orchestrates incident response: creates timelines, suggests runbooks.",
              status: "idle",
              tools_count: 6,
            },
            {
              type: "anomaly",
              name: "Anomaly Detection",
              description:
                "Monitors metrics and logs for anomalous patterns using ML models.",
              status: "idle",
              tools_count: 4,
            },
          ]);
        }
      } catch (err) {
        if (!cancelled) setAgentsError("Failed to load agents");
      } finally {
        if (!cancelled) setAgentsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Auto-scroll chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages, chatLoading]);

  // Animate messages in
  useEffect(() => {
    const lastIdx = chatMessages.length - 1;
    if (lastIdx >= 0 && !visibleMessages.has(lastIdx)) {
      const timer = setTimeout(() => {
        setVisibleMessages((prev) => new Set([...prev, lastIdx]));
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [chatMessages, visibleMessages]);

  const handleSend = async (message?: string) => {
    const text = (message ?? chatInput).trim();
    if (!text || chatLoading) return;

    setChatInput("");
    setChatMessages((prev) => [...prev, { role: "user", content: text }]);
    setChatLoading(true);

    const startTime = Date.now();
    const execId = `exec-${Date.now()}`;

    setExecutions((prev) =>
      [
        {
          id: execId,
          agentType: "QUERY",
          input: text,
          status: "running" as const,
          timestamp: new Date(),
        },
        ...prev,
      ].slice(0, 5)
    );

    try {
      const result = await invokeAgent("QUERY", { question: text });
      const durationMs = Date.now() - startTime;

      if (result.status === "FAILED") {
        const errorMsg = result.output?.error || "Agent invocation failed";
        const isApiKeyError =
          errorMsg.toLowerCase().includes("api key") ||
          errorMsg.toLowerCase().includes("unauthorized") ||
          errorMsg.toLowerCase().includes("authentication");

        setChatMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: isApiKeyError
              ? `**Configuration Required**\n\nIt looks like the AI agent API key is not configured. To set it up:\n\n- Set the \`OPENAI_API_KEY\` or \`ANTHROPIC_API_KEY\` environment variable on the backend\n- Restart the RayOlly backend service\n- Try your query again\n\nOriginal error: ${errorMsg}`
              : `**Error:** ${errorMsg}`,
            isError: true,
            durationMs,
          },
        ]);
        setExecutions((prev) =>
          prev.map((e) =>
            e.id === execId
              ? { ...e, status: "failed" as const, durationMs }
              : e
          )
        );
      } else {
        const output = result.output ?? result;
        const responseText =
          typeof output === "string"
            ? output
            : output.response ??
              output.answer ??
              output.result ??
              output.message ??
              JSON.stringify(output, null, 2);

        const tokensInput =
          result.tokens_used?.input ?? result.input_tokens ?? undefined;
        const tokensOutput =
          result.tokens_used?.output ?? result.output_tokens ?? undefined;
        const cost = result.cost ?? result.total_cost ?? undefined;

        setChatMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: responseText,
            tokensInput,
            tokensOutput,
            cost,
            durationMs,
          },
        ]);

        setExecutions((prev) =>
          prev.map((e) =>
            e.id === execId
              ? { ...e, status: "completed" as const, durationMs, cost }
              : e
          )
        );
      }
    } catch (err: any) {
      const durationMs = Date.now() - startTime;
      setChatMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `**Connection Error**\n\nFailed to reach the agent backend. Please check:\n\n- The RayOlly backend is running\n- Network connectivity is available\n- API endpoint is configured correctly\n\n_${err.message || "Unknown error"}_`,
          isError: true,
          durationMs,
        },
      ]);
      setExecutions((prev) =>
        prev.map((e) =>
          e.id === execId
            ? { ...e, status: "failed" as const, durationMs }
            : e
        )
      );
    } finally {
      setChatLoading(false);
    }
  };

  // Limit to 4 agents for the 2x2 grid
  const displayAgents = agents.slice(0, 4);

  return (
    <div className="space-y-8">
      {/* ── Header ─────────────────────────────────────────── */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-text-primary">
          AI Agents
        </h1>
        <p className="mt-1 text-sm text-text-muted">
          Autonomous observability intelligence
        </p>
      </div>

      {/* ── Row 1: Agent Cards (2x2 grid) ─────────────────── */}
      {agentsLoading ? (
        <div className="flex items-center justify-center py-16">
          <div className="flex flex-col items-center gap-3">
            <div className="relative">
              <div className="absolute inset-0 animate-ping rounded-full bg-cyan-400/20" />
              <Loader2 className="relative h-8 w-8 animate-spin text-cyan-400" />
            </div>
            <span className="text-sm text-text-muted">Loading agents...</span>
          </div>
        </div>
      ) : agentsError ? (
        <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-400">
          {agentsError}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {displayAgents.map((agent) => {
            const style =
              agentStyleMap[agent.type.toLowerCase()] ?? defaultStyle;
            const IconComp = style.icon;
            return (
              <div
                key={agent.type}
                className="group relative overflow-hidden rounded-xl border border-border-default/60 bg-surface-secondary transition-all duration-300 hover:border-navy-500 hover:shadow-lg hover:shadow-black/20"
              >
                {/* Gradient left border */}
                <div
                  className={cn(
                    "absolute left-0 top-0 h-full w-1 bg-gradient-to-b",
                    style.borderGradient
                  )}
                />
                <div className="p-5 pl-6">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      <div
                        className={cn(
                          "flex h-10 w-10 items-center justify-center rounded-lg",
                          style.bgColor
                        )}
                      >
                        <IconComp className={cn("h-5 w-5", style.color)} />
                      </div>
                      <div>
                        <h3 className="text-sm font-semibold text-text-primary">
                          {agent.name}
                        </h3>
                        <p className="mt-0.5 text-xs text-text-muted line-clamp-1">
                          {agent.description}
                        </p>
                      </div>
                    </div>
                  </div>
                  <div className="mt-4 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      {agent.tools_count != null && (
                        <span
                          className={cn(
                            "flex items-center gap-1 rounded-md px-2 py-0.5 text-[10px] font-medium",
                            style.bgColor,
                            style.color
                          )}
                        >
                          <Wrench className="h-3 w-3" />
                          {agent.tools_count} tools
                        </span>
                      )}
                      <span className="rounded-md bg-navy-700/60 px-2 py-0.5 text-[10px] font-mono text-text-muted uppercase">
                        {agent.type}
                      </span>
                    </div>
                    <button
                      onClick={() =>
                        handleSend(
                          `Run ${agent.name.toLowerCase()} analysis`
                        )
                      }
                      disabled={chatLoading}
                      className={cn(
                        "flex items-center gap-1.5 rounded-lg px-3.5 py-1.5 text-xs font-medium transition-all duration-200",
                        chatLoading
                          ? "bg-navy-700 text-text-muted cursor-not-allowed"
                          : "bg-cyan-600 text-white hover:bg-cyan-500 hover:shadow-md hover:shadow-cyan-500/20"
                      )}
                    >
                      {chatLoading ? (
                        <>
                          <Loader2 className="h-3 w-3 animate-spin" />
                          Working...
                        </>
                      ) : (
                        <>
                          <Zap className="h-3 w-3" />
                          Invoke
                        </>
                      )}
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ── Row 2: Full-width Chat Panel ──────────────────── */}
      <div className="flex flex-col rounded-2xl border border-border-default/60 bg-surface-secondary shadow-xl shadow-black/10">
        {/* Chat header */}
        <div className="flex items-center gap-3 border-b border-border-default px-5 py-3.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-cyan-400 to-cyan-600">
            <Zap className="h-4 w-4 text-white" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-text-primary">
              RayOlly AI Assistant
            </h3>
            <p className="text-[11px] text-text-muted">
              Ask anything about your observability data
            </p>
          </div>
          {chatLoading && (
            <span className="ml-auto rounded-full bg-cyan-500/10 px-2.5 py-0.5 text-[10px] font-medium text-cyan-400">
              Processing...
            </span>
          )}
        </div>

        {/* Chat messages area */}
        <div
          ref={chatContainerRef}
          className="flex-1 space-y-4 overflow-y-auto p-5"
          style={{ minHeight: "320px", maxHeight: "520px" }}
        >
          {chatMessages.length === 0 && !chatLoading && (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-cyan-400/10 to-purple-400/10">
                <Sparkles className="h-7 w-7 text-cyan-400" />
              </div>
              <p className="text-sm font-medium text-text-secondary">
                How can I help you today?
              </p>
              <p className="mt-1 text-xs text-text-muted">
                Ask about logs, metrics, traces, or any observability data
              </p>
            </div>
          )}

          {chatMessages.map((msg, i) => (
            <div
              key={i}
              className={cn(
                "flex transition-all duration-300",
                msg.role === "user" ? "justify-end" : "justify-start",
                visibleMessages.has(i)
                  ? "translate-y-0 opacity-100"
                  : "translate-y-2 opacity-0"
              )}
            >
              {msg.role === "assistant" && (
                <div className="mr-2.5 mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-cyan-400 to-cyan-600">
                  <Zap className="h-3.5 w-3.5 text-white" />
                </div>
              )}
              <div
                className={cn(
                  "max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed",
                  msg.role === "user"
                    ? "bg-cyan-500/20 text-text-primary"
                    : msg.isError
                      ? "bg-red-500/5 border border-red-500/20 text-text-primary"
                      : "bg-surface-tertiary text-text-primary"
                )}
              >
                {msg.role === "assistant" ? (
                  <div className="whitespace-pre-wrap">
                    {renderMarkdown(msg.content)}
                  </div>
                ) : (
                  <div className="whitespace-pre-wrap">{msg.content}</div>
                )}

                {/* Metadata footer */}
                {msg.role === "assistant" && msg.durationMs != null && (
                  <div className="mt-2.5 flex items-center gap-3 border-t border-border-default/50 pt-2 text-[10px] text-text-muted">
                    {msg.tokensInput != null && msg.tokensOutput != null && (
                      <span>
                        Tokens:{" "}
                        {(
                          msg.tokensInput + msg.tokensOutput
                        ).toLocaleString()}
                      </span>
                    )}
                    {msg.cost != null && (
                      <span>Cost: ${msg.cost.toFixed(3)}</span>
                    )}
                    <span>
                      Duration: {(msg.durationMs / 1000).toFixed(1)}s
                    </span>
                  </div>
                )}
              </div>
            </div>
          ))}

          {/* Typing indicator */}
          {chatLoading && (
            <div className="flex items-start justify-start">
              <div className="mr-2.5 mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-cyan-400 to-cyan-600">
                <Zap className="h-3.5 w-3.5 text-white" />
              </div>
              <div className="rounded-2xl bg-surface-tertiary px-4 py-3">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-text-muted">Thinking</span>
                  <span className="flex gap-0.5">
                    <span
                      className="h-1.5 w-1.5 animate-bounce rounded-full bg-cyan-400/70"
                      style={{ animationDelay: "0ms" }}
                    />
                    <span
                      className="h-1.5 w-1.5 animate-bounce rounded-full bg-cyan-400/70"
                      style={{ animationDelay: "150ms" }}
                    />
                    <span
                      className="h-1.5 w-1.5 animate-bounce rounded-full bg-cyan-400/70"
                      style={{ animationDelay: "300ms" }}
                    />
                  </span>
                </div>
              </div>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>

        {/* Suggested questions (shown only when no messages) */}
        {chatMessages.length === 0 && (
          <div className="border-t border-border-default/50 px-5 py-3">
            <div className="flex flex-wrap gap-2">
              {suggestedQuestions.map((q) => (
                <button
                  key={q}
                  onClick={() => handleSend(q)}
                  disabled={chatLoading}
                  className="rounded-lg border border-border-default bg-navy-800/40 px-3 py-1.5 text-xs text-text-secondary transition-all duration-200 hover:border-cyan-500/30 hover:bg-cyan-500/5 hover:text-cyan-400"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Input bar */}
        <div className="border-t border-border-default p-4">
          <div className="flex items-center gap-3">
            <input
              type="text"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSend()}
              placeholder="Ask about your observability data..."
              disabled={chatLoading}
              className="flex-1 rounded-lg border border-border-default bg-navy-900 px-4 py-2.5 text-sm text-text-primary placeholder:text-text-muted focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500/30 disabled:opacity-50 transition-colors"
            />
            <button
              onClick={() => handleSend()}
              disabled={chatLoading || !chatInput.trim()}
              className={cn(
                "flex h-10 w-10 items-center justify-center rounded-lg transition-all duration-200",
                chatLoading || !chatInput.trim()
                  ? "bg-navy-700 text-text-muted cursor-not-allowed"
                  : "bg-cyan-600 text-white hover:bg-cyan-500 hover:shadow-md hover:shadow-cyan-500/20"
              )}
            >
              {chatLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </button>
          </div>
          <p className="mt-1.5 text-[10px] text-text-muted">
            Press Enter to send
          </p>
        </div>
      </div>

      {/* ── Row 3: Marketplace Preview ────────────────────── */}
      <div>
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-text-primary">
              Agent Marketplace
            </h2>
            <p className="mt-0.5 text-xs text-text-muted">
              Extend your observability with community agents
            </p>
          </div>
          <button className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-cyan-400 transition-colors hover:bg-cyan-500/10">
            Browse all
            <ArrowRight className="h-3.5 w-3.5" />
          </button>
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {marketplaceAgents.map((agent) => {
            const IconComp = agent.icon;
            return (
              <div
                key={agent.name}
                className="group rounded-xl border border-border-default/60 bg-surface-secondary p-5 transition-all duration-300 hover:border-navy-500 hover:shadow-lg hover:shadow-black/10"
              >
                <div className="flex items-start gap-3">
                  <div
                    className={cn(
                      "flex h-9 w-9 items-center justify-center rounded-lg",
                      agent.bgColor
                    )}
                  >
                    <IconComp className={cn("h-4 w-4", agent.color)} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="text-sm font-semibold text-text-primary">
                      {agent.name}
                    </h3>
                    <p className="mt-1 text-xs leading-relaxed text-text-muted line-clamp-2">
                      {agent.description}
                    </p>
                  </div>
                </div>

                <div className="mt-4 flex items-center justify-between">
                  <div className="flex items-center gap-3 text-[10px] text-text-muted">
                    <span className="flex items-center gap-1">
                      <Download className="h-3 w-3" />
                      {(agent.downloads / 1000).toFixed(1)}k
                    </span>
                    <span className="flex items-center gap-0.5">
                      <Star className="h-3 w-3 fill-amber-400 text-amber-400" />
                      {agent.rating}
                    </span>
                  </div>
                  <button className="flex items-center gap-1 rounded-lg bg-navy-700/60 px-3 py-1.5 text-[11px] font-medium text-text-secondary transition-all duration-200 hover:bg-cyan-600 hover:text-white">
                    Install
                    <ArrowUpRight className="h-3 w-3" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
