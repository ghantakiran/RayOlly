"use client";

import { useState } from "react";
import { Clock, ChevronDown } from "lucide-react";
import * as Popover from "@radix-ui/react-popover";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/stores/app";
import type { TimeRange } from "@/types";

const presets: { label: string; duration: number }[] = [
  { label: "Last 15m", duration: 15 * 60 * 1000 },
  { label: "Last 1h", duration: 60 * 60 * 1000 },
  { label: "Last 6h", duration: 6 * 60 * 60 * 1000 },
  { label: "Last 24h", duration: 24 * 60 * 60 * 1000 },
  { label: "Last 7d", duration: 7 * 24 * 60 * 60 * 1000 },
  { label: "Last 30d", duration: 30 * 24 * 60 * 60 * 1000 },
];

export function TimeRangePicker() {
  const timeRange = useAppStore((s) => s.timeRange);
  const setTimeRange = useAppStore((s) => s.setTimeRange);
  const [open, setOpen] = useState(false);

  const handlePreset = (preset: { label: string; duration: number }) => {
    const now = new Date();
    const range: TimeRange = {
      from: new Date(now.getTime() - preset.duration),
      to: now,
      label: preset.label,
    };
    setTimeRange(range);
    setOpen(false);
  };

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <button
          className={cn(
            "flex items-center gap-2 rounded-lg border border-border-default bg-surface-secondary px-3 py-1.5 text-sm text-text-secondary transition-colors hover:border-navy-500 hover:text-text-primary",
          )}
        >
          <Clock className="h-3.5 w-3.5" />
          <span>{timeRange.label || "Custom"}</span>
          <ChevronDown className="h-3 w-3" />
        </button>
      </Popover.Trigger>

      <Popover.Portal>
        <Popover.Content
          align="end"
          sideOffset={8}
          className="z-50 w-56 rounded-xl border border-border-default bg-surface-primary p-2 shadow-xl shadow-black/30"
        >
          <div className="space-y-0.5">
            {presets.map((preset) => (
              <button
                key={preset.label}
                onClick={() => handlePreset(preset)}
                className={cn(
                  "flex w-full items-center rounded-lg px-3 py-2 text-sm transition-colors",
                  timeRange.label === preset.label
                    ? "bg-cyan-500/10 text-cyan-400"
                    : "text-text-secondary hover:bg-navy-700 hover:text-text-primary",
                )}
              >
                {preset.label}
              </button>
            ))}
          </div>
          <div className="mt-2 border-t border-border-default pt-2">
            <p className="px-3 py-1 text-xs text-text-muted">
              Custom range (coming soon)
            </p>
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
