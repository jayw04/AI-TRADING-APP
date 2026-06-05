import { useCallback, useEffect, useState } from "react";
import type { Strategy } from "@/api/types";
import {
  llmOptInApi,
  RISK_ACK_PHRASE,
  type LLMOptInStatus,
} from "@/api/llmOptIn";
import { ApiError } from "@/api/client";

interface Props {
  strategy: Strategy;
}

/**
 * P6b §5 (ADR 0006 v2 §5) — LLM-driven live trading opt-in card. Renders only for
 * a LIVE strategy with an eval harness. States:
 *   - ineligible: shows the §4 double-floor progress; no opt-in control.
 *   - eligible (none): typed-ack + TOTP + a prominent risk disclosure → opt in.
 *   - pending: "activates in N days" + Opt-out.
 *   - active: "$X.XX / $Y.YY today" + Opt-out.
 *
 * Plain useState/useEffect (the detail page has no QueryClientProvider — matches
 * DriftCard / VariantCard). Opting in is ALWAYS user-gated; never auto-enabled.
 */
export function LLMOptInCard({ strategy }: Props) {
  const [st, setSt] = useState<LLMOptInStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setSt(await llmOptInApi.status(strategy.id));
    } catch {
      setSt(null);
    } finally {
      setLoading(false);
    }
  }, [strategy.id]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  if (loading || st === null) return null;
  // No harness at all → nothing to show (the §4 eval hasn't started).
  if (st.eligibility === null && st.status === "none") return null;

  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-4">
      <div className="text-sm font-semibold text-neutral-100">
        LLM-driven live trading
      </div>

      {st.status === "active" && <ActiveView st={st} onChanged={refresh} strategyId={strategy.id} />}
      {st.status === "pending" && <PendingView st={st} onChanged={refresh} strategyId={strategy.id} />}
      {st.status === "none" && st.eligibility !== null && (
        st.eligibility.eligible ? (
          <EligibleView strategyId={strategy.id} onChanged={refresh} />
        ) : (
          <IneligibleView st={st} />
        )
      )}
    </div>
  );
}

function IneligibleView({ st }: { st: LLMOptInStatus }) {
  const e = st.eligibility!;
  return (
    <p className="mt-2 text-xs text-neutral-400">
      Not yet eligible — the LLM eval harness must run on paper first:{" "}
      <span className="text-neutral-200">
        {e.b_trade_count}/{e.min_trades} Mode-B trades, {e.window_days}/{e.min_days} days
      </span>
      . Opt-in unlocks once both floors are met.
    </p>
  );
}

function EligibleView({
  strategyId,
  onChanged,
}: {
  strategyId: number;
  onChanged: () => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2">
      <p className="text-xs text-neutral-400">
        Eligible. Opting in lets this strategy's <span className="text-amber-200">live</span>{" "}
        orders pass through an LLM act/skip gate after a 7-day cooldown. You can opt out
        anytime.
      </p>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="mt-3 rounded border border-red-700 px-3 py-1.5 text-sm font-semibold text-red-100 hover:bg-red-900/30"
      >
        Opt in to LLM-driven trading…
      </button>
      {open && (
        <OptInModal
          strategyId={strategyId}
          onClose={() => setOpen(false)}
          onDone={() => {
            setOpen(false);
            onChanged();
          }}
        />
      )}
    </div>
  );
}

function PendingView({
  st,
  strategyId,
  onChanged,
}: {
  st: LLMOptInStatus;
  strategyId: number;
  onChanged: () => void;
}) {
  const days = Math.ceil((st.seconds_remaining ?? 0) / 86400);
  return (
    <div className="mt-2">
      <p className="text-xs text-amber-200">
        Activating in ~{days} day{days === 1 ? "" : "s"} (7-day cooldown). Live orders stay
        deterministic until then.
      </p>
      <OptOutButton strategyId={strategyId} onChanged={onChanged} />
    </div>
  );
}

function ActiveView({
  st,
  strategyId,
  onChanged,
}: {
  st: LLMOptInStatus;
  strategyId: number;
  onChanged: () => void;
}) {
  const spent = ((st.spend_today_cents ?? 0) / 100).toFixed(2);
  const cap = ((st.daily_cap_cents ?? 0) / 100).toFixed(2);
  return (
    <div className="mt-2">
      <p className="text-xs text-red-200">
        LLM-gating live orders · ${spent} / ${cap} today
      </p>
      <OptOutButton strategyId={strategyId} onChanged={onChanged} />
    </div>
  );
}

function OptOutButton({
  strategyId,
  onChanged,
}: {
  strategyId: number;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  return (
    <button
      type="button"
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        try {
          await llmOptInApi.optOut(strategyId);
          onChanged();
        } finally {
          setBusy(false);
        }
      }}
      className="mt-3 rounded border border-neutral-700 px-3 py-1.5 text-sm font-semibold text-neutral-200 hover:bg-neutral-800"
    >
      {busy ? "Opting out…" : "Opt out"}
    </button>
  );
}

function OptInModal({
  strategyId,
  onClose,
  onDone,
}: {
  strategyId: number;
  onClose: () => void;
  onDone: () => void;
}) {
  const [ack, setAck] = useState("");
  const [totp, setTotp] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ackOk = ack.trim().toLowerCase() === RISK_ACK_PHRASE.toLowerCase();

  async function handleOptIn() {
    setSubmitting(true);
    setError(null);
    try {
      await llmOptInApi.optIn(strategyId, ack, totp);
      onDone();
    } catch (e) {
      setError(
        e instanceof ApiError && (e.status === 400 || e.status === 401 || e.status === 409)
          ? "Rejected — check the acknowledgment phrase and TOTP code."
          : "Opt-in failed.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80">
      <div className="w-[28rem] space-y-3 rounded-lg border-2 border-red-700 bg-neutral-950 p-5">
        <h2 className="text-lg font-semibold text-red-100">
          Opt in to LLM-driven live trading
        </h2>
        <p className="text-xs text-amber-200">
          An LLM will decide whether to act on each live order this strategy generates.
          It is non-deterministic and can suppress trades. A 7-day cooldown applies; you
          can opt out anytime. Type the exact phrase and your TOTP code to confirm.
        </p>
        <div className="rounded bg-neutral-900 p-2 text-xs text-neutral-400">
          {RISK_ACK_PHRASE}
        </div>
        <input
          type="text"
          value={ack}
          onChange={(e) => setAck(e.target.value)}
          placeholder="type the acknowledgment phrase"
          className="w-full rounded bg-neutral-800 px-2 py-1.5 text-sm text-white"
        />
        <input
          type="text"
          inputMode="numeric"
          value={totp}
          onChange={(e) => setTotp(e.target.value.replace(/\D/g, ""))}
          placeholder="TOTP code"
          maxLength={8}
          className="w-full rounded bg-neutral-800 px-2 py-1.5 font-mono text-sm text-white"
          autoComplete="one-time-code"
        />
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
            onClick={handleOptIn}
            disabled={submitting || !ackOk || totp.length < 6}
            className="rounded bg-red-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-red-600 disabled:bg-neutral-700"
          >
            {submitting ? "Opting in…" : "Opt in"}
          </button>
        </div>
      </div>
    </div>
  );
}
