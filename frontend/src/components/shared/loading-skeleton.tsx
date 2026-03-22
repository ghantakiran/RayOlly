"use client";

import { cn } from "@/lib/utils";

function Shimmer({ className, style }: { className?: string; style?: React.CSSProperties }) {
  return (
    <div
      className={cn("skeleton", className)}
      style={style}
    />
  );
}

export function CardSkeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "rounded-xl border border-border-default/60 bg-surface-secondary p-4",
        className,
      )}
    >
      <Shimmer className="mb-3 h-4 w-1/3" />
      <Shimmer className="mb-2 h-8 w-2/3" />
      <Shimmer className="h-3 w-1/2" />
    </div>
  );
}

export function TableSkeleton({
  rows = 5,
  columns = 4,
  className,
}: {
  rows?: number;
  columns?: number;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-xl border border-border-default/60 bg-surface-secondary overflow-hidden",
        className,
      )}
    >
      {/* Header */}
      <div className="flex gap-4 border-b border-border-default px-4 py-3">
        {Array.from({ length: columns }).map((_, i) => (
          <Shimmer key={i} className="h-3 flex-1" />
        ))}
      </div>
      {/* Rows */}
      {Array.from({ length: rows }).map((_, r) => (
        <div
          key={r}
          className="flex gap-4 border-b border-border-subtle px-4 py-3 last:border-b-0"
        >
          {Array.from({ length: columns }).map((_, c) => (
            <Shimmer
              key={c}
              className="h-3 flex-1"
            />
          ))}
        </div>
      ))}
    </div>
  );
}

export function ChartSkeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "rounded-xl border border-border-default/60 bg-surface-secondary p-4",
        className,
      )}
    >
      <Shimmer className="mb-4 h-4 w-1/4" />
      <div className="flex items-end gap-1 h-32">
        {Array.from({ length: 12 }).map((_, i) => (
          <Shimmer
            key={i}
            className="flex-1 rounded-t-sm"
            style={{ height: `${20 + Math.random() * 80}%` }}
          />
        ))}
      </div>
    </div>
  );
}

export function TextSkeleton({
  lines = 3,
  className,
}: {
  lines?: number;
  className?: string;
}) {
  return (
    <div className={cn("space-y-2", className)}>
      {Array.from({ length: lines }).map((_, i) => (
        <Shimmer
          key={i}
          className="h-3"
          style={{ width: i === lines - 1 ? "60%" : "100%" }}
        />
      ))}
    </div>
  );
}
