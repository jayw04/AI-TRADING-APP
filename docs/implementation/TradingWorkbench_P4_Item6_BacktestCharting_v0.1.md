# P4 Item 6 — Backtest Charting Improvements

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-05-23 |
| Phase | **P4 — Polish & Extend**, Item §6 |
| Predecessor | *TradingWorkbench_P4_Item5_OrderSourceFilter_v0.1.md* (tag `p4-order-source-filter-complete`) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | Extend the P2 Session 5 `BacktestResultsView` with four charting upgrades: (1) drawdown sub-chart aligned with the equity curve; (2) trade markers (entry ▲ / exit ▼) on the equity curve with hover tooltip; (3) toggle the y-axis between absolute equity ($) and cumulative returns (%); (4) per-trade stats table (best / worst / avg / median / win-loss breakdown). **Frontend-only PR.** No backend changes — every datum needed is already in the persisted `BacktestResult` row. |
| Estimated wall time | 3 hours |
| Stopping point | `git tag p4-backtest-charting-complete` |
| Out of scope | Comparing multiple backtests side-by-side (P5+). Annotations (manual lines, regime markers). Exporting the chart as PNG. Trade-level drill-down (clicking a trade marker opens that trade's detail page). Streaming progress charts during a running backtest — Item §2 already added progress events, but a real-time equity curve during execution is a separate UX. |

---

## Session Goal

After this session:
- `BacktestResultsView` renders the equity curve as before AND a drawdown sub-chart below it. The two charts share their x-axis (time); zooming/panning later (out of scope) would zoom both together via recharts' synchronized `syncId`.
- Trade markers appear on the equity curve: a small green ▲ at each long entry, red ▼ at each exit. Hovering a marker shows the trade's symbol, side, entry/exit prices, qty, pnl, duration, exit reason.
- A toggle switch above the chart flips the y-axis between **Equity ($)** and **Returns (%)**. The chart re-renders without re-fetching.
- A new "Trade stats" section below the equity curve shows: best/worst/avg/median trade, total wins/losses, avg duration by win/loss, longest winning/losing streak.
- All four upgrades work on existing `BacktestResult` rows; no migration, no backend change.
- One new Vitest test covering the y-axis toggle; existing `BacktestResultsView.test.tsx` cases still pass.

What does NOT happen this session:
- No backend computation of additional metrics. Everything new (median trade, streaks, etc.) is computed client-side from `result.trades` and `result.equity_curve`. The P2 `BacktestMetrics` Pydantic shape is unchanged.
- No "compare two backtests" UI. The results view stays single-backtest.
- No PNG/PDF export. The browser's print dialog is the workaround; native export is P5+.
- No chart annotations or zoom. Recharts supports it (`Brush`); we don't add it because it shifts the layout and the current 60-rem modal is already at the edge of comfortable.

---

## Prerequisites Check

```bash
cd ~/code/AI-TRADING-APP
git status                                       # clean
git pull origin main
git describe --tags --abbrev=0                   # expect: p4-order-source-filter-complete

./scripts/dev.sh &
sleep 30

# A persisted backtest exists to smoke against
SID=$(curl -s "http://127.0.0.1:8000/api/v1/strategies?limit=1" | jq -r '.items[0].id')
curl -s "http://127.0.0.1:8000/api/v1/strategies/${SID}/backtests?limit=1" | jq '.items[0] | {id, label, metrics: {trade_count, total_return}}'

# Recharts is in the frontend deps from P2 Session 5; sanity check
grep -E "\"recharts\"" apps/frontend/package.json

docker compose down
```

- [ ] On `main`, at `p4-order-source-filter-complete`.
- [ ] At least one persisted `BacktestResult` exists (or you can submit one).
- [ ] `recharts` is in deps (no version bump expected).

```bash
git checkout -b feat/p4-backtest-charting-improvements
```

---

## §6.1 — Plan

The existing `BacktestResultsView` (P2 Session 5 §5.6) renders one recharts `<LineChart>`. The four upgrades require:

1. **Drawdown sub-chart.** Compute drawdown series from `result.equity_curve` (running peak then `(value - peak) / peak`). Render as a small `<AreaChart>` below the equity chart. Both charts use the same `t`-axis domain.

2. **Trade markers.** Recharts supports `<Scatter>` and `<ReferenceDot>`. For a small number of trades (typically <100 in a reference RSI backtest), `<ReferenceDot>` per-entry and per-exit is the simplest: each gets `x={timestamp}` and `y={equity_at_that_moment}`. The hover tooltip needs the trade data attached; recharts handles tooltips per-dot via the `label` prop.

   The trickier bit: getting the y-value (equity) at the trade timestamp. The `equity_curve` is sampled at bar boundaries; trades fall on those same boundaries (the backtester fills at next-bar-open). For each trade, find the equity point at the trade's `entry_ts` and `exit_ts` and use that y.

3. **Y-axis toggle.** Add a `mode: "equity" | "returns"` state. When `returns`, transform the data on the fly: `equity_pct = (e.equity / starting_equity - 1) * 100`. Same scale issue applies to trade markers' y-values.

4. **Trade stats section.** Pure data crunching on `result.trades`. Median is `trades.sort((a,b) => a.pnl - b.pnl)[Math.floor(n/2)]`. Streaks iterate once through trades-sorted-by-time.

The work splits naturally:
- §6.2 — helper functions (drawdown, returns transform, stats, streaks)
- §6.3 — the upgraded view component
- §6.4 — Vitest tests
- §6.5 — manual smoke

---

## §6.2 — Helper Functions

Create `apps/frontend/src/pages/Strategies/backtestHelpers.ts`:

```typescript
/**
 * Helpers for the BacktestResultsView upgrades. Pure functions of the
 * BacktestResult contents — no I/O, no React.
 */
import type { BacktestResult, BacktestTradeT, EquityPointT } from "@/api/types";

// ---------------- Drawdown ----------------

export interface DrawdownPoint {
  t: number;            // epoch ms (matches the equity chart's x axis)
  drawdown_pct: number; // negative fraction, e.g. -0.087 for -8.7%
  peak: number;
}

/**
 * Drawdown series from an equity curve. At each point we track the
 * running peak; drawdown is (value - peak) / peak.
 *
 * The result is a series of the same length as the input curve. If the
 * curve is empty, returns []. If the first equity point is <= 0 (shouldn't
 * happen, but be defensive), uses it as the initial peak; the rest of
 * the series will compute drawdown relative to whatever the peak becomes.
 */
export function computeDrawdown(curve: EquityPointT[]): DrawdownPoint[] {
  if (curve.length === 0) return [];
  let peak = curve[0].equity;
  return curve.map((p) => {
    if (p.equity > peak) peak = p.equity;
    const dd = peak > 0 ? (p.equity - peak) / peak : 0;
    return {
      t: new Date(p.t).getTime(),
      drawdown_pct: dd,
      peak,
    };
  });
}

// ---------------- Equity → returns transform ----------------

export interface EquityChartPoint {
  t: number;
  value: number;   // dollars OR percent depending on the mode
}

export function transformEquityForChart(
  curve: EquityPointT[],
  mode: "equity" | "returns",
  startingEquity: number,
): EquityChartPoint[] {
  if (curve.length === 0) return [];
  if (mode === "equity") {
    return curve.map((p) => ({ t: new Date(p.t).getTime(), value: p.equity }));
  }
  // returns: percent from starting equity
  const base = startingEquity > 0 ? startingEquity : curve[0].equity;
  return curve.map((p) => ({
    t: new Date(p.t).getTime(),
    value: base > 0 ? ((p.equity / base) - 1) * 100 : 0,
  }));
}

// ---------------- Trade markers ----------------

export interface TradeMarker {
  t: number;
  y: number;       // y-value matching the current mode
  kind: "entry" | "exit";
  trade: BacktestTradeT;
}

/**
 * Given trades + the equity curve + the current mode, compute trade markers.
 *
 * Each closed trade contributes two markers (entry, exit). Trades with
 * exit_ts=null contribute only an entry marker.
 *
 * Y-values are sampled from the equity curve at the nearest point to the
 * trade timestamp. If the curve is sparse, the marker will sit on the
 * polyline; if there's an exact match, perfect.
 */
export function computeTradeMarkers(
  trades: BacktestTradeT[],
  curve: EquityPointT[],
  mode: "equity" | "returns",
  startingEquity: number,
): TradeMarker[] {
  if (trades.length === 0 || curve.length === 0) return [];
  // Precompute mode-transformed series for fast nearest-point lookup
  const transformed = transformEquityForChart(curve, mode, startingEquity);
  const markers: TradeMarker[] = [];

  function valueAt(timestampMs: number): number {
    // Binary-search the closest point — curve is sorted by t.
    let lo = 0, hi = transformed.length - 1;
    if (timestampMs <= transformed[0].t) return transformed[0].value;
    if (timestampMs >= transformed[hi].t) return transformed[hi].value;
    while (lo < hi - 1) {
      const mid = (lo + hi) >> 1;
      if (transformed[mid].t <= timestampMs) lo = mid; else hi = mid;
    }
    // Pick the closer of lo / hi
    return Math.abs(transformed[lo].t - timestampMs) <=
           Math.abs(transformed[hi].t - timestampMs)
      ? transformed[lo].value
      : transformed[hi].value;
  }

  for (const t of trades) {
    const entryT = new Date(t.entry_ts).getTime();
    markers.push({ t: entryT, y: valueAt(entryT), kind: "entry", trade: t });
    if (t.exit_ts) {
      const exitT = new Date(t.exit_ts).getTime();
      markers.push({ t: exitT, y: valueAt(exitT), kind: "exit", trade: t });
    }
  }
  return markers;
}

// ---------------- Per-trade stats ----------------

export interface TradeStats {
  count: number;
  wins: number;
  losses: number;
  best_pnl: number;
  worst_pnl: number;
  avg_pnl: number;
  median_pnl: number;
  avg_win_pnl: number;
  avg_loss_pnl: number;
  avg_duration_win_sec: number;
  avg_duration_loss_sec: number;
  longest_win_streak: number;
  longest_loss_streak: number;
}

const EMPTY_STATS: TradeStats = {
  count: 0, wins: 0, losses: 0,
  best_pnl: 0, worst_pnl: 0,
  avg_pnl: 0, median_pnl: 0,
  avg_win_pnl: 0, avg_loss_pnl: 0,
  avg_duration_win_sec: 0, avg_duration_loss_sec: 0,
  longest_win_streak: 0, longest_loss_streak: 0,
};

function _median(nums: number[]): number {
  if (nums.length === 0) return 0;
  const sorted = [...nums].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? (sorted[mid - 1] + sorted[mid]) / 2
    : sorted[mid];
}

export function computeTradeStats(trades: BacktestTradeT[]): TradeStats {
  // Only closed trades with non-null pnl count
  const closed = trades.filter((t): t is BacktestTradeT & { pnl: number } =>
    t.pnl !== null && t.exit_ts !== null
  );
  if (closed.length === 0) return EMPTY_STATS;

  const pnls = closed.map((t) => t.pnl);
  const wins = closed.filter((t) => t.pnl > 0);
  const losses = closed.filter((t) => t.pnl < 0);

  const best_pnl = Math.max(...pnls);
  const worst_pnl = Math.min(...pnls);
  const avg_pnl = pnls.reduce((a, b) => a + b, 0) / pnls.length;
  const median_pnl = _median(pnls);
  const avg_win_pnl = wins.length > 0
    ? wins.reduce((a, t) => a + t.pnl, 0) / wins.length
    : 0;
  const avg_loss_pnl = losses.length > 0
    ? losses.reduce((a, t) => a + t.pnl, 0) / losses.length
    : 0;

  const winsWithDuration = wins.filter((t) => t.duration_seconds !== null) as
    (typeof wins[0] & { duration_seconds: number })[];
  const lossesWithDuration = losses.filter((t) => t.duration_seconds !== null) as
    (typeof losses[0] & { duration_seconds: number })[];
  const avg_duration_win_sec = winsWithDuration.length > 0
    ? winsWithDuration.reduce((a, t) => a + t.duration_seconds, 0) / winsWithDuration.length
    : 0;
  const avg_duration_loss_sec = lossesWithDuration.length > 0
    ? lossesWithDuration.reduce((a, t) => a + t.duration_seconds, 0) / lossesWithDuration.length
    : 0;

  // Streaks: iterate trades in time order
  const byTime = [...closed].sort((a, b) =>
    new Date(a.exit_ts!).getTime() - new Date(b.exit_ts!).getTime()
  );
  let cur_win_streak = 0, cur_loss_streak = 0;
  let longest_win_streak = 0, longest_loss_streak = 0;
  for (const t of byTime) {
    if (t.pnl > 0) {
      cur_win_streak += 1;
      cur_loss_streak = 0;
      if (cur_win_streak > longest_win_streak) longest_win_streak = cur_win_streak;
    } else if (t.pnl < 0) {
      cur_loss_streak += 1;
      cur_win_streak = 0;
      if (cur_loss_streak > longest_loss_streak) longest_loss_streak = cur_loss_streak;
    } else {
      // pnl == 0: reset both
      cur_win_streak = 0;
      cur_loss_streak = 0;
    }
  }

  return {
    count: closed.length,
    wins: wins.length,
    losses: losses.length,
    best_pnl, worst_pnl,
    avg_pnl, median_pnl,
    avg_win_pnl, avg_loss_pnl,
    avg_duration_win_sec, avg_duration_loss_sec,
    longest_win_streak, longest_loss_streak,
  };
}
```

- [ ] `backtestHelpers.ts` created.

---

## §6.3 — Upgraded `BacktestResultsView`

Edit `apps/frontend/src/pages/Strategies/BacktestResultsView.tsx`. Replace the existing component. Major changes:

- Add y-axis mode toggle in the modal header.
- Replace the single `<LineChart>` with two stacked charts (equity + drawdown).
- Overlay trade markers on the equity chart via `<ReferenceDot>`s.
- Replace the existing single MetricCard grid with two rows: the eight P2 metrics (unchanged) PLUS a new "Trade stats" panel below the equity chart.

```tsx
import { useMemo, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ReferenceLine, ReferenceDot,
  AreaChart, Area, CartesianGrid,
} from "recharts";
import type { BacktestResult } from "@/api/types";
import {
  formatPct, formatNumber, formatCurrency, formatDuration,
} from "@/components/strategies/formatters";
import {
  computeDrawdown,
  computeTradeMarkers,
  computeTradeStats,
  transformEquityForChart,
  type TradeMarker,
} from "./backtestHelpers";


interface Props {
  result: BacktestResult;
  onClose: () => void;
}


type YAxisMode = "equity" | "returns";


export function BacktestResultsView({ result, onClose }: Props) {
  const [mode, setMode] = useState<YAxisMode>("equity");
  const startingEquity = result.metrics.starting_equity;

  const equityChartData = useMemo(
    () => transformEquityForChart(result.equity_curve, mode, startingEquity),
    [result.equity_curve, mode, startingEquity],
  );
  const drawdownData = useMemo(
    () => computeDrawdown(result.equity_curve),
    [result.equity_curve],
  );
  const tradeMarkers = useMemo(
    () => computeTradeMarkers(result.trades, result.equity_curve, mode, startingEquity),
    [result.trades, result.equity_curve, mode, startingEquity],
  );
  const tradeStats = useMemo(
    () => computeTradeStats(result.trades),
    [result.trades],
  );

  const yReferenceValue = mode === "equity" ? startingEquity : 0;
  const yLabel = mode === "equity" ? "Equity ($)" : "Returns (%)";

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/80">
      <div className="w-[64rem] max-h-[92vh] overflow-y-auto rounded-lg border border-gray-700 bg-gray-950 p-5">

        {/* ---- Header ---- */}
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
          <div className="flex items-center gap-2">
            <ModeToggle mode={mode} onChange={setMode} />
            <button onClick={onClose} className="text-gray-400 hover:text-white">✕</button>
          </div>
        </div>

        {/* ---- Top metric grid (unchanged from P2) ---- */}
        <div className="mb-4 grid grid-cols-4 gap-2">
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

        {/* ---- Equity curve with trade markers ---- */}
        <div className="mb-3 rounded border border-gray-800 bg-gray-900 p-3">
          <div className="mb-1 flex items-center justify-between text-sm">
            <span className="font-semibold text-gray-300">{yLabel}</span>
            <span className="text-xs text-gray-500">{tradeMarkers.length / 2} trades</span>
          </div>
          {equityChartData.length === 0 ? (
            <div className="py-8 text-center text-sm text-gray-500">No equity points</div>
          ) : (
            <div style={{ width: "100%", height: 240 }}>
              <ResponsiveContainer>
                <LineChart data={equityChartData} syncId="bt">
                  <CartesianGrid stroke="#1f2937" strokeDasharray="3 3" />
                  <XAxis dataKey="t" type="number" scale="time"
                    domain={["dataMin", "dataMax"]}
                    tickFormatter={(v) => new Date(v).toLocaleDateString()}
                    tick={{ fill: "#9ca3af", fontSize: 11 }}
                  />
                  <YAxis domain={["auto", "auto"]} tick={{ fill: "#9ca3af", fontSize: 11 }}
                    tickFormatter={(v) =>
                      mode === "equity" ? `$${(v / 1000).toFixed(0)}k` : `${v.toFixed(1)}%`
                    } />
                  <Tooltip
                    contentStyle={{ background: "#111827", border: "1px solid #374151" }}
                    labelFormatter={(v) => new Date(v as number).toLocaleString()}
                    formatter={(v) =>
                      mode === "equity" ? formatCurrency(v as number) : `${(v as number).toFixed(2)}%`
                    }
                  />
                  <ReferenceLine y={yReferenceValue} stroke="#6b7280" strokeDasharray="3 3" />
                  <Line type="monotone" dataKey="value" stroke="#3b82f6" dot={false} strokeWidth={2} />

                  {/* Trade markers */}
                  {tradeMarkers.map((m, i) => (
                    <ReferenceDot
                      key={`mk-${i}`}
                      x={m.t}
                      y={m.y}
                      r={4}
                      fill={m.kind === "entry" ? "#10b981" : "#ef4444"}
                      stroke="#0f172a"
                      strokeWidth={1.5}
                      ifOverflow="hidden"
                      // We don't get per-dot hover tooltips out of the box from
                      // <ReferenceDot>; the per-point Tooltip above shows the
                      // line's y. A future polish would replace these with a
                      // <Scatter> series for hover. For now: dots are visual
                      // only; the trade list table below carries the detail.
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
          <div className="mt-1 flex items-center justify-end gap-3 text-xs">
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-full bg-emerald-500" /> entry
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-full bg-rose-500" /> exit
            </span>
          </div>
        </div>

        {/* ---- Drawdown sub-chart ---- */}
        <div className="mb-4 rounded border border-gray-800 bg-gray-900 p-3">
          <div className="mb-1 text-sm font-semibold text-gray-300">Drawdown (%)</div>
          {drawdownData.length === 0 ? (
            <div className="py-4 text-center text-sm text-gray-500">No drawdown data</div>
          ) : (
            <div style={{ width: "100%", height: 120 }}>
              <ResponsiveContainer>
                <AreaChart data={drawdownData} syncId="bt">
                  <CartesianGrid stroke="#1f2937" strokeDasharray="3 3" />
                  <XAxis dataKey="t" type="number" scale="time"
                    domain={["dataMin", "dataMax"]}
                    tickFormatter={(v) => new Date(v).toLocaleDateString()}
                    tick={{ fill: "#9ca3af", fontSize: 11 }}
                  />
                  <YAxis domain={["auto", 0]} tick={{ fill: "#9ca3af", fontSize: 11 }}
                    tickFormatter={(v) => `${(v * 100).toFixed(1)}%`} />
                  <Tooltip
                    contentStyle={{ background: "#111827", border: "1px solid #374151" }}
                    labelFormatter={(v) => new Date(v as number).toLocaleString()}
                    formatter={(v) => `${((v as number) * 100).toFixed(2)}%`}
                  />
                  <ReferenceLine y={0} stroke="#6b7280" strokeDasharray="3 3" />
                  <Area type="monotone" dataKey="drawdown_pct"
                    stroke="#ef4444" fill="#ef4444" fillOpacity={0.25} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

        {/* ---- Trade stats ---- */}
        <div className="mb-4 rounded border border-gray-800 bg-gray-900 p-3">
          <div className="mb-2 text-sm font-semibold text-gray-300">Trade stats</div>
          {tradeStats.count === 0 ? (
            <div className="py-2 text-sm text-gray-500">No closed trades</div>
          ) : (
            <div className="grid grid-cols-4 gap-3 text-sm">
              <StatPair label="Wins / Losses"
                value={`${tradeStats.wins} / ${tradeStats.losses}`} />
              <StatPair label="Best trade"
                value={formatCurrency(tradeStats.best_pnl)}
                color="text-emerald-300" />
              <StatPair label="Worst trade"
                value={formatCurrency(tradeStats.worst_pnl)}
                color="text-rose-300" />
              <StatPair label="Median pnl"
                value={formatCurrency(tradeStats.median_pnl)}
                color={tradeStats.median_pnl >= 0 ? "text-emerald-300" : "text-rose-300"} />
              <StatPair label="Avg win" value={formatCurrency(tradeStats.avg_win_pnl)}
                color="text-emerald-300" />
              <StatPair label="Avg loss" value={formatCurrency(tradeStats.avg_loss_pnl)}
                color="text-rose-300" />
              <StatPair label="Avg win duration"
                value={formatDuration(tradeStats.avg_duration_win_sec)} />
              <StatPair label="Avg loss duration"
                value={formatDuration(tradeStats.avg_duration_loss_sec)} />
              <StatPair label="Longest win streak"
                value={`${tradeStats.longest_win_streak}`} />
              <StatPair label="Longest loss streak"
                value={`${tradeStats.longest_loss_streak}`} />
            </div>
          )}
        </div>

        {/* ---- Trades table (unchanged from P2) ---- */}
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
                  <tr><td colSpan={8} className="px-3 py-4 text-center text-gray-500">
                    No closed trades
                  </td></tr>
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


// ---- Sub-components ----


function ModeToggle({ mode, onChange }: { mode: YAxisMode; onChange: (m: YAxisMode) => void }) {
  return (
    <div className="inline-flex overflow-hidden rounded border border-gray-700 text-xs">
      <button
        onClick={() => onChange("equity")}
        className={`px-3 py-1 ${
          mode === "equity" ? "bg-blue-700 text-white" : "bg-gray-800 text-gray-300"
        }`}
      >
        Equity ($)
      </button>
      <button
        onClick={() => onChange("returns")}
        className={`px-3 py-1 ${
          mode === "returns" ? "bg-blue-700 text-white" : "bg-gray-800 text-gray-300"
        }`}
      >
        Returns (%)
      </button>
    </div>
  );
}


function StatPair({
  label, value, color,
}: { label: string; value: string; color?: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase text-gray-500">{label}</div>
      <div className={`text-base font-semibold ${color ?? "text-white"}`}>{value}</div>
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

> Width bumped from `w-[60rem]` to `w-[64rem]` to accommodate the wider drawdown chart without crowding. On a 13" laptop (1280px), 64rem ≈ 1024px still fits with margin. If a future viewer thinks 64rem is too wide, drop to 60rem and let the drawdown chart compress; recharts `ResponsiveContainer` handles it.

- [ ] `BacktestResultsView` rewritten.
- [ ] All four upgrades (drawdown, markers, mode toggle, stats) wired in.

---

## §6.4 — Vitest Tests

Edit `apps/frontend/src/pages/Strategies/__tests__/BacktestResultsView.test.tsx`. **Don't replace** the existing tests; add new ones alongside.

```tsx
import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { BacktestResultsView } from "../BacktestResultsView";
import {
  computeDrawdown,
  computeTradeStats,
  transformEquityForChart,
  computeTradeMarkers,
} from "../backtestHelpers";


// ---- existing tests from P2 Session 5 stay ----

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
    { t: "2025-11-03T16:00:00Z", equity: 101500 },
    { t: "2025-11-04T14:30:00Z", equity: 102000 },
    { t: "2025-11-04T16:00:00Z", equity: 99000 },     // drawdown begins
    { t: "2025-11-05T14:30:00Z", equity: 103000 },
    { t: "2025-11-05T16:00:00Z", equity: 105230 },
  ],
  trades: [
    {
      symbol: "AAPL", side: "long" as const,
      entry_ts: "2025-11-03T15:00:00Z", entry_price: 190.0,
      exit_ts: "2025-11-03T15:30:00Z", exit_price: 191.5,
      qty: 10, pnl: 15.0, duration_seconds: 1800, exit_reason: "rsi_exit",
    },
    {
      symbol: "AAPL", side: "long" as const,
      entry_ts: "2025-11-04T15:00:00Z", entry_price: 189.0,
      exit_ts: "2025-11-04T15:30:00Z", exit_price: 188.5,
      qty: 10, pnl: -5.0, duration_seconds: 1800, exit_reason: "stop_loss",
    },
    {
      symbol: "AAPL", side: "long" as const,
      entry_ts: "2025-11-05T15:00:00Z", entry_price: 192.0,
      exit_ts: "2025-11-05T15:30:00Z", exit_price: 195.0,
      qty: 10, pnl: 30.0, duration_seconds: 1800, exit_reason: "rsi_exit",
    },
  ],
  range_start: "2025-11-03T00:00:00Z",
  range_end: "2025-11-06T00:00:00Z",
  created_at: "2025-11-06T00:00:00Z",
};


