# P2 Session 5 — Frontend Strategies Pages

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-05-22 |
| Phase | **P2**, **§7** |
| Predecessor | *TradingWorkbench_P2_Session4_v0.1.md* (tag `p2-session4-complete`) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | (1) Typed API client modules for strategies, signals, backtests. (2) WS subscription hook for live strategy/signal events. (3) Strategies list page. (4) Strategy detail page with 5 tabs (Overview, Signals, Orders, Backtests, Params). (5) Backtest results view (modal or sub-page) with recharts equity curve + trade list. (6) Vitest tests for the highest-value components. Single PR. |
| Estimated wall time | 5–7 hours |
| Stopping point | `git tag p2-session5-complete` |
| Out of scope | Async backtest progress UI (synchronous endpoint, the page just shows a spinner until the response). Strategy parameter form schemas — params is a JSON textarea in MVP. Cross-strategy P&L attribution rollup (P4 polish). Strategy hot-reload from UI (the engine reads from disk on register; restarting is the workflow). |

---

## Session Goal

After this session:
- A `/strategies` page lists every registered strategy with name, type, status (color-coded badge), symbols, last-run-at, today's signal count, today's strategy-attributed P&L approximation, and a Start/Stop button.
- A `/strategies/:id` page shows the strategy detail with five tabs.
- Trader can register the reference RSI strategy from the UI (a "+ New strategy" button opens a modal with the create form).
- Trader can run a backtest from the UI (the Backtests tab has a "Run backtest" button that opens a config modal; result renders inline with equity curve + trade table).
- Live updates: the Strategies list polls every 5s AND subscribes to the `strategies` WS topic for instant status transitions. The Signals tab polls every 5s AND subscribes to `signals` topic for instant signal arrival.
- Three Vitest tests pass: list page renders + start/stop wiring, detail page tabs switch correctly, backtest results render metrics + recharts.

What does NOT happen this session:
- Real-time chart of equity curve during a running paper deploy. The equity curve view is backtest-only in MVP.
- Inline parameter editor with field-level validation. The Params tab is a JSON textarea + Save button.
- Bulk operations (start-all / stop-all). Per-row buttons only.
- Multi-strategy comparison view. Each strategy renders independently.

---

## Prerequisites Check

```bash
cd ~/code/AI-TRADING-APP
git status                                       # clean
git pull origin main
git describe --tags --abbrev=0                   # expect: p2-session4-complete

# Backend REST surface from Session 4 is reachable
./scripts/dev.sh &
sleep 30
curl -fs http://127.0.0.1:8000/api/v1/strategies | jq '{count, items: (.items | length)}'
# Expect: count: 0 (or some if you've created strategies)

# Reference strategy exists at the expected code_path
ls apps/backend/strategies_user/examples/rsi_meanreversion.py

docker compose down
```

- [ ] On `main`, clean tree, at `p2-session4-complete` or later.
- [ ] `GET /api/v1/strategies` returns a list (empty or otherwise).
- [ ] Reference strategy file exists on disk.

Cut the branch:

```bash
git checkout -b feat/p2-strategies-frontend
```

---

## §5.1 — Typed API Client Modules

Three new client modules, mirroring the backend Pydantic schemas.

### 5.1.1 — Type definitions

