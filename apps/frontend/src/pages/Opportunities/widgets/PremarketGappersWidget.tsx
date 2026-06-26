import type { OppPremarketGapperItem } from "@/api/types";
import { Widget, EmptyState } from "./Widget";

interface Props {
  items: OppPremarketGapperItem[];
  count: number;
  asOf: string;
  scannedAt: string | null;
  date: string | null;
  stale: boolean;
}

function fmtVolume(v: number | null): string {
  if (v == null) return "—";
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(0)}K`;
  return String(v);
}

export function PremarketGappersWidget({
  items,
  count,
  scannedAt,
  date,
  stale,
}: Props) {
  return (
    <Widget
      title="Pre-market gappers"
      count={count}
      asOf={scannedAt ?? ""}
      helpText={
        date
          ? `Yahoo gainers + Benzinga catalyst · ${date}${stale ? " (stale)" : ""}`
          : "Yahoo gainers + Benzinga catalyst"
      }
    >
      {stale && items.length > 0 && (
        <div className="mb-2 rounded border border-amber-800 bg-amber-950/40 px-2 py-1 text-[10px] text-amber-200">
          Showing the last available scan — not today's pre-market.
        </div>
      )}
      {items.length === 0 ? (
        <EmptyState>
          {stale ? "No pre-market gapper scan available" : "No gappers today"}
        </EmptyState>
      ) : (
        <ul className="divide-y divide-neutral-800 text-sm">
          {items.map((g) => (
            <li key={g.symbol} className="py-1.5">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-baseline gap-2">
                  <span className="font-semibold text-neutral-100">
                    {g.symbol}
                  </span>
                  {g.gap_pct != null && (
                    <span className="font-mono text-xs font-semibold text-emerald-400">
                      +{g.gap_pct.toFixed(1)}%
                    </span>
                  )}
                </div>
                <div className="font-mono text-[10px] text-neutral-500">
                  {g.price != null ? `$${g.price.toFixed(2)}` : "—"} ·{" "}
                  {fmtVolume(g.premarket_volume)} pre-mkt vol
                </div>
              </div>
              {g.catalyst && (
                <p className="mt-0.5 line-clamp-2 text-xs text-neutral-400">
                  {g.catalyst}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </Widget>
  );
}
