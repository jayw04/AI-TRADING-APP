import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { riskApi } from "@/api/risk";
import type { RiskState } from "@/api/risk";

interface Props {
  accountId: number;
  accountLabel?: string | null;
}

/**
 * P5 §5 — circuit-breaker + PDT warning banners for one account. Polls the
 * risk-state endpoint every 60s. Best-effort: renders nothing until loaded.
 */
export function RiskStateBanner({ accountId, accountLabel }: Props) {
  const { data: state } = useQuery({
    queryKey: ["risk-state", accountId],
    queryFn: () => riskApi.accountRiskState(accountId),
    refetchInterval: 60_000,
    retry: false,
  });

  if (!state) return null;

  return (
    <div className="space-y-2">
      {state.circuit_breaker.tripped && (
        <CircuitBreakerTrippedBanner
          accountId={accountId}
          accountLabel={accountLabel ?? null}
          state={state}
        />
      )}
      {state.pdt.is_at_risk && <PdtWarningBanner state={state} />}
    </div>
  );
}

function CircuitBreakerTrippedBanner({
  accountId,
  accountLabel,
  state,
}: {
  accountId: number;
  accountLabel: string | null;
  state: RiskState;
}) {
  const [resetOpen, setResetOpen] = useState(false);
  const cb = state.circuit_breaker;
  return (
    <>
      <div className="rounded border-2 border-red-700 bg-red-950/40 p-3">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-bold text-red-100">⚠ CIRCUIT BREAKER TRIPPED</div>
            <div className="mt-1 text-xs text-red-200">
              Daily loss limit reached
              {cb.tripped_at && ` on ${new Date(cb.tripped_at).toLocaleString()}`}. All
              strategies on this account have been HALTED. Order submission is rejected.
            </div>
            <div className="mt-1 text-[10px] text-red-300">
              Net PnL today: ${cb.realized_pnl_today} realized + ${cb.unrealized_pnl_now}{" "}
              unrealized. Daily loss limit: ${cb.max_daily_loss}.
            </div>
          </div>
          <button
            type="button"
            onClick={() => setResetOpen(true)}
            className="rounded border border-red-700 px-3 py-1.5 text-xs font-semibold text-red-100 hover:bg-red-900/30"
          >
            Reset…
          </button>
        </div>
      </div>
      {resetOpen && (
        <ResetCircuitBreakerModal
          accountId={accountId}
          accountLabel={accountLabel}
          onClose={() => setResetOpen(false)}
        />
      )}
    </>
  );
}

function PdtWarningBanner({ state }: { state: RiskState }) {
  const pdt = state.pdt;
  return (
    <div className="rounded border border-amber-700 bg-amber-950/30 p-3">
      <div className="text-sm font-semibold text-amber-100">⚠ Pattern Day Trader warning</div>
      <div className="mt-1 text-xs text-amber-200">
        {pdt.day_trade_count} day trades detected in the last {pdt.window_days} business days
        (threshold: {pdt.threshold}). Account equity ${pdt.account_equity ?? "?"} vs FINRA
        threshold ${pdt.equity_threshold}.
      </div>
      <div className="mt-1 text-[10px] text-amber-300">
        FINRA flags accounts at 4+ day trades / 5 business days with equity {"<"} $25,000. You own
        this decision; the workbench will not block trading.
      </div>
    </div>
  );
}

function ResetCircuitBreakerModal({
  accountId,
  accountLabel,
  onClose,
}: {
  accountId: number;
  accountLabel: string | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [confirmation, setConfirmation] = useState("");
  const label = accountLabel ?? "";

  const reset = useMutation({
    mutationFn: () => riskApi.resetCircuitBreaker(accountId, confirmation),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["risk-state", accountId] });
      onClose();
    },
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80">
      <div className="w-96 space-y-3 rounded-lg border-2 border-red-700 bg-neutral-950 p-5">
        <h2 className="text-lg font-semibold text-red-100">Reset circuit breaker</h2>
        <p className="text-sm text-neutral-300">
          Resetting re-enables order submission for this account. Strategies remain HALTED; you
          must start each one manually.
        </p>
        <p className="text-xs text-amber-200">
          Type the account label{" "}
          <code className="rounded bg-neutral-800 px-1 font-mono">{label}</code> to confirm.
        </p>
        <input
          type="text"
          value={confirmation}
          onChange={(e) => setConfirmation(e.target.value)}
          placeholder="account label"
          className="w-full rounded bg-neutral-800 px-2 py-1 font-mono text-sm text-white"
        />
        {reset.isError && (
          <div className="rounded border border-red-700 bg-red-950/40 p-2 text-xs text-red-200">
            Reset failed. Check the label and try again.
          </div>
        )}
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded bg-neutral-700 px-3 py-1.5 text-sm text-neutral-200"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => reset.mutate()}
            disabled={reset.isPending || confirmation !== label}
            className="rounded bg-red-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-red-600 disabled:bg-neutral-700"
          >
            {reset.isPending ? "Resetting…" : "Reset"}
          </button>
        </div>
      </div>
    </div>
  );
}
