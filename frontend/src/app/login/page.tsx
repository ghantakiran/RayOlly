"use client";

import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Zap, Loader2 } from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await fetch("/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Login failed");
      }

      const data = await res.json();
      localStorage.setItem("rayolly_token", data.access_token);
      localStorage.setItem("rayolly_user", JSON.stringify(data.user));
      router.push("/");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-navy-950 bg-grid px-4">
      {/* Decorative background orbs */}
      <div className="pointer-events-none fixed -left-32 top-1/4 h-80 w-80 rounded-full bg-cyan-500/[0.05] blur-[100px]" />
      <div className="pointer-events-none fixed -right-32 bottom-1/4 h-80 w-80 rounded-full bg-accent-indigo/[0.05] blur-[100px]" />
      <div className="pointer-events-none fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 h-[600px] w-[600px] rounded-full bg-cyan-500/[0.02] blur-[120px]" />

      <div className="w-full max-w-sm relative z-10">
        {/* Logo / brand */}
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-cyan-400 to-accent-indigo shadow-xl shadow-cyan-500/25 glow-cyan">
            <Zap className="h-7 w-7 text-white" />
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-text-primary">
            Ray<span className="text-shimmer">Olly</span>
          </h1>
          <p className="mt-1.5 text-sm text-text-muted">
            AI-Native Observability Platform
          </p>
        </div>

        {/* Login card */}
        <form
          onSubmit={handleSubmit}
          className="glass-aurora rounded-2xl p-6 shadow-2xl shadow-black/30"
        >
          <h2 className="mb-5 text-lg font-semibold text-text-primary">
            Sign in to your account
          </h2>

          {error && (
            <div className="mb-4 rounded-lg border border-severity-critical/20 bg-severity-critical/8 px-3 py-2.5 text-sm text-severity-critical">
              {error}
            </div>
          )}

          <div className="space-y-4">
            <div className="space-y-1.5">
              <label
                htmlFor="email"
                className="text-sm font-medium text-text-secondary"
              >
                Email
              </label>
              <input
                id="email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="w-full rounded-lg border border-border-default/60 bg-navy-800/40 px-3 py-2.5 text-sm text-text-primary placeholder:text-text-muted/50 focus:border-cyan-500/50 focus:outline-none focus:ring-1 focus:ring-cyan-500/30 transition-all duration-150"
              />
            </div>

            <div className="space-y-1.5">
              <label
                htmlFor="password"
                className="text-sm font-medium text-text-secondary"
              >
                Password
              </label>
              <input
                id="password"
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter password"
                className="w-full rounded-lg border border-border-default/60 bg-navy-800/40 px-3 py-2.5 text-sm text-text-primary placeholder:text-text-muted/50 focus:border-cyan-500/50 focus:outline-none focus:ring-1 focus:ring-cyan-500/30 transition-all duration-150"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="mt-6 w-full flex items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-cyan-500 to-cyan-600 px-4 py-2.5 text-sm font-semibold text-navy-950 shadow-lg shadow-cyan-500/20 transition-all duration-200 hover:from-cyan-400 hover:to-cyan-500 hover:shadow-cyan-500/30 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Signing in...
              </>
            ) : (
              "Sign in"
            )}
          </button>

          <p className="mt-5 text-center text-xs text-text-muted/60">
            Demo: use any email with password{" "}
            <code className="rounded bg-navy-800/40 px-1.5 py-0.5 text-cyan-400/80 font-mono">
              demo
            </code>
          </p>
        </form>

        {/* Footer */}
        <p className="mt-8 text-center text-[10px] text-text-muted/30">
          Enterprise AI-native observability &middot; Logs &middot; Metrics &middot; Traces
        </p>
      </div>
    </div>
  );
}
