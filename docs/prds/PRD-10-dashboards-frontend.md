# PRD-10: Dashboards & Visualization Frontend

**Product**: RayOlly — AI-Native Observability Platform
**Version**: 1.0
**Date**: 2026-03-19
**Status**: Draft
**Parent**: PRD-00 Platform Vision & Architecture
**Dependencies**: PRD-01 (Ingestion), PRD-02 (Storage), PRD-03 (Query Engine), PRD-06 (Logs), PRD-07 (Metrics), PRD-08 (Traces), PRD-09 (Alerting)

---

## 1. Executive Summary

The Dashboards & Visualization Frontend is the primary user-facing surface of RayOlly. It provides an enterprise-grade dashboard builder, 15+ widget types, real-time data streaming, AI-powered dashboard generation, and a collaborative editing experience. This module competes directly with **Grafana**, **Datadog Dashboards**, and **Splunk Dashboards**, while surpassing them through AI-native capabilities, superior performance, and a modern developer experience.

**Key Differentiators vs Competitors**:

| Capability | Grafana | Datadog | Splunk | **RayOlly** |
|---|---|---|---|---|
| AI-generated dashboards | No | Limited | No | **Full NL-to-dashboard** |
| Collaborative editing | No | No | No | **Real-time cursors** |
| Dashboard-as-code | JSON only | Terraform | XML | **JSON + YAML + Terraform** |
| Widget types | 30+ (plugin) | 20+ | 15+ | **15+ native, extensible** |
| Unified data (logs+metrics+traces) | Plugin per source | Native | Logs-first | **Native unified** |
| First Contentful Paint | ~3s | ~2s | ~4s | **< 1.5s** |
| Chart render (100K points) | ~2s | ~1s | ~3s | **< 500ms** |
| Open source | Yes (AGPLv3) | No | No | **Yes (Apache 2.0 core)** |
| Streaming SSR | No | No | No | **Yes (React Server Components)** |
| Grafana import | N/A | Limited | No | **Full JSON import** |

**Architecture Overview**:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         RayOlly Frontend                                │
│                                                                         │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐       │
│  │ Dashboard  │  │  Explorer  │  │  Alerting  │  │  Settings  │       │
│  │  Builder   │  │  (Logs/    │  │    UI      │  │    & Admin │       │
│  │            │  │  Metrics/  │  │            │  │            │       │
│  │            │  │  Traces)   │  │            │  │            │       │
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘       │
│        │                │                │                │              │
│  ┌─────▼────────────────▼────────────────▼────────────────▼──────┐     │
│  │                   Shared UI Layer                              │     │
│  │  Widget Library │ Query Editor │ Time Picker │ Variable Bar    │     │
│  └──────────────────────┬────────────────────────────────────────┘     │
│                          │                                              │
│  ┌──────────────────────▼────────────────────────────────────────┐     │
│  │                   Data Layer                                   │     │
│  │  WebSocket Manager │ Query Client │ Cache │ State (Zustand)   │     │
│  └──────────────────────┬────────────────────────────────────────┘     │
│                          │                                              │
└──────────────────────────┼──────────────────────────────────────────────┘
                           │
              ┌────────────▼────────────┐
              │   RayOlly Backend API   │
              │  REST + WebSocket + SSE │
              └─────────────────────────┘
```

---

## 2. Goals & Non-Goals

### 2.1 Goals

- Deliver a world-class dashboard builder that surpasses Grafana in usability and performance
- Support 15+ widget types covering all observability data: metrics, logs, traces, events
- Achieve sub-2-second dashboard load times for dashboards with 20+ widgets
- Enable AI-powered dashboard creation from natural language prompts
- Support real-time collaborative editing with conflict resolution
- Provide Grafana dashboard import for zero-friction migration
- Meet WCAG 2.1 AA accessibility standards
- Support dashboard-as-code workflows for GitOps teams
- Deliver responsive design from 4K monitors to tablets
- Enable TV/kiosk mode for NOC and war room displays

### 2.2 Non-Goals

- Native mobile app (responsive web is the target; native apps are future scope)
- Plugin marketplace for third-party widgets (v2 scope)
- Embedded analytics for external customers (v2 scope)
- Custom branding / white-labeling (enterprise feature, post-GA)
- Offline dashboard viewing (future scope)
- Video/screen recording of dashboards (future scope)

---

## 3. Frontend Architecture

### 3.1 Technology Stack

| Layer | Technology | Rationale |
|---|---|---|
| Framework | React 19 + Next.js 15 | Server Components, Streaming SSR, App Router |
| Language | TypeScript 5.5+ (strict mode) | Type safety, DX, refactoring confidence |
| State Management | Zustand 5 | Lightweight, real-time friendly, minimal boilerplate |
| Component Library | Radix UI + Tailwind CSS 4 | Accessible primitives + utility-first styling |
| Charts | Apache ECharts 6 | 100K+ data point performance, WebGL renderer |
| Custom Viz | D3.js v7 | Topology maps, flame charts, custom renderers |
| Topology | react-flow v12 | Service maps, dependency graphs |
| Query Editor | Monaco Editor | Syntax highlighting, autocomplete, multi-language |
| Drag-and-Drop | dnd-kit | Accessible, performant, framework-agnostic |
| Virtual Scrolling | TanStack Virtual v3 | Virtualized tables and log streams |
| Data Fetching | TanStack Query v5 | Caching, refetching, optimistic updates |
| Real-Time | Native WebSocket + EventSource | Live data, streaming queries |
| Testing | Vitest + Playwright + Storybook | Unit, E2E, visual regression |
| Build | Turbopack (via Next.js) | Fast incremental builds |
| Monorepo | Turborepo | Caching, task orchestration |

### 3.2 App Router & Server Components Strategy

```
┌───────────────────────────────────────────────────────────┐
│                    Request Flow                            │
│                                                            │
│  Browser ──► Next.js Edge Runtime ──► RSC Render           │
│                                         │                  │
│              ┌──────────────────────────┘                  │
│              │                                             │
│              ▼                                             │
│  ┌───────────────────┐    ┌───────────────────┐           │
│  │  Server Component │    │  Server Component │           │
│  │  (Dashboard Meta) │    │  (Widget Configs) │           │
│  │  Streamed first   │    │  Streamed second  │           │
│  └────────┬──────────┘    └────────┬──────────┘           │
│           │                         │                      │
│           ▼                         ▼                      │
│  ┌───────────────────┐    ┌───────────────────┐           │
│  │ Client Component  │    │ Client Component  │           │
│  │ (Interactive Grid)│    │ (Chart Renderers) │           │
│  │ Hydrates on load  │    │ Hydrates on load  │           │
│  └───────────────────┘    └───────────────────┘           │
│                                                            │
│  Suspense boundaries allow progressive rendering           │
│  Static shell loads in < 500ms, widgets stream in          │
└───────────────────────────────────────────────────────────┘
```

**Server Components** handle:
- Dashboard metadata, layout configuration, and permissions
- Initial data fetch for widgets (first render)
- SEO-friendly dashboard titles and descriptions
- Static navigation shell, sidebar, breadcrumbs

**Client Components** handle:
- Interactive chart rendering (ECharts, D3)
- Drag-and-drop grid layout
- WebSocket subscriptions for live data
- Query editor with Monaco
- Time picker and variable selectors

### 3.3 State Management Architecture

```typescript
// stores/dashboard.ts — Zustand store
interface DashboardStore {
  // Dashboard metadata
  dashboard: Dashboard | null;
  isDirty: boolean;
  version: number;

  // Layout
  layout: WidgetLayout[];
  selectedWidgetId: string | null;

  // Time controls
  timeRange: TimeRange;
  refreshInterval: number | null;
  isLive: boolean;

  // Variables
  variables: Record<string, TemplateVariable>;
  resolvedVariables: Record<string, string | string[]>;

  // Collaboration
  cursors: Record<string, CollaboratorCursor>;
  lockedWidgets: Record<string, string>; // widgetId → userId

  // Actions
  setTimeRange: (range: TimeRange) => void;
  updateWidgetLayout: (layouts: WidgetLayout[]) => void;
  addWidget: (widget: WidgetConfig) => void;
  removeWidget: (widgetId: string) => void;
  updateWidgetConfig: (widgetId: string, config: Partial<WidgetConfig>) => void;
  saveDashboard: () => Promise<void>;
  revertToVersion: (version: number) => Promise<void>;
}

// stores/realtime.ts — WebSocket state
interface RealtimeStore {
  connections: Map<string, WebSocket>;
  subscriptions: Map<string, Subscription>;
  connectionStatus: 'connected' | 'reconnecting' | 'disconnected';

  subscribe: (channel: string, handler: MessageHandler) => () => void;
  send: (channel: string, message: unknown) => void;
}
```

### 3.4 Monorepo Structure

```
rayolly/
├── apps/
│   ├── web/                          # Next.js 15 application
│   │   ├── app/                      # App Router
│   │   │   ├── (auth)/               # Auth group
│   │   │   │   ├── login/
│   │   │   │   └── signup/
│   │   │   ├── (dashboard)/          # Dashboard group
│   │   │   │   ├── d/[dashboardId]/  # Dashboard view
│   │   │   │   │   ├── page.tsx      # Server Component — streams layout
│   │   │   │   │   ├── edit/page.tsx # Edit mode
│   │   │   │   │   └── layout.tsx
│   │   │   │   ├── dashboards/       # Dashboard list
│   │   │   │   └── new/              # Create dashboard
│   │   │   ├── (explore)/            # Explore logs/metrics/traces
│   │   │   ├── (alerts)/             # Alerting UI
│   │   │   ├── (settings)/           # Org/team/user settings
│   │   │   ├── layout.tsx            # Root layout (sidebar, nav)
│   │   │   └── globals.css
│   │   ├── components/               # App-specific components
│   │   ├── hooks/                    # App-specific hooks
│   │   ├── lib/                      # App utilities
│   │   ├── stores/                   # Zustand stores
│   │   ├── next.config.ts
│   │   ├── tailwind.config.ts
│   │   └── tsconfig.json
│   │
│   └── storybook/                    # Storybook app for component dev
│       └── .storybook/
│
├── packages/
│   ├── ui/                           # Shared component library
│   │   ├── src/
│   │   │   ├── primitives/           # Radix-based primitives
│   │   │   │   ├── Button.tsx
│   │   │   │   ├── Dialog.tsx
│   │   │   │   ├── DropdownMenu.tsx
│   │   │   │   ├── Popover.tsx
│   │   │   │   ├── Select.tsx
│   │   │   │   ├── Tooltip.tsx
│   │   │   │   └── index.ts
│   │   │   ├── composed/            # Higher-level components
│   │   │   │   ├── TimePicker.tsx
│   │   │   │   ├── VariableBar.tsx
│   │   │   │   ├── SearchInput.tsx
│   │   │   │   ├── CommandPalette.tsx
│   │   │   │   └── index.ts
│   │   │   └── widgets/             # Dashboard widgets
│   │   │       ├── TimeSeriesChart.tsx
│   │   │       ├── BarChart.tsx
│   │   │       ├── GaugeStat.tsx
│   │   │       ├── TableWidget.tsx
│   │   │       ├── Heatmap.tsx
│   │   │       ├── Histogram.tsx
│   │   │       ├── PieDonut.tsx
│   │   │       ├── ServiceMap.tsx
│   │   │       ├── LogStream.tsx
│   │   │       ├── FlameChart.tsx
│   │   │       ├── MarkdownText.tsx
│   │   │       ├── AlertStatus.tsx
│   │   │       ├── SLOStatus.tsx
│   │   │       ├── GeoMap.tsx
│   │   │       ├── SankeyDiagram.tsx
│   │   │       └── index.ts
│   │   ├── themes/
│   │   │   ├── dark.css
│   │   │   ├── light.css
│   │   │   └── tokens.css           # Design tokens
│   │   └── package.json
│   │
│   ├── query-engine/                 # Client-side query SDK
│   │   ├── src/
│   │   │   ├── client.ts            # API client
│   │   │   ├── languages/           # Query language parsers
│   │   │   │   ├── roql.ts          # RayOlly Query Language
│   │   │   │   ├── promql.ts        # PromQL compatibility
│   │   │   │   └── sql.ts           # SQL mode
│   │   │   ├── autocomplete.ts      # Monaco autocomplete provider
│   │   │   ├── formatter.ts         # Query formatter
│   │   │   └── types.ts
│   │   └── package.json
│   │
│   ├── dashboard-schema/            # Dashboard JSON schema + validators
│   │   ├── src/
│   │   │   ├── schema.ts            # Zod schema definitions
│   │   │   ├── migrate.ts           # Version migration logic
│   │   │   ├── grafana-import.ts    # Grafana JSON converter
│   │   │   └── types.ts             # Generated TypeScript types
│   │   └── package.json
│   │
│   └── shared/                      # Shared utilities
│       ├── src/
│       │   ├── time.ts              # Time range utilities
│       │   ├── color.ts             # Color palettes
│       │   ├── format.ts            # Number/byte formatting
│       │   └── constants.ts
│       └── package.json
│
├── turbo.json
├── package.json
└── tsconfig.base.json
```

---

## 4. Dashboard Builder

### 4.1 Grid Layout System

The dashboard uses a responsive 24-column grid with configurable row height.

```
┌─────────────────────────────────────────────────────────────────┐
│  [Variables Bar]  env: production ▼  region: us-east-1 ▼        │
│  [Time Range]     Last 1 hour ▼     [Auto-refresh: 30s ▼] [▶]  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────┐  ┌──────────────────────────┐     │
│  │  Request Rate            │  │  Error Rate              │     │
│  │  ████████▓▓░░            │  │  ▁▂▁▁▅█▃▁               │     │
│  │  12,456 req/s            │  │  0.23%                   │     │
│  │          [12 cols]       │  │          [12 cols]       │     │
│  └──────────────────────────┘  └──────────────────────────┘     │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  P99 Latency (Time Series)                    [24 cols]  │   │
│  │  250ms ┤                                                  │   │
│  │  200ms ┤        ╭──╮                                      │   │
│  │  150ms ┤   ╭────╯  ╰──╮      ╭──╮                        │   │
│  │  100ms ┤───╯          ╰──────╯  ╰────────                │   │
│  │   50ms ┤                                                  │   │
│  │        └──────────────────────────────────────────────    │   │
│  │        10:00  10:15  10:30  10:45  11:00  11:15  11:30   │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐    │
│  │ Top Services │ │  Alert       │ │  Service Map         │    │
│  │ (Table)      │ │  Status      │ │  (Topology)          │    │
│  │ [8 cols]     │ │  [8 cols]    │ │  [8 cols]            │    │
│  └──────────────┘ └──────────────┘ └──────────────────────┘    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Grid Configuration**:

