import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { positionsApi } from "@/api/positions";
import type { Position } from "@/api/types";
import { ApiError } from "@/api/client";
import {
  formatMoney,
  formatPercent,
  formatQty,
  formatTimestamp,
  pnlClassName,
} from "@/lib/format";

export default function PositionsPage() {
  const query = useQuery({
    queryKey: ["positions"],
    queryFn: positionsApi.list,
    refetchInterval: 5_000,
  });

  return (
    <div className="grid gap-4">
      <h2 className="text-lg font-semibold text-neutral-100">Positions</h2>

      <div className="rounded-lg bg-neutral-900 border border-neutral-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-neutral-950 text-[11px] uppercase tracking-wider text-neutral-500">
            <tr>
              <th className="text-left px-3 py-2">Symbol</th>
              <th className="text-left px-3 py-2">Side</th>
              <th className="text-right px-3 py-2">Qty</th>
              <th className="text-right px-3 py-2">Avg entry</th>
              <th className="text-right px-3 py-2">Market value</th>
              <th className="text-right px-3 py-2">Unrealized P&amp;L</th>
              <th className="text-right px-3 py-2">P&amp;L %</th>
              <th className="text-right px-3 py-2">Updated</th>
              <th className="text-right px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {query.isLoading && (
              <tr>
                <td colSpan={9} className="px-3 py-4 text-center text-neutral-500">
                  Loading…
                </td>
              </tr>
            )}
            {query.error && (
              <tr>
                <td colSpan={9} className="px-3 py-4 text-center text-rose-400">
                  {(query.error as Error).message}
                </td>
              </tr>
            )}
            {query.data?.items.length === 0 && (
              <tr>
                <td colSpan={9} className="px-3 py-6 text-center text-neutral-500">
                  No open positions.
                </td>
              </tr>
            )}
            {query.data?.items.map((p) => <PositionRow key={p.id} position={p} />)}
          </tbody>
          {query.data && query.data.items.length > 0 && (
            <tfoot className="bg-neutral-950 text-xs text-neutral-300">
              <tr className="border-t border-neutral-800">
                <td colSpan={4} className="px-3 py-2 text-right text-neutral-500 uppercase tracking-wider text-[11px]">
                  Totals
                </td>
                <td className="px-3 py-2 text-right font-mono">
                  Gross {formatMoney(query.data.gross_exposure)}
                </td>
                <td className="px-3 py-2 text-right font-mono">
                  <span className={pnlClassName(query.data.total_unrealized_pl)}>
                    {formatMoney(query.data.total_unrealized_pl)}
                  </span>
                </td>
                <td colSpan={3} className="px-3 py-2 text-right font-mono">
                  Net {formatMoney(query.data.net_exposure)}
                </td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    </div>
  );
}

function PositionRow({ position }: { position: Position }) {
  const queryClient = useQueryClient();
  const closeM = useMutation({
    mutationFn: () => positionsApi.close(position.symbol),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["positions"] });
      void queryClient.invalidateQueries({ queryKey: ["orders"] });
    },
  });

  const sideCls =
    position.side === "long"
      ? "bg-emerald-900/40 text-emerald-300 border-emerald-800/60"
      : position.side === "short"
        ? "bg-rose-900/40 text-rose-300 border-rose-800/60"
        : "bg-neutral-800 text-neutral-300 border-neutral-700";

  return (
    <tr className="border-t border-neutral-800">
      <td className="px-3 py-2 font-semibold text-neutral-100">{position.symbol}</td>
      <td className="px-3 py-2">
        <span
          className={`inline-flex rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${sideCls}`}
        >
          {position.side ?? "—"}
        </span>
      </td>
      <td className="px-3 py-2 text-right font-mono">{formatQty(position.qty)}</td>
      <td className="px-3 py-2 text-right font-mono text-neutral-300">
        {formatMoney(position.avg_entry_price)}
      </td>
      <td className="px-3 py-2 text-right font-mono text-neutral-200">
        {formatMoney(position.market_value)}
      </td>
      <td className={`px-3 py-2 text-right font-mono ${pnlClassName(position.unrealized_pl)}`}>
        {formatMoney(position.unrealized_pl)}
      </td>
      <td className={`px-3 py-2 text-right font-mono ${pnlClassName(position.unrealized_pl)}`}>
        {formatPercent(position.unrealized_plpc)}
      </td>
      <td className="px-3 py-2 text-right font-mono text-[11px] text-neutral-500">
        {formatTimestamp(position.updated_at)}
      </td>
      <td className="px-3 py-2 text-right">
        <button
          type="button"
          onClick={() => {
            if (closeM.isPending) return;
            const confirmed = window.confirm(
              `Close position in ${position.symbol} (${position.qty} shares)?`,
            );
            if (confirmed) closeM.mutate();
          }}
          disabled={closeM.isPending}
          className="text-rose-400 hover:text-rose-300 text-xs disabled:opacity-50"
        >
          {closeM.isPending ? "Closing…" : "Close"}
        </button>
        {closeM.error && (
          <p className="text-[10px] text-rose-300 mt-1">
            {closeM.error instanceof ApiError && typeof closeM.error.body === "object"
              ? String(
                  (closeM.error.body as { detail?: unknown })?.detail ??
                    closeM.error.message,
                )
              : (closeM.error as Error).message}
          </p>
        )}
      </td>
    </tr>
  );
}
