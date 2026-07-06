import { useQuery } from "@tanstack/react-query";
import { rangeLevelsApi, type RangeLevelRow } from "@/api/rangeLevels";
import { formatMoney, formatQty } from "@/lib/format";

const STATUS_STYLE: Record<string, string> = {
  holding: "bg-sky-900/50 text-sky-300",
  at_buy: "bg-emerald-900/50 text-emerald-300",
  at_sell: "bg-amber-900/50 text-amber-300",
  below_stop: "bg-rose-900/50 text-rose-300",
  in_range: "bg-neutral-800 text-neutral-400",
  forming: "bg-neutral-800 text-neutral-500",
  levels_set: "bg-neutral-800 text-neutral-400",
};

const STATUS_LABEL: Record<string, string> = {
  holding: "Holding",
  at_buy: "At buy ↧",
  at_sell: "At sell ↥",
  below_stop: "Below stop!",
  in_range: "In range",
  forming: "Forming…",
  levels_set: "Levels set",
};

function LevelCell({ value }: { value: number | null }) {
  return (
    <td className="px-3 py-2 text-right font-mono">
      {value == null ? <span className="text-neutral-600">—</span> : formatMoney(value)}
    </td>
  );
}

function Row({ r }: { r: RangeLevelRow }) {
  // Highlight the current price when it has crossed a trigger while flat.
  const cur = r.current_price;
  const curClass =
    cur != null && r.position_qty === 0 && r.buy != null && cur <= r.buy
      ? "text-emerald-400"
      : cur != null && r.position_qty === 0 && r.sell != null && cur >= r.sell
        ? "text-amber-400"
        : "text-neutral-200";
  return (
    <tr className="border-t border-neutral-800">
      <td className="px-3 py-2 font-medium text-neutral-100">{r.symbol}</td>
      <LevelCell value={r.buy} />
      <LevelCell value={r.sell} />
      <LevelCell value={r.stop} />
      <td className={`px-3 py-2 text-right font-mono ${curClass}`}>
        {r.current_price == null ? "—" : formatMoney(r.current_price)}
      </td>
      <td className="px-3 py-2 text-right font-mono text-neutral-300">
        {r.position_qty ? formatQty(r.position_qty) : <span className="text-neutral-600">flat</span>}
      </td>
      <td className="px-3 py-2">
        <span
          className={`rounded px-1.5 py-0.5 text-[11px] ${STATUS_STYLE[r.status] ?? "bg-neutral-800 text-neutral-400"}`}
        >
          {STATUS_LABEL[r.status] ?? r.status}
        </span>
      </td>
    </tr>
  );
}

/** Live buy/sell/stop levels per range symbol — for monitoring that triggers fire. */
export default function RangeLevelsPanel({ strategyId }: { strategyId?: number }) {
  const query = useQuery({
    queryKey: ["range-levels", strategyId ?? "active"],
    queryFn: () => rangeLevelsApi.list(strategyId),
    refetchInterval: 15_000,
  });

  const rows = query.data?.rows ?? [];
  if (!query.isLoading && !query.isError && rows.length === 0) {
    return null; // not a range strategy / nothing to show
  }

  return (
    <div className="rounded-lg bg-neutral-900 border border-neutral-800 overflow-hidden">
      <div className="flex items-baseline justify-between px-3 py-2 border-b border-neutral-800">
        <h3 className="text-sm font-semibold text-neutral-100">Range levels</h3>
        <span className="text-[11px] text-neutral-500">
          buy = support · sell = resistance · updates 15s
        </span>
      </div>
      <table className="w-full text-sm">
        <thead className="bg-neutral-950 text-[11px] uppercase tracking-wider text-neutral-500">
          <tr>
            <th className="text-left px-3 py-2">Symbol</th>
            <th className="text-right px-3 py-2">Buy</th>
            <th className="text-right px-3 py-2">Sell</th>
            <th className="text-right px-3 py-2">Stop</th>
            <th className="text-right px-3 py-2">Current</th>
            <th className="text-right px-3 py-2">Position</th>
            <th className="text-left px-3 py-2">Status</th>
          </tr>
        </thead>
        <tbody>
          {query.isLoading && (
            <tr>
              <td colSpan={7} className="px-3 py-4 text-center text-neutral-500">Loading…</td>
            </tr>
          )}
          {query.isError && (
            <tr>
              <td colSpan={7} className="px-3 py-4 text-center text-rose-400">Failed to load levels.</td>
            </tr>
          )}
          {rows.map((r) => (
            <Row key={r.symbol} r={r} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
