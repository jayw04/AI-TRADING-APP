import { useEffect, useState } from "react";
import { strategiesApi } from "@/api/strategies";
import { ordersApi } from "@/api/orders";
import type { Strategy, StrategyRun, Signal, Order, BacktestSummary } from "@/api/types";
import { formatPct, formatNumber } from "@/components/strategies/formatters";

interface Props {
  strategy: Strategy;
}

export function OverviewTab({ strategy }: Props) {
  const [runs, setRuns] = useState<StrategyRun[]>([]);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [latestBacktest, setLatestBacktest] = useState<BacktestSummary | null>(null);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const [r, s, o, b] = await Promise.all([
          strategiesApi.listRuns(strategy.id, 5),
          strategiesApi.listSignals(strategy.id, 10),
          // P4 §5: server-side scoping replaces the pull-all-then-filter.
          ordersApi.list({
            source_type: "strategy",
            source_id: String(strategy.id),
            limit: 10,
          }),
          strategiesApi.listBacktests(strategy.id, 1),
        ]);
        if (!mounted) return;
        setRuns(r.items);
        setSignals(s.items);
        setOrders(o.items);
        setLatestBacktest(b.items[0] ?? null);
      } catch {
        /* silent — overview is informational only */
      }
    })();
    return () => { mounted = false; };
  }, [strategy.id]);

  const latestRun = runs[0] ?? null;

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <Card title="Latest run">
        {latestRun ? (
          <dl className="space-y-1 text-sm text-gray-300">
            <Row label="Status">{latestRun.status}</Row>
            <Row label="Started">{new Date(latestRun.started_at).toLocaleString()}</Row>
            <Row label="Ended">{latestRun.ended_at ? new Date(latestRun.ended_at).toLocaleString() : "still running"}</Row>
            {latestRun.error_text && (
              <Row label="Error"><span className="text-rose-400">{latestRun.error_text}</span></Row>
            )}
          </dl>
        ) : <Empty>No runs yet</Empty>}
      </Card>

      <Card title="Latest backtest">
        {latestBacktest ? (
          <dl className="space-y-1 text-sm text-gray-300">
            <Row label="Label">{latestBacktest.label}</Row>
            <Row label="Range">
              {new Date(latestBacktest.range_start).toLocaleDateString()} →{" "}
              {new Date(latestBacktest.range_end).toLocaleDateString()}
            </Row>
            <Row label="Trades">{latestBacktest.metrics.trade_count}</Row>
            <Row label="Total return">{formatPct(latestBacktest.metrics.total_return)}</Row>
            <Row label="Sharpe">{formatNumber(latestBacktest.metrics.sharpe_ratio)}</Row>
            <Row label="Max DD">{formatPct(latestBacktest.metrics.max_drawdown)}</Row>
            <Row label="Win rate">{formatPct(latestBacktest.metrics.win_rate)}</Row>
          </dl>
        ) : <Empty>No backtests yet — run one from the Backtests tab</Empty>}
      </Card>

      <Card title={`Recent signals (${signals.length})`}>
        {signals.length === 0 ? <Empty>No signals</Empty> : (
          <ul className="space-y-1 text-sm">
            {signals.slice(0, 8).map((s) => (
              <li key={s.id} className="flex justify-between border-b border-gray-800 py-1">
                <span>
                  <span className="font-semibold">{s.symbol}</span>{" "}
                  <span className={
                    s.type === "entry" ? "text-emerald-400" :
                    s.type === "exit" ? "text-rose-400" : "text-gray-400"
                  }>
                    {s.type}
                  </span>
                </span>
                <span className="text-xs text-gray-500">
                  {new Date(s.received_at).toLocaleTimeString()}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title={`Recent orders (${orders.length})`}>
        {orders.length === 0 ? <Empty>No strategy-attributed orders</Empty> : (
          <ul className="space-y-1 text-sm">
            {orders.slice(0, 8).map((o) => (
              <li key={o.id} className="flex justify-between border-b border-gray-800 py-1">
                <span>
                  <span className={o.side === "buy" ? "text-emerald-400" : "text-rose-400"}>
                    {o.side.toUpperCase()}
                  </span>{" "}
                  <span className="font-semibold">{o.symbol}</span> ×{o.qty}
                </span>
                <span className="text-xs text-gray-500">{o.status}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
      <div className="mb-2 text-sm font-semibold text-gray-300">{title}</div>
      {children}
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between">
      <dt className="text-gray-500">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <div className="text-sm text-gray-500">{children}</div>;
}
