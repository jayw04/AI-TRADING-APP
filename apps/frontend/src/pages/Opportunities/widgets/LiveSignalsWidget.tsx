import { Link } from "react-router-dom";
import type { OppSignalItem } from "@/api/types";
import { Widget, EmptyState } from "./Widget";

interface Props {
  items: OppSignalItem[];
  count: number;
  asOf: string;
}

export function LiveSignalsWidget({ items, count, asOf }: Props) {
  return (
    <Widget
      title="Live signals"
      count={count}
      asOf={asOf}
      helpText="Strategy signals, last 30 min"
    >
      {items.length === 0 ? (
        <EmptyState>No signals in the last 30 minutes</EmptyState>
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
                </span>{" "}
                <span
                  className={
                    s.type === "entry"
                      ? "text-emerald-400"
                      : s.type === "exit"
                        ? "text-rose-400"
                        : "text-neutral-400"
                  }
                >
                  {s.type}
                </span>
                {s.strategy_name && (
                  <span className="ml-2 text-xs text-neutral-500">
                    via {s.strategy_name}
                  </span>
                )}
                {s.reason && (
                  <span className="ml-2 text-xs text-neutral-400">
                    — {s.reason}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 text-xs">
                <span className="text-neutral-500">
                  {new Date(s.received_at).toLocaleTimeString()}
                </span>
                {s.strategy_id !== null && (
                  <Link
                    to={`/strategies/${s.strategy_id}`}
                    className="text-sky-400 hover:underline"
                  >
                    View
                  </Link>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Widget>
  );
}
