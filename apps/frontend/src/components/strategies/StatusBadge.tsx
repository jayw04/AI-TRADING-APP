import type { StrategyStatus } from "@/api/types";

const STYLES: Record<StrategyStatus, { label: string; classes: string }> = {
  idle:     { label: "IDLE",     classes: "bg-gray-700 text-gray-200" },
  backtest: { label: "BACKTEST", classes: "bg-blue-800 text-blue-100" },
  paper:    { label: "PAPER",    classes: "bg-emerald-700 text-emerald-100" },
  pending_live: { label: "PENDING LIVE", classes: "bg-amber-800 text-amber-100" },
  live:     { label: "LIVE",     classes: "bg-red-700 text-red-100" },
  halted:   { label: "HALTED",   classes: "bg-amber-700 text-amber-100" },
  error:    { label: "ERROR",    classes: "bg-rose-800 text-rose-100" },
};

export function StatusBadge({ status }: { status: StrategyStatus }) {
  const { label, classes } = STYLES[status];
  return (
    <span className={`inline-block rounded px-2 py-0.5 text-xs font-semibold ${classes}`}>
      {label}
    </span>
  );
}