Extend `apps/frontend/src/api/types.ts` by appending these types (don't remove anything that exists from P1):

```typescript
// ===== Strategies =====

export type StrategyType = "python" | "pine" | "agent";
export type StrategyStatus = "idle" | "backtest" | "paper" | "live" | "halted" | "error";

export const ACTIVE_STRATEGY_STATUSES: ReadonlyArray<StrategyStatus> = ["paper", "live"];

export interface Strategy {
  id: number;
  name: string;
  version: string;
  type: StrategyType;
  status: StrategyStatus;
  code_path: string | null;
  params: Record<string, unknown>;
  symbols: string[];
  schedule: string;
  risk_limits_id: number | null;
  error_text: string | null;
  created_at: string;
  updated_at: string;
}

export interface StrategyListResponse {
  items: Strategy[];
  count: number;
}

export interface StrategyCreateRequest {
  name: string;
  version?: string;
  type?: StrategyType;
  code_path?: string;
  params?: Record<string, unknown>;
  symbols?: string[];
  schedule?: string;
  risk_limits_id?: number | null;
}

export interface StrategyUpdateRequest {
  params?: Record<string, unknown>;
  symbols?: string[];
  schedule?: string;
  risk_limits_id?: number | null;
  version?: string;
}

export interface StrategyActionResponse {
  strategy_id: number;
  action: "start" | "stop";
  new_status: StrategyStatus;
  run_id: number | null;
}

// ===== Strategy runs =====

export interface StrategyRun {
  id: number;
  strategy_id: number;
  started_at: string;
  ended_at: string | null;
  status: StrategyStatus;
  error_text: string | null;
}

export interface StrategyRunListResponse {
  items: StrategyRun[];
  count: number;
}

// ===== Signals =====

export type SignalTypeT = "entry" | "exit" | "flat" | "info" | "agent_action" | "pine_alert";

export interface Signal {
  id: number;
  strategy_id: number | null;
  symbol: string;
  type: SignalTypeT;
  payload: Record<string, unknown>;
  received_at: string;
  processed_at: string | null;
}

export interface SignalListResponse {
  items: Signal[];
  count: number;
}

// ===== Backtests =====

export interface BacktestRequest {
  start: string;                            // ISO datetime
  end: string;
  label?: string;
  initial_equity?: string;                  // Decimal as string
  slippage_bps?: number;
  commission_per_share?: number;
  timeframe?: string;
  params?: Record<string, unknown>;
  symbols?: string[];
}

export interface BacktestMetricsT {
  total_return: number;
  annualized_return: number;
  sharpe_ratio: number;
  max_drawdown: number;
  win_rate: number;
  profit_factor: number;
  trade_count: number;
  avg_win: number;
  avg_loss: number;
  avg_trade_duration_seconds: number;
  starting_equity: number;
  ending_equity: number;
}

export interface BacktestTradeT {
  symbol: string;
  side: "long" | "short";
  entry_ts: string;
  entry_price: number;
  exit_ts: string | null;
  exit_price: number | null;
  qty: number;
  pnl: number | null;
  duration_seconds: number | null;
  exit_reason: string | null;
}

export interface EquityPointT {
  t: string;
  equity: number;
}

export interface BacktestResult {
  id: number;
  strategy_id: number;
  label: string;
  params: Record<string, unknown>;
  metrics: BacktestMetricsT;
  equity_curve: EquityPointT[];
  trades: BacktestTradeT[];
  range_start: string;
  range_end: string;
  created_at: string;
}

export interface BacktestSummary {
  id: number;
  strategy_id: number;
  label: string;
  metrics: BacktestMetricsT;
  range_start: string;
  range_end: string;
  created_at: string;
}

export interface BacktestListResponse {
  items: BacktestSummary[];
  count: number;
}
```

### 5.1.2 — Strategies API client

Create `apps/frontend/src/api/strategies.ts`:

```typescript
import { apiFetch } from "./client";
import type {
  Strategy,
  StrategyActionResponse,
  StrategyCreateRequest,
  StrategyListResponse,
  StrategyRunListResponse,
  StrategyStatus,
  StrategyType,
  StrategyUpdateRequest,
  SignalListResponse,
  BacktestListResponse,
  BacktestRequest,
  BacktestResult,
} from "./types";

export const strategiesApi = {
  list: (params: { status?: StrategyStatus; type?: StrategyType; limit?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.status) q.set("status", params.status);
    if (params.type) q.set("type", params.type);
    if (params.limit) q.set("limit", String(params.limit));
    const suffix = q.toString() ? `?${q}` : "";
    return apiFetch<StrategyListResponse>(`/api/v1/strategies${suffix}`);
  },

  get: (id: number) => apiFetch<Strategy>(`/api/v1/strategies/${id}`),

  create: (body: StrategyCreateRequest) =>
    apiFetch<Strategy>("/api/v1/strategies", { method: "POST", body }),

  update: (id: number, body: StrategyUpdateRequest) =>
    apiFetch<Strategy>(`/api/v1/strategies/${id}`, { method: "PUT", body }),

  start: (id: number) =>
    apiFetch<StrategyActionResponse>(`/api/v1/strategies/${id}/start`, { method: "POST", body: {} }),

  stop: (id: number) =>
    apiFetch<StrategyActionResponse>(`/api/v1/strategies/${id}/stop`, { method: "POST", body: {} }),

  listRuns: (id: number, limit = 50) =>
    apiFetch<StrategyRunListResponse>(`/api/v1/strategies/${id}/runs?limit=${limit}`),

  listSignals: (id: number, limit = 100) =>
    apiFetch<SignalListResponse>(`/api/v1/strategies/${id}/signals?limit=${limit}`),

  listBacktests: (id: number, limit = 50) =>
    apiFetch<BacktestListResponse>(`/api/v1/strategies/${id}/backtests?limit=${limit}`),

  getBacktest: (id: number, backtestId: number) =>
    apiFetch<BacktestResult>(`/api/v1/strategies/${id}/backtests/${backtestId}`),

  runBacktest: (id: number, body: BacktestRequest) =>
    apiFetch<BacktestResult>(`/api/v1/strategies/${id}/backtest`, { method: "POST", body }),
};
```

### 5.1.3 — Signals client

Create `apps/frontend/src/api/signals.ts`:

```typescript
import { apiFetch } from "./client";
import type { SignalListResponse, SignalTypeT } from "./types";

export const signalsApi = {
  list: (
    params: {
      strategy_id?: number;
      symbol?: string;
      type?: SignalTypeT;
      since?: string;
      limit?: number;
    } = {},
  ) => {
    const q = new URLSearchParams();
    if (params.strategy_id !== undefined) q.set("strategy_id", String(params.strategy_id));
    if (params.symbol) q.set("symbol", params.symbol);
    if (params.type) q.set("type", params.type);
    if (params.since) q.set("since", params.since);
    if (params.limit) q.set("limit", String(params.limit));
    const suffix = q.toString() ? `?${q}` : "";
    return apiFetch<SignalListResponse>(`/api/v1/signals${suffix}`);
  },
};
```

- [ ] `types.ts` extended.
- [ ] `strategies.ts` and `signals.ts` API clients created.

---

## §5.2 — WebSocket Hook for Strategy Events

The Orders / Positions pages from P1 poll at 5s. For strategies, polling alone misses the moment-of-transition feel (a strategy switching IDLE → PAPER should be instantaneous in the UI). Add a hook that subscribes to the relevant WS topics and triggers re-fetches.

Create `apps/frontend/src/hooks/useWorkbenchSocket.ts`:

```typescript
import { useEffect, useRef, useCallback } from "react";

const WS_BASE = import.meta.env.VITE_WS_BASE || "ws://127.0.0.1:8000";

interface WorkbenchMessage {
  topic: string;
  type: string;
  payload: Record<string, unknown>;
  ts: string;
}

type Handler = (msg: WorkbenchMessage) => void;

/**
 * useWorkbenchSocket — subscribe to one or more topics on the workbench WS.
 *
 * The hook owns a single shared WebSocket connection across the app via a
 * module-level singleton, so multiple consumers don't open multiple sockets.
 * Each consumer registers its own (topics, handler) pair; the singleton fans
 * messages to whoever is subscribed to the topic.
 *
 * On reconnect, the singleton re-subscribes to all topics aggregated from
 * active consumers.
 */

interface Subscription {
  topics: string[];
  handler: Handler;
}

class WorkbenchSocketSingleton {
  private ws: WebSocket | null = null;
  private subs = new Set<Subscription>();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectAttempt = 0;

  subscribe(sub: Subscription) {
    this.subs.add(sub);
    this.ensureConnected();
    this.sendSubscribe(sub.topics);
    return () => {
      this.subs.delete(sub);
      // Don't unsubscribe topic-by-topic; other consumers might still want
      // them. The full re-subscribe on reconnect handles cleanup.
      if (this.subs.size === 0) {
        this.close();
      }
    };
  }

  private ensureConnected() {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }
    this.connect();
  }

  private connect() {
    try {
      this.ws = new WebSocket(`${WS_BASE}/ws`);
    } catch (e) {
      console.error("WS connect failed:", e);
      this.scheduleReconnect();
      return;
    }
    this.ws.onopen = () => {
      this.reconnectAttempt = 0;
      // Re-subscribe to every topic any consumer wants
      const allTopics = new Set<string>();
      this.subs.forEach((s) => s.topics.forEach((t) => allTopics.add(t)));
      this.sendSubscribe([...allTopics]);
    };
    this.ws.onmessage = (ev) => {
      try {
        const msg: WorkbenchMessage = JSON.parse(ev.data);
        this.subs.forEach((s) => {
          if (s.topics.includes(msg.topic)) {
            try {
              s.handler(msg);
            } catch (e) {
              console.error("WS handler threw:", e);
            }
          }
        });
      } catch {
        // Ignore non-JSON frames
      }
    };
    this.ws.onclose = () => {
      this.ws = null;
      if (this.subs.size > 0) {
        this.scheduleReconnect();
      }
    };
    this.ws.onerror = () => {
      try {
        this.ws?.close();
      } catch {
        // ignore
      }
    };
  }

  private sendSubscribe(topics: string[]) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    try {
      this.ws.send(JSON.stringify({ action: "subscribe", topics }));
    } catch (e) {
      console.error("WS subscribe send failed:", e);
    }
  }

  private scheduleReconnect() {
    if (this.reconnectTimer) return;
    const backoff = Math.min(30_000, 1_000 * Math.pow(2, this.reconnectAttempt));
    this.reconnectAttempt += 1;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, backoff);
  }

  private close() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    try {
      this.ws?.close();
    } catch {
      // ignore
    }
    this.ws = null;
  }
}

const singleton = new WorkbenchSocketSingleton();

export function useWorkbenchSocket(topics: string[], handler: Handler) {
  const handlerRef = useRef(handler);
  // Always call the latest handler without forcing re-subscription on every render
  handlerRef.current = handler;

  const stableHandler = useCallback((msg: WorkbenchMessage) => {
    handlerRef.current(msg);
  }, []);

  useEffect(() => {
    const unsub = singleton.subscribe({ topics, handler: stableHandler });
    return unsub;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topics.join(",")]);
}
```

- [ ] Hook created with shared singleton.
- [ ] Reconnect with exponential backoff.

---

## §5.3 — Status Badge + Shared Bits

A small UI primitive for the colored status pill. Used in the list page row and the detail page header.

Create `apps/frontend/src/components/strategies/StatusBadge.tsx`:

```tsx
import type { StrategyStatus } from "@/api/types";

const STYLES: Record<StrategyStatus, { label: string; classes: string }> = {
  idle:     { label: "IDLE",     classes: "bg-gray-700 text-gray-200" },
  backtest: { label: "BACKTEST", classes: "bg-blue-800 text-blue-100" },
  paper:    { label: "PAPER",    classes: "bg-emerald-700 text-emerald-100" },
  live:     { label: "LIVE",     classes: "bg-red-700 text-red-100" },
  halted:   { label: "HALTED",   classes: "bg-amber-700 text-amber-100" },
  error:    { label: "ERROR",    classes: "bg-rose-800 text-rose-100" },
};

export function StatusBadge({ status }: { status: StrategyStatus }) {
  const { label, classes } = STYLES[status];
  return (
    <span className={`inline-block rounded px-2 py-0.5 text-xs font-semibold ${classes}`}>
      {label}
    </span>
  );
}
```

Create `apps/frontend/src/components/strategies/formatters.ts`:

```typescript
export function formatPct(n: number, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return `${(n * 100).toFixed(digits)}%`;
}

export function formatNumber(n: number, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return n.toFixed(digits);
}

export function formatCurrency(n: number, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return `$${n.toFixed(digits)}`;
}

export function formatDuration(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 60) return `${seconds.toFixed(0)}s`;
  if (seconds < 3600) return `${(seconds / 60).toFixed(1)}m`;
  return `${(seconds / 3600).toFixed(2)}h`;
}
```

- [ ] `StatusBadge` and `formatters` created.

---

## §5.4 — Strategies List Page

The landing page for the strategies area. Polls every 5s, subscribes to WS for instant updates.

Create `apps/frontend/src/pages/Strategies/index.tsx`:

```tsx
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { strategiesApi } from "@/api/strategies";
import { signalsApi } from "@/api/signals";
import { ApiError } from "@/api/client";
import type { Strategy } from "@/api/types";
import { ACTIVE_STRATEGY_STATUSES } from "@/api/types";
import { StatusBadge } from "@/components/strategies/StatusBadge";
import { NewStrategyModal } from "./NewStrategyModal";
import { useWorkbenchSocket } from "@/hooks/useWorkbenchSocket";

interface RowStats {
  signalsToday: number;
}

export default function StrategiesListPage() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [stats, setStats] = useState<Map<number, RowStats>>(new Map());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showNew, setShowNew] = useState(false);
  const [actionPending, setActionPending] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await strategiesApi.list();
      setStrategies(resp.items);
      setError(null);

      // Best-effort: fetch today's signal count per strategy. One round-trip
      // each for now; if this becomes slow with many strategies, add an
      // aggregated /strategies/signals_count endpoint in P4.
      const startOfDay = new Date();
      startOfDay.setHours(0, 0, 0, 0);
      const since = startOfDay.toISOString();
      const newStats = new Map<number, RowStats>();
      await Promise.all(
        resp.items.map(async (s) => {
          try {
            const sig = await signalsApi.list({ strategy_id: s.id, since, limit: 1000 });
            newStats.set(s.id, { signalsToday: sig.count });
          } catch {
            newStats.set(s.id, { signalsToday: 0 });
          }
        }),
      );
      setStats(newStats);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load]);

  // WS for instant transitions
  useWorkbenchSocket(["strategies", "signals"], (msg) => {
    if (msg.topic === "strategies") {
      // Any strategy state change triggers a re-fetch
      load();
    } else if (msg.topic === "signals") {
      // Increment the local count optimistically
      const sid = msg.payload.strategy_id as number | null | undefined;
      if (sid !== null && sid !== undefined) {
        setStats((prev) => {
          const next = new Map(prev);
          const cur = next.get(sid) ?? { signalsToday: 0 };
          next.set(sid, { signalsToday: cur.signalsToday + 1 });
          return next;
        });
      }
    }
  });

  async function handleStart(s: Strategy) {
    if (!confirm(`Start strategy "${s.name}" on paper?`)) return;
    setActionPending(s.id);
    try {
      await strategiesApi.start(s.id);
      await load();
    } catch (e) {
      if (e instanceof ApiError) {
        alert(`Start failed: ${e.detail}`);
      } else {
        alert(`Start failed: ${e}`);
      }
    } finally {
      setActionPending(null);
    }
  }

  async function handleStop(s: Strategy) {
    if (!confirm(`Stop strategy "${s.name}"?`)) return;
    setActionPending(s.id);
    try {
      await strategiesApi.stop(s.id);
      await load();
    } catch (e) {
      alert(`Stop failed: ${e}`);
    } finally {
      setActionPending(null);
    }
  }

  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-white">Strategies</h1>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowNew(true)}
            className="rounded bg-blue-700 px-3 py-1 text-sm font-semibold text-white hover:bg-blue-600"
          >
            + New strategy
          </button>
          <button
            onClick={load}
            className="rounded bg-gray-700 px-3 py-1 text-sm text-gray-200"
          >
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded border border-red-700 bg-red-900/40 p-2 text-red-200">
          {error}
        </div>
      )}

      <div className="overflow-x-auto rounded border border-gray-800">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-800 text-gray-300">
            <tr>
              <th className="px-3 py-2">Name</th>
              <th className="px-3 py-2">Type</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Symbols</th>
              <th className="px-3 py-2 text-right">Signals today</th>
              <th className="px-3 py-2">Schedule</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {strategies.length === 0 && !loading && (
              <tr>
                <td colSpan={7} className="px-3 py-4 text-center text-gray-500">
                  No strategies yet. Click "+ New strategy" to register one.
                </td>
              </tr>
            )}
            {strategies.map((s) => (
              <tr key={s.id} className="border-t border-gray-800 hover:bg-gray-900">
                <td className="px-3 py-2 font-semibold">
                  <Link to={`/strategies/${s.id}`} className="text-white hover:underline">
                    {s.name}
                  </Link>
                  <span className="ml-2 text-xs text-gray-500">v{s.version}</span>
                  {s.status === "error" && s.error_text && (
                    <div className="mt-1 text-xs text-rose-400">
                      {s.error_text.slice(0, 80)}{s.error_text.length > 80 ? "…" : ""}
                    </div>
                  )}
                </td>
                <td className="px-3 py-2 text-gray-300">{s.type}</td>
                <td className="px-3 py-2"><StatusBadge status={s.status} /></td>
                <td className="px-3 py-2 text-gray-300">{s.symbols.join(", ") || "—"}</td>
                <td className="px-3 py-2 text-right">{stats.get(s.id)?.signalsToday ?? 0}</td>
                <td className="px-3 py-2 font-mono text-xs text-gray-400">{s.schedule}</td>
                <td className="px-3 py-2 text-right">
                  {ACTIVE_STRATEGY_STATUSES.includes(s.status) ? (
                    <button
                      onClick={() => handleStop(s)}
                      disabled={actionPending === s.id}
                      className="rounded bg-red-800 px-2 py-1 text-xs font-semibold text-white hover:bg-red-700 disabled:bg-gray-700"
                    >
                      {actionPending === s.id ? "…" : "Stop"}
                    </button>
                  ) : (
                    <button
                      onClick={() => handleStart(s)}
                      disabled={actionPending === s.id || s.status === "error"}
                      className="rounded bg-emerald-700 px-2 py-1 text-xs font-semibold text-white hover:bg-emerald-600 disabled:bg-gray-700"
                    >
                      {actionPending === s.id ? "…" : (s.status === "error" ? "Errored" : "Start")}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showNew && (
        <NewStrategyModal
          onClose={() => setShowNew(false)}
          onCreated={async () => {
            setShowNew(false);
            await load();
          }}
        />
      )}
    </div>
  );
}
```

### 5.4.1 — New strategy modal

Create `apps/frontend/src/pages/Strategies/NewStrategyModal.tsx`:

```tsx
import { useState } from "react";
import { strategiesApi } from "@/api/strategies";
import { ApiError } from "@/api/client";
import type { StrategyType } from "@/api/types";

interface Props {
  onClose: () => void;
  onCreated: () => void;
}

const KNOWN_REFERENCE_PATHS = [
  "examples/rsi_meanreversion.py",
];

export function NewStrategyModal({ onClose, onCreated }: Props) {
  const [name, setName] = useState("rsi-mean-reversion");
  const [codePath, setCodePath] = useState("examples/rsi_meanreversion.py");
  const [symbolsText, setSymbolsText] = useState("AAPL");
  const [paramsText, setParamsText] = useState('{"entry_threshold": 30, "exit_threshold": 55}');
  const [schedule, setSchedule] = useState("*/1 * * * *");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCreate() {
    setError(null);
    let parsedParams: Record<string, unknown>;
    try {
      parsedParams = paramsText.trim() ? JSON.parse(paramsText) : {};
    } catch (e) {
      setError(`Params is not valid JSON: ${e}`);
      return;
    }
    const symbols = symbolsText
      .split(/[,\s]+/)
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);
    if (!name.trim()) {
      setError("Name is required");
      return;
    }
    if (!codePath.trim()) {
      setError("Code path is required");
      return;
    }
    setSubmitting(true);
    try {
      await strategiesApi.create({
        name: name.trim(),
        code_path: codePath.trim(),
        type: "python" as StrategyType,
        params: parsedParams,
        symbols,
        schedule,
      });
      onCreated();
    } catch (e) {
      if (e instanceof ApiError) {
        setError(`${e.detail} (status ${e.status})`);
      } else {
        setError(String(e));
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/70">
      <div className="w-[32rem] max-h-[90vh] overflow-y-auto rounded-lg border border-gray-700 bg-gray-950 p-5">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">Register a new strategy</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white">✕</button>
        </div>

        <div className="space-y-3 text-sm text-gray-300">
          <label className="block">
            <span className="text-xs text-gray-400">Name</span>
            <input
              type="text" value={name} onChange={(e) => setName(e.target.value)}
              className="mt-1 w-full rounded bg-gray-800 px-2 py-1 text-white"
            />
          </label>

          <label className="block">
            <span className="text-xs text-gray-400">Code path (under strategies_user/)</span>
            <input
              type="text" value={codePath} onChange={(e) => setCodePath(e.target.value)}
              className="mt-1 w-full rounded bg-gray-800 px-2 py-1 font-mono text-white"
              placeholder="examples/rsi_meanreversion.py"
              list="known-paths"
            />
            <datalist id="known-paths">
              {KNOWN_REFERENCE_PATHS.map((p) => <option key={p} value={p} />)}
            </datalist>
          </label>

          <label className="block">
            <span className="text-xs text-gray-400">Symbols (comma or space separated)</span>
            <input
              type="text" value={symbolsText} onChange={(e) => setSymbolsText(e.target.value)}
              className="mt-1 w-full rounded bg-gray-800 px-2 py-1 text-white"
              placeholder="AAPL MSFT SPY"
            />
          </label>

          <label className="block">
            <span className="text-xs text-gray-400">Params (JSON)</span>
            <textarea
              value={paramsText} onChange={(e) => setParamsText(e.target.value)}
              rows={6}
              className="mt-1 w-full rounded bg-gray-800 px-2 py-1 font-mono text-xs text-white"
            />
          </label>

          <label className="block">
            <span className="text-xs text-gray-400">Schedule (cron, or "event")</span>
            <input
              type="text" value={schedule} onChange={(e) => setSchedule(e.target.value)}
              className="mt-1 w-full rounded bg-gray-800 px-2 py-1 font-mono text-white"
            />
          </label>

          {error && (
            <div className="rounded border border-red-700 bg-red-900/40 p-2 text-sm text-red-200">
              {error}
            </div>
          )}
        </div>

        <div className="mt-4 flex justify-end gap-2">
          <button onClick={onClose}
                  className="rounded bg-gray-700 px-3 py-1.5 text-sm text-gray-200">
            Cancel
          </button>
          <button onClick={handleCreate} disabled={submitting}
                  className="rounded bg-blue-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-600 disabled:bg-gray-700">
            {submitting ? "Creating…" : "Register"}
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] List page renders, has working start/stop buttons, opens the New modal.

---

## §5.5 — Strategy Detail Page

Five tabs. Owns the strategy id from the URL, loads the strategy + tab-specific data lazily.

Create `apps/frontend/src/pages/Strategies/Detail.tsx`:

```tsx
import { useCallback, useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { strategiesApi } from "@/api/strategies";
import type { Strategy, StrategyRun } from "@/api/types";
import { ACTIVE_STRATEGY_STATUSES } from "@/api/types";
import { StatusBadge } from "@/components/strategies/StatusBadge";
import { OverviewTab } from "./tabs/OverviewTab";
import { SignalsTab } from "./tabs/SignalsTab";
import { OrdersTab } from "./tabs/OrdersTab";
import { BacktestsTab } from "./tabs/BacktestsTab";
import { ParamsTab } from "./tabs/ParamsTab";

type Tab = "overview" | "signals" | "orders" | "backtests" | "params";

const TAB_LABELS: Record<Tab, string> = {
  overview: "Overview",
  signals: "Signals",
  orders: "Orders",
  backtests: "Backtests",
  params: "Params",
};

export default function StrategyDetailPage() {
  const { id } = useParams<{ id: string }>();
  const sid = id ? parseInt(id, 10) : NaN;
  const [strategy, setStrategy] = useState<Strategy | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (Number.isNaN(sid)) return;
    try {
      const s = await strategiesApi.get(sid);
      setStrategy(s);
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, [sid]);

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load]);

  async function handleStart() {
    if (!strategy) return;
    if (!confirm(`Start "${strategy.name}" on paper?`)) return;
    try {
      await strategiesApi.start(strategy.id);
      await load();
    } catch (e) { alert(`Start failed: ${e}`); }
  }

  async function handleStop() {
    if (!strategy) return;
    if (!confirm(`Stop "${strategy.name}"?`)) return;
    try {
      await strategiesApi.stop(strategy.id);
      await load();
    } catch (e) { alert(`Stop failed: ${e}`); }
  }

  if (Number.isNaN(sid)) {
    return <div className="p-4 text-red-400">Invalid strategy id</div>;
  }

  if (error) {
    return (
      <div className="p-4 text-red-400">
        Could not load strategy: {error}{" "}
        <Link to="/strategies" className="ml-2 underline text-blue-400">Back</Link>
      </div>
    );
  }

  if (!strategy) {
    return <div className="p-4 text-gray-400">Loading…</div>;
  }

  return (
    <div className="space-y-4 p-4">
      <div className="flex items-start justify-between">
        <div>
          <Link to="/strategies" className="text-xs text-blue-400 hover:underline">
            ← All strategies
          </Link>
          <h1 className="mt-1 text-xl font-semibold text-white">
            {strategy.name} <span className="text-sm text-gray-400">v{strategy.version}</span>
          </h1>
          <div className="mt-1 flex items-center gap-3 text-sm text-gray-300">
            <StatusBadge status={strategy.status} />
            <span className="font-mono text-xs text-gray-500">{strategy.code_path}</span>
            <span>Symbols: {strategy.symbols.join(", ")}</span>
          </div>
          {strategy.status === "error" && strategy.error_text && (
            <div className="mt-2 rounded border border-rose-700 bg-rose-900/30 p-2 text-sm text-rose-200">
              <span className="font-semibold">Error:</span> {strategy.error_text}
            </div>
          )}
        </div>
        <div>
          {ACTIVE_STRATEGY_STATUSES.includes(strategy.status) ? (
            <button onClick={handleStop}
                    className="rounded bg-red-800 px-3 py-1.5 text-sm font-semibold text-white hover:bg-red-700">
              Stop
            </button>
          ) : (
            <button onClick={handleStart}
                    disabled={strategy.status === "error"}
                    className="rounded bg-emerald-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-emerald-600 disabled:bg-gray-700">
              Start (paper)
            </button>
          )}
        </div>
      </div>

      <div className="flex gap-1 border-b border-gray-800">
        {(Object.keys(TAB_LABELS) as Tab[]).map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`rounded-t px-3 py-1.5 text-sm ${
              tab === t ? "bg-gray-900 text-white" : "text-gray-400 hover:bg-gray-900/50"
            }`}>
            {TAB_LABELS[t]}
          </button>
        ))}
      </div>

      <div>
        {tab === "overview" && <OverviewTab strategy={strategy} />}
        {tab === "signals" && <SignalsTab strategyId={strategy.id} />}
        {tab === "orders" && <OrdersTab strategyId={strategy.id} />}
        {tab === "backtests" && <BacktestsTab strategy={strategy} />}
        {tab === "params" && <ParamsTab strategy={strategy} onSaved={load} />}
      </div>
    </div>
  );
}
```

### 5.5.1 — Overview tab

Create `apps/frontend/src/pages/Strategies/tabs/OverviewTab.tsx`:

```tsx
import { useEffect, useState } from "react";
import { strategiesApi } from "@/api/strategies";
import { signalsApi } from "@/api/signals";
import { ordersApi } from "@/api/orders";
import type { Strategy, StrategyRun, Signal, Order, BacktestSummary } from "@/api/types";
import { formatPct, formatNumber, formatCurrency } from "@/components/strategies/formatters";