```typescript
interface GridConfig {
  columns: 24;                    // Fixed 24-column grid
  rowHeight: number;              // Default: 40px, configurable
  gap: number;                    // Default: 8px
  containerPadding: [number, number]; // Default: [16, 16]
  breakpoints: {
    xl: 1920;  // 24 columns
    lg: 1200;  // 24 columns (narrower)
    md: 996;   // 12 columns
    sm: 768;   // 6 columns
    xs: 480;   // 1 column (stacked)
  };
  compactType: 'vertical' | 'horizontal' | null;
  preventCollision: boolean;
}

interface WidgetLayout {
  i: string;          // Widget ID
  x: number;          // Column position (0-23)
  y: number;          // Row position
  w: number;          // Width in columns
  h: number;          // Height in rows
  minW?: number;      // Minimum width
  minH?: number;      // Minimum height
  maxW?: number;      // Maximum width
  maxH?: number;      // Maximum height
  static?: boolean;   // Prevent drag/resize
}
```

### 4.2 Drag-and-Drop Widget Placement

```
┌────────────────────────────────────────────────────┐
│  Dashboard Edit Mode                        [Save] │
├───────────┬────────────────────────────────────────┤
│           │                                        │
│  Widget   │   ┌────────┐   ┌────────┐             │
│  Palette  │   │ Chart  │   │ Gauge  │             │
│           │   │ ┈┈┈┈┈┈ │   │  78%   │             │
│  ▸ Charts │   └────────┘   └────────┘             │
│    Line   │                                        │
│    Bar    │   ┌──────────────────────────────┐     │
│    Area   │   │                              │     │
│  ▸ Stats  │   │   ╔══════════════╗           │     │
│    Gauge  │   │   ║  DRAGGING    ║ ← cursor  │     │
│    Single │   │   ║  (Table)     ║           │     │
│  ▸ Data   │   │   ╚══════════════╝           │     │
│    Table  │   │   ┌ ─ ─ ─ ─ ─ ─ ┐           │     │
│    Logs   │   │     Drop zone     ← guides   │     │
│  ▸ Maps   │   │   └ ─ ─ ─ ─ ─ ─ ┘           │     │
│    Topo   │   │                              │     │
│    Geo    │   └──────────────────────────────┘     │
│  ▸ Other  │                                        │
│    Text   │                                        │
│    Alert  │                                        │
│           │                                        │
└───────────┴────────────────────────────────────────┘
```

**Implementation with dnd-kit**:
- Drag from widget palette to grid canvas
- Snap to grid with visual guides
- Collision detection prevents widget overlap
- Resize handles on all widget corners and edges
- Undo/redo support via Zustand middleware (temporal history)
- Keyboard-accessible: Tab to select widget, Arrow keys to move, Shift+Arrow to resize

### 4.3 Dashboard Templates

Pre-built templates for common use cases:

| Template | Widgets | Data Sources |
|---|---|---|
| **Kubernetes Overview** | Pod CPU/Memory, Node Status, Deployment Rollouts, Namespace Usage, Events | Metrics (k8s.*), Events |
| **AWS Infrastructure** | EC2 instances, RDS metrics, ELB latency, S3 usage, Lambda invocations | CloudWatch metrics |
| **API Gateway** | Request rate, Error rate, Latency percentiles, Top endpoints, Geographic distribution | Metrics, Traces |
| **Database Monitoring** | Query throughput, Slow queries, Connection pool, Replication lag, Buffer pool | Metrics, Logs |
| **Service Overview** | RED metrics, Dependency map, Error logs, Active alerts, SLO status | Metrics, Logs, Traces |
| **Incident Response** | Alert timeline, Affected services, Error spikes, Change events, On-call status | All sources |
| **Cost Explorer** | Cloud spend by service, Resource utilization, Idle resources, Forecast | Metrics, Custom |
| **SLO Dashboard** | SLO status, Error budget, Burn rate, Historical compliance | Metrics, Alerts |

### 4.4 Template Variables

```
┌──────────────────────────────────────────────────────────────┐
│  Variable Configuration                                       │
│                                                               │
│  Name:       [$environment]                                   │
│  Type:       [Query ▼]                                        │
│  Query:      SELECT DISTINCT environment FROM services        │
│  Multi:      [✓] Allow multiple values                        │
│  Include:    [✓] Include "All" option                         │
│  Default:    [production]                                      │
│  Refresh:    [On dashboard load ▼]                            │
│  Depends on: [none ▼]                                         │
│                                                               │
│  Preview:  production | staging | development                 │
│                                                               │
│  [Cancel]                                    [Save Variable]  │
└──────────────────────────────────────────────────────────────┘
```

**Variable Types**:

| Type | Description | Example |
|---|---|---|
| **Query** | Values from a data source query | `SELECT DISTINCT region FROM services` |
| **Custom** | Static list of values | `us-east-1, us-west-2, eu-west-1` |
| **Text** | Free-text input | User-entered filter string |
| **Interval** | Time interval selection | `1m, 5m, 15m, 1h, 6h, 1d` |
| **Datasource** | Select a data source | Switch between prod/staging clusters |
| **Constant** | Hidden fixed value | Tenant ID, environment prefix |

**Variable interpolation** in queries:

```sql
-- ROQL query with variables
SELECT avg(latency_ms) FROM traces
WHERE service = '${service}'
  AND environment = '${environment}'
  AND timestamp >= ${__from}
  AND timestamp <= ${__to}
GROUP BY time(${__interval})
```

### 4.5 Time Range Controls

```
┌─────────────────────────────────────────────────────────────────┐
│  Time Picker                                                     │
│                                                                   │
│  Quick Ranges          │  Absolute Range                         │
│  ─────────────         │  ──────────────                         │
│  ○ Last 5 minutes      │  From: [2026-03-19 09:00:00]           │
│  ○ Last 15 minutes     │  To:   [2026-03-19 10:00:00]           │
│  ○ Last 30 minutes     │                                         │
│  ● Last 1 hour         │  [Apply]                                │
│  ○ Last 3 hours        │                                         │
│  ○ Last 6 hours        │  Recent Ranges                         │
│  ○ Last 12 hours       │  ──────────────                         │
│  ○ Last 24 hours       │  • Last 1 hour (3 min ago)             │
│  ○ Last 7 days         │  • Last 24 hours (15 min ago)          │
│  ○ Last 30 days        │  • Mar 18 09:00 → Mar 18 12:00        │
│                        │                                         │
│  Auto-refresh: [30s ▼] │  Fiscal/Custom                         │
│  [▶ Live]              │  • This week / Last week                │
│                        │  • This month / Last month              │
└─────────────────────────────────────────────────────────────────┘
```

**Time range features**:
- Global time range applies to all widgets by default
- Per-widget time range override (e.g., show 7-day trend in one widget while others show 1 hour)
- URL-encoded time range for shareable links: `?from=now-1h&to=now`
- Auto-refresh intervals: 5s, 10s, 30s, 1m, 5m, 15m, 30m, 1h
- Live mode: real-time streaming with auto-scrolling time window
- Timezone selection: UTC, local, custom

### 4.6 Dashboard Versioning

Git-like version history for every dashboard:

```typescript
interface DashboardVersion {
  id: string;
  dashboardId: string;
  version: number;
  createdAt: string;
  createdBy: User;
  message: string;            // Optional commit message
  diff: DashboardDiff;        // JSON Patch (RFC 6902)
  snapshot: Dashboard;         // Full dashboard state at this version
}

interface DashboardDiff {
  operations: JsonPatchOp[];
  summary: {
    widgetsAdded: number;
    widgetsRemoved: number;
    widgetsModified: number;
    layoutChanged: boolean;
    variablesChanged: boolean;
  };
}
```

```
┌──────────────────────────────────────────────────────────────┐
│  Dashboard History                                            │
│                                                               │
│  v12 (current) — Alice — 5 min ago                           │
│  │  "Add P99 latency chart for payment service"              │
│  │  +1 widget, layout modified                               │
│  │                                                            │
│  v11 — Bob — 2 hours ago                                     │
│  │  "Update error rate thresholds"                           │
│  │  2 widgets modified                                       │
│  │                                                            │
│  v10 — Alice — 1 day ago                                     │
│  │  "Add SLO status widget"                                  │
│  │  +1 widget                                                │
│  │                                                            │
│  v9 — System — 3 days ago                                    │
│     "Auto-saved"                                              │
│                                                               │
│  [Compare v10 ↔ v12]  [Restore v11]  [Export v12]           │
└──────────────────────────────────────────────────────────────┘
```

### 4.7 Collaborative Editing

Real-time multi-user dashboard editing using WebSocket + CRDT:

```
┌──────────────────────────────────────────────────────────────┐
│  Dashboard: Production Overview          [Alice 🟢] [Bob 🔵] │
│                                                               │
│  ┌────────────────────┐  ┌──────────────────────┐            │
│  │  Request Rate      │  │  Error Rate  🔒 Bob  │            │
│  │                    │  │  (locked for editing) │            │
│  │  Alice's cursor ──►│◄─┤                      │            │
│  │  (red outline)     │  │  (blue outline)      │            │
│  └────────────────────┘  └──────────────────────┘            │
│                                                               │
│  ┌──────────────────────────────────────────────┐            │
│  │  P99 Latency                                  │            │
│  │                                               │            │
│  └──────────────────────────────────────────────┘            │
│                                                               │
│  Presence: Alice is editing "Request Rate"                   │
│            Bob is editing "Error Rate"                        │
└──────────────────────────────────────────────────────────────┘
```

**Collaboration protocol**:
- **Presence awareness**: See who is viewing/editing the dashboard
- **Widget locking**: When a user edits a widget, others see it as locked with the editor's name
- **Conflict resolution**: Last-writer-wins for non-overlapping changes; prompt for overlapping
- **Cursor broadcasting**: Real-time cursor position shown for all collaborators
- **Change feed**: Activity sidebar shows real-time edits by others
- **Implementation**: WebSocket channels per dashboard, Yjs CRDT for conflict-free merging

### 4.8 Dashboard-as-Code

Export and import dashboards as JSON or YAML for GitOps workflows:

