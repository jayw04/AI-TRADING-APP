import { useQuery } from "@tanstack/react-query";
import type { ResearchRun } from "@/api/markets";
import { marketQueryKey, marketsApi } from "@/api/markets";
import { useMarket } from "@/markets/MarketContext";
import { useOptionalSession } from "@/markets/session";
import { formatInstant, formatMoney, formatPct } from "@/markets/format";
import { Card, LabelPill, PageHeader, QueryState } from "./shared";

const COST_LABEL: Record<string, string> = {
  commission: "Commission (assumed)",
  stamp_duty: "Stamp duty",
  transfer_fee: "Transfer fee",
  handling_fee: "Handling fee",
  regulatory_fee: "Regulatory fee",
};

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-neutral-500">{label}</dt>
      <dd className="text-neutral-200">{value}</dd>
    </div>
  );
}

function RunCard({ run }: { run: ResearchRun }) {
  const market = useMarket();
  const r = run.result;
  const refusals = Object.entries(r.refusals ?? {});
  const stranded = Object.entries(r.unexecutable_delisting_exits ?? {});
  return (
    <Card
      title={run.candidate_id}
      subtitle={`${run.period ? `${run.period.start} – ${run.period.end}` : "no period"} · ${run.market_context.provider} · ${run.market_context.price_basis} · run ${formatInstant(run.created_at_utc, market)}`}
    >
      <div className="flex flex-wrap gap-1">
        {run.labels.map((l) => (
          <LabelPill key={l} text={l} />
        ))}
      </div>

      <h4 className="mt-4 text-xs font-semibold uppercase text-neutral-400">Result</h4>
      <dl className="mt-1 grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-4">
        <Stat label="Net return" value={formatPct(r.net_return)} />
        <Stat label="Before costs" value={formatPct(r.gross_return_before_fees)} />
        <Stat label="End equity" value={formatMoney(r.end_equity_cny, market)} />
        <Stat label="Capital" value={formatMoney(run.capital_cny, market)} />
        <Stat label="Fills" value={String(r.fills)} />
        <Stat label="Turnover" value={r.turnover == null ? "—" : `${r.turnover.toFixed(2)}×`} />
      </dl>

      <h4 className="mt-4 text-xs font-semibold uppercase text-neutral-400">Costs ({market.currencyLabel})</h4>
      <dl className="mt-1 grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-3">
        {Object.entries(r.costs_cny ?? {})
          .filter(([k]) => k !== "total")
          .map(([k, v]) => (
            <Stat key={k} label={COST_LABEL[k] ?? k} value={formatMoney(v, market, 2)} />
          ))}
        <Stat label="Total costs" value={formatMoney(r.fees_cny, market, 2)} />
        <Stat label="Cost drag" value={formatPct(r.cost_drag)} />
      </dl>
      {run.commission_assumption && (
        <p className="mt-1 text-[11px] text-neutral-500">
          Commission assumption: {(run.commission_assumption.rate * 100).toFixed(3)}%, minimum{" "}
          {formatMoney(run.commission_assumption.minimum_cny, market, 2)} per order.
        </p>
      )}

      <h4 className="mt-4 text-xs font-semibold uppercase text-neutral-400">Risk</h4>
      <dl className="mt-1 grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-4">
        <Stat label="Max drawdown" value={formatPct(r.risk?.max_drawdown ?? r.max_drawdown)} />
        <Stat label="Volatility (ann.)" value={formatPct(r.risk?.volatility_annualized)} />
        <Stat label="Worst day" value={formatPct(r.risk?.worst_day)} />
        <Stat label="Best day" value={formatPct(r.risk?.best_day)} />
      </dl>

      <h4 className="mt-4 text-xs font-semibold uppercase text-neutral-400">Execution constraints</h4>
      <p className="mt-1 text-xs text-neutral-400">
        Refused orders: {refusals.length ? refusals.map(([k, v]) => `${k} ${v}`).join(", ") : "none"}
      </p>
      <p className="text-xs text-neutral-400">
        Stranded by delisting:{" "}
        {stranded.length
          ? stranded.map(([s, v]) => `${s} (${formatMoney(v.last_close_value_cny, market)} at last close, valued at zero)`).join(", ")
          : "none"}
      </p>

      <details className="mt-4 text-xs text-neutral-400">
        <summary className="cursor-pointer text-neutral-300">Limitations and assumptions</summary>
        <ul className="mt-2 list-disc pl-5 space-y-0.5">
          {[...run.limitations.not_modelled.map((x) => `Not modelled: ${x}`), ...run.limitations.accounting].map((x) => (
            <li key={x}>{x}</li>
          ))}
        </ul>
        {run.limitations.rules.length > 0 && (
          <table className="mt-2 w-full">
            <thead className="text-neutral-500">
              <tr>
                <th className="text-left font-normal">Rule</th>
                <th className="text-left font-normal">From</th>
                <th className="text-left font-normal">Value</th>
                <th className="text-left font-normal">Checked</th>
              </tr>
            </thead>
            <tbody>
              {run.limitations.rules.map((rule) => (
                <tr key={`${rule.name}-${rule.effective_from}`}>
                  <td>{rule.name}</td>
                  <td>{rule.effective_from}</td>
                  <td>{rule.value}</td>
                  <td>{rule.verified}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </details>
    </Card>
  );
}

export default function ResultsPage() {
  const market = useMarket();
  const session = useOptionalSession();
  const q = useQuery({
    queryKey: marketQueryKey(market, "results", session?.user_id),
    queryFn: () => marketsApi.results(market),
  });

  return (
    <div className="grid gap-4">
      <PageHeader title="Results · 测试结果">
        <p className="text-xs text-neutral-500 mt-1">
          Descriptive runs only. A plumbing or synthetic sample supports no claim that a strategy works.
        </p>
      </PageHeader>
      <QueryState loading={q.isLoading} error={q.error} what="results" />
      {q.data && q.data.runs.length === 0 && <p className="text-sm text-neutral-400">No research runs yet.</p>}
      {q.data?.runs.map((run) => (
        <RunCard key={run.run_id} run={run} />
      ))}
    </div>
  );
}
