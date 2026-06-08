import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { OppDiscoveryMatchItem } from "@/api/types";
import { strategyTemplatesApi } from "@/api/strategyTemplates";
import { Widget, EmptyState } from "./Widget";

interface Props {
  items: OppDiscoveryMatchItem[];
  count: number;
  asOf: string;
}

export function DiscoveryMatchesWidget({ items, count, asOf }: Props) {
  const navigate = useNavigate();
  const [applying, setApplying] = useState<string | null>(null);

  async function apply(symbol: string) {
    setApplying(symbol);
    try {
      const result = await strategyTemplatesApi.applyRange(symbol);
      navigate(`/strategies/${result.id}`);
    } catch {
      setApplying(null);
    }
  }

  return (
    <Widget
      title="Discovery matches"
      count={count}
      asOf={asOf}
      helpText="Latest pre-market scheduled scan"
    >
      {items.length === 0 ? (
        <EmptyState>No scheduled-scan matches yet today</EmptyState>
      ) : (
        <ul className="divide-y divide-neutral-800 text-sm">
          {items.map((m) => (
            <li
              key={`${m.run_id}-${m.symbol}`}
              className="flex items-center justify-between gap-2 py-1.5"
            >
              <div className="min-w-0 flex-1">
                <span className="font-semibold text-neutral-100">
                  {m.symbol}
                </span>
                <span className="ml-2 text-xs text-neutral-500">
                  {m.scan_name}
                </span>
                {Object.keys(m.values).length > 0 && (
                  <span className="ml-2 font-mono text-xs text-neutral-400">
                    {Object.entries(m.values)
                      .map(([k, v]) => `${k} ${v.toFixed(2)}`)
                      .join(" · ")}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 text-xs">
                <button
                  type="button"
                  onClick={() => apply(m.symbol)}
                  disabled={applying === m.symbol}
                  title="Apply the range-trading template to this symbol"
                  className="text-blue-300 hover:underline disabled:opacity-50"
                >
                  {applying === m.symbol ? "applying…" : "apply"}
                </button>
                <Link to="/discovery" className="text-sky-400 hover:underline">
                  View
                </Link>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Widget>
  );
}
