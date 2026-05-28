import { Link } from "react-router-dom";
import type { OppSignalItem } from "@/api/types";
import { Widget, EmptyState } from "./Widget";

interface Props {
  items: OppSignalItem[];
  count: number;
  asOf: string;
}

export function PineAlertsWidget({ items, count, asOf }: Props) {
  return (
    <Widget
      title="Pine alerts"
      count={count}
      asOf={asOf}
      helpText="TradingView webhooks, last 30 min"
    >
      {items.length === 0 ? (
        <EmptyState>No Pine alerts in the last 30 minutes</EmptyState>
      ) : (
        <ul className="divide-y divide-neutral-800 text-sm">
          {items.map((s) => (
            <li
              key={s.id}
              className="flex items-center justify-between gap-2 py-1.5"
            >
              <div className="min-w-0 flex-1">
                <span className="font-semibold text-neutral-100">
                  {s.symbol}
                </span>
                {s.side && (
                  <span
                    className={`ml-2 ${
                      s.side === "buy" || s.side === "long"
                        ? "text-emerald-400"
                        : s.side === "sell" || s.side === "short"
                          ? "text-rose-400"
                          : "text-neutral-400"
                    }`}
                  >
                    {s.side.toUpperCase()}
                  </span>
                )}
                {s.reason && (
                  <span className="ml-2 text-xs text-neutral-400">
                    — {s.reason}
                  </span>
                )}
                {s.strategy_name && (
                  <span className="ml-2 text-xs text-neutral-500">
                    bound to {s.strategy_name}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 text-xs">
                <span className="text-neutral-500">
                  {new Date(s.received_at).toLocaleTimeString()}
                </span>
                <Link
                  to="/orders"
                  className="text-sky-400 hover:underline"
                >
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
