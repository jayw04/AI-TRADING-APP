import { Link } from "react-router-dom";
import type { OppDiscoveryMatchItem } from "@/api/types";
import { Widget, EmptyState } from "./Widget";

interface Props {
  items: OppDiscoveryMatchItem[];
  count: number;
  asOf: string;
}

export function DiscoveryMatchesWidget({ items, count, asOf }: Props) {
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
              <Link to="/discovery" className="text-xs text-sky-400 hover:underline">
                View
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Widget>
  );
}
