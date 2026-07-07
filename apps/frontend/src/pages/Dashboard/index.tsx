import { useQuery } from "@tanstack/react-query";
import { accountApi } from "@/api/account";
import { ordersApi } from "@/api/orders";
import { positionsApi } from "@/api/positions";
import { benchmarksApi } from "@/api/benchmarks";
import { ApiError } from "@/api/client";
import OrderTicket from "@/components/ticket/OrderTicket";
import MorningBriefCard from "@/components/morning-brief/MorningBriefCard";
import RecentProposalsCard from "@/components/proposals/RecentProposalsCard";
import { VariantsCard } from "@/components/strategies/VariantsCard";
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

  const benchmarks = useQuery({
    queryKey: ["benchmarks"],
    queryFn: benchmarksApi.list,
    refetchInterval: 60_000,
    retry: false,
  });

  const acc = account.data;
  const openOrders = orders.data?.items ?? [];
  const positionItems = positions.data?.items ?? [];
  const benchItems = benchmarks.data?.items ?? [];
  const inceptionDate = benchItems.find((b) => b.inception_date)?.inception_date;

  return (
    <div className="grid gap-4">
      <div className="rounded-lg bg-neutral-900 border border-neutral-800 p-6">
        <h2 className="text-lg font-semibold text-neutral-100">Dashboard</h2>
        <p className="text-sm text-neutral-400 mt-1">
          Account state, working orders, open positions, and an order ticket.
          The <span className="font-mono">Opportunities</span> page surfaces
          cross-cutting things to look at.
        </p>
      </div>

      <VariantsCard />

      <MorningBriefCard />

      <RecentProposalsCard />

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
          <div className="mt-3">
            {/* Explicit: these figures are THIS logged-in user's own paper account only. */}
            <div className="text-[11px] text-neutral-500 mb-3">
              Your paper account · {acc.mode.toUpperCase()} · #{acc.account_id}
            </div>
            {/* Headline: what you actually have, and how you're doing overall + today. */}
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <Stat label="Total Value (Equity)" value={formatMoney(acc.equity)} big />
              <Stat
                label="Total Gain / Loss"
                value={formatMoney(acc.total_return)}
                valueClassName={pnlClassName(acc.total_return)}
                sub={`${formatPercent(acc.total_return_pct)} since start`}
                big
              />
              <Stat
                label="Today's Change"
                value={formatMoney(acc.day_change)}
                valueClassName={pnlClassName(acc.day_change)}
                sub={formatPercent(acc.day_change_pct)}
                big
              />
            </div>
            {/* Breakdown: starting money, and where the value sits now. */}
            <div className="grid gap-4 mt-4 sm:grid-cols-2 lg:grid-cols-4">
              <Stat label="Starting Capital" value={formatMoney(acc.starting_equity)} />
              <Stat label="Cash" value={formatMoney(acc.cash)} />
              <Stat
                label="Invested (positions)"
                value={formatMoney(Number(acc.equity) - Number(acc.cash))}
              />
              <Stat
                label="Status"
                value={acc.status}
                sub={acc.pattern_day_trader ? "PDT" : acc.mode.toUpperCase()}
              />
            </div>
            {/* De-emphasized: margin/technical figures that were confusing up top. */}
            <div className="mt-3 text-[11px] text-neutral-500 flex flex-wrap gap-x-4 gap-y-1">
              <span>
                Buying power (margin ≈{" "}
                {(Number(acc.buying_power) / Math.max(Number(acc.equity), 1)).toFixed(1)}×):{" "}
                {formatMoney(acc.buying_power)}
              </span>
              <span>Portfolio value: {formatMoney(acc.portfolio_value)}</span>
              <span>Last equity: {formatMoney(acc.last_equity)}</span>
              <span>Day-trade count: {formatNumber(acc.daytrade_count, 0)}</span>
              <span>Updated {formatTimestamp(acc.updated_at)}</span>
              {acc.trading_blocked ? (
                <span className="text-rose-400">Trading blocked</span>
              ) : (
                <span className="text-emerald-400">Trading OK</span>
              )}
            </div>
          </div>
        )}
      </section>

      {/* Your book's return vs passive index funds over the SAME window (starting balance → now). */}
      <section className="rounded-lg bg-neutral-900 border border-neutral-800 p-6">
        <div className="flex items-baseline justify-between">
          <h3 className="text-sm font-semibold text-neutral-300 uppercase tracking-wide">
            Performance vs Benchmarks
          </h3>
          <span className="text-[11px] text-neutral-500">
            {inceptionDate ? `since ${inceptionDate}` : "since inception"}
          </span>
        </div>
        <p className="text-[11px] text-neutral-500 mt-1">
          Your book vs. index funds over the same period (from your starting balance to now).
        </p>
        {benchmarks.isLoading && (
          <p className="text-neutral-400 text-sm mt-2">Loading…</p>
        )}
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[11px] uppercase tracking-wider text-neutral-500 text-left">
                <th className="py-1 pr-4 font-medium">Fund</th>
                <th className="py-1 pr-4 font-medium text-right">Start</th>
                <th className="py-1 pr-4 font-medium text-right">Now</th>
                <th className="py-1 font-medium text-right">Return</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-800">
              {acc && (
                <tr className="bg-neutral-950/40">
                  <td className="py-1.5 pr-4 font-semibold text-neutral-100">
                    Your book{" "}
                    <span className="text-[11px] font-normal text-neutral-500">
                      #{acc.account_id}
                    </span>
                  </td>
                  <td className="py-1.5 pr-4 text-right font-mono text-neutral-300">
                    {formatMoney(acc.starting_equity)}
                  </td>
                  <td className="py-1.5 pr-4 text-right font-mono text-neutral-100">
                    {formatMoney(acc.equity)}
                  </td>
                  <td
                    className={`py-1.5 text-right font-mono font-semibold ${pnlClassName(
                      acc.total_return_pct,
                    )}`}
                  >
                    {formatPercent(acc.total_return_pct)}
                  </td>
                </tr>
              )}
              {benchItems.map((b) => (
                <tr key={b.symbol} className="text-neutral-300">
                  <td className="py-1.5 pr-4">
                    <span className="font-semibold text-neutral-100">{b.symbol}</span>{" "}
                    <span className="text-[11px] text-neutral-500">{b.name}</span>
                  </td>
                  <td className="py-1.5 pr-4 text-right font-mono">
                    {b.inception_price
                      ? `$${Number(b.inception_price).toFixed(2)}`
                      : "—"}
                  </td>
                  <td className="py-1.5 pr-4 text-right font-mono">
                    {b.current_price ? `$${Number(b.current_price).toFixed(2)}` : "—"}
                  </td>
                  <td
                    className={`py-1.5 text-right font-mono ${
                      b.return_pct != null ? pnlClassName(b.return_pct) : "text-neutral-500"
                    }`}
                  >
                    {b.return_pct != null ? formatPercent(b.return_pct) : "pending"}
                  </td>
                </tr>
              ))}
              {!benchmarks.isLoading && benchItems.length === 0 && (
                <tr>
                  <td colSpan={4} className="py-2 text-neutral-500">
                    No benchmark snapshots yet — captured daily near market close.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
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

      <section>
        <OrderTicket />
      </section>
    </div>
  );
}

function Stat({
  label,
  value,
  sub,
  valueClassName,
  big,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  valueClassName?: string;
  big?: boolean;
}) {
  return (
    <div className="rounded border border-neutral-800 bg-neutral-950 p-3">
      <div className="text-[11px] uppercase tracking-wider text-neutral-500">
        {label}
      </div>
      <div
        className={`mt-1 font-mono ${big ? "text-2xl" : "text-lg"} ${valueClassName ?? "text-neutral-100"}`}
      >
        {value}
      </div>
      {sub && <div className="text-[11px] text-neutral-500 mt-0.5">{sub}</div>}
    </div>
  );
}
