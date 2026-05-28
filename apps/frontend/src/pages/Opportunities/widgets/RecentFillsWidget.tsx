import { Link } from "react-router-dom";
import type { OppFillItem } from "@/api/types";
import { Widget, EmptyState } from "./Widget";

interface Props {
  items: OppFillItem[];
  count: number;
  asOf: string;
}

export function RecentFillsWidget({ items, count, asOf }: Props) {
  return (
    <Widget
      title="Recent fills"
      count={count}
      asOf={asOf}
      helpText="Executed trades, last 15 min"
    >
      {items.length === 0 ? (
        <EmptyState>No fills in the last 15 minutes</EmptyState>
      ) : (
        <ul className="divide-y divide-neutral-800 text-sm">
          {items.map((f) => (
            <li
              key={f.id}
              className="flex items-center justify-between gap-2 py-1.5"
            >
              <div className="min-w-0 flex-1">
                <span
                  className={
                    f.side === "buy" ? "text-emerald-400" : "text-rose-400"
                  }
                >
                  {f.side.toUpperCase()}
                </span>{" "}
                <span className="font-semibold text-neutral-100">
                  {f.symbol}
                </span>
                <span className="ml-1 text-xs text-neutral-400">
                  ×{f.qty} @ ${parseFloat(f.price).toFixed(2)}
                </span>
                {f.strategy_name && (
                  <span className="ml-2 text-xs text-neutral-500">
                    via {f.strategy_name}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 text-xs">
                <span className="text-neutral-500">
                  {new Date(f.filled_at).toLocaleTimeString()}
                </span>
                <Link to="/orders" className="text-sky-400 hover:underline">
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
