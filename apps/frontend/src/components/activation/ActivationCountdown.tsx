import { useEffect, useState } from "react";
import { activationApi } from "@/api/activation";

interface Props {
  strategyId: number;
}

/**
 * P5 §7 — banner shown on the strategy detail page while a strategy is
 * PENDING_LIVE (24h activation cooldown, ADR 0005). Shows time-to-live and a
 * frictionless cancel. Plain useEffect polling (the detail page has no
 * QueryClientProvider). Renders nothing once the cooldown has elapsed.
 */
export function ActivationCountdown({ strategyId }: Props) {
  const [status, setStatus] = useState<{
    seconds_remaining: number;
    completes_at: string | null;
  } | null>(null);
  const [canceling, setCanceling] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function refresh() {
      try {
        const s = await activationApi.status(strategyId);
        if (!cancelled) setStatus(s);
      } catch {
        /* silent — the banner is non-critical */
      }
    }
    refresh();
    const id = setInterval(refresh, 30_000); // countdown is in hours
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [strategyId]);

  async function handleCancel() {
    if (!window.confirm("Cancel activation? The strategy returns to IDLE.")) return;
    setCanceling(true);
    try {
      await activationApi.cancelActivation(strategyId);
      window.location.reload();
    } finally {
      setCanceling(false);
    }
  }

  if (!status || status.seconds_remaining <= 0) return null;

  const hours = Math.floor(status.seconds_remaining / 3600);
  const minutes = Math.floor((status.seconds_remaining % 3600) / 60);

  return (
    <div className="rounded border-2 border-amber-700 bg-amber-950/40 p-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-amber-100">
            ⏳ Activation pending — {hours}h {minutes}m remaining
          </div>
          <div className="mt-1 text-[10px] text-amber-300">
            Goes LIVE at{" "}
            {status.completes_at && new Date(status.completes_at).toLocaleString()}. Cancel
            anytime before then.
          </div>
        </div>
        <button
          type="button"
          onClick={handleCancel}
          disabled={canceling}
          className="rounded border border-amber-700 px-3 py-1.5 text-xs text-amber-100 hover:bg-amber-900/30 disabled:opacity-50"
        >
          {canceling ? "Canceling…" : "Cancel"}
        </button>
      </div>
    </div>
  );
}
