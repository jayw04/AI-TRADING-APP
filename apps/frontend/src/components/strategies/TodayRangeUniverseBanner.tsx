import { Link } from "react-router-dom";
import type { Strategy } from "@/api/types";

/**
 * Shows, for each range strategy whose universe is auto-selected daily
 * (`params.auto_select_top_n > 0`), the symbols it is range-trading TODAY — so the user can
 * see at a glance what the system picked this morning, without opening each strategy.
 */

/** Top-N a strategy auto-selects daily (0 = not an auto-select strategy). */
export function autoSelectN(s: Strategy): number {
  const raw = (s.params as Record<string, unknown> | undefined)?.auto_select_top_n;
  const n = Number(raw ?? 0);
  return Number.isFinite(n) && n > 0 ? n : 0;
}

function whenLabel(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  });
}

export function TodayRangeUniverseBanner({ strategies }: { strategies: Strategy[] }) {
  const autos = strategies.filter((s) => autoSelectN(s) > 0);
  if (autos.length === 0) return null;
  return (
    <div className="rounded border border-sky-900/60 bg-sky-950/30 p-3">
      <div className="flex items-center gap-2">
        <span className="rounded bg-sky-800/70 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-sky-100">
          Auto-selected
        </span>
        <h2 className="text-sm font-semibold text-white">Today&apos;s range universe</h2>
      </div>
      <p className="mt-0.5 text-[11px] text-sky-200/70">
        The system picks the Top-N range candidates each morning — these are the symbols being
        range-traded today.
      </p>
      <div className="mt-2 grid gap-2">
        {autos.map((s) => (
          <div key={s.id} className="flex flex-wrap items-center gap-2">
            <Link
              to={`/strategies/${s.id}`}
              className="text-xs font-semibold text-sky-200 hover:underline"
            >
              {s.name}
            </Link>
            <span className="text-[10px] uppercase tracking-wider text-gray-500">
              Top {autoSelectN(s)}
            </span>
            <div className="flex flex-wrap gap-1">
              {s.symbols.length === 0 ? (
                <span className="text-xs text-gray-500">— not selected yet</span>
              ) : (
                s.symbols.map((sym) => (
                  <span
                    key={sym}
                    className="rounded bg-gray-800 px-1.5 py-0.5 font-mono text-xs text-gray-100"
                  >
                    {sym}
                  </span>
                ))
              )}
            </div>
            <span className="text-[10px] text-gray-500">updated {whenLabel(s.updated_at)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
