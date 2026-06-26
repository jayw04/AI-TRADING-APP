import type { EvaluationResults } from "@/api/proposals";

const EVAL_BADGE_CLASS: Record<string, string> = {
  complete: "bg-green-900/50 text-green-300",
  running: "bg-yellow-900/50 text-yellow-300",
  pending: "bg-yellow-900/50 text-yellow-300",
  skipped: "bg-neutral-800 text-neutral-400",
  failed: "bg-red-900/50 text-red-300",
};

// E4: a verdict requires evidence. Zero-trade evals are insufficient/needs-review,
// never a silent "above baseline".
const VERDICT_LABEL: Record<string, string> = {
  above_baseline: "Above baseline",
  below_baseline: "Below baseline",
  insufficient_evidence: "Insufficient evidence",
  needs_review: "Needs review",
};

const VERDICT_LINE: Record<string, string> = {
  above_baseline: "Above baseline ✓",
  below_baseline: "Below baseline ✗",
  insufficient_evidence: "Insufficient evidence — no trades on either side ⚠",
  needs_review: "Needs review — only the variant traded ⚠",
};

function badgeLabel(ev: EvaluationResults): string {
  switch (ev.status) {
    case "complete":
      return VERDICT_LABEL[ev.verdict ?? ""] ?? "Below baseline";
    case "running":
      return "Backtest running";
    case "pending":
      return "Backtest pending";
    case "skipped":
      return `Eval skipped`;
    case "failed":
      return "Eval failed";
    default:
      return "No eval";
  }
}

export function EvalBadge({ ev }: { ev: EvaluationResults }) {
  if (!ev || !ev.status) return null;
  const cls = EVAL_BADGE_CLASS[ev.status] ?? "bg-neutral-800 text-neutral-400";
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${cls}`}>
      {badgeLabel(ev)}
    </span>
  );
}

const METRIC_ROWS = ["sharpe_ratio", "max_drawdown", "total_return", "win_rate"];

export function EvalPanel({ ev }: { ev: EvaluationResults }) {
  if (!ev || !ev.status) return null;

  if (ev.status === "skipped") {
    return (
      <div className="mt-2 rounded border border-neutral-800 bg-neutral-950 p-2 text-xs text-neutral-400">
        <span className="font-medium text-neutral-300">Evaluation</span> — skipped
        {ev.skipped_reason ? ` (${ev.skipped_reason})` : ""}.
      </div>
    );
  }
  if (ev.status === "failed") {
    return (
      <div className="mt-2 rounded border border-red-900/50 bg-neutral-950 p-2 text-xs text-red-300">
        <span className="font-medium">Evaluation failed</span>
        {ev.failure_reason ? `: ${ev.failure_reason}` : ""}.
      </div>
    );
  }
  if (ev.status === "pending" || ev.status === "running") {
    return (
      <div className="mt-2 rounded border border-neutral-800 bg-neutral-950 p-2 text-xs text-neutral-400">
        Backtest in progress (window: {ev.window_days ?? 90} days). Refresh in a
        minute.
      </div>
    );
  }

  // complete
  const num = (v: number | undefined) => (typeof v === "number" ? v.toFixed(3) : "—");
  return (
    <div className="mt-2 rounded border border-neutral-800 bg-neutral-950 p-3 text-xs">
      <div className="font-medium text-neutral-200">
        Evaluation — {VERDICT_LINE[ev.verdict ?? ""] ?? "Below baseline ✗"}
      </div>
      <table className="mt-2 w-full text-left">
        <thead className="text-neutral-500">
          <tr>
            <th className="pr-2">Metric</th>
            <th className="pr-2">Baseline</th>
            <th className="pr-2">Variant</th>
            <th>Δ</th>
          </tr>
        </thead>
        <tbody className="text-neutral-300">
          {METRIC_ROWS.map((m) => (
            <tr key={m}>
              <td className="pr-2 font-mono">{m}</td>
              <td className="pr-2 font-mono">{num(ev.baseline_metrics?.[m])}</td>
              <td className="pr-2 font-mono">{num(ev.variant_metrics?.[m])}</td>
              <td className="font-mono">{num(ev.delta_metrics?.[`${m}_delta`])}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {ev.completed_at && (
        <p className="mt-1 text-neutral-500">
          Backtested over {ev.window_days ?? 90} days.
        </p>
      )}
    </div>
  );
}
