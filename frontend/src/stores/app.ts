import { create } from "zustand";
import type { TimeRange } from "@/types";

interface AppState {
  timeRange: TimeRange;
  selectedService: string | null;
  sidebarCollapsed: boolean;
  theme: "dark" | "light";

  setTimeRange: (range: TimeRange) => void;
  setSelectedService: (service: string | null) => void;
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setTheme: (theme: "dark" | "light") => void;
}

export const useAppStore = create<AppState>((set) => ({
  timeRange: {
    from: new Date(Date.now() - 24 * 60 * 60 * 1000),
    to: new Date(),
    label: "Last 24h",
  },
  selectedService: null,
  sidebarCollapsed: false,
  theme: "dark",

  setTimeRange: (range) => set({ timeRange: range }),
  setSelectedService: (service) => set({ selectedService: service }),
  toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
  setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
  setTheme: (theme) => set({ theme }),
}));
