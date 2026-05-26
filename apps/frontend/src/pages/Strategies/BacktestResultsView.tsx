import { useMemo, useState } from "react";
import type { BacktestResult } from "@/api/types";
import {
  formatCurrency,
  formatDuration,
  formatNumber,
  formatPct,
} from "@/components/strategies/formatters";
import {
  computeDrawdown,
  computeTradeMarkers,
  computeTradeStats,
  transformEquityForChart,
  type DrawdownPoint,
  type EquityChartPoint,
  type TradeMarker,
  type YAxisMode,
} from "./backtestHelpers";

interface Props {
  result: BacktestResult;
  onClose: () => void;
}

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
    () =>
      computeTradeMarkers(
        result.trades,
        result.equity_curve,
        mode,
        startingEquity,
      ),
    [result.trades, result.equity_curve, mode, startingEquity],
  );
  const tradeStats = useMemo(
    () => computeTradeStats(result.trades),
    [result.trades],
  );

  const referenceValue = mode === "equity" ? startingEquity : 0;
  const valueLabel = mode === "equity" ? "Equity ($)" : "Returns (%)";

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/80">
      <div className="w-[64rem] max-h-[92vh] overflow-y-auto rounded-lg border border-gray-700 bg-gray-950 p-5">
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

        <div className="mb-3 rounded border border-gray-800 bg-gray-900 p-3">
          <div className="mb-1 flex items-center justify-between">
            <span className="text-sm font-semibold text-gray-300">{valueLabel}</span>
            <span className="text-xs text-gray-500">
              {tradeMarkers.filter((m) => m.kind === "entry").length} entries
            </span>
          </div>
          <EquityCurveChart
            data={equityChartData}
            markers={tradeMarkers}
            referenceValue={referenceValue}
            mode={mode}
          />
          <div className="mt-1 flex items-center justify-end gap-3 text-xs">
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-full bg-emerald-500" /> entry
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-full bg-rose-500" /> exit
            </span>
          </div>
        </div>

        <div className="mb-4 rounded border border-gray-800 bg-gray-900 p-3">
          <div className="mb-1 text-sm font-semibold text-gray-300">Drawdown (%)</div>
          <DrawdownChart data={drawdownData} />
        </div>

        <div className="mb-4 rounded border border-gray-800 bg-gray-900 p-3">
          <div className="mb-2 text-sm font-semibold text-gray-300">Trade stats</div>
          {tradeStats.count === 0 ? (
            <div className="py-2 text-sm text-gray-500">No closed trades</div>
          ) : (
            <div className="grid grid-cols-4 gap-3 text-sm">
              <StatPair label="Wins / Losses" value={`${tradeStats.wins} / ${tradeStats.losses}`} />
              <StatPair label="Best trade" value={formatCurrency(tradeStats.best_pnl)} color="text-emerald-300" />
              <StatPair label="Worst trade" value={formatCurrency(tradeStats.worst_pnl)} color="text-rose-300" />
              <StatPair label="Median pnl" value={formatCurrency(tradeStats.median_pnl)}
                color={tradeStats.median_pnl >= 0 ? "text-emerald-300" : "text-rose-300"} />
              <StatPair label="Avg win" value={formatCurrency(tradeStats.avg_win_pnl)} color="text-emerald-300" />
              <StatPair label="Avg loss" value={formatCurrency(tradeStats.avg_loss_pnl)} color="text-rose-300" />
              <StatPair label="Avg win duration" value={formatDuration(tradeStats.avg_duration_win_sec)} />
              <StatPair label="Avg loss duration" value={formatDuration(tradeStats.avg_duration_loss_sec)} />
              <StatPair label="Longest win streak" value={`${tradeStats.longest_win_streak}`} />
              <StatPair label="Longest loss streak" value={`${tradeStats.longest_loss_streak}`} />
            </div>
          )}
        </div>

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
                      {t.pnl !== null ? formatCurrency(t.pnl) : "—"}
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

// ---------- Sub-components ----------

