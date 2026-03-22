"use client";

import { forwardRef, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { cva, type VariantProps } from "class-variance-authority";

// ── Badge ──────────────────────────────────────────────────────────

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-semibold leading-none transition-colors",
  {
    variants: {
      variant: {
        default: "bg-navy-700/80 text-text-secondary",
        success: "bg-emerald-500/12 text-emerald-400 border border-emerald-500/10",
        warning: "bg-amber-500/12 text-amber-400 border border-amber-500/10",
        error: "bg-red-500/12 text-red-400 border border-red-500/10",
        critical: "bg-red-600/15 text-red-300 border border-red-500/15",
        info: "bg-blue-500/12 text-blue-400 border border-blue-500/10",
        purple: "bg-purple-500/12 text-purple-400 border border-purple-500/10",
        cyan: "bg-cyan-500/12 text-cyan-400 border border-cyan-500/10",
        outline: "border border-border-default text-text-secondary",
      },
      size: {
        sm: "px-1.5 py-0.5 text-[10px]",
        md: "px-2 py-0.5 text-[11px]",
        lg: "px-2.5 py-1 text-xs",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "md",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {
  dot?: boolean;
  pulse?: boolean;
}

export function Badge({ className, variant, size, dot, pulse, children, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant, size }), className)} {...props}>
      {dot && (
        <span className={cn(
          "h-1.5 w-1.5 rounded-full bg-current",
          pulse && "animate-pulse"
        )} />
      )}
      {children}
    </span>
  );
}

// ── Button ─────────────────────────────────────────────────────────

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-lg text-sm font-medium transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/50 focus-visible:ring-offset-1 focus-visible:ring-offset-navy-950 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        primary: "bg-gradient-to-r from-cyan-500 to-cyan-600 text-navy-950 hover:from-cyan-400 hover:to-cyan-500 shadow-lg shadow-cyan-500/20 hover:shadow-cyan-500/30",
        secondary: "border border-border-default bg-surface-secondary text-text-secondary hover:bg-navy-700 hover:text-text-primary hover:border-navy-500",
        ghost: "text-text-secondary hover:bg-navy-700/50 hover:text-text-primary",
        danger: "bg-red-500/12 text-red-400 border border-red-500/15 hover:bg-red-500/20",
        success: "bg-emerald-500/12 text-emerald-400 border border-emerald-500/15 hover:bg-emerald-500/20",
      },
      size: {
        xs: "h-7 px-2 text-xs",
        sm: "h-8 px-3 text-xs",
        md: "h-9 px-4 text-sm",
        lg: "h-10 px-5 text-sm",
        icon: "h-8 w-8",
        "icon-sm": "h-7 w-7",
      },
    },
    defaultVariants: {
      variant: "secondary",
      size: "sm",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  loading?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, loading, children, disabled, ...props }, ref) => {
    return (
      <button
        className={cn(buttonVariants({ variant, size }), className)}
        ref={ref}
        disabled={disabled || loading}
        {...props}
      >
        {loading && (
          <svg className="h-3.5 w-3.5 animate-spin" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        )}
        {children}
      </button>
    );
  }
);
Button.displayName = "Button";

// ── Card ───────────────────────────────────────────────────────────

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "glass" | "elevated" | "bordered" | "interactive";
  padding?: "none" | "sm" | "md" | "lg";
  glow?: boolean;
}

export function Card({ className, variant = "default", padding = "md", glow, children, ...props }: CardProps) {
  const paddingMap = { none: "", sm: "p-3", md: "p-4", lg: "p-6" };
  const variantMap = {
    default: "rounded-xl border border-border-default bg-surface-secondary",
    glass: "glass-card rounded-xl",
    elevated: "card-elevated",
    bordered: "rounded-xl border border-border-default bg-surface-primary",
    interactive: "card-interactive rounded-xl",
  };

  return (
    <div
      className={cn(
        variantMap[variant],
        paddingMap[padding],
        glow && "glow-cyan",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardHeader({ className, children, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("flex items-center justify-between border-b border-border-default/60 px-4 py-3", className)} {...props}>
      {children}
    </div>
  );
}

export function CardTitle({ className, children, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3 className={cn("text-sm font-medium text-text-secondary", className)} {...props}>
      {children}
    </h3>
  );
}

// ── Input ──────────────────────────────────────────────────────────

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  icon?: ReactNode;
  suffix?: ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, icon, suffix, ...props }, ref) => {
    return (
      <div className="relative">
        {icon && (
          <div className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-muted">
            {icon}
          </div>
        )}
        <input
          ref={ref}
          className={cn(
            "w-full rounded-lg border border-border-default bg-surface-secondary py-2 text-sm text-text-primary placeholder:text-text-muted",
            "focus:border-cyan-500/50 focus:outline-none focus:ring-1 focus:ring-cyan-500/30 transition-all duration-150",
            icon ? "pl-10" : "pl-3",
            suffix ? "pr-10" : "pr-3",
            className,
          )}
          {...props}
        />
        {suffix && (
          <div className="absolute right-3 top-1/2 -translate-y-1/2">
            {suffix}
          </div>
        )}
      </div>
    );
  }
);
Input.displayName = "Input";

