import { useEffect, useState } from "react";
import {
  strategyAuthoringApi,
  type AuthoringStatus,
} from "@/api/strategyAuthoring";

/**
 * P7 §7 (Decision 5) — "AI-authored" / manual-edit notice on the strategy detail
 * page. Renders nothing for manually-authored strategies. For AI-authored ones,
 * shows an "AI-authored" line, plus an amber warning when the on-disk code has
 * been manually edited since it was authored (the AI won't see those edits in a
 * future conversation). Plain useState/useEffect (no QueryClientProvider here).
 */
export function AuthoringNotice({ strategyId }: { strategyId: number }) {
  const [status, setStatus] = useState<AuthoringStatus | null>(null);

  useEffect(() => {
    let alive = true;
    strategyAuthoringApi
      .status(strategyId)
      .then((s) => alive && setStatus(s))
      .catch(() => alive && setStatus(null));
    return () => {
      alive = false;
    };
  }, [strategyId]);

  if (status === null || status.authoring_method === "manual") return null;

  const label =
    status.authoring_method === "nl_refinement"
      ? "AI-authored (refined)"
      : "AI-authored";

  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-3">
      <div className="text-xs font-medium text-neutral-300">✨ {label}</div>
      {status.out_of_sync && (
        <div className="mt-2 rounded border border-amber-800 bg-amber-950/30 p-2 text-xs text-amber-200">
          This strategy's code has been manually edited since it was AI-authored. The
          AI won't see these edits in future conversations — its authoring history no
          longer matches the code on disk.
        </div>
      )}
    </div>
  );
}
