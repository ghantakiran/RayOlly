"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { Sidebar } from "@/components/shared/sidebar";
import { CommandPalette } from "@/components/shared/command-palette";
import { StatusBar } from "@/components/shared/status-bar";
import { KeyboardShortcuts } from "@/components/shared/keyboard-shortcuts";
import { ToastProvider } from "@/components/shared/toast";
import { useAppStore } from "@/stores/app";

/** Maps "g then X" second key to a route */
const gotoMap: Record<string, string> = {
  d: "/",
  l: "/logs",
  m: "/metrics",
  t: "/traces",
  a: "/agents",
  i: "/infrastructure",
  s: "/settings",
  r: "/alerts",
};

export function ClientLayout({ children }: { children: React.ReactNode }) {
  const collapsed = useAppStore((s) => s.sidebarCollapsed);
  const sidebarWidth = collapsed ? "4rem" : "14rem";
  const router = useRouter();
  const pendingGRef = useRef(false);
  const gTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Global "g then X" keyboard navigation
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      const target = e.target as HTMLElement;
      const isInput =
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.isContentEditable;

      if (isInput || e.metaKey || e.ctrlKey || e.altKey) return;

      if (pendingGRef.current) {
        pendingGRef.current = false;
        if (gTimerRef.current) clearTimeout(gTimerRef.current);
        const dest = gotoMap[e.key.toLowerCase()];
        if (dest) {
          e.preventDefault();
          router.push(dest);
        }
        return;
      }

      if (e.key === "g") {
        pendingGRef.current = true;
        gTimerRef.current = setTimeout(() => {
          pendingGRef.current = false;
        }, 800);
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      if (gTimerRef.current) clearTimeout(gTimerRef.current);
    };
  }, [router]);

  return (
    <ToastProvider>
      <div className="flex min-h-screen bg-navy-950 bg-grid noise-overlay">
        <Sidebar />
        <CommandPalette />
        <KeyboardShortcuts />

        {/* Main content area — offset by sidebar width, with room for status bar */}
        <main
          style={{ marginLeft: sidebarWidth }}
          className="min-h-screen flex-1 overflow-x-hidden pb-10 transition-all duration-200 page-enter"
        >
          <div className="mx-auto max-w-[1600px] px-6 py-5">{children}</div>
        </main>

        <StatusBar />
      </div>
    </ToastProvider>
  );
}