interface Props {
  strategy: Strategy;
}

export function OverviewTab({ strategy }: Props) {
  const [runs, setRuns] = useState<StrategyRun[]>([]);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [latestBacktest, setLatestBacktest] = useState<BacktestSummary | null>(null);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const [r, s, o, b] = await Promise.all([
          strategiesApi.listRuns(strategy.id, 5),
          strategiesApi.listSignals(strategy.id, 10),
          ordersApi.list({ limit: 10 }),     // filtered client-side by source_id
          strategiesApi.listBacktests(strategy.id, 1),
        ]);
        if (!mounted) return;
        setRuns(r.items);
        setSignals(s.items);
        setOrders(o.items.filter(
          (ord) => ord.source_type === "strategy" && ord.source_id === String(strategy.id),
        ));
        setLatestBacktest(b.items[0] ?? null);
      } catch (e) {
        // silent — overview is informational only
      }
    })();
    return () => { mounted = false; };
  }, [strategy.id]);

  const latestRun = runs[0] ?? null;

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <Card title="Latest run">
        {latestRun ? (
          <dl className="space-y-1 text-sm text-gray-300">
            <Row label="Status">{latestRun.status}</Row>
            <Row label="Started">{new Date(latestRun.started_at).toLocaleString()}</Row>
            <Row label="Ended">{latestRun.ended_at ? new Date(latestRun.ended_at).toLocaleString() : "still running"}</Row>
            {latestRun.error_text && (
              <Row label="Error"><span className="text-rose-400">{latestRun.error_text}</span></Row>
            )}
          </dl>
        ) : <Empty>No runs yet</Empty>}
      </Card>

      <Card title="Latest backtest">
        {latestBacktest ? (
          <dl className="space-y-1 text-sm text-gray-300">
            <Row label="Label">{latestBacktest.label}</Row>
            <Row label="Range">
              {new Date(latestBacktest.range_start).toLocaleDateString()} →{" "}
              {new Date(latestBacktest.range_end).toLocaleDateString()}
            </Row>
            <Row label="Trades">{latestBacktest.metrics.trade_count}</Row>
            <Row label="Total return">{formatPct(latestBacktest.metrics.total_return)}</Row>
            <Row label="Sharpe">{formatNumber(latestBacktest.metrics.sharpe_ratio)}</Row>
            <Row label="Max DD">{formatPct(latestBacktest.metrics.max_drawdown)}</Row>
            <Row label="Win rate">{formatPct(latestBacktest.metrics.win_rate)}</Row>
          </dl>
        ) : <Empty>No backtests yet — run one from the Backtests tab</Empty>}
      </Card>

      <Card title={`Recent signals (${signals.length})`}>
        {signals.length === 0 ? <Empty>No signals</Empty> : (
          <ul className="space-y-1 text-sm">
            {signals.slice(0, 8).map((s) => (
              <li key={s.id} className="flex justify-between border-b border-gray-800 py-1">
                <span>
                  <span className="font-semibold">{s.symbol}</span>{" "}
                  <span className={
                    s.type === "entry" ? "text-emerald-400" :
                    s.type === "exit" ? "text-rose-400" : "text-gray-400"
                  }>
                    {s.type}
                  </span>
                </span>
                <span className="text-xs text-gray-500">
                  {new Date(s.received_at).toLocaleTimeString()}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title={`Recent orders (${orders.length})`}>
        {orders.length === 0 ? <Empty>No strategy-attributed orders</Empty> : (
          <ul className="space-y-1 text-sm">
            {orders.slice(0, 8).map((o) => (
              <li key={o.id} className="flex justify-between border-b border-gray-800 py-1">
                <span>
                  <span className={o.side === "buy" ? "text-emerald-400" : "text-rose-400"}>
                    {o.side.toUpperCase()}
                  </span>{" "}
                  <span className="font-semibold">{o.symbol}</span> ×{o.qty}
                </span>
                <span className="text-xs text-gray-500">{o.status}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
      <div className="mb-2 text-sm font-semibold text-gray-300">{title}</div>
      {children}
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between">
      <dt className="text-gray-500">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <div className="text-sm text-gray-500">{children}</div>;
}
```

### 5.5.2 — Signals tab

Create `apps/frontend/src/pages/Strategies/tabs/SignalsTab.tsx`:

```tsx
import { useCallback, useEffect, useState } from "react";
import { strategiesApi } from "@/api/strategies";
import type { Signal, SignalTypeT } from "@/api/types";
import { useWorkbenchSocket } from "@/hooks/useWorkbenchSocket";

interface Props {
  strategyId: number;
}

const TYPES: SignalTypeT[] = ["entry", "exit", "flat", "info", "agent_action", "pine_alert"];

export function SignalsTab({ strategyId }: Props) {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [filter, setFilter] = useState<SignalTypeT | "all">("all");
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await strategiesApi.listSignals(strategyId, 200);
      setSignals(resp.items);
    } finally {
      setLoading(false);
    }
  }, [strategyId]);

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load]);

  useWorkbenchSocket(["signals"], (msg) => {
    if (msg.payload.strategy_id === strategyId) {
      // Re-fetch on any new signal for this strategy
      load();
    }
  });

  const filtered = filter === "all" ? signals : signals.filter((s) => s.type === filter);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <span className="text-sm text-gray-400">Filter:</span>
        <button onClick={() => setFilter("all")}
          className={`rounded px-2 py-1 text-xs ${filter === "all" ? "bg-blue-700 text-white" : "bg-gray-800 text-gray-300"}`}>
          All
        </button>
        {TYPES.map((t) => (
          <button key={t} onClick={() => setFilter(t)}
            className={`rounded px-2 py-1 text-xs ${filter === t ? "bg-blue-700 text-white" : "bg-gray-800 text-gray-300"}`}>
            {t}
          </button>
        ))}
        <button onClick={load} className="ml-auto rounded bg-gray-700 px-2 py-1 text-xs text-gray-200">
          {loading ? "…" : "Refresh"}
        </button>
      </div>

      <div className="rounded border border-gray-800">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-800 text-gray-300">
            <tr>
              <th className="px-3 py-2">Time</th>
              <th className="px-3 py-2">Symbol</th>
              <th className="px-3 py-2">Type</th>
              <th className="px-3 py-2">Reason</th>
              <th className="px-3 py-2">Payload</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr><td colSpan={5} className="px-3 py-4 text-center text-gray-500">No signals</td></tr>
            )}
            {filtered.map((s) => (
              <tr key={s.id} className="border-t border-gray-800">
                <td className="px-3 py-2 text-xs text-gray-400">
                  {new Date(s.received_at).toLocaleString()}
                </td>
                <td className="px-3 py-2 font-semibold">{s.symbol}</td>
                <td className="px-3 py-2">
                  <span className={
                    s.type === "entry" ? "text-emerald-400" :
                    s.type === "exit" ? "text-rose-400" :
                    s.type === "info" ? "text-gray-400" : "text-blue-400"
                  }>
                    {s.type}
                  </span>
                </td>
                <td className="px-3 py-2 text-gray-300">
                  {(s.payload as { reason?: string })?.reason ?? "—"}
                </td>
                <td className="px-3 py-2 font-mono text-xs text-gray-500">
                  {JSON.stringify(s.payload).slice(0, 80)}
                  {JSON.stringify(s.payload).length > 80 ? "…" : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

### 5.5.3 — Orders tab

Create `apps/frontend/src/pages/Strategies/tabs/OrdersTab.tsx`:

```tsx
import { useCallback, useEffect, useState } from "react";
import { ordersApi } from "@/api/orders";
import type { Order } from "@/api/types";

interface Props {
  strategyId: number;
}

export function OrdersTab({ strategyId }: Props) {
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // No backend filter by source_id; pull a window and filter client-side.
      // P4 polish: add a source_id query param.
      const resp = await ordersApi.list({ limit: 500 });
      setOrders(resp.items.filter(
        (o) => o.source_type === "strategy" && o.source_id === String(strategyId),
      ));
    } finally {
      setLoading(false);
    }
  }, [strategyId]);

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load]);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm text-gray-400">
          Orders attributed to this strategy
        </span>
        <button onClick={load} className="rounded bg-gray-700 px-2 py-1 text-xs text-gray-200">
          {loading ? "…" : "Refresh"}
        </button>
      </div>

      <div className="rounded border border-gray-800">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-800 text-gray-300">
            <tr>
              <th className="px-3 py-2">Time</th>
              <th className="px-3 py-2">Symbol</th>
              <th className="px-3 py-2">Side</th>
              <th className="px-3 py-2 text-right">Qty</th>
              <th className="px-3 py-2">Type</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Reason</th>
            </tr>
          </thead>
          <tbody>
            {orders.length === 0 && (
              <tr><td colSpan={7} className="px-3 py-4 text-center text-gray-500">No strategy orders</td></tr>
            )}
            {orders.map((o) => (
              <tr key={o.id} className="border-t border-gray-800">
                <td className="px-3 py-2 text-xs text-gray-400">{new Date(o.created_at).toLocaleString()}</td>
                <td className="px-3 py-2 font-semibold">{o.symbol}</td>
                <td className={`px-3 py-2 ${o.side === "buy" ? "text-emerald-400" : "text-rose-400"}`}>
                  {o.side.toUpperCase()}
                </td>
                <td className="px-3 py-2 text-right">{o.qty}</td>
                <td className="px-3 py-2">{o.type}</td>
                <td className="px-3 py-2">{o.status}</td>
                <td className="px-3 py-2 text-xs text-gray-400">{o.rejection_reason ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

### 5.5.4 — Backtests tab

Create `apps/frontend/src/pages/Strategies/tabs/BacktestsTab.tsx`:

```tsx
import { useCallback, useEffect, useState } from "react";
import { strategiesApi } from "@/api/strategies";
import type { Strategy, BacktestSummary, BacktestResult } from "@/api/types";
import { formatPct, formatNumber } from "@/components/strategies/formatters";
import { BacktestRunModal } from "../BacktestRunModal";
import { BacktestResultsView } from "../BacktestResultsView";

interface Props {
  strategy: Strategy;
}

export function BacktestsTab({ strategy }: Props) {
  const [summaries, setSummaries] = useState<BacktestSummary[]>([]);
  const [selected, setSelected] = useState<BacktestResult | null>(null);
  const [showRunModal, setShowRunModal] = useState(false);

  const load = useCallback(async () => {
    try {
      const resp = await strategiesApi.listBacktests(strategy.id, 50);
      setSummaries(resp.items);
    } catch (e) {
      // ignore
    }
  }, [strategy.id]);

  useEffect(() => { load(); }, [load]);

  async function openResult(id: number) {
    try {
      const r = await strategiesApi.getBacktest(strategy.id, id);
      setSelected(r);
    } catch (e) {
      alert(`Could not load backtest: ${e}`);
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-300">Backtests</h3>
        <button onClick={() => setShowRunModal(true)}
          className="rounded bg-blue-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-600">
          Run backtest
        </button>
      </div>

      <div className="rounded border border-gray-800">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-800 text-gray-300">
            <tr>
              <th className="px-3 py-2">Created</th>
              <th className="px-3 py-2">Label</th>
              <th className="px-3 py-2">Range</th>
              <th className="px-3 py-2 text-right">Trades</th>
              <th className="px-3 py-2 text-right">Return</th>
              <th className="px-3 py-2 text-right">Sharpe</th>
              <th className="px-3 py-2 text-right">Max DD</th>
              <th className="px-3 py-2 text-right">Win rate</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {summaries.length === 0 && (
              <tr><td colSpan={9} className="px-3 py-4 text-center text-gray-500">
                No backtests yet
              </td></tr>
            )}
            {summaries.map((b) => (
              <tr key={b.id} className="border-t border-gray-800 hover:bg-gray-900 cursor-pointer"
                  onClick={() => openResult(b.id)}>
                <td className="px-3 py-2 text-xs text-gray-400">
                  {new Date(b.created_at).toLocaleString()}
                </td>
                <td className="px-3 py-2 font-semibold">{b.label}</td>
                <td className="px-3 py-2 text-xs text-gray-400">
                  {new Date(b.range_start).toLocaleDateString()} →{" "}
                  {new Date(b.range_end).toLocaleDateString()}
                </td>
                <td className="px-3 py-2 text-right">{b.metrics.trade_count}</td>
                <td className={`px-3 py-2 text-right ${b.metrics.total_return >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                  {formatPct(b.metrics.total_return)}
                </td>
                <td className="px-3 py-2 text-right">{formatNumber(b.metrics.sharpe_ratio)}</td>
                <td className="px-3 py-2 text-right text-rose-400">{formatPct(b.metrics.max_drawdown)}</td>
                <td className="px-3 py-2 text-right">{formatPct(b.metrics.win_rate)}</td>
                <td className="px-3 py-2 text-xs text-blue-400">View →</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showRunModal && (
        <BacktestRunModal
          strategy={strategy}
          onClose={() => setShowRunModal(false)}
          onCompleted={async (result) => {
            setShowRunModal(false);
            setSelected(result);
            await load();
          }}
        />
      )}

      {selected && (
        <BacktestResultsView result={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
```

### 5.5.5 — Params tab

Create `apps/frontend/src/pages/Strategies/tabs/ParamsTab.tsx`:

```tsx
import { useState } from "react";
import { strategiesApi } from "@/api/strategies";
import type { Strategy } from "@/api/types";
import { ApiError } from "@/api/client";

interface Props {
  strategy: Strategy;
  onSaved: () => void;
}

export function ParamsTab({ strategy, onSaved }: Props) {
  const editable = strategy.status === "idle";
  const [text, setText] = useState(JSON.stringify(strategy.params, null, 2));
  const [symbols, setSymbols] = useState(strategy.symbols.join(", "));
  const [schedule, setSchedule] = useState(strategy.schedule);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    setError(null);
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(text);
    } catch (e) {
      setError(`Params not valid JSON: ${e}`);
      return;
    }
    const symList = symbols.split(/[,\s]+/).map((s) => s.trim().toUpperCase()).filter(Boolean);
    setSaving(true);
    try {
      await strategiesApi.update(strategy.id, {
        params: parsed,
        symbols: symList,
        schedule,
      });
      onSaved();
    } catch (e) {
      if (e instanceof ApiError) setError(`${e.detail} (status ${e.status})`);
      else setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-3 max-w-2xl">
      {!editable && (
        <div className="rounded border border-amber-700 bg-amber-900/30 p-3 text-sm text-amber-100">
          Strategy is <span className="font-semibold">{strategy.status}</span> — stop it before editing.
        </div>
      )}

      <label className="block">
        <span className="text-xs text-gray-400">Symbols (comma or space separated)</span>
        <input
          type="text" value={symbols} onChange={(e) => setSymbols(e.target.value)}
          disabled={!editable}
          className="mt-1 w-full rounded bg-gray-800 px-2 py-1 text-white disabled:opacity-50"
        />
      </label>

      <label className="block">
        <span className="text-xs text-gray-400">Schedule (cron or "event")</span>
        <input
          type="text" value={schedule} onChange={(e) => setSchedule(e.target.value)}
          disabled={!editable}
          className="mt-1 w-full rounded bg-gray-800 px-2 py-1 font-mono text-white disabled:opacity-50"
        />
      </label>

      <label className="block">
        <span className="text-xs text-gray-400">Params (JSON)</span>
        <textarea
          value={text} onChange={(e) => setText(e.target.value)}
          disabled={!editable}
          rows={16}
          className="mt-1 w-full rounded bg-gray-800 px-2 py-1 font-mono text-xs text-white disabled:opacity-50"
        />
      </label>

      {error && (
        <div className="rounded border border-red-700 bg-red-900/40 p-2 text-sm text-red-200">
          {error}
        </div>
      )}

      <div>
        <button onClick={handleSave} disabled={!editable || saving}
          className="rounded bg-blue-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-600 disabled:bg-gray-700">
          {saving ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  );
}
```

- [ ] Detail page renders with all five tabs.

---

## §5.6 — Backtest Run Modal + Results View

The remaining two pieces: the modal that triggers a backtest and the results view that renders metrics + recharts equity curve + trade list.

Create `apps/frontend/src/pages/Strategies/BacktestRunModal.tsx`:

```tsx
import { useState } from "react";
import { strategiesApi } from "@/api/strategies";
import { ApiError } from "@/api/client";
import type { Strategy, BacktestResult } from "@/api/types";

interface Props {
  strategy: Strategy;
  onClose: () => void;
  onCompleted: (result: BacktestResult) => void;
}

export function BacktestRunModal({ strategy, onClose, onCompleted }: Props) {
  const now = new Date();
  const tenDaysAgo = new Date(now.getTime() - 10 * 86400_000);

  const [label, setLabel] = useState("default");
  const [start, setStart] = useState(tenDaysAgo.toISOString().slice(0, 10));
  const [end, setEnd] = useState(now.toISOString().slice(0, 10));
  const [initialEquity, setInitialEquity] = useState("100000");
  const [slippageBps, setSlippageBps] = useState("5");
  const [timeframe, setTimeframe] = useState("1Min");
  const [paramsText, setParamsText] = useState(JSON.stringify(strategy.params, null, 2));
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRun() {
    setError(null);
    let paramsParsed: Record<string, unknown>;
    try {
      paramsParsed = paramsText.trim() ? JSON.parse(paramsText) : {};
    } catch (e) {
      setError(`Params not valid JSON: ${e}`);
      return;
    }
    setRunning(true);
    try {
      const result = await strategiesApi.runBacktest(strategy.id, {
        start: new Date(start).toISOString(),
        end: new Date(end).toISOString(),
        label: label.trim() || "default",
        initial_equity: initialEquity,
        slippage_bps: Number(slippageBps),
        timeframe,
        params: paramsParsed,
      });
      onCompleted(result);
    } catch (e) {
      if (e instanceof ApiError) setError(`${e.detail} (status ${e.status})`);
      else setError(String(e));
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/70">
      <div className="w-[32rem] max-h-[90vh] overflow-y-auto rounded-lg border border-gray-700 bg-gray-950 p-5">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">Run backtest</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white">✕</button>
        </div>

        <div className="space-y-3 text-sm text-gray-300">
          <label className="block">
            <span className="text-xs text-gray-400">Label</span>
            <input type="text" value={label} onChange={(e) => setLabel(e.target.value)}
              className="mt-1 w-full rounded bg-gray-800 px-2 py-1 text-white" />
          </label>

          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              <span className="text-xs text-gray-400">Start</span>
              <input type="date" value={start} onChange={(e) => setStart(e.target.value)}
                className="mt-1 w-full rounded bg-gray-800 px-2 py-1 text-white" />
            </label>
            <label className="block">
              <span className="text-xs text-gray-400">End</span>
              <input type="date" value={end} onChange={(e) => setEnd(e.target.value)}
                className="mt-1 w-full rounded bg-gray-800 px-2 py-1 text-white" />
            </label>
          </div>

          <div className="grid grid-cols-3 gap-2">
            <label className="block">
              <span className="text-xs text-gray-400">Initial equity</span>
              <input type="text" value={initialEquity} onChange={(e) => setInitialEquity(e.target.value)}
                className="mt-1 w-full rounded bg-gray-800 px-2 py-1 text-white" />
            </label>
            <label className="block">
              <span className="text-xs text-gray-400">Slippage (bps)</span>
              <input type="number" min="0" value={slippageBps} onChange={(e) => setSlippageBps(e.target.value)}
                className="mt-1 w-full rounded bg-gray-800 px-2 py-1 text-white" />
            </label>
            <label className="block">
              <span className="text-xs text-gray-400">Timeframe</span>
              <select value={timeframe} onChange={(e) => setTimeframe(e.target.value)}
                className="mt-1 w-full rounded bg-gray-800 px-2 py-1 text-white">
                <option value="1Min">1Min</option>
                <option value="5Min">5Min</option>
                <option value="15Min">15Min</option>
                <option value="1Hour">1Hour</option>
                <option value="1Day">1Day</option>
              </select>
            </label>
          </div>

          <label className="block">
            <span className="text-xs text-gray-400">Params override (JSON)</span>
            <textarea value={paramsText} onChange={(e) => setParamsText(e.target.value)}
              rows={8} className="mt-1 w-full rounded bg-gray-800 px-2 py-1 font-mono text-xs text-white" />
          </label>

          {error && (
            <div className="rounded border border-red-700 bg-red-900/40 p-2 text-sm text-red-200">
              {error}
            </div>
          )}

          {running && (
            <div className="rounded border border-blue-700 bg-blue-900/30 p-2 text-sm text-blue-200">
              Backtest running… typically 2–10 seconds for a short range. The request blocks
              until done; please don't close this window.
            </div>
          )}
        </div>

        <div className="mt-4 flex justify-end gap-2">
          <button onClick={onClose} disabled={running}
            className="rounded bg-gray-700 px-3 py-1.5 text-sm text-gray-200">Cancel</button>
          <button onClick={handleRun} disabled={running}
            className="rounded bg-blue-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-600 disabled:bg-gray-700">
            {running ? "Running…" : "Run"}
          </button>
        </div>
      </div>
    </div>
  );
}
```

Create `apps/frontend/src/pages/Strategies/BacktestResultsView.tsx`:

```tsx
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from "recharts";
import type { BacktestResult } from "@/api/types";
import { formatPct, formatNumber, formatCurrency, formatDuration } from "@/components/strategies/formatters";

interface Props {
  result: BacktestResult;
  onClose: () => void;
}

export function BacktestResultsView({ result, onClose }: Props) {
  const chartData = result.equity_curve.map((p) => ({
    t: new Date(p.t).getTime(),
    equity: p.equity,
  }));
  const startingEquity = result.metrics.starting_equity;

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/80">
      <div className="w-[60rem] max-h-[92vh] overflow-y-auto rounded-lg border border-gray-700 bg-gray-950 p-5">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-white">
              Backtest #{result.id}: <span className="text-blue-300">{result.label}</span>
            </h2>
            <div className="text-xs text-gray-400">
              {new Date(result.range_start).toLocaleDateString()} →{" "}
              {new Date(result.range_end).toLocaleDateString()}{" "}
              · created {new Date(result.created_at).toLocaleString()}
            </div>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-white">✕</button>
        </div>

        {/* Metrics */}
        <div className="grid grid-cols-4 gap-2 mb-4">
          <MetricCard label="Total return" value={formatPct(result.metrics.total_return)}
                      positive={result.metrics.total_return >= 0} />
          <MetricCard label="Annualized" value={formatPct(result.metrics.annualized_return)}
                      positive={result.metrics.annualized_return >= 0} />
          <MetricCard label="Sharpe" value={formatNumber(result.metrics.sharpe_ratio)} />
          <MetricCard label="Max DD" value={formatPct(result.metrics.max_drawdown)} negative />
          <MetricCard label="Win rate" value={formatPct(result.metrics.win_rate)} />
          <MetricCard label="Profit factor" value={formatNumber(result.metrics.profit_factor)} />
          <MetricCard label="Trades" value={String(result.metrics.trade_count)} />
          <MetricCard label="Avg duration" value={formatDuration(result.metrics.avg_trade_duration_seconds)} />
        </div>

        {/* Equity curve */}
        <div className="mb-4 rounded border border-gray-800 bg-gray-900 p-3">
          <div className="mb-1 text-sm font-semibold text-gray-300">Equity curve</div>
          {chartData.length === 0 ? (
            <div className="py-8 text-center text-sm text-gray-500">No equity points</div>
          ) : (
            <div style={{ width: "100%", height: 240 }}>
              <ResponsiveContainer>
                <LineChart data={chartData}>
                  <XAxis dataKey="t" type="number" scale="time"
                    domain={["dataMin", "dataMax"]}
                    tickFormatter={(v) => new Date(v).toLocaleDateString()}
                    tick={{ fill: "#9ca3af", fontSize: 11 }}
                  />
                  <YAxis domain={["auto", "auto"]} tick={{ fill: "#9ca3af", fontSize: 11 }}
                    tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} />
                  <Tooltip
                    contentStyle={{ background: "#111827", border: "1px solid #374151" }}
                    labelFormatter={(v) => new Date(v as number).toLocaleString()}
                    formatter={(v) => formatCurrency(v as number)}
                  />
                  <ReferenceLine y={startingEquity} stroke="#6b7280" strokeDasharray="3 3" />
                  <Line type="monotone" dataKey="equity" stroke="#3b82f6" dot={false} strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

        {/* Trades */}
        <div className="rounded border border-gray-800">
          <div className="bg-gray-800 px-3 py-2 text-sm font-semibold text-gray-300">
            Trades ({result.trades.length})
          </div>
          <div className="max-h-72 overflow-y-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-gray-900 text-gray-300">
                <tr>
                  <th className="px-3 py-2">Symbol</th>
                  <th className="px-3 py-2">Side</th>
                  <th className="px-3 py-2">Entry</th>
                  <th className="px-3 py-2">Exit</th>
                  <th className="px-3 py-2 text-right">Qty</th>
                  <th className="px-3 py-2 text-right">PnL</th>
                  <th className="px-3 py-2">Duration</th>
                  <th className="px-3 py-2">Exit reason</th>
                </tr>
              </thead>
              <tbody>
                {result.trades.length === 0 && (
                  <tr><td colSpan={8} className="px-3 py-4 text-center text-gray-500">No closed trades</td></tr>
                )}
                {result.trades.map((t, i) => (
                  <tr key={i} className="border-t border-gray-800">
                    <td className="px-3 py-2 font-semibold">{t.symbol}</td>
                    <td className={`px-3 py-2 ${t.side === "long" ? "text-emerald-400" : "text-rose-400"}`}>
                      {t.side}
                    </td>
                    <td className="px-3 py-2 text-xs text-gray-400">
                      {new Date(t.entry_ts).toLocaleString()}<br/>
                      <span className="font-mono">{t.entry_price.toFixed(2)}</span>
                    </td>
                    <td className="px-3 py-2 text-xs text-gray-400">
                      {t.exit_ts ? new Date(t.exit_ts).toLocaleString() : "—"}<br/>
                      {t.exit_price !== null && (
                        <span className="font-mono">{t.exit_price.toFixed(2)}</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right">{t.qty.toFixed(0)}</td>
                    <td className={`px-3 py-2 text-right ${(t.pnl ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {t.pnl !== null ? `$${t.pnl.toFixed(2)}` : "—"}
                    </td>
                    <td className="px-3 py-2 text-xs text-gray-400">{formatDuration(t.duration_seconds)}</td>
                    <td className="px-3 py-2 text-xs text-gray-400">{t.exit_reason ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="mt-4 flex justify-end">
          <button onClick={onClose}
            className="rounded bg-gray-700 px-3 py-1.5 text-sm text-gray-200">Close</button>
        </div>
      </div>
    </div>
  );
}

function MetricCard({ label, value, positive, negative }: {
  label: string; value: string; positive?: boolean; negative?: boolean;
}) {
  let cls = "text-white";
  if (positive) cls = "text-emerald-300";
  if (negative) cls = "text-rose-300";
  return (
    <div className="rounded border border-gray-800 bg-gray-900 p-2">
      <div className="text-[10px] uppercase text-gray-500">{label}</div>
      <div className={`text-lg font-semibold ${cls}`}>{value}</div>
    </div>
  );
}
```

- [ ] Backtest run modal + results view created.

---

## §5.7 — Routing

Edit `apps/frontend/src/App.tsx` (or wherever the route table lives). Add two new routes alongside the existing P1 routes:

```tsx
import StrategiesListPage from "@/pages/Strategies";
import StrategyDetailPage from "@/pages/Strategies/Detail";

// ... in the <Routes> block ...
<Route path="/strategies" element={<StrategiesListPage />} />
<Route path="/strategies/:id" element={<StrategyDetailPage />} />
```

Edit the sidebar nav (in the page shell from P1 Session 6 / 7). Add a Strategies link next to Charts:

```tsx
<NavLink to="/strategies" className={...}>Strategies</NavLink>
```

> The Strategies placeholder page from P1 (if one exists) should be replaced by the import above. If the P1 sidebar already had a Strategies entry pointing at a placeholder, this just swaps the implementation.

- [ ] Two routes registered.
- [ ] Sidebar link added.

---

## §5.8 — Vitest Tests

Three high-value tests. Mock the API client, assert that user actions hit the right endpoints with the right bodies.

Create `apps/frontend/src/pages/Strategies/__tests__/StrategiesListPage.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import StrategiesListPage from "../index";
import { strategiesApi } from "@/api/strategies";
import { signalsApi } from "@/api/signals";

vi.mock("@/api/strategies");
vi.mock("@/api/signals");
vi.mock("@/hooks/useWorkbenchSocket", () => ({
  useWorkbenchSocket: () => {},
}));

const mockedStrategiesApi = vi.mocked(strategiesApi);
const mockedSignalsApi = vi.mocked(signalsApi);

const _strategy = (over: Partial<any> = {}) => ({
  id: 1, name: "rsi-test", version: "0.1.0",
  type: "python", status: "idle",
  code_path: "examples/rsi_meanreversion.py",
  params: {}, symbols: ["AAPL"], schedule: "*/1 * * * *",
  risk_limits_id: null, error_text: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  ...over,
});

beforeEach(() => {
  vi.resetAllMocks();
  vi.spyOn(window, "confirm").mockReturnValue(true);
  mockedSignalsApi.list.mockResolvedValue({ items: [], count: 0 });
});

describe("StrategiesListPage", () => {
  it("renders strategies with status badges", async () => {
    mockedStrategiesApi.list.mockResolvedValue({
      items: [_strategy({ id: 1, name: "rsi-1" }), _strategy({ id: 2, name: "rsi-2", status: "paper" })],
      count: 2,
    });
    render(<MemoryRouter><StrategiesListPage /></MemoryRouter>);
    expect(await screen.findByText("rsi-1")).toBeInTheDocument();
    expect(await screen.findByText("rsi-2")).toBeInTheDocument();
    expect(await screen.findByText("PAPER")).toBeInTheDocument();
    expect(await screen.findAllByText("IDLE")).toHaveLength(1);
  });

  it("Start button calls strategiesApi.start", async () => {
    mockedStrategiesApi.list.mockResolvedValue({
      items: [_strategy({ id: 1, name: "rsi-1", status: "idle" })],
      count: 1,
    });
    mockedStrategiesApi.start.mockResolvedValue({
      strategy_id: 1, action: "start", new_status: "paper", run_id: 99,
    });
    render(<MemoryRouter><StrategiesListPage /></MemoryRouter>);
    await screen.findByText("rsi-1");
    fireEvent.click(screen.getByText("Start"));
    await waitFor(() => expect(mockedStrategiesApi.start).toHaveBeenCalledWith(1));
  });

  it("Stop button calls strategiesApi.stop on PAPER strategy", async () => {
    mockedStrategiesApi.list.mockResolvedValue({
      items: [_strategy({ id: 1, name: "rsi-running", status: "paper" })],
      count: 1,
    });
    mockedStrategiesApi.stop.mockResolvedValue({
      strategy_id: 1, action: "stop", new_status: "idle", run_id: null,
    });
    render(<MemoryRouter><StrategiesListPage /></MemoryRouter>);
    await screen.findByText("rsi-running");
    fireEvent.click(screen.getByText("Stop"));
    await waitFor(() => expect(mockedStrategiesApi.stop).toHaveBeenCalledWith(1));
  });

  it("ERROR status disables Start button with explanatory label", async () => {
    mockedStrategiesApi.list.mockResolvedValue({
      items: [_strategy({ id: 1, name: "broken", status: "error", error_text: "loader failed" })],
      count: 1,
    });
    render(<MemoryRouter><StrategiesListPage /></MemoryRouter>);
    const btn = await screen.findByText("Errored") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });
});
```

Create `apps/frontend/src/pages/Strategies/__tests__/StrategyDetailPage.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import StrategyDetailPage from "../Detail";
import { strategiesApi } from "@/api/strategies";
import { signalsApi } from "@/api/signals";
import { ordersApi } from "@/api/orders";

vi.mock("@/api/strategies");
vi.mock("@/api/signals");
vi.mock("@/api/orders");
vi.mock("@/hooks/useWorkbenchSocket", () => ({
  useWorkbenchSocket: () => {},
}));

const mockedStrategiesApi = vi.mocked(strategiesApi);
const mockedSignalsApi = vi.mocked(signalsApi);
const mockedOrdersApi = vi.mocked(ordersApi);

beforeEach(() => {
  vi.resetAllMocks();
  mockedStrategiesApi.get.mockResolvedValue({
    id: 1, name: "rsi-test", version: "0.1.0",
    type: "python", status: "idle",
    code_path: "examples/rsi_meanreversion.py",
    params: { entry_threshold: 30 },
    symbols: ["AAPL"], schedule: "*/1 * * * *",
    risk_limits_id: null, error_text: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  });
  mockedStrategiesApi.listRuns.mockResolvedValue({ items: [], count: 0 });
  mockedStrategiesApi.listSignals.mockResolvedValue({ items: [], count: 0 });
  mockedStrategiesApi.listBacktests.mockResolvedValue({ items: [], count: 0 });
  mockedSignalsApi.list.mockResolvedValue({ items: [], count: 0 });
  mockedOrdersApi.list.mockResolvedValue({ items: [], count: 0 });
});

function renderWithRoute() {
  return render(
    <MemoryRouter initialEntries={["/strategies/1"]}>
      <Routes>
        <Route path="/strategies/:id" element={<StrategyDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("StrategyDetailPage", () => {
  it("renders header with name and status", async () => {
    renderWithRoute();
    expect(await screen.findByText("rsi-test")).toBeInTheDocument();
    expect(await screen.findByText("IDLE")).toBeInTheDocument();
  });

  it("switches between tabs", async () => {
    renderWithRoute();
    await screen.findByText("rsi-test");
    // Default: Overview tab is mounted
    expect(await screen.findByText(/Latest run/i)).toBeInTheDocument();
    // Click Signals tab
    fireEvent.click(screen.getByText("Signals"));
    expect(await screen.findByText(/Filter:/i)).toBeInTheDocument();
    // Click Backtests tab
    fireEvent.click(screen.getByText("Backtests"));
    expect(await screen.findByText(/Run backtest/)).toBeInTheDocument();
  });

  it("Params tab is read-only when status is paper", async () => {
    mockedStrategiesApi.get.mockResolvedValue({
      id: 1, name: "rsi-test", version: "0.1.0",
      type: "python", status: "paper",
      code_path: "examples/rsi_meanreversion.py",
      params: { x: 1 }, symbols: ["AAPL"], schedule: "*/1 * * * *",
      risk_limits_id: null, error_text: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    renderWithRoute();
    await screen.findByText("rsi-test");
    fireEvent.click(screen.getByText("Params"));
    const banner = await screen.findByText(/stop it before editing/i);
    expect(banner).toBeInTheDocument();
  });
});
```

Create `apps/frontend/src/pages/Strategies/__tests__/BacktestResultsView.test.tsx`:

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { BacktestResultsView } from "../BacktestResultsView";

const result = {
  id: 1, strategy_id: 1, label: "test",
  params: {},
  metrics: {
    total_return: 0.0523,
    annualized_return: 0.21,
    sharpe_ratio: 1.42,
    max_drawdown: -0.087,
    win_rate: 0.6,
    profit_factor: 1.85,
    trade_count: 25,
    avg_win: 120.5,
    avg_loss: -65.3,
    avg_trade_duration_seconds: 1820,
    starting_equity: 100000,
    ending_equity: 105230,
  },
  equity_curve: [
    { t: "2025-11-03T14:30:00Z", equity: 100000 },
    { t: "2025-11-04T16:00:00Z", equity: 102000 },
    { t: "2025-11-05T16:00:00Z", equity: 105230 },
  ],
  trades: [
    {
      symbol: "AAPL", side: "long" as const,
      entry_ts: "2025-11-03T15:00:00Z", entry_price: 190.0,
      exit_ts: "2025-11-03T15:30:00Z", exit_price: 191.5,
      qty: 10, pnl: 15.0, duration_seconds: 1800, exit_reason: "rsi_exit",
    },
  ],
  range_start: "2025-11-03T00:00:00Z",
  range_end: "2025-11-06T00:00:00Z",
  created_at: "2025-11-06T00:00:00Z",
};

describe("BacktestResultsView", () => {
  it("renders metric values formatted correctly", () => {
    render(<BacktestResultsView result={result} onClose={() => {}} />);
    expect(screen.getByText("5.23%")).toBeInTheDocument();    // total return
    expect(screen.getByText("21.00%")).toBeInTheDocument();   // annualized
    expect(screen.getByText("1.42")).toBeInTheDocument();     // sharpe
    expect(screen.getByText("-8.70%")).toBeInTheDocument();   // max dd
    expect(screen.getByText("60.00%")).toBeInTheDocument();   // win rate
    expect(screen.getByText("25")).toBeInTheDocument();       // trade count
  });

  it("renders trade list with PnL color coding", () => {
    render(<BacktestResultsView result={result} onClose={() => {}} />);
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("rsi_exit")).toBeInTheDocument();
    expect(screen.getByText("$15.00")).toBeInTheDocument();
  });
});
```

Run tests:

```bash
cd apps/frontend
pnpm test
cd ../..
```

- [ ] All three Vitest test files pass.

---

## §5.9 — Manual Smoke

Walk through the UI end-to-end against the running backend.

```bash
./scripts/dev.sh &
sleep 30
```

In a browser at `http://localhost:5173`:

1. **Navigate to `/strategies`.** Page renders with empty table.
2. **Click "+ New strategy".** Modal opens with reference-strategy defaults.
3. **Click "Register".** Modal closes; the new strategy appears in the table with status IDLE.
4. **Click the strategy name.** Detail page opens at the Overview tab. Latest backtest card says "No backtests yet."
5. **Click the Backtests tab → "Run backtest" button.** Modal opens with sane defaults (last 10 days, 1Min, 5 bps slippage).
6. **Click "Run".** Modal shows the "Backtest running…" banner; ~2–10s later the results view opens with metrics, equity curve (recharts), and trade list.
7. **Close the results view.** The Backtests tab table now shows the run as a row.
8. **Click the Params tab.** Textarea shows the params JSON; can be edited and saved (status must be IDLE).
9. **Back to top of detail page → click "Start (paper)".** Status badge transitions IDLE → PAPER. (During market hours, signals begin to appear in the Signals tab; off-hours, just the start succeeds.)
10. **Open `/strategies` in another tab.** The list shows the same strategy as PAPER. If you stop it from this tab, the original tab should update on the next poll cycle (≤5s) or sooner via WS.
11. **Click "Stop".** Status transitions PAPER → IDLE.

```bash
docker compose down
```

- [ ] Steps 1–11 all green.
- [ ] Equity curve recharts widget renders.
- [ ] Two tabs open at once stay in sync within 5s.

---

## §5.10 — Commit and PR

```bash
git add apps/frontend/src/api/strategies.ts
git add apps/frontend/src/api/signals.ts
git add apps/frontend/src/api/types.ts
git add apps/frontend/src/hooks/useWorkbenchSocket.ts
git add apps/frontend/src/components/strategies/
git add apps/frontend/src/pages/Strategies/
git add apps/frontend/src/App.tsx       # routes + sidebar link

git commit -m "feat(frontend): strategies list + detail + backtest views

- Typed API client modules: strategies + signals
- useWorkbenchSocket hook with shared WS singleton + exponential reconnect
- StrategiesListPage: row per strategy with status badge, start/stop button,
  today's signal count. Polls 5s; WS for instant transitions.
- NewStrategyModal: register a python strategy via JSON params + symbols
- StrategyDetailPage with 5 tabs:
  - Overview (latest run, latest backtest, recent signals/orders)
  - Signals (live signal table, type filter)
  - Orders (strategy-attributed orders, client-side filtered)
  - Backtests (history + Run backtest button)
  - Params (JSON editor; locked when strategy is not IDLE)
- BacktestRunModal + BacktestResultsView with recharts equity curve and
  trade list with PnL color coding
- Vitest: list page actions, detail page tab switching, results view metrics"

git push -u origin feat/p2-strategies-frontend

gh pr create \
  --title "feat(frontend): strategies list + detail + backtest views" \
  --body "P2 Session 5 deliverable.

In scope:
- /strategies list + /strategies/:id detail (5 tabs)
- Backtest trigger + results view with recharts
- WS hook with shared singleton + exponential reconnect
- 3 Vitest test files

Out of scope (Session 6):
- Tests + smoke matrix + runbook docs + P2 exit gate"

gh pr checks
gh pr merge --merge --delete-branch
git checkout main && git pull
```

- [ ] PR merged.

---

## Verification Checklist (full session)

- [ ] §5.1 Three API client modules + types extended.
- [ ] §5.2 `useWorkbenchSocket` hook with shared singleton, topic subscription, exponential reconnect.
- [ ] §5.3 `StatusBadge` + formatters created.
- [ ] §5.4 Strategies list page + NewStrategyModal.
- [ ] §5.5 Strategy detail page with all five tabs.
- [ ] §5.6 BacktestRunModal + BacktestResultsView with recharts.
- [ ] §5.7 Routes + sidebar link.
- [ ] §5.8 Three Vitest tests pass.
- [ ] §5.9 Manual smoke walks all eleven steps cleanly.
- [ ] §5.10 PR merged through protected workflow.

---

## Sign-off

```bash
git tag -a p2-session5-complete -m "P2 Session 5 complete: frontend strategies pages"
git push origin p2-session5-complete
```

Update `todo.md`:
- Mark P2 Session 5 complete.
- Tee up **P2 Session 6 — Tests + smoke matrix + runbooks + P2 exit gate** (Checklist §8 + §9 + §10).

---

## Notes & Gotchas

1. **Polling AND WebSocket together.** Each page polls every 5s as a safety net and subscribes to WS for instant transitions. This isn't redundant — it's belt-and-suspenders: if the WS connection drops and the auto-reconnect hasn't kicked in yet, polling guarantees the UI eventually catches up. Don't "optimize" by removing polling.

2. **`useWorkbenchSocket` shares ONE connection across the whole app.** Multiple consumers add subscriptions to the singleton, not new sockets. This matters when the user opens the Strategies list page (subscribes to `strategies`, `signals`) and the strategy detail page (subscribes to `signals`) — there's only one WS frame stream, fanned out client-side.

3. **The `topics.join(",")` dependency in `useEffect`.** Pass `topics` as an array of strings; the effect re-subscribes only when the joined list changes. Passing a fresh array on every render WITHOUT the join would cause infinite re-subscription. If lint complains about exhaustive-deps, the inline disable is appropriate.

4. **Backtest endpoint is synchronous; the modal blocks.** Per Session 4 §4.5's design and Session 4's Gotcha #2: the request takes seconds to tens of seconds. The modal shows a "Backtest running…" banner and disables the Cancel button to prevent a closed-modal-during-request half-state. P4 polish could add async + WS-driven progress.

5. **Orders tab does client-side filtering by `source_id`.** The backend doesn't yet expose a `source_id` filter on `/api/v1/orders`; we pull the latest 500 and filter in the browser. Adequate for MVP, suboptimal at scale. The right fix is a backend query param in Session 4's pattern; deferred to P4 polish (noted in §5.5.3's comment).

6. **`useWorkbenchSocket` hook uses a stable handler ref.** A naïve `useEffect` that includes `handler` in deps would re-subscribe every render. The `handlerRef.current = handler` pattern keeps the singleton's handler stable while letting the latest closure see fresh state via the ref.

7. **`overflow-y-auto max-h-[92vh]`** on modals. Without it, on a 13" laptop screen the backtest results view (metric grid + chart + trade table) overflows and you can't reach the Close button. Always set a viewport-bounded max-height on full-page modals.

8. **`type="date"` in `BacktestRunModal` returns `YYYY-MM-DD`.** The modal converts to ISO via `new Date(start).toISOString()`. This assumes the user's locale interprets the date as midnight local; for users near UTC midnight, this may shift one day. Acceptable for MVP; sophisticated date pickers are P4.

9. **`@/...` aliases.** Vite + tsconfig path alias `@/*` → `src/*`. This should be set up from P0. If your test runs fail with module-not-found, check `vite.config.ts` has `resolve.alias` and `vitest.config.ts` matches.

10. **`vi.spyOn(window, "confirm")` in the list tests.** Tests that go through the start/stop confirm dialog need this mock. The default `vi.fn()` for `window.confirm` returns `undefined` which JavaScript treats as falsy — so confirm-gated handlers never fire. The explicit `mockReturnValue(true)` makes the tests deterministic.

11. **Don't conflate "strategy is registered" with "strategy is running."** A registered strategy in IDLE status is a DB row; the engine is not dispatching to it. Start transitions to PAPER. Stop transitions back to IDLE. The Strategies page makes this distinction visually with the status badge. If users ever confuse "registered" with "running," consider renaming Start to "Deploy to paper" in P4.

12. **The Strategies placeholder page from P0/P1 is replaced.** If your P0 sidebar had a `/strategies` link pointing at a "Coming in P2" stub, this session's routing overwrites it. If the link wasn't in the sidebar, §5.7 adds it.

13. **Don't start Session 6 in this PR.** Tests, smoke matrix, runbook docs, and the P2 exit gate are a focused closing block. Stop at the tag.

---

*End of P2 Session 5 v0.1.*
