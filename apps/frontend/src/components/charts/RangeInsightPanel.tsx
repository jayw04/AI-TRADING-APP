import { useEffect, useState } from "react";
import { ApiError } from "@/api/client";
import { rangeInsightApi, type RangeInsight } from "@/api/rangeInsight";

/**
 * P8 §6 — Range Insight panel (Charts right rail). Descriptive daily-range
 * statistics for the charted symbol — NOT forecasts (the disclaimer is rendered
 * verbatim). Collapsible (owns its width so it reclaims chart space when closed)
 * and refetches on symbol change. Zero-dep; reused by §7's template flow.
 */

function fmt(n: number | null | undefined): string {
  return n === null || n === undefined ? "—" : n.toFixed(2);
}
function pct(n: number | null | undefined): string {
  return n === null || n === undefined ? "—" : `${(n * 100).toFixed(1)}%`;
}

const CLASS_LABEL: Record<string, string> = {
  range_bound: "Range-bound",
  trending: "Trending",
  mixed: "Mixed",
};
const CLASS_STYLE: Record<string, string> = {
  range_bound: "bg-emerald-900/60 text-emerald-200",
  trending: "bg-amber-900/60 text-amber-200",
  mixed: "bg-neutral-800 text-neutral-300",
};

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <span className="text-xs text-neutral-500">{label}</span>
      <span className="font-mono text-sm text-neutral-200">{value}</span>
    </div>
  );
}

export default function RangeInsightPanel({ symbol }: { symbol: string }) {
  const [open, setOpen] = useState(true);
  const [data, setData] = useState<RangeInsight | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    rangeInsightApi
      .get(symbol)
      .then((d) => active && setData(d))
      .catch((e) => {
        if (!active) return;
        setData(null);
        setError(
          e instanceof ApiError && e.status === 503
            ? "Market data is unavailable right now."
            : "Could not load Range Insight.",
        );
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [symbol]);

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        title="Show Range Insight"
        aria-label="Show Range Insight"
        className="w-8 shrink-0 rounded-lg border border-neutral-800 bg-neutral-900 text-neutral-400 hover:text-neutral-200"
      >
        <span className="[writing-mode:vertical-rl] text-xs tracking-wide">
          Range Insight
        </span>
      </button>
    );
  }

  return (
    <div className="flex w-80 shrink-0 flex-col overflow-y-auto rounded-lg border border-neutral-800 bg-neutral-900">
      <div className="flex items-center justify-between border-b border-neutral-800 px-3 py-2">
        <h3 className="text-sm font-semibold text-neutral-100">
          Range Insight{" "}
          <span className="font-mono text-xs text-neutral-500">{symbol}</span>
        </h3>
        <button
          type="button"
          onClick={() => setOpen(false)}
          aria-label="Collapse Range Insight"
          className="text-neutral-500 hover:text-neutral-200"
        >
          ▸
        </button>
      </div>

      <div className="space-y-2 p-3">
        {loading && <div className="text-xs text-neutral-500">Loading…</div>}
        {error && <div className="text-xs text-rose-300">{error}</div>}

        {data && data.status === "insufficient_data" && !error && (
          <div className="text-xs text-neutral-400">
            Not enough history for {symbol} ({data.bars_used} day
            {data.bars_used === 1 ? "" : "s"}) to describe its range.
          </div>
        )}

        {data && data.status === "ok" && !error && (
          <>
            {data.classification && (
              <span
                className={`inline-block rounded px-2 py-0.5 text-[11px] font-semibold ${
                  CLASS_STYLE[data.classification] ?? CLASS_STYLE.mixed
                }`}
              >
                {CLASS_LABEL[data.classification] ?? data.classification}
              </span>
            )}

            {data.low_confidence && (
              <div className="rounded border border-amber-800 bg-amber-950/40 p-1.5 text-[11px] text-amber-200">
                Limited history ({data.bars_used} days) — interpret with caution.
              </div>
            )}

            <Row label="ATR (20d)" value={`$${fmt(data.atr20)} (${pct(data.atr20_pct)})`} />
            {data.typical_move_up && data.typical_move_down && (
              <Row
                label="Typical move (open→hi/lo)"
                value={`+$${fmt(data.typical_move_up.mean)} / −$${fmt(
                  data.typical_move_down.mean,
                )}`}
              />
            )}
            <Row label="Support / Resistance" value={`$${fmt(data.support)} / $${fmt(data.resistance)}`} />
            {data.high_band && (
              <Row
                label="Today's high (80%)"
                value={`$${fmt(data.high_band.low)}–$${fmt(data.high_band.high)}`}
              />
            )}
            {data.low_band && (
              <Row
                label="Today's low (80%)"
                value={`$${fmt(data.low_band.low)}–$${fmt(data.low_band.high)}`}
              />
            )}
            {data.intraday_range !== null && (
              <Row label="Range so far today" value={`$${fmt(data.intraday_range)}`} />
            )}
          </>
        )}

        {data && !error && (
          <p className="border-t border-neutral-800 pt-2 text-[10px] leading-snug text-neutral-500">
            {data.disclaimer}
          </p>
        )}
      </div>
    </div>
  );
}
