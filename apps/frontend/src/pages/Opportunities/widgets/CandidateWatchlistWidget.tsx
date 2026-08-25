import { useMemo, useState } from "react";
import type {
  OppCandidateWatchlistWidget,
  OppWatchlistFamily,
  OppWatchlistItem,
} from "@/api/types";
import {
  HIDDEN_UNBACKTESTED,
  isPatternValidatedStatus,
} from "../backtestedDisplay";

type TabId = "ALL" | "OVERSOLD" | "MOMENTUM" | "GAP";

const TABS: { id: TabId; label: string }[] = [
  { id: "ALL", label: "All" },
  { id: "OVERSOLD", label: "Oversold" },
  { id: "MOMENTUM", label: "Momentum" },
  { id: "GAP", label: "Gap" },
];

function statusClass(status: string): string {
  if (status.startsWith("Source: MOM-001")) return "text-emerald-300";
  if (status === "Backtest Pending") return "text-amber-300";
  return "text-sky-300";
}

function fmtClose(v: number | null): string {
  if (v == null) return "—";
  return `$${v.toFixed(2)}`;
}

function listed(items: OppWatchlistItem[]): OppWatchlistItem[] {
  return items.filter((row) => isPatternValidatedStatus(row.status));
}

function familyUnavailable(
  families: Record<string, OppWatchlistFamily>,
  ids: string[],
): string | null {
  const reasons = ids
    .map((id) => families[id])
    .filter((f) => f && !f.available)
    .map((f) => `${f.operator_name} unavailable: ${f.unavailable_reason ?? "missing inputs"}`);
  return reasons.length ? reasons.join(" · ") : null;
}

function tabItems(
  tab: TabId,
  watchlist: OppCandidateWatchlistWidget,
): { items: OppWatchlistItem[]; unavailable: string | null; emptyHint: string } {
  const fam = watchlist.families;
  if (tab === "ALL") {
    const reasons = ["OVERSOLD", "MOM-NEAR", "MOM-CORE", "GAP"]
      .map((id) => fam[id])
      .filter((f) => f && !f.available)
      .map((f) => f.operator_name);
    return {
      items: listed(watchlist.all_items),
      unavailable: reasons.length
        ? `Hidden from All (unavailable): ${reasons.join(", ")}`
        : null,
      emptyHint: "No pattern-validated names today.",
    };
  }
  if (tab === "OVERSOLD") {
    return {
      items: [],
      unavailable: familyUnavailable(fam, ["OVERSOLD"]),
      emptyHint: "Oversold is Watch only — not listed until backtested.",
    };
  }
  if (tab === "GAP") {
    return {
      items: [],
      unavailable: familyUnavailable(fam, ["GAP"]),
      emptyHint: "Gap is Backtest Pending — not listed.",
    };
  }
  const core = fam["MOM-CORE"];
  const items = listed(core?.available ? core.items : []);
  return {
    items,
    unavailable: familyUnavailable(fam, ["MOM-CORE"]),
    emptyHint: "No pattern-validated momentum names today.",
  };
}

function tabCount(tab: TabId, watchlist: OppCandidateWatchlistWidget): number {
  return tabItems(tab, watchlist).items.length;
}

export function CandidateWatchlistWidget({
  watchlist,
}: {
  watchlist: OppCandidateWatchlistWidget | null;
}) {
  const [tab, setTab] = useState<TabId>("ALL");
  const [open, setOpen] = useState<string | null>(null);

  const session = watchlist?.as_of_session;
  const { items, unavailable, emptyHint } = useMemo(
    () =>
      watchlist
        ? tabItems(tab, watchlist)
        : { items: [], unavailable: "Candidate watchlist not loaded", emptyHint: "" },
    [tab, watchlist],
  );

  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-3">
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-neutral-100">
            Candidate Watchlist
          </h3>
          <div className="text-[10px] text-neutral-500">
            {watchlist?.subtitle ?? "Watch, not a signal"}
            {session ? ` · as-of ${session} close` : ""}
            {watchlist?.vix != null ? ` · VIX ${watchlist.vix}` : ""}
            {watchlist?.universe_id ? ` · ${watchlist.universe_id}` : ""}
          </div>
        </div>
        <div className="text-[10px] text-neutral-500">
          {watchlist?.screen_id} {watchlist?.screen_version}
        </div>
      </div>

      <div className="mb-3 flex flex-wrap gap-1">
        {TABS.map((t) => {
          const count = watchlist ? tabCount(t.id, watchlist) : 0;
          const active = tab === t.id;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`rounded px-2 py-1 text-xs ${
                active
                  ? "bg-sky-800 text-white"
                  : "bg-neutral-800 text-neutral-300 hover:bg-neutral-700"
              }`}
            >
              {t.label}
              <span className="ml-1 text-[10px] opacity-80">{count}</span>
            </button>
          );
        })}
      </div>

      {unavailable && (
        <div className="mb-2 rounded border border-amber-800 bg-amber-950/40 px-2 py-1 text-[10px] text-amber-200">
          {unavailable}
        </div>
      )}

      {items.length === 0 ? (
        <div className="py-3 text-center text-xs text-neutral-500">
          {emptyHint}
        </div>
      ) : (
        <ul className="divide-y divide-neutral-800 text-sm">
          {items.map((row) => {
            const key = `${row.symbol}-${row.family_ids.join(",")}`;
            const expanded = open === key;
            return (
              <li key={key} className="py-1.5">
                <button
                  type="button"
                  onClick={() => setOpen(expanded ? null : key)}
                  className="w-full text-left"
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <div className="min-w-0">
                      <span className="font-semibold text-neutral-100">
                        {row.symbol}
                      </span>
                      <span className="ml-2 text-[10px] uppercase tracking-wide text-neutral-500">
                        {row.family_ids.join(" · ")} · {row.horizon}
                      </span>
                    </div>
                    <span className={`shrink-0 text-[10px] ${statusClass(row.status)}`}>
                      {row.status}
                    </span>
                  </div>
                  <div className="mt-0.5 font-mono text-[10px] text-neutral-400">
                    {row.chips.map((c) => c.value).join(" · ")}
                  </div>
                </button>
                {expanded && (
                  <div className="mt-1 rounded border border-neutral-800 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-400">
                    <p>{row.why}</p>
                    <p className="mt-1">
                      {fmtClose(row.close)} · tradability: {row.tradability}
                    </p>
                    <p className="mt-1 font-mono text-[10px] text-neutral-600">
                      {row.price_source}
                      {row.name ? ` · ${row.name}` : ""}
                    </p>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <div className="mt-2 text-[10px] text-neutral-600">
        Candidates only. Does not enter the order path. {HIDDEN_UNBACKTESTED}
      </div>
    </div>
  );
}
