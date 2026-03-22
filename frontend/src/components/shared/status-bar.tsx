"use client";

import { useEffect, useState, useMemo } from "react";
import { useAppStore } from "@/stores/app";
import { cn } from "@/lib/utils";
import {
  Wifi,
  WifiOff,
  Clock,
  Gauge,
  ChevronRight,
  Terminal,
  Cpu,
} from "lucide-react";

interface ServiceStatus {
  name: string;
  connected: boolean;
}

export function StatusBar() {
  const [services, setServices] = useState<ServiceStatus[]>([
    { name: "ClickHouse", connected: true },
    { name: "NATS", connected: true },
    { name: "Redis", connected: true },
    { name: "Postgres", connected: true },
    { name: "MinIO", connected: true },
  ]);
  const [ingestionRate, setIngestionRate] = useState<number | null>(null);
  const [latencyP99, setLatencyP99] = useState<number | null>(null);
  const [deployVersion, setDeployVersion] = useState("v2.4.1");
  const [currentTime, setCurrentTime] = useState("");
  const timeRange = useAppStore((s) => s.timeRange);

  // Clock update
  useEffect(() => {
    function updateTime() {
      setCurrentTime(
        new Date().toLocaleTimeString("en-US", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
          hour12: false,
        })
      );
    }
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    let mounted = true;

    async function fetchStatus() {
      try {
        const res = await fetch("/api/v1/status");
        if (!res.ok) return;
        const data = await res.json();
        if (!mounted) return;
        if (data.services) setServices(data.services);
        if (typeof data.ingestionRate === "number") setIngestionRate(data.ingestionRate);
        if (typeof data.latencyP99 === "number") setLatencyP99(data.latencyP99);
        if (data.version) setDeployVersion(data.version);
      } catch {
        // Silently fail — status bar is non-critical
      }
    }

    fetchStatus();
    const interval = setInterval(fetchStatus, 30_000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  const allConnected = services.every((s) => s.connected);
  const disconnectedCount = services.filter((s) => !s.connected).length;

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 flex h-[26px] items-center justify-between border-t border-border-default/60 bg-surface-primary/95 backdrop-blur-sm px-4 text-[11px] text-text-muted">
      {/* Left: connection status */}
      <div className="flex items-center gap-3">
        {/* Overall health indicator */}
        <div className="flex items-center gap-1.5">
          <span
            className={cn(
              "inline-block h-[6px] w-[6px] rounded-full transition-colors",
              allConnected ? "bg-emerald-400 shadow-[0_0_6px_rgba(34,197,94,0.4)]" : "bg-red-400 shadow-[0_0_6px_rgba(239,68,68,0.4)]",
            )}
          />
          <span className={cn(
            "font-medium",
            allConnected ? "text-emerald-400/80" : "text-red-400/80",
          )}>
            {allConnected ? "All systems operational" : `${disconnectedCount} down`}
          </span>
        </div>

        <span className="text-border-default/60">|</span>

        {/* Individual services - compact */}
        <div className="flex items-center gap-2">
          {services.map((svc) => (
            <div
              key={svc.name}
              className="flex items-center gap-1"
              title={`${svc.name}: ${svc.connected ? "Connected" : "Disconnected"}`}
            >
              <span
                className={cn(
                  "inline-block h-[5px] w-[5px] rounded-full transition-colors",
                  svc.connected ? "bg-emerald-400/50" : "bg-red-400",
                )}
              />
              <span className={cn(
                "text-[10px]",
                !svc.connected && "text-red-400 font-medium",
              )}>
                {svc.name}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Center: env + version + tenant */}
      <div className="flex items-center gap-2.5">
        <span className="inline-flex items-center gap-1 rounded border border-red-500/20 bg-red-500/8 px-1.5 py-0 text-[9px] font-bold uppercase tracking-wider text-red-400">
          prod
        </span>
        <span className="text-text-muted/30">&middot;</span>
        <span className="text-text-secondary font-mono text-[10px]">{deployVersion}</span>
        <span className="text-text-muted/30">&middot;</span>
        <span className="text-text-muted text-[10px]">default</span>
        <span className="text-text-muted/30">&middot;</span>
        <span className="text-text-secondary text-[10px]">admin</span>
      </div>

      {/* Right: metrics + time + shortcuts */}
      <div className="flex items-center gap-3">
        {ingestionRate !== null && (
          <span className="flex items-center gap-1 font-mono text-[10px]" style={{ fontFeatureSettings: '"tnum"' }}>
            <Gauge className="h-3 w-3 text-text-muted/50" />
            <span className="text-cyan-400/80">{ingestionRate.toLocaleString()}/m</span>
          </span>
        )}
        {latencyP99 !== null && (
          <span className="flex items-center gap-1 font-mono text-[10px]" style={{ fontFeatureSettings: '"tnum"' }}>
            <span className="text-text-muted/50">p99</span>
            <span className={cn(
              latencyP99 > 500 ? "text-red-400" : latencyP99 > 200 ? "text-amber-400" : "text-emerald-400/80",
            )}>
              {latencyP99}ms
            </span>
          </span>
        )}
        {timeRange.label && (
          <span className="flex items-center gap-1 text-text-muted/60 text-[10px]">
            <Clock className="h-3 w-3" />
            {timeRange.label}
          </span>
        )}
        <span className="text-text-muted/30">|</span>
        <span className="font-mono text-[10px] text-text-secondary tabular-nums">{currentTime}</span>
        <kbd className="rounded border border-border-default/60 bg-navy-800/60 px-1 py-0.5 text-[9px] font-medium text-text-muted/60">
          &#8984;K
        </kbd>
      </div>
    </div>
  );
}