// ---- Helper unit tests ----


describe("computeDrawdown", () => {
  it("returns empty for empty input", () => {
    expect(computeDrawdown([])).toEqual([]);
  });

  it("computes drawdown as negative fraction from running peak", () => {
    const dd = computeDrawdown([
      { t: "2025-11-03T00:00:00Z", equity: 100000 },
      { t: "2025-11-03T01:00:00Z", equity: 105000 },   // new peak
      { t: "2025-11-03T02:00:00Z", equity: 102000 },   // 3000 below peak
      { t: "2025-11-03T03:00:00Z", equity: 110000 },   // new peak
    ]);
    expect(dd[0].drawdown_pct).toBe(0);
    expect(dd[1].drawdown_pct).toBe(0);                 // at new peak
    expect(dd[2].drawdown_pct).toBeCloseTo(-3000 / 105000, 5);
    expect(dd[3].drawdown_pct).toBe(0);                 // new peak
  });
});


describe("transformEquityForChart", () => {
  it("equity mode passes values through", () => {
    const out = transformEquityForChart([
      { t: "2025-11-03T00:00:00Z", equity: 100000 },
      { t: "2025-11-03T01:00:00Z", equity: 105000 },
    ], "equity", 100000);
    expect(out[0].value).toBe(100000);
    expect(out[1].value).toBe(105000);
  });

  it("returns mode converts to percent from starting equity", () => {
    const out = transformEquityForChart([
      { t: "2025-11-03T00:00:00Z", equity: 100000 },
      { t: "2025-11-03T01:00:00Z", equity: 110000 },
      { t: "2025-11-03T02:00:00Z", equity: 95000 },
    ], "returns", 100000);
    expect(out[0].value).toBeCloseTo(0, 5);
    expect(out[1].value).toBeCloseTo(10, 5);
    expect(out[2].value).toBeCloseTo(-5, 5);
  });

  it("returns mode handles zero starting equity gracefully", () => {
    const out = transformEquityForChart([
      { t: "2025-11-03T00:00:00Z", equity: 100 },
    ], "returns", 0);
    // Falls back to first equity point as base — so first point is 0%
    expect(out[0].value).toBeCloseTo(0, 5);
  });
});


