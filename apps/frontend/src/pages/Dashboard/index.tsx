import { useQuery } from "@tanstack/react-query";
import { accountApi } from "@/api/account";
import { ApiError } from "@/api/client";
import {
  formatMoney,
  formatNumber,
  formatPercent,
  formatTimestamp,
  pnlClassName,
} from "@/lib/format";

export default function Dashboard() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["account"],
    queryFn: accountApi.get,
    refetchInterval: 5_000,
  });

  return (
    <div className="grid gap-4">
      <div className="rounded-lg bg-neutral-900 border border-neutral-800 p-6">
        <h2 className="text-lg font-semibold text-neutral-100">Dashboard</h2>
        <p className="text-sm text-neutral-400 mt-1">
          Quick view of account state. Place orders on the Opportunities page; track
          them on Orders and Positions.
        </p>
      </div>

      <div className="rounded-lg bg-neutral-900 border border-neutral-800 p-6">
        <h3 className="text-sm font-semibold text-neutral-300 uppercase tracking-wide">
          Account
        </h3>
        {isLoading && <p className="text-neutral-400 text-sm mt-2">Loading…</p>}
        {error && (
          <p className="text-rose-400 text-sm mt-2">
            {error instanceof ApiError && error.status === 404
              ? "No account state yet. Wait for the next sync tick or POST /api/v1/internal/account/sync."
              : `Backend unreachable: ${(error as Error).message}`}
          </p>
        )}
        {data && (
          <div className="grid gap-4 mt-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Equity" value={formatMoney(data.equity)} />
            <Stat
              label="Day change"
              value={formatMoney(data.day_change)}
              valueClassName={pnlClassName(data.day_change)}
              sub={formatPercent(data.day_change_pct)}
            />
            <Stat label="Cash" value={formatMoney(data.cash)} />
            <Stat label="Buying power" value={formatMoney(data.buying_power)} />
            <Stat label="Portfolio value" value={formatMoney(data.portfolio_value)} />
            <Stat label="Last equity" value={formatMoney(data.last_equity)} />
            <Stat label="Day-trade count" value={formatNumber(data.daytrade_count, 0)} />
            <Stat
              label="Status"
              value={data.status}
              sub={data.pattern_day_trader ? "PDT" : data.mode.toUpperCase()}
            />
            <div className="sm:col-span-2 lg:col-span-4 text-[11px] text-neutral-500">
              Updated {formatTimestamp(data.updated_at)} ·{" "}
              {data.trading_blocked ? (
                <span className="text-rose-400">Trading blocked</span>
              ) : (
                <span className="text-emerald-400">Trading OK</span>
              )}
            </div>
          </div>
        )}
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