```yaml
# dashboard.yaml
apiVersion: rayolly.io/v1
kind: Dashboard
metadata:
  name: production-overview
  folder: /team-platform/production
  tags: [production, sre, k8s]
  description: "Production service overview with RED metrics"
spec:
  variables:
    - name: environment
      type: query
      query: "SELECT DISTINCT environment FROM services"
      default: production
    - name: service
      type: query
      query: "SELECT name FROM services WHERE env = '${environment}'"
      multi: true
  timeRange:
    default: "now-1h"
    refreshInterval: "30s"
  layout:
    columns: 24
    rowHeight: 40
  widgets:
    - id: request-rate
      type: timeseries
      title: "Request Rate"
      position: { x: 0, y: 0, w: 12, h: 8 }
      query: |
        rate(http_requests_total{service="${service}"}[5m])
      options:
        legend: { show: true, position: bottom }
        axes:
          y: { label: "req/s", min: 0 }
        thresholds:
          - value: 1000
            color: warning
          - value: 5000
            color: critical
    - id: error-rate
      type: gauge
      title: "Error Rate"
      position: { x: 12, y: 0, w: 12, h: 8 }
      query: |
        rate(http_errors_total{service="${service}"}[5m])
        / rate(http_requests_total{service="${service}"}[5m]) * 100
      options:
        unit: percent
        thresholds:
          - value: 1
            color: green
          - value: 5
            color: yellow
          - value: 10
            color: red
```

CLI support:

```bash
# Apply dashboard from file
rayolly dashboard apply -f dashboard.yaml

# Export existing dashboard
rayolly dashboard export production-overview -o yaml > dashboard.yaml

# Diff dashboard changes
rayolly dashboard diff production-overview dashboard.yaml

# Validate dashboard schema
rayolly dashboard validate dashboard.yaml
```

### 4.9 Folder Organization & Tagging

```
Dashboards/
├── 📁 Platform Team/
│   ├── 📁 Production/
│   │   ├── 📊 Service Overview          [production] [sre]
│   │   ├── 📊 K8s Cluster Health        [production] [k8s]
│   │   └── 📊 Database Monitoring       [production] [rds]
│   └── 📁 Staging/
│       └── 📊 Staging Overview           [staging]
├── 📁 Payment Team/
│   ├── 📊 Payment Pipeline              [payment] [critical]
│   └── 📊 Stripe Integration            [payment] [vendor]
├── 📁 Shared/
│   ├── 📊 SLO Dashboard                 [slo] [company-wide]
│   └── 📊 Cost Explorer                 [finops]
└── ⭐ Starred
    ├── 📊 Service Overview
    └── 📊 Payment Pipeline
```

- Nested folder structure with team-based organization
- Tag-based filtering across folders
- Star/favorite dashboards for quick access
- Recently viewed dashboards list
- Dashboard search by title, tag, creator, or widget content

---

## 5. Widget Types

### 5.1 Time Series Chart

```
┌──────────────────────────────────────────────────────────────┐
│  P99 Latency by Service                    [⋯] [↗] [✏️]     │
│                                                               │
│  300ms ┤                                                      │
│        │           ╭──╮                                       │
│  250ms ┤          ╱    ╲         payment-svc ────             │
│        │    ╭────╱      ╲        auth-svc    - - -            │
│  200ms ┤───╱              ╲      user-svc    ·····            │
│        │                   ╲                                  │
│  150ms ┤                    ╰──────╮                          │
│        │  · · · · · · · · · · · · · · · · · · · · ·          │
│  100ms ┤─────────────────────────────────────────────         │
│        │                                                      │
│   50ms ┤                                                      │
│        └──────────────────────────────────────────────        │
│        10:00   10:15   10:30   10:45   11:00   11:15         │
│                                                               │
│  [Anomaly detected at 10:20 — click to investigate]   🔴 AI  │
└──────────────────────────────────────────────────────────────┘
```

**Description**: The core visualization for time-based data. Renders multiple series as lines, areas, or stacked areas. Supports annotations, thresholds, and AI anomaly overlays.

**Configuration Options**:

| Option | Type | Description |
|---|---|---|
| `drawStyle` | `line \| area \| stacked-area \| bars` | Rendering style |
| `lineWidth` | `1-5` | Line thickness in px |
| `fillOpacity` | `0-100` | Area fill transparency |
| `pointSize` | `0-10` | Data point marker size |
| `interpolation` | `linear \| smooth \| step-before \| step-after` | Curve interpolation |
| `showLegend` | `boolean` | Show/hide legend |
| `legendPosition` | `bottom \| right \| hidden` | Legend placement |
| `yAxis.label` | `string` | Y-axis label |
| `yAxis.min` | `number \| auto` | Y-axis minimum |
| `yAxis.max` | `number \| auto` | Y-axis maximum |
| `yAxis.scale` | `linear \| log` | Y-axis scale |
| `yAxis.unit` | `string` | Unit for formatting (bytes, ms, percent, etc.) |
| `dualYAxis` | `boolean` | Enable second Y-axis |
| `thresholds` | `Threshold[]` | Horizontal threshold lines |
| `annotations` | `Annotation[]` | Vertical event markers |
| `showAnomalies` | `boolean` | AI anomaly band overlay |
| `nullHandling` | `connected \| gap \| zero` | How to handle null values |
| `maxDataPoints` | `number` | Max points before downsampling |
| `tooltip` | `single \| all \| hidden` | Tooltip mode |

**Data source compatibility**: Metrics, Traces (latency/throughput), Custom queries

### 5.2 Bar Chart

