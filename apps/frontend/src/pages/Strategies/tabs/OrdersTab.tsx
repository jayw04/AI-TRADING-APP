import { useCallback, useEffect, useState } from "react";
import { ordersApi } from "@/api/orders";
import type { Order } from "@/api/types";

interface Props {
  strategyId: number;
}

export function OrdersTab({ strategyId }: Props) {
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // No backend filter by source_id; pull recent and filter client-side.
      // P4 polish: add a source_id query param.
      const resp = await ordersApi.list("all");
      setOrders(resp.items.filter(
        (o) => o.source_type === "strategy" && o.source_id === String(strategyId),
      ));
    } finally {
      setLoading(false);
    }
  }, [strategyId]);

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load]);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm text-gray-400">
          Orders attributed to this strategy
        </span>
        <button onClick={load} className="rounded bg-gray-700 px-2 py-1 text-xs text-gray-200">
          {loading ? "…" : "Refresh"}
        </button>
      </div>

      <div className="rounded border border-gray-800">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-800 text-gray-300">
            <tr>
              <th className="px-3 py-2">Time</th>
              <th className="px-3 py-2">Symbol</th>
              <th className="px-3 py-2">Side</th>
              <th className="px-3 py-2 text-right">Qty</th>
              <th className="px-3 py-2">Type</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Reason</th>
            </tr>
          </thead>
          <tbody>
            {orders.length === 0 && (
              <tr><td colSpan={7} className="px-3 py-4 text-center text-gray-500">No strategy orders</td></tr>
            )}
            {orders.map((o) => (
              <tr key={o.id ?? `${o.client_order_id}-${o.created_at}`} className="border-t border-gray-800">
                <td className="px-3 py-2 text-xs text-gray-400">{new Date(o.created_at).toLocaleString()}</td>
                <td className="px-3 py-2 font-semibold">{o.symbol}</td>
                <td className={`px-3 py-2 ${o.side === "buy" ? "text-emerald-400" : "text-rose-400"}`}>
                  {o.side.toUpperCase()}
                </td>
                <td className="px-3 py-2 text-right">{o.qty}</td>
                <td className="px-3 py-2">{o.type}</td>
                <td className="px-3 py-2">{o.status}</td>
                <td className="px-3 py-2 text-xs text-gray-400">{o.rejection_reason ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
