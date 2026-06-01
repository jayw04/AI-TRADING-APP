import { useEffect, useState } from "react";
import { strategiesApi } from "@/api/strategies";

interface Props {
  strategyId: number;
}

interface CooldownState {
  in_cooldown: boolean;
  cooldown_until: string | null;
  seconds_remaining: number;
}

/**
 * P5 §6 — countdown badge shown on the strategy detail page while the strategy
 * is in cooldown (set after a failed order submission). Renders nothing when
 * not in cooldown. Polls every 1s while counting down, 30s otherwise.
 *
 * Plain useEffect polling (not React Query) to match the strategy detail page,
 * which manages its own data without a QueryClientProvider.
 */
export function CooldownIndicator({ strategyId }: Props) {
  const [status, setStatus] = useState<CooldownState | null>(null);
  const [clearing, setClearing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function refresh() {
      try {
        const s = await strategiesApi.cooldownStatus(strategyId);
        if (!cancelled) setStatus(s);
      } catch {
        /* best-effort; the badge is non-critical */
      }
    }
    refresh();
    const interval = status?.in_cooldown ? 1_000 : 30_000;
    const id = setInterval(refresh, interval);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [strategyId, status?.in_cooldown]);

  async function handleClear() {
    setClearing(true);
    try {
      await strategiesApi.clearCooldown(strategyId);
      const s = await strategiesApi.cooldownStatus(strategyId);
      setStatus(s);
    } catch {
      /* ignore */
    } finally {
      setClearing(false);
    }
  }

  if (!status || !status.in_cooldown) return null;

  return (
    <div className="rounded border border-amber-700 bg-amber-950/30 p-2">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-xs font-semibold text-amber-100">⏸ Cooldown active</div>
          <div className="mt-0.5 text-[10px] text-amber-300">
            {status.seconds_remaining}s remaining — automatic resume. Triggered by a
            failed order submission.
          </div>
        </div>
        <button
          type="button"
          onClick={handleClear}
          disabled={clearing}
          className="rounded border border-amber-700 px-2 py-1 text-[10px] text-amber-100 hover:bg-amber-900/30 disabled:opacity-50"
        >
          {clearing ? "Clearing…" : "Clear now"}
        </button>
      </div>
    </div>
  );
}
