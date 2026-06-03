import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { morningBriefApi } from "@/api/morningBrief";
import type { MorningBrief, SymbolObservation } from "@/api/morningBrief";
import { driftApi } from "@/api/drift";

const BIAS_ORDER = ["bullish", "bearish", "neutral"] as const;

function biasClass(bias: string): string {
  if (bias === "bullish") return "bg-emerald-900/60 text-emerald-200";
  if (bias === "bearish") return "bg-rose-900/60 text-rose-200";
  return "bg-neutral-800 text-neutral-300";
}

function counts(brief: MorningBrief): Record<string, number> {
  const c: Record<string, number> = { bullish: 0, bearish: 0, neutral: 0 };
  for (const o of brief.symbols) c[o.bias] = (c[o.bias] ?? 0) + 1;
  return c;
}

function SymbolRow({
  obs,
  priorBias,
}: {
  obs: SymbolObservation;
  priorBias?: string;
}) {
  const [open, setOpen] = useState(false);
  const changed = priorBias !== undefined && priorBias !== obs.bias;
  return (
    <li className="py-1.5">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between text-left"
      >
        <div className="flex items-center gap-2">
          <span className="font-semibold text-neutral-100">{obs.symbol}</span>
          <span
            className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${biasClass(obs.bias)}`}
          >
            {obs.bias}
          </span>
          {changed && (
            <span className="text-[10px] text-neutral-500">was {priorBias}</span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {obs.key_level !== null && (
            <span className="font-mono text-xs text-neutral-300">{obs.key_level}</span>
          )}
          <span className="text-[11px] text-neutral-500">{open ? "−" : "+"}</span>
        </div>
      </button>
      {obs.watch_for && (
        <div className="mt-0.5 text-[11px] text-neutral-500">{obs.watch_for}</div>
      )}
      {open && (
        <pre className="mt-1 overflow-x-auto rounded bg-neutral-950 p-2 text-[10px] text-neutral-400">
          {JSON.stringify(obs.indicators, null, 2)}
        </pre>
      )}
    </li>
  );
}

export default function MorningBriefCard() {
  const queryClient = useQueryClient();
  const [compare, setCompare] = useState(false);

  const today = useQuery({
    queryKey: ["morning-brief", "today"],
    queryFn: morningBriefApi.today,
    retry: false,
  });
  const recent = useQuery({
    queryKey: ["morning-brief", "recent"],
    queryFn: () => morningBriefApi.recent(2),
    enabled: compare,
    retry: false,
  });

  const regenerate = useMutation({
    mutationFn: morningBriefApi.generate,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["morning-brief"] }),
  });

  // P6b §1b-drift: recent drift findings across the user's strategies — one
  // call (no per-strategy fan-out). Renders only when findings exist.
  const drift = useQuery({
    queryKey: ["drift-findings"],
    queryFn: () => driftApi.findings(10),
    retry: false,
  });
  const driftItems = drift.data?.items ?? [];

  const brief = today.data ?? null;

  // Map symbol -> prior bias from yesterday's brief (recent[1]).
  const priorBias = useMemo<Record<string, string>>(() => {
    const out: Record<string, string> = {};
    const yesterday = recent.data?.[1];
    if (yesterday) for (const o of yesterday.symbols) out[o.symbol] = o.bias;
    return out;
  }, [recent.data]);

  return (
    <section className="rounded-lg border border-neutral-800 bg-neutral-900 p-6">
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-neutral-300">
          Morning Brief
          {brief && (
            <span className="ml-2 text-[11px] normal-case text-neutral-500">
              {brief.brief_date}
            </span>
          )}
        </h3>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-1 text-[11px] text-neutral-400">
            <input
              type="checkbox"
              checked={compare}
              onChange={(e) => setCompare(e.target.checked)}
            />
            Compare to yesterday
          </label>
          <button
            type="button"
            onClick={() => regenerate.mutate()}
            disabled={regenerate.isPending}
            className="rounded bg-blue-700 px-2 py-1 text-[11px] font-semibold text-white hover:bg-blue-600 disabled:bg-neutral-700"
          >
            {regenerate.isPending ? "Generating…" : "Regenerate"}
          </button>
        </div>
      </div>

      {driftItems.length > 0 && (
        <div className="mt-3 rounded border border-amber-800 bg-amber-950/20 p-3">
          <div className="text-[10px] uppercase tracking-wider text-amber-300">
            Strategy drift detected ({driftItems.length})
          </div>
          <p className="mt-0.5 text-[11px] text-amber-300/70">
            Live behavior diverges from backtest baseline.
          </p>
          <ul className="mt-1 space-y-1">
            {driftItems.map((f) => (
              <li key={f.audit_id} className="text-[11px] text-amber-200">
                <Link
                  to={`/strategies/${f.strategy_id}`}
                  className="font-semibold hover:underline"
                >
                  Strategy #{f.strategy_id}
                </Link>{" "}
                — {f.breached.join(", ")} diverged from backtest
              </li>
            ))}
          </ul>
        </div>
      )}

      {today.isLoading && (
        <p className="mt-2 text-sm text-neutral-400">Loading…</p>
      )}

      {!today.isLoading && !brief && (
        <div className="mt-3 text-sm text-neutral-400">
          No brief yet for today.{" "}
          <button
            type="button"
            onClick={() => regenerate.mutate()}
            className="text-blue-400 hover:underline"
          >
            Generate one
          </button>
          .
        </div>
      )}

      {brief && (
        <>
          <div className="mt-3 flex gap-2">
            {BIAS_ORDER.map((b) => (
              <span
                key={b}
                className={`rounded px-2 py-0.5 text-xs font-semibold ${biasClass(b)}`}
              >
                {counts(brief)[b] ?? 0} {b}
              </span>
            ))}
          </div>

          {brief.symbols.length === 0 ? (
            <p className="mt-3 text-sm text-neutral-500">
              No watchlist symbols. Add some in Settings → Trading Profile.
            </p>
          ) : (
            <ul className="mt-3 divide-y divide-neutral-800">
              {brief.symbols.map((o) => (
                <SymbolRow key={o.symbol} obs={o} priorBias={priorBias[o.symbol]} />
              ))}
            </ul>
          )}

          {brief.overall_note && (
            <div className="mt-4 rounded border border-neutral-800 bg-neutral-950 p-3">
              <div className="text-[10px] uppercase tracking-wider text-neutral-500">
                AI-generated note
              </div>
              <p className="mt-1 text-sm italic text-neutral-300">
                {brief.overall_note}
              </p>
            </div>
          )}
        </>
      )}
    </section>
  );
}
