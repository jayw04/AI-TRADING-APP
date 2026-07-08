import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { rangeHistoryApi, type RangeExecutionRow } from "@/api/rangeHistory";
import { formatMoney } from "@/lib/format";

function isoDaysAgo(n: number): string {
  return new Date(Date.now() - n * 86_400_000).toISOString().slice(0, 10);
}

/** (fill − low) / (high − low): buy 0.00 = bought the low (ideal), sell 1.00 = sold the high. */
function placement(price: string | null, low: string | null, high: string | null): string {
  if (price == null || low == null || high == null) return "—";
  const p = Number(price);
  const lo = Number(low);
  const hi = Number(high);
  if (!Number.isFinite(p) || !Number.isFinite(lo) || !Number.isFinite(hi) || hi <= lo) return "—";
  return ((p - lo) / (hi - lo)).toFixed(2);
}

function Row({ r }: { r: RangeExecutionRow }) {
  return (
    <tr className="border-t border-neutral-800">
      <td className="px-3 py-2 text-neutral-300">{r.et_date}</td>
      <td className="px-3 py-2 font-medium text-neutral-100">{r.symbol}</td>
      <td className="px-3 py-2 text-right font-mono">{formatMoney(r.avg_buy_price)}</td>
      <td className="px-3 py-2 text-right font-mono">{formatMoney(r.avg_sell_price)}</td>
      <td className="px-3 py-2 text-right font-mono">{formatMoney(r.daily_low)}</td>
      <td className="px-3 py-2 text-right font-mono">{formatMoney(r.daily_high)}</td>
      <td className="px-3 py-2 text-right font-mono text-neutral-400">
        {placement(r.avg_buy_price, r.daily_low, r.daily_high)}
      </td>
      <td className="px-3 py-2 text-right font-mono text-neutral-400">
        {placement(r.avg_sell_price, r.daily_low, r.daily_high)}
      </td>
    </tr>
  );
}

/** Modal: pick a date range, see the Range Trader's daily buy/sell vs. each stock's daily high/low. */
export function RangeTraderHistoryModal({ onClose }: { onClose: () => void }) {
  const [from, setFrom] = useState(isoDaysAgo(14));
  const [to, setTo] = useState(isoDaysAgo(0));
  const [submitted, setSubmitted] = useState<{ from: string; to: string } | null>(null);

  const query = useQuery({
    queryKey: ["range-history", submitted?.from, submitted?.to],
    queryFn: () => rangeHistoryApi.list(submitted!),
    enabled: submitted != null,
  });
  const rows = query.data?.items ?? [];
  const empty = submitted != null && !query.isLoading && !query.isError && rows.length === 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
      <div className="w-[54rem] max-h-[90vh] space-y-4 overflow-y-auto rounded-lg border border-neutral-700 bg-neutral-950 p-5">
        <div className="flex items-baseline justify-between">
          <h2 className="text-lg font-semibold text-neutral-100">
            Range Trader — buy/sell vs. daily high/low
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="text-neutral-400 hover:text-neutral-200"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <div className="flex items-end gap-3">
          <label className="text-sm text-neutral-300">
            From
            <input
              type="date"
              value={from}
              onChange={(e) => setFrom(e.target.value)}
              className="mt-1 block rounded bg-neutral-800 px-2 py-1 text-white"
            />
          </label>
          <label className="text-sm text-neutral-300">
            To
            <input
              type="date"
              value={to}
              onChange={(e) => setTo(e.target.value)}
              className="mt-1 block rounded bg-neutral-800 px-2 py-1 text-white"
            />
          </label>
          <button
            type="button"
            onClick={() => setSubmitted({ from, to })}
            className="rounded bg-blue-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-600"
          >
            Show
          </button>
        </div>

        <p className="text-[11px] text-neutral-500">
          Placement = (fill − low) / (high − low): <b>buy 0.00</b> = bought the low (ideal fade),{" "}
          <b>sell 1.00</b> = sold the high. Days with no trade show high/low only; today appears after
          its 16:00 ET close.
        </p>

        <table className="w-full text-sm">
          <thead className="bg-neutral-900 text-[11px] uppercase tracking-wider text-neutral-500">
            <tr>
              <th className="px-3 py-2 text-left">Date</th>
              <th className="px-3 py-2 text-left">Symbol</th>
              <th className="px-3 py-2 text-right">Buy</th>
              <th className="px-3 py-2 text-right">Sell</th>
              <th className="px-3 py-2 text-right">Low</th>
              <th className="px-3 py-2 text-right">High</th>
              <th className="px-3 py-2 text-right">Buy pl.</th>
              <th className="px-3 py-2 text-right">Sell pl.</th>
            </tr>
          </thead>
          <tbody>
            {submitted == null && (
              <tr>
                <td colSpan={8} className="px-3 py-6 text-center text-neutral-500">
                  Pick a date range and click Show.
                </td>
              </tr>
            )}
            {query.isLoading && (
              <tr>
                <td colSpan={8} className="px-3 py-6 text-center text-neutral-500">
                  Loading…
                </td>
              </tr>
            )}
            {query.isError && (
              <tr>
                <td colSpan={8} className="px-3 py-6 text-center text-rose-400">
                  Failed to load.
                </td>
              </tr>
            )}
            {empty && (
              <tr>
                <td colSpan={8} className="px-3 py-6 text-center text-neutral-500">
                  No records in this window.
                </td>
              </tr>
            )}
            {rows.map((r) => (
              <Row key={`${r.et_date}-${r.symbol}`} r={r} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
