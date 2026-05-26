/**
 * Helpers for the BacktestResultsView upgrades (P4 §6). Pure functions of
 * the BacktestResult contents — no I/O, no React, easy to test.
 *
 * Rendering uses hand-rolled SVG (matching the existing chart approach,
 * since recharts isn't installed — see [[blocker-norton-ssl-npm]]). These
 * helpers don't care which renderer consumes them.
 */
import type { BacktestTradeT, EquityPointT } from "@/api/types";

// ---------------- Drawdown ----------------

export interface DrawdownPoint {
  t: number; // epoch ms (same axis as the equity chart)
  drawdown_pct: number; // negative fraction, e.g. -0.087 for -8.7%
  peak: number;
}

/**
 * Drawdown series from an equity curve. At each point we track the running
 * peak; drawdown is ``(value - peak) / peak``.
 *
 * Returns a series of the same length as the input curve. Empty input
 * yields ``[]``. If the first equity point is <= 0 (shouldn't happen but
 * defensive), uses it as the initial peak and the rest of the series
 * computes drawdown relative to whatever the peak becomes.
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
  value: number; // dollars OR percent depending on the mode
}

export type YAxisMode = "equity" | "returns";

export function transformEquityForChart(
  curve: EquityPointT[],
  mode: YAxisMode,
  startingEquity: number,
): EquityChartPoint[] {
  if (curve.length === 0) return [];
  if (mode === "equity") {
    return curve.map((p) => ({
      t: new Date(p.t).getTime(),
      value: p.equity,
    }));
  }
  // returns: percent from starting equity. Fall back to the first equity
  // point if startingEquity is missing or zero — keeps the first point at
  // 0% in that degenerate case.
  const base = startingEquity > 0 ? startingEquity : curve[0].equity;
  return curve.map((p) => ({
    t: new Date(p.t).getTime(),
    value: base > 0 ? (p.equity / base - 1) * 100 : 0,
  }));
}

// ---------------- Trade markers ----------------

export interface TradeMarker {
  t: number;
  y: number; // y-value matching the current mode
  kind: "entry" | "exit";
  trade: BacktestTradeT;
}

/**
 * Markers for the equity chart. Each closed trade contributes two
 * (entry + exit); open trades contribute only the entry.
 *
 * Y-values come from the nearest equity-curve point to the trade
 * timestamp. The backtester fills at next-bar-open and the equity curve
 * is sampled at every bar, so in practice this lookup almost always
 * finds an exact match.
 */
export function computeTradeMarkers(
  trades: BacktestTradeT[],
  curve: EquityPointT[],
  mode: YAxisMode,
  startingEquity: number,
): TradeMarker[] {
  if (trades.length === 0 || curve.length === 0) return [];
  const transformed = transformEquityForChart(curve, mode, startingEquity);
  const markers: TradeMarker[] = [];

  function valueAt(timestampMs: number): number {
    let lo = 0;
    let hi = transformed.length - 1;
    if (timestampMs <= transformed[0].t) return transformed[0].value;
    if (timestampMs >= transformed[hi].t) return transformed[hi].value;
    while (lo < hi - 1) {
      const mid = (lo + hi) >> 1;
      if (transformed[mid].t <= timestampMs) lo = mid;
      else hi = mid;
    }
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
  count: 0,
  wins: 0,
  losses: 0,
  best_pnl: 0,
  worst_pnl: 0,
  avg_pnl: 0,
  median_pnl: 0,
  avg_win_pnl: 0,
  avg_loss_pnl: 0,
  avg_duration_win_sec: 0,
  avg_duration_loss_sec: 0,
  longest_win_streak: 0,
  longest_loss_streak: 0,
};

function median(nums: number[]): number {
  if (nums.length === 0) return 0;
  const sorted = [...nums].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? (sorted[mid - 1] + sorted[mid]) / 2
    : sorted[mid];
}

export function computeTradeStats(trades: BacktestTradeT[]): TradeStats {
  // Only closed trades (non-null pnl + non-null exit_ts) count.
  const closed = trades.filter(
    (t): t is BacktestTradeT & { pnl: number } =>
      t.pnl !== null && t.exit_ts !== null,
  );
  if (closed.length === 0) return EMPTY_STATS;

  const pnls = closed.map((t) => t.pnl);
  const wins = closed.filter((t) => t.pnl > 0);
  const losses = closed.filter((t) => t.pnl < 0);

  const best_pnl = Math.max(...pnls);
  const worst_pnl = Math.min(...pnls);
  const avg_pnl = pnls.reduce((a, b) => a + b, 0) / pnls.length;
  const median_pnl = median(pnls);
  const avg_win_pnl =
    wins.length > 0
      ? wins.reduce((a, t) => a + t.pnl, 0) / wins.length
      : 0;
  const avg_loss_pnl =
    losses.length > 0
      ? losses.reduce((a, t) => a + t.pnl, 0) / losses.length
      : 0;

  const winDurations = wins
    .map((t) => t.duration_seconds)
    .filter((d): d is number => d !== null);
  const lossDurations = losses
    .map((t) => t.duration_seconds)
    .filter((d): d is number => d !== null);
  const avg_duration_win_sec =
    winDurations.length > 0
      ? winDurations.reduce((a, b) => a + b, 0) / winDurations.length
      : 0;
  const avg_duration_loss_sec =
    lossDurations.length > 0
      ? lossDurations.reduce((a, b) => a + b, 0) / lossDurations.length
      : 0;

  // Streaks: iterate trades in exit-time order. Zero-pnl trades reset
  // both streaks — that's the most defensible interpretation (a zero-pnl
  // trade isn't a win OR a loss, so it ends whatever streak was active).
  const byTime = [...closed].sort(
    (a, b) =>
      new Date(a.exit_ts!).getTime() - new Date(b.exit_ts!).getTime(),
  );
  let curWin = 0;
  let curLoss = 0;
  let longest_win_streak = 0;
  let longest_loss_streak = 0;
  for (const t of byTime) {
    if (t.pnl > 0) {
      curWin += 1;
      curLoss = 0;
      if (curWin > longest_win_streak) longest_win_streak = curWin;
    } else if (t.pnl < 0) {
      curLoss += 1;
      curWin = 0;
      if (curLoss > longest_loss_streak) longest_loss_streak = curLoss;
    } else {
      curWin = 0;
      curLoss = 0;
    }
  }

  return {
    count: closed.length,
    wins: wins.length,
    losses: losses.length,
    best_pnl,
    worst_pnl,
    avg_pnl,
    median_pnl,
    avg_win_pnl,
    avg_loss_pnl,
    avg_duration_win_sec,
    avg_duration_loss_sec,
    longest_win_streak,
    longest_loss_streak,
  };
}
