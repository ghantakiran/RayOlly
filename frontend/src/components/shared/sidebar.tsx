"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import * as Tooltip from "@radix-ui/react-tooltip";
import {
  LayoutDashboard,
  FileText,
  BarChart3,
  GitBranch,
  Bell,
  LayoutGrid,
  Bot,
  Settings,
  ChevronLeft,
  ChevronRight,
  Zap,
  Activity,
  Server,
  Globe,
  FlaskConical,
  MonitorSmartphone,
  Eye,
  Puzzle,
  Command,
  Shield,
  Flame,
  Terminal,
  Workflow,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/stores/app";

interface NavItem {
  href: string;
  label: string;
  icon: any;
  badge?: string | number | null;
}

interface NavSection {
  title: string;
  items: NavItem[];
}

export function Sidebar() {
  const pathname = usePathname();
  const collapsed = useAppStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useAppStore((s) => s.toggleSidebar);
  const [alertCount, setAlertCount] = useState<number | null>(null);

  // Fetch active alert count
  useEffect(() => {
    let mounted = true;

    async function fetchAlertCount() {
      try {
        const res = await fetch("/api/v1/alerts?state=firing");
        if (!res.ok) return;
        const data = await res.json();
        if (!mounted) return;
        const count = Array.isArray(data) ? data.length : data?.count ?? null;
        setAlertCount(typeof count === "number" ? count : null);
      } catch {
        // Non-critical
      }
    }

    fetchAlertCount();
    const interval = setInterval(fetchAlertCount, 60_000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  const navSections: NavSection[] = [
    {
      title: "Overview",
      items: [
        { href: "/", label: "Dashboard", icon: LayoutDashboard },
      ],
    },
    {
      title: "Observability",
      items: [
        { href: "/logs", label: "Logs", icon: FileText },
        { href: "/metrics", label: "Metrics", icon: BarChart3 },
        { href: "/traces", label: "Traces", icon: GitBranch },
        { href: "/apm", label: "APM", icon: Activity },
        { href: "/infrastructure", label: "Infrastructure", icon: Server },
      ],
    },
    {
      title: "Digital Experience",
      items: [
        { href: "/rum", label: "RUM", icon: MonitorSmartphone },
        { href: "/synthetics", label: "Synthetics", icon: FlaskConical },
        { href: "/experience", label: "DEM", icon: Globe },
      ],
    },
    {
      title: "Intelligence",
      items: [
        { href: "/agents", label: "AI Agents", icon: Bot, badge: "AI" },
        { href: "/agents/observability", label: "Agent Insights", icon: Eye },
        {
          href: "/alerts",
          label: "Alerts",
          icon: Bell,
          badge: alertCount !== null && alertCount > 0 ? alertCount : null,
        },
      ],
    },
    {
      title: "Platform",
      items: [
        { href: "/dashboards", label: "Dashboards", icon: LayoutGrid },
        { href: "/integrations", label: "Integrations", icon: Puzzle },
        { href: "/settings", label: "Settings", icon: Settings },
      ],
    },
  ];

  return (
    <Tooltip.Provider delayDuration={200} skipDelayDuration={0}>
      <aside
        className={cn(
          "fixed left-0 top-0 z-40 flex h-screen flex-col border-r border-border-default/80 bg-surface-primary/95 backdrop-blur-xl transition-all duration-200 ease-in-out",
          collapsed ? "w-16" : "w-56",
        )}
      >
        {/* Logo */}
        <div className="flex h-14 items-center gap-2.5 border-b border-border-default/60 px-4">
          <div className="sidebar-logo-icon flex h-8 w-8 shrink-0 items-center justify-center rounded-lg">
            <Zap className="h-4.5 w-4.5 text-cyan-400" />
          </div>
          <span
            className={cn(
              "text-lg font-bold tracking-tight text-text-primary transition-opacity duration-200",
              collapsed ? "w-0 opacity-0 overflow-hidden" : "opacity-100",
            )}
          >
            Ray<span className="text-shimmer">Olly</span>
          </span>
        </div>

        {/* Environment Indicator */}
        <div className={cn(
          "mx-3 mt-2 mb-1 flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-[10px] font-semibold uppercase tracking-wider transition-all",
          "env-production",
          collapsed && "mx-2 justify-center px-1.5",
        )}>
          <Shield className="h-3 w-3 shrink-0" />
          <span className={cn(
            "transition-opacity duration-200",
            collapsed ? "w-0 opacity-0 overflow-hidden" : "opacity-100",
          )}>
            Production
          </span>
        </div>

        {/* Nav links */}
        <nav className="flex-1 space-y-0.5 overflow-y-auto px-2 py-3">
          {navSections.map((section, sIdx) => (
            <div key={section.title} className="mb-1">
              {sIdx > 0 && !collapsed && (
                <div className="sidebar-section-line mx-3 my-2" />
              )}
              <div
                className={cn(
                  "mb-1 px-3 text-[10px] font-semibold uppercase tracking-widest text-text-muted/70 transition-opacity duration-200",
                  collapsed ? "opacity-0 h-0 mb-0 overflow-hidden" : "opacity-100",
                )}
              >
                {section.title}
              </div>
              {section.items.map((item) => {
                const isActive =
                  item.href === "/"
                    ? pathname === "/"
                    : pathname.startsWith(item.href);

                const linkContent = (
                  <Link
                    href={item.href}
                    className={cn(
                      "group relative flex items-center gap-3 rounded-lg px-3 py-1.5 text-sm font-medium transition-all duration-150",
                      isActive
                        ? "nav-link-active text-cyan-400"
                        : "text-text-secondary hover:bg-navy-700/50 hover:text-text-primary",
                      collapsed && "justify-center px-2",
                    )}
                  >
                    <item.icon className={cn(
                      "h-4 w-4 shrink-0 transition-colors",
                      isActive && "drop-shadow-[0_0_6px_rgba(6,182,212,0.4)]",
                    )} />
                    <span
                      className={cn(
                        "flex-1 transition-opacity duration-200",
                        collapsed ? "w-0 opacity-0 overflow-hidden" : "opacity-100",
                      )}
                    >
                      {item.label}
                    </span>
                    {/* Badge */}
                    {item.badge !== null && item.badge !== undefined && !collapsed && (
                      <span
                        className={cn(
                          "ml-auto inline-flex items-center justify-center rounded-full text-[10px] font-semibold transition-opacity duration-200",
                          typeof item.badge === "number"
                            ? "min-w-[18px] h-[18px] px-1 bg-severity-critical/20 text-severity-critical"
                            : "px-1.5 py-0.5 bg-cyan-500/15 text-cyan-400 text-[9px]",
                        )}
                      >
                        {item.badge}
                      </span>
                    )}
                  </Link>
                );

                // Show tooltip when sidebar is collapsed
                if (collapsed) {
                  return (
                    <Tooltip.Root key={item.href}>
                      <Tooltip.Trigger asChild>{linkContent}</Tooltip.Trigger>
                      <Tooltip.Portal>
                        <Tooltip.Content
                          side="right"
                          sideOffset={8}
                          className="z-50 rounded-lg bg-navy-700/95 backdrop-blur-sm px-3 py-2 text-xs font-medium text-text-primary shadow-xl border border-border-default/50"
                        >
                          <div className="flex items-center gap-2">
                            {item.label}
                            {item.badge !== null && item.badge !== undefined && (
                              <span
                                className={cn(
                                  "inline-flex items-center justify-center rounded-full text-[9px] font-semibold",
                                  typeof item.badge === "number"
                                    ? "min-w-[16px] h-[16px] px-0.5 bg-severity-critical/20 text-severity-critical"
                                    : "px-1 py-0.5 bg-cyan-500/15 text-cyan-400",
                                )}
                              >
                                {item.badge}
                              </span>
                            )}
                          </div>
                          <Tooltip.Arrow className="fill-navy-700/95" />
                        </Tooltip.Content>
                      </Tooltip.Portal>
                    </Tooltip.Root>
                  );
                }

                return <div key={item.href}>{linkContent}</div>;
              })}
            </div>
          ))}
        </nav>

        {/* Active Incident Strip */}
        <div className={cn(
          "mx-2 mb-2 overflow-hidden rounded-lg incident-banner px-3 py-2 cursor-pointer transition-all hover:opacity-90",
          collapsed && "mx-1 px-1.5",
        )}>
          <div className="flex items-center gap-2">
            <Flame className="h-3.5 w-3.5 shrink-0 text-red-400" />
            <div className={cn(
              "min-w-0 transition-opacity duration-200",
              collapsed ? "w-0 opacity-0 overflow-hidden" : "opacity-100",
            )}>
              <p className="text-[10px] font-semibold text-red-300 truncate">INC-2847 Active</p>
              <p className="text-[9px] text-red-400/70 truncate">payment-service degraded</p>
            </div>
          </div>
        </div>

        {/* Bottom section: shortcut hint + collapse toggle */}
        <div className="border-t border-border-default/60 p-2 space-y-1">
          {/* Command palette hint */}
          <button
            onClick={() => {
              document.dispatchEvent(
                new KeyboardEvent("keydown", {
                  key: "k",
                  metaKey: true,
                  bubbles: true,
                }),
              );
            }}
            className={cn(
              "flex w-full items-center gap-2.5 rounded-lg px-3 py-1.5 text-text-muted transition-all duration-150 hover:bg-navy-700/50 hover:text-text-primary",
              collapsed && "justify-center px-2",
            )}
          >
            <Command className="h-3.5 w-3.5 shrink-0" />
            <span
              className={cn(
                "text-xs transition-opacity duration-200",
                collapsed ? "w-0 opacity-0 overflow-hidden" : "opacity-100",
              )}
            >
              Search
            </span>
            {!collapsed && (
              <kbd className="ml-auto rounded border border-border-default bg-navy-800/80 px-1 py-0.5 text-[10px] font-medium text-text-muted/80">
                &#8984;K
              </kbd>
            )}
          </button>

          {/* On-call indicator */}
          <div className={cn(
            "flex items-center gap-2.5 rounded-lg px-3 py-1.5 text-text-muted",
            collapsed && "justify-center px-2",
          )}>
            <span className="relative flex h-2 w-2 shrink-0">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
            </span>
            <span className={cn(
              "text-xs text-emerald-400 transition-opacity duration-200",
              collapsed ? "w-0 opacity-0 overflow-hidden" : "opacity-100",
            )}>
              On-call
            </span>
          </div>

          {/* Collapse toggle */}
          <button
            onClick={toggleSidebar}
            className="flex w-full items-center justify-center rounded-lg p-2 text-text-muted/60 transition-all duration-150 hover:bg-navy-700/50 hover:text-text-primary"
          >
            {collapsed ? (
              <ChevronRight className="h-4 w-4" />
            ) : (
              <ChevronLeft className="h-4 w-4" />
            )}
          </button>
        </div>
      </aside>
    </Tooltip.Provider>
  );
}
