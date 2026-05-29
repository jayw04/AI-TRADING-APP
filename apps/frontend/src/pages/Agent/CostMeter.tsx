import type { AgentBudget } from "@/api/types";

/**
 * Daily-budget meter for the chat panel header.
 *
 * Colors track usage: emerald < 50%, amber 50–80%, rose >= 80%.
 */
export function CostMeter({ budget }: { budget: AgentBudget }) {
  const pct = budget.pct_used;
  const spent = parseFloat(budget.spent_usd);
  const total = parseFloat(budget.budget_usd);

  let barColor = "bg-emerald-500";
  let textColor = "text-emerald-400";
  if (pct >= 80) {
    barColor = "bg-rose-500";
    textColor = "text-rose-400";
  } else if (pct >= 50) {
    barColor = "bg-amber-500";
    textColor = "text-amber-400";
  }

  return (
    <div>
      <div className={`text-[10px] ${textColor}`}>
        ${spent.toFixed(2)} / ${total.toFixed(2)} today
      </div>
      <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-gray-800">
        <div
          className={`h-full ${barColor}`}
          style={{ width: `${Math.min(100, pct)}%` }}
        />
      </div>
    </div>
  );
}