```
┌──────────────────────────────────────────────────────────────┐
│  Error Count by Service (Top 10)           [⋯] [↗] [✏️]     │
│                                                               │
│  payment-svc   ████████████████████████████░░░░  1,247       │
│  auth-svc      █████████████████░░░░░░░░░░░░░░    892       │
│  user-svc      ████████████░░░░░░░░░░░░░░░░░░░    634       │
│  order-svc     █████████░░░░░░░░░░░░░░░░░░░░░░    512       │
│  catalog-svc   ██████░░░░░░░░░░░░░░░░░░░░░░░░░    345       │
│  search-svc    ████░░░░░░░░░░░░░░░░░░░░░░░░░░░    223       │
│  notify-svc    ███░░░░░░░░░░░░░░░░░░░░░░░░░░░░    178       │
│  cache-svc     ██░░░░░░░░░░░░░░░░░░░░░░░░░░░░░    112       │
│  gateway-svc   █░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░     67       │
│  config-svc    ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░     23       │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

**Description**: Horizontal or vertical bar charts for comparing categorical values. Supports stacked, grouped, and percentage modes.

**Configuration Options**:

| Option | Type | Description |
|---|---|---|
| `orientation` | `horizontal \| vertical` | Bar direction |
| `mode` | `grouped \| stacked \| percent` | Multi-series mode |
| `barWidth` | `auto \| number` | Bar width |
| `showValues` | `boolean` | Display values on bars |
| `sortBy` | `value \| label \| none` | Sort order |
| `sortDirection` | `asc \| desc` | Sort direction |
| `topN` | `number` | Limit to top N entries |
| `colorByValue` | `boolean` | Color bars by threshold |
| `xAxis.label` | `string` | Axis label |

**Data source compatibility**: Metrics (aggregated), Logs (count by field), Traces (grouped stats)

### 5.3 Gauge / Single Stat

```
┌───────────────────┐  ┌───────────────────┐  ┌───────────────────┐
│    CPU Usage       │  │    Memory         │  │    Disk I/O       │
│                    │  │                    │  │                    │
│      ╭─────╮      │  │      ╭─────╮      │  │      ╭─────╮      │
│    ╱    78%  ╲    │  │    ╱    42%  ╲    │  │    ╱    91%  ╲    │
│   │  ████████░░│   │  │   │  █████░░░░░│   │  │   │  ██████████│   │
│    ╲          ╱    │  │    ╲          ╱    │  │    ╲          ╱    │
│      ╰─────╯      │  │      ╰─────╯      │  │      ╰─────╯      │
│                    │  │                    │  │                    │
│   ▲ 12% from avg  │  │   ▼ 3% from avg   │  │   ▲ 28% ⚠️        │
│   [🟡 Warning]    │  │   [🟢 Normal]      │  │   [🔴 Critical]   │
└───────────────────┘  └───────────────────┘  └───────────────────┘
```

**Description**: Displays a single value prominently, optionally as a gauge dial. Ideal for KPIs, SLIs, and system health indicators.

**Configuration Options**:

| Option | Type | Description |
|---|---|---|
| `displayMode` | `gauge \| stat \| sparkline` | Visual style |
| `gaugeStyle` | `arc \| bar \| gradient` | Gauge rendering |
| `unit` | `string` | Value unit (percent, bytes, ms, etc.) |
| `decimals` | `number` | Decimal precision |
| `thresholds` | `Threshold[]` | Color thresholds |
| `showSparkline` | `boolean` | Mini trend line below value |
| `sparklineColor` | `string` | Sparkline color |
| `comparisonPeriod` | `string` | Show % change vs previous period |
| `prefix` | `string` | Text before value |
| `suffix` | `string` | Text after value |
| `colorMode` | `value \| background \| none` | What to color |
| `textSize` | `auto \| number` | Font size |

**Data source compatibility**: Metrics (instant query), Custom (any single value)

### 5.4 Table

```
┌──────────────────────────────────────────────────────────────────┐
│  Top Endpoints by Latency                      [⋯] [↗] [✏️]    │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ Service      │ Endpoint       │ P50    │ P99    │ Rate    │  │
│  ├──────────────┼────────────────┼────────┼────────┼─────────┤  │
│  │ payment-svc  │ /api/charge    │ 120ms  │ 890ms  │ 1.2K/s  │  │
│  │ auth-svc     │ /api/token     │  45ms  │ 234ms  │ 3.4K/s  │  │
│  │ user-svc     │ /api/profile   │  67ms  │ 456ms  │  890/s  │  │
│  │ order-svc    │ /api/create    │ 230ms  │ 1.2s   │  450/s  │  │
│  │ catalog-svc  │ /api/search    │  89ms  │ 678ms  │ 2.1K/s  │  │
│  │ ⋮            │ ⋮              │ ⋮      │ ⋮      │ ⋮       │  │
│  └────────────────────────────────────────────────────────────┘  │
│  Showing 1-20 of 156 rows       [◀ 1 2 3 4 ... 8 ▶]           │
└──────────────────────────────────────────────────────────────────┘
```

**Description**: Tabular data display with sorting, filtering, pagination, and cell-level formatting. Uses TanStack Virtual for large datasets (100K+ rows).

**Configuration Options**:

| Option | Type | Description |
|---|---|---|
| `columns` | `ColumnDef[]` | Column definitions with formatting |
| `pageSize` | `number` | Rows per page (default: 20) |
| `sortable` | `boolean` | Enable column sorting |
| `filterable` | `boolean` | Enable column filtering |
| `columnFormatting` | `Record<string, CellFormat>` | Per-column formatting (color, bar, link) |
| `cellThresholds` | `Record<string, Threshold[]>` | Color cells by value |
| `showRowNumbers` | `boolean` | Display row index |
| `enableExport` | `boolean` | Allow CSV/JSON export |
| `linkTemplate` | `string` | Click row to navigate (template URL) |
| `virtualScroll` | `boolean` | Enable virtual scrolling for large datasets |

**Data source compatibility**: Metrics, Logs, Traces, Custom queries

### 5.5 Heatmap

```
┌──────────────────────────────────────────────────────────────┐
│  Request Latency Distribution                  [⋯] [↗] [✏️] │
│                                                               │
│  >1s  │░░░░░░░░░░░░░░░░░▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░░░░    │
│  500ms│░░░░░░░░░░░░░░░░▓▓█▓▓░░░░░░░░░░░░░░░░░░░░░░░░░░    │
│  200ms│░░░░░░░░▓▓▓▓▓▓▓█████▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░    │
│  100ms│▓▓▓▓▓▓▓████████████████████▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░    │
│   50ms│██████████████████████████████████████████▓▓▓▓▓▓▓    │
│   20ms│██████████████████████████████████████████████████    │
│   10ms│██████████████████████████████████████████████████    │
│       └──────────────────────────────────────────────────    │
│       10:00   10:15   10:30   10:45   11:00   11:15         │
│                                                               │
│  Legend: ░ low  ▓ medium  █ high                             │
└──────────────────────────────────────────────────────────────┘
```

**Description**: Visualizes data density over two dimensions, typically time vs. a bucketed numeric dimension. Ideal for latency distributions and usage patterns.

**Configuration Options**:

| Option | Type | Description |
|---|---|---|
| `colorScheme` | `string` | Color gradient (Viridis, Inferno, Plasma, etc.) |
| `yAxisBuckets` | `auto \| number` | Number of Y-axis buckets |
| `yAxisScale` | `linear \| log \| sqrt` | Bucket scale |
| `showValues` | `boolean` | Display count in cells |
| `showTooltip` | `boolean` | Show details on hover |
| `minColor` | `string` | Color for minimum value |
| `maxColor` | `string` | Color for maximum value |

**Data source compatibility**: Metrics (histograms), Traces (latency distributions)

### 5.6 Histogram

**Description**: Distribution chart showing frequency of values across configurable buckets. Useful for understanding latency, payload size, or response code distributions.

**Configuration Options**:

| Option | Type | Description |
|---|---|---|
| `bucketCount` | `number` | Number of buckets (auto or fixed) |
| `bucketSize` | `number` | Fixed bucket width |
| `showPercentile` | `boolean` | Overlay percentile lines |
| `percentiles` | `number[]` | Which percentiles to show (p50, p90, p99) |
| `cumulative` | `boolean` | Show cumulative distribution |
| `unit` | `string` | Value unit |

**Data source compatibility**: Metrics (histogram type), Traces (latency), Logs (numeric fields)

### 5.7 Pie / Donut Chart

```
┌──────────────────────────────────┐
│  Error Distribution by Type      │
│                                   │
│         ╭───────────╮            │
│       ╱   ░░░░░░░░   ╲          │
│      │  ░░        ▓▓▓  │         │
│      │ ░░   Total  ▓▓▓ │   ░ 5xx (42%)  │
│      │ ░░  4,231   ███ │   ▓ 4xx (35%)  │
│      │  ░░        ███  │   █ timeout (18%) │
│       ╲   ████████   ╱      ▒ other (5%)  │
│         ╰───────────╯            │
│                                   │
└──────────────────────────────────┘
```

**Description**: Proportional breakdown of categorical data. Donut variant shows a total value in the center.

**Configuration Options**:

| Option | Type | Description |
|---|---|---|
| `variant` | `pie \| donut` | Chart style |
| `showLabels` | `boolean` | Label each slice |
| `showPercentages` | `boolean` | Show percentage values |
| `showLegend` | `boolean` | Display legend |
| `innerRadius` | `number` | Donut hole size (0 = pie) |
| `centerText` | `string` | Text inside donut hole |
| `maxSlices` | `number` | Group small slices into "other" |

**Data source compatibility**: Metrics (aggregated), Logs (count by field), Custom

### 5.8 Service Map (Topology)

```
┌──────────────────────────────────────────────────────────────────┐
│  Service Topology                                  [⋯] [↗] [✏️] │
│                                                                   │
│                    ┌──────────┐                                   │
│                    │ Gateway  │                                   │
│                    │ 12K rpm  │                                   │
│                    │ 🟢 0.1%  │                                   │
│                    └────┬─────┘                                   │
│                   ╱     │     ╲                                   │
│           ┌──────┴──┐   │   ┌──┴───────┐                        │
│           │ Auth    │   │   │ Search   │                        │
│           │ 8K rpm  │   │   │ 3K rpm   │                        │
│           │ 🟢 0.2% │   │   │ 🟡 2.3%  │                        │
│           └─────────┘   │   └──────────┘                        │
│                    ┌────┴─────┐                                   │
│                    │ Payment  │                                   │
│                    │ 1.2K rpm │                                   │
│                    │ 🔴 5.1%  │                                   │
│                    └────┬─────┘                                   │
│                    ┌────┴─────┐                                   │
│                    │ Postgres │                                   │
│                    │ 2K qps   │                                   │
│                    │ 🟢 0.0%  │                                   │
│                    └──────────┘                                   │
│                                                                   │
│  Node size = throughput │ Edge width = request rate              │
│  Color = error rate     │ Click node to drill down              │
└──────────────────────────────────────────────────────────────────┘
```

**Description**: Interactive topology graph showing service dependencies, traffic flow, and health status. Built with react-flow. Nodes represent services, edges represent call relationships.

**Configuration Options**:

| Option | Type | Description |
|---|---|---|
| `layout` | `dagre \| force \| hierarchical` | Graph layout algorithm |
| `nodeMetric` | `string` | Metric controlling node size |
| `edgeMetric` | `string` | Metric controlling edge width |
| `colorMetric` | `string` | Metric controlling node color |
| `showLabels` | `boolean` | Show node labels |
| `showEdgeLabels` | `boolean` | Show edge metrics |
| `groupBy` | `namespace \| team \| none` | Cluster nodes by attribute |
| `onNodeClick` | `drilldown \| filter \| navigate` | Click behavior |
| `animateTraffic` | `boolean` | Animated dots along edges |
| `depth` | `number` | Max dependency depth (1-5) |

**Data source compatibility**: Traces (service dependencies), Metrics (service-level)

### 5.9 Log Stream

```
┌──────────────────────────────────────────────────────────────────┐
│  Log Stream — payment-svc                      [⋯] [↗] [✏️]     │
│  [Filter: level=error AND service=payment-svc]  [▶ Live Tail]   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ 11:23:45.123 ERR  payment-svc  Stripe API timeout after   │  │
│  │                                 30s — order_id=ord_8f2k    │  │
│  │ 11:23:44.891 ERR  payment-svc  Failed to process refund   │  │
│  │                                 — amount=49.99 cur=USD     │  │
│  │ 11:23:44.567 WARN payment-svc  Retry attempt 3/5 for      │  │
│  │                                 charge chr_9x2m            │  │
│  │ 11:23:43.234 ERR  payment-svc  Connection pool exhausted  │  │
│  │                                 — active=50 max=50         │  │
│  │ 11:23:42.890 INFO payment-svc  Health check OK            │  │
│  │ ▼ Loading more...                                          │  │
│  └────────────────────────────────────────────────────────────┘  │
│  Showing 5 of 12,456 matching logs                              │
└──────────────────────────────────────────────────────────────────┘
```

**Description**: Scrollable log viewer with syntax highlighting, live tail streaming, and field extraction. Uses virtual scrolling for performance.

**Configuration Options**:

| Option | Type | Description |
|---|---|---|
| `query` | `string` | Log filter query |
| `columns` | `string[]` | Visible log fields |
| `wrapLines` | `boolean` | Wrap long lines |
| `showTimestamp` | `boolean` | Display timestamp column |
| `showLevel` | `boolean` | Display level column |
| `liveTail` | `boolean` | Enable live streaming |
| `maxLines` | `number` | Lines to display before virtualization |
| `highlightPatterns` | `Pattern[]` | Regex patterns to highlight |
| `contextLines` | `number` | Lines of context on expand |
| `sortOrder` | `newest-first \| oldest-first` | Sort direction |

**Data source compatibility**: Logs

### 5.10 Trace Flame Chart

```
┌──────────────────────────────────────────────────────────────────┐
│  Trace: ord_8f2k — 1.23s total                  [⋯] [↗] [✏️]  │
│                                                                   │
│  ├─ gateway /api/order/create ████████████████████████████ 1.23s │
│  │  ├─ auth-svc /validate    ███░░░░░░░░░░░░░░░░░░░░░░░   120ms │
│  │  ├─ order-svc /create     ░░░██████████░░░░░░░░░░░░░   450ms │
│  │  │  ├─ postgres INSERT    ░░░███░░░░░░░░░░░░░░░░░░░░    89ms │
│  │  │  └─ redis SET          ░░░░░░█░░░░░░░░░░░░░░░░░░░    12ms │
│  │  └─ payment-svc /charge   ░░░░░░░░░░░████████████████   650ms │
│  │     ├─ stripe API call    ░░░░░░░░░░░███████████░░░░░   580ms │
│  │     └─ postgres UPDATE    ░░░░░░░░░░░░░░░░░░░░░██░░░    45ms │
│  │                                                               │
│  └───────────────────────────────────────────────────────────    │
│     0ms    200ms   400ms   600ms   800ms   1000ms  1200ms       │
│                                                                   │
│  Critical path: gateway → payment-svc → stripe (71% of total)   │
└──────────────────────────────────────────────────────────────────┘
```

**Description**: Interactive flame chart for distributed traces. Shows span hierarchy, timing waterfall, and critical path analysis. Click spans to see attributes and related logs.

**Configuration Options**:

| Option | Type | Description |
|---|---|---|
| `colorBy` | `service \| duration \| status` | Span coloring strategy |
| `showCriticalPath` | `boolean` | Highlight critical path |
| `minSpanDuration` | `string` | Hide spans shorter than threshold |
| `collapseRepeated` | `boolean` | Collapse similar repeated spans |
| `showLogs` | `boolean` | Show span-level logs inline |
| `showEvents` | `boolean` | Show span events as markers |
| `timeFormat` | `absolute \| relative` | Time axis format |

**Data source compatibility**: Traces

### 5.11 Markdown / Text

**Description**: Static content widget for adding context, instructions, or links to dashboards. Supports full Markdown with embedded variables.

**Configuration Options**:

| Option | Type | Description |
|---|---|---|
| `content` | `string` | Markdown content (supports variables `${var}`) |
| `fontSize` | `number` | Base font size |
| `textAlign` | `left \| center \| right` | Text alignment |
| `backgroundColor` | `string` | Widget background color |

**Data source compatibility**: None (static content)

### 5.12 Alert Status

```
┌──────────────────────────────────────────────────────┐
│  Active Alerts                         [⋯] [↗] [✏️]  │
│                                                       │
│  🔴 CRITICAL  Payment error rate > 5%     12m ago    │
│               payment-svc | prod-us-east             │
│                                                       │
│  🟡 WARNING   CPU > 80% on k8s-node-12   45m ago    │
│               infra | prod-us-east                   │
│                                                       │
│  🟡 WARNING   Disk usage > 85%            2h ago     │
│               postgres-primary | prod-us-east        │
│                                                       │
│  ───────────────────────────────────────────────     │
│  3 active alerts (1 critical, 2 warning)             │
│  Last 24h: 7 fired, 4 resolved                      │
└──────────────────────────────────────────────────────┘
```

**Description**: Shows active alert status for selected services or rules. Groups by severity, shows duration and affected components.

**Configuration Options**:

| Option | Type | Description |
|---|---|---|
| `filter` | `AlertFilter` | Filter by service, severity, team |
| `groupBy` | `severity \| service \| rule` | Grouping strategy |
| `showResolved` | `boolean` | Include recently resolved alerts |
| `resolvedWindow` | `string` | How far back to show resolved alerts |
| `maxAlerts` | `number` | Max alerts to display |
| `sortBy` | `severity \| time \| service` | Sort order |

**Data source compatibility**: Alerts (PRD-09)

### 5.13 SLO Status

```
┌──────────────────────────────────────────────────────────────┐
│  SLO Status                                    [⋯] [↗] [✏️]  │
│                                                               │
│  Payment Availability (99.95%)                               │
│  ████████████████████████████████████████████░░  99.97%      │
│  Error budget remaining: 78.2% (21.6 min left)              │
│  Burn rate: 1.2x                              [🟢 Healthy]  │
│                                                               │
│  API Latency P99 < 500ms (99.9%)                            │
│  ██████████████████████████████████████░░░░░░░  99.82%      │
│  Error budget remaining: 12.4% (3.2 min left)               │
│  Burn rate: 4.8x                              [🟡 At Risk]  │
│                                                               │
│  Search Availability (99.9%)                                 │
│  ████████████████████████████░░░░░░░░░░░░░░░░  99.78%      │
│  Error budget remaining: -22% (EXHAUSTED)                    │
│  Burn rate: 8.2x                              [🔴 Breached] │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

**Description**: Displays SLO compliance, error budget consumption, and burn rate for selected SLOs. Color-coded by status.

**Configuration Options**:

| Option | Type | Description |
|---|---|---|
| `sloIds` | `string[]` | SLOs to display |
| `showBurnRate` | `boolean` | Display burn rate |
| `showErrorBudget` | `boolean` | Display error budget bar |
| `showHistory` | `boolean` | Show 30-day trend sparkline |
| `complianceWindow` | `7d \| 28d \| 30d \| 90d` | Compliance calculation window |

**Data source compatibility**: SLO (PRD-09), Metrics

### 5.14 Geographic Map

