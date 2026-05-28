import { Link } from "react-router-dom";
import type { OppOpenOrderItem } from "@/api/types";
import { Widget, EmptyState } from "./Widget";

interface Props {
  items: OppOpenOrderItem[];
  count: number;
  asOf: string;
}

export function OpenOrdersExpiringWidget({ items, count, asOf }: Props) {
  return (
    <Widget
      title="Orders nearing expiry"
      count={count}
      asOf={asOf}
      helpText="DAY orders <30 min to close, or GTC ≥7 days old"
    >
      {items.length === 0 ? (
        <EmptyState>No orders nearing expiry</EmptyState>
      ) : (
        <ul className="divide-y divide-neutral-800 text-sm">
          {items.map((o) => (
            <li
              key={o.id}
              className="flex items-center justify-between gap-2 py-1.5"
            >
              <div className="min-w-0 flex-1">
                <span
                  className={
                    o.side === "buy" ? "text-emerald-400" : "text-rose-400"
                  }
                >
                  {o.side.toUpperCase()}
                </span>{" "}
                <span className="font-semibold text-neutral-100">
                  {o.symbol}
                </span>
                <span className="ml-1 text-xs text-neutral-400">
                  ×{o.qty} {o.type}
                  {o.limit_price ? ` @ $${o.limit_price}` : ""}
                </span>
                <div className="text-[10px] text-amber-400">
                  {o.expiry_reason}
                </div>
              </div>
              <Link
                to="/orders"
                className="text-xs text-sky-400 hover:underline"
              >
                View
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Widget>
  );
}
