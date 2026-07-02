import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { journalApi, type JournalEntry } from "@/api/journal";
import { formatMoney, formatQty, formatTimestamp } from "@/lib/format";

function sideClassName(side: string): string {
  return side.toLowerCase() === "buy" ? "text-emerald-400" : "text-rose-400";
}

/** One row: trade details + an inline note that saves on blur when changed. */
function JournalRow({ entry }: { entry: JournalEntry }) {
  const queryClient = useQueryClient();
  const [note, setNote] = useState(entry.note);

  // Keep local state in sync if the server value changes (e.g. after refetch).
  useEffect(() => setNote(entry.note), [entry.note]);

  const save = useMutation({
    mutationFn: (value: string) => journalApi.saveNote(entry.order_id, value),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["journal"] }),
  });

  const dirty = note !== entry.note;

  return (
    <tr className="border-t border-neutral-800 align-top">
      <td className="px-3 py-2 text-neutral-400 whitespace-nowrap">
        {formatTimestamp(entry.filled_at)}
      </td>
      <td className="px-3 py-2 font-medium text-neutral-100">{entry.symbol}</td>
      <td className={`px-3 py-2 font-medium uppercase ${sideClassName(entry.side)}`}>
        {entry.side}
      </td>
      <td className="px-3 py-2 text-right font-mono">{formatQty(entry.qty)}</td>
      <td className="px-3 py-2 text-right font-mono">
        {formatMoney(entry.avg_fill_price)}
      </td>
      <td className="px-3 py-2 text-right font-mono">{formatMoney(entry.value)}</td>
      <td className="px-3 py-2 text-neutral-400 whitespace-nowrap">
        {entry.source_label}
      </td>
      <td className="px-3 py-2 w-[34%]">
        <div className="flex items-start gap-2">
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            onBlur={() => {
              if (dirty) save.mutate(note);
            }}
            rows={1}
            placeholder="Why this trade? Reflection…"
            className="w-full resize-y rounded border border-neutral-800 bg-neutral-950 px-2 py-1 text-sm text-neutral-200 focus:border-neutral-600 focus:outline-none"
          />
          {dirty && !save.isPending && (
            <span className="mt-1 text-[10px] uppercase text-amber-400">unsaved</span>
          )}
          {save.isPending && (
            <span className="mt-1 text-[10px] uppercase text-neutral-500">saving…</span>
          )}
        </div>
      </td>
    </tr>
  );
}

export default function Journal() {
  const query = useQuery({
    queryKey: ["journal"],
    queryFn: journalApi.list,
    refetchInterval: 15_000,
  });

  const items = query.data?.items ?? [];

  return (
    <div className="grid gap-4">
      <div className="flex items-baseline justify-between">
        <h2 className="text-lg font-semibold text-neutral-100">Journal</h2>
        <span className="text-xs text-neutral-500">
          {items.length} trade{items.length === 1 ? "" : "s"} · notes save on blur
        </span>
      </div>

      <div className="rounded-lg bg-neutral-900 border border-neutral-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-neutral-950 text-[11px] uppercase tracking-wider text-neutral-500">
            <tr>
              <th className="text-left px-3 py-2">Date</th>
              <th className="text-left px-3 py-2">Symbol</th>
              <th className="text-left px-3 py-2">Side</th>
              <th className="text-right px-3 py-2">Qty</th>
              <th className="text-right px-3 py-2">Fill price</th>
              <th className="text-right px-3 py-2">Value</th>
              <th className="text-left px-3 py-2">Source</th>
              <th className="text-left px-3 py-2">Note</th>
            </tr>
          </thead>
          <tbody>
            {query.isLoading && (
              <tr>
                <td colSpan={8} className="px-3 py-4 text-center text-neutral-500">
                  Loading…
                </td>
              </tr>
            )}
            {query.isError && (
              <tr>
                <td colSpan={8} className="px-3 py-4 text-center text-rose-400">
                  Failed to load the journal.
                </td>
              </tr>
            )}
            {!query.isLoading && !query.isError && items.length === 0 && (
              <tr>
                <td colSpan={8} className="px-3 py-6 text-center text-neutral-500">
                  No trades yet. Filled orders appear here — add a note to each to
                  record your rationale.
                </td>
              </tr>
            )}
            {items.map((entry) => (
              <JournalRow key={entry.order_id} entry={entry} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
