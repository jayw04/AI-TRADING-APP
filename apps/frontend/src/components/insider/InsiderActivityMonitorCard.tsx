import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  insiderReferenceApi,
  type InsiderReferenceRow,
} from "@/api/insiderReference";

// Insider Activity Monitor — Reference Only (plan v1.0, owner-locked rules):
// - the reference-only language block is ALWAYS visible (never a tooltip)
// - rows render in the API's order (filed_at DESC) — no client-side re-sorting
// - forbidden UI: Buy / Sell / Signal / Alpha / Conviction / Recommendation / Rank / Score /
//   attach-to-strategy / create-order. Ticker links go to the chart page ONLY.

function money(v: number | null): string {
  if (v == null) return "—";
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `$${(v / 1_000).toFixed(0)}k`;
  return `$${v.toFixed(0)}`;
}

function freshness(hours: number): string {
  if (hours < 24) return `${Math.max(1, Math.round(hours))}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

function contextLine(r: InsiderReferenceRow): string {
  const bits: string[] = [];
  if (r.pct_of_marketcap != null) bits.push(`${r.pct_of_marketcap.toFixed(2)}% of mktcap`);
  if (r.pct_of_adv != null) bits.push(`${r.pct_of_adv.toFixed(0)}% of ADV`);
  if (r.sector) bits.push(r.sector);
  if (r.size_bucket) bits.push(r.size_bucket);
  return bits.join(" · ");
}

export default function InsiderActivityMonitorCard() {
  const q = useQuery({
    queryKey: ["insider-reference"],
    queryFn: () => insiderReferenceApi.list(14),
    refetchInterval: 5 * 60_000,
  });
  const data = q.data;

  return (
    <section className="rounded-lg bg-neutral-900 border border-neutral-800 p-6">
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-neutral-300 uppercase tracking-wide">
          Insider Activity Monitor — Reference Only
        </h3>
        {data?.universe_as_of && (
          <span className="text-[11px] text-neutral-500">
            universe {data.universe_size ?? "—"} names · {data.universe_as_of}
          </span>
        )}
      </div>

      {/* Required language block — always visible, never a tooltip (owner-locked). */}
      <div className="mt-2 rounded border border-amber-900/60 bg-amber-950/30 px-3 py-2 text-[12px] text-amber-200/90">
        Reference Only — INSIDER-001 found no standalone residual alpha.
        <br />
        Not a validated trading signal. Not used for ranking, sizing, or orders.{" "}
        <a
          className="underline text-amber-300/80 hover:text-amber-200"
          href="https://github.com/jayw04/AI-TRADING-APP/tree/main/docs/implementation/evidence/insider_001_s4_reproduction"
          target="_blank"
          rel="noreferrer"
        >
          INSIDER-001 evidence
        </a>
      </div>

      {q.isLoading && <p className="text-neutral-400 text-sm mt-3">Loading…</p>}
      {q.isError && (
        <p className="text-neutral-500 text-sm mt-3">
          Monitor unavailable right now (the surface degrades, it never blocks anything).
        </p>
      )}
      {data && data.rows.length === 0 && (
        <p className="text-neutral-500 text-sm mt-3">
          No qualifying open-market insider buys in the last 14 days — sparse is normal
          (frequently 0/day).
        </p>
      )}

      {data && data.rows.length > 0 && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[11px] uppercase tracking-wider text-neutral-500 text-left">
                <th className="py-1 pr-4 font-medium">Ticker</th>
                <th className="py-1 pr-4 font-medium">Insider (role)</th>
                <th className="py-1 pr-4 font-medium text-right">Value</th>
                <th className="py-1 pr-4 font-medium">Context</th>
                <th className="py-1 pr-4 font-medium text-center">Cluster</th>
                <th className="py-1 font-medium text-right">Filed</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-800">
              {data.rows.map((r) => (
                <tr key={`${r.ticker}-${r.filed_at}-${r.insider_name ?? ""}`}>
                  <td className="py-1.5 pr-4">
                    {/* chart link ONLY — no order-ticket links from this surface */}
                    <Link
                      to={`/charts?symbol=${encodeURIComponent(r.ticker)}`}
                      className="font-semibold text-neutral-100 hover:text-white underline decoration-neutral-700"
                    >
                      {r.ticker}
                    </Link>
                    {r.company && (
                      <span className="ml-2 text-[11px] text-neutral-500">{r.company}</span>
                    )}
                  </td>
                  <td className="py-1.5 pr-4 text-neutral-300">
                    {r.insider_name ?? "—"}{" "}
                    <span className="text-[11px] text-neutral-500">({r.insider_role})</span>
                  </td>
                  <td className="py-1.5 pr-4 text-right font-mono text-neutral-200">
                    {money(r.transaction_value)}
                  </td>
                  <td className="py-1.5 pr-4 text-[11px] text-neutral-500">
                    {contextLine(r) || "—"}
                  </td>
                  <td className="py-1.5 pr-4 text-center">
                    {r.cluster_count >= 2 ? (
                      <span className="inline-block rounded bg-neutral-800 px-1.5 py-0.5 text-[11px] text-neutral-300">
                        ×{r.cluster_count}
                      </span>
                    ) : (
                      <span className="text-neutral-600">—</span>
                    )}
                  </td>
                  <td className="py-1.5 text-right text-[11px] text-neutral-400">
                    {freshness(r.freshness_hours)}
                    {r.transaction_date && r.filing_date && r.transaction_date !== r.filing_date && (
                      <span className="text-neutral-600"> (traded {r.transaction_date})</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