describe("computeTradeStats", () => {
  it("returns empty stats for no trades", () => {
    const s = computeTradeStats([]);
    expect(s.count).toBe(0);
    expect(s.best_pnl).toBe(0);
  });

  it("computes wins / losses / streaks from three trades", () => {
    const s = computeTradeStats(result.trades);
    expect(s.count).toBe(3);
    expect(s.wins).toBe(2);
    expect(s.losses).toBe(1);
    expect(s.best_pnl).toBe(30.0);
    expect(s.worst_pnl).toBe(-5.0);
    expect(s.avg_pnl).toBeCloseTo((15 + -5 + 30) / 3, 5);
    // Median of [-5, 15, 30] = 15
    expect(s.median_pnl).toBe(15);
    // Longest win streak: trade 1 (win), trade 3 (win after loss) → 1
    expect(s.longest_win_streak).toBe(1);
    expect(s.longest_loss_streak).toBe(1);
  });

  it("computes streaks across consecutive wins", () => {
    const trades = [
      { symbol: "X", side: "long" as const,
        entry_ts: "2025-01-01T10:00:00Z", entry_price: 100,
        exit_ts: "2025-01-01T11:00:00Z", exit_price: 110,
        qty: 1, pnl: 10, duration_seconds: 3600, exit_reason: "x" },
      { symbol: "X", side: "long" as const,
        entry_ts: "2025-01-02T10:00:00Z", entry_price: 100,
        exit_ts: "2025-01-02T11:00:00Z", exit_price: 105,
        qty: 1, pnl: 5, duration_seconds: 3600, exit_reason: "x" },
      { symbol: "X", side: "long" as const,
        entry_ts: "2025-01-03T10:00:00Z", entry_price: 100,
        exit_ts: "2025-01-03T11:00:00Z", exit_price: 102,
        qty: 1, pnl: 2, duration_seconds: 3600, exit_reason: "x" },
      { symbol: "X", side: "long" as const,
        entry_ts: "2025-01-04T10:00:00Z", entry_price: 100,
        exit_ts: "2025-01-04T11:00:00Z", exit_price: 95,
        qty: 1, pnl: -5, duration_seconds: 3600, exit_reason: "x" },
    ];
    const s = computeTradeStats(trades);
    expect(s.longest_win_streak).toBe(3);
    expect(s.longest_loss_streak).toBe(1);
  });
});