```
┌──────────────────────────────────────────────────────────────┐
│  Request Distribution by Region                [⋯] [↗] [✏️]  │
│                                                               │
│          ╭──────────────────────────────╮                     │
│        ╱                  ·              ╲                    │
│      ╱     ●              ·    ◉          ╲                  │
│     │   (US-W)            ·  (EU-W)        │                 │
│     │   12K rpm     ╱─────·─╲  8K rpm      │                 │
│     │              │      ·   │             │                 │
│      ╲        ●   │      ·   │    ○       ╱                  │
│        ╲    (US-E)│      ·   │  (APAC)  ╱                    │
│          ╲  22K   │      ·   │  3K rpm╱                      │
│            ╰──────┴──────────┴───────╯                       │
│                                                               │
│  ● > 10K rpm   ◉ 5-10K rpm   ○ < 5K rpm                     │
│  Total: 45K rpm across 4 regions                             │
└──────────────────────────────────────────────────────────────┘
```

**Description**: World map with data overlays showing geographic distribution of traffic, errors, or latency. Supports region-level and point-level markers.

**Configuration Options**:

| Option | Type | Description |
|---|---|---|
| `mapStyle` | `world \| us \| europe \| custom` | Base map |
| `markerType` | `circle \| heatmap \| choropleth` | Visualization style |
| `sizeMetric` | `string` | Metric controlling marker size |
| `colorMetric` | `string` | Metric controlling marker color |
| `thresholds` | `Threshold[]` | Color thresholds |
| `showLabels` | `boolean` | Display region labels |
| `zoomLevel` | `number` | Initial zoom (1-18) |
| `center` | `[lat, lng]` | Initial map center |

**Data source compatibility**: Metrics (with geo labels), Logs (with IP geolocation)

### 5.15 Sankey Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│  Traffic Flow: Gateway → Backend                   [⋯] [↗] [✏️] │
│                                                                   │
│              ┌─────────┐                                         │
│  ╔═══════╗══╡ auth    ╞═══╗                                     │
│  ║       ║  └─────────┘   ║   ┌──────────┐                      │
│  ║       ║                ╠═══╡ postgres ╞══╗                    │
│  ║       ║  ┌─────────┐   ║   └──────────┘  ║   ┌────────┐     │
│  ║  GW   ╠══╡ payment ╞═══╣                  ╠═══╡ stripe ╞     │
│  ║ 45K/s ║  └─────────┘   ║   ┌──────────┐  ║   └────────┘     │
│  ║       ║                ╠═══╡  redis   ╞══╝                    │
│  ║       ║  ┌─────────┐   ║   └──────────┘                      │
│  ║       ╠══╡ search  ╞═══╝                                     │
│  ╚═══════╝  └─────────┘                                         │
│                                                                   │
│  Width = request volume │ Color = error rate                     │
└──────────────────────────────────────────────────────────────────┘
```

**Description**: Flow diagram showing how traffic moves through system components. Width of flows represents volume, color represents health.

**Configuration Options**:

| Option | Type | Description |
|---|---|---|
| `sourceField` | `string` | Source node field |
| `targetField` | `string` | Target node field |
| `valueField` | `string` | Flow volume field |
| `colorField` | `string` | Flow color field |
| `nodeAlign` | `left \| right \| center \| justify` | Node alignment |
| `orientation` | `horizontal \| vertical` | Flow direction |
| `showValues` | `boolean` | Display values on flows |

**Data source compatibility**: Traces (service-to-service flows), Metrics (network flow)

---

## 6. Visualization Library

### 6.1 Rendering Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                  Rendering Pipeline                            │
│                                                               │
│  Query Result ──► Data Transform ──► Renderer Selection       │
│                                          │                    │
│                          ┌───────────────┼───────────────┐   │
│                          │               │               │    │
│                          ▼               ▼               ▼    │
│                    ┌──────────┐   ┌──────────┐   ┌────────┐ │
│                    │ ECharts  │   │   D3.js  │   │ react- │ │
│                    │ (Canvas/ │   │  (SVG)   │   │ flow   │ │
│                    │  WebGL)  │   │          │   │        │ │
│                    └──────────┘   └──────────┘   └────────┘ │
│                         │               │               │    │
│                    Time series    Custom viz       Topology   │
│                    Bar, Pie       Flame chart      Service    │
│                    Gauge          Sankey           maps       │
│                    Heatmap        Geo map                     │
│                    Histogram                                  │
│                                                               │
│  Threshold: > 10K data points → WebGL renderer               │
│             < 10K data points → Canvas renderer               │
│             Custom viz        → SVG (D3)                      │
└──────────────────────────────────────────────────────────────┘
```

### 6.2 ECharts Configuration

```typescript
// Shared ECharts wrapper with performance optimizations
interface ChartProps {
  option: EChartsOption;
  width: number;
  height: number;
  renderer?: 'canvas' | 'svg' | 'webgl';    // Auto-selected by data size
  lazyUpdate?: boolean;                       // Batch updates
  notMerge?: boolean;                         // Full replace vs merge
  theme?: 'dark' | 'light' | string;
  loading?: boolean;
  onEvents?: Record<string, (params: any) => void>;
}

// Performance: auto-downsampling for large datasets
function downsample(data: DataPoint[], maxPoints: number): DataPoint[] {
  if (data.length <= maxPoints) return data;
  // Largest-Triangle-Three-Buckets (LTTB) algorithm
  return lttbDownsample(data, maxPoints);
}
```

### 6.3 Virtual Scrolling Strategy

For large datasets (log streams, tables with 100K+ rows):

```typescript
// TanStack Virtual integration for tables
const virtualizer = useVirtualizer({
  count: rows.length,
  getScrollElement: () => scrollContainerRef.current,
  estimateSize: () => 36,         // Row height estimate
  overscan: 20,                   // Extra rows to render above/below viewport
  enableSmoothScroll: true,
});
```

### 6.4 Color Themes

**Design Tokens** (CSS custom properties):

```css
/* themes/tokens.css */
:root {
  /* Chart palette — 12 distinct colors, colorblind-safe */
  --chart-1: #2563eb;    /* Blue */
  --chart-2: #16a34a;    /* Green */
  --chart-3: #ea580c;    /* Orange */
  --chart-4: #9333ea;    /* Purple */
  --chart-5: #0891b2;    /* Cyan */
  --chart-6: #e11d48;    /* Rose */
  --chart-7: #ca8a04;    /* Yellow */
  --chart-8: #4f46e5;    /* Indigo */
  --chart-9: #059669;    /* Emerald */
  --chart-10: #dc2626;   /* Red */
  --chart-11: #7c3aed;   /* Violet */
  --chart-12: #0284c7;   /* Sky */

  /* Semantic colors */
  --color-success: #16a34a;
  --color-warning: #ca8a04;
  --color-critical: #dc2626;
  --color-info: #2563eb;
}

[data-theme="dark"] {
  --bg-primary: #0a0a0a;
  --bg-secondary: #171717;
  --bg-widget: #1c1c1c;
  --border-default: #2e2e2e;
  --text-primary: #fafafa;
  --text-secondary: #a3a3a3;
}

[data-theme="light"] {
  --bg-primary: #ffffff;
  --bg-secondary: #f5f5f5;
  --bg-widget: #ffffff;
  --border-default: #e5e5e5;
  --text-primary: #0a0a0a;
  --text-secondary: #737373;
}
```

---

## 7. Real-Time Features

### 7.1 WebSocket Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Real-Time Data Flow                            │
│                                                                   │
│  Browser                          Server                         │
│  ┌──────────────┐                ┌──────────────┐               │
│  │ WS Manager   │◄──────────────►│ WS Gateway   │               │
│  │              │   WebSocket     │              │               │
│  │ Subscriptions│   (wss://)     │ Fan-out to   │               │
│  │ - dashboard  │                │ subscribers   │               │
│  │ - widget:1   │                │              │               │
│  │ - widget:2   │                └──────┬───────┘               │
│  │ - live-tail  │                       │                        │
│  └──────┬───────┘                ┌──────▼───────┐               │
│         │                        │ Query Engine │               │
│         ▼                        │ (streaming)  │               │
│  ┌──────────────┐                └──────────────┘               │
│  │ Widget Store │                                                │
│  │ (Zustand)    │  Messages:                                    │
│  │ - data cache │  • widget.data    — query results             │
│  │ - timestamps │  • widget.error   — query errors              │
│  │ - errors     │  • dashboard.sync — collaborative edits       │
│  └──────────────┘  • live-tail.line — streaming log lines       │
│                     • alert.fire     — new alert notifications   │
└─────────────────────────────────────────────────────────────────┘
```

### 7.2 WebSocket Protocol

```typescript
// Client → Server messages
type ClientMessage =
  | { type: 'subscribe'; channel: string; params: Record<string, unknown> }
  | { type: 'unsubscribe'; channel: string }
  | { type: 'query'; id: string; query: string; timeRange: TimeRange }
  | { type: 'cursor'; dashboardId: string; position: { x: number; y: number } }
  | { type: 'lock'; dashboardId: string; widgetId: string }
  | { type: 'unlock'; dashboardId: string; widgetId: string }
  | { type: 'ping' };

// Server → Client messages
type ServerMessage =
  | { type: 'data'; channel: string; payload: unknown; timestamp: number }
  | { type: 'error'; channel: string; error: string; code: number }
  | { type: 'cursor'; userId: string; name: string; position: { x: number; y: number } }
  | { type: 'presence'; users: PresenceUser[] }
  | { type: 'lock.acquired'; widgetId: string; userId: string }
  | { type: 'lock.released'; widgetId: string }
  | { type: 'pong' };
```

### 7.3 Streaming Query Results (SSE)

For long-running queries, use Server-Sent Events to stream partial results:

```typescript
// Streaming query with SSE
async function* streamQuery(query: string, timeRange: TimeRange) {
  const response = await fetch('/api/query/stream', {
    method: 'POST',
    body: JSON.stringify({ query, timeRange }),
    headers: { 'Accept': 'text/event-stream' },
  });

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const chunk = decoder.decode(value);
    yield JSON.parse(chunk) as QueryResultChunk;
  }
}
```

### 7.4 Optimistic UI Updates

When users modify dashboard widgets, changes appear instantly before server confirmation:

```typescript
// Zustand middleware for optimistic updates
const useDashboardStore = create<DashboardStore>()(
  immer((set, get) => ({
    updateWidgetConfig: async (widgetId, config) => {
      // 1. Apply optimistically
      const previousState = get().dashboard;
      set((state) => {
        const widget = state.dashboard!.widgets.find(w => w.id === widgetId);
        if (widget) Object.assign(widget.config, config);
      });

      // 2. Persist to server
      try {
        await api.updateWidget(widgetId, config);
      } catch (error) {
        // 3. Rollback on failure
        set({ dashboard: previousState });
        toast.error('Failed to save widget changes');
      }
    },
  }))
);
```

---

## 8. AI-Powered Dashboard Features

### 8.1 Natural Language to Dashboard

```
┌──────────────────────────────────────────────────────────────────┐
│  Create Dashboard with AI                                        │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  "Create a dashboard for the payment service showing       │  │
│  │   request rate, error rate, latency percentiles, and       │  │
│  │   top errors from the last hour"                           │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                      [Generate]  │
│                                                                   │
│  ┌─ AI is generating your dashboard... ──────────────────────┐  │
│  │                                                            │  │
│  │  ✓ Analyzed available metrics for payment-svc              │  │
│  │  ✓ Selected 6 widgets based on your description            │  │
│  │  ✓ Configured queries with appropriate aggregations        │  │
│  │  ✓ Applied layout and thresholds                           │  │
│  │                                                            │  │
│  │  Generated dashboard preview:                              │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐     │  │
│  │  │ Req Rate │ │ Err Rate │ │ P50 Lat  │ │ P99 Lat  │     │  │
│  │  │ (stat)   │ │ (gauge)  │ │ (stat)   │ │ (stat)   │     │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘     │  │
│  │  ┌─────────────────────────┐ ┌────────────────────────┐   │  │
│  │  │ Latency Over Time       │ │ Top Errors (Table)     │   │  │
│  │  │ (time series)           │ │                        │   │  │
│  │  └─────────────────────────┘ └────────────────────────┘   │  │
│  │                                                            │  │
│  │  [Apply & Edit]                      [Regenerate]         │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

**AI Dashboard Generation Flow**:

1. User provides natural language description
2. Backend AI agent (Claude) analyzes available data sources for mentioned services
3. Agent selects appropriate widget types and metrics
4. Agent generates complete dashboard JSON with queries, layout, and thresholds
5. Frontend renders preview for user approval
6. User can edit, regenerate, or apply the dashboard

### 8.2 AI-Suggested Widgets

