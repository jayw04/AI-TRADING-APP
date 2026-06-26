import { useCallback, useEffect, useState } from "react";
import { ApiError } from "@/api/client";
import { rangeInsightApi, type RangeCandidate } from "@/api/rangeInsight";
import { strategyTemplatesApi } from "@/api/strategyTemplates";

/**
 * P8 §5a — Range Candidates panel (Strategies page). Ranks a universe by range-trading
 * suitability — NORMALIZED range (`atr20_pct`, so price level doesn't distort it) weighted
 * by how range-bound each name is — so the user can pick which symbol to range-trade today
 * rather than being stuck on one fixed ticker. "Use" applies the range template to the
 * picked symbol (creates an IDLE range strategy). Descriptive, not predictive.
 */

const CLASS_LABEL: Record<string, string> = {
  range_bound: "Range-bound",
  trending: "Trending",
  mixed: "Mixed",
};
const CLASS_STYLE: Record<string, string> = {
  range_bound: "bg-emerald-900/60 text-emerald-200",
  trending: "bg-amber-900/60 text-amber-200",
  mixed: "bg-neutral-800 text-neutral-300",
};

function pct(n: number | null | undefined): string {
  return n === null || n === undefined ? "—" : `${(n * 100).toFixed(1)}%`;
}
function fmt(n: number | null | undefined): string {
  return n === null || n === undefined ? "—" : n.toFixed(2);
}

interface Props {
  /** Called after a candidate is adopted (parent reloads its strategy list). */
  onApplied?: (symbol: string) => void;
}

export default function RangeCandidatesPanel({ onApplied }: Props) {
  const [candidates, setCandidates] = useState<RangeCandidate[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [applying, setApplying] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await rangeInsightApi.candidates();
      setCandidates(resp.candidates);
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleUse(symbol: string) {
    if (
      !confirm(
        `Apply the range template to ${symbol}? This creates an IDLE "Range Trader ${symbol}" ` +
          `strategy with params prefilled from its Range Insight — you then Start it (24h cooldown).`,
      )
    )
      return;
    setApplying(symbol);
    try {
      await strategyTemplatesApi.applyRange(symbol);
      onApplied?.(symbol);
      alert(`Created an IDLE "Range Trader ${symbol}". Start it from the list when ready.`);
    } catch (e) {
      if (e instanceof ApiError) alert(`Apply failed: ${JSON.stringify(e.body)}`);
      else alert(`Apply failed: ${e}`);
    } finally {
      setApplying(null);
    }
  }

  return (
    <div className="rounded border border-gray-800 bg-gray-900/40">
      <div className="flex items-center justify-between border-b border-gray-800 px-3 py-2">
        <div>
          <h2 className="text-sm font-semibold text-white">Range candidates — pick what to trade today</h2>
          <p className="text-[11px] text-gray-500">
            Ranked by normalized range (ATR%) × how range-bound — not raw dollars. Descriptive, not a forecast.
          </p>
        </div>
        <button
          onClick={load}
          className="rounded bg-gray-700 px-2 py-1 text-xs text-gray-200 hover:bg-gray-600"
        >
          Refresh
        </button>
      </div>

      {error && (
        <div className="m-2 rounded border border-red-700 bg-red-900/40 p-2 text-xs text-red-200">
          {error}
        </div>
      )}
      {loading && candidates.length === 0 ? (
        <div className="p-3 text-xs text-gray-500">Loading candidates…</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-gray-800/60 text-[11px] uppercase tracking-wider text-gray-400">
              <tr>
                <th className="px-3 py-1.5">#</th>
                <th className="px-3 py-1.5">Symbol</th>
                <th className="px-3 py-1.5 text-right">ATR%</th>
                <th
                  className="px-3 py-1.5 text-right"
                  title="Range Efficiency = 1 − Kaufman ER (higher = more oscillating = better)"
                >
                  Osc
                </th>
                <th className="px-3 py-1.5">Behavior</th>
                <th className="px-3 py-1.5 text-right">Range ($)</th>
                <th className="px-3 py-1.5"></th>
              </tr>
            </thead>
            <tbody>
              {candidates.map((c) => (
                <tr
                  key={c.symbol}
                  className={`border-t border-gray-800/60 ${c.suitable ? "" : "opacity-60"}`}
                >
                  <td className="px-3 py-1.5 font-mono text-gray-500">{c.rank}</td>
                  <td className="px-3 py-1.5 font-mono font-semibold text-gray-100">{c.symbol}</td>
                  <td className="px-3 py-1.5 text-right font-mono text-gray-200">{pct(c.atr20_pct)}</td>
                  <td className="px-3 py-1.5 text-right font-mono text-gray-400">{pct(c.oscillation)}</td>
                  <td className="px-3 py-1.5">
                    <span
                      className={`rounded px-1.5 py-0.5 text-[11px] ${
                        CLASS_STYLE[c.classification ?? ""] ?? "bg-neutral-800 text-neutral-300"
                      }`}
                    >
                      {CLASS_LABEL[c.classification ?? ""] ?? "—"}
                    </span>
                  </td>
                  <td className="px-3 py-1.5 text-right font-mono text-gray-400">{fmt(c.intraday_range)}</td>
                  <td className="px-3 py-1.5 text-right">
                    <button
                      onClick={() => handleUse(c.symbol)}
                      disabled={applying !== null || c.status !== "ok"}
                      className="rounded bg-blue-700 px-2 py-0.5 text-xs font-semibold text-white hover:bg-blue-600 disabled:opacity-40"
                    >
                      {applying === c.symbol ? "Applying…" : "Use"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