describe("computeTradeMarkers", () => {
  it("produces 2 markers per closed trade (entry + exit)", () => {
    const markers = computeTradeMarkers(result.trades, result.equity_curve, "equity", 100000);
    expect(markers).toHaveLength(6);
    expect(markers.filter((m) => m.kind === "entry")).toHaveLength(3);
    expect(markers.filter((m) => m.kind === "exit")).toHaveLength(3);
  });

  it("produces 1 marker for an open trade with null exit_ts", () => {
    const openTrade = { ...result.trades[0], exit_ts: null, exit_price: null, pnl: null };
    const markers = computeTradeMarkers([openTrade], result.equity_curve, "equity", 100000);
    expect(markers).toHaveLength(1);
    expect(markers[0].kind).toBe("entry");
  });

  it("returns [] when there are no trades or no curve", () => {
    expect(computeTradeMarkers([], result.equity_curve, "equity", 100000)).toEqual([]);
    expect(computeTradeMarkers(result.trades, [], "equity", 100000)).toEqual([]);
  });
});


// ---- Component-level tests ----


describe("BacktestResultsView — P4 §6", () => {
  it("renders Trade stats section with computed values", () => {
    render(<BacktestResultsView result={result as any} onClose={() => {}} />);
    expect(screen.getByText("Trade stats")).toBeInTheDocument();
    // wins / losses values
    expect(screen.getByText("2 / 1")).toBeInTheDocument();
    // best / worst trade
    expect(screen.getByText("$30.00")).toBeInTheDocument();
    expect(screen.getByText("$-5.00")).toBeInTheDocument();
  });

  it("renders Drawdown chart heading", () => {
    render(<BacktestResultsView result={result as any} onClose={() => {}} />);
    expect(screen.getByText("Drawdown (%)")).toBeInTheDocument();
  });

  it("renders both mode toggle buttons", () => {
    render(<BacktestResultsView result={result as any} onClose={() => {}} />);
    expect(screen.getByText("Equity ($)")).toBeInTheDocument();
    expect(screen.getByText("Returns (%)")).toBeInTheDocument();
  });

  it("y-axis mode toggle changes the displayed chart heading", () => {
    render(<BacktestResultsView result={result as any} onClose={() => {}} />);
    // Default mode is equity — header reads "Equity ($)"
    // The exact-string matching here will match BOTH the button label
    // and the chart-header label; assert via the chart-section's role context
    // For simplicity: click "Returns (%)" and assert the chart header changes.
    fireEvent.click(screen.getByRole("button", { name: "Returns (%)" }));
    // The chart-section heading should now read "Returns (%)"
    // (The button still also says "Returns (%)", so we look for 2 occurrences.)
    expect(screen.getAllByText("Returns (%)").length).toBeGreaterThanOrEqual(2);
  });

  it("shows 'No closed trades' empty state when trades is empty", () => {
    const noTradeResult = { ...result, trades: [], metrics: { ...result.metrics, trade_count: 0 } };
    render(<BacktestResultsView result={noTradeResult as any} onClose={() => {}} />);
    expect(screen.getByText("No closed trades")).toBeInTheDocument();
  });
});
```

Run:

```bash
cd apps/frontend
pnpm test --run
cd ../..
```

- [ ] 12 new test cases pass (3 + 3 + 2 + 3 + 5 = component tests, helper unit tests).
- [ ] Existing P2 Session 5 cases still pass.

---

## §6.5 — Manual Smoke

```bash
./scripts/dev.sh
```

In the browser:

1. Navigate to a strategy that has at least one persisted backtest. If you don't have one, submit one first via the BacktestRunModal.
2. Strategies → click strategy → Backtests tab → click a row to open BacktestResultsView.
3. **Equity chart:** verify the dashed horizontal line at starting equity. Verify trade markers — green dots at each entry, red at each exit. Verify the marker positions roughly match the trade timestamps shown in the trades table below.
4. **Drawdown chart:** verify it sits below the equity chart and shares its x-axis range. Drawdown is always ≤ 0; the area is red-tinted. The maximum drawdown shown should match the metric in the top grid ("Max DD").
5. **Mode toggle:** click "Returns (%)". The equity chart re-renders with y-axis in percent, starting at 0%. The horizontal reference line moves from $X to 0%. Trade markers reposition. Click "Equity ($)" again — returns to original view.
6. **Trade stats section:** verify wins/losses count matches the trades table. Best trade = max pnl row. Median pnl is between best and worst. Streak values are non-negative.
7. **Empty state:** force a backtest that produces no trades (e.g. set RSI thresholds outside the data range). Open its results view → Trade stats shows "No closed trades", trades table shows "No closed trades", drawdown chart shows the equity curve as flat (no drawdown).

```bash
docker compose down
```

- [ ] All seven smoke steps green.
- [ ] No console errors in DevTools.
- [ ] Modal fits within a 13" laptop viewport without horizontal scroll.

---

## §6.6 — Commit and PR

```bash
git add apps/frontend/src/pages/Strategies/backtestHelpers.ts
git add apps/frontend/src/pages/Strategies/BacktestResultsView.tsx
git add apps/frontend/src/pages/Strategies/__tests__/BacktestResultsView.test.tsx

