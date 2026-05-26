import { useMemo } from "react";
import type { BacktestResult } from "@/api/types";
import {
  formatPct,
  formatNumber,
  formatCurrency,
  formatDuration,
} from "@/components/strategies/formatters";

interface Props {
  result: BacktestResult;
  onClose: () => void;
}

export function BacktestResultsView({ result, onClose }: Props) {
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

        <div className="mb-4 rounded border border-gray-800 bg-gray-900 p-3">
          <div className="mb-1 text-sm font-semibold text-gray-300">Equity curve</div>
          <EquityCurveChart
            points={result.equity_curve}
            startingEquity={result.metrics.starting_equity}
          />
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

// ----- Equity curve (inline SVG, no recharts dep) -----

interface CurveProps {
  points: { t: string; equity: number }[];
  startingEquity: number;
}

const CHART_W = 880;
const CHART_H = 240;
const PAD = { top: 16, right: 24, bottom: 28, left: 64 };

function EquityCurveChart({ points, startingEquity }: CurveProps) {
  const data = useMemo(
    () =>
      points.map((p) => ({
        t: new Date(p.t).getTime(),
        equity: p.equity,
      })),
    [points],
  );

  if (data.length < 2) {
    return (
      <div className="py-8 text-center text-sm text-gray-500">
        {data.length === 0 ? "No equity points" : "Only one equity point — need ≥2 to draw a line"}
      </div>
    );
  }

  const tMin = data[0].t;
  const tMax = data[data.length - 1].t;
  const eValues = data.map((d) => d.equity);
  const eMin = Math.min(...eValues, startingEquity);
  const eMax = Math.max(...eValues, startingEquity);
  const ePad = (eMax - eMin) * 0.08 || 1;
  const yMin = eMin - ePad;
  const yMax = eMax + ePad;

  const w = CHART_W - PAD.left - PAD.right;
  const h = CHART_H - PAD.top - PAD.bottom;
  const xScale = (t: number) => PAD.left + ((t - tMin) / (tMax - tMin || 1)) * w;
  const yScale = (e: number) => PAD.top + (1 - (e - yMin) / (yMax - yMin || 1)) * h;

  const path = data
    .map((d, i) => `${i === 0 ? "M" : "L"} ${xScale(d.t).toFixed(1)} ${yScale(d.equity).toFixed(1)}`)
    .join(" ");

  // Y-axis ticks at min / starting / max
  const yTicks = Array.from(new Set([yMin, startingEquity, yMax])).sort((a, b) => a - b);
  // X-axis ticks: first, middle, last
  const xTicks = [tMin, (tMin + tMax) / 2, tMax];

  return (
    <svg
      viewBox={`0 0 ${CHART_W} ${CHART_H}`}
      preserveAspectRatio="none"
      style={{ width: "100%", height: 240 }}
      role="img"
      aria-label="Equity curve"
    >
      <line
        x1={PAD.left} x2={CHART_W - PAD.right}
        y1={yScale(startingEquity)} y2={yScale(startingEquity)}
        stroke="#6b7280" strokeDasharray="4 4" strokeWidth={1}
      />
      <path d={path} fill="none" stroke="#3b82f6" strokeWidth={2} />

      {yTicks.map((y, i) => (
        <g key={i}>
          <line
            x1={PAD.left - 4} x2={PAD.left}
            y1={yScale(y)} y2={yScale(y)}
            stroke="#374151" strokeWidth={1}
          />
          <text
            x={PAD.left - 8} y={yScale(y) + 4}
            textAnchor="end" fontSize={11} fill="#9ca3af"
          >
            ${(y / 1000).toFixed(1)}k
          </text>
        </g>
      ))}

      {xTicks.map((x, i) => (
        <g key={i}>
          <line
            x1={xScale(x)} x2={xScale(x)}
            y1={CHART_H - PAD.bottom} y2={CHART_H - PAD.bottom + 4}
            stroke="#374151" strokeWidth={1}
          />
          <text
            x={xScale(x)} y={CHART_H - PAD.bottom + 18}
            textAnchor={i === 0 ? "start" : i === xTicks.length - 1 ? "end" : "middle"}
            fontSize={11} fill="#9ca3af"
          >
            {new Date(x).toLocaleDateString()}
          </text>
        </g>
      ))}
    </svg>
  );
}
