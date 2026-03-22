"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import * as Dialog from "@radix-ui/react-dialog";
import {
  Search,
  LayoutDashboard,
  FileText,
  BarChart3,
  GitBranch,
  Activity,
  Server,
  Bell,
  Bot,
  Settings,
  LayoutGrid,
  Zap,
  Play,
  Database,
  MessageSquare,
  ArrowRight,
  Command,
  Globe,
  FlaskConical,
  MonitorSmartphone,
  Eye,
  Puzzle,
  Terminal,
  AlertTriangle,
  Cpu,
  Sparkles,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface CommandItem {
  id: string;
  label: string;
  category: "Navigation" | "Search" | "Actions" | "AI Agents" | "SRE Tools";
  icon: any;
  shortcut?: string;
  onSelect: () => void;
}

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const router = useRouter();

  const navigate = useCallback(
    (path: string) => {
      router.push(path);
      setOpen(false);
    },
    [router],
  );

  const items: CommandItem[] = useMemo(
    () => [
      // Navigation
      { id: "nav-dashboard", label: "Dashboard", category: "Navigation", icon: LayoutDashboard, shortcut: "G D", onSelect: () => navigate("/") },
      { id: "nav-logs", label: "Logs", category: "Navigation", icon: FileText, shortcut: "G L", onSelect: () => navigate("/logs") },
      { id: "nav-metrics", label: "Metrics", category: "Navigation", icon: BarChart3, shortcut: "G M", onSelect: () => navigate("/metrics") },
      { id: "nav-traces", label: "Traces", category: "Navigation", icon: GitBranch, shortcut: "G T", onSelect: () => navigate("/traces") },
      { id: "nav-apm", label: "APM", category: "Navigation", icon: Activity, onSelect: () => navigate("/apm") },
      { id: "nav-infra", label: "Infrastructure", category: "Navigation", icon: Server, shortcut: "G I", onSelect: () => navigate("/infrastructure") },
      { id: "nav-rum", label: "RUM", category: "Navigation", icon: MonitorSmartphone, onSelect: () => navigate("/rum") },
      { id: "nav-synthetics", label: "Synthetics", category: "Navigation", icon: FlaskConical, onSelect: () => navigate("/synthetics") },
      { id: "nav-dem", label: "DEM", category: "Navigation", icon: Globe, onSelect: () => navigate("/experience") },
      { id: "nav-alerts", label: "Alerts", category: "Navigation", icon: Bell, shortcut: "G R", onSelect: () => navigate("/alerts") },
      { id: "nav-agents", label: "AI Agents", category: "Navigation", icon: Bot, shortcut: "G A", onSelect: () => navigate("/agents") },
      { id: "nav-agent-insights", label: "Agent Insights", category: "Navigation", icon: Eye, onSelect: () => navigate("/agents/observability") },
      { id: "nav-dashboards", label: "Dashboards", category: "Navigation", icon: LayoutGrid, onSelect: () => navigate("/dashboards") },
      { id: "nav-integrations", label: "Integrations", category: "Navigation", icon: Puzzle, onSelect: () => navigate("/integrations") },
      { id: "nav-settings", label: "Settings", category: "Navigation", icon: Settings, shortcut: "G S", onSelect: () => navigate("/settings") },
      // Search
      { id: "search-logs", label: "Search logs...", category: "Search", icon: Search, onSelect: () => navigate("/logs") },
      { id: "search-metrics", label: "Search metrics...", category: "Search", icon: Search, onSelect: () => navigate("/metrics") },
      { id: "search-traces", label: "Find trace by ID...", category: "Search", icon: Search, onSelect: () => navigate("/traces") },
      // SRE Tools
      { id: "sre-status", label: "System status overview", category: "SRE Tools", icon: Cpu, onSelect: () => navigate("/") },
      { id: "sre-oncall", label: "View on-call schedule", category: "SRE Tools", icon: Bell, onSelect: () => navigate("/") },
      { id: "sre-runbook", label: "Search runbooks", category: "SRE Tools", icon: Terminal, onSelect: () => navigate("/agents") },
      { id: "sre-incident", label: "Declare incident", category: "SRE Tools", icon: AlertTriangle, onSelect: () => navigate("/alerts") },
      // Actions
      { id: "action-alert", label: "Create alert rule", category: "Actions", icon: Bell, onSelect: () => navigate("/alerts") },
      { id: "action-seed", label: "Seed demo data", category: "Actions", icon: Database, onSelect: () => navigate("/settings") },
      { id: "action-bench", label: "Run benchmarks", category: "Actions", icon: Play, onSelect: () => navigate("/settings") },
      // AI Agents
      { id: "agent-rca", label: "Run root cause analysis", category: "AI Agents", icon: Sparkles, onSelect: () => navigate("/agents") },
      { id: "agent-errors", label: "Ask AI: What are the top errors?", category: "AI Agents", icon: MessageSquare, onSelect: () => navigate("/agents") },
      { id: "agent-slow", label: "Ask AI: Which service is slowest?", category: "AI Agents", icon: MessageSquare, onSelect: () => navigate("/agents") },
      { id: "agent-anomaly", label: "Run anomaly detection", category: "AI Agents", icon: Zap, onSelect: () => navigate("/agents") },
    ],
    [navigate],
  );

  // Fuzzy match
  const filtered = useMemo(() => {
    if (!query.trim()) return items;
    const q = query.toLowerCase();
    return items.filter((item) => {
      const label = item.label.toLowerCase();
      const category = item.category.toLowerCase();
      let qi = 0;
      for (let i = 0; i < label.length && qi < q.length; i++) {
        if (label[i] === q[qi]) qi++;
      }
      return qi === q.length || category.includes(q) || label.includes(q);
    });
  }, [items, query]);

  // Group by category
  const grouped = useMemo(() => {
    const groups: Record<string, CommandItem[]> = {};
    for (const item of filtered) {
      if (!groups[item.category]) groups[item.category] = [];
      groups[item.category].push(item);
    }
    return groups;
  }, [filtered]);

  const flatFiltered = useMemo(() => filtered, [filtered]);

  // Reset selection when query changes
  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  // Keyboard shortcut to open
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Keyboard navigation inside palette
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      switch (e.key) {
        case "ArrowDown":
          e.preventDefault();
          setSelectedIndex((prev) =>
            prev < flatFiltered.length - 1 ? prev + 1 : 0,
          );
          break;
        case "ArrowUp":
          e.preventDefault();
          setSelectedIndex((prev) =>
            prev > 0 ? prev - 1 : flatFiltered.length - 1,
          );
          break;
        case "Enter":
          e.preventDefault();
          if (flatFiltered[selectedIndex]) {
            flatFiltered[selectedIndex].onSelect();
          }
          break;
      }
    },
    [flatFiltered, selectedIndex],
  );

  // Scroll selected item into view
  useEffect(() => {
    const el = listRef.current?.querySelector(`[data-index="${selectedIndex}"]`);
    if (el) {
      el.scrollIntoView({ block: "nearest" });
    }
  }, [selectedIndex]);

  // Category icons for visual emphasis
  const categoryIcons: Record<string, { icon: any; color: string }> = {
    "Navigation": { icon: Command, color: "text-text-muted/50" },
    "Search": { icon: Search, color: "text-cyan-400/50" },
    "SRE Tools": { icon: Terminal, color: "text-emerald-400/50" },
    "Actions": { icon: Zap, color: "text-amber-400/50" },
    "AI Agents": { icon: Sparkles, color: "text-purple-400/50" },
  };

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0" />
        <Dialog.Content
          className="fixed left-1/2 top-[18%] z-50 w-full max-w-[580px] -translate-x-1/2 rounded-xl border border-border-default/60 bg-surface-primary/95 backdrop-blur-xl shadow-2xl shadow-black/50 outline-none data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95 data-[state=open]:slide-in-from-top-2 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95"
          onKeyDown={handleKeyDown}
        >
          {/* Search input */}
          <div className="flex items-center gap-3 border-b border-border-default/40 px-4 py-3.5">
            <Search className="h-4 w-4 shrink-0 text-cyan-400/60" />
            <Dialog.Title className="sr-only">Command Palette</Dialog.Title>
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Type a command or search..."
              className="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-muted/60 outline-none"
              autoFocus
            />
            <kbd className="hidden sm:inline-flex items-center gap-0.5 rounded border border-border-default/40 bg-navy-800/40 px-1.5 py-0.5 text-[10px] font-medium text-text-muted/50">
              ESC
            </kbd>
          </div>

          {/* Results */}
          <div
            ref={listRef}
            className="max-h-[380px] overflow-y-auto py-2"
          >
            {flatFiltered.length === 0 ? (
              <div className="px-4 py-10 text-center">
                <Search className="mx-auto h-8 w-8 text-text-muted/20 mb-2" />
                <p className="text-sm text-text-muted">
                  No results for &ldquo;{query}&rdquo;
                </p>
              </div>
            ) : (
              Object.entries(grouped).map(([category, categoryItems]) => {
                const catConfig = categoryIcons[category];
                const CatIcon = catConfig?.icon;
                return (
                  <div key={category}>
                    <div className="flex items-center gap-1.5 px-4 py-1.5 text-[10px] font-semibold uppercase tracking-widest text-text-muted/50">
                      {CatIcon && <CatIcon className={cn("h-3 w-3", catConfig.color)} />}
                      {category}
                    </div>
                    {categoryItems.map((item) => {
                      const globalIndex = flatFiltered.indexOf(item);
                      const isSelected = globalIndex === selectedIndex;
                      return (
                        <button
                          key={item.id}
                          data-index={globalIndex}
                          onClick={() => {
                            item.onSelect();
                          }}
                          onMouseEnter={() => setSelectedIndex(globalIndex)}
                          className={cn(
                            "flex w-full items-center gap-3 px-4 py-2 text-sm transition-all duration-100",
                            isSelected
                              ? "bg-cyan-500/8 text-cyan-400"
                              : "text-text-secondary hover:bg-navy-800/40 hover:text-text-primary",
                          )}
                        >
                          <item.icon className={cn("h-4 w-4 shrink-0", isSelected && "text-cyan-400")} />
                          <span className="flex-1 text-left">{item.label}</span>
                          {item.shortcut && (
                            <kbd className="ml-auto inline-flex items-center gap-1 text-[10px] font-medium text-text-muted/50">
                              {item.shortcut.split(" ").map((key) => (
                                <span
                                  key={key}
                                  className="rounded border border-border-default/40 bg-navy-800/40 px-1 py-0.5"
                                >
                                  {key}
                                </span>
                              ))}
                            </kbd>
                          )}
                          {isSelected && (
                            <ArrowRight className="h-3 w-3 shrink-0 text-cyan-400/60" />
                          )}
                        </button>
                      );
                    })}
                  </div>
                );
              })
            )}
          </div>

          {/* Footer */}
          <div className="flex items-center gap-4 border-t border-border-default/40 px-4 py-2 text-[10px] text-text-muted/40">
            <span className="flex items-center gap-1">
              <kbd className="rounded border border-border-default/30 bg-navy-800/30 px-1 py-0.5">
                &uarr;&darr;
              </kbd>
              Navigate
            </span>
            <span className="flex items-center gap-1">
              <kbd className="rounded border border-border-default/30 bg-navy-800/30 px-1 py-0.5">
                &crarr;
              </kbd>
              Select
            </span>
            <span className="flex items-center gap-1">
              <kbd className="rounded border border-border-default/30 bg-navy-800/30 px-1 py-0.5">
                ESC
              </kbd>
              Close
            </span>
            <span className="ml-auto text-text-muted/30">
              {flatFiltered.length} results
            </span>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