When viewing a dashboard, AI can suggest additional widgets:

```typescript
interface WidgetSuggestion {
  title: string;
  description: string;       // Why this widget is recommended
  widgetConfig: WidgetConfig;
  confidence: number;         // 0.0 - 1.0
  reason: 'correlated_metric' | 'missing_coverage' | 'anomaly_context' | 'best_practice';
}
```

Suggestions appear as a non-intrusive sidebar:

```
┌──────────────────────────────────────────────────────────────┐
│  💡 AI Suggestions                                           │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐     │
│  │  Add: Memory Usage for payment-svc                   │     │
│  │  Reason: CPU is monitored but memory is not.         │     │
│  │  This service has had 3 OOM events this week.        │     │
│  │                                          [+ Add]     │     │
│  └─────────────────────────────────────────────────────┘     │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐     │
│  │  Add: Error Log Stream                               │     │
│  │  Reason: Error rate widget shows spikes but there    │     │
│  │  is no log widget to investigate root cause.         │     │
│  │                                          [+ Add]     │     │
│  └─────────────────────────────────────────────────────┘     │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

### 8.3 Anomaly Highlighting

AI-detected anomalies are overlaid on time series charts:

- **Anomaly band**: Shaded region showing expected range (based on historical patterns)
- **Anomaly markers**: Red dots or vertical bands at points exceeding expected range
- **Anomaly tooltip**: "This value is 3.2 standard deviations above the 7-day average for this time of day"
- **Drill-down**: Click anomaly marker to see correlated anomalies across other metrics
- **Suppression**: Users can dismiss false positives, which feeds back into the ML model

### 8.4 AI-Generated Dashboard Descriptions

When saving or sharing a dashboard, AI generates a human-readable summary:

> "This dashboard monitors the **payment-svc** in production. It tracks request throughput (currently 1.2K req/s), error rates (0.23%), and latency percentiles (P99: 234ms). The SLO widget shows 99.97% availability against a 99.95% target. There is 1 active warning alert for elevated P99 latency."

---

## 9. Dashboard Sharing & Permissions

### 9.1 Sharing Model

```
┌──────────────────────────────────────────────────────────────┐
│  Share Dashboard: Production Overview                         │
│                                                               │
│  Visibility                                                   │
│  ○ Private (only you)                                        │
│  ● Organization (all members of Acme Corp)                   │
│  ○ Public link (anyone with the link)                        │
│  ○ Password protected                                        │
│                                                               │
│  Permissions                                                  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ User / Team         │ Permission     │                 │  │
│  ├─────────────────────┼────────────────┼─────────────────┤  │
│  │ Platform Team       │ [Admin ▼]      │ [Remove]        │  │
│  │ alice@acme.com      │ [Edit  ▼]      │ [Remove]        │  │
│  │ bob@acme.com        │ [View  ▼]      │ [Remove]        │  │
│  │ On-Call Group       │ [View  ▼]      │ [Remove]        │  │
│  └────────────────────────────────────────────────────────┘  │
│  [+ Add user or team]                                        │
│                                                               │
│  Link:  https://app.rayolly.io/d/abc123?share=tok_xyz       │
│  [Copy Link]                                                  │
│                                                               │
│  Embed:                                                       │
│  <iframe src="https://app.rayolly.io/embed/abc123?...">     │
│  [Copy Embed Code]                                           │
│                                                               │
│  Advanced                                                     │
│  [✓] Allow viewers to change time range                      │
│  [✓] Allow viewers to change variables                       │
│  [ ] Hide variable bar                                       │
│  [ ] Hide widget titles                                      │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

### 9.2 Permission Levels

| Level | View | Change Time/Vars | Edit Widgets | Manage Sharing | Delete |
|---|---|---|---|---|---|
| **Viewer** | Yes | Yes | No | No | No |
| **Editor** | Yes | Yes | Yes | No | No |
| **Admin** | Yes | Yes | Yes | Yes | Yes |

### 9.3 Snapshot Sharing

Create a point-in-time snapshot of a dashboard with frozen data:

```typescript
interface DashboardSnapshot {
  id: string;
  dashboardId: string;
  createdAt: string;
  createdBy: User;
  expiresAt: string;           // Auto-expire after N days
  timeRange: TimeRange;
  variableValues: Record<string, string>;
  widgetData: Record<string, unknown>; // Frozen query results
  accessControl: 'public' | 'org' | 'password';
}
```

### 9.4 Scheduled Reports

```
┌──────────────────────────────────────────────────────────────┐
│  Schedule Report: Production Overview                         │
│                                                               │
│  Format:     [PDF ▼]  (PDF, PNG, CSV)                        │
│  Frequency:  [Weekly ▼]                                       │
│  Day:        [Monday ▼]                                       │
│  Time:       [09:00 AM ▼]  Timezone: [UTC ▼]                │
│  Time Range: [Last 7 days ▼]                                 │
│                                                               │
│  Recipients:                                                  │
│  [platform-team@acme.com]  [+ Add]                           │
│  [alice@acme.com]          [+ Add]                           │
│                                                               │
│  Message:                                                     │
│  [Weekly production health summary]                          │
│                                                               │
│  [Cancel]                                     [Save Schedule] │
└──────────────────────────────────────────────────────────────┘
```

### 9.5 TV / Kiosk Mode

Full-screen display mode for NOC screens and war rooms:

- Removes all navigation chrome (sidebar, header, breadcrumbs)
- Auto-cycles through multiple dashboards on a configurable interval
- Larger fonts and higher contrast for wall-mounted displays
- Optional clock overlay
- Auto-refresh always enabled
- URL parameter: `?kiosk=true&cycle=30s&dashboards=id1,id2,id3`

---

## 10. Navigation & Information Architecture

### 10.1 Global Navigation

```
┌──────────────────────────────────────────────────────────────────┐
│ ┌────┐                                                           │
│ │ R  │  RayOlly       [Cmd+K Search...]          [🔔] [👤 Alice]│
│ └────┘                                                           │
├──────────┬───────────────────────────────────────────────────────┤
│          │                                                       │
│  ◀ Nav   │  Dashboards > Platform Team > Production Overview     │
│          │                                                       │
│ ┌──────┐ │  ┌────────────────────────────────────────────────┐  │
│ │ 📊   │ │  │                                                │  │
│ │Dash- │ │  │        Dashboard Content Area                  │  │
│ │boards│ │  │                                                │  │
│ ├──────┤ │  │                                                │  │
│ │ 🔍   │ │  │                                                │  │
│ │Explore│ │  │                                                │  │
│ ├──────┤ │  │                                                │  │
│ │ 🔔   │ │  │                                                │  │
│ │Alerts│ │  │                                                │  │
│ ├──────┤ │  │                                                │  │
│ │ 🎯   │ │  │                                                │  │
│ │ SLOs │ │  │                                                │  │
│ ├──────┤ │  │                                                │  │
│ │ 🤖   │ │  │                                                │  │
│ │AI    │ │  │                                                │  │
│ │Agent │ │  │                                                │  │
│ ├──────┤ │  └────────────────────────────────────────────────┘  │
│ │ ⚙️   │ │                                                       │
│ │Settng│ │                                                       │
│ └──────┘ │                                                       │
└──────────┴───────────────────────────────────────────────────────┘
```

### 10.2 Command Palette (Cmd+K)

```
┌──────────────────────────────────────────────────────────────┐
│  ┌────────────────────────────────────────────────────────┐  │
│  │ 🔍  payment service latency...                         │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                               │
│  Dashboards                                                   │
│  ├─ 📊 Payment Pipeline Dashboard            Cmd+Enter       │
│  └─ 📊 Service Overview (payment-svc)        Cmd+Enter       │
│                                                               │
│  Metrics                                                      │
│  ├─ 📈 payment.request.latency.p99                           │
│  └─ 📈 payment.request.rate                                  │
│                                                               │
│  Services                                                     │
│  └─ 🔧 payment-svc (production)                              │
│                                                               │
│  Actions                                                      │
│  ├─ ➕ Create new dashboard                   Cmd+N          │
│  ├─ 🔍 Explore logs                          Cmd+Shift+L    │
│  └─ 🤖 Ask AI about payment service          Cmd+Shift+A    │
│                                                               │
│  Recent                                                       │
│  ├─ 📊 Production Overview                   (2 min ago)     │
│  └─ 🔍 Trace: ord_8f2k                       (15 min ago)    │
└──────────────────────────────────────────────────────────────┘
```

### 10.3 Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Cmd+K` / `Ctrl+K` | Open command palette |
| `Cmd+N` | Create new dashboard |
| `Cmd+S` | Save dashboard |
| `Cmd+Z` / `Cmd+Shift+Z` | Undo / Redo |
| `Cmd+Shift+L` | Open log explorer |
| `Cmd+Shift+M` | Open metric explorer |
| `Cmd+Shift+T` | Open trace explorer |
| `Cmd+Shift+F` | Toggle fullscreen / kiosk mode |
| `E` | Enter edit mode (when viewing dashboard) |
| `Escape` | Exit edit mode / close modal |
| `T` | Open time picker |
| `R` | Refresh dashboard |
| `?` | Show keyboard shortcuts help |
| `Arrow keys` | Navigate between widgets (when not editing) |
| `Enter` | Drill into selected widget |

### 10.4 Context Switching

Hierarchical context navigation:

```
Organization: Acme Corp
  └─ Team: Platform Team
       └─ Environment: production
            └─ Service: payment-svc
                 └─ Dashboard: Payment Pipeline
```

Context is preserved in URL and shared via links. Switching context filters all data globally.

---

## 11. Responsive Design

### 11.1 Breakpoint Strategy

| Breakpoint | Width | Columns | Behavior |
|---|---|---|---|
| **Desktop XL** | >= 1920px | 24 | Full layout, sidebar expanded |
| **Desktop** | >= 1200px | 24 | Full layout, sidebar collapsed by default |
| **Tablet** | >= 768px | 12 | Widgets reflow to 12-col grid, sidebar overlay |
| **Mobile** | < 768px | 1 | Single column stack, bottom navigation |

### 11.2 Widget Reflow

```
Desktop (24 columns):
┌──────────┐ ┌──────────┐ ┌──────────┐
│  Widget 1 │ │  Widget 2 │ │  Widget 3 │
│  (8 cols) │ │  (8 cols) │ │  (8 cols) │
└──────────┘ └──────────┘ └──────────┘

Tablet (12 columns):
┌──────────┐ ┌──────────┐
│  Widget 1 │ │  Widget 2 │
│  (6 cols) │ │  (6 cols) │
└──────────┘ └──────────┘
┌──────────┐
│  Widget 3 │
│  (6 cols) │
└──────────┘

Mobile (1 column):
┌──────────────────────┐
│  Widget 1 (full)     │
└──────────────────────┘
┌──────────────────────┐
│  Widget 2 (full)     │
└──────────────────────┘
┌──────────────────────┐
│  Widget 3 (full)     │
└──────────────────────┘
```

### 11.3 Mobile-Optimized Incident View

On mobile, the incident view shows a condensed single-column layout:
- Alert summary card at top
- Affected service quick-stats
- Swipeable tabs: Timeline | Logs | Metrics | Actions
- One-tap acknowledge/resolve
- Push notifications integration

---

## 12. Performance Targets

### 12.1 Core Web Vitals

| Metric | Target | Measurement |
|---|---|---|
| **First Contentful Paint (FCP)** | < 1.5s | Lighthouse, RUM |
| **Largest Contentful Paint (LCP)** | < 2.5s | Lighthouse, RUM |
| **Time to Interactive (TTI)** | < 3.0s | Lighthouse |
| **Cumulative Layout Shift (CLS)** | < 0.1 | Lighthouse, RUM |
| **First Input Delay (FID)** | < 100ms | RUM |
| **Interaction to Next Paint (INP)** | < 200ms | RUM |

### 12.2 Application-Specific Metrics

| Metric | Target | Notes |
|---|---|---|
| **Dashboard load (20 widgets)** | < 2.0s | From URL navigation to all widgets rendered |
| **Chart render (100K data points)** | < 500ms | Using LTTB downsampling + WebGL |
| **Chart render (1M data points)** | < 2.0s | Using WebGL renderer + progressive loading |
| **Widget refresh (single)** | < 300ms | Query + render for one widget |
| **Time range change** | < 500ms | All widgets re-query and render |
| **Variable change** | < 500ms | All dependent widgets re-query |
| **Initial JS bundle** | < 500KB | Gzipped, code-split by route |
| **Widget JS (lazy)** | < 50KB each | Per-widget code splitting |
| **WebSocket latency** | < 100ms | Client receives data within 100ms of generation |
| **Memory usage** | < 200MB | For 20-widget dashboard with live data |