function ModeToggle({ mode, onChange }: { mode: YAxisMode; onChange: (m: YAxisMode) => void }) {
  return (
    <div className="inline-flex overflow-hidden rounded border border-gray-700 text-xs">
      <button
        onClick={() => onChange("equity")}
        className={`px-3 py-1 ${mode === "equity" ? "bg-blue-700 text-white" : "bg-gray-800 text-gray-300"}`}
      >
        Equity ($)
      </button>
      <button
        onClick={() => onChange("returns")}
        className={`px-3 py-1 ${mode === "returns" ? "bg-blue-700 text-white" : "bg-gray-800 text-gray-300"}`}
      >
        Returns (%)
      </button>
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

function StatPair({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase text-gray-500">{label}</div>
      <div className={`text-base font-semibold ${color ?? "text-white"}`}>{value}</div>
    </div>
  );
}

// ----- Equity curve (inline SVG, no recharts dep) -----

const CHART_W = 920;
const EQUITY_H = 240;
const DD_H = 120;
const PAD = { top: 16, right: 24, bottom: 28, left: 64 };

function EquityCurveChart({
  data,
  markers,
  referenceValue,
  mode,
}: {
  data: EquityChartPoint[];
  markers: TradeMarker[];
  referenceValue: number;
  mode: YAxisMode;
}) {
  if (data.length < 2) {
    return (
      <div className="py-8 text-center text-sm text-gray-500">
        {data.length === 0
          ? "No equity points"
          : "Only one equity point — need ≥2 to draw a line"}
      </div>
    );
  }

  const tMin = data[0].t;
  const tMax = data[data.length - 1].t;
  const values = data.map((d) => d.value);
  const vMin = Math.min(...values, referenceValue);
  const vMax = Math.max(...values, referenceValue);
  const vPad = (vMax - vMin) * 0.08 || 1;
  const yMin = vMin - vPad;
  const yMax = vMax + vPad;

  const w = CHART_W - PAD.left - PAD.right;
  const h = EQUITY_H - PAD.top - PAD.bottom;
  const xScale = (t: number) =>
    PAD.left + ((t - tMin) / (tMax - tMin || 1)) * w;
  const yScale = (v: number) =>
    PAD.top + (1 - (v - yMin) / (yMax - yMin || 1)) * h;

  const path = data
    .map(
      (d, i) =>
        `${i === 0 ? "M" : "L"} ${xScale(d.t).toFixed(1)} ${yScale(d.value).toFixed(1)}`,
    )
    .join(" ");

  const yTicks = Array.from(new Set([yMin, referenceValue, yMax])).sort(
    (a, b) => a - b,
  );
  const xTicks = [tMin, (tMin + tMax) / 2, tMax];

  // Clamp markers to the visible y-range so an off-axis trade doesn't draw
  // a stray dot. Trades exactly on tMin/tMax are kept; out-of-range are
  // skipped.
  const visibleMarkers = markers.filter(
    (m) => m.t >= tMin && m.t <= tMax && m.y >= yMin && m.y <= yMax,
  );

  function formatYTick(v: number): string {
    if (mode === "equity") return `$${(v / 1000).toFixed(1)}k`;
    return `${v.toFixed(1)}%`;
  }

  return (
    <svg
      viewBox={`0 0 ${CHART_W} ${EQUITY_H}`}
      preserveAspectRatio="none"
      style={{ width: "100%", height: EQUITY_H }}
      role="img"
      aria-label="Equity curve"
    >
      <line
        x1={PAD.left}
        x2={CHART_W - PAD.right}
        y1={yScale(referenceValue)}
        y2={yScale(referenceValue)}
        stroke="#6b7280"
        strokeDasharray="4 4"
        strokeWidth={1}
      />
      <path d={path} fill="none" stroke="#3b82f6" strokeWidth={2} />

      {visibleMarkers.map((m, i) => (
        <circle
          key={`mk-${i}`}
          cx={xScale(m.t)}
          cy={yScale(m.y)}
          r={4}
          fill={m.kind === "entry" ? "#10b981" : "#ef4444"}
          stroke="#0f172a"
          strokeWidth={1.5}
        >
          <title>
            {m.kind === "entry" ? "Entry " : "Exit "}
            {m.trade.symbol} {m.trade.side}
            {"\n"}
            {new Date(m.t).toLocaleString()}
            {m.trade.pnl !== null
              ? `\nPnL ${formatCurrency(m.trade.pnl)}`
              : ""}
          </title>
        </circle>
      ))}

      {yTicks.map((y, i) => (
        <g key={i}>
          <line
            x1={PAD.left - 4}
            x2={PAD.left}
            y1={yScale(y)}
            y2={yScale(y)}
            stroke="#374151"
            strokeWidth={1}
          />
          <text
            x={PAD.left - 8}
            y={yScale(y) + 4}
            textAnchor="end"
            fontSize={11}
            fill="#9ca3af"
          >
            {formatYTick(y)}
          </text>
        </g>
      ))}

      {xTicks.map((x, i) => (
        <g key={i}>
          <line
            x1={xScale(x)}
            x2={xScale(x)}
            y1={EQUITY_H - PAD.bottom}
            y2={EQUITY_H - PAD.bottom + 4}
            stroke="#374151"
            strokeWidth={1}
          />
          <text
            x={xScale(x)}
            y={EQUITY_H - PAD.bottom + 18}
            textAnchor={
              i === 0
                ? "start"
                : i === xTicks.length - 1
                  ? "end"
                  : "middle"
            }
            fontSize={11}
            fill="#9ca3af"
          >
            {new Date(x).toLocaleDateString()}
          </text>
        </g>
      ))}
    </svg>
  );
}

function DrawdownChart({ data }: { data: DrawdownPoint[] }) {
  if (data.length < 2) {
    return (
      <div className="py-4 text-center text-sm text-gray-500">
        {data.length === 0 ? "No drawdown data" : "Need ≥2 points for drawdown"}
      </div>
    );
  }

  const tMin = data[0].t;
  const tMax = data[data.length - 1].t;
  // Drawdown is always ≤ 0; force the y-domain top to 0 so the chart reads
  // "deepest at the bottom" without wasted positive headroom.
  const ddValues = data.map((d) => d.drawdown_pct);
  const yMin = Math.min(...ddValues, 0);
  const yMax = 0;
  const yPad = Math.abs(yMin) * 0.08 || 0.001;

  const w = CHART_W - PAD.left - PAD.right;
  const h = DD_H - PAD.top - PAD.bottom;
  const xScale = (t: number) =>
    PAD.left + ((t - tMin) / (tMax - tMin || 1)) * w;
  const yScale = (v: number) =>
    PAD.top + (1 - (v - (yMin - yPad)) / (yMax - (yMin - yPad) || 1)) * h;

  const linePath = data
    .map(
      (d, i) =>
        `${i === 0 ? "M" : "L"} ${xScale(d.t).toFixed(1)} ${yScale(d.drawdown_pct).toFixed(1)}`,
    )
    .join(" ");
  // Filled area: line path + close to y=0 baseline.
  const areaPath = [
    linePath,
    `L ${xScale(tMax).toFixed(1)} ${yScale(0).toFixed(1)}`,
    `L ${xScale(tMin).toFixed(1)} ${yScale(0).toFixed(1)}`,
    "Z",
  ].join(" ");

  const yTicks = [yMin, yMin / 2, 0];
  const xTicks = [tMin, (tMin + tMax) / 2, tMax];

  return (
    <svg
      viewBox={`0 0 ${CHART_W} ${DD_H}`}
      preserveAspectRatio="none"
      style={{ width: "100%", height: DD_H }}
      role="img"
      aria-label="Drawdown"
    >
      <line
        x1={PAD.left}
        x2={CHART_W - PAD.right}
        y1={yScale(0)}
        y2={yScale(0)}
        stroke="#6b7280"
        strokeDasharray="4 4"
        strokeWidth={1}
      />
      <path d={areaPath} fill="#ef4444" fillOpacity={0.25} stroke="none" />
      <path d={linePath} fill="none" stroke="#ef4444" strokeWidth={1.5} />

      {yTicks.map((y, i) => (
        <g key={i}>
          <line
            x1={PAD.left - 4}
            x2={PAD.left}
            y1={yScale(y)}
            y2={yScale(y)}
            stroke="#374151"
            strokeWidth={1}
          />
          <text
            x={PAD.left - 8}
            y={yScale(y) + 4}
            textAnchor="end"
            fontSize={11}
            fill="#9ca3af"
          >
            {`${(y * 100).toFixed(1)}%`}
          </text>
        </g>
      ))}

      {xTicks.map((x, i) => (
        <g key={i}>
          <line
            x1={xScale(x)}
            x2={xScale(x)}
            y1={DD_H - PAD.bottom}
            y2={DD_H - PAD.bottom + 4}
            stroke="#374151"
            strokeWidth={1}
          />
          <text
            x={xScale(x)}
            y={DD_H - PAD.bottom + 18}
            textAnchor={
              i === 0
                ? "start"
                : i === xTicks.length - 1
                  ? "end"
                  : "middle"
            }
            fontSize={11}
            fill="#9ca3af"
          >
            {new Date(x).toLocaleDateString()}
          </text>
        </g>
      ))}
    </svg>
  );
}
