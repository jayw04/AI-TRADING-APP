import { useQuery } from "@tanstack/react-query";
import { marketQueryKey, marketsApi } from "@/api/markets";
import { useMarket } from "@/markets/MarketContext";
import { useOptionalSession } from "@/markets/session";
import { formatInstant } from "@/markets/format";
import { Card, LabelPill, PageHeader, Pill, QueryState } from "./shared";

export default function StrategiesPage() {
  const market = useMarket();
  const session = useOptionalSession();
  const q = useQuery({
    queryKey: marketQueryKey(market, "strategies", session?.user_id),
    queryFn: () => marketsApi.strategies(market),
  });

  return (
    <div className="grid gap-4">
      <PageHeader title="Strategies · 策略">
        <p className="text-xs text-neutral-500 mt-1">
          China registry. A US test or activation does not activate the China row. Research only — no broker or order control.
        </p>
      </PageHeader>
      <QueryState loading={q.isLoading} error={q.error} what="strategies" />
      {q.data && (
        <Card title="Research candidates">
          <ul className="space-y-4">
            {q.data.candidates.map((c) => (
              <li key={c.candidate_id} className="text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-neutral-100">{c.candidate_id}</span>
                  <span className="text-neutral-400">{c.name}</span>
                  <Pill text={c.status} />
                </div>
                <p className="mt-1 text-xs text-neutral-400">{c.hypothesis}</p>
                <p className="text-xs text-neutral-500">
                  {c.family ? `${c.family} · ` : ""}
                  {c.version ? `v${c.version} · ` : ""}
                  {c.signal}
                  {c.rebalance ? `; ${c.rebalance}` : ""}
                </p>
                {c.source_us_code_path && (
                  <p className="text-xs text-neutral-500">
                    US source {c.source_us_strategy_id ?? "no row id"} · {c.source_us_code_path}
                    {c.source_us_version ? ` · ${c.source_us_version}` : ""} · {c.equivalence}
                  </p>
                )}
                {c.blocked_reason && <p className="mt-1 text-xs text-amber-300">{c.blocked_reason}</p>}
                <p className="mt-1 text-xs text-neutral-500">
                  {c.last_run ? (
                    <>
                      {c.run_count} run{c.run_count === 1 ? "" : "s"} · last {formatInstant(c.last_run.created_at_utc, market)}{" "}
                      <LabelPill text={c.last_run.sample_label} />
                    </>
                  ) : (
                    "Not run yet"
                  )}
                </p>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
