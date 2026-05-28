import { Link } from "react-router-dom";
import type { OppRiskRejectItem } from "@/api/types";
import { Widget, EmptyState } from "./Widget";

interface Props {
  items: OppRiskRejectItem[];
  count: number;
  asOf: string;
}

export function RiskRejectionsWidget({ items, count, asOf }: Props) {
  return (
    <Widget
      title="Risk rejections"
      count={count}
      asOf={asOf}
      helpText="Orders rejected by Risk Engine, last 60 min"
    >
      {items.length === 0 ? (
        <EmptyState>No risk rejections in the last hour</EmptyState>
      ) : (
        <ul className="divide-y divide-neutral-800 text-sm">
          {items.map((r) => (
            <li
              key={r.id}
              className="flex items-center justify-between gap-2 py-1.5"
            >
              <div className="min-w-0 flex-1">
                {r.symbol && (
                  <span className="font-semibold text-neutral-100">
                    {r.symbol}
                  </span>
                )}
                <span className="ml-2 text-xs text-rose-400">
                  {r.reason_codes.join(", ") || "rejected"}
                </span>
              </div>
              <div className="flex items-center gap-2 text-xs">
                <span className="text-neutral-500">
                  {new Date(r.evaluated_at).toLocaleTimeString()}
                </span>
                {r.order_id && (
                  <Link
                    to="/orders"
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
