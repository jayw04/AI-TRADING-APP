import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ordersApi, type OrderListFilter } from "@/api/orders";
import type { Order, OrderSide, OrderStatus } from "@/api/types";
import { TERMINAL_ORDER_STATUSES } from "@/api/types";
import { ApiError } from "@/api/client";
import { describeReasons } from "@/lib/risk-reasons";
import { formatMoney, formatQty, formatTimestamp } from "@/lib/format";

type OrdersView = OrderListFilter | "today";

export default function OrdersPage() {
  // Default to "Today" so the first thing a user sees is the day's executed trades.
  const [view, setView] = useState<OrdersView>("today");
  const [selectedId, setSelectedId] = useState<number | null>(null);

  return (
    <div className="grid gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-neutral-100">Orders</h2>
        <Tabs value={view} onChange={setView} />
      </div>

      {view === "today" ? (
        <TodayActivity onSelect={setSelectedId} />
      ) : (
        <OrdersTable filter={view} onSelect={setSelectedId} />
      )}

      {selectedId !== null && (
        <OrderDrawer orderId={selectedId} onClose={() => setSelectedId(null)} />
      )}
    </div>
  );
}

function OrdersTable({
  filter,
  onSelect,
}: {
  filter: OrderListFilter;
  onSelect: (id: number) => void;
}) {
  const query = useQuery({
    queryKey: ["orders", filter],
    queryFn: () => ordersApi.list({ filter }),
    refetchInterval: 5_000,
  });

  return (
    <div className="rounded-lg bg-neutral-900 border border-neutral-800 overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-neutral-950 text-[11px] uppercase tracking-wider text-neutral-500">
          <tr>
            <th className="text-left px-3 py-2">Created</th>
            <th className="text-left px-3 py-2">Symbol</th>
            <th className="text-left px-3 py-2">Side</th>
            <th className="text-right px-3 py-2">Qty</th>
            <th className="text-left px-3 py-2">Type</th>
            <th className="text-right px-3 py-2">Limit / Stop</th>
            <th className="text-right px-3 py-2">Avg Fill</th>
            <th className="text-left px-3 py-2">Status</th>
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
                No {filter === "all" ? "" : filter} orders.
              </td>
            </tr>
          )}
          {query.data?.items.map((o) => (
            <OrderRow
              key={o.id ?? `eph-${o.created_at}-${o.symbol}`}
              order={o}
              onSelect={() => o.id !== null && onSelect(o.id)}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

interface FillRow {
  key: string;
  orderId: number | null;
  symbol: string;
  side: OrderSide;
  qty: string;
  price: string;
  filledAt: string;
  source: string;
}

function startOfTodayMs(): number {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d.getTime();
}

/** Flatten every fill executed today (local day) across all orders, newest first.
 * One row per fill = one executed buy/sell with its actual price. */
export function todaysFills(orders: Order[]): FillRow[] {
  const start = startOfTodayMs();
  const rows: FillRow[] = [];
  for (const o of orders) {
    for (const f of o.fills) {
      if (new Date(f.filled_at).getTime() >= start) {
        rows.push({
          key: `${o.id ?? o.created_at}-${f.id}`,
          orderId: o.id,
          symbol: o.symbol,
          side: o.side,
          qty: f.qty,
          price: f.price,
          filledAt: f.filled_at,
          source: o.source_type,
        });
      }
    }
  }
  rows.sort((a, b) => new Date(b.filledAt).getTime() - new Date(a.filledAt).getTime());
  return rows;
}

/** Today's executed trades — a flat buy/sell history with fill prices. */
function TodayActivity({ onSelect }: { onSelect: (id: number) => void }) {
  const query = useQuery({
    queryKey: ["orders", "today"],
    queryFn: () => ordersApi.list({ filter: "all", limit: 500 }),
    refetchInterval: 5_000,
  });

  const fills = query.data ? todaysFills(query.data.items) : [];
  let bought = 0;
  let sold = 0;
  let buys = 0;
  let sells = 0;
  for (const f of fills) {
    const notional = Number(f.qty) * Number(f.price);
    if (f.side === "buy") {
      bought += notional;
      buys += 1;
    } else {
      sold += notional;
      sells += 1;
    }
  }

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap gap-3">
        <Stat label="Trades today" value={String(fills.length)} />
        <Stat label="Buys" value={`${buys} · ${formatMoney(String(bought))}`} tone="buy" />
        <Stat label="Sells" value={`${sells} · ${formatMoney(String(sold))}`} tone="sell" />
      </div>
      <div className="rounded-lg bg-neutral-900 border border-neutral-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-neutral-950 text-[11px] uppercase tracking-wider text-neutral-500">
            <tr>
              <th className="text-left px-3 py-2">Time</th>
              <th className="text-left px-3 py-2">Symbol</th>
              <th className="text-left px-3 py-2">Side</th>
              <th className="text-right px-3 py-2">Qty</th>
              <th className="text-right px-3 py-2">Price</th>
              <th className="text-right px-3 py-2">Value</th>
              <th className="text-left px-3 py-2">Source</th>
            </tr>
          </thead>
          <tbody>
            {query.isLoading && (
              <tr>
                <td colSpan={7} className="px-3 py-4 text-center text-neutral-500">
                  Loading…
                </td>
              </tr>
            )}
            {query.error && (
              <tr>
                <td colSpan={7} className="px-3 py-4 text-center text-rose-400">
                  {(query.error as Error).message}
                </td>
              </tr>
            )}
            {query.data && fills.length === 0 && (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-neutral-500">
                  No fills yet today.
                </td>
              </tr>
            )}
            {fills.map((f) => (
              <tr
                key={f.key}
                onClick={() => f.orderId !== null && onSelect(f.orderId)}
                className="border-t border-neutral-800 hover:bg-neutral-850/30 cursor-pointer"
              >
                <td className="px-3 py-2 font-mono text-xs text-neutral-400">
                  {formatTimestamp(f.filledAt)}
                </td>
                <td className="px-3 py-2 font-semibold text-neutral-100">{f.symbol}</td>
                <td className="px-3 py-2">
                  <SideBadge side={f.side} />
                </td>
                <td className="px-3 py-2 text-right font-mono">{formatQty(f.qty)}</td>
                <td className="px-3 py-2 text-right font-mono text-neutral-100">
                  {formatMoney(f.price)}
                </td>
                <td className="px-3 py-2 text-right font-mono text-neutral-300">
                  {formatMoney(String(Number(f.qty) * Number(f.price)))}
                </td>
                <td className="px-3 py-2 text-xs capitalize text-neutral-400">
                  {f.source.replace("_", " ")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "buy" | "sell";
}) {
  const toneCls =
    tone === "buy" ? "text-emerald-300" : tone === "sell" ? "text-rose-300" : "text-neutral-200";
  return (
    <div className="rounded border border-neutral-800 bg-neutral-900 px-3 py-1.5">
      <div className="text-[10px] uppercase tracking-wider text-neutral-500">{label}</div>
      <div className={`font-mono text-sm ${toneCls}`}>{value}</div>
    </div>
  );
}

function Tabs({
  value,
  onChange,
}: {
  value: OrdersView;
  onChange: (v: OrdersView) => void;
}) {
  const tabs: { id: OrdersView; label: string }[] = [
    { id: "today", label: "Today" },
    { id: "open", label: "Working" },
    { id: "history", label: "History" },
    { id: "all", label: "All" },
  ];
  return (
    <div className="inline-flex rounded border border-neutral-800 bg-neutral-950 p-1">
      {tabs.map((t) => (
        <button
          key={t.id}
          type="button"
          onClick={() => onChange(t.id)}
          className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
            value === t.id
              ? "bg-neutral-800 text-neutral-100"
              : "text-neutral-400 hover:text-neutral-200"
          }`}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

function OrderRow({ order, onSelect }: { order: Order; onSelect: () => void }) {
  const isTerminal =
    TERMINAL_ORDER_STATUSES.has(order.status) || order.id === null;
  const limitOrStop = order.limit_price ?? order.stop_price ?? null;
  // Quantity-weighted average execution price across this order's fills. Market orders
  // carry no limit/stop, so this is the only price the History/All/Working tabs can show.
  const fills = order.fills ?? [];
  const filledQty = fills.reduce((s, f) => s + Number(f.qty), 0);
  const avgFill =
    filledQty > 0
      ? fills.reduce((s, f) => s + Number(f.qty) * Number(f.price), 0) / filledQty
      : null;
  return (
    <tr
      onClick={onSelect}
      className="border-t border-neutral-800 hover:bg-neutral-850/30 cursor-pointer"
      style={{ background: undefined }}
    >
      <td className="px-3 py-2 font-mono text-xs text-neutral-400">
        {formatTimestamp(order.created_at)}
      </td>
      <td className="px-3 py-2 font-semibold text-neutral-100">{order.symbol}</td>
      <td className="px-3 py-2">
        <SideBadge side={order.side} />
      </td>
      <td className="px-3 py-2 text-right font-mono">{formatQty(order.qty)}</td>
      <td className="px-3 py-2 capitalize text-neutral-300">
        {order.type.replace("_", "-")}
      </td>
      <td className="px-3 py-2 text-right font-mono text-neutral-300">
        {limitOrStop ? formatMoney(limitOrStop) : "—"}
      </td>
      <td className="px-3 py-2 text-right font-mono text-neutral-200">
        {avgFill !== null ? formatMoney(String(avgFill)) : "—"}
      </td>
      <td className="px-3 py-2">
        <StatusBadge status={order.status} />
      </td>
      <td
        className="px-3 py-2 text-right"
        onClick={(e) => e.stopPropagation()}
      >
        {!isTerminal && order.id !== null ? (
          <OrderActions order={order} />
        ) : (
          <span className="text-neutral-600 text-xs">—</span>
        )}
      </td>
    </tr>
  );
}

function OrderActions({ order }: { order: Order }) {
  const queryClient = useQueryClient();
  const [modifying, setModifying] = useState(false);
  const [newQty, setNewQty] = useState("");
  const [newLimit, setNewLimit] = useState("");

  const cancelM = useMutation({
    mutationFn: () => ordersApi.cancel(order.id!),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["orders"] }),
  });
  const modifyM = useMutation({
    mutationFn: () =>
      ordersApi.modify(order.id!, {
        new_qty: newQty || null,
        new_limit_price: newLimit || null,
      }),
    onSuccess: () => {
      setModifying(false);
      setNewQty("");
      setNewLimit("");
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["orders"] }),
  });

  if (!modifying) {
    return (
      <div className="inline-flex gap-2 text-xs">
        <button
          type="button"
          onClick={() => setModifying(true)}
          className="text-neutral-300 hover:text-neutral-100"
        >
          Modify
        </button>
        <button
          type="button"
          onClick={() => cancelM.mutate()}
          disabled={cancelM.isPending}
          className="text-rose-400 hover:text-rose-300 disabled:opacity-50"
        >
          {cancelM.isPending ? "Canceling…" : "Cancel"}
        </button>
      </div>
    );
  }
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (!newQty && !newLimit) {
          setModifying(false);
          return;
        }
        modifyM.mutate();
      }}
      className="inline-flex items-center gap-1 text-xs"
    >
      <input
        aria-label="New qty"
        className="w-16 bg-neutral-950 border border-neutral-800 rounded px-1.5 py-0.5"
        placeholder="Qty"
        value={newQty}
        onChange={(e) => setNewQty(e.target.value)}
        inputMode="decimal"
      />
      <input
        aria-label="New limit"
        className="w-20 bg-neutral-950 border border-neutral-800 rounded px-1.5 py-0.5"
        placeholder="Limit"
        value={newLimit}
        onChange={(e) => setNewLimit(e.target.value)}
        inputMode="decimal"
      />
      <button
        type="submit"
        disabled={modifyM.isPending}
        className="text-emerald-400 hover:text-emerald-300 disabled:opacity-50"
      >
        {modifyM.isPending ? "…" : "Send"}
      </button>
      <button
        type="button"
        onClick={() => setModifying(false)}
        className="text-neutral-500 hover:text-neutral-300"
      >
        ✕
      </button>
    </form>
  );
}

function SideBadge({ side }: { side: "buy" | "sell" }) {
  const cls =
    side === "buy"
      ? "bg-emerald-900/50 text-emerald-300 border-emerald-800/60"
      : "bg-rose-900/50 text-rose-300 border-rose-800/60";
  return (
    <span className={`inline-flex rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${cls}`}>
      {side}
    </span>
  );
}

function StatusBadge({ status }: { status: OrderStatus }) {
  const palette: Partial<Record<OrderStatus, string>> = {
    pending_risk: "bg-neutral-800 text-neutral-300 border-neutral-700",
    pending_submit: "bg-neutral-800 text-neutral-300 border-neutral-700",
    submitted: "bg-sky-900/50 text-sky-300 border-sky-800/60",
    partially_filled: "bg-amber-900/50 text-amber-200 border-amber-800/60",
    filled: "bg-emerald-900/50 text-emerald-300 border-emerald-800/60",
    canceled: "bg-neutral-800 text-neutral-400 border-neutral-700",
    expired: "bg-neutral-800 text-neutral-400 border-neutral-700",
    rejected: "bg-rose-900/50 text-rose-300 border-rose-800/60",
    replaced: "bg-violet-900/50 text-violet-300 border-violet-800/60",
  };
  const cls = palette[status] ?? "bg-neutral-800 text-neutral-300 border-neutral-700";
  return (
    <span className={`inline-flex rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${cls}`}>
      {status.replace("_", " ")}
    </span>
  );
}

function OrderDrawer({ orderId, onClose }: { orderId: number; onClose: () => void }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["order", orderId],
    queryFn: () => ordersApi.get(orderId),
    refetchInterval: 3_000,
  });

  return (
    <div className="fixed inset-0 z-30 flex justify-end">
      <button
        type="button"
        aria-label="Close drawer"
        className="flex-1 bg-black/40"
        onClick={onClose}
      />
      <div className="w-full max-w-md bg-neutral-950 border-l border-neutral-800 overflow-y-auto p-5 grid gap-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-neutral-300">
            Order #{orderId}
          </h3>
          <button
            type="button"
            onClick={onClose}
            className="text-neutral-400 hover:text-neutral-100 text-sm"
          >
            Close
          </button>
        </div>
        {isLoading && <p className="text-neutral-400 text-sm">Loading…</p>}
        {error && (
          <p className="text-rose-400 text-sm">
            {error instanceof ApiError && error.status === 404
              ? "Order not found."
              : (error as Error).message}
          </p>
        )}
        {data && <OrderDetail order={data} />}
      </div>
    </div>
  );
}

function OrderDetail({ order }: { order: Order }) {
  return (
    <div className="grid gap-4">
      <DetailRow label="Symbol" value={order.symbol} />
      <DetailRow label="Side" value={order.side.toUpperCase()} />
      <DetailRow label="Qty" value={formatQty(order.qty)} />
      <DetailRow label="Type" value={order.type.replace("_", "-")} />
      <DetailRow label="TIF" value={order.tif.toUpperCase()} />
      {order.limit_price && (
        <DetailRow label="Limit price" value={formatMoney(order.limit_price)} />
      )}
      {order.stop_price && (
        <DetailRow label="Stop price" value={formatMoney(order.stop_price)} />
      )}
      <DetailRow label="Status" value={<StatusBadge status={order.status} />} />
      {order.rejection_reason && (
        <DetailRow label="Rejection" value={order.rejection_reason} />
      )}
      <DetailRow label="Broker order id" value={order.broker_order_id ?? "—"} mono />
      <DetailRow label="Client order id" value={order.client_order_id ?? "—"} mono />
      <DetailRow label="Created" value={formatTimestamp(order.created_at)} />
      <DetailRow label="Submitted" value={formatTimestamp(order.submitted_at)} />
      <DetailRow label="Terminal" value={formatTimestamp(order.terminal_at)} />
      <DetailRow label="Source" value={order.source_type} />

      {order.risk_check && (
        <section className="rounded border border-neutral-800 bg-neutral-900 p-3 grid gap-1">
          <h4 className="text-[11px] uppercase tracking-wider text-neutral-500">
            Risk check
          </h4>
          <div className="flex items-center gap-2 text-sm">
            <span
              className={
                order.risk_check.decision === "pass"
                  ? "text-emerald-400"
                  : "text-amber-300"
              }
            >
              {order.risk_check.decision.toUpperCase()}
            </span>
            <span className="text-neutral-500 text-xs">
              {formatTimestamp(order.risk_check.evaluated_at)}
            </span>
          </div>
          {order.risk_check.reason_codes.length > 0 && (
            <div className="text-xs text-neutral-400">
              {describeReasons(order.risk_check.reason_codes)}
            </div>
          )}
        </section>
      )}

      <section className="grid gap-1">
        <h4 className="text-[11px] uppercase tracking-wider text-neutral-500">
          Fills ({order.fills.length})
        </h4>
        {order.fills.length === 0 ? (
          <p className="text-xs text-neutral-500">No fills yet.</p>
        ) : (
          <table className="w-full text-xs">
            <thead className="text-neutral-500">
              <tr>
                <th className="text-left py-1">Time</th>
                <th className="text-right py-1">Qty</th>
                <th className="text-right py-1">Price</th>
              </tr>
            </thead>
            <tbody>
              {order.fills.map((f) => (
                <tr key={f.id} className="border-t border-neutral-800">
                  <td className="py-1 font-mono text-neutral-400">
                    {formatTimestamp(f.filled_at)}
                  </td>
                  <td className="py-1 text-right font-mono">{formatQty(f.qty)}</td>
                  <td className="py-1 text-right font-mono">{formatMoney(f.price)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

function DetailRow({
  label,
  value,
  mono,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="grid grid-cols-[120px_1fr] gap-2 text-sm">
      <span className="text-[11px] uppercase tracking-wider text-neutral-500 self-center">
        {label}
      </span>
      <span className={mono ? "font-mono text-neutral-200" : "text-neutral-200"}>
        {value}
      </span>
    </div>
  );
}