### 12.3 Performance Optimization Strategies

1. **Streaming SSR**: Dashboard shell renders server-side; widgets stream in via Suspense
2. **Code splitting**: Each widget type is a separate lazy-loaded chunk
3. **Route-level splitting**: Dashboard, Explore, Alerts are separate route bundles
4. **Data downsampling**: LTTB algorithm reduces 100K points to ~2K for rendering
5. **WebGL rendering**: ECharts WebGL renderer for datasets > 10K points
6. **Request deduplication**: Multiple widgets with overlapping queries share a single request
7. **Query caching**: TanStack Query caches results with configurable stale time
8. **Virtual rendering**: Large tables and log streams use windowed rendering
9. **Image optimization**: Next.js Image component for static assets
10. **Font subsetting**: Only load required character sets
11. **Prefetching**: Prefetch dashboard data on hover over dashboard links
12. **Service Worker**: Cache static assets and API responses for instant revisits

---

## 13. Accessibility

### 13.1 WCAG 2.1 AA Compliance

| Requirement | Implementation |
|---|---|
| **Perceivable** | |
| Text contrast ratio >= 4.5:1 | Enforced via Tailwind CSS theme tokens |
| Non-text contrast >= 3:1 | Chart colors verified against both themes |
| Images have alt text | All icons have aria-labels |
| Content reflows at 400% zoom | Responsive layout scales to 400% |
| **Operable** | |
| All interactive elements keyboard accessible | Tab order follows visual layout |
| No keyboard traps | Escape closes all modals/popovers |
| Focus indicators visible | Custom focus ring (2px solid, high contrast) |
| Skip navigation links | "Skip to main content" link on Tab |
| No content flashing > 3/sec | Animations respect `prefers-reduced-motion` |
| **Understandable** | |
| Error messages are descriptive | Form validation with inline messages |
| Labels associated with inputs | All form controls have labels |
| Consistent navigation | Sidebar and breadcrumbs persist |
| **Robust** | |
| Valid HTML semantics | Landmarks, headings, lists used correctly |
| ARIA attributes where needed | Radix UI provides built-in ARIA |
| Screen reader announcements | Live regions for dynamic content |

### 13.2 Colorblind-Friendly Themes

Three built-in colorblind-safe palettes:

| Theme | Designed For | Palette |
|---|---|---|
| **Deuteranopia** | Red-green (most common) | Blue, orange, yellow, purple, cyan |
| **Protanopia** | Red-blind | Blue, yellow, cyan, magenta, gray |
| **Tritanopia** | Blue-yellow (rare) | Red, green, magenta, cyan, orange |

Charts always use distinct patterns (dashed, dotted, solid) in addition to color to differentiate series.

### 13.3 Screen Reader Support

- Charts provide a text-based data summary accessible to screen readers
- Tables use proper `<thead>`, `<tbody>`, `scope` attributes
- Dashboard grid announces widget positions ("Widget 3 of 12: Request Rate, row 1, columns 1 through 8")
- Live data updates are announced via `aria-live="polite"` regions
- Alert status changes use `aria-live="assertive"`

---

## 14. Grafana Import

### 14.1 Import Flow

```
┌──────────────────────────────────────────────────────────────┐
│  Import Grafana Dashboard                                     │
│                                                               │
│  Upload:  [Choose JSON file]  or  [Paste JSON]               │
│                                                               │
│  ──── or ────                                                │
│                                                               │
│  Grafana URL: [https://grafana.internal/api/dashboards/...]  │
│  API Key:     [glsa_xxxxx...]                                │
│  [Connect & Import]                                           │
│                                                               │
│  ─────────────────────────────────────────────────────────── │
│                                                               │
│  Import Preview:                                              │
│                                                               │
│  Dashboard: "Production K8s Cluster"                         │
│  Panels: 18 found                                             │
│                                                               │
│  ✅ 14 panels — full compatibility                           │
│  ⚠️  3 panels — partial (missing plugin: grafana-piechart)   │
│  ❌  1 panel  — unsupported (custom plugin: corp-heatmap)    │
│                                                               │
│  Variable Mapping:                                            │
│  ┌─────────────────┬─────────────────┬───────────────────┐   │
│  │ Grafana Variable│ Type            │ RayOlly Mapping   │   │
│  ├─────────────────┼─────────────────┼───────────────────┤   │
│  │ $cluster        │ query           │ ✅ Auto-mapped     │   │
│  │ $namespace      │ query           │ ✅ Auto-mapped     │   │
│  │ $interval       │ interval        │ ✅ Auto-mapped     │   │
│  └─────────────────┴─────────────────┴───────────────────┘   │
│                                                               │
│  Data Source Mapping:                                         │
│  ┌─────────────────┬───────────────────────────────────┐     │
│  │ Grafana Source   │ RayOlly Source                    │     │
│  ├─────────────────┼───────────────────────────────────┤     │
│  │ Prometheus       │ [RayOlly Metrics (PromQL) ▼]     │     │
│  │ Loki             │ [RayOlly Logs ▼]                 │     │
│  │ Elasticsearch    │ [RayOlly Logs ▼]                 │     │
│  └─────────────────┴───────────────────────────────────┘     │
│                                                               │
│  [Cancel]                           [Import Dashboard]       │
└──────────────────────────────────────────────────────────────┘
```

### 14.2 Grafana Panel Compatibility Map

| Grafana Panel | RayOlly Widget | Compatibility |
|---|---|---|
| `timeseries` | `TimeSeriesChart` | Full |
| `graph` (legacy) | `TimeSeriesChart` | Full |
| `stat` | `GaugeStat` (stat mode) | Full |
| `gauge` | `GaugeStat` (gauge mode) | Full |
| `table` | `TableWidget` | Full |
| `barchart` | `BarChart` | Full |
| `heatmap` | `Heatmap` | Full |
| `histogram` | `Histogram` | Full |
| `piechart` | `PieDonut` | Full |
| `text` | `MarkdownText` | Full |
| `alertlist` | `AlertStatus` | Full |
| `logs` | `LogStream` | Full |
| `nodeGraph` | `ServiceMap` | Partial (layout differences) |
| `geomap` | `GeoMap` | Partial (layer subset) |
| `state-timeline` | `TimeSeriesChart` (step) | Partial |
| `status-history` | `Heatmap` | Partial |
| `traces` | `FlameChart` | Full |
| `flamegraph` | `FlameChart` | Full |

### 14.3 Query Translation

```typescript
// Grafana PromQL queries are natively supported
// Grafana Loki LogQL → RayOlly Log Query translation

interface QueryTranslation {
  source: 'promql' | 'logql' | 'elasticsearch' | 'influxql';
  target: 'roql' | 'promql';  // RayOlly supports PromQL natively
  translator: (query: string, variables: VariableMap) => TranslatedQuery;
}

// Example: LogQL → ROQL
// Grafana:  {job="payment"} |= "error" | json | rate [5m]
// RayOlly:  SELECT count(*) FROM logs WHERE service='payment' AND message LIKE '%error%' GROUP BY time(5m)
```

### 14.4 Bulk Import

For organizations migrating from Grafana:

```bash
# Export all dashboards from Grafana
rayolly import grafana \
  --url https://grafana.internal \
  --api-key glsa_xxxxx \
  --folder "/Production" \
  --dry-run                       # Preview without importing

# Import with data source mapping
rayolly import grafana \
  --url https://grafana.internal \
  --api-key glsa_xxxxx \
  --datasource-map prometheus=rayolly-metrics \
  --datasource-map loki=rayolly-logs \
  --target-folder "/Imported from Grafana"
```

---

## 15. Frontend Project Structure

Detailed directory tree for the web application:

```
apps/web/
├── app/
│   ├── (auth)/
│   │   ├── login/
│   │   │   └── page.tsx
│   │   ├── signup/
│   │   │   └── page.tsx
│   │   └── layout.tsx                    # Auth layout (no sidebar)
│   │
│   ├── (main)/
│   │   ├── layout.tsx                    # Main layout (sidebar + header)
│   │   │
│   │   ├── dashboards/
│   │   │   ├── page.tsx                  # Dashboard list (server component)
│   │   │   ├── new/
│   │   │   │   └── page.tsx              # Create dashboard
│   │   │   └── folders/
│   │   │       └── [folderId]/
│   │   │           └── page.tsx          # Folder view
│   │   │
│   │   ├── d/[dashboardId]/
│   │   │   ├── page.tsx                  # Dashboard view (server component, streams widgets)
│   │   │   ├── edit/
│   │   │   │   └── page.tsx              # Dashboard edit mode
│   │   │   ├── settings/
│   │   │   │   └── page.tsx              # Dashboard settings (variables, permissions)
│   │   │   ├── history/
│   │   │   │   └── page.tsx              # Version history
│   │   │   ├── share/
│   │   │   │   └── page.tsx              # Sharing settings
│   │   │   └── loading.tsx               # Suspense fallback
│   │   │
│   │   ├── explore/
│   │   │   ├── page.tsx                  # Explore hub
│   │   │   ├── logs/
│   │   │   │   └── page.tsx              # Log explorer
│   │   │   ├── metrics/
│   │   │   │   └── page.tsx              # Metric explorer
│   │   │   └── traces/
│   │   │       └── page.tsx              # Trace explorer
│   │   │
│   │   ├── alerts/
│   │   │   ├── page.tsx                  # Alert list
│   │   │   ├── [alertId]/
│   │   │   │   └── page.tsx              # Alert detail
│   │   │   └── rules/
│   │   │       └── page.tsx              # Alert rules
│   │   │
│   │   ├── slos/
│   │   │   ├── page.tsx                  # SLO list
│   │   │   └── [sloId]/
│   │   │       └── page.tsx              # SLO detail
│   │   │
│   │   ├── ai/
│   │   │   └── page.tsx                  # AI assistant / chat
│   │   │
│   │   └── settings/
│   │       ├── page.tsx                  # Settings hub
│   │       ├── organization/
│   │       │   └── page.tsx
│   │       ├── teams/
│   │       │   └── page.tsx
│   │       ├── users/
│   │       │   └── page.tsx
│   │       ├── data-sources/
│   │       │   └── page.tsx
│   │       └── api-keys/
│   │           └── page.tsx
│   │
│   ├── embed/[dashboardId]/
│   │   └── page.tsx                      # Embeddable dashboard (no chrome)
│   │
│   ├── kiosk/
│   │   └── page.tsx                      # TV/kiosk mode
│   │
│   ├── layout.tsx                        # Root layout
│   ├── globals.css
│   ├── not-found.tsx
│   └── error.tsx
│
├── components/
│   ├── dashboard/
│   │   ├── DashboardGrid.tsx             # Grid layout (dnd-kit)
│   │   ├── DashboardHeader.tsx           # Title, time picker, variables
│   │   ├── DashboardToolbar.tsx          # Edit mode toolbar
│   │   ├── WidgetWrapper.tsx             # Widget container with menu
│   │   ├── WidgetPalette.tsx             # Draggable widget palette
│   │   ├── WidgetConfigPanel.tsx         # Right-side config panel
│   │   ├── VariableBar.tsx               # Template variable selectors
│   │   ├── TimeRangePicker.tsx           # Global time picker
│   │   ├── AutoRefreshPicker.tsx         # Refresh interval selector
│   │   ├── DashboardVersionHistory.tsx   # Version diff viewer
│   │   ├── CollaborationPresence.tsx     # User cursors/presence
│   │   └── AIGenerateDialog.tsx          # NL → dashboard dialog
│   │
│   ├── widgets/
│   │   ├── WidgetRenderer.tsx            # Dynamic widget loader
│   │   ├── TimeSeriesChart.tsx
│   │   ├── BarChart.tsx
│   │   ├── GaugeStat.tsx
│   │   ├── TableWidget.tsx
│   │   ├── Heatmap.tsx
│   │   ├── Histogram.tsx
│   │   ├── PieDonut.tsx
│   │   ├── ServiceMap.tsx
│   │   ├── LogStream.tsx
│   │   ├── FlameChart.tsx
│   │   ├── MarkdownText.tsx
│   │   ├── AlertStatus.tsx
│   │   ├── SLOStatus.tsx
│   │   ├── GeoMap.tsx
│   │   └── SankeyDiagram.tsx
│   │
│   ├── query/
│   │   ├── QueryEditor.tsx               # Monaco-based query editor
│   │   ├── QueryBuilder.tsx              # Visual query builder
│   │   ├── DataSourcePicker.tsx
│   │   └── QueryInspector.tsx            # Debug query results
│   │
│   ├── navigation/
│   │   ├── Sidebar.tsx
│   │   ├── Breadcrumbs.tsx
│   │   ├── CommandPalette.tsx
│   │   ├── ContextSwitcher.tsx
│   │   └── UserMenu.tsx
│   │
│   └── shared/
│       ├── LoadingSkeleton.tsx
│       ├── ErrorBoundary.tsx
│       ├── EmptyState.tsx
│       └── ConfirmDialog.tsx
│
├── hooks/
│   ├── useWebSocket.ts                   # WebSocket connection manager
│   ├── useDashboard.ts                   # Dashboard data hook
│   ├── useWidgetData.ts                  # Per-widget query + caching
│   ├── useTimeRange.ts                   # Time range state
│   ├── useVariables.ts                   # Template variable resolution
│   ├── useKeyboardShortcuts.ts           # Global keyboard shortcuts
│   ├── useCollaboration.ts               # Real-time collaboration
│   └── useTheme.ts                       # Theme management
│
├── stores/
│   ├── dashboardStore.ts                 # Dashboard state (Zustand)
│   ├── realtimeStore.ts                  # WebSocket state
│   ├── uiStore.ts                        # UI preferences (sidebar, theme)
│   └── userStore.ts                      # Auth/user state
│
├── lib/
│   ├── api/
│   │   ├── client.ts                     # Base API client (fetch)
│   │   ├── dashboards.ts                 # Dashboard CRUD
│   │   ├── queries.ts                    # Query execution
│   │   ├── alerts.ts                     # Alert API
│   │   └── users.ts                      # User/auth API
│   ├── grafana/
│   │   ├── importer.ts                   # Grafana JSON parser
│   │   ├── panelMapper.ts                # Panel → Widget mapper
│   │   └── queryTranslator.ts            # Query translation
│   ├── utils/
│   │   ├── downsample.ts                 # LTTB downsampling
│   │   ├── format.ts                     # Number formatting
│   │   ├── color.ts                      # Color utilities
│   │   └── time.ts                       # Time range math
│   └── constants.ts
│
├── __tests__/
│   ├── components/                       # Component unit tests
│   ├── hooks/                            # Hook tests
│   ├── stores/                           # Store tests
│   └── e2e/                              # Playwright E2E tests
│       ├── dashboard.spec.ts
│       ├── explore.spec.ts
│       └── grafana-import.spec.ts
│
├── next.config.ts
├── tailwind.config.ts
├── tsconfig.json
├── vitest.config.ts
└── playwright.config.ts
```

