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
    } catch {
      /* ignore */
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