// ── MetricCard ─────────────────────────────────────────────────────

export interface MetricCardProps {
  label: string;
  value: string | number;
  suffix?: string;
  description?: string;
  trend?: { direction: "up" | "down" | "flat"; value: string; positive?: boolean };
  icon?: ReactNode;
  className?: string;
  variant?: "default" | "compact";
}

export function MetricCard({ label, value, suffix, description, trend, icon, className, variant = "default" }: MetricCardProps) {
  if (variant === "compact") {
    return (
      <div className={cn("flex items-center gap-3 rounded-lg border border-border-default bg-surface-secondary px-3 py-2", className)}>
        {icon && <div className="shrink-0 text-text-muted">{icon}</div>}
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-medium uppercase tracking-wider text-text-muted">{label}</p>
          <p className="metric-value text-lg font-bold text-text-primary">
            {value}{suffix && <span className="ml-0.5 text-xs font-normal text-text-muted">{suffix}</span>}
          </p>
        </div>
        {trend && (
          <span className={cn(
            "text-[11px] font-medium",
            trend.positive === true ? "text-emerald-400" : trend.positive === false ? "text-red-400" : "text-text-muted",
          )}>
            {trend.direction === "up" ? "\u2191" : trend.direction === "down" ? "\u2193" : "\u2192"} {trend.value}
          </span>
        )}
      </div>
    );
  }

  return (
    <div className={cn("rounded-xl border border-border-default bg-surface-secondary p-4", className)}>
      <div className="flex items-center justify-between">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">{label}</p>
        {icon && <div className="text-text-muted">{icon}</div>}
      </div>
      <p className="metric-value mt-2 text-3xl font-bold text-text-primary">
        {value}{suffix && <span className="ml-1 text-sm font-normal text-text-muted">{suffix}</span>}
      </p>
      {(description || trend) && (
        <div className="mt-1 flex items-center gap-2">
          {trend && (
            <span className={cn(
              "text-xs font-medium",
              trend.positive === true ? "text-emerald-400" : trend.positive === false ? "text-red-400" : "text-text-muted",
            )}>
              {trend.direction === "up" ? "\u2191" : trend.direction === "down" ? "\u2193" : "\u2192"} {trend.value}
            </span>
          )}
          {description && <span className="text-xs text-text-muted">{description}</span>}
        </div>
      )}
    </div>
  );
}

// ── StatusDot ──────────────────────────────────────────────────────

