import { useState } from "react";
import { activationApi } from "@/api/activation";

interface Props {
  strategyId: number;
  strategyName: string;
  onClose: () => void;
  onDeactivated: () => void;
}

/**
 * P5 §7 — deactivate a LIVE/HALTED strategy (immediate; no cooldown). Optional
 * liquidation closes open positions in the strategy's symbols via the
 * OrderRouter (normal risk gates apply).
 */
export function DeactivationModal({ strategyId, strategyName, onClose, onDeactivated }: Props) {
  const [liquidate, setLiquidate] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDeactivate() {
    setSubmitting(true);
    setError(null);
    try {
      const result = await activationApi.deactivate(strategyId, liquidate);
      onDeactivated();
      if (result.liquidation_orders.length > 0) {
        window.alert(
          `Deactivated. ${result.liquidation_orders.length} liquidation order(s) submitted.`,
        );
      }
    } catch {
      setError("Deactivation failed. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80">
      <div className="w-96 space-y-3 rounded-lg border-2 border-amber-700 bg-neutral-950 p-5">
        <h2 className="text-lg font-semibold text-amber-100">Deactivate strategy</h2>
        <p className="text-sm text-neutral-300">
          <code className="font-mono">{strategyName}</code> will transition LIVE → IDLE and
          stop submitting orders.
        </p>
        <label className="flex items-center gap-2 text-sm text-amber-200">
          <input
            type="checkbox"
            checked={liquidate}
            onChange={(e) => setLiquidate(e.target.checked)}
          />
          Also liquidate open positions in this strategy&apos;s symbols
        </label>
        <p className="text-[10px] text-amber-300">
          {liquidate
            ? "Closing market orders will be submitted for each open position. Submissions go through the normal risk gates."
            : "Open positions stay open. Close manually if needed."}
        </p>
        {error && (
          <div className="rounded border border-red-700 bg-red-950/40 p-2 text-xs text-red-200">
            {error}
          </div>
        )}
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="rounded bg-neutral-700 px-3 py-1.5 text-sm text-neutral-200"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleDeactivate}
            disabled={submitting}
            className="rounded bg-amber-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-amber-600 disabled:bg-neutral-700"
          >
            {submitting ? "Deactivating…" : "Deactivate"}
          </button>
        </div>
      </div>
    </div>
  );
}
