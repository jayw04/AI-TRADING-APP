import { useCallback, useEffect, useState } from "react";
import { strategiesApi } from "@/api/strategies";
import type { Signal, SignalTypeT } from "@/api/types";
import { useWorkbenchSocket } from "@/hooks/useWorkbenchSocket";

interface Props {
  strategyId: number;
}

const TYPES: SignalTypeT[] = ["entry", "exit", "flat", "info", "agent_action", "pine_alert"];

export function SignalsTab({ strategyId }: Props) {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [filter, setFilter] = useState<SignalTypeT | "all">("all");
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await strategiesApi.listSignals(strategyId, 200);
      setSignals(resp.items);
    } finally {
      setLoading(false);
    }
  }, [strategyId]);

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load]);

  useWorkbenchSocket(["signals"], (msg) => {
    if (msg.payload.strategy_id === strategyId) {
      load();
    }
  });

  const filtered = filter === "all" ? signals : signals.filter((s) => s.type === filter);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <span className="text-sm text-gray-400">Filter:</span>
        <button onClick={() => setFilter("all")}
          className={`rounded px-2 py-1 text-xs ${filter === "all" ? "bg-blue-700 text-white" : "bg-gray-800 text-gray-300"}`}>
          All
        </button>
        {TYPES.map((t) => (
          <button key={t} onClick={() => setFilter(t)}
            className={`rounded px-2 py-1 text-xs ${filter === t ? "bg-blue-700 text-white" : "bg-gray-800 text-gray-300"}`}>
            {t}
          </button>
        ))}
        <button onClick={load} className="ml-auto rounded bg-gray-700 px-2 py-1 text-xs text-gray-200">
          {loading ? "…" : "Refresh"}
        </button>
      </div>

      <div className="rounded border border-gray-800">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-800 text-gray-300">
            <tr>
              <th className="px-3 py-2">Time</th>
              <th className="px-3 py-2">Symbol</th>
              <th className="px-3 py-2">Type</th>
              <th className="px-3 py-2">Reason</th>
              <th className="px-3 py-2">Payload</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr><td colSpan={5} className="px-3 py-4 text-center text-gray-500">No signals</td></tr>
            )}
            {filtered.map((s) => (
              <tr key={s.id} className="border-t border-gray-800">
                <td className="px-3 py-2 text-xs text-gray-400">
                  {new Date(s.received_at).toLocaleString()}
                </td>
                <td className="px-3 py-2 font-semibold">{s.symbol}</td>
                <td className="px-3 py-2">
                  <span className={
                    s.type === "entry" ? "text-emerald-400" :
                    s.type === "exit" ? "text-rose-400" :
                    s.type === "info" ? "text-gray-400" : "text-blue-400"
                  }>
                    {s.type}
                  </span>
                </td>
                <td className="px-3 py-2 text-gray-300">
                  {(s.payload as { reason?: string })?.reason ?? "—"}
                </td>
                <td className="px-3 py-2 font-mono text-xs text-gray-500">
                  {JSON.stringify(s.payload).slice(0, 80)}
                  {JSON.stringify(s.payload).length > 80 ? "…" : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