export function StatusDot({ status, pulse, size = "md", className }: {
  status: "ok" | "warning" | "error" | "critical" | "unknown" | "idle";
  pulse?: boolean;
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  const colorMap = {
    ok: "bg-emerald-400",
    warning: "bg-amber-400",
    error: "bg-red-400",
    critical: "bg-red-500",
    unknown: "bg-slate-400",
    idle: "bg-slate-500",
  };
  const glowMap = {
    ok: "shadow-[0_0_6px_rgba(34,197,94,0.4)]",
    warning: "shadow-[0_0_6px_rgba(234,179,8,0.4)]",
    error: "shadow-[0_0_6px_rgba(239,68,68,0.4)]",
    critical: "shadow-[0_0_6px_rgba(239,68,68,0.5)]",
    unknown: "",
    idle: "",
  };
  const pulseMap = {
    ok: "pulse-ok",
    warning: "pulse-warning",
    error: "pulse-critical",
    critical: "pulse-critical",
    unknown: "",
    idle: "",
  };
  const sizeMap = { sm: "h-1.5 w-1.5", md: "h-2 w-2", lg: "h-2.5 w-2.5" };

  return (
    <span
      className={cn(
        "relative inline-block rounded-full",
        colorMap[status],
        sizeMap[size],
        glowMap[status],
        pulse && pulseMap[status],
        className,
      )}
    />
  );
}

// ── EmptyState ─────────────────────────────────────────────────────

export function EmptyState({ icon, title, description, action, className }: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center py-16 px-4", className)}>
      {icon && <div className="mb-4 text-text-muted/30">{icon}</div>}
      <p className="text-sm font-medium text-text-muted">{title}</p>
      {description && <p className="mt-1 text-xs text-text-muted/70">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

// ── SectionHeader ──────────────────────────────────────────────────

export function SectionHeader({ title, subtitle, actions, className }: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex items-center justify-between", className)}>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-text-primary">{title}</h1>
        {subtitle && <p className="mt-0.5 text-sm text-text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

// ── ProgressBar ────────────────────────────────────────────────────

export function ProgressBar({ value, max = 100, variant = "default", size = "md", showLabel, className }: {
  value: number;
  max?: number;
  variant?: "default" | "success" | "warning" | "error" | "gradient";
  size?: "sm" | "md" | "lg";
  showLabel?: boolean;
  className?: string;
}) {
  const pct = Math.min((value / max) * 100, 100);
  const colorMap = {
    default: "bg-cyan-500",
    success: "bg-emerald-500",
    warning: "bg-amber-500",
    error: "bg-red-500",
    gradient: pct > 90 ? "bg-red-500" : pct > 70 ? "bg-amber-500" : "bg-emerald-500",
  };
  const sizeMap = { sm: "h-1", md: "h-1.5", lg: "h-2" };

  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className={cn("flex-1 overflow-hidden rounded-full bg-navy-700/60", sizeMap[size])}>
        <div
          className={cn("h-full rounded-full transition-all duration-500 ease-out", colorMap[variant])}
          style={{ width: `${pct}%` }}
        />
      </div>
      {showLabel && (
        <span className="metric-value shrink-0 text-xs text-text-muted w-10 text-right">
          {pct.toFixed(0)}%
        </span>
      )}
    </div>
  );
}

// ── KeyValue ───────────────────────────────────────────────────────

export function KeyValue({ label, value, mono, className }: {
  label: string;
  value: ReactNode;
  mono?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("flex items-baseline gap-2 text-xs", className)}>
      <span className="w-28 shrink-0 text-text-muted truncate">{label}</span>
      <span className={cn("text-text-primary break-all", mono && "font-mono")}>{value}</span>
    </div>
  );
}

// ── Divider ────────────────────────────────────────────────────────

export function Divider({ label, className }: { label?: string; className?: string }) {
  if (label) {
    return (
      <div className={cn("flex items-center gap-3", className)}>
        <div className="h-px flex-1 bg-gradient-to-r from-border-default to-transparent" />
        <span className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">{label}</span>
        <div className="h-px flex-1 bg-gradient-to-l from-border-default to-transparent" />
      </div>
    );
  }
  return <div className={cn("h-px bg-border-default", className)} />;
}

// ── LiveIndicator ──────────────────────────────────────────────────

export function LiveIndicator({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-[11px] font-medium text-emerald-400", className)}>
      <span className="relative flex h-2 w-2">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
        <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
      </span>
      Live
    </span>
  );
}

// ── Kbd (keyboard shortcut display) ────────────────────────────────

export function Kbd({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <kbd className={cn(
      "inline-flex items-center rounded border border-border-default/60 bg-navy-800/60 px-1.5 py-0.5 text-[10px] font-medium text-text-muted/80",
      className,
    )}>
      {children}
    </kbd>
  );
}

// ── UptimeBar (SRE widget) ─────────────────────────────────────────

export function UptimeBar({ data, className }: {
  data: { status: "ok" | "degraded" | "down" | "unknown"; label?: string }[];
  className?: string;
}) {
  const colorMap = {
    ok: "bg-emerald-500",
    degraded: "bg-amber-500",
    down: "bg-red-500",
    unknown: "bg-navy-600",
  };

  return (
    <div className={cn("uptime-bar", className)}>
      {data.map((segment, i) => (
        <div
          key={i}
          className={cn("uptime-bar-segment", colorMap[segment.status])}
          title={segment.label || segment.status}
        />
      ))}
    </div>
  );
}

// ── MiniSparkline (inline sparkline for metrics) ───────────────────

export function MiniSparkline({ data, color = "bg-cyan-400", height = 20, className }: {
  data: number[];
  color?: string;
  height?: number;
  className?: string;
}) {
  const max = Math.max(...data, 1);

  return (
    <div className={cn("flex items-end gap-[2px]", className)} style={{ height }}>
      {data.map((v, i) => {
        const h = Math.max((v / max) * 100, 4);
        return (
          <div
            key={i}
            className={cn("flex-1 min-w-[2px] rounded-t-sm", color)}
            style={{
              height: `${h}%`,
              opacity: 0.3 + (i / data.length) * 0.7,
            }}
          />
        );
      })}
    </div>
  );
}

// ── Exports for variant functions ──────────────────────────────────
export { badgeVariants, buttonVariants };