git commit -m "feat(ui): backtest charting upgrades — drawdown, markers, mode toggle, stats (P4 §6)

- Drawdown sub-chart below the equity curve, sharing the x-axis via syncId
- Trade markers (green ▲ entry, red ▼ exit) on the equity curve via ReferenceDot
- Y-axis mode toggle: Equity (\$) vs Returns (%); re-renders without re-fetch
- Trade stats panel: wins / losses / best / worst / median / streaks /
  avg duration by win or loss
- All math client-side from result.equity_curve + result.trades — no
  backend schema change, no migration, works on every existing BacktestResult
- backtestHelpers.ts: pure functions for drawdown, equity transform, trade
  markers, trade stats. 12 new test cases (helpers + component)"

git push -u origin feat/p4-backtest-charting-improvements

gh pr create \
  --title "feat(ui): backtest charting upgrades (P4 §6)" \
  --body "P4 Item 6 — frontend-only. Closes P2 Session 5 Gotcha #10 ('intentionally minimal' chart). Works on every existing BacktestResult; no migration."

gh pr checks
gh pr merge --merge --delete-branch
git checkout main && git pull
git tag -a p4-backtest-charting-complete -m "P4 §6 complete"
git push origin p4-backtest-charting-complete
```

- [ ] PR merged.
- [ ] Tag pushed.
- [ ] `todo.md` updated: P4 §6 ✅.

---

## Verification Checklist (full session)

- [ ] §6.1 Plan reviewed; no backend changes confirmed.
- [ ] §6.2 `backtestHelpers.ts` with `computeDrawdown`, `transformEquityForChart`, `computeTradeMarkers`, `computeTradeStats`.
- [ ] §6.3 `BacktestResultsView` rewritten with mode toggle, drawdown sub-chart, markers, stats section.
- [ ] §6.4 12 new Vitest cases pass; existing cases still pass.
- [ ] §6.5 Manual smoke walks all seven steps cleanly.
- [ ] §6.6 PR merged, tag pushed.

---

## Notes & Gotchas

1. **Pure-frontend item, no backend changes.** Everything new (drawdown, streaks, trade markers) is computed in the browser from data the backend already persists. No migration, no schema bump, no Pydantic change. Backwards-compatible with every existing `BacktestResult`.

2. **`syncId="bt"` synchronizes the equity and drawdown x-axes.** Recharts' built-in mechanism. If you later add `<Brush>` (zoom) to either chart, both follow. Both charts must use the same x-axis `dataKey` and matching `type="number"` + `scale="time"`.

3. **`<ReferenceDot>` doesn't carry per-dot tooltips out of the box.** The hover tooltip on the line shows the line's y at the hovered x, not the trade detail. The dots are visual aids; the trade list table below carries the per-trade detail. If you want true per-dot tooltips, the upgrade is to use a `<Scatter>` series with a custom `Tooltip` renderer — but that's a separate UX iteration; the current setup serves "see where trades fired" already.

4. **Marker y-values are nearest-equity-point lookups.** §6.2's `valueAt` binary-searches the closest equity point to a trade timestamp. Trades fall on bar boundaries (the P2 backtester fills at next-bar-open), and the equity curve is sampled at every bar — so in practice the lookup almost always finds an exact match. For sparse curves the marker sits "near" the line, which is visually acceptable.

5. **`ifOverflow="hidden"`** on each `ReferenceDot` clips markers whose y is off-chart (e.g. if the user is zoomed). Without it, recharts draws the dot at the edge with a glitchy projection.

6. **Mode toggle re-renders memoized data via `useMemo`.** The mode is a dependency of `equityChartData` and `tradeMarkers`. Drawdown is NOT mode-dependent — drawdown is always a percent. Don't add `mode` to its dep array; it'd waste re-computes.

7. **The drawdown chart's y-domain is `["auto", 0]`.** Forces 0 to be the top of the axis so drawdown reads "always negative, deepest at the bottom." Without the explicit 0, recharts auto-scales with some headroom above 0 which is wasted space (drawdown can never be positive).

8. **`computeTradeStats` only counts CLOSED trades.** Trades with `exit_ts === null` are open positions force-closed by the backtester at end-of-range (P2 Session 3 logic) OR strategies that opened a position that never closed. The metric set treats them as "not yet a stat." If a user submits a backtest where every trade is open at the end, `count=0` is correct — they should design the strategy to close.

9. **Streak counting resets on zero-pnl trades.** A trade with `pnl=0` (e.g. immediate exit at entry price after slippage cancellation) breaks both streaks. This is the most defensible interpretation — zero-pnl isn't a win or a loss, so it ends whichever streak was active.

10. **The modal width grew from `w-[60rem]` to `w-[64rem]`.** Drawdown sub-chart needs vertical breathing room; rather than cramping side-by-side, we keep the two charts stacked and accept the extra height. The 64rem width gives the trade-stats grid four columns without wrap. On a 13" laptop (1280px native, ~1024 effective), 64rem ≈ 1024px just fits with margin. If you ever target smaller screens (10" tablets), drop to `w-[56rem]` and let the stat grid wrap to 3 columns.

11. **No new MCP tool here.** The agent already has `list_recent_backtests` from P3 Session 2. A "get_backtest_detail" tool that returns drawdown, trade stats, etc. would be nice for the agent — but `get_strategy_detail` already returns the latest backtest summary, and the agent can compute the same stats from the trade list if it really wants. Not worth the tool inflation.

12. **Don't bundle other P4 items.** Tag and ship.

---

*End of P4 Item 6 v0.1.*
