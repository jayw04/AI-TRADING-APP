import { useQuery } from "@tanstack/react-query";
import { accountApi } from "@/api/account";
import { ordersApi } from "@/api/orders";
import { positionsApi } from "@/api/positions";
import { ApiError } from "@/api/client";
import {
  formatMoney,
  formatNumber,
  formatPercent,
  formatQty,
  formatTimestamp,
  pnlClassName,
} from "@/lib/format";

const REFETCH_MS = 5_000;

export default function Dashboard() {
  const account = useQuery({
    queryKey: ["account"],
    queryFn: accountApi.get,
    refetchInterval: REFETCH_MS,
    retry: false,
  });
  const orders = useQuery({
    queryKey: ["orders", "open"],
    queryFn: () => ordersApi.list({ filter: "open" }),
    refetchInterval: REFETCH_MS,
    retry: false,
  });
  const positions = useQuery({
    queryKey: ["positions"],
    queryFn: positionsApi.list,
    refetchInterval: REFETCH_MS,
    retry: false,
  });

  const acc = account.data;
  const openOrders = orders.data?.items ?? [];
  const positionItems = positions.data?.items ?? [];

  return (
    <div className="grid gap-4">
      <div className="rounded-lg bg-neutral-900 border border-neutral-800 p-6">
        <h2 className="text-lg font-semibold text-neutral-100">Dashboard</h2>
        <p className="text-sm text-neutral-400 mt-1">
          Account state, working orders, open positions. Place orders on the
          Opportunities page.
        </p>
      </div>

      <section className="rounded-lg bg-neutral-900 border border-neutral-800 p-6">
        <h3 className="text-sm font-semibold text-neutral-300 uppercase tracking-wide">
          Account
        </h3>
        {account.isLoading && (
          <p className="text-neutral-400 text-sm mt-2">Loading…</p>
        )}
        {account.error && (
          <p className="text-rose-400 text-sm mt-2">
            {account.error instanceof ApiError && account.error.status === 404
              ? "No account state yet. Wait for the next sync tick or POST /api/v1/internal/account/sync."
              : `Backend unreachable: ${(account.error as Error).message}`}
          </p>
        )}
        {acc && (
          <div className="grid gap-4 mt-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Equity" value={formatMoney(acc.equity)} />
            <Stat
              label="Day P&L"
              value={formatMoney(acc.day_change)}
              valueClassName={pnlClassName(acc.day_change)}
              sub={formatPercent(acc.day_change_pct)}
            />
            <Stat label="Cash" value={formatMoney(acc.cash)} />
            <Stat label="Buying power" value={formatMoney(acc.buying_power)} />
            <Stat label="Portfolio value" value={formatMoney(acc.portfolio_value)} />
            <Stat label="Last equity" value={formatMoney(acc.last_equity)} />
            <Stat label="Day-trade count" value={formatNumber(acc.daytrade_count, 0)} />
            <Stat
              label="Status"
              value={acc.status}
              sub={acc.pattern_day_trader ? "PDT" : acc.mode.toUpperCase()}
            />
            <div className="sm:col-span-2 lg:col-span-4 text-[11px] text-neutral-500">
              Updated {formatTimestamp(acc.updated_at)} ·{" "}
              {acc.trading_blocked ? (
                <span className="text-rose-400">Trading blocked</span>
              ) : (
                <span className="text-emerald-400">Trading OK</span>
              )}
            </div>
          </div>
        )}
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-lg bg-neutral-900 border border-neutral-800 p-6">
          <div className="flex items-baseline justify-between">
            <h3 className="text-sm font-semibold text-neutral-300 uppercase tracking-wide">
              Working orders
            </h3>
            <span className="text-[11px] text-neutral-500">
              {orders.data ? `${orders.data.count} open` : ""}
            </span>
          </div>
          {orders.isLoading && (
            <p className="text-neutral-400 text-sm mt-2">Loading…</p>
          )}
          {orders.error && (
            <p className="text-rose-400 text-sm mt-2">
              {(orders.error as Error).message}
            </p>
          )}
          {orders.data && openOrders.length === 0 && (
            <p className="text-neutral-500 text-sm mt-2">No working orders.</p>
          )}
          {openOrders.length > 0 && (
            <ul className="mt-3 divide-y divide-neutral-800 text-sm">
              {openOrders.slice(0, 8).map((o) => (
                <li
                  key={o.id ?? `eph-${o.created_at}-${o.symbol}`}
                  className="flex items-center justify-between py-1.5"
                >
                  <div className="flex items-center gap-2">
                    <span
                      className={
                        o.side === "buy" ? "text-emerald-400" : "text-rose-400"
                      }
                    >
                      {o.side.toUpperCase()}
                    </span>
                    <span className="font-mono">{formatQty(o.qty)}</span>
                    <span className="font-semibold text-neutral-100">
                      {o.symbol}
                    </span>
                    <span className="text-[11px] uppercase text-neutral-500">
                      {o.type.replace("_", "-")}
                    </span>
                  </div>
                  <span className="text-[11px] uppercase text-neutral-400">
                    {o.status.replace("_", " ")}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="rounded-lg bg-neutral-900 border border-neutral-800 p-6">
          <div className="flex items-baseline justify-between">
            <h3 className="text-sm font-semibold text-neutral-300 uppercase tracking-wide">
              Positions
            </h3>
            <span className="text-[11px] text-neutral-500">
              {positions.data
                ? `Net ${formatMoney(positions.data.net_exposure)}`
                : ""}
            </span>
          </div>
          {positions.isLoading && (
            <p className="text-neutral-400 text-sm mt-2">Loading…</p>
          )}
          {positions.error && (
            <p className="text-rose-400 text-sm mt-2">
              {(positions.error as Error).message}
            </p>
          )}
          {positions.data && positionItems.length === 0 && (
            <p className="text-neutral-500 text-sm mt-2">No open positions.</p>
          )}
          {positionItems.length > 0 && (
            <ul className="mt-3 divide-y divide-neutral-800 text-sm">
              {positionItems.slice(0, 8).map((p) => (
                <li key={p.id} className="flex items-center justify-between py-1.5">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-neutral-100">{p.symbol}</span>
                    <span className="font-mono text-neutral-300">
                      {formatQty(p.qty)}
                    </span>
                    <span className="text-[11px] uppercase text-neutral-500">
                      {p.side ?? ""}
                    </span>
                  </div>
                  <span className={`font-mono ${pnlClassName(p.unrealized_pl)}`}>
                    {formatMoney(p.unrealized_pl)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  sub,
  valueClassName,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  valueClassName?: string;
}) {
  return (
    <div className="rounded border border-neutral-800 bg-neutral-950 p-3">
      <div className="text-[11px] uppercase tracking-wider text-neutral-500">
        {label}
      </div>
      <div className={`mt-1 font-mono text-lg ${valueClassName ?? "text-neutral-100"}`}>
        {value}
      </div>
      {sub && <div className="text-[11px] text-neutral-500 mt-0.5">{sub}</div>}
    </div>
  );
}
