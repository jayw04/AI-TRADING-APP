import { useQuery } from "@tanstack/react-query";
import { marketQueryKey, marketsApi } from "@/api/markets";
import { useMarket } from "@/markets/MarketContext";
import { formatInstant } from "@/markets/format";
import { Card, LabelPill, PageHeader, Pill, QueryState } from "./shared";

export default function StrategiesPage() {
  const market = useMarket();
  const q = useQuery({ queryKey: marketQueryKey(market, "strategies"), queryFn: () => marketsApi.strategies(market) });

  return (
    <div className="grid gap-4">
      <PageHeader title="Strategies · 策略">
        <p className="text-xs text-neutral-500 mt-1">
          Research candidates, defined before any result. There is no activation, broker or order control here.
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
                  {c.signal}; top {c.top_k}; {c.rebalance}
                </p>
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