---

## 16. Success Metrics

### 16.1 Adoption Metrics

| Metric | Target (6 months post-GA) | Measurement |
|---|---|---|
| Daily Active Users (DAU) | 60% of org users | Auth + page views |
| Dashboards created per org | 50+ | Dashboard count |
| Avg widgets per dashboard | 8+ | Widget count |
| AI-generated dashboards | 20% of new dashboards | Creation source tracking |
| Grafana imports completed | 100+ orgs | Import events |
| Dashboards shared externally | 30% of dashboards | Share events |

### 16.2 Performance Metrics (RUM)

| Metric | Target | P50 | P95 |
|---|---|---|---|
| FCP | < 1.5s | < 0.8s | < 1.5s |
| LCP | < 2.5s | < 1.5s | < 2.5s |
| TTI | < 3.0s | < 2.0s | < 3.0s |
| Dashboard load (20 widgets) | < 2.0s | < 1.2s | < 2.0s |
| Widget refresh | < 300ms | < 150ms | < 300ms |

### 16.3 Engagement Metrics

| Metric | Target | Notes |
|---|---|---|
| Avg time on dashboard | > 5 min | Active engagement, not idle |
| Dashboard revisit rate | > 70% | Users return to same dashboard within 24h |
| Edit-to-view ratio | > 15% | Users customize dashboards |
| Collaborative edit sessions | > 10% of edit sessions | Multiple users editing simultaneously |
| TV/kiosk mode adoption | > 20% of orgs | At least one kiosk display |
| Scheduled report adoption | > 30% of orgs | At least one scheduled report |

### 16.4 Quality Metrics

| Metric | Target | Notes |
|---|---|---|
| Client-side error rate | < 0.1% | JS errors / page views |
| WebSocket reconnection rate | < 5% per hour | Connection stability |
| Lighthouse performance score | > 90 | Desktop audit |
| Accessibility audit score | > 95 | axe-core automated checks |
| Grafana import success rate | > 90% | Full/partial compatibility |
| Bundle size regression | 0% | CI check on every PR |

---

## 17. Risks & Mitigations

### 17.1 Technical Risks

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| **ECharts bundle size** — ECharts is ~1MB uncompressed | High | Medium | Tree-shake unused chart types; lazy-load per widget type; use `echarts/core` with registered components only |
| **WebSocket scalability** — 1000s of concurrent connections per dashboard | Medium | High | Use WebSocket gateway with connection pooling; implement fan-out via Redis pub/sub; fall back to SSE for view-only users |
| **React 19 instability** — Server Components API may change | Low | High | Abstract RSC usage behind thin wrappers; maintain escape hatch to client components; pin React version |
| **Monaco Editor size** — ~2MB for full editor | High | Medium | Lazy-load only when query panel opens; use lighter editor (CodeMirror) for inline/small queries; Monaco workers via CDN |
| **Collaborative editing conflicts** — CRDT complexity | Medium | Medium | Start with widget-level locking (simpler); evolve to field-level CRDT if needed; Yjs has proven production track record |
| **100K+ data point rendering** — browser memory/CPU | Medium | High | LTTB downsampling on client; server-side pre-aggregation; WebGL renderer; progressive loading |
| **Grafana import accuracy** — edge cases in JSON format | High | Medium | Start with top 10 most-used panel types; community-reported compatibility tracker; graceful degradation for unsupported panels |

### 17.2 Product Risks

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| **Grafana community loyalty** — users prefer open-source Grafana | High | High | Emphasize AI-native features Grafana lacks; provide frictionless import; Apache 2.0 license (more permissive than Grafana's AGPL) |
| **Feature parity gap** — Grafana has 100+ plugins | Medium | High | Focus on native quality over quantity; prioritize the 15 widget types that cover 95% of use cases; plugin SDK in v2 |
| **AI dashboard quality** — generated dashboards may be poor | Medium | Medium | Use few-shot examples; template-based generation with AI customization; always show preview before applying; collect feedback |
| **Learning curve** — new query language (ROQL) | Medium | Medium | Support PromQL and SQL natively; visual query builder for non-power-users; AI query generation from natural language |

### 17.3 Organizational Risks

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| **Scope creep** — dashboard features are infinite | High | High | Strict adherence to 15 widget types for v1; clear non-goals; bi-weekly scope review |
| **Frontend team scaling** — need 6-8 frontend engineers | Medium | High | Monorepo + package structure enables parallel development; Storybook for independent widget development |
| **Design consistency** — multiple engineers building widgets | Medium | Medium | Shared design system in `packages/ui`; Storybook visual regression tests; design review checklist |

---

## Appendix A: Dashboard JSON Schema (v1)

```typescript
interface Dashboard {
  apiVersion: 'rayolly.io/v1';
  kind: 'Dashboard';
  metadata: {
    id: string;
    name: string;
    slug: string;
    description: string;
    folder: string;
    tags: string[];
    createdAt: string;
    updatedAt: string;
    createdBy: string;
    version: number;
  };
  spec: {
    variables: TemplateVariable[];
    timeRange: {
      default: string;           // "now-1h", "now-24h", etc.
      refreshInterval: string;   // "30s", "1m", "off"
    };
    layout: {
      columns: 24;
      rowHeight: number;
    };
    widgets: WidgetConfig[];
    annotations: AnnotationConfig[];
    links: DashboardLink[];
  };
}

interface WidgetConfig {
  id: string;
  type: WidgetType;
  title: string;
  description?: string;
  position: { x: number; y: number; w: number; h: number };
  query: QueryConfig | QueryConfig[];
  options: Record<string, unknown>;   // Widget-type-specific options
  thresholds?: Threshold[];
  overrides?: FieldOverride[];
  timeRangeOverride?: string;         // Per-widget time range
  transparent?: boolean;
  repeatVariable?: string;            // Repeat widget for each variable value
}

type WidgetType =
  | 'timeseries'
  | 'bar'
  | 'gauge'
  | 'stat'
  | 'table'
  | 'heatmap'
  | 'histogram'
  | 'pie'
  | 'donut'
  | 'service-map'
  | 'log-stream'
  | 'flame-chart'
  | 'markdown'
  | 'alert-status'
  | 'slo-status'
  | 'geo-map'
  | 'sankey';
```

---

## Appendix B: Component Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Component Hierarchy                            │
│                                                                       │
│  RootLayout                                                          │
│  ├── ThemeProvider                                                    │
│  ├── AuthProvider                                                    │
│  ├── WebSocketProvider                                               │
│  └── MainLayout                                                      │
│      ├── Sidebar                                                     │
│      │   ├── Logo                                                    │
│      │   ├── NavItem (Dashboards)                                    │
│      │   ├── NavItem (Explore)                                       │
│      │   ├── NavItem (Alerts)                                        │
│      │   ├── NavItem (SLOs)                                          │
│      │   ├── NavItem (AI Agent)                                      │
│      │   └── NavItem (Settings)                                      │
│      ├── Header                                                      │
│      │   ├── Breadcrumbs                                             │
│      │   ├── CommandPalette (Cmd+K)                                  │
│      │   ├── NotificationBell                                        │
│      │   └── UserMenu                                                │
│      └── PageContent                                                 │
│          └── DashboardPage (Server Component)                        │
│              ├── DashboardHeader (Client)                             │
│              │   ├── TitleEditor                                     │
│              │   ├── VariableBar                                     │
│              │   │   └── VariableSelect (per variable)               │
│              │   ├── TimeRangePicker                                  │
│              │   ├── AutoRefreshPicker                                │
│              │   └── DashboardActions (save, share, edit, etc.)      │
│              ├── DashboardGrid (Client)                               │
│              │   └── WidgetWrapper (per widget)                      │
│              │       ├── WidgetHeader (title, menu)                  │
│              │       ├── WidgetRenderer (dynamic import)             │
│              │       │   ├── TimeSeriesChart                         │
│              │       │   ├── BarChart                                │
│              │       │   ├── GaugeStat                               │
│              │       │   ├── TableWidget                             │
│              │       │   ├── (... other widget types)                │
│              │       │   └── WidgetLoading (Suspense fallback)       │
│              │       └── WidgetFooter (last updated, link)           │
│              └── CollaborationPresence (Client)                      │
│                  └── CursorOverlay (per collaborator)                │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Appendix C: API Endpoints (Frontend Consumes)

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/dashboards` | GET | List dashboards (paginated, filterable) |
| `/api/v1/dashboards` | POST | Create dashboard |
| `/api/v1/dashboards/:id` | GET | Get dashboard by ID |
| `/api/v1/dashboards/:id` | PUT | Update dashboard |
| `/api/v1/dashboards/:id` | DELETE | Delete dashboard |
| `/api/v1/dashboards/:id/versions` | GET | List version history |
| `/api/v1/dashboards/:id/versions/:v` | GET | Get specific version |
| `/api/v1/dashboards/:id/share` | POST | Create share link |
| `/api/v1/dashboards/:id/snapshot` | POST | Create snapshot |
| `/api/v1/dashboards/:id/export` | GET | Export as JSON/YAML |
| `/api/v1/dashboards/import` | POST | Import dashboard (JSON/YAML) |
| `/api/v1/dashboards/import/grafana` | POST | Import Grafana dashboard |
| `/api/v1/query` | POST | Execute query |
| `/api/v1/query/stream` | POST | Stream query results (SSE) |
| `/api/v1/query/suggest` | POST | Query autocomplete suggestions |
| `/api/v1/variables/resolve` | POST | Resolve template variable values |
| `/api/v1/ai/generate-dashboard` | POST | AI dashboard generation |
| `/api/v1/ai/suggest-widgets` | POST | AI widget suggestions |
| `wss://ws.rayolly.io/v1/stream` | WS | WebSocket for live data |

---

*PRD-10 v1.0 | RayOlly Dashboards & Visualization Frontend | AI-Native Observability Platform*
