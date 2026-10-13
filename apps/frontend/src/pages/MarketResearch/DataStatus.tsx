import { useQuery } from "@tanstack/react-query";
import { marketQueryKey, marketsApi } from "@/api/markets";
import { useMarket } from "@/markets/MarketContext";
import { useOptionalSession } from "@/markets/session";
import { formatInstant } from "@/markets/format";
import { Card, LabelPill, PageHeader, Pill, QueryState } from "./shared";

export default function DataStatusPage() {
  const market = useMarket();
  const session = useOptionalSession();
  const q = useQuery({
    queryKey: marketQueryKey(market, "data-status", session?.user_id),
    queryFn: () => marketsApi.dataStatus(market),
  });
  const d = q.data;

  return (
    <div className="grid gap-4">
      <PageHeader title="Data status · 数据状态">
        {d?.scope && <p className="text-xs text-neutral-500 mt-1">Scope: {d.scope}</p>}
      </PageHeader>
      <QueryState loading={q.isLoading} error={q.error} what="data status" />
      {d && (
        <>
          <Card title="Unresolved data issues" subtitle="Blockers stop the affected data from being used">
            {d.issues.length === 0 ? (
              <p className="text-sm text-neutral-400">No open issues.</p>
            ) : (
              <ul className="space-y-1.5 text-xs">
                {d.issues.map((i, n) => (
                  <li key={i.issue_id ?? `${i.kind}-${n}`} className="flex flex-wrap items-start gap-2">
                    <Pill text={i.severity} tone={i.severity === "BLOCKER" ? "red" : "amber"} />
                    <span className="font-mono text-neutral-300">{i.kind}</span>
                    <span className="text-neutral-400">{i.detail}</span>
                    {i.created_at_utc && <span className="text-neutral-600">{formatInstant(i.created_at_utc, market)}</span>}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Providers and coverage" subtitle={d.store === "PRESENT" ? "From the A-share store" : "No data store yet"}>
            <div className="space-y-4">
              {d.providers.map((p) => (
                <div key={p.source_id}>
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <span className="font-medium text-neutral-100">{p.name}</span>
                    <span className="text-xs text-neutral-500">{p.access}</span>
                    <Pill text={`presentation ${p.presentation}`} />
                    {p.credential !== "NOT_REQUIRED" && (
                      <Pill text={`token ${p.credential.toLowerCase()}`} tone={p.credential === "PRESENT" ? "green" : "amber"} />
                    )}
                    <span className="text-xs text-neutral-500">Last update: {formatInstant(p.last_update_utc, market)}</span>
                  </div>
                  {p.datasets.length === 0 ? (
                    <p className="mt-1 text-xs text-neutral-500">Nothing ingested from this provider.</p>
                  ) : (
                    <table className="mt-2 w-full text-xs">
                      <thead className="text-neutral-500">
                        <tr>
                          <th className="text-left font-normal">Dataset</th>
                          <th className="text-right font-normal">Rows</th>
                          <th className="text-left font-normal pl-3">Coverage</th>
                          <th className="text-left font-normal pl-3">Label</th>
                        </tr>
                      </thead>
                      <tbody className="text-neutral-200">
                        {p.datasets.map((ds) => (
                          <tr key={`${ds.dataset}-${ds.sample_label}`}>
                            <td>{ds.dataset}</td>
                            <td className="text-right">{ds.rows.toLocaleString()}</td>
                            <td className="pl-3 text-neutral-400">
                              {ds.symbols !== undefined ? `${ds.symbols} symbols, ${ds.first_date} – ${ds.last_date}` : "—"}
                            </td>
                            <td className="pl-3">
                              <LabelPill text={ds.sample_label} />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              ))}
            </div>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Trading calendar" subtitle={`Exchange calendar, ${market.timezone}`}>
              {d.calendar.length === 0 ? (
                <p className="text-sm text-neutral-400">No calendar stored.</p>
              ) : (
                <ul className="space-y-1 text-xs text-neutral-300">
                  {d.calendar.map((c) => (
                    <li key={`${c.provider}-${c.exchange}`}>
                      {c.exchange} via {c.provider}: {c.open_days} open days, {c.first_day} – {c.last_day} (last open {c.last_open_day})
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card title="Provider cross-check" subtitle="Every difference between providers is explained or flagged">
              {!d.crosscheck ? (
                <p className="text-sm text-neutral-400">No cross-check recorded.</p>
              ) : (
                <div className="text-xs text-neutral-300 space-y-1">
                  <p>
                    {d.crosscheck.providers.join(" vs ")} · {d.crosscheck.days_compared.toLocaleString()} days ·{" "}
                    {formatInstant(d.crosscheck.created_at_utc, market)}
                  </p>
                  <p>
                    {d.crosscheck.all_explained ? (
                      <Pill text="ALL EXPLAINED" tone="green" />
                    ) : (
                      <Pill text="UNEXPLAINED DIFFERENCES" tone="red" />
                    )}
                  </p>
                  <ul>
                    {Object.entries(d.crosscheck.counts).map(([k, v]) => (
                      <li key={k} className={k in d.crosscheck!.unexplained ? "text-red-300" : "text-neutral-400"}>
                        {k}: {v.toLocaleString()}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
