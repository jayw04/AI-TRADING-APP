import { useCallback, useEffect, useState } from "react";
import { driftApi, type DriftStatus } from "@/api/drift";

interface Props {
  strategyId: number;
}

function pct(v: number | undefined): string {
  return typeof v === "number" ? `${(v * 100).toFixed(1)}%` : "—";
}

/**
 * P6b §1b-drift — drift status card on the strategy detail page. Shows whether
 * the strategy's recent live behavior has diverged from its backtest baseline,
 * with a "Re-check now" button (the on-demand mitigation for the "audit records
 * findings, not check-runs" ambiguity).
 *
 * Plain useState/useEffect (not React Query) to match the strategy detail page,
 * which manages its own data without a QueryClientProvider (cf. CooldownIndicator).
 */
export function DriftCard({ strategyId }: Props) {
  const [status, setStatus] = useState<DriftStatus | null>(null);
  const [checking, setChecking] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setStatus(await driftApi.status(strategyId, 7));
    } catch {
      /* best-effort; the card is advisory */
    }
  }, [strategyId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function handleCheck() {
    setChecking(true);
    try {
      await driftApi.check(strategyId);
      await refresh();
    } catch {
      /* ignore */
    } finally {
      setChecking(false);
    }
  }

  const p = status?.status === "drift_detected" ? status.payload : undefined;

  return (
    <div className="rounded border border-neutral-800 bg-neutral-950 p-3">
      <div className="flex items-center justify-between">
        <div className="text-xs font-semibold uppercase tracking-wide text-neutral-300">
          Drift vs backtest
        </div>
        <button
          type="button"
          onClick={handleCheck}
          disabled={checking}
          className="rounded border border-neutral-700 px-2 py-1 text-[10px] text-neutral-200 hover:bg-neutral-800 disabled:opacity-50"
        >
          {checking ? "Checking…" : "Re-check now"}
        </button>
      </div>

      {!status && <div className="mt-2 text-[11px] text-neutral-500">Loading…</div>}

      {status && !p && (
        <div className="mt-2 text-[11px] text-neutral-400">
          No drift detected in the last {status.lookback_days} days — behaving as
          backtested.
        </div>
      )}

      {p && (
        <div className="mt-2 space-y-1 text-[11px] text-amber-200">
          <div className="font-semibold text-amber-100">
            ⚠ Drift detected{" "}
            <span className="font-normal text-amber-300/70">
              ({new Date(p.detected_at).toLocaleDateString()})
            </span>
          </div>
          {p.breached.includes("win_rate") && (
            <div>
              Win rate {pct(p.win_rate.live)} vs {pct(p.win_rate.baseline)} baseline (
              {p.win_rate.delta_pp.toFixed(1)}pp)
            </div>
          )}
          {p.breached.includes("avg_return_per_trade") && (
            <div>
              Avg return/trade {pct(p.avg_return_per_trade.live)} vs{" "}
              {pct(p.avg_return_per_trade.baseline)} baseline (
              {p.avg_return_per_trade.delta_pct.toFixed(0)}%)
            </div>
          )}
          <div className="text-amber-300/70">
            {p.trade_count} live trades over the window.
          </div>
        </div>
      )}
    </div>
  );
}
