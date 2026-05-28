import { Link } from "react-router-dom";
import type { OppStrategyErrorItem } from "@/api/types";
import { Widget, EmptyState } from "./Widget";

interface Props {
  items: OppStrategyErrorItem[];
  count: number;
  asOf: string;
}

export function StrategyErrorsWidget({ items, count, asOf }: Props) {
  return (
    <Widget title="Strategies in error" count={count} asOf={asOf}>
      {items.length === 0 ? (
        <EmptyState>All strategies are healthy</EmptyState>
      ) : (
        <ul className="divide-y divide-neutral-800 text-sm">
          {items.map((s) => (
            <li key={s.id} className="py-2">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-rose-300">{s.name}</span>
                <Link
                  to={`/strategies/${s.id}`}
                  className="text-xs text-sky-400 hover:underline"
                >
                  View
                </Link>
              </div>
              <div className="mt-1 text-xs text-rose-400">{s.error_text}</div>
              {s.error_first_seen && (
                <div className="mt-0.5 text-[10px] text-neutral-500">
                  Since {new Date(s.error_first_seen).toLocaleString()}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </Widget>
  );
}
