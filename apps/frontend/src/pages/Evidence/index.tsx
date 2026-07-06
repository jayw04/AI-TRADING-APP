import { useQuery } from "@tanstack/react-query";
import { evidenceApi } from "@/api/evidence";
import type { ResearchProgram, KpiRow } from "@/api/evidence";

const REFETCH_MS = 15_000;

const DOT: Record<ResearchProgram["color"], string> = {
  green: "bg-emerald-500",
  red: "bg-red-500",
  amber: "bg-amber-500",
  blue: "bg-sky-500",
  gray: "bg-neutral-500",
};

const KPI_BADGE: Record<KpiRow["status"], string> = {
  ok: "bg-emerald-900 text-emerald-300",
  watch: "bg-amber-900 text-amber-300",
  n_a: "bg-neutral-800 text-neutral-400",
};

function Card({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg bg-neutral-900 border border-neutral-800 p-5">
      <h3 className="text-base font-semibold text-neutral-100">{title}</h3>
      {subtitle && <p className="text-xs text-neutral-400 mt-0.5">{subtitle}</p>}
      <div className="mt-3">{children}</div>
    </div>
  );
}

function Bar({ label, value, weight }: { label: string; value: number; weight: number }) {
  return (
    <div className="mb-2">
      <div className="flex justify-between text-xs text-neutral-400">
        <span>{label} <span className="text-neutral-600">({Math.round(weight * 100)}%)</span></span>
        <span className="text-neutral-200">{Math.round(value)}</span>
      </div>
      <div className="h-1.5 rounded bg-neutral-800 mt-1">
        <div className="h-1.5 rounded bg-sky-500" style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
      </div>
    </div>
  );
}

export default function Evidence() {
  const q = useQuery({
    queryKey: ["evidence", "summary"],
    queryFn: evidenceApi.summary,
    refetchInterval: REFETCH_MS,
    retry: false,
  });
  const d = q.data;

  return (
    <div className="grid gap-4">
      <div className="rounded-lg bg-neutral-900 border border-neutral-800 p-6 flex items-start justify-between">
        <div>
          <h2 className="text-lg font-semibold text-neutral-100">Evidence Dashboard</h2>
          <p className="text-sm text-neutral-400 mt-1">
            The live evidence story — Production Confidence, operational KPIs, research programs, and the
            live books. Reads from the API; the report scripts remain the printable artifacts.
          </p>
        </div>
        <button
          onClick={() => window.print()}
          className="print:hidden shrink-0 rounded-md border border-neutral-700 px-3 py-1.5 text-sm text-neutral-200 hover:bg-neutral-800"
        >
          Print report
        </button>
      </div>

      {q.isLoading && <div className="text-sm text-neutral-400">Loading evidence…</div>}
      {q.isError && <div className="text-sm text-red-400">Could not load the evidence summary.</div>}

      {d && (
        <div className="grid gap-4 lg:grid-cols-2">
          {/* Production Confidence Score */}
          <Card title="Production Confidence Score" subtitle="Rises with clean operation over time">
            <div className="flex items-baseline gap-3">
              <span className="text-4xl font-bold text-neutral-100">{Math.round(d.confidence.score)}</span>
              <span className="text-neutral-500">/ 100</span>
              <span className="ml-auto rounded-md bg-neutral-800 px-2 py-0.5 text-xs text-neutral-300">
                {d.confidence.band}
              </span>
            </div>
            <div className="mt-4">
              <Bar label="Verifiability" value={d.confidence.components.verifiability} weight={d.confidence.weights.verifiability} />
              <Bar label="Safety" value={d.confidence.components.safety} weight={d.confidence.weights.safety} />
              <Bar label="Maturity" value={d.confidence.components.maturity} weight={d.confidence.weights.maturity} />
              <Bar label="Operational" value={d.confidence.components.operational} weight={d.confidence.weights.operational} />
            </div>
            <ul className="mt-3 space-y-0.5 text-xs text-neutral-400 list-disc list-inside">
              {d.confidence.rationale.map((r, i) => <li key={i}>{r}</li>)}
            </ul>
          </Card>

          {/* Research programs */}
          <Card title="Research Programs" subtitle="Every program produces a citable verdict">
            <ul className="space-y-2">
              {d.research_programs.map((p) => (
                <li key={p.id} className="flex gap-3 text-sm">
                  <span className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${DOT[p.color]}`} />
                  <div>
                    <div className="text-neutral-100">
                      <span className="font-mono text-xs text-neutral-500">{p.id}</span>{" "}
                      {p.family} <span className="text-neutral-500">· {p.status}</span>
                    </div>
                    <div className="text-xs text-neutral-400">{p.headline}</div>
                  </div>
                </li>
              ))}
            </ul>
          </Card>

          {/* Operational KPIs */}
          <Card title="Operational KPIs" subtitle={`${d.kpis.summary.ok ?? 0} ok · ${d.kpis.summary.watch ?? 0} watch · ${d.kpis.summary.n_a ?? 0} n/a`}>
            <table className="w-full text-sm">
              <tbody>
                {d.kpis.rows.map((k) => (
                  <tr key={k.key} className="border-t border-neutral-800 first:border-0">
                    <td className="py-1.5 text-neutral-300">{k.label}</td>
                    <td className="py-1.5 text-right text-neutral-100">
                      {k.value === null ? "n/a" : `${k.value}${k.unit === "%" ? "%" : ""}`}
                    </td>
                    <td className="py-1.5 pl-3 text-right">
                      <span className={`rounded px-1.5 py-0.5 text-xs ${KPI_BADGE[k.status]}`}>
                        {k.status === "n_a" ? "n/a" : k.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>

          {/* Live strategy books */}
          <Card title="Live Strategy Books" subtitle="The momentum risk dial + any other registered strategies">
            <table className="w-full text-sm">
              <tbody>
                {d.strategies.map((s) => (
                  <tr key={s.id} className="border-t border-neutral-800 first:border-0">
                    <td className="py-1.5 text-neutral-200">{s.name}</td>
                    <td className="py-1.5 text-neutral-400">{s.status}</td>
                    <td className="py-1.5 text-right text-neutral-300">
                      {s.vol_scaling && s.vol_target != null ? `vol ${Math.round(s.vol_target * 100)}%` : "—"}
                    </td>
                  </tr>
                ))}
                {d.strategies.length === 0 && (
                  <tr><td className="py-1.5 text-neutral-500">No strategies registered.</td></tr>
                )}
              </tbody>
            </table>
          </Card>
        </div>
      )}
    </div>
  );
}
