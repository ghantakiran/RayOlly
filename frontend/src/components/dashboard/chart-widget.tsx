"use client";

import dynamic from "next/dynamic";
import type { EChartsOption } from "echarts";

const ReactECharts = dynamic(() => import("echarts-for-react"), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center rounded-lg border border-border-default/60 bg-surface-secondary animate-pulse">
      <span className="text-xs text-text-muted">Loading chart...</span>
    </div>
  ),
});

interface ChartWidgetProps {
  title?: string;
  type: "line" | "bar" | "area";
  xData: string[];
  series: {
    name: string;
    data: number[];
    color?: string;
  }[];
  height?: number;
  showLegend?: boolean;
  yAxisLabel?: string;
}

const THEME_COLORS = [
  "#06b6d4", // cyan
  "#3b82f6", // blue
  "#6366f1", // indigo
  "#22c55e", // green
  "#eab308", // yellow
  "#f97316", // orange
  "#ef4444", // red
  "#a855f7", // purple
];

export function ChartWidget({
  title,
  type,
  xData,
  series,
  height = 280,
  showLegend = true,
  yAxisLabel,
}: ChartWidgetProps) {
  const option: EChartsOption = {
    backgroundColor: "transparent",
    title: title
      ? {
          text: title,
          textStyle: { color: "#94a3b8", fontSize: 13, fontWeight: 500, fontFamily: "Inter, system-ui, sans-serif" },
          left: 0,
          top: 0,
        }
      : undefined,
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(15, 22, 41, 0.95)",
      borderColor: "rgba(30, 42, 74, 0.6)",
      borderWidth: 1,
      textStyle: { color: "#f1f5f9", fontSize: 12, fontFamily: "Inter, system-ui, sans-serif" },
      axisPointer: {
        type: "cross",
        lineStyle: { color: "rgba(6, 182, 212, 0.15)" },
        crossStyle: { color: "rgba(6, 182, 212, 0.1)" },
      },
      extraCssText: "border-radius: 8px; box-shadow: 0 8px 32px rgba(0,0,0,0.4); backdrop-filter: blur(8px);",
    },
    legend: showLegend
      ? {
          show: series.length > 1,
          top: title ? 25 : 0,
          right: 0,
          textStyle: { color: "#64748b", fontSize: 11, fontFamily: "Inter, system-ui, sans-serif" },
          icon: "roundRect",
          itemWidth: 12,
          itemHeight: 3,
          itemGap: 16,
        }
      : undefined,
    grid: {
      left: 8,
      right: 12,
      top: title ? (series.length > 1 ? 52 : 32) : series.length > 1 ? 30 : 8,
      bottom: 8,
      containLabel: true,
    },
    xAxis: {
      type: "category",
      data: xData,
      axisLine: { lineStyle: { color: "rgba(30, 42, 74, 0.6)" } },
      axisTick: { show: false },
      axisLabel: { color: "#546a8f", fontSize: 10, margin: 12, fontFamily: "'JetBrains Mono', monospace" },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value",
      name: yAxisLabel,
      nameTextStyle: { color: "#546a8f", fontSize: 10 },
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: "#546a8f", fontSize: 10, fontFamily: "'JetBrains Mono', monospace" },
      splitLine: { lineStyle: { color: "rgba(30, 42, 74, 0.4)", type: "dashed" } },
    },
    series: series.map((s, i) => ({
      name: s.name,
      type: type === "area" ? "line" : type,
      data: s.data,
      smooth: true,
      symbol: "none",
      lineStyle: { width: 2, shadowColor: (s.color || THEME_COLORS[i % THEME_COLORS.length]) + "30", shadowBlur: 8 },
      itemStyle: { color: s.color || THEME_COLORS[i % THEME_COLORS.length] },
      emphasis: {
        lineStyle: { width: 2.5 },
      },
      ...(type === "area" && {
        areaStyle: {
          color: {
            type: "linear" as const,
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: (s.color || THEME_COLORS[i % THEME_COLORS.length]) + "30" },
              { offset: 0.7, color: (s.color || THEME_COLORS[i % THEME_COLORS.length]) + "08" },
              { offset: 1, color: (s.color || THEME_COLORS[i % THEME_COLORS.length]) + "02" },
            ],
          },
        },
      }),
      ...(type === "bar" && {
        barMaxWidth: 20,
        borderRadius: [2, 2, 0, 0],
      }),
    })) as any,
    animationDuration: 600,
    animationEasing: "cubicOut",
  };

  return (
    <ReactECharts
      option={option}
      style={{ height, width: "100%" }}
      opts={{ renderer: "svg" }}
      notMerge
    />
  );
}
